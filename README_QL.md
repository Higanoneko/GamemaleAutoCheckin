# GameMale 每日任务 · 青龙面板

青龙入口为 `gamemale_daily_ql.py`，支持多账户、Cookie / 密码登录、每日任务、可选挂机和青龙通知。完整部署说明见 [README：青龙面板部署](README.md#青龙面板部署)，配置字段见 [ql_config.example.yaml](ql_config.example.yaml)。

## 浏览器扩展配置（推荐）

本仓库提供独立的 [GameMale 青龙配置助手](extensions/gamemale-qinglong/README.md)，为本项目生成 **`GameMale_Config.yaml`**，支持手动复制和 API 自动写入两种方式。

1. 在 Chrome / Edge 扩展管理页面开启「开发者模式」，加载 `extensions/gamemale-qinglong` 文件夹。
2. 在同一浏览器登录 [GameMale](https://www.gamemale.com/)，完成验证，点击扩展图标打开助手。
3. 点击 **读取并复制完整 YAML**，将生成内容粘贴进青龙「配置文件」中的 **`GameMale_Config.yaml`**。文件尚不存在时先运行一次青龙脚本创建模板。
4. 已有多账户配置时点击 **读取并复制账户片段**，追加到现有 `accounts:` 下。新账户默认关闭血液兑换，需要兑换时填写论坛密码并启用开关。

## 青龙 API 自动构建配置

**先去 青龙面板 → 设置 → 系统设置 → 应用设置 创建 API Key（添加应用），至少包含「配置文件」权限。**

将获取到的 **Client ID** 和 **Client Secret** 连同面板地址填写到助手，用于自动构建配置文件：

1. 点击 **连接并读取现有配置**，允许浏览器访问该面板。
2. 选择新增账户或更新某个已有账户，点击 **生成合并预览**。
3. 检查完整 YAML，点击 **将预览写入青龙**。文件不存在时自动创建；已有文件会保留其他账户、Cloudflare 配置及未展示的账户设置。保存会重新排版 YAML，注释不保留，请先备份。
4. 保存后助手回读核对；若保存结果未确认，请先在青龙检查文件，再重新读取配置。

扩展不需要定时任务、环境变量等额外 API 权限；凭据只存在当前页面内存中，关闭或刷新即清空。Client ID / Client Secret 不会写入签到配置。安装、连接限制和接口兼容说明见 [扩展 README](extensions/gamemale-qinglong/README.md)。

## 配置路径与自检

青龙入口优先在 `/ql/data/config`、`/ql/config` 中寻找 **`GameMale_Config.yaml`**，目录不存在时回落到脚本旁。配置源优先级为：YAML → `APP_CONFIG_JSON` → `GAMEMALE_ACCOUNTS` → `GAMEMALE_COOKIE` → 脚本旁 `config.json`。已有 YAML 会优先于环境变量，请更新实际使用的文件。

自检命令（保留面板生成的真实订阅路径）：

```bash
task Higanoneko_GamemaleAutoCheckin/gamemale_daily_ql.py -- --check-config
task Higanoneko_GamemaleAutoCheckin/gamemale_daily_ql.py -- --check
```

`--check-config` 完全离线；`--check` 在线验证登录和资产读取，不执行签到或兑换，也不发送通知，遇到验证页可能消耗 Cloudflare 解算额度。通过后恢复正常命令并启用定时任务：

```bash
task Higanoneko_GamemaleAutoCheckin/gamemale_daily_ql.py
```

挂机需按本次运行启用，如追加 `-- --enable-online --online-time-minutes 30`。通知使用青龙自带的 `notify.send` / `sendNotify.send`，保持账户 `notify_enabled: true`，在面板系统设置中配置通知渠道。

浏览器 Cookie 中的 Cloudflare 放行凭据不保证在青龙服务器可用；遇到验证页时继续按 [README 的 Cloudflare 配置](README.md#常用配置) 设置解算通道。未配置解算通道时仍会明确报错。
