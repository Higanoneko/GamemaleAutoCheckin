# -*- coding: utf-8 -*-
"""Daily task orchestration, sign-in, and lottery actions."""

import time

from .constants import BASE_URL
from .logging_utils import log_error, log_info, log_success, log_warning
from .parsers import _classify_sign_response, _parse_lottery_response
from .social import interact_with_blogs
from .results import AccountRunResult, TaskResult
from .workflow import execute_daily_workflow


class DailyTasksMixin:
    def execute_all_tasks(self, collect_task_summary: bool = True) -> AccountRunResult:
        """兼容客户端入口；流程由独立编排模块执行。"""
        return execute_daily_workflow(self, interact_with_blogs, collect_task_summary=collect_task_summary)

    def quick_daily_sign(self) -> TaskResult:
        """快速签到"""
        try:
            if not self.formhash:
                return TaskResult('签到', 'failed')
            url = (
                f"{BASE_URL}/k_misign-sign.html"
                f"?operation=qiandao&format=button&formhash={self.formhash}"
            )
            response = self._send_request(
                'GET', url, headers={'X-Requested-With': 'XMLHttpRequest'}
            )
            status = _classify_sign_response(response.text)
            if status == "success":
                log_success("签到成功", self.account_name)
                return TaskResult('签到', 'success')
            if status == "already":
                log_info("今日已签到", self.account_name)
                return TaskResult('签到', 'already_done')
            log_warning("签到状态未知", self.account_name)
            return TaskResult('签到', 'failed')
        except Exception as e:
            log_error(f"签到失败: {e}", self.account_name)
            return TaskResult('签到', 'failed')
    def quick_daily_lottery(self) -> TaskResult:
        """快速抽奖"""
        try:
            if not self.formhash:
                return TaskResult('抽奖', 'failed')
            url = (
                f"{BASE_URL}/plugin.php?id=it618_award:ajax"
                f"&ac=getaward&formhash={self.formhash}&_={int(time.time() * 1000)}"
            )
            response = self._send_request(
                'GET', url, headers={'X-Requested-With': 'XMLHttpRequest'}
            )

            status, payload = _parse_lottery_response(response.text)
            if status == "won":
                log_success(f"抽奖成功: {payload}", self.account_name)
                return TaskResult('抽奖', 'success')
            if status == "already":
                log_info("今日已抽奖", self.account_name)
                return TaskResult('抽奖', 'already_done')
            if status == "failed":
                log_warning(f"抽奖返回: {payload}", self.account_name)
            else:
                log_warning(f"抽奖结果未知: {payload}", self.account_name)
            return TaskResult('抽奖', 'failed')

        except Exception as e:
            log_error(f"抽奖失败: {e}", self.account_name)
            return TaskResult('抽奖', 'failed')

