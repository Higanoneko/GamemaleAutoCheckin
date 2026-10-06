"""Pure daily task selection and ordering; no client or IO dependencies."""

from dataclasses import dataclass
from typing import Literal, Tuple


TaskKind = Literal['initial_assets', 'status', 'sign', 'lottery', 'accept',
                   'online', 'social', 'rewards', 'final_assets']


@dataclass(frozen=True)
class DailyTaskOptions:
    mode: str = 'full'
    only_online: bool = False
    accept_tasks: bool = True
    online_enabled: bool = False
    complete_tasks: bool = True


@dataclass(frozen=True)
class PlannedTask:
    kind: TaskKind
    name: str
    enabled: bool = True
    skip_reason: str = ''


def plan_daily_tasks(options: DailyTaskOptions) -> Tuple[PlannedTask, ...]:
    """输入配置决策，返回不可变计划；互动必须在领奖之前。"""
    if options.only_online:
        return (PlannedTask('online', '挂机时长'),)
    if options.mode in ('check', 'status'):
        return (PlannedTask('status', '资产查询'),)
    return (
        PlannedTask('initial_assets', '初始资产查询'),
        PlannedTask('sign', '签到'),
        PlannedTask('lottery', '抽奖'),
        PlannedTask('accept', '接取新任务', options.accept_tasks, '已禁用'),
        PlannedTask('online', '挂机时长', options.online_enabled, '未启用'),
        PlannedTask('social', '震惊互动'),
        PlannedTask('rewards', '完成任务', options.complete_tasks, '已禁用'),
        PlannedTask('final_assets', '资产查询'),
    )
