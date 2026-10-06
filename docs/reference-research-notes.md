# Reference 源码对比研究笔记

研究日期：2026-10-06。范围：本地 `Reference/GM-All-In-One` 与当前项目源码。研究过程中未访问 GameMale、未执行签到或其它账户操作、未读取实际凭据文件。以下结论描述本地代码行为，不把参考项目注释中的“实测”“最稳”等说法视为当前线上保证。

## 总体判断

Reference 真正提供的增量主要是 Cookie 输入容错和诊断、明确的登录 UID 验证、验证码预校验、资产跨运行差额，以及只查询资产的运行模式。当前项目已经有参考项目没有的多账户编排、任务接取/领奖、可中断挂机、三种解算平台和多渠道通知，不能用 Reference 主类整体替换。

证据：Reference 主流程只调用签到、抽奖、互动与资产查询 [gamemale.py:1135](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gamemale.py:1135)；当前任务流程额外接取/领奖与挂机 [daily_tasks.py:40](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/daily_tasks.py:40)，多账户入口 [runner.py:15](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/runner.py:15)，解算平台 [cloudflare.py:30](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/cloudflare.py:30)。

## 优先借鉴：认证及诊断

### 1. 登录判定使用当前账户的明确 UID

当前 `_is_profile_page_logged_in` 只要正文含“我的资料”“个人空间”或 `uid=` 就判登录成功；这些文本也可能出现在游客页面的链接和导航里 [parsers.py:157](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/parsers.py:157)。Reference 从 `discuz_uid` 提取数字，在 Cookie 检查中要求非零值，并对空间管理页/论坛首页做交叉验证 [gm_gate.py:278](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gm_gate.py:278)、[gm_gate.py:1290](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gm_gate.py:1290)。

适配建议：在 `parsers.py` 增加返回 `Optional[int]` 的纯函数，优先验证 `discuz_uid > 0`；明确区分游客 `0`、页面无身份标记、请求失败、验证页与已登录。只有明确游客状态才应判 Cookie 过期。Reference 本身把两个探测均异常或缺少 UID 的情形最终归为 `expired`，该误判需要改进，不能直接复制 [gm_gate.py:1293](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gm_gate.py:1293)、[gm_gate.py:1324](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gm_gate.py:1324)。

### 2. Cookie 输入标准化与只验证模式

当前只按分号拆分字符串并注入 Cookie [login.py:71](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/login.py:71)。Reference 的纯解析函数支持 `Cookie:` 前缀、包裹引号、换行与 JSON 字典，且保留值中的 `=` [gm_gate.py:222](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gm_gate.py:222)；还提供长度/项数/短指纹诊断 [gm_gate.py:209](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gm_gate.py:209)、[gm_gate.py:1269](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gm_gate.py:1269) 和独立的 `--verify-cookie` 工具 [gm_gate.py:1620](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gm_gate.py:1620)。

适配建议：Cookie 文本解析放入 `parsers.py`，返回解析数据和可诊断的格式问题；常规日志输出项数/必要 Cookie 名称，不输出值。对缺失、格式损坏、游客、网络失败、验证页分别给出可操作提示。验证模式只校验会话并输出结构化状态；不要把参考工具展示部分 Cookie 文本的方式带入 CI。

边界：Reference 判断缺少 auth 的条件实际同时检查 `_auth` 和 `_saltkey`，仅有 saltkey 也不会触发警告，不能视为可靠的登录凭据验证 [gm_gate.py:1272](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gm_gate.py:1272)。

### 3. 登录验证码的兼容性和预校验

当前已解析动态 `seccodehash`、提取返回的图片 URL、清理 OCR 文本，无需重新移植 Reference 的相同逻辑 [parsers.py:30](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/parsers.py:30)、[login.py:165](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/login.py:165)。仍可借鉴 Reference 解析 `seccodemodid`、检查图片响应 Content-Type、OCR 后调用验证码 `action=check` 的流程 [gamemale.py:519](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gamemale.py:519)、[gamemale.py:581](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gamemale.py:581)、[gamemale.py:599](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gamemale.py:599)。这样错误验证码可在登录提交前识别，验证码刷新次数与登录重试次数可独立预算。

当前密码登录在请求登录页前要求 OCR 可用，而且参数要求验证码哈希及识别值都存在 [login.py:84](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/login.py:84)、[login.py:114](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/login.py:114)。Reference 在没有验证码时可以尝试不带验证码登录 [gamemale.py:635](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gamemale.py:635)。可以让解析结果显式携带 `captcha_required`，有验证码才初始化 OCR。所有获取/检查请求继续走 `_send_request`，等待继续可中断；参考项目裸 `time.sleep` 不应移植。

