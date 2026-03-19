"""
ChatGPT 批量自动注册工具 (纯协议版) - DuckMail 临时邮箱 + Team 邀请 + Codex OAuth(CPA、SUB2API)
依赖: pip install curl_cffi
功能: 纯协议实现注册 → Team 邀请 → Codex OAuth 全流程，无需浏览器
"""

import os
import re
import uuid
import json
import random
import string
import time
import sys
import threading
import traceback
import secrets
import hashlib
import base64
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, parse_qs, urlencode

from curl_cffi import requests as curl_requests


# ================= 加载配置 =================
def _load_config():
    """从 config.json 加载配置，环境变量优先级更高"""
    config = {
        "total_accounts": 4,
        "mail_provider": "duckmail",
        "duckmail_api_base": "",
        "duckmail_domain": "",
        "duckmail_bearer": "",
        "cf_mail_api_base": "",
        "cf_mail_domain": "",
        "cf_mail_admin_password": "",
        "cf_mail_jwt_secret": "",
        "proxy": "",
        "output_file": "registered_accounts.txt",
        "csv_file": "registered_accounts.csv",
        "invite_tracker_file": "invite_tracker.json",
        "enable_oauth": True,
        "oauth_required": True,
        "oauth_issuer": "https://auth.openai.com",
        "oauth_client_id": "app_EMoamEEZ73f0CkXaXp7hrann",
        "oauth_redirect_uri": "http://localhost:1455/auth/callback",
        "ak_file": "ak.txt",
        "rk_file": "rk.txt",
        "token_json_dir": "codex_tokens",
        "upload_api_url": "",
        "upload_api_token": "",
        "SUB2API_URL": "",
        "SUB2API_TOKEN": "",
        "teams": [],
    }

    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                file_config = json.load(f)
                config.update(file_config)
        except Exception as e:
            print(f"⚠️ 加载 config.json 失败: {e}")

    config["mail_provider"] = os.environ.get("MAIL_PROVIDER", config["mail_provider"])
    config["duckmail_api_base"] = os.environ.get("DUCKMAIL_API_BASE", config["duckmail_api_base"])
    config["duckmail_bearer"] = os.environ.get("DUCKMAIL_BEARER", config["duckmail_bearer"])
    config["duckmail_domain"] = os.environ.get("DUCKMAIL_DOMAIN", config["duckmail_domain"])
    config["cf_mail_api_base"] = os.environ.get("CF_MAIL_API_BASE", config["cf_mail_api_base"])
    config["cf_mail_admin_password"] = os.environ.get("CF_MAIL_ADMIN_PASSWORD", config["cf_mail_admin_password"])
    config["cf_mail_jwt_secret"] = os.environ.get("CF_MAIL_JWT_SECRET", config["cf_mail_jwt_secret"])
    config["cf_mail_domain"] = os.environ.get("CF_MAIL_DOMAIN", config["cf_mail_domain"])
    config["proxy"] = os.environ.get("PROXY", config["proxy"])
    config["total_accounts"] = int(os.environ.get("TOTAL_ACCOUNTS", config["total_accounts"]))
    config["enable_oauth"] = os.environ.get("ENABLE_OAUTH", config["enable_oauth"])
    config["oauth_required"] = os.environ.get("OAUTH_REQUIRED", config["oauth_required"])
    config["oauth_issuer"] = os.environ.get("OAUTH_ISSUER", config["oauth_issuer"])
    config["oauth_client_id"] = os.environ.get("OAUTH_CLIENT_ID", config["oauth_client_id"])
    config["oauth_redirect_uri"] = os.environ.get("OAUTH_REDIRECT_URI", config["oauth_redirect_uri"])
    config["ak_file"] = os.environ.get("AK_FILE", config["ak_file"])
    config["rk_file"] = os.environ.get("RK_FILE", config["rk_file"])
    config["token_json_dir"] = os.environ.get("TOKEN_JSON_DIR", config["token_json_dir"])
    config["upload_api_url"] = os.environ.get("UPLOAD_API_URL", config["upload_api_url"])
    config["upload_api_token"] = os.environ.get("UPLOAD_API_TOKEN", config["upload_api_token"])
    config["SUB2API_URL"] = os.environ.get("SUB2API_URL", config["SUB2API_URL"])
    config["SUB2API_TOKEN"] = os.environ.get("SUB2API_TOKEN", config["SUB2API_TOKEN"])

    return config


def _as_bool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


_CONFIG = _load_config()
MAIL_PROVIDER = _CONFIG.get("mail_provider", "duckmail").strip().lower()
DUCKMAIL_API_BASE = _CONFIG["duckmail_api_base"]
DUCKMAIL_DOMAIN = _CONFIG.get("duckmail_domain", "duckmail.sbs")
DUCKMAIL_BEARER = _CONFIG["duckmail_bearer"]
CF_MAIL_API_BASE = _CONFIG.get("cf_mail_api_base", "")
# 支持中英文逗号分隔的多域名，统一转为列表；向后兼容保留单值 CF_MAIL_DOMAIN
_raw_cf_domain = _CONFIG.get("cf_mail_domain", "")
CF_MAIL_DOMAINS: list = [
    d.strip()
    for d in _raw_cf_domain.replace("，", ",").split(",")
    if d.strip()
]
CF_MAIL_DOMAIN = CF_MAIL_DOMAINS[0] if CF_MAIL_DOMAINS else ""
CF_MAIL_ADMIN_PASSWORD = _CONFIG.get("cf_mail_admin_password", "")
CF_MAIL_JWT_SECRET = _CONFIG.get("cf_mail_jwt_secret", "")
DEFAULT_TOTAL_ACCOUNTS = _CONFIG["total_accounts"]
DEFAULT_PROXY = _CONFIG["proxy"]
DEFAULT_OUTPUT_FILE = _CONFIG["output_file"]
CSV_FILE = _CONFIG.get("csv_file", "registered_accounts.csv")
INVITE_TRACKER_FILE = _CONFIG.get("invite_tracker_file", "invite_tracker.json")
ENABLE_OAUTH = _as_bool(_CONFIG.get("enable_oauth", True))
OAUTH_REQUIRED = _as_bool(_CONFIG.get("oauth_required", True))
OAUTH_ISSUER = _CONFIG["oauth_issuer"].rstrip("/")
OAUTH_CLIENT_ID = _CONFIG["oauth_client_id"]
OAUTH_REDIRECT_URI = _CONFIG["oauth_redirect_uri"]
AK_FILE = _CONFIG["ak_file"]
RK_FILE = _CONFIG["rk_file"]
TOKEN_JSON_DIR = _CONFIG["token_json_dir"]
UPLOAD_API_URL = _CONFIG["upload_api_url"]
UPLOAD_API_TOKEN = _CONFIG["upload_api_token"]
SUB2API_URL = _CONFIG["SUB2API_URL"]
SUB2API_TOKEN = _CONFIG["SUB2API_TOKEN"]
# CPA 推送是否经过代理，默认 False（CPA 通常内网直连可达）
CPA_USE_PROXY = _CONFIG.get("cpa_use_proxy", False)
TEAMS = _CONFIG.get("teams", [])

if MAIL_PROVIDER == "cloudflare":
    if not CF_MAIL_ADMIN_PASSWORD and not CF_MAIL_JWT_SECRET:
        print("⚠️ 警告: 邮箱提供商为 CloudflareMail 但未设置 cf_mail_admin_password 或 cf_mail_jwt_secret")
else:
    if not DUCKMAIL_BEARER:
        print("⚠️ 警告: 邮箱提供商为 DuckMail 但未设置 duckmail_bearer")

if not TEAMS:
    print("⚠️ 警告: 未设置 teams，请在 config.json 中配置 Team 信息")

# 全局线程锁
_print_lock = threading.Lock()
_file_lock = threading.Lock()


