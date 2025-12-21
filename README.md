# Gamemale Daily Tasks (Refactored) 🚀

高效、健壮的 Gamemale 论坛自动化脚本，基于 API 直接通信和本地验证码识别，支持 GitHub Actions 无人值守运行。

## ✨ 功能特性 (v2.1)

- 🚀 **性能卓越**: 通过直接 API 调用代替页面抓取，执行速度提升 **70%+**。
- 🧠 **本地验证码识别**: 集成 `ddddocr`，实现本地、免费、高效的登录验证码识别。
- 🍪 **智能登录**: 优先使用 Cookie 登录，失败时自动回退到密码登录（最多8次尝试）。
- 🏗️ **现代化架构**: 采用面向对象设计，代码结构清晰，易于维护和扩展。
- 🔄 **核心任务自动化**:
  - 每日自动签到
  - 每日自动抽奖
  - **智能日志互动**: 自动为最新日志“震惊”，精确计数新互动，并确保在无新互动时也能继续执行关联任务（如访问空间、打招呼）。
  - 智能访问用户空间
  - **动态用户打招呼** (新功能!)
- 🔔 **多渠道通知**: 支持企业微信、Telegram、Email 和控制台输出详细的图文报告。
- ⚙️ **集中化配置**: 所有配置通过单个 JSON 对象管理，部署简单。
- 🕒 **定时执行**: 通过 GitHub Actions 每日自动运行。

## 登录方式

脚本支持两种登录方式，按优先级自动选择：

1.  **Cookie 登录 (推荐)**
    - **优点**: 速度最快，最稳定，无需验证码。
    - **缺点**: Cookie 会过期，需要定期更新。

2.  **密码登录 (备用方案)**
    - **优点**: 长期有效。
    - **缺点**: 需要识别验证码，虽然 `ddddocr` 成功率高，但仍有失败可能。

## 环境要求

- Python 3.8+
- `pip install -r requirements.txt`

## 🚀 快速开始

### 本地运行

1.  **克隆项目**
    ```bash
    git clone https://github.com/your-username/your-repo.git
    cd your-repo
    ```

2.  **安装依赖**
    ```bash
    pip install -r requirements.txt
    ```

3.  **配置 `config.json`**
    - 复制 `config.example.json` 并重命名为 `config.json`。
    - 编辑 `config.json`，填入你的个人信息（见下方配置说明）。

4.  **运行脚本**
    ```bash
    python gamemale_daily.py
    ```

### GitHub Actions 部署

1.  **Fork/创建仓库**
    - Fork 本项目或创建一个新的 **私有** 仓库，并将项目文件上传。

2.  **配置 `APP_CONFIG_JSON` Secret**
    - 在你的 GitHub 仓库中，进入 `Settings` -> `Secrets and variables` -> `Actions`。
    - 点击 `New repository secret` 创建一个新的 Secret。
    - **Name**: `APP_CONFIG_JSON`
    - **Value**: 粘贴下方 JSON 内容，并根据说明修改。

    ```json
    {
      "gamemale": {
        "cookie": "你的论坛Cookie字符串",
        "username": "你的论坛用户名",
        "password": "你的论坛密码",
        "questionid": "0",
        "answer": "",
        "auto_exchange_enabled": true
      },
      "notification": {
        "enabled": true,
        "type": "console",
        "telegram": {
          "bot_token": "",
          "chat_id": ""
        },
        "wechat": {
          "webhook": ""
        },
        "email": {
          "smtp_server": "smtp.example.com",
          "smtp_port": 587,
          "username": "your_email@example.com",
          "password": "your_email_password",
          "from": "sender@example.com",
          "to": "recipient@example.com"
        }
      }
    }
    ```

3.  **启用 Actions**
    - 脚本默认会在每天北京时间 0 点自动运行。你也可以在 Actions 页面手动触发。

## ⚙️ 配置说明

### `gamemale` (论坛配置)

这部分包含了所有与 Gamemale 论坛账户和登录相关的设置。

-   `cookie`: **(字符串, 推荐)**
    -   **说明**: 你的论坛登录凭证。提供此项可实现最快速、最稳定的登录，因为它能跳过用户名/密码和验证码环节。
    -   **如何获取**:
        1.  在电脑浏览器中登录 Gamemale 论坛。
        2.  按 `F12` 打开开发者工具。
        3.  切换到 `网络` (Network) 标签页。
        4.  刷新页面，找到任意一个对 `gamemale.com` 的请求。
        5.  在请求头 (Request Headers) 中找到 `Cookie:` 字段，并复制其完整的字符串值。
    -   **注意**: Cookie 会定期失效，届时需要手动更新。

-   `username`: **(字符串, 备用)**
    -   **说明**: 你的论坛用户名。仅在 `cookie` 未提供或失效时，脚本才会尝试使用此项进行密码登录。

