# Reference 与当前项目对比：改进建议

对比日期：2026-10-06。当前项目版本 `10d0997`，Reference/GM-All-In-One 版本 `b316d82`。依据本地源码、工作流和离线模拟，不依据 README 中未经验证的站点行为或性能宣传。Reference 在当前仓库中被忽略，复查其代码需要保留本地 Reference 文件夹。

本次仅新增研究文档，没有修改业务代码、实际访问论坛、签到、兑换或发送通知。既有 `.gitignore` 改动保留。

## 总体判断

当前项目的模块拆分、纯解析函数、配置别名兼容、多账户编排、可中断等待和跨账户 Cloudflare 放行池值得保留。Reference 主要提供了更细的运行状态、资产变化展示、诊断流程和可选网络适配方案；不适合整体替换当前实现。

当前基础：[客户端组合](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/client.py:40)、[多账户运行器](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/runner.py:15)、[解析模块](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/parsers.py:14)、[停止控制器](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/stop_controller.py:7)。

建议先修正“是否登录、是否成功、失败能否被发现”，再扩展报告和部署体验。

## 优先修正的可靠性问题

### 1. Cloudflare 检测应发生在 HTTP 错误处理之前

**当前问题：** `_send_request` 先执行 `raise_for_status()`，然后才识别验证页。带挑战正文的 403 会直接抛错，无法进入共享放行池或解算流程。503 还需要一并考虑 HTTPAdapter 的状态码重试：响应可能在适配器内被耗尽重试，不能只交换两行代码。

**Reference 借鉴：** `GatedSession._request` 获取响应后先检查正文是否为验证页。不过它最终可能返回未放行页面，且没有完整保留当前项目的普通 HTTP 状态校验，因此也不能直接照搬。

**建议：** 在统一请求边界识别挑战、执行有预算的放行与重放，再处理普通 HTTP 错误；协调适配器重试策略。保留未配置解算通道时明确报错的既有行为。验证失败/预算耗尽可用明确状态或异常交给编排层，避免验证页被解释为正常的空任务列表。

**验证要求：** 200/403/503 挑战、普通 403、未配置解算、预算耗尽、停止信号、共享池失效；必须跑 `tests/test_cloudflare.py`。

依据：[当前请求顺序](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/client.py:149)、[适配器重试](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/http.py:26)、[Reference 请求边界](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gm_gate.py:1541)。离线构造真实 `requests.Response(status_code=403)`：正文被挑战识别函数判为 `True`，放行处理调用次数为 **0**。

### 2. 用结构化结果判断账户成功，并把失败账户纳入通知

**当前问题：** `execute_all_tasks()` 返回报告字符串；运行器只要发现字符串非空，就累计成功账户。签到或抽奖返回 `False` 仍然可能让 Actions 以成功退出。配置无效、登录失败及账户异常只写日志，没有加入通知报告；所有账户登录失败时完全不调用通知。

**Reference 借鉴：** `run()` 有布尔返回结果，并在 `finally` 中尝试通知，资产解析失败也影响结果。但 Reference 的签到/互动失败没有全部纳入该布尔结果，通知失败也没有影响返回值，不能认为它已完整解决成功判定。

**建议：** 函数返回 `TaskResult` / `AccountRunResult`，明确 `success`、`already_done`、`skipped`、`failed`、`stopped`、`unknown`，通过纯函数汇总。先定义哪些任务必须成功，避免把主动禁用、未配置兑换或已有完成状态当失败。报告文本由结构化数据生成；账户失败也生成简短报告，并尊重 `notify_enabled`。退出码根据任务结果决定。

**验证要求：** 必需任务失败导致失败计数；跳过不算失败；登录失败仍收到失败摘要；全部失败仍通知；停止后不能宣称全部完成。

依据：[当前账户判定与通知](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/runner.py:87)、[当前任务结果](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/daily_tasks.py:24)、[Reference 运行结果](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gamemale.py:1135)。离线假客户端返回包含失败信息的非空报告：运行器返回失败数 **0**；假客户端登录失败：失败数 **1**，通知调用次数 **0**。

### 3. 互动结束后再检查一次任务领奖

**当前问题：** 任务顺序是签到 → 抽奖 → 接任务 → 领奖 → 挂机 → 日志互动 → 空间访问 → 打招呼。只有挂机完成且刷新次数大于 0 才额外领奖，而这次检查仍在社交互动之前。依赖本次社交互动完成的任务可能只能等下一次运行领取。

**建议：** 接任务后执行达成条件的动作，在动作完成后统一检查领奖。必要时保留一次前置领奖，用于领取历史已完成任务；不要为每个动作无条件重复请求任务页。由流程函数组合结果，避免继续叠加实例中间状态。