# ================= Chrome 指纹配置 =================
_CHROME_PROFILES = [
    {
        "major": 131, "impersonate": "chrome131",
        "build": 6778, "patch_range": (69, 205),
        "sec_ch_ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    },
    {
        "major": 133, "impersonate": "chrome133a",
        "build": 6943, "patch_range": (33, 153),
        "sec_ch_ua": '"Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
    },
    {
        "major": 136, "impersonate": "chrome136",
        "build": 7103, "patch_range": (48, 175),
        "sec_ch_ua": '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
    },
    {
        "major": 142, "impersonate": "chrome142",
        "build": 7540, "patch_range": (30, 150),
        "sec_ch_ua": '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
    },
]


def _random_chrome_version():
    profile = random.choice(_CHROME_PROFILES)
    major = profile["major"]
    build = profile["build"]
    patch = random.randint(*profile["patch_range"])
    full_ver = f"{major}.0.{build}.{patch}"
    ua = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{full_ver} Safari/537.36"
    return profile["impersonate"], major, full_ver, ua, profile["sec_ch_ua"]


def _random_delay(low=0.3, high=1.0):
    time.sleep(random.uniform(low, high))


def _make_trace_headers():
    trace_id = random.randint(10**17, 10**18 - 1)
    parent_id = random.randint(10**17, 10**18 - 1)
    tp = f"00-{uuid.uuid4().hex}-{format(parent_id, '016x')}-01"
    return {
        "traceparent": tp, "tracestate": "dd=s:1;o:rum",
        "x-datadog-origin": "rum", "x-datadog-sampling-priority": "1",
        "x-datadog-trace-id": str(trace_id), "x-datadog-parent-id": str(parent_id),
    }


def _generate_pkce():
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode("ascii")
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge


def _generate_password(length=14):
    lower = string.ascii_lowercase
    upper = string.ascii_uppercase
    digits = string.digits
    special = "!@#$%&*"
    pwd = [random.choice(lower), random.choice(upper),
           random.choice(digits), random.choice(special)]
    all_chars = lower + upper + digits + special
    pwd += [random.choice(all_chars) for _ in range(length - 4)]
    random.shuffle(pwd)
    return "".join(pwd)


def _random_name():
    first_names = [
        "James", "Emma", "Liam", "Olivia", "Noah", "Ava", "Ethan", "Sophia",
        "Lucas", "Mia", "Mason", "Isabella", "Logan", "Charlotte", "Alexander",
        "Amelia", "Benjamin", "Harper", "William", "Evelyn", "Henry", "Abigail",
        "Sebastian", "Emily", "Jack", "Elizabeth", "Michael", "Robert", "David",
        "Joseph", "Thomas", "Christopher", "Daniel", "Matthew", "Anthony",
        "Mary", "Patricia", "Jennifer", "Linda", "Barbara", "Susan", "Jessica",
        "Sarah", "Karen", "Lisa", "Nancy", "Betty", "Margaret", "Sandra",
        "Ashley", "Kimberly", "Donna", "Michelle", "Dorothy", "Carol",
        "Amanda", "Melissa", "Deborah", "Stephanie", "Rebecca", "Sharon",
    ]
    last_names = [
        "Smith", "Johnson", "Brown", "Davis", "Wilson", "Moore", "Taylor",
        "Clark", "Hall", "Young", "Anderson", "Thomas", "Jackson", "White",
        "Harris", "Martin", "Thompson", "Garcia", "Robinson", "Lewis",
        "Walker", "Allen", "King", "Wright", "Scott", "Green", "Adams",
        "Nelson", "Baker", "Rivera", "Campbell", "Mitchell", "Carter",
        "Roberts", "Phillips", "Evans", "Turner", "Diaz", "Parker",
    ]
    return f"{random.choice(first_names)} {random.choice(last_names)}"


def _random_birthdate():
    y = random.randint(1980, 2002)
    m = random.randint(1, 12)
    d = random.randint(1, 28)
    return f"{y}-{m:02d}-{d:02d}"


# ================= Sentinel Token (PoW) =================

class SentinelTokenGenerator:
    """纯 Python 版本 sentinel token 生成器（PoW）"""

    MAX_ATTEMPTS = 500000
    ERROR_PREFIX = "wQ8Lk5FbGpA2NcR9dShT6gYjU7VxZ4D"

    def __init__(self, device_id=None, user_agent=None):
        self.device_id = device_id or str(uuid.uuid4())
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/145.0.0.0 Safari/537.36"
        )
        self.requirements_seed = str(random.random())
        self.sid = str(uuid.uuid4())

    @staticmethod
    def _fnv1a_32(text: str):
        h = 2166136261
        for ch in text:
            h ^= ord(ch)
            h = (h * 16777619) & 0xFFFFFFFF
        h ^= (h >> 16)
        h = (h * 2246822507) & 0xFFFFFFFF
        h ^= (h >> 13)
        h = (h * 3266489909) & 0xFFFFFFFF
        h ^= (h >> 16)
        h &= 0xFFFFFFFF
        return format(h, "08x")

    def _get_config(self):
        now_str = time.strftime(
            "%a %b %d %Y %H:%M:%S GMT+0000 (Coordinated Universal Time)",
            time.gmtime(),
        )
        perf_now = random.uniform(1000, 50000)
        time_origin = time.time() * 1000 - perf_now
        nav_prop = random.choice([
            "vendorSub", "productSub", "vendor", "maxTouchPoints",
            "scheduling", "userActivation", "doNotTrack", "geolocation",
            "connection", "plugins", "mimeTypes", "pdfViewerEnabled",
            "webkitTemporaryStorage", "webkitPersistentStorage",
            "hardwareConcurrency", "cookieEnabled", "credentials",
            "mediaDevices", "permissions", "locks", "ink",
        ])
        nav_val = f"{nav_prop}-undefined"

        return [
            "1920x1080", now_str, 4294705152, random.random(),
            self.user_agent,
            "https://sentinel.openai.com/sentinel/20260124ceb8/sdk.js",
            None, None, "en-US", "en-US,en", random.random(), nav_val,
            random.choice(["location", "implementation", "URL", "documentURI", "compatMode"]),
            random.choice(["Object", "Function", "Array", "Number", "parseFloat", "undefined"]),
            perf_now, self.sid, "",
            random.choice([4, 8, 12, 16]), time_origin,
        ]

    @staticmethod
    def _base64_encode(data):
        raw = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return base64.b64encode(raw).decode("ascii")

    def _run_check(self, start_time, seed, difficulty, config, nonce):
        config[3] = nonce
        config[9] = round((time.time() - start_time) * 1000)
        data = self._base64_encode(config)
        hash_hex = self._fnv1a_32(seed + data)
        diff_len = len(difficulty)
        if hash_hex[:diff_len] <= difficulty:
            return data + "~S"
        return None

    def generate_token(self, seed=None, difficulty=None):
        seed = seed if seed is not None else self.requirements_seed
        difficulty = str(difficulty or "0")
        start_time = time.time()
        config = self._get_config()
        for i in range(self.MAX_ATTEMPTS):
            result = self._run_check(start_time, seed, difficulty, config, i)
            if result:
                return "gAAAAAB" + result
        return "gAAAAAB" + self.ERROR_PREFIX + self._base64_encode(str(None))

    def generate_requirements_token(self):
        config = self._get_config()
        config[3] = 1
        config[9] = round(random.uniform(5, 50))
        data = self._base64_encode(config)
        return "gAAAAAC" + data


def fetch_sentinel_challenge(session, device_id, flow="authorize_continue", user_agent=None,
                             sec_ch_ua=None, impersonate=None):
    generator = SentinelTokenGenerator(device_id=device_id, user_agent=user_agent)
    req_body = {"p": generator.generate_requirements_token(), "id": device_id, "flow": flow}
    headers = {
        "Content-Type": "text/plain;charset=UTF-8",
        "Referer": "https://sentinel.openai.com/backend-api/sentinel/frame.html",
        "Origin": "https://sentinel.openai.com",
        "User-Agent": user_agent or "Mozilla/5.0",
        "sec-ch-ua": sec_ch_ua or '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
        "sec-ch-ua-mobile": "?0", "sec-ch-ua-platform": '"Windows"',
    }
    kwargs = {"data": json.dumps(req_body), "headers": headers, "timeout": 20}
    if impersonate:
        kwargs["impersonate"] = impersonate
    try:
        resp = session.post("https://sentinel.openai.com/backend-api/sentinel/req", **kwargs)
    except Exception:
        return None
    if resp.status_code != 200:
        return None
    try:
        return resp.json()
    except Exception:
        return None


def build_sentinel_token(session, device_id, flow="authorize_continue", user_agent=None,
                         sec_ch_ua=None, impersonate=None):
    challenge = fetch_sentinel_challenge(session, device_id, flow=flow, user_agent=user_agent,
                                         sec_ch_ua=sec_ch_ua, impersonate=impersonate)
    if not challenge:
        return None
    c_value = challenge.get("token", "")
    if not c_value:
        return None
    pow_data = challenge.get("proofofwork") or {}
    generator = SentinelTokenGenerator(device_id=device_id, user_agent=user_agent)
    if pow_data.get("required") and pow_data.get("seed"):
        p_value = generator.generate_token(seed=pow_data.get("seed"), difficulty=pow_data.get("difficulty", "0"))
    else:
        p_value = generator.generate_requirements_token()
    return json.dumps({"p": p_value, "t": "", "c": c_value, "id": device_id, "flow": flow}, separators=(",", ":"))


def _extract_code_from_url(url: str):
    if not url or "code=" not in url:
        return None
    try:
        return parse_qs(urlparse(url).query).get("code", [None])[0]
    except Exception:
        return None


def _decode_jwt_payload(token: str):
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return {}
        payload = parts[1]
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += "=" * padding
        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)
    except Exception:
        return {}


# ================= Token 保存与上传 =================
def _build_default_model_mapping() -> dict:
    return {
        "gpt-3.5-turbo": "gpt-3.5-turbo",
        "gpt-3.5-turbo-0125": "gpt-3.5-turbo-0125",
        "gpt-3.5-turbo-1106": "gpt-3.5-turbo-1106",
        "gpt-3.5-turbo-16k": "gpt-3.5-turbo-16k",
        "gpt-4": "gpt-4",
        "gpt-4-turbo": "gpt-4-turbo",
        "gpt-4-turbo-preview": "gpt-4-turbo-preview",
        "gpt-4o": "gpt-4o",
        "gpt-4o-2024-08-06": "gpt-4o-2024-08-06",
        "gpt-4o-2024-11-20": "gpt-4o-2024-11-20",
        "gpt-4o-mini": "gpt-4o-mini",
        "gpt-4o-mini-2024-07-18": "gpt-4o-mini-2024-07-18",
        "gpt-4.5-preview": "gpt-4.5-preview",
        "gpt-4.1": "gpt-4.1",
        "gpt-4.1-mini": "gpt-4.1-mini",
        "gpt-4.1-nano": "gpt-4.1-nano",
        "o1": "o1",
        "o1-preview": "o1-preview",
        "o1-mini": "o1-mini",
        "o1-pro": "o1-pro",
        "o3": "o3",
        "o3-mini": "o3-mini",
        "o3-pro": "o3-pro",
        "o4-mini": "o4-mini",
        "gpt-5": "gpt-5",
        "gpt-5-2025-08-07": "gpt-5-2025-08-07",
        "gpt-5-chat": "gpt-5-chat",
        "gpt-5-chat-latest": "gpt-5-chat-latest",
        "gpt-5-codex": "gpt-5-codex",
        "gpt-5.3-codex-spark": "gpt-5.3-codex-spark",
        "gpt-5-pro": "gpt-5-pro",
        "gpt-5-pro-2025-10-06": "gpt-5-pro-2025-10-06",
        "gpt-5-mini": "gpt-5-mini",
        "gpt-5-mini-2025-08-07": "gpt-5-mini-2025-08-07",
        "gpt-5-nano": "gpt-5-nano",
        "gpt-5-nano-2025-08-07": "gpt-5-nano-2025-08-07",
        "gpt-5.1": "gpt-5.1",
        "gpt-5.1-2025-11-13": "gpt-5.1-2025-11-13",
        "gpt-5.1-chat-latest": "gpt-5.1-chat-latest",
        "gpt-5.1-codex": "gpt-5.1-codex",
        "gpt-5.1-codex-max": "gpt-5.1-codex-max",
        "gpt-5.1-codex-mini": "gpt-5.1-codex-mini",
        "gpt-5.2": "gpt-5.2",
        "gpt-5.2-2025-12-11": "gpt-5.2-2025-12-11",
        "gpt-5.2-chat-latest": "gpt-5.2-chat-latest",
        "gpt-5.2-codex": "gpt-5.2-codex",
        "gpt-5.2-pro": "gpt-5.2-pro",
        "gpt-5.2-pro-2025-12-11": "gpt-5.2-pro-2025-12-11",
        "gpt-5.4": "gpt-5.4",
        "gpt-5.4-2026-03-05": "gpt-5.4-2026-03-05",
        "gpt-5.3-codex": "gpt-5.3-codex",
        "chatgpt-4o-latest": "chatgpt-4o-latest",
        "gpt-4o-audio-preview": "gpt-4o-audio-preview",
        "gpt-4o-realtime-preview": "gpt-4o-realtime-preview",
    }


