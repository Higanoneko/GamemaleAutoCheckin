# -*- coding: utf-8 -*-
"""Login and formhash handling for the shared automation client."""

import random
from dataclasses import dataclass
from typing import Optional

import requests

from .cloudflare import CloudflareChallengeError
from .constants import BASE_URL, MAX_LOGIN_RETRIES
from .logging_utils import log_error, log_info, log_section, log_success, log_warning
from .parsers import (
    _clean_captcha_text,
    _extract_ajax_content,
    _extract_formhash,
    _extract_login_error_message,
    parse_login_form,
    parse_login_state,
    parse_cookie_header,
    extract_logged_in_uid,
    is_captcha_check_success,
    is_terminal_login_error,
    is_login_redirect,
    _extract_seccode_image_url,
    _is_login_form_session_alive,
    _is_login_response_success,
    _is_profile_page_logged_in,
)


class LoginVerificationError(ValueError):
    """响应没有足够的登录标记，不能把网络/结构问题解释为 Cookie 过期。"""


class CaptchaRecognitionError(ValueError):
    """独立验证码预算耗尽，不再通过重新登录刷新同一预算。"""


@dataclass(frozen=True)
class LoginParameters:
    loginhash: str
    formhash: Optional[str] = None
    seccodehash: Optional[str] = None
    seccode_verify: Optional[str] = None
    modid: Optional[str] = None


