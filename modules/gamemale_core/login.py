# -*- coding: utf-8 -*-
"""Login and formhash handling for the shared automation client."""

import random
import re
from typing import Optional, Tuple

from bs4 import BeautifulSoup

from .constants import BASE_URL, DDDDOCR_AVAILABLE, DEFAULT_TIMEOUT, MAX_LOGIN_RETRIES
from .logging_utils import log_error, log_info, log_section, log_success, log_warning
from .parsers import (
    _clean_captcha_text,
    _extract_ajax_content,
    _extract_seccode_image_url,
    _extract_seccodehash,
)


class LoginMixin:
    def _verify_logged_in_session(self) -> bool:
        """访问个人资料页，确认当前 Session 已经处于登录状态。"""
        try:
            test_url = f'{BASE_URL}/home.php?mod=space&do=profile'
            response = self.session.get(test_url, allow_redirects=False, timeout=DEFAULT_TIMEOUT)
            if response.status_code != 200:
                return False

            page_text = response.text
            if '登录' in page_text and '请先登录' in page_text:
                return False
            return any(token in page_text for token in ('我的资料', '个人空间', 'uid='))
        except Exception as e:
            log_warning(f"登录状态验证出错: {e}", self.account_name)
            return False
    def _extract_login_error_message(self, response_text: str) -> str:
        """从登录失败的 Discuz AJAX 响应中提取可读错误信息。"""
        content = _extract_ajax_content(response_text)
        content = re.split(r'<script\b', content, maxsplit=1, flags=re.IGNORECASE)[0]
        message = BeautifulSoup(content, 'html.parser').get_text(" ", strip=True)
        message = re.sub(r'\s+', ' ', message)
        return message or "未知登录错误"
    def login(self) -> bool:
        """统一的登录管理"""
        log_section("登录流程", self.account_name)

        login_successful = False

        # 优先尝试 Cookie 登录
        if self.config.get("cookie"):
            if self._login_with_cookie():
                log_success("Cookie 登录成功", self.account_name)
                login_successful = True
            else:
                self.session.cookies.clear()
                log_info("Cookie 已过期或无效，尝试密码登录", self.account_name)

        # Cookie 登录失败则尝试密码登录
        if not login_successful and self.config.get("username") and self.config.get("password"):
            if self._login_with_password():
                log_success("密码登录成功", self.account_name)
                # 通过回调保存 Cookie（具体实现由入口脚本提供）
                if self._save_cookie_callback:
                    self._save_cookie_callback(self)
                login_successful = True

        if login_successful:
            self.is_logged_in = True
            self.get_and_store_formhash()
        else:
            log_error("所有登录方式均失败", self.account_name)

        return self.is_logged_in
    def _login_with_cookie(self) -> bool:
        """使用 Cookie 尝试登录"""
        cookie_string = self.config.get("cookie")
        if not cookie_string:
            return False

        for cookie in cookie_string.split(';'):
            cookie = cookie.strip()
            if '=' in cookie:
                name, value = cookie.split('=', 1)
                self.session.cookies.set(name.strip(), value.strip(), domain='www.gamemale.com')

        return self._verify_logged_in_session()
    def _login_with_password(self) -> bool:
        """使用密码进行登录"""
        if not DDDDOCR_AVAILABLE:
            log_warning("ddddocr 未安装，无法进行密码登录", self.account_name)
            return False

        if not self._init_ocr():
            log_warning("OCR初始化失败", self.account_name)
            return False

        username = self.config.get("username")
        password = self.config.get("password")

        if not all([username, password]):
            log_warning("密码登录信息不完整", self.account_name)
            return False

        for attempt in range(MAX_LOGIN_RETRIES):
            if self._is_stopped():
                log_warning("收到停止信号，中断登录", self.account_name)
                return False

            log_info(f"尝试密码登录 ({attempt + 1}/{MAX_LOGIN_RETRIES})...", self.account_name)

            try:
                loginhash, formhash, seccodehash, seccode_verify = self._get_login_parameters()

                if loginhash == "ALREADY_LOGGED_IN":
                    return True

                if not all([loginhash, formhash, seccodehash, seccode_verify]):
                    raise ValueError("获取登录参数失败")

                login_url = (
                    f"{BASE_URL}/member.php?mod=logging&action=login"
                    f"&loginsubmit=yes&handlekey=login&loginhash={loginhash}&inajax=1"
                )
                payload = {
                    'formhash': formhash,
                    'referer': f'{BASE_URL}/forum.php',
                    'loginfield': 'username',
                    'username': username,
                    'password': password,
                    'questionid': self.config.get("questionid", "0"),
                    'answer': self.config.get("answer", ""),
                    'seccodehash': seccodehash,
                    'seccodeverify': seccode_verify,
                }

                login_response = self._send_request(
                    'POST', login_url, data=payload,
                    headers={'X-Requested-With': 'XMLHttpRequest'},
                )
                if 'succeed' in login_response.text or '欢迎您回来' in login_response.text:
                    if self._verify_logged_in_session():
                        return True
                    raise ValueError("登录响应成功，但未能验证登录状态")

                raise ValueError(self._extract_login_error_message(login_response.text))

            except Exception as e:
                log_warning(f"登录尝试失败: {e}", self.account_name)
                if attempt < MAX_LOGIN_RETRIES - 1:
                    self._sleep(random.uniform(2, 5))

        return False
    def _get_login_parameters(self) -> Tuple[str, Optional[str], Optional[str], Optional[str]]:
        """获取登录所需的动态参数和验证码"""
        ajax_headers = {'X-Requested-With': 'XMLHttpRequest'}
        login_popup_url = (
            f'{BASE_URL}/member.php?mod=logging&action=login'
            f'&infloat=yes&handlekey=login&inajax=1'
        )
        response = self._send_request('GET', login_popup_url, headers=ajax_headers)

        html_content = _extract_ajax_content(response.text)

        if '欢迎您回来' in html_content or 'succeedhandle_login' in html_content:
            log_info("检测到已登录状态，无需重新登录", self.account_name)
            return "ALREADY_LOGGED_IN", None, None, None

        soup = BeautifulSoup(html_content, 'html.parser')

        action_tag = soup.find('form', {'name': 'login'})
        if not action_tag or not action_tag.has_attr('action'):
            raise ValueError("未找到登录表单的action URL")
        action_url = action_tag['action']

        loginhash_match = re.search(r'loginhash=(\w+)', action_url)
        if not loginhash_match:
            raise ValueError("未找到loginhash")
        loginhash = loginhash_match.group(1)

        formhash_tag = soup.find('input', {'name': 'formhash'})
        if not formhash_tag or not formhash_tag.has_attr('value'):
            raise ValueError("未找到formhash")
        formhash = formhash_tag['value']

        seccodehash = _extract_seccodehash(html_content, soup)

        js_url = f"{BASE_URL}/misc.php?mod=seccode&action=update&idhash={seccodehash}&inajax=1"
        js_response = self._send_request('GET', js_url, headers=ajax_headers)
        img_url = _extract_seccode_image_url(js_response.text)
        img_response = self._send_request('GET', img_url)

        seccode_verify = self._recognize_captcha(img_response.content)
        if not seccode_verify:
            raise ValueError("验证码识别失败")

        return loginhash, formhash, seccodehash, seccode_verify
    def _recognize_captcha(self, image_bytes: bytes) -> Optional[str]:
        """使用 ddddocr 识别验证码"""
        try:
            raw_result = str(self._ocr.classification(image_bytes))
            clean_result = _clean_captcha_text(raw_result)
            if raw_result != clean_result:
                log_info(f"验证码识别结果: {raw_result} -> {clean_result}", self.account_name)
            else:
                log_info(f"验证码识别结果: {clean_result}", self.account_name)
            return clean_result or None
        except Exception as e:
            log_warning(f"验证码识别失败: {e}", self.account_name)
            return None
    def get_and_store_formhash(self) -> bool:
        """获取并存储 formhash"""
        log_info("获取 FormHash...", self.account_name)
        try:
            home_url = f'{BASE_URL}/home.php?mod=spacecp'
            response = self._send_request('GET', home_url)
            formhash_match = (
                re.search(r'formhash" value="([a-f0-9]+)"', response.text)
                or re.search(r'formhash=([a-f0-9]+)', response.text)
                or re.search(r'"formhash":"([a-f0-9]+)"', response.text)
            )

            if formhash_match:
                self.formhash = formhash_match.group(1)
                log_success("FormHash 获取成功", self.account_name)
                return True
            else:
                log_error("FormHash 获取失败", self.account_name)
                return False
        except Exception as e:
            log_error(f"FormHash 获取异常: {e}", self.account_name)
            return False