**验证要求：** 假客户端记录调用顺序；互动后才变为可领取的任务能够在本次运行领奖；停止后不追加领奖请求。

依据：[任务编排](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/daily_tasks.py:43)。离线调用顺序与上述源码一致。此项是当前项目的独立改进，Reference 没有对应的通用任务接取/领奖流程。

### 4. 收紧登录态判定，同时改善 Cookie 输入兼容

**当前问题：** 个人资料页出现 `uid=` 或“个人空间”就可能被判定为已登录。这些内容也可能是游客页面上的公开链接。Cookie 解析只按分号切分，粘贴 `Cookie:` 前缀、JSON 导出或外层引号时没有归一化处理。

**Reference 借鉴：** 提取页面中的 `discuz_uid`，结合大于 0 的账户标记判断；`parse_cookie_header` 兼容前缀、换行、JSON、引号，仍按第一个等号切分值。

**建议：** 在 `parsers.py` 实现纯函数解析登录标记和 Cookie 输入。明确游客、已登录和无法判断三种状态；校验字段应先用真实页面样本确认，不能仅依赖单一正则。不要通过 Cookie 内容本身推断一定有效。

**验证要求：** 游客页带公开 UID 链接、`discuz_uid=0`、正 UID、无 UID、正常登录页；Cookie 前缀、带等号值、多行、JSON 和非法输入。

依据：[当前登录判定](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/parsers.py:157)、[当前 Cookie 导入](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/login.py:71)、[Reference UID 解析](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gm_gate.py:278)、[Reference Cookie 解析](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gm_gate.py:222)。离线游客 HTML 含 `discuz_uid=0` 和公开 `uid=123` 链接，当前判定为 **True**。

### 5. 统一两个入口的配置归一化

**当前问题：** Actions 工作流注入 `GAMEMALE_ACCOUNTS` 和 `GAMEMALE_COOKIE`，却运行不读取这两个变量的标准入口。青龙入口从 `APP_CONFIG_JSON` 只读取旧 `gamemale` 结构，没有读取 `accounts`；其全局 Cloudflare 设置只从 YAML 加载，环境 JSON 顶层的 `cloudflare` 不会一起传给运行器。两处运行参数覆盖函数也重复并直接修改传入账户字典。

**Reference 借鉴：** 同一处环境变量读取助手兼容新旧变量名，工作流包含配置预检。当前项目需要进一步适配多账户与已有来源优先级。

**建议：** 文件和环境读取留在 IO 层，共享纯函数负责结构校验、旧结构迁移、别名归一化和返回新账户配置。让账户列表与全局 Cloudflare 设置来自同一份已加载配置，并明确两个入口的来源优先级。遇到空 YAML、非法根类型、错误账户类型时给出具体错误。

**验证要求：** 各配置来源、两个 JSON 结构、全局/局部 CF 优先级、空 YAML、非法类型、参数覆盖不改变原始输入。

依据：[标准入口加载](D:/Projects/Code/GameMale/GamemaleAutoCheckin/gamemale_daily.py:87)、[青龙加载](D:/Projects/Code/GameMale/GamemaleAutoCheckin/gamemale_daily_ql.py:100)、[青龙 CF 加载](D:/Projects/Code/GameMale/GamemaleAutoCheckin/gamemale_daily_ql.py:213)、[工作流注入](D:/Projects/Code/GameMale/GamemaleAutoCheckin/.github/workflows/daily_checkin.yml:47)、[Reference 环境读取](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gamemale.py:184)。以上由源码确认。

## 值得借鉴的功能与体验

### 6. 互动报告区分新增、已完成、失败和目标缺口

Reference 日志互动分别记录新增表态与服务端返回的“已表过态”，报告展示两者。当前只识别新增成功，且用成功 UID 的集合计数：同一作者不同日志只计一个 UID；编排层只要新增成功数量大于 0 就把互动标为成功，无法表达 1/10 与 10/10 的区别。

建议返回明确的互动统计：新增次数、已完成次数、失败次数、扫描数，以及用于后续空间访问的稳定顺序 UID 列表。日志动作计数与独立用户去重分开。若服务端没有明确确认当日完成，不应把“已表态”自动解释为“今日额度已满”；每日目标口径仍需实际页面/规则验证。

依据：[当前集合计数](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/social.py:61)、[当前成功判定](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/daily_tasks.py:68)、[Reference 分项计数](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gamemale.py:784)。

### 7. 资产变化报告，并明确“无法解析”不等于 0

