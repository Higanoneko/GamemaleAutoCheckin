# -*- coding: utf-8 -*-
"""Report generation for account task runs."""

from typing import Dict, List, Mapping, Optional, Sequence, Union

from .assets import asset_deltas, parse_asset_snapshot
from .progression import BLOOD_PER_POINT, UpgradeEstimate, UsergroupProgress, estimate_upgrade
from .results import TaskResult


def format_duration(seconds: int) -> str:
    """将秒数格式化为 HH:MM:SS。"""
    seconds = max(0, int(seconds))
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def build_upgrade_report(
    estimate: Optional[UpgradeEstimate], progress: Optional[UsergroupProgress] = None,
    blood: Optional[int] = None,
) -> str:
    """优先显示页面积分缺口，血液需求始终标为换算估算。"""
    lines = ['升级预估:']
    if progress is not None:
        if progress.current_group:
            lines.append(f'  - 当前用户组: {progress.current_group}')
        target = progress.target_group or '页面所示用户组'
        lines.append(f'  - 距 {target} 还需 {progress.points_needed} 积分（用户组页面）')
        blood_per_point = BLOOD_PER_POINT
        blood_needed = progress.points_needed * blood_per_point
        current_blood = blood if type(blood) is int and blood >= 0 else None
        blood_shortfall = max(0, blood_needed - current_blood) if current_blood is not None else None
        footer = f'  - 积分缺口来自用户组页面；血液按 1 积分 ≈ {blood_per_point} 血液估算，实际以论坛为准'
    elif estimate is None:
        return '\n'.join(lines + ['  - 未解析到有效积分，无法预估']) + '\n\n'
    else:
        lines.append('  - 用户组页面未取得有效升级缺口，以下按参考门槛估算')
        lines.append(f'  - 当前等级预估: Lvl. {estimate.current_level}')
        footer = f'  - 按参考门槛及 1 积分 ≈ {estimate.blood_per_point} 血液估算，实际以论坛为准'
        if estimate.next_threshold is None:
            return '\n'.join(lines + ['  - 已达到参考门槛表最高等级，无下一档预估', footer]) + '\n\n'
        lines.append(f'  - 距 Lvl. {estimate.current_level + 1} 还需 {estimate.points_needed} 积分'
                     f'（门槛 {estimate.next_threshold}）')
        blood_needed, current_blood, blood_shortfall = estimate.blood_needed, estimate.current_blood, estimate.blood_shortfall
    blood_line = f'  - 血液估算: 约需 {blood_needed} 滴血液'
    if current_blood is None:
        blood_line += '；当前血液未解析到'
    elif blood_shortfall:
        blood_line += f'；当前 {current_blood} 滴，尚差 {blood_shortfall} 滴'
    else:
        blood_line += f'；当前 {current_blood} 滴，按估算已足够'
    lines.extend([blood_line, footer])
    return '\n'.join(lines) + '\n\n'


