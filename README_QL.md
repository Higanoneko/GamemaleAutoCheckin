# Gamemale 每日任务 - 青龙面板版

## 功能特性

- 支持多账户运行
- 自动签到、抽奖、日志互动、空间访问、打招呼
- 自动检查并接取新任务，支持排除指定任务；已接取任务完成后自动领取奖励
- 可配置挂机总时长和刷新间隔，定时刷新论坛页面累计在线时间
- 自动血液兑换旅程
- 集成青龙面板通知系统
- 支持 Cookie 登录和密码登录
- **首次运行自动创建配置文件模板**

## 快速部署

### 1. 上传脚本

将 `gamemale_daily_ql.py` 上传到青龙面板的脚本目录，或通过订阅添加。

### 2. 安装依赖

在青龙面板 → **依赖管理** → **Python3** 中添加：

```
requests
beautifulsoup4
ddddocr
```

> `ddddocr` 仅在需要密码登录时必需，如果只使用 Cookie 登录可不安装。

### 3. 首次运行

在青龙面板 → **定时任务** 中添加任务并运行一次：

- **名称**：Gamemale每日任务
- **命令**：`task gamemale_daily_ql.py`
- **定时规则**：`0 8 * * *`

如需某次任务启用挂机刷新，可在命令后追加参数：

```
task gamemale_daily_ql.py --enable-online --online-time-minutes 30 --online-refresh-interval-seconds 900
```

如只想执行挂机刷新，不执行签到、抽奖等其它任务：

```
task gamemale_daily_ql.py --only-online --online-time-minutes 30
```

**首次运行会自动在配置目录创建 `gamemale.json` 模板文件！**

### 4. 填写配置

1. 打开青龙面板 → **配置文件**
2. 找到 `gamemale.json` 文件
3. 点击编辑，填写你的账户信息
4. 保存

### 5. 再次运行

保存配置后，手动运行一次任务验证配置是否正确。

---

## 配置文件说明

配置文件位置：青龙面板配置目录下的 `gamemale.json`

### 单账户配置

```json
{
    "accounts": [
        {
            "cookie": "你的完整Cookie",
            "username": "你的用户名",
            "password": "你的密码",
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
        }
    ]
}
```

### 多账户配置

```json
{
    "accounts": [
        {
            "cookie": "第一个账户的Cookie",
            "username": "用户名1",
            "password": "密码1"
        },
        {
            "cookie": "第二个账户的Cookie",
            "username": "用户名2",
            "password": "密码2"
        },
        {
            "cookie": "第三个账户的Cookie",
            "username": "用户名3",
            "password": "密码3"
        }
    ]
}
```

### 配置参数说明

| 参数 | 必需 | 说明 |
|------|------|------|
| `cookie` | 是* | 登录Cookie（优先使用，稳定） |
| `username` | 是* | 用户名（用于显示和密码登录） |
| `password` | 是* | 密码（用于Cookie失效时自动登录和血液兑换） |
| `questionid` | 否 | 安全问题ID，默认 `"0"` 表示无安全问题 |
| `answer` | 否 | 安全问题答案 |
| `auto_exchange_enabled` | 否 | 是否自动兑换血液为旅程，默认 `true` |
| `auto_accept_tasks` | 否 | 是否自动接取“新任务”页面中的可接任务，默认 `true` |
| `auto_complete_tasks` | 否 | 是否自动领取已完成的进行中任务奖励，默认 `true` |
| `online_time_minutes` | 否 | 挂机总时长候选值（分钟），默认运行会忽略，只有传入 `--enable-online` 或 `--only-online` 时读取 |
| `online_refresh_interval_seconds` | 否 | 刷新间隔（秒），默认 `900` |
| `task_exclude_ids` | 否 | 按任务 ID 排除，例如 `["25"]` |
| `task_exclude_names` | 否 | 按完整任务名排除，例如 `["每周发帖任务"]` |
| `task_exclude_keywords` | 否 | 按任务名或描述关键词排除，例如 `["发帖"]` |

> *注：`cookie` 或 `username + password` 至少提供一组

