# 域名自动续期助手

本项目是一组基于 GitHub Actions 的自动化脚本，分别利用 **DNSHE** 与 **DigitalPlat** 免费域名 API 实现域名的自动续期，并通过 **SMTP 邮件** 推送执行结果，确保您的免费域名永不过期。

- **DNSHE**：支持多账号，可同时配置最多 10 个 DNSHE 账号，脚本依次处理每个账号下的所有域名，最终汇总为一封邮件报告。
- **DigitalPlat**：单账号模式，自动列出账号下所有域名并按剩余天数智能续期，结果通过邮件推送。

## 🌟 功能特性

- **全自动续期**：每月 1 日自动执行续期操作。

- **多账号支持**：支持同时配置最多 10 个 DNSHE 账号，统一管理、统一报告。

- **多域名支持**：自动遍历每个账户下所有子域名进行批量续期。

- **智能续期**：先检查域名到期时间，仅对剩余天数不足 180 天的域名执行续期。

- **永不过期识别**：识别已设置为永不过期的域名，自动跳过续期。

- **故障隔离**：单个账号处理失败不会中断整体流程，其余账号继续执行。

- **即时通知**：通过 SMTP 邮件推送详细报告，所有账号结果汇总为一封邮件，按账号分段展示，清晰直观。

- **安全合规**：采用 GitHub Secrets 管理密钥，不在代码中硬编码敏感信息。

***

## 📝 更新说明

（2026-08-25）

- **多账号支持**：从单账号升级为多账号模式，支持同时配置最多 10 个 DNSHE 账号（`DNSHE_API_KEY_1` / `DNSHE_API_SECRET_1` 起，依次编号）。

- **账号间间隔**：相邻账号处理之间等待 2 秒，避免触发 API 速率限制。

- **故障隔离**：单个账号认证失败或处理异常时，仅在报告中标注该账号失败，不影响其他账号的续期。

- **汇总邮件**：所有账号的续期结果与到期信息汇总为一封邮件，按账号分段展示。

（2026-07-18）

- **智能续期**：先检查域名到期时间，仅对剩余天数不足 180 天的域名执行续期。

- **永不过期识别**：识别已设置为永不过期的域名，自动跳过续期。

- **通知优化**：推送消息分为两段——第一段展示本次续期结果，第二段汇总所有域名到期时间。

- **通知方式**：使用 SMTP 邮件发送执行报告。

***

## 🚀 快速上手

### 第一步：获取 API 密钥