class LoginMixin:
    def _verify_logged_in_session(self) -> bool:
        response = self._send_request('GET', f'{BASE_URL}/home.php?mod=space&do=profile',
                                      allow_redirects=False, safe_to_retry=True)
        if response.status_code != 200:
            if response.status_code in (301, 302, 303, 307, 308) and is_login_redirect(response.headers.get('Location', '')):
                self.uid = None
                return False
            raise LoginVerificationError('登录探测返回重定向或异常状态，无法确认身份')
        state = parse_login_state(response.text)
        if state == 'unknown':
            raise LoginVerificationError('登录页面缺少身份标记，未确认 Cookie 是否过期')
        if state == 'logged_in':
            uid = extract_logged_in_uid(response.text)
            self.uid = uid if uid and uid > 0 else None
            return True
        self.uid = None
        return False

    def login(self) -> bool:
        """统一的登录管理"""
        log_section("登录流程", self.account_name)

        login_successful = False

        # 优先尝试 Cookie 登录
        if self.config.get("cookie"):
            try:
                if self._login_with_cookie():
                    log_success("Cookie 登录成功", self.account_name)
                    login_successful = True
                    if self._cf_solved_count > 0 and self._save_cookie_callback:
                        self._save_cookie_callback(self)
                else:
                    # 只在明确游客状态时清除登录 Cookie；保留已有 CF 放行标记。
                    for cookie in list(self.session.cookies):
                        if cookie.name.lower().endswith(('_auth', '_saltkey', '_sid')):
                            self.session.cookies.clear(cookie.domain, cookie.path, cookie.name)
                    log_info("已确认游客状态，尝试密码登录", self.account_name)
            except (ValueError, requests.RequestException, CloudflareChallengeError) as error:
                log_error(f"Cookie 验证未完成: {type(error).__name__}，请检查输入、网络或页面结构", self.account_name)
                return False

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

        for name, value in parse_cookie_header(cookie_string).items():
            self.session.cookies.set(name, value, domain='www.gamemale.com')

        return self._verify_logged_in_session()
    def _login_with_password(self) -> bool:
        """使用密码进行登录"""
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
                parameters = self._get_login_parameters()
                loginhash, formhash = parameters.loginhash, parameters.formhash
                seccodehash, seccode_verify = parameters.seccodehash, parameters.seccode_verify

                if loginhash == "ALREADY_LOGGED_IN":
                    return self._verify_logged_in_session()

                if not loginhash or not formhash or (seccodehash and not seccode_verify):
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
                }

                if seccodehash:
                    payload.update({'seccodehash': seccodehash, 'seccodeverify': seccode_verify,
                                    'seccodemodid': parameters.modid})

                login_response = self._send_request(
                    'POST', login_url, data=payload,
                    headers={'X-Requested-With': 'XMLHttpRequest'},
                )
                if _is_login_response_success(login_response.text):
                    if self._verify_logged_in_session():
                        return True
                    raise ValueError("登录响应成功，但未能验证登录状态")

                if is_terminal_login_error(login_response.text):
                    log_error('账号凭据错误或登录被限制，停止重试', self.account_name)
                    return False
                raise ValueError(_extract_login_error_message(login_response.text))

            except (requests.RequestException, CloudflareChallengeError, LoginVerificationError, CaptchaRecognitionError):
                # 提交结果未知时不能再次发送密码登录；CF 失败也不反复付费。
                log_error('登录请求结果未确认或被验证拦截，停止重复提交', self.account_name)
                return False
            except Exception as error:
                log_warning(f"登录尝试失败: {type(error).__name__}", self.account_name)
                if attempt < MAX_LOGIN_RETRIES - 1:
                    self._sleep(random.uniform(2, 5))

        return False
    def _get_login_parameters(self) -> LoginParameters:
        """获取登录所需的动态参数和验证码"""
        ajax_headers = {'X-Requested-With': 'XMLHttpRequest'}
        login_popup_url = (
            f'{BASE_URL}/member.php?mod=logging&action=login'
            f'&infloat=yes&handlekey=login&inajax=1'
        )
        response = self._send_request('GET', login_popup_url, headers=ajax_headers, safe_to_retry=True)

        html_content = _extract_ajax_content(response.text)

        if _is_login_form_session_alive(html_content):
            log_info("检测到已登录状态，无需重新登录", self.account_name)
            return LoginParameters('ALREADY_LOGGED_IN')

        form = parse_login_form(html_content)
        if not form.captcha_required:
            return LoginParameters(form.loginhash, form.formhash)
        if not self._init_ocr():
            raise ValueError('验证码登录需要安装 OCR 依赖')
        attempts = min(8, max(1, self._get_config_int(['captcha_max_retries'], default=3)))
        for attempt in range(attempts):
            if self._is_stopped():
                raise CloudflareChallengeError('已停止验证码识别')
            params = {'mod': 'seccode', 'action': 'update', 'idhash': form.seccodehash,
                      'modid': form.modid, 'inajax': '1'}
            js_response = self._send_request('GET', f'{BASE_URL}/misc.php', params=params, headers=ajax_headers)
            img_url = _extract_seccode_image_url(js_response.text)
            img_response = self._send_request('GET', img_url, params={'modid': form.modid})
            content_type = img_response.headers.get('Content-Type', '').split(';')[0].lower()
            code = self._recognize_captcha(img_response.content) if content_type.startswith('image/') and img_response.content else None
            if code:
                if not self._get_config_bool(['captcha_precheck'], default=True):
                    return LoginParameters(form.loginhash, form.formhash, form.seccodehash, code, form.modid)
                check_response = self._send_request('GET', f'{BASE_URL}/misc.php', params={
                    'mod': 'seccode', 'action': 'check', 'idhash': form.seccodehash,
                    'modid': form.modid, 'secverify': code, 'inajax': '1'}, headers=ajax_headers, safe_to_retry=True)
                if is_captcha_check_success(check_response.text):
                    return LoginParameters(form.loginhash, form.formhash, form.seccodehash, code, form.modid)
            if attempt + 1 < attempts:
                self._sleep(0.5)
        raise CaptchaRecognitionError('验证码识别或服务端预校验未通过')

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
            response = self._send_request('GET', home_url, safe_to_retry=True)
            formhash = _extract_formhash(response.text)

            if formhash:
                self.formhash = formhash
                log_success("FormHash 获取成功", self.account_name)
                return True
            else:
                log_error("FormHash 获取失败", self.account_name)
                return False
        except Exception as e:
            log_error(f"FormHash 获取异常: {e}", self.account_name)
            return False