def _build_codex_account_payload(email: str, tokens: dict) -> dict:
    """将 OAuth token 转换为 codex.csun.site /api/v1/admin/accounts 所需的 payload 格式"""
    access_token = tokens.get("access_token", "")
    refresh_token = tokens.get("refresh_token", "")
    id_token = tokens.get("id_token", "")
    expires_in = tokens.get("expires_in", 863999)

    # 从 access_token JWT 中提取字段
    at_payload = _decode_jwt_payload(access_token) if access_token else {}
    at_auth = at_payload.get("https://api.openai.com/auth", {})
    chatgpt_account_id = at_auth.get("chatgpt_account_id", "")
    chatgpt_user_id = at_auth.get("chatgpt_user_id", "")
    exp_timestamp = at_payload.get("exp", 0)
    expires_at = exp_timestamp if isinstance(exp_timestamp, int) and exp_timestamp > 0 else int(time.time()) + expires_in

    # 从 id_token JWT 中提取 organization_id
    it_payload = _decode_jwt_payload(id_token) if id_token else {}
    it_auth = it_payload.get("https://api.openai.com/auth", {})
    organization_id = it_auth.get("organization_id", "")
    if not organization_id:
        orgs = it_auth.get("organizations", [])
        if orgs:
            organization_id = (orgs[0] or {}).get("id", "")

    return {
        "name": email,
        "notes": "",
        "platform": "openai",
        "type": "oauth",
        "credentials": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": expires_in,
            "expires_at": expires_at,
            "client_id": OAUTH_CLIENT_ID,
            "chatgpt_account_id": chatgpt_account_id,
            "chatgpt_user_id": chatgpt_user_id,
            "organization_id": organization_id,
            "model_mapping": _build_default_model_mapping(),
        },
        "extra": {
            "email": email,
            "openai_oauth_responses_websockets_v2_mode": "off",
            "openai_oauth_responses_websockets_v2_enabled": False,
        },
        "proxy_id": None,
        "concurrency": 10,
        "priority": 1,
        "rate_multiplier": 1,
        "group_ids": [2], #根据实际情况修改分组
        "expires_at": None,
        "auto_pause_on_expired": True,
    }

def _save_codex_tokens(email: str, tokens: dict):
    access_token = tokens.get("access_token", "")
    refresh_token = tokens.get("refresh_token", "")
    id_token = tokens.get("id_token", "")

    if access_token:
        with _file_lock:
            with open(AK_FILE, "a", encoding="utf-8") as f:
                f.write(f"{access_token}\n")

    if refresh_token:
        with _file_lock:
            with open(RK_FILE, "a", encoding="utf-8") as f:
                f.write(f"{refresh_token}\n")

    if not access_token:
        return

    payload = _decode_jwt_payload(access_token)
    auth_info = payload.get("https://api.openai.com/auth", {})
    account_id = auth_info.get("chatgpt_account_id", "")

    exp_timestamp = payload.get("exp")
    expired_str = ""
    if isinstance(exp_timestamp, int) and exp_timestamp > 0:
        from datetime import datetime, timezone, timedelta
        exp_dt = datetime.fromtimestamp(exp_timestamp, tz=timezone(timedelta(hours=8)))
        expired_str = exp_dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")

    from datetime import datetime, timezone, timedelta
    now = datetime.now(tz=timezone(timedelta(hours=8)))
    token_data = {
        "type": "codex", "email": email, "expired": expired_str,
        "id_token": id_token, "account_id": account_id,
        "access_token": access_token,
        "last_refresh": now.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "refresh_token": refresh_token, "websockets": True,
    }

    base_dir = os.path.dirname(os.path.abspath(__file__))
    token_dir = TOKEN_JSON_DIR if os.path.isabs(TOKEN_JSON_DIR) else os.path.join(base_dir, TOKEN_JSON_DIR)
    os.makedirs(token_dir, exist_ok=True)
    token_path = os.path.join(token_dir, f"{email}.json")
    with _file_lock:
        with open(token_path, "w", encoding="utf-8") as f:
            json.dump(token_data, f, ensure_ascii=False)

    if UPLOAD_API_URL:
        # 推送到 CPA（旧方式 - 文件上传）
        _upload_token_json(token_path)

    if SUB2API_URL and SUB2API_TOKEN:
        # 推送到 CPA（通过 /v0/management/auth-files 上传 token JSON）
        _upload_to_cpa(token_path)
    else:
        print("[CPA] 未配置 SUB2API_URL 或 SUB2API_TOKEN，跳过 CPA 推送")


def _upload_token_json(filepath):
    """旧版 CPA 上传（使用标准 requests 避免 curl_cffi TLS 问题）"""
    try:
        import requests as std_requests
        filename = os.path.basename(filepath)
        session = std_requests.Session()
        session.verify = False
        if DEFAULT_PROXY:
            session.proxies = {"http": DEFAULT_PROXY, "https": DEFAULT_PROXY}
        with open(filepath, "rb") as f:
            resp = session.post(
                UPLOAD_API_URL,
                files={"file": (filename, f, "application/json")},
                headers={"Authorization": f"Bearer {UPLOAD_API_TOKEN}"},
                timeout=30,
            )
        if resp.status_code in (200, 201):
            with _print_lock:
                print(f"  [CPA] Token JSON 已上传到 CPA 管理平台")
        else:
            with _print_lock:
                print(f"  [CPA] 上传失败: {resp.status_code} - {resp.text[:200]}")
    except Exception as e:
        with _print_lock:
            print(f"  [CPA] 上传异常: {e}")


def _upload_to_cpa(filepath):
    """推送 token JSON 到 CPA (CliProxyAPI) /v0/management/auth-files"""
    try:
        import requests as std_requests
        base = SUB2API_URL.rstrip("/")
        upload_url = f"{base}/v0/management/auth-files"
        filename = os.path.basename(filepath)
        session = std_requests.Session()
        session.verify = False
        # 仅在 cpa_use_proxy 开启时才为推送请求附加代理；
        # CPA 地址通常内网直连可达，默认走代理会导致 502
        if DEFAULT_PROXY and CPA_USE_PROXY:
            session.proxies = {"http": DEFAULT_PROXY, "https": DEFAULT_PROXY}
        with open(filepath, "rb") as f:
            file_bytes = f.read()
        resp = session.post(
            upload_url,
            files={"file": (filename, file_bytes, "application/json")},
            headers={"Authorization": f"Bearer {SUB2API_TOKEN}"},
            timeout=30,
        )
        if resp.status_code in (200, 201):
            with _print_lock:
                print(f"  [CPA] Token 已推送到 CPA: {filename}")
        elif resp.status_code == 409:
            with _print_lock:
                print(f"  [CPA] Token 已存在，跳过: {filename}")
        else:
            with _print_lock:
                print(f"  [CPA] 推送失败: {resp.status_code} - {resp.text[:200]}")
    except Exception as e:
        with _print_lock:
            print(f"  [CPA] 推送异常: {e}")


