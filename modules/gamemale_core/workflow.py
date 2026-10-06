"""Daily workflow IO orchestration over a pure plan and immutable run data."""

import random
from dataclasses import dataclass, replace
from functools import partial
from typing import TYPE_CHECKING, Callable, Dict, List, Tuple, Union

from .assets import parse_asset_snapshot
from .constants import POKE_TARGET_COUNT
from .logging_utils import log_error, log_info
from .reports import build_detailed_report
from .results import AccountRunResult, TaskResult
from .social import BlogInteractionResult, blog_task_result
from .task_plan import DailyTaskOptions, PlannedTask, plan_daily_tasks

if TYPE_CHECKING:
    from .client import GamemaleAutomation


@dataclass(frozen=True)
class _WorkflowData:
    tasks: Tuple[TaskResult, ...] = ()
    credits: Tuple[Tuple[str, str], ...] = ()
    before: Tuple[Tuple[str, int], ...] = ()
    after: Tuple[Tuple[str, int], ...] = ()
    summary: Tuple[Tuple[Tuple[str, str], ...], ...] = ()


def _run_action(
    client: 'GamemaleAutomation', name: str,
    action: Callable[[], Union[bool, TaskResult]],
) -> TaskResult:
    """动作副作用集中执行，返回结果给上层组合，不修改中间实例状态。"""
    log_info(f'执行任务: {name}', client.account_name)
    try:
        value = action()
        result = value if isinstance(value, TaskResult) else TaskResult(name, 'success' if value else 'failed')
        if name == '挂机时长' and client.online_time_summary.get('status') in ('disabled', 'skipped'):
            result = TaskResult(name, 'skipped', '未启用或未配置有效时长')
        if client._is_stopped():
            result = TaskResult(name, 'stopped')
    except Exception as error:
        result = TaskResult(name, 'failed', type(error).__name__)
        log_error(f'{name}执行失败: {type(error).__name__}', client.account_name)
    if not client._is_stopped():
        client._sleep(random.uniform(1, 2))
    return result


def _run_social_tasks(
    client: 'GamemaleAutomation',
    interact: Callable[['GamemaleAutomation', str], BlogInteractionResult],
) -> Tuple[TaskResult, ...]:
    blogs = interact(client, client.account_name)
    outcomes: Tuple[TaskResult, ...] = (blog_task_result(blogs),)
    if client._is_stopped():
        return outcomes
    user_ids = list(blogs.processed_uids[:POKE_TARGET_COUNT])
    if not user_ids:
        return outcomes + (TaskResult('空间访问', 'skipped', '没有可用用户'),
                           TaskResult('打招呼', 'skipped', '没有可用用户'))
    for name, action in (
        ('空间访问', partial(client.quick_visit_spaces, user_ids)),
        ('打招呼', partial(client.quick_poke_users, user_ids)),
    ):
        if client._is_stopped():
            break
        outcomes += (_run_action(client, name, action),)
    return outcomes


def _read_assets(
    client: 'GamemaleAutomation', step: PlannedTask, data: _WorkflowData,
) -> _WorkflowData:
    if step.kind == 'final_assets':
        credits, exchanged = client.get_user_credits_and_exchange()
        after = tuple(parse_asset_snapshot(credits).items())
        exchange_task = TaskResult('血液兑换', 'skipped' if exchanged is None else 'success' if exchanged else 'failed')
        summary = tuple(tuple(row.items()) for row in client.get_daily_task_summary())
        return replace(data, credits=tuple(credits.items()), after=after, summary=summary,
                       tasks=data.tasks + (exchange_task, TaskResult('资产查询', 'success' if after else 'failed')))
    try:
        credits, _ = client._get_credits()
        snapshot = tuple(parse_asset_snapshot(credits).items())
    except Exception as error:
        initial = step.kind == 'initial_assets'
        return replace(data, tasks=data.tasks + (TaskResult(
            step.name, 'unknown' if initial else 'failed', type(error).__name__, required=not initial),))
    if step.kind == 'initial_assets':
        return replace(data, before=snapshot)
    return replace(data, credits=tuple(credits.items()), after=snapshot,
                   tasks=data.tasks + (TaskResult('登录自检', 'success'),
                                       TaskResult('资产查询', 'success' if snapshot else 'failed')))


def execute_daily_workflow(
    client: 'GamemaleAutomation',
    interact: Callable[['GamemaleAutomation', str], BlogInteractionResult],
) -> AccountRunResult:
    """注入客户端和互动实现；计划、结果和报告通过返回值连接。"""
    data = _WorkflowData()
    if not client.is_logged_in:
        data = replace(data, tasks=(TaskResult('登录', 'failed', '未登录'),))
    elif not client.formhash:
        data = replace(data, tasks=(TaskResult('formhash', 'failed', '未取得有效表单令牌'),))
    else:
        options = DailyTaskOptions(
            mode=client._get_config_str(['run_mode'], default='full'),
            only_online=client._get_config_bool(['only_online', 'only_online_time'], default=False),
            accept_tasks=client._get_config_bool(
                ['auto_accept_tasks', 'auto_accept_tasks_enabled', 'auto_task_accept_enabled'], default=True),
            online_enabled=client._get_config_bool(['online_runtime_enabled'], default=False),
            complete_tasks=client._get_config_bool(
                ['auto_complete_tasks', 'auto_complete_tasks_enabled', 'auto_draw_tasks'], default=True),
        )
        actions: Dict[str, Callable[[], Union[bool, TaskResult]]] = {
            'sign': client.quick_daily_sign,
            'lottery': client.quick_daily_lottery,
            'accept': client.quick_accept_new_tasks,
            'online': client.quick_accumulate_online_time,
            'rewards': client.quick_complete_doing_missions,
        }
        for step in plan_daily_tasks(options):
            if client._is_stopped():
                break
            if not step.enabled:
                data = replace(data, tasks=data.tasks + (TaskResult(step.name, 'skipped', step.skip_reason),))
            elif step.kind in ('initial_assets', 'status', 'final_assets'):
                data = _read_assets(client, step, data)
            elif step.kind == 'social':
                data = replace(data, tasks=data.tasks + _run_social_tasks(client, interact))
            else:
                outcome = _run_action(client, step.name, actions[step.kind])
                data = replace(data, tasks=data.tasks + (outcome,))

    stopped = client._is_stopped()
    if stopped and not any(task.status == 'stopped' for task in data.tasks):
        data = replace(data, tasks=data.tasks + (TaskResult('运行', 'stopped', '收到停止信号'),))
    summary: List[Dict[str, str]] = [dict(row) for row in data.summary]
    report = build_detailed_report(
        client.account_name, data.tasks, user_credits=dict(data.credits),
        task_summary_data=summary, mission_summary=client.mission_summary,
        mission_results=client.mission_results, online_time_summary=client.online_time_summary,
        assets_before=dict(data.before) if data.before or data.after else None,
        assets_after=dict(data.after) if data.before or data.after else None,
    )
    return AccountRunResult(client.account_name, data.tasks, report, stopped, data.before, data.after)
