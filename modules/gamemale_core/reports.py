# -*- coding: utf-8 -*-
"""Report generation for account task runs."""

from typing import Dict, List, Optional


class ReportMixin:
    def generate_detailed_report(
        self,
        task_results: Dict[str, bool],
        user_credits: Optional[Dict[str, str]] = None,
        task_summary_data: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """生成详细的统计报告"""
        message = f"【{self.account_name}】 Gamemale 每日任务完成统计\n\n"

        if user_credits:
            message += "当前积分:\n"
            for name, value in user_credits.items():
                message += f"  - {name}: {value}\n"
            message += "\n"

        success_count = sum(1 for result in task_results.values() if result)
        total_count = len(task_results)
        message += f"任务执行概况: {success_count}/{total_count} 成功\n\n"

        message += "任务详情:\n"
        status_map = {True: "✅ 成功", False: "❌ 失败", None: "⏸️ 跳过"}
        sorted_tasks = sorted(task_results.items(), key=lambda item: item[0] == "血液兑换")
        for task_name, result in sorted_tasks:
            status = status_map.get(result, "❓ 未知")
            message += f"  - {task_name}: {status}\n"
        message += "\n"

        mission_summary = getattr(self, "mission_summary", {})
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
                    result for result in getattr(self, "mission_results", [])
                    if result.get("status") in {"accepted", "already_doing"}
                ]
                completed_missions = [
                    result for result in getattr(self, "mission_results", [])
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

        if task_summary_data:
            message += "任务总次数统计:\n"
            for task in task_summary_data:
                message += f"  - {task['name']}: {task['count']} 次\n"
            message += "\n"

        return message