def refresh_one_token(token_filepath):
    """刷新单个 codex token 文件的 refresh_token，成功返回更新后的数据，失败返回 None"""
    import requests as std_requests
    try:
        with open(token_filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None

    rt = data.get("refresh_token", "")
    if not rt:
        return None

    # 构建标准 HTTP session（不使用 curl_cffi，避免 TLS 指纹问题）
    session = std_requests.Session()
    session.verify = False
    if DEFAULT_PROXY:
        session.proxies = {"http": DEFAULT_PROXY, "https": DEFAULT_PROXY}

    try:
        resp = session.post(
            f"{OAUTH_ISSUER}/oauth/token",
            data={
                "grant_type": "refresh_token",
                "client_id": OAUTH_CLIENT_ID,
                "refresh_token": rt,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
    except Exception:
        return None

    if resp.status_code != 200:
        return None

    try:
        new_tokens = resp.json()
    except Exception:
        return None

    new_at = new_tokens.get("access_token", "")
    if not new_at:
        return None

    # 解析新 access_token 的过期时间
    payload = _decode_jwt_payload(new_at)
    exp_timestamp = payload.get("exp")
    expired_str = ""
    if isinstance(exp_timestamp, int) and exp_timestamp > 0:
        from datetime import datetime, timezone, timedelta
        exp_dt = datetime.fromtimestamp(exp_timestamp, tz=timezone(timedelta(hours=8)))
        expired_str = exp_dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")

    from datetime import datetime, timezone, timedelta
    now = datetime.now(tz=timezone(timedelta(hours=8)))

    # 更新 token 数据（保留原有字段，仅更新变化的部分）
    data["access_token"] = new_at
    data["expired"] = expired_str
    data["last_refresh"] = now.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    if new_tokens.get("refresh_token"):
        data["refresh_token"] = new_tokens["refresh_token"]
    if new_tokens.get("id_token"):
        data["id_token"] = new_tokens["id_token"]

    # 写回文件
    try:
        with open(token_filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        return None

    return data


# ================= Team 邀请 =================

def load_invite_tracker():
    default = {"teams": {team["account_id"]: [] for team in TEAMS}}
    if os.path.exists(INVITE_TRACKER_FILE):
        try:
            with open(INVITE_TRACKER_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "teams" in data:
                    return data
        except Exception as e:
            print(f"⚠️ Failed to load invite tracker: {e}")
    return default


def save_invite_tracker(tracker):
    """保存 invite tracker（调用者应已持有 _file_lock）"""
    try:
        with open(INVITE_TRACKER_FILE, "w", encoding="utf-8") as f:
            json.dump(tracker, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Failed to save invite tracker: {e}")


def get_available_team(tracker):
    for team in TEAMS:
        account_id = team["account_id"]
        invited = tracker["teams"].get(account_id, [])
        if len(invited) < team["max_invites"]:
            return team
    return None


def _get_fresh_access_token(team: dict, tag: str = ""):
    """使用 session_token (cookie) 从 /api/auth/session 获取 fresh access_token"""
    prefix = f"[{tag}] " if tag else ""
    session_token = team.get("session_token", "")
    if not session_token:
        # 降级: 直接使用 auth_token
        return team.get("auth_token", "")

    s = curl_requests.Session(verify=False, impersonate="chrome120")
    if DEFAULT_PROXY:
        s.proxies = {"http": DEFAULT_PROXY, "https": DEFAULT_PROXY}
    s.cookies.set("__Secure-next-auth.session-token", session_token, domain="chatgpt.com")

    try:
        r = s.get("https://chatgpt.com/api/auth/session", timeout=30)
        if r.status_code == 200:
            data = r.json()
            fresh_token = data.get("accessToken", "")
            if fresh_token:
                with _print_lock:
                    print(f"{prefix}🔑 获取 fresh access_token 成功 (expires: {data.get('expires', '?')})")
                return f"Bearer {fresh_token}"
        with _print_lock:
            print(f"{prefix}⚠️ 获取 fresh token 失败 (status={r.status_code})，降级使用 auth_token")
    except Exception as e:
        with _print_lock:
            print(f"{prefix}⚠️ 获取 fresh token 异常: {e}，降级使用 auth_token")
    return team.get("auth_token", "")


def invite_to_team(email: str, team: dict, tag: str = ""):
    """通过协议发送 Team 邀请 (自动刷新 access_token)"""
    prefix = f"[{tag}] " if tag else ""

    # 获取 fresh access token
    auth_token = _get_fresh_access_token(team, tag)

    session = curl_requests.Session(verify=False, impersonate="chrome120")
    if DEFAULT_PROXY:
        session.proxies = {"http": DEFAULT_PROXY, "https": DEFAULT_PROXY}

    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "authorization": auth_token,
        "chatgpt-account-id": team["account_id"],
        "content-type": "application/json",
        "origin": "https://chatgpt.com",
        "referer": "https://chatgpt.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    }
    payload = {
        "email_addresses": [email],
        "role": "standard-user",
        "resend_emails": True,
    }
    invite_url = f"https://chatgpt.com/backend-api/accounts/{team['account_id']}/invites"
    try:
        response = session.post(invite_url, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            result = response.json()
            if result.get("account_invites"):
                with _print_lock:
                    print(f"{prefix}✅ Successfully invited {email} to {team['name']}")
                return True
            elif result.get("errored_emails"):
                with _print_lock:
                    print(f"{prefix}⚠️ Invite error for {email}: {result['errored_emails']}")
                return False
        else:
            with _print_lock:
                print(f"{prefix}❌ Failed to invite {email}: HTTP {response.status_code}")
                print(f"{prefix}   Response: {response.text[:200]}")
            return False
    except Exception as e:
        with _print_lock:
            print(f"{prefix}❌ Invite request failed: {e}")
        return False


def auto_invite_to_team(email: str, tag: str = ""):
    """自动选择可用 Team 并发送邀请"""
    if not TEAMS:
        with _print_lock:
            print(f"[{tag}] ⚠️ 未配置 teams，跳过邀请" if tag else "⚠️ 未配置 teams，跳过邀请")
        return False

    with _file_lock:
        tracker = load_invite_tracker()
        for account_id, emails in tracker["teams"].items():
            if email in emails:
                with _print_lock:
                    print(f"[{tag}] ⚠️ {email} already invited, skipping" if tag else f"⚠️ {email} already invited")
                return False
        team = get_available_team(tracker)
        if not team:
            with _print_lock:
                print(f"[{tag}] ❌ All teams are full" if tag else "❌ All teams are full")
            return False

    if invite_to_team(email, team, tag=tag):
        with _file_lock:
            tracker = load_invite_tracker()
            account_id = team["account_id"]
            if account_id not in tracker["teams"]:
                tracker["teams"][account_id] = []
            tracker["teams"][account_id].append(email)
            save_invite_tracker(tracker)
            count = len(tracker["teams"][account_id])
            with _print_lock:
                print(f"[{tag}]    Team status: {team['name']} has {count}/{team['max_invites']} invites"
                      if tag else f"   Team status: {team['name']} has {count}/{team['max_invites']} invites")
        return True
    return False


# ================= CSV 保存 =================

def save_to_csv(email: str, password: str, dm_password: str = "", oauth_status: str = ""):
    import csv
    file_exists = os.path.exists(CSV_FILE)
    with _file_lock:
        with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["email", "password", "duckmail_password", "oauth_status", "timestamp"])
            writer.writerow([email, password, dm_password, oauth_status, time.strftime("%Y-%m-%d %H:%M:%S")])


# ================= ChatGPTRegister 核心类 =================

class ChatGPTRegister:
    BASE = "https://chatgpt.com"
    AUTH = "https://auth.openai.com"

    def __init__(self, proxy: str = None, tag: str = ""):
        self.tag = tag
        self.device_id = str(uuid.uuid4())
        self.auth_session_logging_id = str(uuid.uuid4())
        self.impersonate, self.chrome_major, self.chrome_full, self.ua, self.sec_ch_ua = _random_chrome_version()

        self.session = curl_requests.Session(impersonate=self.impersonate, verify=False)
        self.proxy = proxy
        if self.proxy:
            self.session.proxies = {"http": self.proxy, "https": self.proxy}

        self.session.headers.update({
            "User-Agent": self.ua,
            "Accept-Language": random.choice([
                "en-US,en;q=0.9", "en-US,en;q=0.9,zh-CN;q=0.8",
                "en,en-US;q=0.9", "en-US,en;q=0.8",
            ]),
            "sec-ch-ua": self.sec_ch_ua, "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"', "sec-ch-ua-arch": '"x86"',
            "sec-ch-ua-bitness": '"64"',
            "sec-ch-ua-full-version": f'"{self.chrome_full}"',
            "sec-ch-ua-platform-version": f'"{random.randint(10, 15)}.0.0"',
        })
        self.session.cookies.set("oai-did", self.device_id, domain="chatgpt.com")
        self._callback_url = None

    def _print(self, msg):
        prefix = f"[{self.tag}] " if self.tag else ""
        with _print_lock:
            print(f"{prefix}{msg}")

    def _log(self, step, method, url, status, body=None):
        prefix = f"[{self.tag}] " if self.tag else ""
        lines = [f"\n{'='*60}", f"{prefix}[Step] {step}", f"{prefix}[{method}] {url}",
                 f"{prefix}[Status] {status}"]
        if body:
            try:
                lines.append(f"{prefix}[Response] {json.dumps(body, indent=2, ensure_ascii=False)[:1000]}")
            except Exception:
                lines.append(f"{prefix}[Response] {str(body)[:1000]}")
        lines.append(f"{'='*60}")
        with _print_lock:
            print("\n".join(lines))

    # ---- DuckMail (使用标准 requests，避免 curl_cffi TLS 超时) ----

    def _create_duckmail_session(self):
        """使用标准 requests + retry 策略（与 cpa.py 保持一致）"""
        import requests as std_requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        session = std_requests.Session()
        retry_strategy = Retry(
            total=5, backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST", "OPTIONS"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers.update({
            "User-Agent": self.ua, "Accept": "application/json", "Content-Type": "application/json",
        })
        if self.proxy:
            session.proxies = {"http": self.proxy, "https": self.proxy}
        return session

    def create_temp_email(self):
        """根据 MAIL_PROVIDER 分发到 DuckMail 或 CloudflareMail"""
        if MAIL_PROVIDER == "cloudflare":
            return self._create_temp_email_cf()
        return self._create_temp_email_duckmail()

    def _create_temp_email_duckmail(self):
        if not DUCKMAIL_BEARER:
            raise Exception("DUCKMAIL_BEARER 未设置")
        api_base = DUCKMAIL_API_BASE.rstrip("/")
        session = self._create_duckmail_session()
        max_retries = 5
        
        is_worker = "workers.dev" in api_base or "temp-email" in api_base
        
        for attempt in range(max_retries):
            chars = string.ascii_lowercase + string.digits
            ts = int(time.time()) % 100000
            random_suffix = "".join(random.choices(chars, k=12))
            email = f"t{ts}_{random_suffix}@{DUCKMAIL_DOMAIN}"
            password = _generate_password()
            
            try:
                print(f"  DuckMail 创建邮箱 (第{attempt+1}次): {email}")
                if is_worker:
                    payload = {
                        "admin_password": DUCKMAIL_BEARER,
                        "name": f"t{ts}_{random_suffix}",
                        "domain": DUCKMAIL_DOMAIN
                    }
                    res = session.post(f"{api_base}/new_address", json=payload, timeout=120)
                    if res.status_code == 200:
                        result = res.json()
                        if result.get("jwt"):
                            print(f"  ✅ 邮箱创建成功: {result['address']}")
                            return result["address"], password, result["jwt"]
                        raise Exception(f"Worker获取邮件 Token 失败: {res.text}")
                    elif res.status_code == 400 and "already exists" in res.text:
                        print("  ⚠️ 地址碰撞，换名重试...")
                        continue
                    else:
                        raise Exception(f"Worker创建邮箱失败: {res.status_code} - {res.text[:200]}")
                else:
                    headers = {"Authorization": f"Bearer {DUCKMAIL_BEARER}"}
                    res = session.post(f"{api_base}/accounts", json={"address": email, "password": password},
                                       headers=headers, timeout=120)
                    if res.status_code in [200, 201]:
                        result = res.json()
                        if result.get("address"):
                            print(f"  ✅ 邮箱创建成功: {result['address']}")
                            time.sleep(0.5)
                            token_res = session.post(f"{api_base}/token",
                                                     json={"address": email, "password": password},
                                                     headers=headers, timeout=120)
                            if token_res.status_code == 200:
                                mail_token = token_res.json().get("token")
                                if mail_token:
                                    print("  ✅ DuckMail token 获取成功")
                                    return email, password, mail_token
                            raise Exception(f"获取邮件 Token 失败: {token_res.status_code}")
                    elif res.status_code == 422 and "already exists" in res.text:
                        print("  ⚠️ 地址碰撞，换名重试...")
                        continue
                    else:
                        raise Exception(f"创建邮箱失败: {res.status_code} - {res.text[:200]}")
            except Exception as e:
                if "already exists" in str(e):
                    continue
                raise Exception(f"DuckMail/Worker 创建邮箱失败: {e}")
        raise Exception("DuckMail 创建邮箱失败: 超过最大重试次数")

    # ---- CloudflareMail ----

    def _create_temp_email_cf(self):
        auth_key = CF_MAIL_ADMIN_PASSWORD or CF_MAIL_JWT_SECRET
        if not auth_key:
            raise Exception("cf_mail_admin_password 未设置")
        api_base = CF_MAIL_API_BASE.rstrip("/")
        session = self._create_duckmail_session()
        max_retries = 5

        for attempt in range(max_retries):
            chars = string.ascii_lowercase + string.digits
            ts = int(time.time()) % 100000
            random_suffix = "".join(random.choices(chars, k=12))
            name = f"t{ts}{random_suffix}"
            password = _generate_password()
            # 多域名时随机选择，单域名退化为原行为
            domain = random.choice(CF_MAIL_DOMAINS) if CF_MAIL_DOMAINS else CF_MAIL_DOMAIN
            address = f"{name}@{domain}"

            try:
                print(f"  CloudflareMail 创建邮箱 (第{attempt+1}次)...")
                payload = {"enablePrefix": False, "name": name, "domain": domain}
                res = session.post(
                    f"{api_base}/admin/new_address",
                    json=payload,
                    headers={"x-admin-auth": auth_key},
                    timeout=120,
                )
                if res.status_code == 200:
                    result = res.json()
                    jwt_token = result.get("jwt")
                    actual_address = result.get("address", address)
                    if jwt_token:
                        print(f"  ✅ 邮箱创建成功: {actual_address}")
                        return actual_address, password, jwt_token
                    raise Exception(f"创建邮箱未返回 JWT: {res.text[:200]}")
                elif res.status_code == 400 and "already exists" in res.text:
                    print("  ⚠️ 地址碰撞，换名重试...")
                    continue
                else:
                    raise Exception(f"创建邮箱失败: {res.status_code} - {res.text[:200]}")
            except Exception as e:
                if "already exists" in str(e):
                    continue
                raise Exception(f"CloudflareMail 创建邮箱失败: {e}")
        raise Exception("CloudflareMail 创建邮箱失败: 超过最大重试次数")

    def _delete_temp_email_cf(self, mail_token: str):
        """通过用户 JWT 调用 DELETE /api/delete_address 删除临时邮箱，失败静默"""
        try:
            api_base = CF_MAIL_API_BASE.rstrip("/")
            session = self._create_duckmail_session()
            res = session.delete(
                f"{api_base}/api/delete_address",
                headers={"Authorization": f"Bearer {mail_token}"},
                timeout=15,
            )
            if res.status_code == 200:
                self._print("🗑️ 临时邮箱已删除")
            else:
                self._print(f"⚠️ 删除临时邮箱失败: {res.status_code}")
        except Exception as e:
            self._print(f"⚠️ 删除临时邮箱异常: {e}")

    def _fetch_emails_cf(self, mail_token: str):
        try:
            api_base = CF_MAIL_API_BASE.rstrip("/")
            session = self._create_duckmail_session()
            res = session.get(
                f"{api_base}/api/mails",
                params={"limit": 20, "offset": 0},
                headers={"Authorization": f"Bearer {mail_token}"},
                timeout=120,
            )
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, dict) and "results" in data:
                    return data.get("results", [])
                return data if isinstance(data, list) else []
            else:
                print(f"  [DEBUG] CF fetch emails failed: {res.status_code} {res.text[:100]}")
            return []
        except Exception as e:
            print(f"  [DEBUG] Exception in _fetch_emails_cf: {e}")
            return []

    def _fetch_email_detail_cf(self, mail_token: str, msg_id: str):
        try:
            api_base = CF_MAIL_API_BASE.rstrip("/")
            session = self._create_duckmail_session()
            if isinstance(msg_id, str) and msg_id.startswith("/messages/"):
                msg_id = msg_id.split("/")[-1]
            res = session.get(
                f"{api_base}/api/mails/{msg_id}",
                headers={"Authorization": f"Bearer {mail_token}"},
                timeout=120,
            )
            if res.status_code == 200:
                data = res.json()
                html_val = data.get("html", "")
                text_val = data.get("text", "")
                data["html"] = html_val if html_val else text_val
                return data
        except Exception:
            pass
        return None

    def _fetch_emails_duckmail(self, mail_token: str):
        try:
            api_base = DUCKMAIL_API_BASE.rstrip("/")
            session = self._create_duckmail_session()
            is_worker = "workers.dev" in api_base or "temp-email" in api_base
            
            if is_worker:
                # Worker temp email usually expects Authorization Bearer header
                res = session.get(f"{api_base}/mails", params={"limit": 20, "offset": 0},
                                  headers={"Authorization": f"Bearer {mail_token}"}, timeout=120)
                if res.status_code == 200:
                    data = res.json()
                    if isinstance(data, dict) and "results" in data:
                        msgs = data.get("results", [])
                        return msgs
                    return data if isinstance(data, list) else []
                else:
                    print(f"  [DEBUG] Fetch emails failed: {res.status_code} {res.text[:100]}")
                return []
            else:
                res = session.get(f"{api_base}/messages", params={"page": 1},
                                  headers={"Authorization": f"Bearer {mail_token}"}, timeout=120)
                if res.status_code == 200:
                    data = res.json()
                    if isinstance(data, dict) and "hydra:member" in data:
                        msgs = data["hydra:member"]
                        if msgs:
                            print(f"  [DEBUG] Fetched {len(msgs)} messages from duckmail")
                        return msgs
                    elif isinstance(data, list):
                        return data
                    return []
                else:
                    print(f"  [DEBUG] Fetch emails failed: {res.status_code}")
                return []
        except Exception as e:
            print(f"  [DEBUG] Exception in _fetch_emails_duckmail: {e}")
            return []

    def _fetch_email_detail_duckmail(self, mail_token: str, msg_id: str):
        try:
            api_base = DUCKMAIL_API_BASE.rstrip("/")
            session = self._create_duckmail_session()
            is_worker = "workers.dev" in api_base or "temp-email" in api_base

            if is_worker:
                # msg_id might be just an integer id. The endpoint is typically /api/mails/:id
                if isinstance(msg_id, str) and msg_id.startswith("/messages/"):
                    msg_id = msg_id.split("/")[-1]
                res = session.get(f"{api_base}/mails/{msg_id}",
                                  headers={"Authorization": f"Bearer {mail_token}"}, timeout=120)
                if res.status_code == 200:
                    data = res.json()
                    # normalizes html or text output
                    html_val = data.get("html", "")
                    text_val = data.get("text", "")
                    data["html"] = html_val if html_val else text_val
                    return data
            else:
                if isinstance(msg_id, str) and msg_id.startswith("/messages/"):
                    msg_id = msg_id.split("/")[-1]
                res = session.get(f"{api_base}/messages/{msg_id}",
                                  headers={"Authorization": f"Bearer {mail_token}"}, timeout=120)
                if res.status_code == 200:
                    data = res.json()
                    # DuckMail API returns html as array, normalize to string
                    html_val = data.get("html")
                    if isinstance(html_val, list):
                        data["html"] = "\n".join(str(h) for h in html_val)
                    return data
        except Exception:
            pass
        return None

    def _extract_verification_code(self, email_content: str):
        if not email_content:
            return None
        patterns = [
            r"Verification code:?\s*(\d{6})", r"code is\s*(\d{6})",
            r"代码为[:：]?\s*(\d{6})", r"验证码[:：]?\s*(\d{6})",
            r">\s*(\d{6})\s*<", r"(?<![#&])\b(\d{6})\b",
        ]
        for pattern in patterns:
            matches = re.findall(pattern, email_content, re.IGNORECASE)
            for code in matches:
                if code == "177010":
                    continue
                return code
        return None

    def _fetch_emails(self, mail_token: str):
        """根据 MAIL_PROVIDER 调用对应的 fetch"""
        if MAIL_PROVIDER == "cloudflare":
            return self._fetch_emails_cf(mail_token)
        return self._fetch_emails_duckmail(mail_token)

    def _fetch_email_detail(self, mail_token: str, msg_id: str):
        """根据 MAIL_PROVIDER 调用对应的 detail"""
        if MAIL_PROVIDER == "cloudflare":
            return self._fetch_email_detail_cf(mail_token, msg_id)
        return self._fetch_email_detail_duckmail(mail_token, msg_id)

    def wait_for_verification_email(self, mail_token: str, timeout: int = 120):
        self._print(f"[OTP] 等待验证码邮件 (最多 {timeout}s)...")
        start_time = time.time()
        while time.time() - start_time < timeout:
            messages = self._fetch_emails(mail_token)
            if messages and len(messages) > 0:
                first_msg = messages[0]
                print(f"  [DEBUG] Message keys: {list(first_msg.keys())}")
                msg_id = first_msg.get("id") or first_msg.get("@id") or first_msg.get("message_id")
                
                # First try: extract OTP directly from list item
                inline_content = first_msg.get("text") or first_msg.get("html") or first_msg.get("raw") or first_msg.get("source") or ""
                if inline_content:
                    code = self._extract_verification_code(inline_content)
                    if code:
                        self._print(f"[OTP] 验证码: {code}")
                        return code
                
                # Second try: fetch detail by msg_id
                if msg_id:
                    detail = self._fetch_email_detail(mail_token, str(msg_id))
                    if detail:
                        content = detail.get("text") or detail.get("html") or detail.get("source") or ""
                        code = self._extract_verification_code(content)
                        if code:
                            self._print(f"[OTP] 验证码: {code}")
                            return code
            elapsed = int(time.time() - start_time)
            self._print(f"[OTP] 等待中... ({elapsed}s/{timeout}s)")
            time.sleep(3)
        self._print(f"[OTP] 超时 ({timeout}s)")
        return None

    # ---- 注册流程 ----

    def visit_homepage(self):
        url = f"{self.BASE}/"
        r = self.session.get(url, headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Upgrade-Insecure-Requests": "1",
        }, allow_redirects=True)
        self._log("0. Visit homepage", "GET", url, r.status_code,
                   {"cookies_count": len(self.session.cookies)})

    def get_csrf(self) -> str:
        url = f"{self.BASE}/api/auth/csrf"
        r = self.session.get(url, headers={"Accept": "application/json", "Referer": f"{self.BASE}/"})
        data = r.json()
        token = data.get("csrfToken", "")
        self._log("1. Get CSRF", "GET", url, r.status_code, data)
        if not token:
            raise Exception("Failed to get CSRF token")
        return token

    def signin(self, email: str, csrf: str) -> str:
        url = f"{self.BASE}/api/auth/signin/openai"
        params = {
            "prompt": "login", "ext-oai-did": self.device_id,
            "auth_session_logging_id": self.auth_session_logging_id,
            "screen_hint": "login_or_signup", "login_hint": email,
        }
        form_data = {"callbackUrl": f"{self.BASE}/", "csrfToken": csrf, "json": "true"}
        r = self.session.post(url, params=params, data=form_data, headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json", "Referer": f"{self.BASE}/", "Origin": self.BASE,
        })
        data = r.json()
        authorize_url = data.get("url", "")
        self._log("2. Signin", "POST", url, r.status_code, data)
        if not authorize_url:
            raise Exception("Failed to get authorize URL")
        return authorize_url

    def authorize(self, url: str) -> str:
        r = self.session.get(url, headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": f"{self.BASE}/", "Upgrade-Insecure-Requests": "1",
        }, allow_redirects=True)
        final_url = str(r.url)
        self._log("3. Authorize", "GET", url, r.status_code, {"final_url": final_url})
        return final_url

    def register(self, email: str, password: str):
        url = f"{self.AUTH}/api/accounts/user/register"
        headers = {"Content-Type": "application/json", "Accept": "application/json",
                    "Referer": f"{self.AUTH}/create-account/password", "Origin": self.AUTH}
        headers.update(_make_trace_headers())
        r = self.session.post(url, json={"username": email, "password": password}, headers=headers)
        try:
            data = r.json()
        except Exception:
            data = {"text": r.text[:500]}
        self._log("4. Register", "POST", url, r.status_code, data)
        return r.status_code, data

    def send_otp(self):
        url = f"{self.AUTH}/api/accounts/email-otp/send"
        r = self.session.get(url, headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": f"{self.AUTH}/create-account/password", "Upgrade-Insecure-Requests": "1",
        }, allow_redirects=True)
        try:
            data = r.json()
        except Exception:
            data = {"final_url": str(r.url), "status": r.status_code}
        self._log("5. Send OTP", "GET", url, r.status_code, data)
        return r.status_code, data

    def validate_otp(self, code: str):
        url = f"{self.AUTH}/api/accounts/email-otp/validate"
        headers = {"Content-Type": "application/json", "Accept": "application/json",
                    "Referer": f"{self.AUTH}/email-verification", "Origin": self.AUTH}
        headers.update(_make_trace_headers())
        r = self.session.post(url, json={"code": code}, headers=headers)
        try:
            data = r.json()
        except Exception:
            data = {"text": r.text[:500]}
        self._log("6. Validate OTP", "POST", url, r.status_code, data)
        return r.status_code, data

    def create_account(self, name: str, birthdate: str):
        url = f"{self.AUTH}/api/accounts/create_account"
        headers = {"Content-Type": "application/json", "Accept": "application/json",
                    "Referer": f"{self.AUTH}/about-you", "Origin": self.AUTH}
        headers.update(_make_trace_headers())
        r = self.session.post(url, json={"name": name, "birthdate": birthdate}, headers=headers)
        try:
            data = r.json()
        except Exception:
            data = {"text": r.text[:500]}
        self._log("7. Create Account", "POST", url, r.status_code, data)
        if isinstance(data, dict):
            cb = data.get("continue_url") or data.get("url") or data.get("redirect_url")
            if cb:
                self._callback_url = cb
        return r.status_code, data

    def callback(self, url: str = None):
        if not url:
            url = self._callback_url
        if not url:
            self._print("[!] No callback URL, skipping.")
            return None, None
        r = self.session.get(url, headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Upgrade-Insecure-Requests": "1",
        }, allow_redirects=True)
        self._log("8. Callback", "GET", url, r.status_code, {"final_url": str(r.url)})
        return r.status_code, {"final_url": str(r.url)}

    # ---- 注册主流程 ----

    def run_register(self, email, password, name, birthdate, mail_token):
        self.visit_homepage()
        _random_delay(0.3, 0.8)
        csrf = self.get_csrf()
        _random_delay(0.2, 0.5)
        auth_url = self.signin(email, csrf)
        _random_delay(0.3, 0.8)
        final_url = self.authorize(auth_url)
        final_path = urlparse(final_url).path
        _random_delay(0.3, 0.8)
        self._print(f"Authorize → {final_path}")
        need_otp = False

        if "create-account/password" in final_path:
            self._print("全新注册流程")
            _random_delay(0.5, 1.0)
            status, data = self.register(email, password)
            if status != 200:
                raise Exception(f"Register 失败 ({status}): {data}")
            _random_delay(0.3, 0.8)
            self.send_otp()
            need_otp = True
        elif "email-verification" in final_path or "email-otp" in final_path:
            self._print("跳到 OTP 验证阶段")
            need_otp = True
        elif "about-you" in final_path:
            self._print("跳到填写信息阶段")
            _random_delay(0.5, 1.0)
            self.create_account(name, birthdate)
            _random_delay(0.3, 0.5)
            self.callback()
            return True
        elif "callback" in final_path or "chatgpt.com" in final_url:
            self._print("账号已完成注册")
            return True
        else:
            self._print(f"未知跳转: {final_url}")
            self.register(email, password)
            self.send_otp()
            need_otp = True

        if need_otp:
            otp_code = self.wait_for_verification_email(mail_token)
            if not otp_code:
                raise Exception("未能获取验证码")
            _random_delay(0.3, 0.8)
            status, data = self.validate_otp(otp_code)
            if status != 200:
                self._print("验证码失败，重试...")
                self.send_otp()
                _random_delay(1.0, 2.0)
                otp_code = self.wait_for_verification_email(mail_token, timeout=60)
                if not otp_code:
                    raise Exception("重试后仍未获取验证码")
                _random_delay(0.3, 0.8)
                status, data = self.validate_otp(otp_code)
                if status != 200:
                    raise Exception(f"验证码失败 ({status}): {data}")

        _random_delay(0.5, 1.5)
        status, data = self.create_account(name, birthdate)
        if status != 200:
            raise Exception(f"Create account 失败 ({status}): {data}")
        _random_delay(0.2, 0.5)
        self.callback()
        return True

    # ---- OAuth helpers ----

    def _decode_oauth_session_cookie(self):
        jar = getattr(self.session.cookies, "jar", None)
        cookie_items = list(jar) if jar is not None else []
        for c in cookie_items:
            name = getattr(c, "name", "") or ""
            if "oai-client-auth-session" not in name:
                continue
            raw_val = (getattr(c, "value", "") or "").strip()
            if not raw_val:
                continue
            candidates = [raw_val]
            try:
                from urllib.parse import unquote
                decoded = unquote(raw_val)
                if decoded != raw_val:
                    candidates.append(decoded)
            except Exception:
                pass
            for val in candidates:
                try:
                    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                        val = val[1:-1]
                    part = val.split(".")[0] if "." in val else val
                    pad = 4 - len(part) % 4
                    if pad != 4:
                        part += "=" * pad
                    raw = base64.urlsafe_b64decode(part)
                    data = json.loads(raw.decode("utf-8"))
                    if isinstance(data, dict):
                        return data
                except Exception:
                    continue
        return None

    def _oauth_allow_redirect_extract_code(self, url: str, referer: str = None):
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Upgrade-Insecure-Requests": "1", "User-Agent": self.ua,
        }
        if referer:
            headers["Referer"] = referer
        try:
            resp = self.session.get(url, headers=headers, allow_redirects=True,
                                    timeout=30, impersonate=self.impersonate)
            final_url = str(resp.url)
            code = _extract_code_from_url(final_url)
            if code:
                return code
            for r in getattr(resp, "history", []) or []:
                loc = r.headers.get("Location", "")
                code = _extract_code_from_url(loc) or _extract_code_from_url(str(r.url))
                if code:
                    return code
        except Exception as e:
            maybe_localhost = re.search(r'(https?://localhost[^\s\'\"]+)', str(e))
            if maybe_localhost:
                code = _extract_code_from_url(maybe_localhost.group(1))
                if code:
                    return code
        return None

    def _oauth_follow_for_code(self, start_url: str, referer: str = None, max_hops: int = 16):
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Upgrade-Insecure-Requests": "1", "User-Agent": self.ua,
        }
        if referer:
            headers["Referer"] = referer
        current_url = start_url
        last_url = start_url
        for hop in range(max_hops):
            try:
                resp = self.session.get(current_url, headers=headers, allow_redirects=False,
                                        timeout=30, impersonate=self.impersonate)
            except Exception as e:
                maybe_localhost = re.search(r'(https?://localhost[^\s\'\"]+)', str(e))
                if maybe_localhost:
                    code = _extract_code_from_url(maybe_localhost.group(1))
                    if code:
                        return code, maybe_localhost.group(1)
                return None, last_url
            last_url = str(resp.url)
            code = _extract_code_from_url(last_url)
            if code:
                return code, last_url
            if resp.status_code in (301, 302, 303, 307, 308):
                loc = resp.headers.get("Location", "")
                if not loc:
                    return None, last_url
                if loc.startswith("/"):
                    loc = f"{OAUTH_ISSUER}{loc}"
                code = _extract_code_from_url(loc)
                if code:
                    return code, loc
                current_url = loc
                headers["Referer"] = last_url
                continue
            return None, last_url
        return None, last_url

    def _oauth_submit_workspace_and_org(self, consent_url: str):
        session_data = self._decode_oauth_session_cookie()
        if not session_data:
            self._print("[OAuth] 无法解码 oai-client-auth-session")
            return None
        workspaces = session_data.get("workspaces", [])
        if not workspaces:
            self._print("[OAuth] session 中没有 workspace 信息")
            return None
        workspace_id = (workspaces[0] or {}).get("id")
        if not workspace_id:
            return None

        h = {"Accept": "application/json", "Content-Type": "application/json",
             "Origin": OAUTH_ISSUER, "Referer": consent_url,
             "User-Agent": self.ua, "oai-device-id": self.device_id}
        h.update(_make_trace_headers())

        resp = self.session.post(f"{OAUTH_ISSUER}/api/accounts/workspace/select",
                                 json={"workspace_id": workspace_id}, headers=h,
                                 allow_redirects=False, timeout=30, impersonate=self.impersonate)
        self._print(f"[OAuth] workspace/select -> {resp.status_code}")

        if resp.status_code in (301, 302, 303, 307, 308):
            loc = resp.headers.get("Location", "")
            if loc.startswith("/"):
                loc = f"{OAUTH_ISSUER}{loc}"
            code = _extract_code_from_url(loc)
            if code:
                return code
            code, _ = self._oauth_follow_for_code(loc, referer=consent_url)
            if not code:
                code = self._oauth_allow_redirect_extract_code(loc, referer=consent_url)
            return code

        if resp.status_code != 200:
            return None

        try:
            ws_data = resp.json()
        except Exception:
            return None

        ws_next = ws_data.get("continue_url", "")
        orgs = ws_data.get("data", {}).get("orgs", [])

        org_id = None
        project_id = None
        if orgs:
            org_id = (orgs[0] or {}).get("id")
            projects = (orgs[0] or {}).get("projects", [])
            if projects:
                project_id = (projects[0] or {}).get("id")

        if org_id:
            org_body = {"org_id": org_id}
            if project_id:
                org_body["project_id"] = project_id
            h_org = dict(h)
            if ws_next:
                h_org["Referer"] = ws_next if ws_next.startswith("http") else f"{OAUTH_ISSUER}{ws_next}"
            resp_org = self.session.post(f"{OAUTH_ISSUER}/api/accounts/organization/select",
                                         json=org_body, headers=h_org, allow_redirects=False,
                                         timeout=30, impersonate=self.impersonate)
            self._print(f"[OAuth] organization/select -> {resp_org.status_code}")
            if resp_org.status_code in (301, 302, 303, 307, 308):
                loc = resp_org.headers.get("Location", "")
                if loc.startswith("/"):
                    loc = f"{OAUTH_ISSUER}{loc}"
                code = _extract_code_from_url(loc)
                if code:
                    return code
                code, _ = self._oauth_follow_for_code(loc, referer=h_org.get("Referer"))
                if not code:
                    code = self._oauth_allow_redirect_extract_code(loc, referer=h_org.get("Referer"))
                return code
            if resp_org.status_code == 200:
                try:
                    org_data = resp_org.json()
                except Exception:
                    return None
                org_next = org_data.get("continue_url", "")
                if org_next:
                    if org_next.startswith("/"):
                        org_next = f"{OAUTH_ISSUER}{org_next}"
                    code, _ = self._oauth_follow_for_code(org_next, referer=h_org.get("Referer"))
                    if not code:
                        code = self._oauth_allow_redirect_extract_code(org_next, referer=h_org.get("Referer"))
                    return code

        if ws_next:
            if ws_next.startswith("/"):
                ws_next = f"{OAUTH_ISSUER}{ws_next}"
            code, _ = self._oauth_follow_for_code(ws_next, referer=consent_url)
            if not code:
                code = self._oauth_allow_redirect_extract_code(ws_next, referer=consent_url)
            return code
        return None

    # ---- Codex OAuth 纯协议 ----

    def perform_codex_oauth_login_http(self, email: str, password: str, mail_token: str = None):
        self._print("[OAuth] 开始执行 Codex OAuth 纯协议流程...")
        self.session.cookies.set("oai-did", self.device_id, domain=".auth.openai.com")
        self.session.cookies.set("oai-did", self.device_id, domain="auth.openai.com")

        code_verifier, code_challenge = _generate_pkce()
        state = secrets.token_urlsafe(24)
        authorize_params = {
            "response_type": "code", "client_id": OAUTH_CLIENT_ID,
            "redirect_uri": OAUTH_REDIRECT_URI, "scope": "openid profile email offline_access",
            "code_challenge": code_challenge, "code_challenge_method": "S256", "state": state,
        }
        authorize_url = f"{OAUTH_ISSUER}/oauth/authorize?{urlencode(authorize_params)}"

        def _oauth_json_headers(referer: str):
            h = {"Accept": "application/json", "Content-Type": "application/json",
                 "Origin": OAUTH_ISSUER, "Referer": referer,
                 "User-Agent": self.ua, "oai-device-id": self.device_id}
            h.update(_make_trace_headers())
            return h

        def _bootstrap_oauth_session():
            self._print("[OAuth] 1/7 GET /oauth/authorize")
            try:
                r = self.session.get(authorize_url, headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Referer": f"{self.BASE}/", "Upgrade-Insecure-Requests": "1", "User-Agent": self.ua,
                }, allow_redirects=True, timeout=30, impersonate=self.impersonate)
            except Exception as e:
                self._print(f"[OAuth] /oauth/authorize 异常: {e}")
                return False, ""
            final_url = str(r.url)
            self._print(f"[OAuth] /oauth/authorize -> {r.status_code}, final={final_url[:140]}")
            has_login = any(getattr(c, "name", "") == "login_session" for c in self.session.cookies)
            if not has_login:
                try:
                    r2 = self.session.get(f"{OAUTH_ISSUER}/api/oauth/oauth2/auth",
                                          headers={"Accept": "text/html", "Referer": authorize_url,
                                                   "User-Agent": self.ua},
                                          params=authorize_params, allow_redirects=True,
                                          timeout=30, impersonate=self.impersonate)
                    final_url = str(r2.url)
                except Exception:
                    pass
                has_login = any(getattr(c, "name", "") == "login_session" for c in self.session.cookies)
            return has_login, final_url

        def _post_authorize_continue(referer_url: str):
            sentinel = build_sentinel_token(self.session, self.device_id, flow="authorize_continue",
                                            user_agent=self.ua, sec_ch_ua=self.sec_ch_ua, impersonate=self.impersonate)
            if not sentinel:
                self._print("[OAuth] authorize_continue sentinel 失败")
                return None
            headers = _oauth_json_headers(referer_url)
            headers["openai-sentinel-token"] = sentinel
            try:
                return self.session.post(f"{OAUTH_ISSUER}/api/accounts/authorize/continue",
                                         json={"username": {"kind": "email", "value": email}},
                                         headers=headers, timeout=30, allow_redirects=False,
                                         impersonate=self.impersonate)
            except Exception as e:
                self._print(f"[OAuth] authorize/continue 异常: {e}")
                return None

        has_login_session, authorize_final_url = _bootstrap_oauth_session()
        if not authorize_final_url:
            return None

        continue_referer = authorize_final_url if authorize_final_url.startswith(OAUTH_ISSUER) else f"{OAUTH_ISSUER}/log-in"

        self._print("[OAuth] 2/7 POST /api/accounts/authorize/continue")
        resp_continue = _post_authorize_continue(continue_referer)
        if resp_continue is None:
            return None

        if resp_continue.status_code == 400 and "invalid_auth_step" in (resp_continue.text or ""):
            self._print("[OAuth] invalid_auth_step, 重新 bootstrap")
            has_login_session, authorize_final_url = _bootstrap_oauth_session()
            if not authorize_final_url:
                return None
            continue_referer = authorize_final_url if authorize_final_url.startswith(OAUTH_ISSUER) else f"{OAUTH_ISSUER}/log-in"
            resp_continue = _post_authorize_continue(continue_referer)
            if resp_continue is None:
                return None

        if resp_continue.status_code != 200:
            self._print(f"[OAuth] 邮箱提交失败: {resp_continue.text[:180]}")
            return None

        try:
            continue_data = resp_continue.json()
        except Exception:
            return None

        continue_url = continue_data.get("continue_url", "")
        page_type = (continue_data.get("page") or {}).get("type", "")

        self._print("[OAuth] 3/7 POST /api/accounts/password/verify")
        sentinel_pwd = build_sentinel_token(self.session, self.device_id, flow="password_verify",
                                            user_agent=self.ua, sec_ch_ua=self.sec_ch_ua, impersonate=self.impersonate)
        if not sentinel_pwd:
            return None

        headers_verify = _oauth_json_headers(f"{OAUTH_ISSUER}/log-in/password")
        headers_verify["openai-sentinel-token"] = sentinel_pwd

        try:
            resp_verify = self.session.post(f"{OAUTH_ISSUER}/api/accounts/password/verify",
                                            json={"password": password}, headers=headers_verify,
                                            timeout=30, allow_redirects=False, impersonate=self.impersonate)
        except Exception as e:
            self._print(f"[OAuth] password/verify 异常: {e}")
            return None

        if resp_verify.status_code != 200:
            self._print(f"[OAuth] 密码校验失败: {resp_verify.text[:180]}")
            return None

        try:
            verify_data = resp_verify.json()
        except Exception:
            return None

        continue_url = verify_data.get("continue_url", "") or continue_url
        page_type = (verify_data.get("page") or {}).get("type", "") or page_type

        # OTP 阶段
        need_oauth_otp = (page_type == "email_otp_verification"
                          or "email-verification" in (continue_url or "")
                          or "email-otp" in (continue_url or ""))

        if need_oauth_otp:
            self._print("[OAuth] 4/7 检测到邮箱 OTP 验证")
            if not mail_token:
                self._print("[OAuth] 需要 OTP 但未提供 mail_token")
                return None
            headers_otp = _oauth_json_headers(f"{OAUTH_ISSUER}/email-verification")
            tried_codes = set()
            otp_success = False
            otp_deadline = time.time() + 120
            while time.time() < otp_deadline and not otp_success:
                messages = self._fetch_emails(mail_token) or []
                candidate_codes = []
                for msg in messages[:12]:
                    code = None
                    # Try inline content first (like workers do)
                    inline_content = msg.get("text") or msg.get("html") or msg.get("raw") or msg.get("source") or ""
                    if inline_content:
                        code = self._extract_verification_code(inline_content)
                    
                    # Try fetching detail if inline extraction failed
                    if not code:
                        msg_id = msg.get("id") or msg.get("@id") or msg.get("message_id")
                        if msg_id:
                            detail = self._fetch_email_detail(mail_token, str(msg_id))
                            if detail:
                                content = detail.get("text") or detail.get("html") or detail.get("source") or ""
                                code = self._extract_verification_code(content)
                    
                    if code and code not in tried_codes:
                        candidate_codes.append(code)
                if not candidate_codes:
                    time.sleep(2)
                    continue
                for otp_code in candidate_codes:
                    tried_codes.add(otp_code)
                    self._print(f"[OAuth] 尝试 OTP: {otp_code}")
                    try:
                        resp_otp = self.session.post(f"{OAUTH_ISSUER}/api/accounts/email-otp/validate",
                                                     json={"code": otp_code}, headers=headers_otp,
                                                     timeout=30, allow_redirects=False, impersonate=self.impersonate)
                    except Exception:
                        continue
                    if resp_otp.status_code != 200:
                        continue
                    try:
                        otp_data = resp_otp.json()
                    except Exception:
                        continue
                    continue_url = otp_data.get("continue_url", "") or continue_url
                    page_type = (otp_data.get("page") or {}).get("type", "") or page_type
                    otp_success = True
                    break
                if not otp_success:
                    time.sleep(2)
            if not otp_success:
                self._print(f"[OAuth] OTP 验证失败")
                return None

        # 提取 code
        code = None
        consent_url = continue_url
        if consent_url and consent_url.startswith("/"):
            consent_url = f"{OAUTH_ISSUER}{consent_url}"
        if not consent_url and "consent" in page_type:
            consent_url = f"{OAUTH_ISSUER}/sign-in-with-chatgpt/codex/consent"
        if consent_url:
            code = _extract_code_from_url(consent_url)

        if not code and consent_url:
            self._print("[OAuth] 5/7 跟随 continue_url 提取 code")
            code, _ = self._oauth_follow_for_code(consent_url, referer=f"{OAUTH_ISSUER}/log-in/password")

        consent_hint = (("consent" in (consent_url or "")) or ("sign-in-with-chatgpt" in (consent_url or ""))
                        or ("workspace" in (consent_url or "")) or ("organization" in (consent_url or ""))
                        or ("consent" in page_type) or ("organization" in page_type))

        if not code and consent_hint:
            if not consent_url:
                consent_url = f"{OAUTH_ISSUER}/sign-in-with-chatgpt/codex/consent"
            self._print("[OAuth] 6/7 执行 workspace/org 选择")
            code = self._oauth_submit_workspace_and_org(consent_url)

        if not code:
            fallback_consent = f"{OAUTH_ISSUER}/sign-in-with-chatgpt/codex/consent"
            self._print("[OAuth] 6/7 回退 consent 路径重试")
            code = self._oauth_submit_workspace_and_org(fallback_consent)
            if not code:
                code, _ = self._oauth_follow_for_code(fallback_consent, referer=f"{OAUTH_ISSUER}/log-in/password")

        if not code:
            self._print("[OAuth] 未获取到 authorization code")
            return None

        self._print("[OAuth] 7/7 POST /oauth/token")
        token_resp = self.session.post(f"{OAUTH_ISSUER}/oauth/token",
                                       headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": self.ua},
                                       data={"grant_type": "authorization_code", "code": code,
                                             "redirect_uri": OAUTH_REDIRECT_URI, "client_id": OAUTH_CLIENT_ID,
                                             "code_verifier": code_verifier},
                                       timeout=60, impersonate=self.impersonate)
        self._print(f"[OAuth] /oauth/token -> {token_resp.status_code}")

        if token_resp.status_code != 200:
            self._print(f"[OAuth] token 交换失败: {token_resp.text[:200]}")
            return None

        try:
            data = token_resp.json()
        except Exception:
            return None
        if not data.get("access_token"):
            return None

        self._print("[OAuth] Codex Token 获取成功 ✅")
        return data


