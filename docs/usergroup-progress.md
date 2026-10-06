# 用户组页面升级缺口

## 需求

用户提供 `https://www.gamemale.com/home.php?mod=spacecp&ac=usergroup`，要求利用页面中的“您升级到此用户组还需积分 XX”做精确估算。

- 当前积分后的升级预估优先采用页面实际积分缺口，显示可解析的当前/目标用户组；不再把参考门槛推算的等级混入页面结果。
- 血液需求和余额缺口仍按 Reference 的 `1 积分 ≈ 34 血液` 换算，明确标为估算，不增加兑换动作。
- 完整任务流程在领奖、兑换、末尾资产采集后只读查询一次；`status` / `check` 也只读查询，只有挂机的流程及已停止的流程不增加查询。
- 页面不可用、登录页、格式异常、积分下限或歧义不能当作零/满级。失败明确回退到既有参考估算，不跨运行缓存页面结果。Cloudflare 未放行明确记录错误。
- 保持青龙不查询“任务总次数统计”、资产历史时间末行归纳、依托青龙原生通知。
- 解析、报告为有类型标注的纯函数；结果为不可变数据。HTTP 通过注入的客户端 `_send_request`，不新增中间实例状态。

## 页面依据与验证边界

公开访问 GameMale 页面遇到 Cloudflare 验证，未用真实账户登录或执行任务。
离线内联 HTML 样例依据 Discuz 模板结构，站点自定义主题仍需实际运行确认。

[Discuz 用户组控制器源码](https://github.com/ra2diy/DiscuzX/blob/v3.5/upload/source/include/spacecp/spacecp_usergroup.php)在未指定 `gid` 时选择当前会员组的下一晋级组；[模板源码](https://github.com/ra2diy/DiscuzX/blob/v3.5/upload/template/default/home/spacecp_usergroup.htm)把目标组缺口放在 `.tscr .notice`，目标组标题放在 `#tba #c2`；[语言资源](https://github.com/ra2diy/DiscuzX/blob/v3.5/upload/source/language/home/lang_template.php)包含用户提供的提示语。

解析只接受唯一可见提示中的非负整数（可含合法千位逗号）；拒绝小数、科学计数、负数、非法逗号。缺少名称时显示“页面所示用户组”，不推断目标等级。

## 审查基线

本次实现从 `e661864fe2fbab2b212f6793baba435e9f299164` 开始，按本文需求与 AGENTS.md 分别做 Spec / Standards 审查。

## Standards

独立审查未发现违反 AGENTS.md 的新增代码或值得提出的代码异味。解析与报告保持纯函数，页面结果不可变，通过返回值传递；请求使用注入的 `_send_request`，日志、停止检查与 Cloudflare 明确报错符合约定。本轴 0 项发现。

## Spec

独立审查发现 1 项 P2：同一页面同时出现有效缺口与格式异常的缺口提示时，原实现只计数匹配成功的提示，错误采用有效值。现已改为先检查相关提示唯一，再验证数值。新增回归测试在修复前失败、修复后通过。本轴 1 项发现，已修复。

## 验证

- 151 项 unittest 全量通过（包括 Cloudflare 测试），测试时禁止 socket 网络连接。
- mypy 检查 10 个纯逻辑/编排源文件通过；`git diff --check` 通过。
- 公共页面仍有验证页限制；未执行真实账户登录、任务或兑换。实际主题兼容性由部署后的用户组页面响应确认。
