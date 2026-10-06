# Gamemale Daily Tasks (Refactored) 🚀

高效、健壮的 Gamemale 论坛自动化脚本，基于 API 直接通信和本地验证码识别，支持 GitHub Actions 无人值守运行。

## ✨ 功能特性 (v2.3)

- 🔎 **可诊断运行**: 支持离线配置检查、在线自检与只查询资产；任务结果决定退出码。
- 🧠 **本地验证码识别**: 集成 `ddddocr`，实现本地、免费、高效的登录验证码识别。
- 🍪 **智能登录**: 优先使用 Cookie 登录，失败时自动回退到密码登录（最多8次尝试）。
- 🏗️ **函数式逻辑**: 页面解析、结果汇总和资产差额使用纯函数，HTTP、等待和文件写入集中在边界。
- 🔄 **核心任务自动化**:
  - 每日自动签到
  - 每日自动抽奖
  - **自动接取与完成任务**: 自动检查“新任务”列表并接取可用任务，支持按 ID、任务名或关键词排除指定任务；已接取任务达到完成条件后自动领取奖励。
  - **挂机时长刷新**: 可配置总挂机时长和刷新间隔，使用登录后的 Session 定时刷新论坛页面以累计在线时间。
  - **智能日志互动**: 自动为最新日志“震惊”，精确计数新互动，并确保在无新互动时也能继续执行关联任务（如访问空间、打招呼）。
  - 智能访问用户空间
  - **动态用户打招呼** (新功能!)
- 🔔 **多渠道通知**: 支持企业微信、Telegram、Email 和控制台输出详细的图文报告。
- 🛡️ **Cloudflare Turnstile 适配**: 自动识别论坛的人机验证页，通过打码平台（2captcha / capsolver / yescaptcha）自动解算放行，无需人工干预。
- ⚙️ **集中化配置**: 所有配置通过单个 JSON 对象管理，部署简单。
- 🕒 **定时执行**: 通过 GitHub Actions 每日自动运行。

## ⚠️ Cloudflare 人机验证适配（重要）

> GameMale 论坛已接入 Cloudflare 防护（边缘 CDN + 源站 Turnstile 人机验证插件
> `dev8133_cloudflare`）。**没有放行标记的访问会话会被返回 "请稍候 / 检查站点连接
> 是否安全" 的验证页**，需要浏览器执行 Cloudflare Turnstile 拿到 token 并提交回
> 论坛后才能继续访问。纯脚本请求（包括本脚本旧版本）都会命中该验证页而全部失败。

本脚本按 **直连 → 打码平台自动解算** 顺序适配：

1. **直连**：总是先直接请求，只有命中验证页才进入下一步（若你的网络/登录 Cookie
   本身放行，全程零开销）；
2. **打码平台解算**（可选配置）：命中验证页时自动调用打码平台解算 Turnstile
   （单次约 ¥0.02~0.05）并提交放行，无需人工干预。

其他保障：每次运行最多解算 `cloudflare.max_solves` 次（默认 2，控制成本）；
解算成功后会把含放行标记的完整 Cookie 回写配置，后续运行大概率直接放行。

### 方式一：打码平台（付费兜底，稳定可靠）