Reference 保存前次金币、血液、积分快照，包含日期与账户归属，解析金币失败时不更新基准。当前只展示运行末尾余额；缺失血液字段被默认成 `0 滴`，无法区分真实余额为 0 与页面解析失败。此外，解析器允许 `1,234`，数值转换却直接调用 `int`，千位分隔符会触发 `ValueError`。

建议先做本次运行前后差额，再按需要增加跨运行快照。二者分别标为“本次变化”和“较上次记录”，均不能直接称作“今天任务收益”，因为可能包含其他操作。纯函数计算差额、检查归属和有效性；IO 层按账户保存快照，数据缺失不覆盖旧值，写入采用原子替换。跨运行存储需明确本地、青龙与 Actions 的持久化方式，不默认沿用 Reference 的提交资产文件到 Git 的方式。

依据：[当前积分与兑换](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/credits.py:23)、[当前积分解析](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/parsers.py:284)、[当前数值转换](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/parsers.py:304)、[Reference 资产快照](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gamemale.py:951)。离线输入 `1,234 drops`，当前转换抛出 **ValueError**。

### 8. 增加只读检查模式和配置诊断

Reference 提供 `full/light/check`：后两者跳过签到、抽奖、互动，只抓资产；其工作流支持手动选择模式和 Cookie 预检。当前只有全量与 `only_online`。

建议增加 `--check` / `--status-only`，用于验证配置、登录态、formhash 和资产解析，不发起签到、兑换或社交写操作。明确“离线配置检查”和“在线登录检查”的区别：在线检查仍有 HTTP 副作用，密码登录/CF 解算还可能消耗资源。诊断日志可显示来源、字段是否配置、Cookie 长度或短指纹，不能输出凭据原文。

依据：[当前 CLI](D:/Projects/Code/GameMale/GamemaleAutoCheckin/gamemale_daily.py:120)、[Reference 模式分支](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gamemale.py:1151)、[Reference 手动模式与预检](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/.github/workflows/signin.yml:11)、[Cookie 指纹](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gm_gate.py:209)。

### 9. 通知应返回送达结果，补充传输配置

当前 Telegram/企业微信 POST 不检查 HTTP 状态及响应中的业务成功标记；Telegram 对普通报告文本设置 `parse_mode=HTML`，动态文本没有 HTML 转义。SMTP 固定走 STARTTLS 且没有超时；配置缺失可能静默不发送。Reference 有带 30 秒超时的 SMTP_SSL 和布尔送达结果，但也没有把送达失败纳入最终运行状态。

建议通知边界返回成功/失败/跳过状态，分别处理任务执行失败与推送失败。支持 SSL/STARTTLS 与超时；如果只发普通文本，Telegram 直接取消 HTML 解析。检查渠道响应，给出缺失配置原因；长报告按渠道限制拆分，具体限制实现前核实官方文档。HTML 邮件可以作为后续独立渲染函数，当前纯文本报告应继续可用。

依据：[当前通知实现](D:/Projects/Code/GameMale/GamemaleAutoCheckin/gamemale_daily.py:204)、[青龙通知](D:/Projects/Code/GameMale/GamemaleAutoCheckin/gamemale_daily_ql.py:260)、[Reference SMTP 实现](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gamemale.py:1102)。

## 工程改进与采纳边界

### 10. 区分读取请求与产生副作用的动作，再决定是否重试

当前适配器对 GET/POST 都配置了状态码重试；而本项目签到、抽奖、接任务、领奖、表态等动作有不少是 GET。只按 HTTP 方法决定重试安全性不够。兑换提交成功但响应异常时，自动重放存在重复操作风险；是否真的会重复取决于服务端幂等保障，本次未在线验证。适配器退避也没有接入当前停止控制器。

建议在 `_send_request` 的边界表达请求意图：可安全读取、明确拒绝后可重放、结果未知需查询确认。读取失败可用可中断退避；动作提交结果未知时先核实状态。继续保留统一 CF 处理，避免各业务模块自建请求通道。账户结束时在 `finally` 中关闭 Session。

依据：[当前重试配置](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/http.py:26)、[GET 动作](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/daily_tasks.py:115)、[兑换 POST](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/credits.py:65)、[账户生命周期](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/runner.py:80)。此项是风险改进建议，不是已证实发生重复兑换。

### 11. 将离线测试放入 PR 检查，并固定可复现依赖

当前已经有 90 个离线测试，但唯一工作流主要执行真实日常任务，没有 PR 离线测试步骤；`requirements.txt` 没有限制依赖版本。Reference 锁定依赖组合，工作流做依赖导入检查，但本地参考目录没有测试套件，不值得替代当前测试基础。