# ================= 并发批量注册 =================

def _register_one(idx, total, proxy, output_file, stop_event=None):
    """单个注册任务（线程内运行）：DuckMail 创建 → 注册 → Team 邀请 → Codex OAuth"""
    def _stopped():
        return stop_event and stop_event.is_set()

    reg = None
    mail_token = None  # 用于 finally 中清理临时邮箱
    result = (False, None, "未知错误")
    try:
        if _stopped():
            return False, None, "任务已停止"

        reg = ChatGPTRegister(proxy=proxy, tag=f"{idx}")

        # 1. 创建临时邮箱
        reg._print("[邮箱] 创建临时邮箱...")
        email, email_pwd, mail_token = reg.create_temp_email()
        tag = email.split("@")[0]
        reg.tag = tag

        if _stopped():
            result = (False, None, "任务已停止")
            return result

        chatgpt_password = _generate_password()
        name = _random_name()
        birthdate = _random_birthdate()

        with _print_lock:
            print(f"\n{'='*60}")
            print(f"  [{idx}/{total}] 注册: {email}")
            print(f"  ChatGPT密码: {chatgpt_password}")
            print(f"  邮箱密码: {email_pwd}")
            print(f"  姓名: {name} | 生日: {birthdate}")
            print(f"{'='*60}")

        # 2. 执行注册流程
        reg.run_register(email, chatgpt_password, name, birthdate, mail_token)

        if _stopped():
            result = (False, None, "任务已停止")
            return result

        # 3. Team 邀请
        reg._print("📨 发送 Team 邀请...")
        invite_ok = auto_invite_to_team(email, tag=tag)
        if invite_ok:
            reg._print("⏳ 等待邀请生效...")
            # 可中断的等待：每秒检查一次停止信号
            for _ in range(5):
                if _stopped():
                    result = (False, None, "任务已停止")
                    return result
                time.sleep(1)

        if _stopped():
            result = (False, None, "任务已停止")
            return result

        # 4. Codex OAuth
        oauth_ok = True
        if ENABLE_OAUTH:
            reg._print("[OAuth] 开始获取 Codex Token...")
            tokens = reg.perform_codex_oauth_login_http(email, chatgpt_password, mail_token=mail_token)
            oauth_ok = bool(tokens and tokens.get("access_token"))
            if oauth_ok:
                _save_codex_tokens(email, tokens)
                reg._print("[OAuth] Token 已保存 ✅")
            else:
                if OAUTH_REQUIRED:
                    raise Exception("OAuth 获取失败（oauth_required=true）")
                reg._print("[OAuth] 获取失败（按配置继续）")

        if _stopped():
            result = (False, None, "任务已停止")
            return result

        # 5. 保存结果
        with _file_lock:
            with open(output_file, "a", encoding="utf-8") as out:
                out.write(f"{email}----{chatgpt_password}----{email_pwd}----oauth={'ok' if oauth_ok else 'fail'}\n")

        save_to_csv(email, chatgpt_password, email_pwd, oauth_status="ok" if oauth_ok else "fail")

        with _print_lock:
            print(f"\n[OK] [{tag}] {email} 注册成功! 🎉")
        result = (True, email, None)
        return result

    except Exception as e:
        error_msg = str(e)
        with _print_lock:
            print(f"\n[FAIL] [{idx}] 注册失败: {error_msg}")
            traceback.print_exc()
        result = (False, None, error_msg)
        return result

    finally:
        # CloudflareMail 模式下，无论成功失败都删除临时邮箱，避免残留
        if MAIL_PROVIDER == "cloudflare" and mail_token and reg:
            reg._delete_temp_email_cf(mail_token)