-   `password`: **(字符串, 备用)**
    -   **说明**: 你的论坛密码。与 `username` 配套使用。

-   `questionid`: **(字符串, 可选)**
    -   **说明**: 登录安全问题的 ID。如果你的账户设置了安全问题，请填写对应问题的数字ID。如果未设置，请保持为 `"0"`。
    -   **可选值**:
        -   `"1"`: 母亲的名字
        -   `"2"`: 爷爷的名字
        -   `"3"`: 父亲出生的城市
        -   `"4"`: 您其中一位老师的名字
        -   `"5"`: 您个人计算机的型号
        -   `"6"`: 您最喜欢的餐馆名称
        -   `"7"`: 驾驶执照最后四位数字

-   `answer`: **(字符串, 可选)**
    -   **说明**: 安全问题的答案。与 `questionid` 配套使用。

-   `auto_exchange_enabled`: **(布尔值, 可选, 默认为 true)**
    -   **说明**: 是否开启“血液自动兑换旅程”功能。如果血液超过34，且配置了密码，脚本会尝试兑换。设置为 `false` 可禁用此功能。

### `notification` (通知配置)

这部分用于配置任务完成后的报告推送。

-   `enabled`: **(布尔值)**
    -   **说明**: 控制是否启用通知功能。设置为 `true` 启用，`false` 禁用。

-   `type`: **(字符串)**
    -   **说明**: 指定发送通知的渠道。
    -   **可选值**:
        -   `"console"`: (默认) 直接在日志中打印详细报告。
        -   `"telegram"`: 通过 Telegram Bot 发送。
        -   `"wechat"`: 通过企业微信应用机器人发送。
        -   `"email"`: 通过 SMTP 发送邮件。

-   `telegram`: **(对象, 可选)**
    -   **说明**: 如果 `type` 设置为 `"telegram"`，则需要填写此部分。
    -   `bot_token`: 你的 Telegram Bot 的 Token。
    -   `chat_id`: 接收通知的聊天或频道的 ID。

-   `wechat`: **(对象, 可选)**
    -   **说明**: 如果 `type` 设置为 `"wechat"`，则需要填写此部分。
    -   `webhook`: 企业微信群机器人的 Webhook 地址。

-   `email`: **(对象, 可选)**
    -   **说明**: 如果 `type` 设置为 `"email"`，则需要填写此部分的 SMTP 服务器信息。请确保你的邮箱开启了 SMTP 服务，并可能需要使用授权码而非登录密码。
    -   `smtp_server`: **(字符串)** SMTP 服务器地址。例如，QQ邮箱是 `"smtp.qq.com"`，Gmail 是 `"smtp.gmail.com"`。
    -   `smtp_port`: **(整数)** SMTP 服务器端口。通常，加密端口是 `465` (SSL) 或 `587` (TLS)，未加密端口是 `25`。脚本目前使用 `587` (TLS)。
    -   `username`: **(字符串)** 你的发件邮箱地址。例如 `"your_account@qq.com"`。
    -   `password`: **(字符串)** **授权码**而非邮箱登录密码。出于安全原因，大多数邮箱服务商要求使用专用的SMTP授权码。请登录你的邮箱网页版，在设置中查找并生成它。
    -   `from`: **(字符串)** 发件人地址，通常与 `username` 相同。
    -   `to`: **(字符串)** 收件人地址。可以是单个地址，也可以是多个地址，用逗号 `,` 分隔。

    **示例 (以QQ邮箱为例):**
    ```json
    "email": {
      "smtp_server": "smtp.qq.com",
      "smtp_port": 587,
      "username": "123456@qq.com",
      "password": "这里填写生成的SMTP授权码",
      "from": "123456@qq.com",
      "to": "recipient1@example.com,recipient2@another.com"
    }
    ```

## ⚠️ 安全注意事项

-   **私有仓库**: 强烈建议使用私有仓库来运行此项目。
-   **Secrets 管理**: 所有敏感信息都应通过 GitHub Secrets 进行管理，切勿硬编码在代码中。
-   **合规使用**: 本项目仅供学习和个人自动化使用，请遵守 Gamemale 论坛的使用条款。

## 故障排除

1.  **登录失败**
    -   **Cookie 登录**: 检查 `cookie` 是否已过期。
    -   **密码登录**: 确认 `username` 和 `password` 是否正确。验证码识别失败的日志会显示在 Actions 输出中。

2.  **GitHub Actions 失败**
    -   检查 `APP_CONFIG_JSON` Secret 是否已正确配置，并确保其为有效的 JSON 格式。
    -   查看 Actions 日志以获取详细错误信息。

## 许可证

本项目基于 MIT 许可证。