建议新增独立 PR 测试工作流，不加载论坛凭据，执行 `python -m unittest discover -s tests`。先补前述结果汇总、流程顺序、入口归一化和非 200 挑战测试，再加入经验证的依赖约束；不要直接复制 Reference 的包版本。Cookie 模式可考虑把 OCR 作为可选依赖，降低无需密码登录的安装成本。README 的“提升 70%+”缺少本次可见的基准证据，应给出测量依据或删除，并更新架构描述以符合 AGENTS.md 的函数式优先原则。

依据：[现有工作流](D:/Projects/Code/GameMale/GamemaleAutoCheckin/.github/workflows/daily_checkin.yml:25)、[当前依赖](D:/Projects/Code/GameMale/GamemaleAutoCheckin/requirements.txt:1)、[Reference 依赖约束](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/requirements.txt:1)、[README 说明](D:/Projects/Code/GameMale/GamemaleAutoCheckin/README.md:7)。

### 12. 密码登录按实际表单决定验证码流程

当前密码登录在读取表单前就要求 OCR 可用，随后要求验证码哈希和识别值必须存在；验证码更新没有传入表单中的动态 `modid`，图片响应直接送入 OCR。Reference 解析 `seccodemodid`，校验图片类型，并在登录提交前调用验证码检查接口；也支持无验证码表单。

建议解析函数返回明确的 `captcha_required` 与验证码参数，有验证码才初始化 OCR；图片类型和识别结果先校验，再提交登录。验证码刷新与密码登录尝试各自限额，并继续使用 `_send_request` 和可中断等待。预校验增加请求次数，是否默认启用需看真实表单兼容性和识别失败情况。

依据：[当前 OCR 前置条件](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/login.py:84)、[当前验证码获取](D:/Projects/Code/GameMale/GamemaleAutoCheckin/modules/gamemale_core/login.py:150)、[Reference 动态 modid](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gamemale.py:519)、[Reference 图片与验证码检查](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gamemale.py:581)、[Reference 无验证码路径](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gamemale.py:635)。这是可兼容性改进，未证明当前线上登录一定因此失败。

### 暂不建议直接引入

- **爬虫 User-Agent 绕验证。** Reference 的实现确实使用该策略，但 README 的“始终零验证”不能由本地源码证明，未验证现站效果。它还包含某些路径的限制，不能作为当前密码登录和兑换的通用替代。
- **整套浏览器兜底与 curl_cffi。** Reference 支持可选传输和浏览器流程，可作为现有请求方案确实失败后的实验；会增加依赖、运行环境和调试成本。若引入，需统一在 `_send_request` 下适配，而不是新增绕过边界的业务请求。
- **你画我猜自动发布。** Reference 采用固定标题、答案和占位图片发帖。当前用户需求是每日任务可靠执行，自动发布内容会扩大副作用，应作为单独明确启用的功能讨论。
- **把资产、Cookie 或保活提交整体照搬到 Git。** 先决定存储和运行平台要求；保持配置文件忽略，避免把运行态误当源码。Reference 的资产归属短哈希仅作对账，不应承诺隐藏低熵 UID/用户名。

依据：[可选传输](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gm_gate.py:319)、[用户 Cookie UA 路径](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gm_gate.py:1235)、[自动发布内容](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/gamemale.py:853)、[资产提交](D:/Projects/Code/GameMale/GamemaleAutoCheckin/Reference/GM-All-In-One/.github/workflows/signin.yml:153)。

## 推荐实施顺序与验收

1. **正确性：** CF 响应顺序、登录态判定、结构化结果与失败通知、互动后领奖、配置归一化；补相应离线回归测试。
2. **可观测性：** 互动分项结果、通知送达状态、只读诊断、资产解析有效性与本次差额。
3. **工程与可选体验：** PR 测试工作流、依赖约束、跨运行资产快照、HTML 邮件。仅有实际失败证据时评估额外网络适配。

所有新增逻辑沿用项目规则：解析和汇总使用带类型标注的纯函数；HTTP、时间、随机、日志、文件写入在边界注入；不新增用于中间结果的可变实例属性。新增配置同步两个入口模板、JSON/YAML 示例与 README 参数表。

验证基线：`python -m unittest discover -s tests`，**90 tests，OK**。另以 Mock/假客户端/内联 HTML 进行了上述诊断，全部无网络、无真实配置加载；诊断不是已提交的回归测试。现站页面结构、服务器幂等保障、不同 UA 放行效果和实际邮件送达均未验证。

进一步的源码依据与参考项目自身缺陷见 [后台研究笔记](D:/Projects/Code/GameMale/GamemaleAutoCheckin/docs/reference-research-notes.md)。
