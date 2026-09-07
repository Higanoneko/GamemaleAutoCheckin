# AGENTS.md — 项目开发范式

GameMale（gamemale.com）每日任务自动签到脚本：以 requests 会话模拟登录态，
执行签到、抽奖、任务接取/领奖、挂机刷新、日志互动、血液兑换，并把结果推送给
通知渠道。支持多账户、GitHub Actions 与青龙面板两种入口。

测试：`python -m unittest discover -s tests`（unittest，不依赖网络，HTML 样例内联）。

## 1. 开发范式：Functional Programming 优先

本仓库以 **函数式风格** 为第一开发原则，目标是代码可维护：逻辑可独立推演、
可离线测试、改动不牵连隐藏状态。

- **纯函数写逻辑**：解析、判定、过滤、统计、文本/报告构建等业务逻辑写成
  纯函数——同一输入必得同一输出，不读全局、不写实例状态、不发起副作用。
  现有范本：`modules/gamemale_core/parsers.py` 全部函数、`social.interact_with_blogs`。
- **副作用隔离在边界**：HTTP 请求、时间/随机、日志、配置与文件 IO 只出现在
  编排层或 IO 模块内；纯函数需要它们时通过参数注入（回调、session 等），
  而不是在函数体内直接调用。
- **数据流替代状态叠加**：新流程用"函数返回新值、上层组合"传递结果；
  不为中间结果给对象新增可变属性（`mission_results` / `online_time_summary`
  这类实例状态是既有编排产物的历史形态，新增代码不沿用）。
- **依赖注入优先**：需要访问会话/客户端能力的模块级函数，把依赖作为参数传入
  （如 `interact_with_blogs(client, account_name, ...)`），测试时用假对象替换。
- **每个函数补全类型标注**（`typing`），纯函数显式声明返回结构。
- 组合优于继承：不要为小功能新建 mixin；先写成纯函数，确认需要共享
  `GamemaleAutomation` 会话状态时才考虑挂到既有 mixin 上。

## 2. 结构地图

- `gamemale_daily.py` / `gamemale_daily_ql.py`：入口，只做配置加载、CLI 覆盖、
  通知回调组装，调用 `run_all_accounts`。
- `modules/gamemale_core/runner.py`：多账户编排；持有跨账户共享的
  `CloudflarePassPool`（放行 Cookie 复用池）。
- `modules/gamemale_core/client.py`：`GamemaleAutomation` —— 唯一允许长期持有
  会话状态（session / formhash / 登录态）的 IO 聚合器，由多个功能 mixin 组合：
  `login`（登录/formhash）、`missions`（任务接取/领奖）、`daily_tasks`
  （每日任务编排 execute_all_tasks）、`online`（挂机刷新）、`social`
  （日志互动/空间/打招呼）、`credits`（积分/兑换/统计）、`reports`（报告生成）。
- `modules/gamemale_core/cloudflare.py`：验证页识别、放行 Cookie 池、
  第三方打码平台（2captcha / capsolver / yescaptcha）解算与提交的纯请求函数。
- `modules/gamemale_core/http.py`、`config_utils.py`、`constants.py`、
  `logging_utils.py`、`stop_controller.py`：基础设施。

## 3. 硬性约定

- **所有业务 HTTP 请求走 `client._send_request`**：统一超时、重试与 Cloudflare
  验证页放行都在这一处，绕过它等于放弃 CF 处理。不要直接 `session.get/post`。
- **等待必须可中断**：循环内用 `client._sleep()` 或
  `controller.interruptible_sleep()`，并定期检查 `client._is_stopped()`；
  不要在任务循环里裸用 `time.sleep`（青龙停止信号依赖它生效）。
- **日志**用 `logging_utils` 的 `log_info / log_warning / log_success / log_error`
  （第二个参数传账户名）；模块内不用 `print`（入口脚本的 console 输出除外）。
- **配置读取**用别名兼容的 `_get_config_bool / _get_config_int / _get_config_list`，
  不直接对 `self.config` 做真值判断。新增配置键时同步四处：两个入口脚本的
  `CONFIG_TEMPLATE`、`config.example.json`、`ql_config.example.yaml`、README 参数表。
- **页面解析**（HTML / Discuz AJAX / URL / 验证码文本）统一写成 `parsers.py`
  中的纯函数，并配内联 HTML 的单元测试。
- **失败策略**：可预期的失败（超时、验证页、未配置）用返回值 / `None` /
  异常类型表达，由编排层决定是否兜底；异常用于真正的意外错误。
- **安全**：所有凭据来自配置文件或环境变量；代码、示例、文档只出现占位符；
  `config.yaml` / `config.json` / `GameMale_Config.yaml` 不应被提交。
- 改动 Cloudflare 放行策略时，必须保持"未配置解算通道时检测到验证页要明确
  报错、不得静默吞掉验证页"的既有行为，并跑通 `tests/test_cloudflare.py`。
