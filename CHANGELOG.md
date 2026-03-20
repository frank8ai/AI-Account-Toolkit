# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2026-03-19

### Added

- **GPT_register+duckmail+CPA+autouploadsub2api** - ChatGPT 批量自动注册工具（DuckMail + OAuth + Sub2Api 版）
  - 支持 DuckMail 临时邮箱并发注册
  - 自动获取 OTP 验证码
  - OAuth 登录获取 Token
  - 可选自动上传 Token 到 Sub2Api 平台
  - Web 管理界面（端口 18421）

- **team_all-in-one** - ChatGPT Team 一键注册工具
  - Flask Web 管理界面
  - 支持 GPTMail、NPCMail 多种临时邮箱
  - 多线程批量注册
  - OAuth 自动授权
  - Token 导出功能
  - Sub2Api 平台上传支持

- **cloudflare_temp_email** (submodule) - Cloudflare 临时邮箱服务
  - 基于 Cloudflare 免费服务构建
  - Rust WASM 邮件解析，高性能
  - AI 邮件识别，自动提取验证码
  - 支持 SMTP/IMAP 代理
  - Telegram Bot 集成
  - 用户管理，支持 OAuth2、Passkey 登录

- **ABCard** (submodule) - ChatGPT Business/Plus 自动开通工具
  - 全自动注册 ChatGPT 账号
  - 开通 Business (5席位 $0) 或 Plus (个人版 $0)
  - Xvfb + Chrome 自动支付，绕过 hCaptcha
  - Web UI (Streamlit) 操作界面
  - 兑换码管控系统

- **OpenAI 相关子模块**
  - **chatgpt-creator** (submodule) - ChatGPT 账号创建工具
  - **openai-oauth** (submodule) - OpenAI OAuth 认证工具

- **Gemini 相关子模块**
  - **gemini-balance-do** (submodule) - Gemini 余额查询工具

- **Codex 相关子模块**
  - **codex-lb** (submodule) - Codex 负载均衡工具

- **Claude 相关子模块**
  - **claude-key-switch** (submodule) - Claude 密钥切换工具

- **通用工具子模块**
  - **Ultimate-openai-gemini-claude-api-key-scraper** (submodule) - 多平台 API 密钥抓取工具

### Updated

- 项目结构优化，整合多个注册工具
- 根目录 README 添加新子项目导航

## [1.0.0] - 2025-02-18

### Added

- **CPAtools** - Codex 账号管理工具
- **GPT-team** - GPT 团队全自动注册工具
- **chatgpt_register_duckmail** - DuckMail 注册工具
- **codex** - Codex 相关工具
- **freemail** - 临时邮箱服务
- **merge-mailtm-share** - MailTM 邮箱合并工具
- **ob12api** - OB12 API 服务
- **openai_pool_orchestrator_v5** - OpenAI 账号池管理工具
- **openai_pool_orchestrator-V6** - OpenAI 账号池编排器
- **ClashVerge_** - ClashVerge 非港轮询脚本
- **any-auto-register** (submodule) - 多平台账号自动注册工具

---

**Note**: This changelog documents the major additions and changes to the AI-Account-Toolkit project. For detailed changes to individual submodules, please refer to their respective repositories.
