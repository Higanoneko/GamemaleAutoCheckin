# -*- coding: utf-8 -*-
"""Daily task orchestration, sign-in, and lottery actions."""

import json
import random
import re
import time
from typing import Dict, Optional

from .constants import BASE_URL, POKE_TARGET_COUNT
from .logging_utils import log_error, log_info, log_section, log_success, log_warning
from .social import interact_with_blogs


class DailyTasksMixin:
    def execute_all_tasks(self) -> Optional[str]:
        """执行所有任务并生成详细报告"""
        if not self.is_logged_in:
            log_error("未登录，无法执行任务", self.account_name)
            return None

        if not self.formhash:
            log_warning("未能获取有效的 formhash，任务可能失败", self.account_name)

        log_section("开始执行任务", self.account_name)
        task_results: Dict[str, bool] = {}

        if self._get_config_bool(["only_online", "only_online_time"], default=False):
            log_info("仅执行任务: 挂机时长", self.account_name)
            task_results["挂机时长"] = self.quick_accumulate_online_time()
            report_message = self.generate_detailed_report(
                task_results,
                user_credits={},
                task_summary_data=[],
            )
            success_count = sum(1 for result in task_results.values() if result)
            total_count = len(task_results)
            log_success(f"任务完成: {success_count}/{total_count} 成功", self.account_name)
            return report_message

        # 基础任务
        tasks = [
            ("签到", self.quick_daily_sign),
            ("抽奖", self.quick_daily_lottery),
            ("接取新任务", self.quick_accept_new_tasks),
            ("完成任务", self.quick_complete_doing_missions),
            ("挂机时长", self.quick_accumulate_online_time),
        ]

        for name, func in tasks:
            if self._is_stopped():
                log_warning("收到停止信号，中断任务执行", self.account_name)
                break
            log_info(f"执行任务: {name}", self.account_name)
            task_results[name] = func()
            self._sleep(random.uniform(1, 2))

        if (
            not self._is_stopped()
            and self.online_time_summary.get("status") == "completed"
            and self.online_time_summary.get("refresh_count", 0) > 0
        ):
            log_info("执行任务: 挂机后完成任务", self.account_name)
            task_results["挂机后完成任务"] = self.quick_complete_doing_missions()
            self._sleep(random.uniform(1, 2))

        # 日志互动
        if not self._is_stopped():
            log_info("执行任务: 震惊互动", self.account_name)
            successful_uids, processed_uids = interact_with_blogs(
                self.session, self.account_name,
                controller=self._controller,
            )
            task_results["震惊互动"] = len(successful_uids) > 0

            if processed_uids and not self._is_stopped():
                target_uids = processed_uids[:POKE_TARGET_COUNT]
                log_info(f"选择 {len(target_uids)} 个用户进行空间访问和打招呼", self.account_name)

                if not self._is_stopped():
                    log_info("执行任务: 空间访问", self.account_name)
                    task_results["空间访问"] = self.quick_visit_spaces(target_uids)

                if not self._is_stopped():
                    log_info("执行任务: 打招呼", self.account_name)
                    task_results["打招呼"] = self.quick_poke_users(target_uids)

        # 统计与兑换
        if not self._is_stopped():
            log_info("收集统计信息", self.account_name)
            user_credits, exchange_result = self.get_user_credits_and_exchange()
            if exchange_result is not None:
                task_results["血液兑换"] = exchange_result
        else:
            user_credits = {}
            log_warning("已停止，跳过统计信息收集", self.account_name)

        task_summary_data = []
        if not self._is_stopped():
            task_summary_data = self.get_daily_task_summary()

        report_message = self.generate_detailed_report(
            task_results,
            user_credits=user_credits,
            task_summary_data=task_summary_data,
        )

        success_count = sum(1 for result in task_results.values() if result)
        total_count = len(task_results)
        log_success(f"任务完成: {success_count}/{total_count} 成功", self.account_name)

        return report_message
    def quick_daily_sign(self) -> bool:
        """快速签到"""
        try:
            if not self.formhash:
                return False
            url = (
                f"{BASE_URL}/k_misign-sign.html"
                f"?operation=qiandao&format=button&formhash={self.formhash}"
            )
            response = self._send_request(
                'GET', url, headers={'X-Requested-With': 'XMLHttpRequest'}
            )
            text = response.text
            if 'succeed' in text or '签到成功' in text:
                log_success("签到成功", self.account_name)
                return True
            if '已签' in text:
                log_info("今日已签到", self.account_name)
                return True
            log_warning("签到状态未知", self.account_name)
            return False
        except Exception as e:
            log_error(f"签到失败: {e}", self.account_name)
            return False
    def quick_daily_lottery(self) -> bool:
        """快速抽奖"""
        try:
            if not self.formhash:
                return False
            url = (
                f"{BASE_URL}/plugin.php?id=it618_award:ajax"
                f"&ac=getaward&formhash={self.formhash}&_={int(time.time() * 1000)}"
            )
            response = self._send_request(
                'GET', url, headers={'X-Requested-With': 'XMLHttpRequest'}
            )

            try:
                res_json = response.json()
                tip_name = res_json.get("tipname")
                tip_value = res_json.get("tipvalue", "")

                if tip_name == "ok":
                    clean_tip_value = re.sub(r'<.*?>', '', tip_value).strip()
                    log_success(f"抽奖成功: {clean_tip_value}", self.account_name)
                    return True
                elif not tip_name:
                    log_info("今日已抽奖", self.account_name)
                    return True
                else:
                    log_warning(f"抽奖返回: {tip_name} - {tip_value}", self.account_name)
                    return False
            except (ValueError, json.JSONDecodeError):
                log_warning(f"抽奖结果未知: {response.text[:100]}", self.account_name)
                return False

        except Exception as e:
            log_error(f"抽奖失败: {e}", self.account_name)
            return False

