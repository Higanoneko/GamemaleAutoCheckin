# -*- coding: utf-8 -*-
"""Blog interaction and social actions."""

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
    _is_shock_click_success,
)
from .stop_controller import StopController


def interact_with_blogs(
    client: Any,
    account_name: str = "",
    target_interactions: int = BLOG_INTERACTION_TARGET,
    max_pages_to_scan: int = BLOG_MAX_PAGES,
    controller: Optional[StopController] = None,
) -> Tuple[List[str], List[str]]:
    """
    持续查找并与日志互动，直到达到目标次数。

    Args:
        client: GamemaleAutomation 实例（所有请求经其统一发送，
            可自动处理 Cloudflare 人机验证页）

    返回: (成功互动的 UID 列表, 已处理的 UID 列表)
    """
    log_section(f"日志互动 (目标: {target_interactions}次)", account_name)

    if controller is None and getattr(client, "_controller", None) is not None:
        controller = client._controller

    def is_stopped() -> bool:
        """统一的中断检查：优先使用显式传入的 controller。"""
        if controller is not None:
            return controller.is_stopped()
        return False

    def interruptible_sleep(seconds: float) -> None:
        """统一的可中断等待：显式 controller 优先，其次 client._sleep()。"""
        if controller is not None:
            controller.interruptible_sleep(seconds)
            return
        sleeper = getattr(client, "_sleep", None)
        if callable(sleeper):
            sleeper(seconds)
        else:
            time.sleep(seconds)

    successful_user_ids: Set[str] = set()
    processed_user_ids: Set[str] = set()
    processed_blog_urls: Set[str] = set()

    page_num = 1
    while len(successful_user_ids) < target_interactions and page_num <= max_pages_to_scan:
        if is_stopped():
            log_warning("收到停止信号，中断日志互动", account_name)
            break

        log_info(f"扫描第 {page_num}/{max_pages_to_scan} 页...", account_name)

        try:
            current_url = f"{BASE_URL}/home.php?mod=space&do=blog&view=all&page={page_num}"
            response = client._send_request('GET', current_url)

            href_matches = _extract_blog_urls(response.text)
            if not href_matches:
                log_info("当前页未找到日志链接，停止扫描", account_name)
                break

            new_blogs_found_on_page = 0
            for href in href_matches:
                if is_stopped():
                    log_warning("收到停止信号，中断日志互动", account_name)
                    break

                full_url = href if href.startswith('http') else f"{BASE_URL}/{href}"
                if full_url in processed_blog_urls:
                    continue

                new_blogs_found_on_page += 1
                processed_blog_urls.add(full_url)

                try:
                    uid = _extract_blog_uid(full_url)
                    if not uid:
                        continue

                    processed_user_ids.add(uid)

                    page_response = client._send_request('GET', full_url)
                    page_text = page_response.text

                    if _is_blog_unavailable(page_text):
                        continue

                    click_url = _extract_shock_click_url(page_text)
                    if not click_url:
                        continue

                    ajax_headers = {'Referer': full_url, 'X-Requested-With': 'XMLHttpRequest'}
                    click_response = client._send_request('GET', click_url, headers=ajax_headers)
                    response_text = click_response.text.strip()

                    if _is_shock_click_success(response_text):
                        log_success(
                            f"震惊成功 (UID:{uid}) [{len(successful_user_ids)+1}/{target_interactions}]",
                            account_name,
                        )
                        successful_user_ids.add(uid)

                    if is_stopped():
                        break

                    # 可中断的等待
                    interruptible_sleep(random.uniform(2, 5))

                    if len(successful_user_ids) >= target_interactions:
                        break

                except Exception as e:
                    log_warning(f"处理日志时出错: {e}", account_name)

            if len(successful_user_ids) >= target_interactions:
                break

            if is_stopped():
                break

            if new_blogs_found_on_page == 0:
                break

        except Exception as e:
            log_error(f"抓取日志列表出错: {e}", account_name)
            break

        page_num += 1

    log_info(f"日志互动完成: 成功 {len(successful_user_ids)} 次", account_name)
    return list(successful_user_ids), list(processed_user_ids)


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
        return success > 0
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
        return success_count > 0