def run_batch(total_accounts: int = 4, output_file="registered_accounts.txt",
              max_workers=1, proxy=None, stop_event=None):
    """并发批量注册 - DuckMail 临时邮箱 + Team 邀请 + Codex OAuth"""
    # 仅在使用 DuckMail 时才需要 BEARER token，CloudflareMail 走自己的认证逻辑
    if MAIL_PROVIDER != "cloudflare" and not DUCKMAIL_BEARER:
        print("❌ 错误: 未设置 DUCKMAIL_BEARER")
        return

    actual_workers = min(max_workers, total_accounts)
    print(f"\n{'#'*60}")
    print(f"  ChatGPT 批量自动注册 (纯协议版)")
    print(f"  注册数量: {total_accounts} | 并发数: {actual_workers}")
    print(f"  DuckMail: {DUCKMAIL_API_BASE}")
    print(f"  Teams: {len(TEAMS)} 个")
    print(f"  OAuth: {'开启' if ENABLE_OAUTH else '关闭'} | required: {'是' if OAUTH_REQUIRED else '否'}")
    if ENABLE_OAUTH:
        print(f"  OAuth Issuer: {OAUTH_ISSUER}")
        print(f"  OAuth Client: {OAUTH_CLIENT_ID}")
        print(f"  Token输出: {TOKEN_JSON_DIR}/, {AK_FILE}, {RK_FILE}")
    print(f"  输出文件: {output_file}")
    print(f"{'#'*60}\n")

    success_count = 0
    fail_count = 0
    start_time = time.time()

    # total_accounts 代表"成功数量"目标，失败自动补充，最多尝试 total_accounts*3 次防止无限循环
    max_attempts = total_accounts * 3
    attempt_idx = 0
    pending = set()

    executor = ThreadPoolExecutor(max_workers=actual_workers)
    try:
        # 初始填满 worker 池
        initial = min(actual_workers, max_attempts)
        while attempt_idx < initial:
            attempt_idx += 1
            f = executor.submit(_register_one, attempt_idx, total_accounts, proxy, output_file, stop_event)
            pending.add(f)

        while pending:
            if stop_event and stop_event.is_set():
                break

            done, pending = concurrent.futures.wait(pending, return_when=concurrent.futures.FIRST_COMPLETED)

            for future in done:
                try:
                    ok, email, err = future.result()
                    if ok:
                        success_count += 1
                    else:
                        fail_count += 1
                        if err != "任务已停止":
                            print(f"  [第{attempt_idx}次尝试] 失败: {err}")
                except Exception as e:
                    fail_count += 1
                    with _print_lock:
                        print(f"[FAIL] 线程异常: {e}")

                # 达到成功目标，取消剩余排队任务
                if success_count >= total_accounts:
                    for pf in pending:
                        pf.cancel()
                    pending.clear()
                    break

                # 未达目标且未超最大尝试次数，补充新任务
                if (success_count < total_accounts
                        and attempt_idx < max_attempts
                        and not (stop_event and stop_event.is_set())):
                    attempt_idx += 1
                    new_f = executor.submit(_register_one, attempt_idx, total_accounts, proxy, output_file, stop_event)
                    pending.add(new_f)

    finally:
        # wait=False: 不等待运行中的线程；cancel_futures=True: 取消排队中的任务
        executor.shutdown(wait=False, cancel_futures=True)
        if stop_event and stop_event.is_set():
            print("⚠️ 任务已强制停止")

    elapsed = time.time() - start_time
    avg = elapsed / attempt_idx if attempt_idx else 0
    print(f"\n{'#'*60}")
    print(f"  注册完成! 耗时 {elapsed:.1f} 秒")
    print(f"  成功目标: {total_accounts} | 实际成功: {success_count} | 失败/重试: {fail_count} | 总尝试: {attempt_idx}")
    print(f"  平均速度: {avg:.1f} 秒/次")
    if success_count > 0:
        print(f"  结果文件: {output_file}")
    print(f"{'#'*60}")