## 优先借鉴：任务结果与运行策略

### 4. 日志表态区分新增、重复与实际达到目标

当前只识别 `succeed`/“表态成功” [parsers.py:365](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/parsers.py:365)，且按成功 UID 去重统计 [social.py:61](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/social.py:61)、[social.py:116](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/social.py:116)；总流程只要一次成功就把日志任务标记成功 [daily_tasks.py:72](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/daily_tasks.py:72)。因此同一作者的多篇成功日志只算一次，“已表过态”无法表达，多次执行可能出现报告与完成程度不一致。

Reference 已分别计数新增和“已表过态”，按日志 URL 去重，并将这些数带入报告 [gamemale.py:794](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gamemale.py:794)、[gamemale.py:831](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gamemale.py:831)、[gamemale.py:886](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gamemale.py:886)。

适配建议：纯分类函数返回 `success/already/failed/unknown`；互动结果按 blog ID/URL 统计，作者 UID 仅用于后续访问空间及打招呼。以结构化结果表达 target、new、already、failed、stopped，报告保留这些差别。

边界：Reference 将“已表过态”直接解释为“今日完成”，但响应文字本身不证明该表态发生于今日，可能是以前已操作过的日志。不能仅凭这些字样计算今日完成 10 次；优先使用站点信用奖励日志/任务进度核对今日额度。Reference 随便提取第一个表态 URL，也不保证选择的是当前项目要求的“震惊”按钮 [gamemale.py:819](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gamemale.py:819)，当前的具体按钮选择器应保留 [parsers.py:349](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/parsers.py:349)。

### 5. 引入 check / report 模式

Reference 的 `light/check` 跳过签到、抽奖及互动，仅抓取资产；`--check` 还禁用邮件 [gamemale.py:1151](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gamemale.py:1151)、[gamemale.py:1221](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gamemale.py:1221)。当前主流程只有 `only_online` 特例 [daily_tasks.py:27](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/daily_tasks.py:27)，两入口现有 CLI 也主要是挂机覆盖参数 [gamemale_daily.py:122](D:/Projects/Code/GameMale/GamemaleAutoCheckin/gamemale_daily.py:122)、[gamemale_daily_ql.py:155](D:/Projects/Code/GameMale/GamemaleAutoCheckin/gamemale_daily_ql.py:155)。

适配建议：统一任务选择/执行计划纯函数，支持会话自检（验证登录、取 formhash、查询积分）、只生成报告、只签到、只领奖与原挂机模式；入口只解析并注入模式。查询模式不得调用 `get_user_credits_and_exchange` 的兑换副作用，需先拆开查询和兑换决定 [credits.py:23](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/credits.py:23)。

边界：Reference 的 check 模式仍可能密码登录、验证门解算与写入本地资产基准 [gamemale.py:1140](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gamemale.py:1140)、[gamemale.py:996](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gamemale.py:996)，所以其“自检”不是严格无副作用的 dry-run。

### 6. 故障也能得到报告和通知

Reference 在 `run()` 的 finally 中尝试通知，再关闭浏览器，登录失败或主流程异常也可收到通知 [gamemale.py:1164](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gamemale.py:1164)。当前 runner 的通知位于有报告的成功分支 [runner.py:78](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/runner.py:78)，可借鉴“无论成功/失败都先产生统一运行结果，再通知”的编排设计。

边界：Reference 邮件总状态只取 `logged_in and not fatal_error`，不汇总签到/互动的失败 [gamemale.py:1112](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gamemale.py:1112)；其 run 的成功值也只额外检查资产抓取 [gamemale.py:1157](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gamemale.py:1157)。此外 finally 中通知调用没有额外保护，通知构建异常可能阻止后面的浏览器关闭。应复用当前通知回调接口，新增结构化 `RunResult` / `TaskResult`，明确业务失败、取消及通知失败，不复制其状态判定。

## 中期能力：跨运行资产报告

Reference 实际对金币、血液、积分保存带日期和账户归属的基准，并报告相对上次的增减；未解析值用 `None`/问号，不强行记零 [gamemale.py:128](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gamemale.py:128)、[gamemale.py:904](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gamemale.py:904)、[gamemale.py:973](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gamemale.py:973)、[gamemale.py:1001](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gamemale.py:1001)。当前报告只展示当前积分 [reports.py:28](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/reports.py:28)。

