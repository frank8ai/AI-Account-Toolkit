# OpenAI Pool Orchestrator

OpenAI 账号池编排器 — 自动化注册、Token 管理与多平台账号池维护

## 项目简介

OpenAI Pool Orchestrator 是一个功能强大的工具，专门用于自动化管理 OpenAI 账号池，支持批量注册、Token 管理、多平台同步等功能。该工具通过 Web 界面提供直观的操作体验，同时具备强大的后端功能。

## 功能特点

- **自动化注册**：支持批量自动注册 OpenAI 账号
- **多平台同步**：支持 Sub2Api 和 CPA 平台账号同步
- **代理池管理**：内置代理池支持，自动切换和故障转移
- **邮箱验证**：集成临时邮箱服务，自动处理验证码
- **账号维护**：自动检测和清理异常账号
- **实时监控**：提供实时注册进度和状态监控
- **Web 界面**：直观的 Web 管理界面
- **多线程支持**：支持多线程并行注册

## 技术栈

- Python 3.10+
- FastAPI
- Uvicorn
- curl-cffi
- aiohttp
- requests

## 安装指南

### 1. 克隆项目

```bash
git clone <repository-url>
cd openai_pool_orchestrator-V6
```

### 2. 安装依赖

使用 pip 安装依赖：

```bash
pip install -e .
```

或使用 uv 安装（推荐）：

```bash
uv sync
```

## 配置说明

### 配置文件

项目配置文件位于 `data/sync_config.json`，包含以下主要配置项：

- **base_url**: Sub2Api 平台基础 URL
- **bearer_token**: Sub2Api 平台认证 Token
- **account_name**: 账号名称前缀
- **auto_sync**: 是否自动同步到 Sub2Api
- **cpa_base_url**: CPA 平台基础 URL
- **cpa_token**: CPA 平台认证 Token
- **min_candidates**: 最小候选账号数
- **used_percent_threshold**: 使用百分比阈值
- **auto_maintain**: 是否自动维护
- **maintain_interval_minutes**: 维护间隔（分钟）
- **upload_mode**: 上传模式（snapshot 或 decoupled）
- **mail_providers**: 邮箱提供商列表
- **mail_provider_configs**: 邮箱提供商配置
- **mail_strategy**: 邮箱选择策略（round_robin、random、failover）
- **sub2api_min_candidates**: Sub2Api 最小候选账号数
- **sub2api_auto_maintain**: Sub2Api 是否自动维护
- **sub2api_maintain_interval_minutes**: Sub2Api 维护间隔（分钟）
- **sub2api_maintain_actions**: Sub2Api 维护动作配置
- **proxy**: 固定代理地址
- **auto_register**: 是否自动注册
- **proxy_pool_enabled**: 是否启用代理池
- **proxy_pool_api_url**: 代理池 API URL
- **proxy_pool_auth_mode**: 代理池认证模式（query 或 header）
- **proxy_pool_api_key**: 代理池 API Key
- **proxy_pool_count**: 代理池获取数量
- **proxy_pool_country**: 代理池国家

### 配置示例

```json
{
  "base_url": "https://sub2api.com",
  "bearer_token": "your-bearer-token",
  "account_name": "AutoReg",
  "auto_sync": true,
  "cpa_base_url": "https://cpa.example.com",
  "cpa_token": "your-cpa-token",
  "min_candidates": 800,
  "used_percent_threshold": 95,
  "auto_maintain": true,
  "maintain_interval_minutes": 30,
  "upload_mode": "snapshot",
  "mail_providers": ["mailtm"],
  "mail_provider_configs": {
    "mailtm": {
      "api_base": "https://api.mail.tm",
      "api_key": "",
      "bearer_token": ""
    }
  },
  "mail_strategy": "round_robin",
  "sub2api_min_candidates": 200,
  "sub2api_auto_maintain": true,
  "sub2api_maintain_interval_minutes": 30,
  "sub2api_maintain_actions": {
    "refresh_abnormal_accounts": true,
    "delete_abnormal_accounts": true,
    "dedupe_duplicate_accounts": true
  },
  "proxy": "",
  "auto_register": false,
  "proxy_pool_enabled": true,
  "proxy_pool_api_url": "https://zenproxy.top/api/fetch",
  "proxy_pool_auth_mode": "query",
  "proxy_pool_api_key": "your-proxy-pool-api-key",
  "proxy_pool_count": 1,
  "proxy_pool_country": "US"
}
```

