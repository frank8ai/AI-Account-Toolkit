"""
ChatGPT 批量注册工具 — Web 管理界面
Flask 后端: 配置管理 / 任务控制 / SSE 实时日志 / 账号管理 / OAuth 导出
"""

import os
import io
import csv
import json
import time
import queue
import zipfile
import threading
from datetime import datetime
from flask import Flask, request, jsonify, Response, render_template, send_file

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
ACCOUNTS_FILE = os.path.join(BASE_DIR, "registered_accounts.txt")
ACCOUNTS_CSV = os.path.join(BASE_DIR, "registered_accounts.csv")
AK_FILE = os.path.join(BASE_DIR, "ak.txt")
RK_FILE = os.path.join(BASE_DIR, "rk.txt")
TOKEN_DIR = os.path.join(BASE_DIR, "codex_tokens")

# ── Task state ──────────────────────────────────────────────
_task_lock = threading.Lock()
_task_running = False
_task_progress = {"total": 0, "done": 0, "success": 0, "fail": 0}

# ── Keepalive state ───────────────────────────────────────
_keepalive_lock = threading.Lock()
_keepalive_running = False
_keepalive_stop_event = threading.Event()
_keepalive_status = {
    "last_run": None,
    "next_run": None,
    "last_result": None,
}

# ── SSE log broadcast ──────────────────────────────────────
_log_subscribers: list[queue.Queue] = []
_log_lock = threading.Lock()
_log_queue = queue.Queue(maxsize=50000)  # 中央日志队列，工作线程只写这里

def _broadcast_log(line: str):
    """高并发安全：只做一次 queue.put，不持有 _log_lock"""
    try:
        _log_queue.put_nowait(line)
    except queue.Full:
        # 队列满时丢弃最旧
        try:
            _log_queue.get_nowait()
        except queue.Empty:
            pass
        try:
            _log_queue.put_nowait(line)
        except queue.Full:
            pass

def _log_dispatcher():
    """专用分发线程：从中央队列批量读取，分发给所有 SSE 订阅者"""
    while True:
        try:
            msg = _log_queue.get(timeout=1)
        except queue.Empty:
            continue
        batch = [msg]
        # 批量取出，减少锁持有次数
        while len(batch) < 500:
            try:
                batch.append(_log_queue.get_nowait())
            except queue.Empty:
                break
        with _log_lock:
            for q in _log_subscribers:
                for m in batch:
                    if q.full():
                        try:
                            q.get_nowait()
                        except queue.Empty:
                            pass
                    try:
                        q.put_nowait(m)
                    except queue.Full:
                        pass

threading.Thread(target=_log_dispatcher, daemon=True, name="log-dispatcher").start()

class _LogCapture(io.TextIOBase):
    """Captures print() output and broadcasts via SSE while also writing to real stdout."""
    def __init__(self, real_stdout):
        self._real = real_stdout
    def write(self, s):
        if s and s.strip():
            _broadcast_log(s.rstrip("\n\r"))
        return self._real.write(s)
    def flush(self):
        return self._real.flush()

# ── Config helpers ──────────────────────────────────────────
def _read_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def _write_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)

# ── Account helpers ─────────────────────────────────────────
def _parse_accounts():
    accounts = []
    seen_emails = set()

    # 1. 从 registered_accounts.txt 读取
    if os.path.exists(ACCOUNTS_FILE):
        with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                parts = line.split("----")
                email = parts[0] if len(parts) > 0 else ""
                acc = {
                    "index": i,
                    "email": email,
                    "password": parts[1] if len(parts) > 1 else "",
                    "email_password": parts[2] if len(parts) > 2 else "",
                    "oauth_status": parts[3] if len(parts) > 3 else "",
                    "raw": line,
                }
                accounts.append(acc)
                if email:
                    seen_emails.add(email.lower())

    # 2. 从 codex_tokens/ 补充仅有 token 文件但不在 txt 中的账号
    if os.path.isdir(TOKEN_DIR):
        for fname in sorted(os.listdir(TOKEN_DIR)):
            if not fname.endswith(".json") or not os.path.isfile(os.path.join(TOKEN_DIR, fname)):
                continue
            name = fname[:-5]  # 去掉 .json
            # 检查是否已在 registered_accounts.txt 中
            if any(name.lower() in e for e in seen_emails):
                continue
            idx = len(accounts)
            accounts.append({
                "index": idx,
                "email": name,
                "password": "",
                "email_password": "",
                "oauth_status": "token-only",
                "raw": name,
            })

    return accounts