在 [2captcha](https://2captcha.com)、[capsolver](https://www.capsolver.com/zh) 或
[yescaptcha](https://www.yescaptcha.com) 任一平台注册并充值少量余额（Turnstile
单次解算约 ¥0.02~0.05，日常每天 1~2 次几乎可以忽略），然后二选一配置：

- **GitHub Actions（Secret 环境变量）**：在仓库 `Settings -> Secrets and variables ->
  Actions` 中添加：
  - `GAMEMALE_CF_SOLVER` = `2captcha` / `capsolver` / `yescaptcha`
  - `GAMEMALE_CF_API_KEY` = 你的平台 API Key
- **配置文件（支持 全局 + 账户局部 两档，均为 `cloudflare: {solver, api_key, max_solves}` 结构）**：
  全局块放在顶层（与 `accounts` 同级，对所有账户生效）：
  ```yaml
  cloudflare:
    solver: "2captcha"      # 2captcha / capsolver / yescaptcha
    api_key: "你的API Key"
    max_solves: 2           # 单次运行最多解算次数（控制成本，默认 2）
  ```
  账户局部块（可选）：把上面的块复制进某个账户、改缩进即可使用，**局部非空字段
  优先于全局**，未填写的字段自动回落到全局：
  ```yaml
  accounts:
    - cookie: "你的Cookie"
      cloudflare:
        solver: "capsolver"   # 仅该账户改用 capsolver
        max_solves: 1         # 并限制该账户单次最多打码 1 次
  ```
  取值优先级：**账户局部（非空字段）> 顶层全局 > 环境变量 `GAMEMALE_CF_SOLVER` / `GAMEMALE_CF_API_KEY`**。

### 多账户与打码成本

同一批账户运行时脚本内置**放行 Cookie 共享池**：首个遇到验证的账户解算成功后，
其余账户会自动复用其放行标记（日志会出现"复用共享的 Cloudflare 放行 Cookie"），
**通常整批账户每次运行只需打码 1 次**，而不是每账户 1 次。共享仅限人机验证
放行标记（自动过滤 saltkey 等会话 Cookie），绝不混入登录态，跨账户安全。

解算成功后，含放行标记的完整 Cookie 会自动回写各账户配置（日志"已把含放行标记
的 Cookie 回写到配置"），下次运行大概率直接放行、零打码。仅当放行标记失效
（服务端过期等）时才会再次解算，且受 `cloudflare.max_solves` 上限保护。

### 方式二：提供"已过验证"的完整 Cookie（零成本，适合本地/手动更新）

在浏览器中打开 gamemale.com 完成一次人机验证并保持登录，然后按上面「登录方式」
的步骤**复制完整的 Cookie 字符串**填入配置。若该 Cookie 仍带论坛的放行标记，
脚本可直接访问而无需解算；放行标记过期后再用方式一或重新复制。

> 若两种方式都未配置，脚本会在日志中明确提示检测到 Cloudflare 人机验证，
> 而不会静默地把验证页当作正常页面处理。

## 登录方式

脚本支持两种登录方式，按优先级自动选择：

1.  **Cookie 登录 (推荐)**
    - **优点**: 速度最快，最稳定，无需验证码。
    - **缺点**: Cookie 会过期，需要定期更新。

2.  **密码登录 (备用方案)**
    - **优点**: 长期有效。
    - **缺点**: 需要识别验证码，虽然 `ddddocr` 成功率高，但仍有失败可能。

## 环境要求

- Python 3.10+（锁定的 requests 版本需要 Python 3.10 及以上）
- Cookie 登录：`pip install -r requirements.txt`；需要验证码的密码登录：`pip install -r requirements-ocr.txt`

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

    如需本次运行启用挂机刷新，可传入参数：
    ```bash
    python gamemale_daily.py --enable-online --online-time-minutes 30 --online-refresh-interval-seconds 900
    ```

    如只想执行挂机刷新，不执行签到、抽奖等其它任务：
    ```bash
    python gamemale_daily.py --only-online --online-time-minutes 30
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
        "auto_exchange_enabled": true,
        "auto_accept_tasks": true,
        "auto_complete_tasks": true,
        "online_time_minutes": 0,
        "online_refresh_interval_seconds": 900,
        "task_exclude_ids": [],
        "task_exclude_names": [],
        "task_exclude_keywords": []
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

-   `auto_accept_tasks`: **(布尔值, 可选, 默认为 true)**
    -   **说明**: 是否自动检查并接取“新任务”页面中的可接取任务。设置为 `false` 可禁用此功能。

-   `auto_complete_tasks`: **(布尔值, 可选, 默认为 true)**
    -   **说明**: 是否自动检查“进行中的任务”，并在任务进度达到 100% 且可领取奖励时自动领取。设置为 `false` 可禁用此功能。

-   `online_time_minutes`: **(整数, 可选, 默认为 0)**
    -   **说明**: 挂机总时长候选值，单位分钟。默认运行会忽略该值；只有传入 `--enable-online` 或 `--only-online` 时才会读取。也可使用 `online_time_seconds` 直接配置秒数。

-   `online_refresh_interval_seconds`: **(整数, 可选, 默认为 900)**
    -   **说明**: 刷新间隔，单位秒。默认 900 秒，等同示例用户脚本的默认刷新间隔。

### 运行模式与配置来源

两个入口均支持以下参数（示例可替换为 `gamemale_daily_ql.py`）：

```bash
python gamemale_daily.py --check-config
python gamemale_daily.py --check
python gamemale_daily.py --status-only
```

| 模式 | 行为 |
| --- | --- |
| 默认 | 查询初始资产 → 签到/抽奖 → 接任务 → 可选挂机 → 日志/空间/打招呼 → 领奖 → 查询/可选兑换 |
| `--check-config` | 仅离线验证配置并显示来源、Cookie 项数和短指纹；不请求论坛、不输出凭据 |
| `--check` | 验证登录、formhash 与资产解析；不签到、兑换、互动，不回写 Cookie/资产文件，不发送通知 |
| `--status-only` | 登录并查询资产、生成报告；允许更新 Cookie 与资产历史，不执行日常动作 |
| `--only-online` | 仅执行已有挂机刷新流程 |

`--check` 仍可能执行密码登录或 Cloudflare 解算，因此属于在线自检，可能消耗解算额度。需要完全离线时使用 `--check-config`。自检/查询模式不能与 `--enable-online` 同时使用。

两入口使用同一来源优先级：`config.yaml`（青龙为 `GameMale_Config.yaml`）> `APP_CONFIG_JSON` > `GAMEMALE_ACCOUNTS` > `GAMEMALE_COOKIE` > `config.json`。JSON 同时兼容 `accounts` 多账户和旧 `gamemale` 单账户结构，顶层 Cloudflare 配置随账户一起加载。`GAMEMALE_COOKIE` 每行代表一个账户；单账户多行 Cookie 请放在 JSON 的 `cookie` 字段中。

Cookie 输入支持 `Cookie:` 前缀、引号、换行和 JSON 对象。只在确认游客状态时回退密码登录；网络异常或缺少身份标记时明确报告未确认，避免误判过期。文件来源 Cookie 仅回写原加载文件，环境变量/Secrets 不写入其它配置文件。

新增账户参数：

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `captcha_max_retries` | `3` | 每次登录表单的图片识别预算，限定 1–8 次；只有需要验证码时加载 OCR |
| `captcha_precheck` | `true` | 登录提交前由服务端验证识别结果；页面不兼容时可关闭 |
| `asset_history_enabled` | `true` | 仅在取得经登录验证的正 UID 后，按账户保存有效资产快照 |

### 结果与资产报告

任务分别展示成功、已完成、跳过、失败、中断和未确认。启用的必需任务失败时账户计为失败，退出码非零；主动禁用或无须兑换属于跳过。日志扫描不足新增目标且没有明确请求失败时展示“未确认”，不单独导致账户失败；如果互动请求失败则计为失败。“已表过态”单独统计，不冒充今日新增或今日额度已完成。失败账户也进入结果汇总，通知仍通过已有回调（青龙使用内置通知）。

资产报告区分“本次运行前后变化”和“较上次有效采集变化”，均不等同于今日任务收益。无法解析的余额保持缺失，千位分隔符可以正常转换；缺失字段不覆盖历史有效值。历史存于脚本目录 `.gamemale-state/assets.json`，按已验证 UID 隔离，每项保留采集时间，采用原子替换写入并已加入 Git 忽略规则。报告将上次记录时间归纳到资产变化的最后一行；时间不同时按资产名称分组，保留真实基准。状态文件包含 UID 和余额，不含 Cookie 或密码。

当前积分后展示升级预估：沿用 Reference 的 Lv.0–10 门槛 `0 / 3 / 10 / 35 / 70 / 120 / 200 / 300 / 450 / 650 / 900`，显示当前等级预估、下一级积分缺口，以及按 `1 积分 ≈ 34 血液` 折算的血液需求和余额缺口。这是参考规则下的估算，不自动追加兑换；实际门槛、兑换税率与特殊用户组以论坛为准。积分缺失不当作零，血液缺失只显示需求，不判断是否足够；达到参考表最高档时不推测更高等级。

青龙入口不查询或展示“任务总次数统计”；标准入口保留原有统计。

青龙/本地保留脚本目录即可跨运行比较。GitHub Actions 临时 Runner 默认不持久化该目录，因此只保证本次差额；未添加资产文件提交、缓存或上传流程。只读自检不写历史，也不更新比较基准。

查询可安全重试并可中断；抽奖、领奖、兑换等动作在超时/5xx 导致结果不明时不会自动重复提交。明确返回验证页时允许放行后重放；403/503 验证页在普通 HTTP 错误之前处理，未放行会明确失败。

### 挂机参数

不传 `--enable-online` 或 `--only-online` 时，挂机任务默认不运行，并且会忽略配置文件里的挂机相关字段。以下参数会覆盖配置文件，仅影响本次运行：

```bash
python gamemale_daily.py --enable-online --online-time-minutes 30
python gamemale_daily.py --enable-online --online-time-seconds 1800 --online-refresh-interval-seconds 900
python gamemale_daily.py --only-online --online-time-minutes 30
```

`--enable-online` 表示在正常任务流程中启用挂机；`--only-online` 表示只执行挂机。二者都不会自动设置挂机时长，通常需要与 `--online-time-minutes` 或 `--online-time-seconds` 一起使用。

-   `task_exclude_ids`: **(数组, 可选)**
    -   **说明**: 按任务 ID 排除不想自动接取的任务。例如 `["25"]`。

-   `task_exclude_names`: **(数组, 可选)**
    -   **说明**: 按完整任务名排除不想自动接取的任务。例如 `["每周发帖任务"]`。

-   `task_exclude_keywords`: **(数组, 可选)**
    -   **说明**: 按任务名或任务描述中的关键词排除任务。例如 `["发帖", "回帖"]`。

-   `cloudflare`: **(对象, 可选, 支持全局与账户局部两档)**
    -   **说明**: Cloudflare 人机验证自动解算配置。顶层全局块（与 `accounts` 同级）对所有账户生效；账户内同结构的 `cloudflare` 块为局部覆盖（**局部非空字段优先**，可只覆盖部分字段）。两处均未配置时回落环境变量 `GAMEMALE_CF_SOLVER` / `GAMEMALE_CF_API_KEY`。
    -   `solver`: **(字符串, 可选)** 解算服务，可选 `2captcha` / `capsolver` / `yescaptcha`。留空表示该层不启用、回落到更低优先级来源。
    -   `api_key`: **(字符串, 可选)** 上述打码平台的 API Key（GitHub Actions 用 Secret 注入环境变量）。
    -   `max_solves`: **(整数, 可选, 默认为 2)** 单次运行最多自动解算人机验证的次数（按次计费，默认 2 次足够）。

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

## 离线开发验证

```bash
pip install -r requirements-dev.txt
python -m mypy
python -m unittest discover -s tests
```

静态类型检查覆盖解析、配置、结果、报告与资产逻辑边界；既有会话 mixin 尚未全部纳入。PR 检查不加载论坛凭据，离线测试使用内联 HTML 和假会话。直接依赖版本已锁定；OCR 作为独立可选依赖。

日常流程遵循函数式优先与模块化：`task_plan.py` 根据不可变选项纯计算任务顺序，`workflow.py` 注入客户端和互动函数执行 IO，并通过不可变运行数据组合结果；`daily_tasks.py` 保留客户端兼容入口以及签到、抽奖请求动作。计划模块不依赖会话、日志或时间，编排模块不解析 HTML，也不为中间结果新增实例属性。新增功能应放入对应职责模块，通过返回值组合。

直接调用客户端的集成代码请使用新的结果接口：`execute_all_tasks()` 返回 `AccountRunResult`，通过 `.report` 读取报告、通过 `.succeeded` 判断账户结果；`quick_daily_sign()` 与 `quick_daily_lottery()` 返回 `TaskResult`，可读取 `.status` 和 `.message`。单项结果仍支持布尔判断，失败、未知、停止均为假。兑换提交结果不确定或提交后余额刷新失败时，不使用兑换前余额计算末尾差额或更新资产历史。