def main():
    print("=" * 60)
    print("  ChatGPT 批量自动注册工具 (纯协议版)")
    print("  注册 → Team 邀请 → Codex OAuth 全流程自动化")
    print("=" * 60)

    if MAIL_PROVIDER != "cloudflare" and not DUCKMAIL_BEARER:
        print("\n⚠️  警告: 未设置 DUCKMAIL_BEARER")
        print("   请编辑 config.json 设置 duckmail_bearer")
        print("   按 Enter 继续...")
        input()

    proxy = DEFAULT_PROXY
    if proxy:
        print(f"[Info] 使用代理: {proxy}")
    else:
        env_proxy = (os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
                     or os.environ.get("ALL_PROXY") or os.environ.get("all_proxy"))
        if env_proxy:
            print(f"[Info] 检测到环境变量代理: {env_proxy}")
            proxy = env_proxy
        else:
            proxy_input = input("输入代理地址 (留空=不使用代理): ").strip()
            proxy = proxy_input or None

    if proxy:
        print(f"[Info] 使用代理: {proxy}")

    count_input = input(f"\n注册账号数量 (默认 {DEFAULT_TOTAL_ACCOUNTS}): ").strip()
    total_accounts = int(count_input) if count_input.isdigit() and int(count_input) > 0 else DEFAULT_TOTAL_ACCOUNTS

    workers_input = input("并发数 (默认 1): ").strip()
    max_workers = int(workers_input) if workers_input.isdigit() and int(workers_input) > 0 else 1

    run_batch(total_accounts=total_accounts, output_file=DEFAULT_OUTPUT_FILE,
              max_workers=max_workers, proxy=proxy)


if __name__ == "__main__":
    main()