def _write_accounts(accounts):
    with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
        for acc in accounts:
            f.write(acc["raw"] + "\n")


# ═══════════════════════════  ROUTES  ═══════════════════════

@app.route("/")
def index():
    return render_template("index.html")


# ── Config ──────────────────────────────────────────────────
@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify(_read_config())

@app.route("/api/config", methods=["POST"])
def save_config():
    cfg = request.get_json(force=True)
    _write_config(cfg)
    return jsonify({"ok": True})


# ── Task control ────────────────────────────────────────────
import multiprocessing

def _task_subprocess(log_q, count, workers, proxy):
    """在子进程里运行注册任务，stdout 重定向到 log_q"""
    import sys, io

    class _QueueWriter(io.TextIOBase):
        def __init__(self, real):
            self._real = real
        def write(self, s):
            if s and s.strip():
                for line in s.rstrip("\n\r").split("\n"):
                    if line.strip():
                        try:
                            log_q.put_nowait(line)
                        except:
                            pass
            return self._real.write(s)
        def flush(self):
            return self._real.flush()

    sys.stdout = _QueueWriter(sys.__stdout__)
    try:
        import importlib
        import config_loader
        importlib.reload(config_loader)
        config_loader.run_batch(
            total_accounts=count,
            output_file="registered_accounts.txt",
            max_workers=workers,
            proxy=proxy,
        )
    except Exception as e:
        print(f"❌ 任务异常: {e}")

_task_process = None
_task_log_queue = None

def _log_reader(log_q):
    """主进程里的读线程：从子进程的 queue 读日志，分发给 SSE"""
    global _task_running
    while True:
        try:
            msg = log_q.get(timeout=1)
            _broadcast_log(msg)
        except queue.Empty:
            if _task_process is None or not _task_process.is_alive():
                break
    # 子进程结束
    with _task_lock:
        _task_running = False
    _broadcast_log("__TASK_DONE__")