适配建议：优先实现本次任务前后快照差值（可以校验签到奖励/兑换影响）；需要历史报告时再提供以经确认 UID 为 key 的存储回调。纯函数负责快照校验、差值和报告，IO 边界负责原子保存。区分“上次成功采集差额”和“当日增长”，不能把不同跨度视为同一种指标；查询失败不覆盖有效基准。

Reference 的适配缺口：

- 单个 JSON 文件面向单账户，当前多账户不能共用同一个记录对象；其归属匹配在身份缺失时放行 [gamemale.py:267](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gamemale.py:267)，并不能保证身份隔离。
- 新基准只写本次解析到的字段，会丢弃暂时缺失的历史血液/积分 [gamemale.py:984](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gamemale.py:984)，不等于完整保存旧值。
- 文件直接覆盖，无原子写入 [gamemale.py:350](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gamemale.py:350)。
- 源码注释声称身份指纹“不能反推”，但它是公开固定盐下的短哈希；低熵 UID 仍可枚举，所以不可作为隐私保证 [gamemale.py:250](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gamemale.py:250)。
- workflow 自动提交资产到 Git 并推送 [signin.yml:153](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/.github/workflows/signin.yml:153)。是否公开这些资产历史应由用户选择，当前项目不宜默认引入。
- 固定等级门槛只是一份硬编码列表 [gamemale.py:138](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gamemale.py:138)，未对照当前站点配置，不应原样用于精确等级预测。

## 网络策略及不宜直接移植的功能

1. **挑战页先识别再处理 HTTP 错误。** 当前 `_send_request` 先 `raise_for_status`，之后才检查挑战 HTML [client.py:149](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/client.py:149)；Reference 包装器先检查正文 [gm_gate.py:1541](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gm_gate.py:1541)。因此当前 403 的插件验证页无法进入解算。应补 403/503 挑战、普通 403、重放后仍挑战的离线测试，保留未配置解算渠道时报错行为。Reference 达到重解次数上限仍返回挑战页 [gm_gate.py:1549](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gm_gate.py:1549)，这个失败传播方式不值得照搬。

2. **按操作语义决定重试。** 当前 HTTPAdapter 对 GET/POST 都重试 5xx [http.py:24](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/http.py:24)，而签到、抽奖、领奖也有 GET 写操作 [daily_tasks.py:116](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/daily_tasks.py:116)、[missions.py:250](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/missions.py:250)。Reference CF 包装器也会重放 GET/POST，因此参考项目并未解决重复副作用。建议区分查询与写入：只有明确未执行的挑战可解算后重放；响应不确定时先查状态再决定。

3. **TLS/浏览器作为可选能力。** Reference 的 HTTP 引擎确实优先用 curl_cffi 模拟 Chrome，失败才回退 requests [gm_gate.py:319](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gm_gate.py:319)；也确实实现浏览器启动、轮询、Cookie 导出 [gm_gate.py:1073](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gm_gate.py:1073)。但浏览器、xvfb、模型与固定版本显著增加青龙部署成本 [requirements.txt:13](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/requirements.txt:13)、[signin.yml:151](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/.github/workflows/signin.yml:151)。没有当前运行证据证明其稳定性更好，优先修复请求顺序/诊断，必要时再通过 session factory 注入可选后端。

4. **蜘蛛 UA 不是可靠的通用放行机制。** Reference 用户 Cookie 流程主动切换为蜘蛛 UA [gm_gate.py:1277](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gm_gate.py:1277)，源码也承认该模式无法获取验证码 [gamemale.py:465](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gamemale.py:465)。这依赖特定站点插件白名单，不能当成当前通用行为或默认策略；任何新路径都仍须经过 `_send_request`、验证实际会话与保留明确失败提示。

5. **“你画我猜”自动提交不列为优先改进。** Reference 的确提交固定标题/答案和一像素图片 [gamemale.py:853](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gamemale.py:853)，但这是产生公开内容的新业务行为，其奖励有效性无法从本地源码证明。用户尚未要求新增该功能，不应把它当作签到必需步骤。

## 建议的离线验证集合

优先测试：真实 requests.Response 的 403/503 挑战识别顺序；游客页面包含 `uid=` 链接但 `discuz_uid=0`；Cookie 前缀/引号/JSON/值内等号；无验证码表单和非图片返回；互动重复响应、同 UID 多 blog、扫描达到上限与停止；任务全部失败/部分失败/通知异常的总结果；查询模式不兑换、不签到、不写资产基准；跨账户快照隔离、损坏记录、缺字段和原子写入。

本次后台研究未新增或运行测试；父任务已运行现有离线测试，并独立验证关键问题。这里是源码依据及适配边界笔记，主任务报告应按已复现的问题确定最终优先级。