def build_detailed_report(
    account_name: str,
    task_results: Union[Dict[str, bool], Sequence[TaskResult]],
    user_credits: Optional[Dict[str, str]] = None,
    task_summary_data: Optional[List[Dict[str, str]]] = None,
    mission_summary: Optional[Dict[str, object]] = None,
    mission_results: Optional[List[Dict[str, str]]] = None,
    online_time_summary: Optional[Dict[str, object]] = None,
    assets_before: Optional[Mapping[str, int]] = None,
    assets_after: Optional[Mapping[str, int]] = None,
    upgrade_progress: Optional[UsergroupProgress] = None,
) -> str:
    """生成详细的统计报告文本（纯函数）。"""
    message = f"【{account_name}】 Gamemale 每日任务完成统计\n\n"

    if user_credits:
        message += "当前积分:\n"
        for name, value in user_credits.items():
            message += f"  - {name}: {value}\n"
        message += "\n"
    if user_credits or upgrade_progress is not None:
        snapshot = parse_asset_snapshot(user_credits or {})
        message += build_upgrade_report(estimate_upgrade(snapshot.get('积分'), snapshot.get('血液')),
                                        upgrade_progress, snapshot.get('血液'))

    outcomes = [TaskResult(name, 'success' if result else 'failed') for name, result in task_results.items()] if isinstance(task_results, dict) else list(task_results)
    active = [result for result in outcomes if result.status != 'skipped']
    success_count = sum(result.status in ('success', 'already_done') for result in active)
    total_count = len(active)
    message += f"任务执行概况: {success_count}/{total_count} 成功\n\n"

    message += "任务详情:\n"
    status_map = {'success': '✅ 成功', 'already_done': '✅ 已完成', 'failed': '❌ 失败',
                  'skipped': '⏸️ 跳过', 'stopped': '⏹️ 已中断', 'unknown': '❓ 未确认'}
    for outcome in outcomes:
        detail = f"（{outcome.message}）" if outcome.message else ''
        message += f"  - {outcome.name}: {status_map[outcome.status]}{detail}\n"
    message += "\n"

    if assets_before is not None and assets_after is not None:
        deltas = asset_deltas(assets_before, assets_after)
        message += '本次资产变化:\n'
        message += ''.join(f'  - {name}: {value:+d}\n' for name, value in deltas.items()) if deltas else '  - 缺少两次有效采集，无法计算\n'
        message += '\n'

    if mission_summary:
        message += "新任务接取:\n"
        if mission_summary.get("disabled"):
            message += "  - 已禁用\n\n"
        else:
            message += (
                f"  - 检测: {mission_summary.get('detected', 0)} 个，"
                f"接取/进行: {mission_summary.get('accepted', 0)} 个，"
                f"跳过: {mission_summary.get('skipped', 0)} 个，"
                f"失败: {mission_summary.get('failed', 0)} 个\n"
            )
            if "doing_detected" in mission_summary:
                message += (
                    f"  - 进行中: {mission_summary.get('doing_detected', 0)} 个，"
                    f"已领取: {mission_summary.get('completed', 0)} 个，"
                    f"未完成: {mission_summary.get('not_ready', 0)} 个，"
                    f"领取失败: {mission_summary.get('complete_failed', 0)} 个\n"
                )
            accepted_missions = [
                result for result in (mission_results or [])
                if result.get("status") in {"accepted", "already_doing"}
            ]
            completed_missions = [
                result for result in (mission_results or [])
                if result.get("status") == "completed"
            ]
            if accepted_missions:
                message += "  - 本次接取/进行:\n"
                for result in accepted_missions:
                    status_text = "已在进行" if result.get("status") == "already_doing" else "已接取"
                    message += f"    - [{result.get('id', '')}] {result.get('name', '')}: {status_text}\n"
            if completed_missions:
                message += "  - 本次完成/领取:\n"
                for result in completed_missions:
                    message += f"    - [{result.get('id', '')}] {result.get('name', '')}: 已领取\n"
            message += "\n"

    if online_time_summary:
        message += "挂机时长:\n"
        status_text = {
            "disabled": "已禁用",
            "skipped": "未配置时长，已跳过",
            "pending": "待执行",
            "completed": "已完成",
            "stopped": "已中断",
            "failed": "失败",
        }.get(str(online_time_summary.get("status")), "未知")
        message += f"  - 状态: {status_text}\n"
        if online_time_summary.get("enabled"):
            message += (
                f"  - 计划时长: {format_duration(int(str(online_time_summary.get('duration_seconds', 0))))}，"
                f"刷新间隔: {format_duration(int(str(online_time_summary.get('interval_seconds', 0))))}，"
                f"刷新次数: {online_time_summary.get('refresh_count', 0)}\n"
            )
            if online_time_summary.get("error"):
                message += f"  - 错误: {online_time_summary.get('error')}\n"
        message += "\n"

    if task_summary_data:
        message += "任务总次数统计:\n"
        for task in task_summary_data:
            message += f"  - {task['name']}: {task['count']} 次\n"
        message += "\n"

    return message


class ReportMixin:
    account_name: str
    def generate_detailed_report(
        self,
        task_results: Dict[str, bool],
        user_credits: Optional[Dict[str, str]] = None,
        task_summary_data: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """生成详细的统计报告（读取本实例数据后交给纯函数构建文本）。"""
        return build_detailed_report(
            account_name=self.account_name,
            task_results=task_results,
            user_credits=user_credits,
            task_summary_data=task_summary_data,
            mission_summary=getattr(self, "mission_summary", None),
            mission_results=getattr(self, "mission_results", None),
            online_time_summary=getattr(self, "online_time_summary", None),
        )


def build_asset_history_report(
    previous: Mapping[str, int], current: Mapping[str, int], sampled_at: Mapping[str, str],
) -> str:
    """差额按字段计算；上次采集时间在末行归纳，保留不同时间的归属。"""
    deltas = asset_deltas(previous, current)
    lines = ['较上次有效采集的资产变化:']
    time_groups: Dict[str, List[str]] = {}
    for name, value in current.items():
        if name in deltas:
            lines.append(f'  - {name}: {deltas[name]:+d}')
            recorded_time = sampled_at.get(name)
            timestamp = recorded_time.strip() if isinstance(recorded_time, str) and recorded_time.strip() else '未知时间'
            time_groups.setdefault(timestamp, []).append(name)
        else:
            lines.append(f'  - {name}: {value}（首次记录）')
    if not time_groups:
        time_summary = '无（首次记录）'
    elif len(time_groups) == 1:
        time_summary = next(iter(time_groups))
    else:
        time_summary = '；'.join(f'{timestamp}（{"、".join(names)}）' for timestamp, names in time_groups.items())
    lines.append(f'上次记录时间: {time_summary}')
    return '\n'.join(lines) + '\n'
