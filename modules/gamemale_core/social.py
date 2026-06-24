# -*- coding: utf-8 -*-
"""Blog interaction and social actions."""

import random
import re
import time
from typing import List, Optional, Set, Tuple

import requests
from bs4 import BeautifulSoup

from .constants import BASE_URL, BLOG_INTERACTION_TARGET, BLOG_MAX_PAGES, DEFAULT_TIMEOUT
from .logging_utils import log_error, log_info, log_section, log_success, log_warning
from .stop_controller import StopController


def interact_with_blogs(
    session: requests.Session,
    account_name: str = "",
    target_interactions: int = BLOG_INTERACTION_TARGET,
    max_pages_to_scan: int = BLOG_MAX_PAGES,
    controller: Optional[StopController] = None,
) -> Tuple[List[str], List[str]]:
    """
    持续查找并与日志互动，直到达到目标次数。

    返回: (成功互动的 UID 列表, 已处理的 UID 列表)
    """
    log_section(f"日志互动 (目标: {target_interactions}次)", account_name)

    successful_user_ids: Set[str] = set()
    processed_user_ids: Set[str] = set()
    processed_blog_urls: Set[str] = set()

    page_num = 1
    while len(successful_user_ids) < target_interactions and page_num <= max_pages_to_scan:
        if controller and controller.is_stopped():
            log_warning("收到停止信号，中断日志互动", account_name)
            break

        log_info(f"扫描第 {page_num}/{max_pages_to_scan} 页...", account_name)

        try:
            current_url = f"{BASE_URL}/home.php?mod=space&do=blog&view=all&page={page_num}"
            response = session.get(current_url, timeout=DEFAULT_TIMEOUT)
            response.raise_for_status()

            href_matches = re.findall(r'href="([^"]*blog-\d+-\d+\.html[^"]*)"', response.text)
            if not href_matches:
                log_info("当前页未找到日志链接，停止扫描", account_name)
                break

            new_blogs_found_on_page = 0
            for href in href_matches:
                if controller and controller.is_stopped():
                    log_warning("收到停止信号，中断日志互动", account_name)
                    break

                full_url = href if href.startswith('http') else f"{BASE_URL}/{href}"
                if full_url in processed_blog_urls:
                    continue

                new_blogs_found_on_page += 1
                processed_blog_urls.add(full_url)

                try:
                    uid_match = re.search(r'blog-(\d+)-', full_url)
                    if not uid_match:
                        continue

                    uid = uid_match.group(1)
                    processed_user_ids.add(uid)

                    page_response = session.get(full_url, timeout=DEFAULT_TIMEOUT)
                    page_response.raise_for_status()
                    page_text = page_response.text

                    if "您不能访问当前内容" in page_text or "指定的主题不存在或已被删除或正在被审核" in page_text:
                        continue

                    shock_button = BeautifulSoup(page_text, 'html.parser').select_one(
                        'a[id*="click_blogid_"][id$="_1"]'
                    )
                    if not shock_button:
                        continue

                    click_url_raw = shock_button.get('href')
                    click_url = (
                        (click_url_raw.replace('&amp;', '&') + '&inajax=1')
                        if '&inajax=1' not in click_url_raw
                        else click_url_raw.replace('&amp;', '&')
                    )
                    if not click_url.startswith('http'):
                        click_url = f"{BASE_URL}/{click_url.lstrip('/')}"

                    ajax_headers = {'Referer': full_url, 'X-Requested-With': 'XMLHttpRequest'}
                    click_response = session.get(click_url, headers=ajax_headers, timeout=DEFAULT_TIMEOUT)
                    response_text = click_response.text.strip()

                    if 'succeed' in response_text or '表态成功' in response_text:
                        log_success(
                            f"震惊成功 (UID:{uid}) [{len(successful_user_ids)+1}/{target_interactions}]",
                            account_name,
                        )
                        successful_user_ids.add(uid)

                    if controller and controller.is_stopped():
                        break

                    # 可中断的等待
                    delay = random.uniform(2, 5)
                    if controller:
                        controller.interruptible_sleep(delay)
                    else:
                        time.sleep(delay)

                    if len(successful_user_ids) >= target_interactions:
                        break

                except Exception as e:
                    log_warning(f"处理日志时出错: {e}", account_name)

            if len(successful_user_ids) >= target_interactions:
                break

            if controller and controller.is_stopped():
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
                if self.session.head(url, allow_redirects=True, timeout=DEFAULT_TIMEOUT).status_code == 200:
                    success += 1
                self._sleep(1)
            except Exception:
                pass
        log_info(f"空间访问: {success}/{len(user_ids)} 成功", self.account_name)
        return success > 0
    def quick_poke_users(self, user_ids: List[str]) -> bool:
        """对一组用户执行\"打招呼\"操作"""
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

                if '今天您已经打过招呼了' in response.text:
                    success_count += 1
                    continue

                content_match = re.search(r'<!\[CDATA\[(.*)\]\]>', response.text, re.DOTALL)
                if not content_match:
                    continue

                soup = BeautifulSoup(content_match.group(1), 'html.parser')
                form = soup.find('form', id=f'pokeform_{uid}')
                if not form:
                    continue

                action_url_raw = form['action']
                action_url = action_url_raw.replace('&amp;', '&')
                if not action_url.startswith('http'):
                    action_url = f"{BASE_URL}/{action_url.lstrip('/')}"

                formhash = form.find('input', {'name': 'formhash'})['value']

                payload = {
                    'formhash': formhash,
                    'handlekey': f'a_poke_{uid}',
                    'pokeuid': uid,
                    'pokesubmit': 'true',
                    'iconid': '3',
                    'note': '',
                }

                final_headers = self.session.headers.copy()
                final_headers.update({
                    'X-Requested-With': 'XMLHttpRequest',
                    'Referer': f'{BASE_URL}/space-uid-{uid}.html',
                })

                post_response = self._send_request('POST', action_url, data=payload, headers=final_headers)

                if '已发送' in post_response.text and '下次访问时会收到通知' in post_response.text:
                    success_count += 1
            except Exception:
                pass
            finally:
                self._sleep(random.uniform(2, 4))

        log_info(f"打招呼完成: {success_count}/{len(user_ids)} 成功", self.account_name)
        return success_count > 0