@app.route("/api/start", methods=["POST"])
def start_task():
    global _task_running, _task_process, _task_log_queue, _task_progress
    with _task_lock:
        if _task_running:
            return jsonify({"ok": False, "error": "任务正在运行中"}), 409

    body = request.get_json(force=True) or {}
    count = int(body.get("count", 1))
    workers = int(body.get("workers", 1))
    proxy = body.get("proxy", "").strip() or None

    _task_progress = {"total": count, "done": 0, "success": 0, "fail": 0}

    # macOS 对 BoundedSemaphore 有系统级上限，maxsize 不能过大
    _task_log_queue = multiprocessing.Queue(maxsize=1000)
    _task_process = multiprocessing.Process(
        target=_task_subprocess,
        args=(_task_log_queue, count, workers, proxy),
        daemon=True,
    )
    _task_running = True
    _task_process.start()
    # 读线程：桥接子进程日志到 SSE
    threading.Thread(target=_log_reader, args=(_task_log_queue,), daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/stop", methods=["POST"])
def stop_task():
    global _task_running, _task_process
    if _task_process and _task_process.is_alive():
        _task_process.kill()   # SIGKILL，立即终止子进程及其所有线程
        _task_process.join(timeout=2)
        _task_process = None
    with _task_lock:
        _task_running = False
    _broadcast_log("⚠️ 任务已停止")
    _broadcast_log("__TASK_DONE__")
    return jsonify({"ok": True})


@app.route("/api/status", methods=["GET"])
def task_status():
    return jsonify({
        "running": _task_running,
        "progress": _task_progress,
    })


# ── SSE Logs ────────────────────────────────────────────────
@app.route("/api/logs")
def sse_logs():
    q = queue.Queue(maxsize=2000)
    with _log_lock:
        _log_subscribers.append(q)

    def stream():
        try:
            while True:
                try:
                    msg = q.get(timeout=30)
                except queue.Empty:
                    yield ": keepalive\n\n"
                    continue
                # 批量取出队列中所有待发消息，合并为一次 yield（小批次快发）
                batch = [msg]
                while len(batch) < 50:
                    try:
                        batch.append(q.get_nowait())
                    except queue.Empty:
                        break
                yield "".join(f"data: {m}\n\n" for m in batch)
        except GeneratorExit:
            pass
        finally:
            with _log_lock:
                if q in _log_subscribers:
                    _log_subscribers.remove(q)

    return Response(stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Accounts ────────────────────────────────────────────────
@app.route("/api/accounts", methods=["GET"])
def list_accounts():
    return jsonify(_parse_accounts())


def _delete_token_file(email):
    """删除账号对应的 token JSON 文件"""
    if not email:
        return
    fname = f"{email}.json"
    fpath = os.path.join(TOKEN_DIR, fname)
    try:
        if os.path.isfile(fpath):
            os.remove(fpath)
    except Exception:
        pass


@app.route("/api/accounts", methods=["DELETE"])
def delete_accounts():
    body = request.get_json(force=True) or {}
    indices = set(body.get("indices", []))
    mode = body.get("mode", "selected")  # "all" or "selected"

    accounts = _parse_accounts()
    if mode == "all":
        # 清空 txt 文件，并删除所有 token JSON 文件
        _write_accounts([])
        for acc in accounts:
            _delete_token_file(acc.get("email", ""))
        return jsonify({"ok": True, "deleted": len(accounts)})

    # 找出要删除的账号，同步删除对应 token JSON 文件
    to_delete = [a for a in accounts if a["index"] in indices]
    for acc in to_delete:
        _delete_token_file(acc.get("email", ""))

    remaining = [a for a in accounts if a["index"] not in indices]
    # token-only 账号（raw 仅含邮箱）不写回 txt；只保留有完整记录的账号
    _write_accounts([a for a in remaining if a.get("oauth_status") != "token-only"])
    return jsonify({"ok": True, "deleted": len(to_delete)})


# ── OAuth Export ────────────────────────────────────────────
@app.route("/api/export", methods=["POST"])
def export_oauth():
    """
    Export individual <email>.json token files from codex_tokens/ as a ZIP.
    - mode: "all" → include every file in codex_tokens/
    - mode: "selected" → only include files whose content contains one of the selected emails
    """
    body = request.get_json(force=True) or {}
    mode = body.get("mode", "all")          # "all" or "selected"
    indices = set(body.get("indices", []))

    # Resolve the email list to filter against
    if mode == "selected":
        accounts = _parse_accounts()
        target_emails = {a["email"] for a in accounts if a["index"] in indices}
    else:
        target_emails = None  # None = include all

    if not os.path.isdir(TOKEN_DIR):
        return jsonify({"error": "codex_tokens 目录不存在"}), 404

    buf = io.BytesIO()
    exported = 0

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in sorted(os.listdir(TOKEN_DIR)):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(TOKEN_DIR, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as tf:
                    content = tf.read()
            except Exception:
                continue

            # Filtering: if selected mode, check if this file's email matches
            if target_emails is not None:
                # Try to match by filename (email is the filename stem)
                stem = fname[:-5]  # remove .json
                matched = any(em in stem or em in content for em in target_emails)
                if not matched:
                    continue

            # Write directly at ZIP root: <email>.json
            zf.writestr(fname, content)
            exported += 1

    if exported == 0:
        return jsonify({"error": f"没有找到匹配的 Token 文件（共扫描 codex_tokens/）"}), 404

    buf.seek(0)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"codex_tokens_{ts}.zip"
    )


# ── CPA 池状态 ──────────────────────────────────────────────
@app.route("/api/pool-status", methods=["GET"])
def pool_status():
    """获取 CPA 池状态: 远程总数 + 本地总数"""
    cfg = _read_config()
    base_url = (cfg.get("SUB2API_URL") or "").strip().rstrip("/")
    token = (cfg.get("SUB2API_TOKEN") or "").strip()
    proxy = (cfg.get("proxy") or "").strip()
    target_count = int(cfg.get("pool_target", 2000))
    if not base_url or not token:
        return jsonify({"ok": False, "error": "未配置 CPA"}), 400
    try:
        import requests as std_requests
        s = std_requests.Session()
        s.verify = False
        if proxy:
            p = proxy if "://" in proxy else f"http://{proxy}"
            s.proxies = {"http": p, "https": p}
        url = f"{base_url}/v0/management/auth-files"
        resp = s.get(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}, timeout=15)
        resp.raise_for_status()
        raw = resp.json()
        files = raw.get("files", []) if isinstance(raw, dict) else []
        remote = len(files)
        local = 0
        if os.path.isdir(TOKEN_DIR):
            local = len([f for f in os.listdir(TOKEN_DIR) if f.endswith(".json") and os.path.isfile(os.path.join(TOKEN_DIR, f))])
        return jsonify({"ok": True, "remote": remote, "local": local})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── CPA 同步 ────────────────────────────────────────────────

def _cpa_config():
    cfg = _read_config()
    # 仅当 cpa_use_proxy 为 True 时才将代理传给 CPA 会话，避免忽略用户配置
    raw_proxy = (cfg.get("proxy") or "").strip()
    proxy = raw_proxy if cfg.get("cpa_use_proxy") else ""
    return (
        (cfg.get("SUB2API_URL") or "").strip().rstrip("/"),
        (cfg.get("SUB2API_TOKEN") or "").strip(),
        proxy,
    )

def _cpa_session(proxy=""):
    import requests as std_requests
    s = std_requests.Session()
    s.verify = False
    if proxy:
        p = proxy if "://" in proxy else f"http://{proxy}"
        s.proxies = {"http": p, "https": p}
    return s

def _is_codex_token(filepath):
    """读取本地 token JSON，判断是否为 codex 类型凭证"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("type") == "codex"
    except Exception:
        return False


def _fetch_remote_files(base_url, token, proxy=""):
    """获取 CPA 远程文件列表, 返回 {name_without_json: file_dict}"""
    url = f"{base_url}/v0/management/auth-files"
    s = _cpa_session(proxy)
    resp = s.get(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}, timeout=15)
    resp.raise_for_status()
    raw = resp.json()
    files = raw.get("files", []) if isinstance(raw, dict) else []
    result = {}
    for f in files:
        n = f.get("name", "")
        key = n[:-5] if n.endswith(".json") else n
        result[key] = f
    return result

def _build_sync_status(base_url, token, proxy=""):
    """对比本地与远程, 返回同步状态"""
    local_names = set()
    if os.path.isdir(TOKEN_DIR):
        for f in os.listdir(TOKEN_DIR):
            if f.endswith(".json"):
                fpath = os.path.join(TOKEN_DIR, f)
                # 仅同步 codex 类型凭证，跳过其他类型
                if os.path.isfile(fpath) and _is_codex_token(fpath):
                    local_names.add(f[:-5])

    remote_map = _fetch_remote_files(base_url, token, proxy)
    remote_names = set(remote_map.keys())
    all_names = local_names | remote_names

    accounts = []
    summary = {"synced": 0, "pending_upload": 0, "remote_only": 0}
    for name in sorted(all_names):
        in_local = name in local_names
        in_remote = name in remote_names
        if in_local and in_remote:
            status, location = "synced", "both"
        elif in_local and not in_remote:
            status, location = "pending_upload", "local"
        else:
            status, location = "remote_only", "remote"
        summary[status] = summary.get(status, 0) + 1
        accounts.append({"name": name, "status": status, "location": location})

    # 排序: pending_upload → remote_only → synced
    order = {"pending_upload": 0, "remote_only": 1, "synced": 2}
    accounts.sort(key=lambda x: order.get(x["status"], 99))
    return {"accounts": accounts, "summary": summary, "local": len(local_names), "remote": len(remote_names)}


@app.route("/api/sync-status", methods=["GET"])
def sync_status():
    """获取 CPA 同步状态"""
    base_url, token, proxy = _cpa_config()
    if not base_url or not token:
        return jsonify({"ok": False, "error": "请先配置 CPA 地址和 Token"}), 400
    try:
        result = _build_sync_status(base_url, token, proxy)
        return jsonify({"ok": True, **result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/sync-cpa", methods=["POST"])
def sync_cpa():
    """双向同步: 上传本地独有 + 下载远程独有（后台线程 + 实时日志）"""
    global _task_running
    with _task_lock:
        if _task_running:
            return jsonify({"ok": False, "error": "有任务正在运行中"}), 409

    base_url, token, proxy = _cpa_config()
    if not base_url or not token:
        return jsonify({"ok": False, "error": "请先配置 CPA 地址和 Token"}), 400

    def _run_sync():
        global _task_running
        import requests as std_requests
        import concurrent.futures

        api_base = f"{base_url}/v0/management/auth-files"
        lock = threading.Lock()

        _broadcast_log(f"[CPA 同步] 正在查询同步状态...")

        # ── 1. 获取同步状态 ──
        try:
            sync_info = _build_sync_status(base_url, token, proxy)
        except Exception as e:
            _broadcast_log(f"[CPA 同步] ❌ 获取同步状态失败: {e}")
            with _task_lock:
                _task_running = False
            _broadcast_log("__TASK_DONE__")
            return

        summary = sync_info["summary"]
        _broadcast_log(f"[CPA 同步] 本地 {sync_info['local']} 个, 远程 {sync_info['remote']} 个 | "
                       f"已同步 {summary['synced']}, 待上传 {summary['pending_upload']}, 仅远程 {summary['remote_only']}")

        to_upload = [a["name"] for a in sync_info["accounts"] if a["status"] == "pending_upload"]
        to_download = [a["name"] for a in sync_info["accounts"] if a["status"] == "remote_only"]

        if not to_upload and not to_download:
            _broadcast_log("[CPA 同步] ✅ 全部已同步，无需操作")
            with _task_lock:
                _task_running = False
            _broadcast_log("__TASK_DONE__")
            return

        uploaded = 0
        downloaded = 0
        failed = 0

        # ── 2. 上传本地独有文件 ──
        if to_upload:
            _broadcast_log(f"[CPA 同步] 开始上传 {len(to_upload)} 个本地文件...")

            def upload_one(name):
                nonlocal uploaded, failed
                fname = f"{name}.json"
                fpath = os.path.join(TOKEN_DIR, fname)
                try:
                    s = _cpa_session(proxy)
                    with open(fpath, "rb") as f:
                        data = f.read()
                    r = s.post(api_base,
                               files={"file": (fname, data, "application/json")},
                               headers={"Authorization": f"Bearer {token}"},
                               timeout=15)
                    with lock:
                        if r.status_code in (200, 201):
                            uploaded += 1
                            _broadcast_log(f"  ⬆️ 上传成功: {name}")
                        elif r.status_code == 409:
                            _broadcast_log(f"  ⏭️ 已存在跳过: {name}")
                        else:
                            failed += 1
                            _broadcast_log(f"  ❌ 上传失败: {name} ({r.status_code})")
                except Exception as e:
                    with lock:
                        failed += 1
                        _broadcast_log(f"  ❌ 上传异常: {name} - {e}")

            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
                list(ex.map(upload_one, to_upload))

        # ── 3. 下载远程独有文件 ──
        if to_download:
            _broadcast_log(f"[CPA 同步] 开始下载 {len(to_download)} 个远程文件...")
            os.makedirs(TOKEN_DIR, exist_ok=True)

            def download_one(name):
                nonlocal downloaded, failed
                fname = f"{name}.json"
                try:
                    s = _cpa_session(proxy)
                    r = s.get(f"{api_base}/download",
                              params={"name": fname},
                              headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                              timeout=15)
                    r.raise_for_status()
                    acc_data = r.json()
                    # 仅保存 codex 类型凭证，跳过其他类型
                    if acc_data.get("type") != "codex":
                        _broadcast_log(f"  ⏭️ 跳过非 codex 类型: {name}")
                        return
                    dst = os.path.join(TOKEN_DIR, fname)
                    with open(dst, "w", encoding="utf-8") as f:
                        json.dump(acc_data, f, ensure_ascii=False, indent=2)
                    with lock:
                        downloaded += 1
                        _broadcast_log(f"  ⬇️ 下载成功: {name}")
                except Exception as e:
                    with lock:
                        failed += 1
                        _broadcast_log(f"  ❌ 下载失败: {name} - {e}")

            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
                list(ex.map(download_one, to_download))

        _broadcast_log(f"[CPA 同步] 完成: ⬆️ {uploaded} 上传, ⬇️ {downloaded} 下载, ❌ {failed} 失败")
        with _task_lock:
            _task_running = False
        _broadcast_log("__TASK_DONE__")

    _task_running = True
    threading.Thread(target=_run_sync, daemon=True).start()
    return jsonify({"ok": True})


# ── Keepalive ──────────────────────────────────────────────

def _keepalive_loop():
    """保活主循环：定时检测 → 清理 → 注册补充 → CPA同步"""
    global _keepalive_running
    import concurrent.futures
    import requests as std_requests

    while not _keepalive_stop_event.is_set():
        # 每轮开始时重新读取配置（支持热更新）
        cfg = _read_config()
        interval = max(int(cfg.get("keepalive_interval", 3600)), 300)
        target = int(cfg.get("keepalive_target_count", 20))
        base_url = (cfg.get("SUB2API_URL") or "").strip().rstrip("/")
        token = (cfg.get("SUB2API_TOKEN") or "").strip()
        raw_proxy = (cfg.get("proxy") or "").strip()
        cpa_proxy = raw_proxy if cfg.get("cpa_use_proxy") else ""
        has_cpa = bool(base_url and token)

        from datetime import datetime, timedelta
        now = datetime.now()
        _keepalive_status["last_run"] = now.strftime("%Y-%m-%dT%H:%M:%S")
        _keepalive_status["next_run"] = (now + timedelta(seconds=interval)).strftime("%Y-%m-%dT%H:%M:%S")

        _broadcast_log(f"[保活] ═══ 保活周期开始 ═══")
        _broadcast_log(f"[保活] 目标数量: {target} | 间隔: {interval}s | CPA: {'已配置' if has_cpa else '未配置'}")

        # ── 1. 从 CPA 拉取远程账号到本地 ──
        if has_cpa:
            try:
                _broadcast_log("[保活] 步骤1: 从 CPA 同步远程账号...")
                sync_info = _build_sync_status(base_url, token, cpa_proxy)
                to_download = [a["name"] for a in sync_info["accounts"] if a["status"] == "remote_only"]
                if to_download:
                    os.makedirs(TOKEN_DIR, exist_ok=True)
                    downloaded = 0
                    s = _cpa_session(cpa_proxy)
                    api_url = f"{base_url}/v0/management/auth-files"
                    for name in to_download:
                        fname = f"{name}.json"
                        try:
                            r = s.get(f"{api_url}/download",
                                      params={"name": fname},
                                      headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                                      timeout=15)
                            r.raise_for_status()
                            acc_data = r.json()
                            if acc_data.get("type") != "codex":
                                continue
                            dst = os.path.join(TOKEN_DIR, fname)
                            with open(dst, "w", encoding="utf-8") as f:
                                json.dump(acc_data, f, ensure_ascii=False, indent=2)
                            downloaded += 1
                        except Exception:
                            pass
                    _broadcast_log(f"[保活] 从 CPA 下载了 {downloaded} 个新账号")
                else:
                    _broadcast_log(f"[保活] CPA 远程 {sync_info['remote']} 个账号已全部同步到本地，无需下载")
            except Exception as e:
                _broadcast_log(f"[保活] ⚠️ CPA 同步失败，跳过: {e}")

        # ── 2. 检测存活（refresh_token 刷新） ──
        _broadcast_log("[保活] 步骤2: 检测账号存活状态...")
        local_tokens = []
        if os.path.isdir(TOKEN_DIR):
            for fname in os.listdir(TOKEN_DIR):
                if fname.endswith(".json"):
                    fpath = os.path.join(TOKEN_DIR, fname)
                    if os.path.isfile(fpath) and _is_codex_token(fpath):
                        local_tokens.append(fpath)

        alive_list = []
        dead_list = []

        if local_tokens:
            from config_loader import refresh_one_token

            def _check_one(fpath):
                result = refresh_one_token(fpath)
                email = os.path.basename(fpath)[:-5]
                return (fpath, email, result is not None)

            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
                futures = {ex.submit(_check_one, fp): fp for fp in local_tokens}
                for future in concurrent.futures.as_completed(futures):
                    try:
                        fpath, email, is_alive = future.result()
                        if is_alive:
                            alive_list.append(email)
                        else:
                            dead_list.append((fpath, email))
                    except Exception:
                        fp = futures[future]
                        dead_list.append((fp, os.path.basename(fp)[:-5]))

        _broadcast_log(f"[保活] 检测完成: 存活 {len(alive_list)} | 死亡 {len(dead_list)}")

        # ── 3. 删除死亡账号 ──
        if dead_list:
            _broadcast_log(f"[保活] 步骤3: 清理 {len(dead_list)} 个死亡账号...")
            for fpath, email in dead_list:
                # 删除本地 token 文件
                try:
                    os.remove(fpath)
                    _broadcast_log(f"[保活]   🗑 删除本地: {email}")
                except Exception:
                    pass

                # CPA 远程删除
                if has_cpa:
                    try:
                        s = _cpa_session(cpa_proxy)
                        fname = f"{email}.json"
                        del_url = f"{base_url}/v0/management/auth-files"
                        r = s.delete(del_url,
                                     params={"name": fname},
                                     headers={"Authorization": f"Bearer {token}"},
                                     timeout=15)
                        if r.status_code in (200, 204, 404):
                            _broadcast_log(f"[保活]   🗑 删除远程: {email}")
                        else:
                            _broadcast_log(f"[保活]   ⚠️ 远程删除失败: {email} ({r.status_code})")
                    except Exception as e:
                        _broadcast_log(f"[保活]   ⚠️ 远程删除异常: {email} - {e}")

            # 清理 registered_accounts.txt 中的死亡账号记录
            dead_emails = {email for _, email in dead_list}
            if os.path.exists(ACCOUNTS_FILE):
                try:
                    with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                    remaining = [l for l in lines if l.strip() and l.strip().split("----")[0] not in dead_emails]
                    with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
                        f.writelines(remaining)
                except Exception:
                    pass
        else:
            _broadcast_log("[保活] 步骤3: 无死亡账号需清理")

        # ── 4. 注册补充 ──
        alive_count = len(alive_list)
        gap = target - alive_count
        registered = 0

        if gap > 0 and target > 0:
            _broadcast_log(f"[保活] 步骤4: 需补充 {gap} 个账号 (存活 {alive_count} / 目标 {target})")
            try:
                # 复用模块级 _task_subprocess（避免嵌套函数无法 pickle 的问题）
                reg_log_q = multiprocessing.Queue(maxsize=1000)
                proxy = raw_proxy or None

                reg_process = multiprocessing.Process(
                    target=_task_subprocess,
                    args=(reg_log_q, gap, min(gap, 3), proxy),
                    daemon=True,
                )
                reg_process.start()

                # 读取注册子进程日志并广播（加 [保活] 前缀）
                while reg_process.is_alive() or not reg_log_q.empty():
                    if _keepalive_stop_event.is_set():
                        reg_process.kill()
                        reg_process.join(timeout=2)
                        _broadcast_log("[保活] ⚠️ 保活已停止，注册补充中断")
                        break
                    try:
                        msg = reg_log_q.get(timeout=1)
                        _broadcast_log(f"[保活] {msg}")
                    except Exception:
                        pass

                reg_process.join(timeout=5)
                # 统计注册后的实际新增数量
                new_count = 0
                if os.path.isdir(TOKEN_DIR):
                    for fname in os.listdir(TOKEN_DIR):
                        if fname.endswith(".json"):
                            fpath = os.path.join(TOKEN_DIR, fname)
                            if os.path.isfile(fpath) and _is_codex_token(fpath):
                                new_count += 1
                registered = max(0, new_count - alive_count)
                _broadcast_log(f"[保活] 注册补充完成，新增 {registered} 个账号")

            except Exception as e:
                _broadcast_log(f"[保活] ❌ 注册补充异常: {e}")
        elif target > 0:
            _broadcast_log(f"[保活] 步骤4: 账号充足，无需补充 (存活 {alive_count} / 目标 {target})")
        else:
            _broadcast_log(f"[保活] 步骤4: 目标数为0，仅执行检测清理")

        # ── 5. 记录本轮结果 ──
        result = {
            "total_checked": len(local_tokens),
            "alive": len(alive_list),
            "dead": len(dead_list),
            "registered": registered,
        }
        _keepalive_status["last_result"] = result
        _broadcast_log(f"[保活] ═══ 本轮完成: 检测 {result['total_checked']} | 存活 {result['alive']} | "
                       f"死亡 {result['dead']} | 补充 {result['registered']} ═══")

        # ── 6. 休眠（可中断） ──
        _keepalive_stop_event.wait(timeout=interval)

    # 循环结束
    with _keepalive_lock:
        _keepalive_running = False
    _broadcast_log("[保活] 保活循环已停止")


def _start_keepalive():
    """启动保活后台线程"""
    global _keepalive_running
    with _keepalive_lock:
        if _keepalive_running:
            return False
        _keepalive_running = True
        _keepalive_stop_event.clear()
    t = threading.Thread(target=_keepalive_loop, daemon=True, name="keepalive")
    t.start()
    return True


def _stop_keepalive():
    """停止保活后台线程"""
    global _keepalive_running
    _keepalive_stop_event.set()
    # 状态会在循环退出时自动更新


@app.route("/api/keepalive/start", methods=["POST"])
def keepalive_start():
    ok = _start_keepalive()
    if ok:
        _broadcast_log("[保活] ✅ 保活功能已启动")
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "保活已在运行中"}), 409


@app.route("/api/keepalive/stop", methods=["POST"])
def keepalive_stop():
    _stop_keepalive()
    _broadcast_log("[保活] ⏹ 保活功能已停止")
    return jsonify({"ok": True})


@app.route("/api/keepalive/status", methods=["GET"])
def keepalive_status():
    return jsonify({
        "running": _keepalive_running,
        "last_run": _keepalive_status.get("last_run"),
        "next_run": _keepalive_status.get("next_run"),
        "last_result": _keepalive_status.get("last_result"),
    })


if __name__ == "__main__":
    multiprocessing.freeze_support()  # Windows 需要
    # 自动启动保活（如果配置启用）
    cfg = _read_config()
    if cfg.get("keepalive_enabled"):
        _start_keepalive()
        print("🔄 保活功能已自动启动")
    print("🚀 ChatGPT 注册管理面板启动: http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
