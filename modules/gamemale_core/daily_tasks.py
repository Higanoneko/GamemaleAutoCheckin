# -*- coding: utf-8 -*-
"""Daily task orchestration, sign-in, and lottery actions."""

import random
import time
from typing import Callable, Dict, List, Union

from .constants import BASE_URL, POKE_TARGET_COUNT
from .logging_utils import log_error, log_info, log_section, log_success, log_warning
from .parsers import _classify_sign_response, _parse_lottery_response
from .social import blog_task_result, interact_with_blogs
from .results import AccountRunResult, TaskResult
from .reports import build_detailed_report
from .assets import parse_asset_snapshot


class DailyTasksMixin:
    def execute_all_tasks(self) -> AccountRunResult:
        """用返回值组合流程，报告与退出状态来自同一份结构化结果。"""
        outcomes: List[TaskResult] = []
        before: Dict[str, int] = {}
        after: Dict[str, int] = {}
        user_credits: Dict[str, str] = {}
        summary: List[Dict[str, str]] = []

        def finish() -> AccountRunResult:
            stopped = self._is_stopped()
            if stopped and not any(item.status == 'stopped' for item in outcomes):
                outcomes.append(TaskResult('运行', 'stopped', '收到停止信号'))
            report = build_detailed_report(
                self.account_name, outcomes, user_credits=user_credits,
                task_summary_data=summary, mission_summary=self.mission_summary,
                mission_results=self.mission_results, online_time_summary=self.online_time_summary,
                assets_before=before if before or after else None,
                assets_after=after if before or after else None,
            )
            return AccountRunResult(self.account_name, tuple(outcomes), report, stopped,
                                    tuple(before.items()), tuple(after.items()))

        def run(name: str, action: Callable[[], Union[bool, TaskResult]]) -> None:
            if self._is_stopped():
                return
            log_info(f'执行任务: {name}', self.account_name)
            try:
                value = action()
                result = value if isinstance(value, TaskResult) else TaskResult(name, 'success' if value else 'failed')
                if name == '挂机时长' and self.online_time_summary.get('status') in ('disabled', 'skipped'):
                    result = TaskResult(name, 'skipped', '未启用或未配置有效时长')
                if self._is_stopped():
                    result = TaskResult(name, 'stopped')
                outcomes.append(result)
            except Exception as error:
                outcomes.append(TaskResult(name, 'failed', type(error).__name__))
                log_error(f'{name}执行失败: {type(error).__name__}', self.account_name)
            if not self._is_stopped():
                self._sleep(random.uniform(1, 2))

        if not self.is_logged_in:
            outcomes.append(TaskResult('登录', 'failed', '未登录'))
            return finish()
        if not self.formhash:
            outcomes.append(TaskResult('formhash', 'failed', '未取得有效表单令牌'))
            return finish()
        if self._get_config_bool(['only_online', 'only_online_time'], default=False):
            run('挂机时长', self.quick_accumulate_online_time)
            return finish()

        mode = self._get_config_str(['run_mode'], default='full')
        if mode in ('check', 'status'):
            if not self._is_stopped():
                try:
                    user_credits, _ = self._get_credits()
                    after = parse_asset_snapshot(user_credits)
                    outcomes.append(TaskResult('登录自检', 'success'))
                    outcomes.append(TaskResult('资产查询', 'success' if after else 'failed'))
                except Exception as error:
                    outcomes.append(TaskResult('资产查询', 'failed', type(error).__name__))
            return finish()

        try:
            credits, _ = self._get_credits()
            before = parse_asset_snapshot(credits)
        except Exception as error:
            outcomes.append(TaskResult('初始资产查询', 'unknown', type(error).__name__, required=False))
        run('签到', self.quick_daily_sign)
        run('抽奖', self.quick_daily_lottery)
        if self._get_config_bool(['auto_accept_tasks', 'auto_accept_tasks_enabled', 'auto_task_accept_enabled'], default=True):
            run('接取新任务', self.quick_accept_new_tasks)
        else:
            outcomes.append(TaskResult('接取新任务', 'skipped', '已禁用'))
        if self._get_config_bool(['online_runtime_enabled'], default=False):
            run('挂机时长', self.quick_accumulate_online_time)
        else:
            outcomes.append(TaskResult('挂机时长', 'skipped', '未启用'))

        if not self._is_stopped():
            blogs = interact_with_blogs(self, self.account_name)
            outcomes.append(blog_task_result(blogs))
            target_uids = list(blogs.processed_uids[:POKE_TARGET_COUNT])
            if target_uids:
                run('空间访问', lambda: self.quick_visit_spaces(target_uids))
                run('打招呼', lambda: self.quick_poke_users(target_uids))
            else:
                outcomes.extend([TaskResult('空间访问', 'skipped', '没有可用用户'),
                                 TaskResult('打招呼', 'skipped', '没有可用用户')])

        # 互动和挂机产生的进度在本次运行内领取，不再提前检查。
        if self._get_config_bool(['auto_complete_tasks', 'auto_complete_tasks_enabled', 'auto_draw_tasks'], default=True):
            run('完成任务', self.quick_complete_doing_missions)
        else:
            outcomes.append(TaskResult('完成任务', 'skipped', '已禁用'))
        if not self._is_stopped():
            user_credits, exchange_result = self.get_user_credits_and_exchange()
            outcomes.append(TaskResult('血液兑换', 'skipped' if exchange_result is None else 'success' if exchange_result else 'failed'))
            after = parse_asset_snapshot(user_credits)
            outcomes.append(TaskResult('资产查询', 'success' if after else 'failed'))
            summary = self.get_daily_task_summary()
        return finish()

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