不传 `--enable-online` 或 `--only-online` 时，挂机默认不运行，并且会忽略配置文件里的挂机相关字段。推荐通过定时任务命令参数按本次运行启用：

```bash
task gamemale_daily_ql.py --enable-online --online-time-minutes 30
task gamemale_daily_ql.py --enable-online --online-time-seconds 1800 --online-refresh-interval-seconds 900
task gamemale_daily_ql.py --only-online --online-time-minutes 30
```

`--enable-online` 表示在正常任务流程中启用挂机；`--only-online` 表示只执行挂机。二者都不会自动设置挂机时长，通常需要与 `--online-time-minutes` 或 `--online-time-seconds` 一起使用。

---

## 获取 Cookie

1. 使用浏览器登录 [Gamemale论坛](https://www.gamemale.com)
2. 按 **F12** 打开开发者工具
3. 切换到 **Network**（网络）标签
4. 刷新页面，点击任意请求
5. 在 **Headers**（请求头）中找到 `Cookie` 字段
6. 复制完整的 Cookie 值

---

## 备选配置方式

如果不想使用配置文件，也可以通过环境变量配置：

### 环境变量 GAMEMALE_ACCOUNTS

在青龙面板 → **环境变量** 中添加：

- **名称**：`GAMEMALE_ACCOUNTS`
- **值**：
```json
[{"cookie":"xxx","username":"user1","password":"pass1"},{"cookie":"yyy","username":"user2","password":"pass2"}]
```

### 环境变量 GAMEMALE_COOKIE

简单格式，仅支持 Cookie 登录：

- **名称**：`GAMEMALE_COOKIE`
- **值**：`cookie1内容` 或多账户用换行分隔

---

## 通知配置

脚本会自动使用青龙面板的通知系统。请在青龙面板的系统设置中配置通知方式（如 Telegram、企业微信、钉钉等）。

---

## 执行日志示例

### 首次运行（无配置）

```
============================================================
Gamemale 每日任务自动化脚本 - 青龙面板版
============================================================

============================================================
首次运行 - 已自动创建配置文件!
============================================================

配置文件位置: /ql/data/config/gamemale.json

请按以下步骤操作:
  1. 打开青龙面板
  2. 点击左侧菜单「配置文件」
  3. 在文件列表中找到 gamemale.json
  4. 点击编辑，填写你的账户信息
  5. 保存后重新运行此任务
```

### 正常运行

```
============================================================
Gamemale 每日任务自动化脚本 - 青龙面板版
============================================================
从配置文件加载了 2 个账户: /ql/data/config/gamemale.json

共加载 2 个账户

############################################################
# 开始处理: user1 (1/2)
############################################################

==================== 登录流程 ====================
[user1] ✅ Cookie 登录成功
[user1] ✅ FormHash 获取成功

==================== 开始执行任务 ====================
[user1] 执行任务: 签到
[user1] ✅ 签到成功
[user1] 执行任务: 抽奖
[user1] 今日已抽奖
...
[user1] ✅ 任务完成: 5/5 成功

============================================================
执行汇总
============================================================
成功: 2 个账户
失败: 0 个账户
总计: 2 个账户
```

---

## 常见问题

### Q: 配置文件在哪里？
A: 首次运行脚本会自动创建。位置在青龙面板「配置文件」选项卡中，文件名为 `gamemale.json`。

### Q: Cookie 多久失效？
A: 一般 30 天左右，建议同时配置密码以便自动登录。

### Q: 验证码识别失败怎么办？
A: 密码登录会自动重试最多 8 次，如果仍然失败建议更新 Cookie。

### Q: 配置文件格式错误怎么办？
A: 检查 JSON 格式是否正确，特别注意：
- 字符串必须用双引号 `""`
- 最后一个元素后面不能有逗号
- 可以使用 `//` 添加注释

### Q: 如何禁用某个功能？
A: 设置 `"auto_exchange_enabled": false` 可禁用血液自动兑换。

---

## 更新日志

- **v2.1** - 支持配置文件方式，首次运行自动创建模板
- **v2.0** - 青龙面板适配，支持多账户
- **v1.0** - 初始版本，支持 GitHub Actions
