# -*- coding: utf-8 -*-
"""Check and accept newly available forum missions."""

import random
from typing import Dict, List, Optional, Set, Tuple

from .constants import TASK_DOING_URL, TASK_LIST_URL
from .logging_utils import log_error, log_info, log_success, log_warning
from .parsers import (
    _classify_task_apply_message,
    _classify_task_draw_message,
    _extract_page_message,
    _parse_doing_task_list,
    _parse_new_task_list,
)


def _task_exclusion_reason(
    task: Dict[str, str],
    exclude_ids: Set[str],
    exclude_names: Set[str],
    exclude_keywords: List[str],
) -> Optional[str]:
    """判断任务是否命中排除规则，命中返回原因文本（纯函数）。"""
    task_id = task.get("id", "")
    task_name = task.get("name", "")
    searchable_text = f"{task_name}\n{task.get('description', '')}".casefold()

    if task_id in exclude_ids:
        return f"ID {task_id} 在排除列表中"
    if task_name.casefold() in exclude_names:
        return f"任务名“{task_name}”在排除列表中"
    for keyword in exclude_keywords:
        if keyword and keyword in searchable_text:
            return f"命中排除关键词“{keyword}”"
    return None


class MissionsMixin:
    def _get_task_exclusions(self) -> Tuple[Set[str], Set[str], List[str]]:
        """读取任务排除配置，支持按 ID、完整名称、关键词排除。"""
        generic_excludes = self._get_config_list([
            "task_exclude",
            "exclude_tasks",
            "excluded_tasks",
        ])
        exclude_ids = {
            item
            for item in self._get_config_list([
                "task_exclude_ids",
                "exclude_task_ids",
                "excluded_task_ids",
            ])
        }
        exclude_ids.update(item for item in generic_excludes if item.isdigit())
        exclude_names = {
            item.casefold()
            for item in self._get_config_list([
                "task_exclude_names",
                "exclude_task_names",
                "excluded_task_names",
                "task_exclude_titles",
            ])
        }
        exclude_keywords = [
            item.casefold()
            for item in self._get_config_list([
                "task_exclude_keywords",
                "exclude_task_keywords",
                "excluded_task_keywords",
            ])
        ]
        exclude_keywords.extend(item.casefold() for item in generic_excludes if not item.isdigit())
        return exclude_ids, exclude_names, exclude_keywords

    def _get_task_exclusion_reason(self, task: Dict[str, str]) -> Optional[str]:
        """判断任务是否命中排除规则（读取配置后交给纯函数判定）。"""
        exclude_ids, exclude_names, exclude_keywords = self._get_task_exclusions()
        return _task_exclusion_reason(task, exclude_ids, exclude_names, exclude_keywords)
    def get_new_tasks(self) -> List[Dict[str, str]]:
        """获取当前可接取的新任务列表。"""
        response = self._send_request('GET', TASK_LIST_URL, safe_to_retry=True)
        tasks = _parse_new_task_list(response.text)
        log_info(f"检测到 {len(tasks)} 个可接取任务", self.account_name)
        return tasks
    def quick_accept_new_tasks(self) -> bool:
        """检查并自动接取新任务，支持按配置排除指定任务。"""
        self.mission_results = []
        self.mission_summary = {
            "detected": 0,
            "accepted": 0,
            "skipped": 0,
            "failed": 0,
        }

        if not self._get_config_bool([
            "auto_accept_tasks",
            "auto_accept_tasks_enabled",
            "auto_task_accept_enabled",
        ], default=True):
            self.mission_summary["disabled"] = 1
            log_info("自动接取新任务已禁用", self.account_name)
            return True

        try:
            tasks = self.get_new_tasks()
            self.mission_summary["detected"] = len(tasks)
            if not tasks:
                log_info("没有可接取的新任务", self.account_name)
                return True

            accepted_count = 0
            failed_count = 0
            skipped_count = 0

            for task in tasks:
                if self._is_stopped():
                    log_warning("收到停止信号，中断新任务接取", self.account_name)
                    break

                exclusion_reason = self._get_task_exclusion_reason(task)
                if exclusion_reason:
                    skipped_count += 1
                    self.mission_results.append({
                        "id": task["id"],
                        "name": task["name"],
                        "status": "skipped",
                        "message": exclusion_reason,
                    })
                    log_info(
                        f"跳过任务: {task['name']} (ID:{task['id']})，{exclusion_reason}",
                        self.account_name,
                    )
                    continue

                log_info(f"接取任务: {task['name']} (ID:{task['id']})", self.account_name)
                try:
                    response = self._send_request(
                        'GET',
                        task["apply_url"],
                        headers={'Referer': TASK_LIST_URL},
                    )
                    message = _extract_page_message(response.text)
                    outcome = _classify_task_apply_message(message)
                    if outcome == "accepted":
                        accepted_count += 1
                        self.mission_results.append({
                            "id": task["id"],
                            "name": task["name"],
                            "status": "accepted",
                            "message": message,
                        })
                        log_success(f"任务接取成功: {task['name']} (ID:{task['id']})", self.account_name)
                    elif outcome == "already_doing":
                        accepted_count += 1
                        self.mission_results.append({
                            "id": task["id"],
                            "name": task["name"],
                            "status": "already_doing",
                            "message": message,
                        })
                        log_info(f"任务已在进行中: {task['name']} (ID:{task['id']})", self.account_name)
                    else:
                        failed_count += 1
                        self.mission_results.append({
                            "id": task["id"],
                            "name": task["name"],
                            "status": "failed",
                            "message": message,
                        })
                        log_warning(
                            f"任务接取结果未知: {task['name']} (ID:{task['id']}) - {message[:120]}",
                            self.account_name,
                        )
                except Exception as e:
                    failed_count += 1
                    self.mission_results.append({
                        "id": task["id"],
                        "name": task["name"],
                        "status": "failed",
                        "message": str(e),
                    })
                    log_error(f"任务接取失败: {task['name']} (ID:{task['id']}): {e}", self.account_name)
                finally:
                    self._sleep(random.uniform(1, 2))

            self.mission_summary.update({
                "accepted": accepted_count,
                "skipped": skipped_count,
                "failed": failed_count,
            })
            log_info(
                f"新任务接取完成: 成功/已在进行 {accepted_count}，跳过 {skipped_count}，失败 {failed_count}",
                self.account_name,
            )
            return failed_count == 0

        except Exception as e:
            log_error(f"检查或接取新任务失败: {e}", self.account_name)
            return False

    def get_doing_missions(self) -> List[Dict[str, str]]:
        """获取进行中的任务列表，并标记可领取奖励的任务。"""
        response = self._send_request('GET', TASK_DOING_URL, safe_to_retry=True)
        missions = _parse_doing_task_list(response.text)
        log_info(f"检测到 {len(missions)} 个进行中的任务", self.account_name)
        return missions

    def quick_complete_doing_missions(self) -> bool:
        """自动领取已经完成的进行中任务奖励。"""
        if not self._get_config_bool([
            "auto_complete_tasks",
            "auto_complete_tasks_enabled",
            "auto_draw_tasks",
        ], default=True):
            self.mission_summary["complete_disabled"] = 1
            log_info("自动完成/领取任务已禁用", self.account_name)
            return True

        try:
            missions = self.get_doing_missions()
            self.mission_summary["doing_detected"] = len(missions)
            if not missions:
                log_info("没有进行中的任务", self.account_name)
                return True

            completed_count = 0
            not_ready_count = 0
            failed_count = 0

            for mission in missions:
                if self._is_stopped():
                    log_warning("收到停止信号，中断任务完成检查", self.account_name)
                    break

                if mission.get("can_draw") != "true":
                    not_ready_count += 1
                    self.mission_results.append({
                        "id": mission["id"],
                        "name": mission["name"],
                        "status": "not_ready",
                        "message": f"进度 {mission.get('progress', '0')}%，暂不可领取",
                    })
                    log_info(
                        f"任务未完成: {mission['name']} (ID:{mission['id']})，进度 {mission.get('progress', '0')}%",
                        self.account_name,
                    )
                    continue

                log_info(f"领取任务奖励: {mission['name']} (ID:{mission['id']})", self.account_name)
                try:
                    response = self._send_request(
                        'GET',
                        mission["draw_url"],
                        headers={'Referer': TASK_DOING_URL},
                    )
                    message = _extract_page_message(response.text)
                    if _classify_task_draw_message(message) == "completed":
                        completed_count += 1
                        self.mission_results.append({
                            "id": mission["id"],
                            "name": mission["name"],
                            "status": "completed",
                            "message": message,
                        })
                        log_success(f"任务奖励领取成功: {mission['name']} (ID:{mission['id']})", self.account_name)
                    else:
                        failed_count += 1
                        self.mission_results.append({
                            "id": mission["id"],
                            "name": mission["name"],
                            "status": "complete_failed",
                            "message": message,
                        })
                        log_warning(
                            f"任务领取结果未知: {mission['name']} (ID:{mission['id']}) - {message[:120]}",
                            self.account_name,
                        )
                except Exception as e:
                    failed_count += 1
                    self.mission_results.append({
                        "id": mission["id"],
                        "name": mission["name"],
                        "status": "complete_failed",
                        "message": str(e),
                    })
                    log_error(f"任务奖励领取失败: {mission['name']} (ID:{mission['id']}): {e}", self.account_name)
                finally:
                    self._sleep(random.uniform(1, 2))

            self.mission_summary.update({
                "completed": completed_count,
                "not_ready": not_ready_count,
                "complete_failed": failed_count,
            })
            log_info(
                f"任务完成检查结束: 领取 {completed_count}，未完成 {not_ready_count}，失败 {failed_count}",
                self.account_name,
            )
            return failed_count == 0

        except Exception as e:
            log_error(f"检查或领取进行中任务失败: {e}", self.account_name)
            return False