1. 登录 [DNSHE](https://my.dnshe.com/)。

2. 进入 **"免费域名"** 页面。

3. 在底部的 **"API 管理"** 卡片中点击 **"创建 API 密钥"**。

4. 妥善保存获取到的 `API Key` 和 `API Secret`。

5. 如有多个 DNSHE 账号，依次登录每个账号并重复上述步骤，分别保存各账号的密钥。

### 第二步：准备 SMTP 邮箱

准备 SMTP 服务商提供的服务器地址、端口、账号和密码（部分服务商要求使用"客户端专用密码"或"授权码"）。常见配置如下：

| 服务商 | `SMTP_HOST` | `SMTP_PORT` | 加密方式 |
| ------ | ---------- | ----------- | -------- |
| QQ 邮箱 | `smtp.qq.com` | `465` | SSL |
| 163 邮箱 | `smtp.163.com` | `465` | SSL |
| Gmail | `smtp.gmail.com` | `587` | STARTTLS |

465 端口默认使用 SSL，其他端口默认使用 STARTTLS；也可以通过 `SMTP_USE_SSL` 和 `SMTP_USE_STARTTLS` 显式指定。

### 第三步：配置 GitHub 仓库

1. **Fork 本仓库** 或将脚本及工作流文件上传至您的私有仓库。
2. 进入仓库设置：**Settings** -> **Secrets and variables** -> **Actions**。
3. 点击 **New repository secret**，依次添加以下变量。

#### DNSHE 多账号密钥

支持配置多个账号，编号从 `1` 开始，最多 `10` 个。至少配置第 1 个账号，其余按需添加。

| 变量名称 | 说明 | 示例 |
| -------- | ---- | ---- |
| `DNSHE_API_KEY_1` | 第 1 个账号的 API Key | `cfsd_xxxxxxxxxx` |
| `DNSHE_API_SECRET_1` | 第 1 个账号的 API Secret | `yyyyyyyyyyyy` |
| `DNSHE_API_KEY_2` | 第 2 个账号的 API Key（可选） | `cfsd_aaaaaaaaaa` |
| `DNSHE_API_SECRET_2` | 第 2 个账号的 API Secret（可选） | `zzzzzzzzzzzz` |
| `DNSHE_API_KEY_3` ~ `DNSHE_API_KEY_10` | 第 3~10 个账号的 API Key（可选） | … |
| `DNSHE_API_SECRET_3` ~ `DNSHE_API_SECRET_10` | 第 3~10 个账号的 API Secret（可选） | … |

> **注意**：每个账号的 `API Key` 和 `API Secret` 必须成对配置；若只配置了其中一个，该账号会被跳过并在日志中给出警告。

#### SMTP 邮件通知

| 变量名称 | 说明 | 示例 |
| -------- | ---- | ---- |
| `SMTP_HOST` | SMTP 服务器地址 | `smtp.qq.com` |
| `SMTP_PORT` | SMTP 服务器端口 | `465` |
| `SMTP_USER` | SMTP 登录账号 | `your@qq.com` |
| `SMTP_PASSWORD` | SMTP 密码或授权码 | `xxxxxxxx` |
| `SMTP_FROM` | 发件人地址（可选，默认使用 `SMTP_USER`） | `your@qq.com` |
| `SMTP_TO` | 收件人地址，多个地址用英文逗号分隔 | `me@example.com` |
| `SMTP_USE_SSL` | 是否使用 SSL（可选） | `true` |
| `SMTP_USE_STARTTLS` | 是否使用 STARTTLS（可选） | `false` |

### 第四步：启用自动化

1. 点击仓库顶部的 **Actions** 选项卡。
2. 在左侧选择 **"DNSHE Domain Auto Renew"** 工作流。
3. 点击 **Run workflow** 手动触发一次，验证配置是否正确。

***

## 🌐 DigitalPlat 域名自动续期

本项目也提供基于 **DigitalPlat 免费域名 API** 的自动续期脚本（`renew_digitalplat.py`），逻辑与 DNSHE 脚本一致：自动列出账号下所有域名，仅对剩余天数不足 180 天的域名执行续期，并通过 SMTP 邮件推送执行报告。

**单账号模式**：配置一个 `DIGITALPLAT_API_KEY` 即可。

### 功能特性

- **全自动续期**：每月 1 日自动执行续期操作。

- **智能续期**：先检查域名到期时间，仅对剩余天数不足 180 天的域名执行续期。

- **订阅制域名跳过**：识别 `lifecycle_type` 为 `subscription`（订阅制，由订阅自动续期）的域名，自动跳过手动续费。

- **即时通知**：通过 SMTP 邮件推送详细报告，续期结果与所有域名到期时间分两段展示。

- **安全合规**：采用 GitHub Secrets 管理密钥，不在代码中硬编码敏感信息。

### 第一步：获取 API 密钥

1. 登录 [DigitalPlat 控制台](https://dashboard.digitalplat.org/)。

2. 进入 **Account & security** 页面，创建一个 API Key（按需选择 `domains:read` / `domains:write` 等权限）。

3. 妥善保存形如 `dp_live_xxxxxxxxxxxxxxxxx` 的 API Key。

### 第二步：准备 SMTP 邮箱

与 DNSHE 脚本共用同一套 SMTP 配置，参考上文 [第二步：准备 SMTP 邮箱](#第二步准备-smtp-邮箱)。

### 第三步：配置 GitHub 仓库

进入仓库设置：**Settings** -> **Secrets and variables** -> **Actions**，点击 **New repository secret** 依次添加以下变量。

#### DigitalPlat API 密钥

| 变量名称 | 说明 | 示例 |
| -------- | ---- | ---- |
| `DIGITALPLAT_API_KEY` | DigitalPlat 账号的 API Key（必填） | `dp_live_xxxxxxxxxxxxxxxxx` |
| `DIGITALPLAT_PAYMENT_METHOD` | 续费支付方式（可选，默认 `sandbox`；免费域名请按实际环境调整） | `sandbox` |
| `DIGITALPLAT_RENEW_YEARS` | 续费年数（可选，默认 `1`） | `1` |
| `DIGITALPLAT_RENEW_THRESHOLD_DAYS` | 续期阈值天数（可选，默认 `180`） | `180` |

> **注意**：`DIGITALPLAT_PAYMENT_METHOD` 默认值为文档示例 `sandbox`，若您的免费域名实际支付方式不同，请务必在 Secrets 中配置正确的值，否则续费请求可能被拒绝。

#### SMTP 邮件通知

与 DNSHE 脚本共用，变量列表见上文 [SMTP 邮件通知](#smtp-邮件通知)（`SMTP_HOST`、`SMTP_PORT`、`SMTP_USER`、`SMTP_PASSWORD`、`SMTP_TO` 等）。

### 第四步：启用自动化

1. 点击仓库顶部的 **Actions** 选项卡。
2. 在左侧选择 **"DigitalPlat Domain Auto Renew"** 工作流。
3. 点击 **Run workflow** 手动触发一次，验证配置是否正确。

### 运行计划

- **执行频率**：每月 1 日北京时间 08:00（与 DNSHE 工作流一致）。

- **错误处理**：若获取域名列表失败（如 API Key 无效），报告中标注失败原因并发送通知邮件。

- **未配置密钥**：若未检测到 `DIGITALPLAT_API_KEY`，脚本会输出提示并尝试发送通知邮件。

***

## 📅 运行计划（DNSHE）

- **执行频率**：每月 1 日北京时间 08:00。

- **多账号处理**：脚本按编号顺序依次处理每个账号，相邻账号之间间隔 2 秒，避免触发速率限制。

- **速率限制**：脚本遵循 API 默认的 60 请求 / 分钟限制。

- **错误处理**：若某个账号续期失败（如认证失败、资源不存在等），仅在报告中标注该账号错误，其余账号继续处理；最终所有结果汇总为一封邮件。

- **未配置账号**：若未检测到任何 DNSHE 账号配置，脚本会输出提示并尝试发送通知邮件。

## ⚠️ 安全建议

- **密钥保护**：切勿将 `API Secret` 上传至公开代码库。

- **定期轮换**：建议定期在 DNSHE 后台使用 `regenerate` 操作更新密钥以增强安全性。

- **最小权限**：建议仅为该脚本配置必要的 API 访问权限。

- **多账号密钥**：每个账号的密钥独立管理，轮换时只需更新对应编号的 Secret，不影响其他账号。

***

## 🙏 致谢

本项目得以实现，特别感谢以下平台与技术的支持：

- [**DNSHE**](https://www.dnshe.com/)

- [**OpenCode**](https://github.com/nicepkg/opencode)

- [**DeepSeek**](https://platform.deepseek.com/usage)

- [**Google Gemini**](https://aistudio.google.com/)

***
