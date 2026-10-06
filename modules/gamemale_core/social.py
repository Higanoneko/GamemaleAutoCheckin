# -*- coding: utf-8 -*-
"""Blog interaction and social actions."""

from dataclasses import dataclass
import random
import time
from typing import Any, List, Optional, Set, Tuple

from .constants import BASE_URL, BLOG_INTERACTION_TARGET, BLOG_MAX_PAGES
from .logging_utils import log_error, log_info, log_section, log_success, log_warning
from .parsers import (
    _extract_blog_uid,
    _extract_blog_urls,
    _extract_poke_form,
    _extract_shock_click_url,
    _is_blog_unavailable,
    _is_poke_already_sent,
    _is_poke_send_success,
    classify_shock_response,
    _resolve_gamemale_url,
    blog_identity,
)
from .stop_controller import StopController
from .results import TaskResult, TaskStatus


@dataclass(frozen=True)
class BlogInteractionResult:
    target: int
    new_count: int = 0
    already_count: int = 0
    failed_count: int = 0
    unknown_count: int = 0
    skipped_count: int = 0
    scanned_count: int = 0
    successful_uids: Tuple[str, ...] = ()
    processed_uids: Tuple[str, ...] = ()
    stopped: bool = False


def blog_task_result(result: BlogInteractionResult) -> TaskResult:
    """统计只解释已确认的动作，扫描不足不推断今日完成或强行报错。"""
    status: TaskStatus
    if result.stopped:
        status = 'stopped'
    elif result.new_count >= result.target:
        status = 'success'
    elif result.failed_count:
        status = 'failed'
    else:
        status = 'unknown'
    detail = (f'新增 {result.new_count}/{result.target}，已操作 {result.already_count}，'
              f'失败 {result.failed_count}，未知 {result.unknown_count}，扫描 {result.scanned_count} 篇；'
              '已操作不代表今日完成')
    return TaskResult('震惊互动', status, detail, required=status != 'unknown')


def interact_with_blogs(
    client: Any,
    account_name: str = "",
    target_interactions: int = BLOG_INTERACTION_TARGET,
    max_pages_to_scan: int = BLOG_MAX_PAGES,
    controller: Optional[StopController] = None,
) -> BlogInteractionResult:
    """按日志计数，按首次发现顺序返回用户；重复表态不冒充今日新增。"""
    active_controller = controller if controller is not None else getattr(client, '_controller', None)

    def is_stopped() -> bool:
        return bool(active_controller and active_controller.is_stopped()) or bool(client._is_stopped())

    def wait(seconds: float) -> None:
        if active_controller:
            active_controller.interruptible_sleep(seconds)
        else:
            client._sleep(seconds)

    successful_uids: List[str] = []
    processed_uids: List[str] = []
    seen: Set[Tuple[str, str]] = set()
    new_count = already_count = failed_count = unknown_count = skipped_count = 0
    log_section(f"日志互动（新增目标: {target_interactions} 次）", account_name)
    for page_num in range(1, max_pages_to_scan + 1):
        if is_stopped() or new_count >= target_interactions:
            break
        try:
            response = client._send_request('GET',
                f"{BASE_URL}/home.php?mod=space&do=blog&view=all&page={page_num}", safe_to_retry=True)
            links = _extract_blog_urls(response.text)
        except Exception as error:
            log_error(f"读取日志列表失败: {type(error).__name__}", account_name)
            failed_count += 1
            break
        found_new = False
        for link in links:
            if is_stopped() or new_count >= target_interactions:
                break
            url = _resolve_gamemale_url(link)
            identity = blog_identity(url)
            if identity is None or identity in seen:
                continue
            found_new = True
            seen.add(identity)
            uid = _extract_blog_uid(url)
            if not uid:
                skipped_count += 1
                continue
            if uid not in processed_uids:
                processed_uids.append(uid)
            try:
                page = client._send_request('GET', url, safe_to_retry=True)
                click_url = _extract_shock_click_url(page.text)
                if _is_blog_unavailable(page.text) or not click_url:
                    skipped_count += 1
                    continue
                response = client._send_request('GET', click_url,
                    headers={'Referer': url, 'X-Requested-With': 'XMLHttpRequest'})
                status = classify_shock_response(response.text)
                if status == 'success':
                    new_count += 1
                    if uid not in successful_uids:
                        successful_uids.append(uid)
                elif status == 'already_done':
                    already_count += 1
                elif status == 'failed':
                    failed_count += 1
                else:
                    unknown_count += 1
            except Exception as error:
                failed_count += 1
                log_warning(f"日志互动失败: {type(error).__name__}", account_name)
            finally:
                if not is_stopped() and new_count < target_interactions:
                    wait(random.uniform(2, 5))
        if not found_new:
            break
    return BlogInteractionResult(
        target=target_interactions, new_count=new_count, already_count=already_count,
        failed_count=failed_count, unknown_count=unknown_count, skipped_count=skipped_count,
        scanned_count=len(seen), successful_uids=tuple(successful_uids),
        processed_uids=tuple(processed_uids), stopped=is_stopped(),
    )


class SocialMixin:
    def quick_visit_spaces(self, user_ids: List[str]) -> bool:
        """快速空间访问"""
        if not user_ids:
            return True
        success = 0
        for uid in user_ids:
            if self._is_stopped():
                break
            try:
                url = f"{BASE_URL}/space-uid-{uid}.html"
                # 用 GET 而非 HEAD：验证页检测依赖响应正文，HEAD 无正文无法触发
                # Cloudflare 自动放行；且访问计数/可达性判定均以 200 为准。
                if self._send_request('GET', url).status_code == 200:
                    success += 1
                self._sleep(1)
            except Exception:
                pass
        log_info(f"空间访问: {success}/{len(user_ids)} 成功", self.account_name)
        return success == len(user_ids) and not self._is_stopped()
    def quick_poke_users(self, user_ids: List[str]) -> bool:
        """对一组用户执行"打招呼"操作"""
        if not user_ids:
            return True
        success_count = 0
        for uid in user_ids:
            if self._is_stopped():
                log_warning("收到停止信号，中断打招呼", self.account_name)
                break
            try:
                get_url = (
                    f"{BASE_URL}/home.php?mod=spacecp&ac=poke"
                    f"&op=send&uid={uid}&inajax=1"
                )
                headers = {'X-Requested-With': 'XMLHttpRequest'}
                response = self._send_request('GET', get_url, headers=headers)

                if _is_poke_already_sent(response.text):
                    success_count += 1
                    continue

                poke_form = _extract_poke_form(response.text, uid)
                if not poke_form:
                    continue

                payload = {
                    'formhash': poke_form["formhash"],
                    'handlekey': f'a_poke_{uid}',
                    'pokeuid': uid,
                    'pokesubmit': 'true',
                    'iconid': '3',
                    'note': '',
                }

                # 会话级 UA/Referer 由统一 Session 自动附带，这里只传本次请求头
                final_headers = {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Referer': f'{BASE_URL}/space-uid-{uid}.html',
                }

                post_response = self._send_request(
                    'POST', poke_form["action"], data=payload, headers=final_headers
                )

                if _is_poke_send_success(post_response.text):
                    success_count += 1
            except Exception:
                pass
            finally:
                self._sleep(random.uniform(2, 4))

        log_info(f"打招呼完成: {success_count}/{len(user_ids)} 成功", self.account_name)
        return success_count == len(user_ids) and not self._is_stopped()
