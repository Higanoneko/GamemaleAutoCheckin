# GameMale 青龙配置助手

独立的 Chrome / Edge / Firefox 桌面版 Manifest V3 扩展，参考 `Reference/GM-All-In-One` 文档中 GM Cookie Helper 的“读取 Cookie → 配置向导”流程，为本仓库的青龙入口构建配置。这里使用独立实现，不包含 GitHub 部署流程。

## 安装

### Chrome / Edge

1. 下载并解压本仓库，保留 `extensions/gamemale-qinglong` 文件夹。
2. 在 Chrome 打开 `chrome://extensions`，或在 Edge 打开 `edge://extensions`。
3. 启用「开发者模式」，点击「加载已解压的扩展程序」，选择该文件夹（里面有 `manifest.json`）。
4. 点击扩展图标 → **打开配置助手**。配置页在独立标签页打开，便于填写与预览。

### Firefox 140+

使用单独生成的 **`gamemale-qinglong-firefox.zip`**，包含 Firefox 扩展 ID、最低版本及认证信息 / 网站内容的数据传输声明。扩展只向用户填写的青龙面板发送数据，详见 [数据说明](PRIVACY.md)。

当前提供未签名的测试包，可以按 Mozilla 的 [临时安装说明](https://extensionworkshop.com/documentation/develop/temporary-installation-in-firefox/) 使用：

1. 在 Firefox 地址栏打开 `about:debugging#/runtime/this-firefox`。
2. 点击 **临时载入附加组件**，选择 `gamemale-qinglong-firefox.zip`；也可以先解压，选择解压目录中的 `manifest.json`。
3. 从浏览器工具栏的扩展菜单打开 **GameMale 青龙配置助手**，在同一 Firefox 默认容器中登录论坛，再读取 Cookie。读取时如出现站点访问权限提示，请允许访问 GameMale。
4. 功能与 Chrome / Edge 相同：复制完整 YAML / 账户片段，或连接青龙 API 合并写入。

**临时扩展在 Firefox 重启后会移除。** 普通正式版 Firefox 的长期安装需要 Mozilla 签名；仅把 ZIP 改名为 XPI 不能完成签名。可以将这个包提交到 [AMO 开发者中心](https://addons.mozilla.org/developers/) 的自分发（unlisted）渠道，拿到签名后的 XPI，再在 `about:addons` 中通过「从文件安装附加组件」安装。见 [Mozilla 签名说明](https://extensionworkshop.com/documentation/publish/signing-and-distribution-overview/)。

Firefox 版的最低版本为 140，以使用 Mozilla 的 [内置数据传输同意机制](https://extensionworkshop.com/documentation/develop/firefox-builtin-data-consent/)。站点权限匹配不包含端口以兼容 Firefox，实际 API 请求仍使用输入的面板端口。当前不支持选择 Firefox 多账户容器或隐私窗口的 Cookie。

### 重新打包

在仓库根目录运行，无需安装 Python 第三方依赖：

```bash
python extensions/gamemale-qinglong/build.py
python extensions/gamemale-qinglong/build.py --browser firefox
```

默认在 `dist` 下生成 `gamemale-qinglong.zip`（Chrome / Edge）和 `gamemale-qinglong-firefox.zip`。两个包共享功能代码，只在 Firefox 包内生成专用 `manifest.json`；源码目录的清单仍用于 Chrome / Edge。打包采用明确的文件名单，不包含测试、打包脚本或本地账户配置。

## 复制配置（不需要 API Key）

1. 在同一浏览器登录 [GameMale](https://www.gamemale.com/)，按页面提示完成验证。
2. 点击 **读取并复制完整 YAML**，会读取包含 HttpOnly 的完整 Cookie 并复制符合当前脚本格式的配置。
3. 进入青龙「配置文件」，将内容粘贴进 **`GameMale_Config.yaml`** 并保存。若文件还不存在，先运行一次 `gamemale_daily_ql.py` 创建模板。
4. 若已有多账户配置，填写用户名、可选密码后，点击 **读取并复制账户片段**，把片段追加到已有 `accounts:` 列表下。也可先读取 Cookie、生成完整 YAML，再复制账户片段。避免用单账户完整配置覆盖其他账户。

新账户默认关闭血液兑换，启用通知、接取和领奖。需要兑换时填写论坛密码并勾选「自动兑换血液」。挂机时长默认 0，仍由脚本 CLI 按本次运行启用。安全问题与答案可选。

## API 自动构建并写入配置

1. **先去青龙面板 → 设置 → 系统设置 → 应用设置**，创建 API Key（添加应用），**至少包含「配置文件」权限**。
2. 将获取到的 **Client ID** 和 **Client Secret** 填入扩展，另填青龙面板地址，如 `https://ql.example.com` 或 `http://192.168.1.10:5700`。可包含反向代理路径前缀。
3. 点击 **连接并读取现有配置**，在浏览器提示中允许访问该面板。认证与配置文件读取都成功才视为连接成功；读取失败不会当成空文件覆盖。
4. 选择 **新增账户** 或明确选择某个现有账户。切换账户后检查用户名与开关。更新时用户名、密码、答案留空会保留原值；需要清空这些字段请在面板手动编辑。
5. 点击 **生成合并预览**，检查完整文件内容，再点击 **将预览写入青龙**。文件不存在时自动创建。其他账户、全局 Cloudflare、账户任务排除、挂机等未展示的设置保留。保存重新排版 YAML，**不保留注释**；建议先备份原文件。
6. 扩展在写入前重新检查原文件，在保存后回读核对。若文件已被其他操作修改，会要求重新读取。青龙接口没有原子比较写入能力，因此操作期间仍应避免其他人或签到任务同时修改配置。
7. 回面板运行配置自检与登录检查，再按主 [README](../../README.md#青龙面板部署) 配置签到时间和通知。

示例命令（保留面板生成的真实脚本路径）：

```bash
task Higanoneko_GamemaleAutoCheckin/gamemale_daily_ql.py -- --check-config
task Higanoneko_GamemaleAutoCheckin/gamemale_daily_ql.py -- --check
```

## 凭据与连接

- Cookie、论坛密码、API 凭据、令牌和配置预览只在当前页面内存中，刷新或关闭即清空；扩展不使用浏览器 storage。
- 配置预览及剪贴板含 Cookie / 密码；「清空」按钮清空页面，剪贴板可手动覆盖。青龙 Client ID / Client Secret 不写入签到配置文件。
- 请求直接从扩展发往填写的青龙面板，无中间服务，不运行远程脚本。面板地址的访问权限按需申请；`optional_host_permissions` 的 HTTP/HTTPS 通配符仅用于支持自建面板地址，不在安装时授予。
- 公网面板建议使用 HTTPS。HTTP 地址会通过明文传输凭据；证书或网络失败需在浏览器检查面板可达性。面板代理应直接提供接口，扩展不跟随重定向。
- 只检查非空 Discuz `auth` Cookie 标识，不能据此保证 Cookie 仍有效，也不能保证浏览器的 Cloudflare 放行 Cookie 在青龙服务器可用。论坛 Cloudflare 处理沿用本仓库既有配置。
- 401：核对 Client ID / Client Secret，重新连接；403：检查应用的「配置文件」权限。
- 写入超时或回读失败：到面板核对实际文件，再重新读取；不要直接重复写入。

## 离线验证

Node.js 22+，无需 npm 安装：

```bash
node --test extensions/gamemale-qinglong/tests/*.test.mjs
python -m unittest discover -s tests
```

配置生成/合并是纯函数，HTTP、浏览器 Cookie、权限与剪贴板位于边界。Node 测试使用假 fetch；Python 测试验证生成的配置可被实际加载器读取。

接口依据青龙官方 [认证路由](https://github.com/whyour/qinglong/blob/develop/back/api/open.ts)、[配置路由](https://github.com/whyour/qinglong/blob/develop/back/api/config.ts) 与 [v2.17.12 配置路由](https://github.com/whyour/qinglong/blob/v2.17.12/back/api/config.ts)：`GET /open/auth/token`、`GET /open/configs/files`、`GET /open/configs/detail?path=...`、`POST /open/configs/save`。读取 detail 返回 404/410 时兼容旧的 `/open/configs/{file}`，权限错误不会触发兜底覆盖。