## 使用方法

### 启动服务

```bash
# 使用命令行启动
openai-pool

# 或使用 Python 模块启动
python -m openai_pool_orchestrator
```

服务启动后，访问 http://localhost:18421 进入 Web 管理界面。

### Web 界面操作

1. **配置管理**：在设置页面配置平台参数、邮箱设置和代理设置
2. **账号注册**：在注册页面启动注册任务，可设置工作线程数和目标数量
3. **账号管理**：查看已注册账号的状态和详情
4. **任务监控**：实时查看注册任务的执行状态和日志

### API 接口

#### 1. 获取服务状态

```bash
GET /api/status
```

返回服务运行状态、统计数据等信息。

#### 2. 开始注册任务

```bash
POST /api/start
Content-Type: application/json

{
  "proxy": "",
  "worker_count": 3,
  "target_count": 10,
  "cpa_target_count": 5,
  "sub2api_target_count": 5
}
```

#### 3. 停止注册任务

```bash
POST /api/stop
```

#### 4. 获取配置

```bash
GET /api/config
```

#### 5. 保存配置

```bash
POST /api/config
Content-Type: application/json

{"base_url": "https://sub2api.com", ...}
```

#### 6. 获取账号列表

```bash
GET /api/accounts?status=all&keyword=&page=1&page_size=20
```

#### 7. 维护账号池

```bash
POST /api/maintain
```

## 工作流程

1. **网络环境检查**：验证代理是否可用，IP 所在地是否支持
2. **创建临时邮箱**：通过配置的邮箱提供商创建临时邮箱
3. **OAuth 授权**：生成授权 URL 并处理回调
4. **提交注册**：提交注册信息并等待验证码
5. **验证 OTP**：从临时邮箱获取并验证验证码
6. **创建账户**：完成账户创建流程
7. **获取 Token**：获取访问令牌和刷新令牌
8. **保存 Token**：将 Token 保存到本地
9. **上传平台**：根据配置同步到 Sub2Api 和/或 CPA 平台

## 常见问题

### 1. 注册失败怎么办？

- 检查网络环境和代理设置
- 确认邮箱提供商是否可用
- 查看详细日志了解具体失败原因

### 2. 验证码收不到怎么办？

- 检查邮箱提供商配置
- 确保网络连接稳定
- 尝试更换邮箱提供商

### 3. 如何提高注册成功率？

- 使用高质量的代理
- 适当调整注册速度
- 配置多个邮箱提供商

### 4. 如何监控注册进度？

- 访问 Web 界面查看实时日志
- 通过 API 接口获取任务状态

## 部署建议

### 生产环境部署

1. **使用 Docker**：

```bash
docker-compose up -d
```

2. **配置环境变量**：

```env
# .env 文件
PROXY_POOL_API_KEY=your-api-key
SUB2API_BEARER_TOKEN=your-token
```

3. **设置自动启动**：

```bash
# 系统服务配置
sudo systemctl enable openai-pool.service
```

### 性能优化

- 根据服务器性能调整工作线程数
- 使用高质量的代理池
- 合理配置邮箱提供商

## 许可证

MIT License - 详见 LICENSE 文件

## 贡献

欢迎提交 Issue 和 Pull Request 来改进这个项目！

## 更新日志

### v2.0.0
- 重构核心架构
- 支持多邮箱提供商
- 优化代理池管理
- 新增 Web 界面
- 支持多平台同步

### v1.0.0
- 初始版本
- 基本注册功能
- Sub2Api 平台支持
