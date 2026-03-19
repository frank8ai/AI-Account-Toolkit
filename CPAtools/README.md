# CPAtools

ChatGPT 账号全自动管理工具，支持批量注册、自动维护和 Token 管理。

## 项目简介

CPAtools 是一个专门用于管理 ChatGPT 账号的工具，通过自动化流程实现账号的批量注册、健康状态检测和维护。该工具集成了邮件网关功能，能够自动处理 OpenAI 的验证码，实现全流程自动化。

## 功能特点

- **全自动注册**：自动完成邮箱申请、验证码获取、账号创建等流程
- **健康状态检测**：定期检查账号有效性，自动清理失效账号
- **内存邮件网关**：内置邮件服务器，处理 OpenAI 验证码
- **Cloudflare 集成**：支持通过 Cloudflare Worker 接收邮件
- **代理支持**：可配置代理服务器，提高注册成功率
- **自动上传**：将生成的 Token 自动上传到 CLIProxyAPI
- **智能延迟**：根据注册结果动态调整注册间隔

## 技术栈

- Python 3.7+
- curl-cffi
- requests
- http.server
- threading

## 安装指南

### 1. 克隆项目

```bash
git clone <repository-url>
cd AI-Account-Toolkit/CPAtools
```

### 2. 安装依赖

```bash
pip install curl-cffi requests
```

## 配置说明

### 1. Cloudflare 配置

1. **配置 Email Routing**：
   - 登录 Cloudflare 控制台
   - 进入 `Email` → `Email Routing`
   - 添加您的域名并配置路由规则

2. **创建 Worker**：
   - 进入 `Workers & Pages`
   - 创建新的 Worker
   - 复制以下代码并部署：

```javascript
export default {
  async email(message, env, ctx) {
    const rawEmail = await new Response(message.raw).text();
    const vps_url = "http://{您的服务器IP}:8080/webhook";
    await fetch(vps_url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        to: message.to,
        from: message.from,
        raw: rawEmail
      })
    });
  }
};
```

### 2. 脚本配置

脚本支持以下命令行参数：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| --base-url | CLIProxyAPI 地址 | http://localhost:8317 |
| --mgmt-key | 管理密钥（必填） | - |
| --target | 账号目标数量 | 100 |
| --check-interval | 检测间隔（秒） | 3600 |
| --reg-delay-min | 最小注册延迟（秒） | 60 |
| --reg-delay-max | 最大注册延迟（秒） | 120 |
| --proxy | 代理地址 | None |
| --domain | 邮箱域名 | example.com |

## 使用方法

### 启动服务

```bash
python manager.py --mgmt-key your-management-key --domain your-domain.com --target 50
```

### 完整示例

```bash
python manager.py \
  --base-url http://localhost:8317 \
  --mgmt-key your-secret-key \
  --target 100 \
  --check-interval 3600 \
  --reg-delay-min 60 \
  --reg-delay-max 120 \
  --proxy http://your-proxy:port \
  --domain your-domain.com
```

## 工作流程

1. **启动邮件网关**：在 8080 端口启动内存邮件网关服务器
2. **健康状态检查**：定期检查已注册账号的有效性
3. **账号注册**：当账号数量低于目标时，自动执行注册流程
4. **验证码处理**：通过 Cloudflare Worker 接收并处理验证码
5. **Token 上传**：将成功注册的账号 Token 上传到 CLIProxyAPI
6. **智能调整**：根据注册结果动态调整注册间隔

## 注册流程

1. **申请邮箱**：生成随机邮箱地址
2. **OAuth 初始化**：生成授权 URL 和状态参数
3. **Sentinel 验证**：处理 OpenAI 的安全验证
4. **提交注册**：提交邮箱和密码
5. **发送验证码**：请求 OpenAI 发送验证码
6. **接收验证码**：通过邮件网关接收并提取验证码
7. **验证 OTP**：提交验证码进行验证
8. **创建账户**：完成账户创建
9. **选择 Workspace**：选择默认工作区
10. **获取 Token**：获取访问令牌和刷新令牌
11. **上传 Token**：将 Token 上传到 CLIProxyAPI

## 常见问题

### 1. 验证码收不到怎么办？

- 确保 Cloudflare Worker 配置正确
- 检查服务器 8080 端口是否开放
- 确认域名 MX 记录配置正确

### 2. 注册失败率高怎么办？

- 使用高质量的代理
- 增加注册延迟
- 检查网络环境是否被 OpenAI 限制

### 3. 如何提高注册成功率？

- 使用稳定的代理 IP
- 合理设置注册间隔
- 确保邮箱域名配置正确

### 4. 如何监控注册状态？

- 查看控制台输出的日志
- 检查 CLIProxyAPI 中的账号数量

## 注意事项

1. **邮箱域名**：需要拥有一个域名并配置 MX 记录指向 Cloudflare
2. **代理设置**：建议使用高质量的代理，避免 IP 被封禁
3. **频率控制**：合理设置注册间隔，避免触发 OpenAI 的风控机制
4. **安全配置**：管理密钥应妥善保管，避免泄露

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request 来改进这个项目！
