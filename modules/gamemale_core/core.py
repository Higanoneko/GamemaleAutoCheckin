#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gamemale 每日任务自动化 - 核心共享模块

包含所有业务逻辑，供 gamemale_daily.py (GitHub Actions) 和
gamemale_daily_ql.py (青龙面板) 共同使用。
"""

import re
import json
import time
import random
import threading
from typing import Optional, Tuple, List, Dict, Set, Any, Callable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup


# ============== 常量 ==============
BASE_URL = "https://www.gamemale.com"
DEFAULT_TIMEOUT = 30  # 请求超时时间（秒）
MAX_LOGIN_RETRIES = 8  # 密码登录最大重试次数
BLOG_INTERACTION_TARGET = 10  # 日志互动目标次数
BLOG_MAX_PAGES = 10  # 日志扫描最大页数
BLOOD_EXCHANGE_THRESHOLD = 34  # 血液兑换阈值
POKE_TARGET_COUNT = 3  # 打招呼目标用户数

# OCR 可用性
try:
    import ddddocr
    DDDDOCR_AVAILABLE = True
except ImportError:
    DDDDOCR_AVAILABLE = False


# ============== 停止控制器 ==============
class StopController:
    """
    基于 threading.Event 的优雅停止控制器。

    用 event.wait(timeout) 替代 time.sleep(timeout)，当收到停止信号时
    event 被 set()，wait() 立即返回，实现可中断的等待。
    """

    def __init__(self):
        self._stop_event = threading.Event()

    def request_stop(self):
        """请求停止，所有 interruptible_sleep 立即唤醒"""
        self._stop_event.set()

    def is_stopped(self) -> bool:
        """检查是否已请求停止"""
        return self._stop_event.is_set()

    def interruptible_sleep(self, seconds: float):
        """
        可中断的等待。等效于 time.sleep(seconds)，
        但当 request_stop() 被调用时会立即返回。
        """
        self._stop_event.wait(timeout=seconds)

    def reset(self):
        """重置停止状态"""
        self._stop_event.clear()


# 全局停止控制器（供青龙版信号处理使用）
stop_controller = StopController()


# ============== 日志工具 ==============
def log_info(msg: str, account_name: str = ""):
    prefix = f"[{account_name}] " if account_name else ""
    print(f"{prefix}{msg}")


def log_success(msg: str, account_name: str = ""):
    log_info(f"✅ {msg}", account_name)


def log_error(msg: str, account_name: str = ""):
    log_info(f"❌ {msg}", account_name)


def log_warning(msg: str, account_name: str = ""):
    log_info(f"⚠️ {msg}", account_name)


def log_section(title: str, account_name: str = ""):
    log_info(f"\n{'='*20} {title} {'='*20}", account_name)


# ============== HTTP Session 工厂 ==============
def create_session() -> requests.Session:
    """创建带有重试策略和默认头的 requests Session"""
    session = requests.Session()

    # 重试策略: 连接错误和 5xx 状态码最多重试 3 次
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET", "POST", "HEAD"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': f'{BASE_URL}/forum.php',
    })

    return session


# ============== 日志互动功能 ==============
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


# ============== 主自动化类 ==============
class GamemaleAutomation:
    """Gamemale 自动化任务客户端"""

    def __init__(
        self,
        account_config: Dict[str, Any],
        account_index: int = 0,
        controller: Optional[StopController] = None,
        save_cookie_callback: Optional[Callable[['GamemaleAutomation'], bool]] = None,
    ):
        """
        Args:
            account_config: 单个账户配置字典
            account_index: 账户在配置列表中的索引
            controller: 停止控制器，用于优雅中断
            save_cookie_callback: 保存 Cookie 的回调，由各入口脚本提供
        """
        self.config = account_config
        self.account_index = account_index
        self.account_name = account_config.get("username", f"账户{account_index+1}")
        self.session = create_session()
        self.formhash: Optional[str] = None
        self.is_logged_in = False
        self._controller = controller
        self._save_cookie_callback = save_cookie_callback

        # 延迟初始化 OCR
        self._ocr = None

    def _is_stopped(self) -> bool:
        """检查是否已请求停止"""
        return self._controller is not None and self._controller.is_stopped()

    def _sleep(self, seconds: float):
        """可中断的等待"""
        if self._controller:
            self._controller.interruptible_sleep(seconds)
        else:
            time.sleep(seconds)

    def _init_ocr(self) -> bool:
        """延迟初始化 OCR"""
        if self._ocr is None and DDDDOCR_AVAILABLE:
            self._ocr = ddddocr.DdddOcr(show_ad=False)
        return self._ocr is not None

    def _send_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """统一的请求发送方法，带默认超时"""
        kwargs.setdefault('timeout', DEFAULT_TIMEOUT)
        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            if e.response is not None:
                log_error(f"请求失败: {url}, 状态码: {e.response.status_code}", self.account_name)
            else:
                log_error(f"请求失败: {url}, 错误: {e}", self.account_name)
            raise

    def _extract_cookies_string(self) -> str:
        """从当前 session 提取 cookie 字符串"""
        cookies = []
        for cookie in self.session.cookies:
            if cookie.domain and 'gamemale.com' in cookie.domain:
                cookies.append(f"{cookie.name}={cookie.value}")
        return '; '.join(cookies)

    # ============== 登录 ==============
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

        try:
            test_url = f'{BASE_URL}/home.php?mod=space&do=profile'
            response = self.session.get(test_url, allow_redirects=False, timeout=DEFAULT_TIMEOUT)

            if response.status_code == 200:
                if '登录' in response.text and '请先登录' in response.text:
                    return False
                if '我的资料' in response.text or '个人空间' in response.text or 'uid=' in response.text:
                    return True
            return False
        except Exception as e:
            log_warning(f"Cookie登录验证出错: {e}", self.account_name)
            return False

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
                    return True
                else:
                    error_match = re.search(r'<!\[CDATA\[(.*?)(?:<script|\]\])', login_response.text)
                    raise ValueError(error_match.group(1).strip() if error_match else "未知登录错误")

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

        html_content_match = re.search(r'<!\[CDATA\[(.*)\]\]>', response.text, re.DOTALL)
        if not html_content_match:
            raise ValueError("无法从登录弹窗响应中提取HTML内容")
        html_content = html_content_match.group(1)

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

        seccodehash_match = re.search(r"updateseccode\('([a-zA-Z0-9]+)'", html_content)
        if not seccodehash_match:
            raise ValueError("未找到seccodehash")
        seccodehash = seccodehash_match.group(1)

        js_url = f"{BASE_URL}/misc.php?mod=seccode&action=update&idhash={seccodehash}&inajax=1"
        js_response = self._send_request('GET', js_url, headers=ajax_headers)
        img_path_match = re.search(r'src="([^"]+mod=seccode[^"]+)"', js_response.text)
        if not img_path_match:
            raise ValueError("无法解析验证码URL")

        img_path = img_path_match.group(1).replace('&amp;', '&')
        img_url = f"{BASE_URL}/{img_path}"
        img_response = self._send_request('GET', img_url)

        seccode_verify = self._recognize_captcha(img_response.content)
        if not seccode_verify:
            raise ValueError("验证码识别失败")

        return loginhash, formhash, seccodehash, seccode_verify

    def _recognize_captcha(self, image_bytes: bytes) -> Optional[str]:
        """使用 ddddocr 识别验证码"""
        try:
            res = self._ocr.classification(image_bytes)
            log_info(f"验证码识别结果: {res}", self.account_name)
            return res
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

    # ============== 任务执行 ==============
    def execute_all_tasks(self) -> Optional[str]:
        """执行所有任务并生成详细报告"""
        if not self.is_logged_in:
            log_error("未登录，无法执行任务", self.account_name)
            return None

        if not self.formhash:
            log_warning("未能获取有效的 formhash，任务可能失败", self.account_name)

        log_section("开始执行任务", self.account_name)
        task_results: Dict[str, bool] = {}

        # 基础任务
        tasks = [
            ("签到", self.quick_daily_sign),
            ("抽奖", self.quick_daily_lottery),
        ]

        for name, func in tasks:
            if self._is_stopped():
                log_warning("收到停止信号，中断任务执行", self.account_name)
                break
            log_info(f"执行任务: {name}", self.account_name)
            task_results[name] = func()
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

    # ============== 积分与兑换 ==============
    def _get_credits(self) -> Tuple[Dict[str, str], str]:
        """获取所有积分"""
        credit_page_url = f'{BASE_URL}/home.php?mod=spacecp&ac=credit&op=base'
        response = self._send_request('GET', credit_page_url)
        soup = BeautifulSoup(response.text, 'html.parser')

        credits_data: Dict[str, str] = {}
        credit_list_items = soup.select('ul.creditl li')
        for item in credit_list_items:
            text = item.get_text(" ", strip=True)
            match = re.match(r'(.+?):\s*([\d,]+\s*\S+)', text)
            if match:
                name, value = match.groups()
                value = re.sub(r'\s*[()]+\s*$', '', value.strip())
                credits_data[name.strip()] = value
        return credits_data, credit_page_url

    def get_user_credits_and_exchange(self) -> Tuple[Dict[str, str], Optional[bool]]:
        """获取用户积分并执行血液兑换"""
        log_info("获取积分并检查兑换...", self.account_name)
        exchange_status: Optional[bool] = None
        credits_data: Dict[str, str] = {}

        try:
            credits_data, credit_page_url = self._get_credits()
            log_info(f"当前积分: {credits_data}", self.account_name)

            if not self.config.get("auto_exchange", True):
                log_info("自动兑换功能已禁用", self.account_name)
                return credits_data, None

            blood_value_str = credits_data.get("血液", "0 滴").split()[0]
            blood_value = int(blood_value_str)

            if blood_value > BLOOD_EXCHANGE_THRESHOLD:
                password = self.config.get("password")
                if not password:
                    log_info(
                        f"血液 ({blood_value}) > {BLOOD_EXCHANGE_THRESHOLD}，但未配置密码，无法兑换",
                        self.account_name,
                    )
                    return credits_data, None

                log_info(f"血液 ({blood_value}) > {BLOOD_EXCHANGE_THRESHOLD}，尝试兑换1旅程...", self.account_name)
                exchange_status = False

                payload = {
                    'formhash': self.formhash,
                    'exchangeamount': '1',
                    'fromcredits': '3',
                    'tocredits': '1',
                    'exchangesubmit': 'true',
                    'password': password,
                }
                exchange_url = (
                    f'{BASE_URL}/home.php?mod=spacecp&ac=credit'
                    f'&op=exchange&handlekey=credit&inajax=1'
                )
                headers = {'X-Requested-With': 'XMLHttpRequest', 'Referer': credit_page_url}

                post_response = self._send_request('POST', exchange_url, data=payload, headers=headers)

                if '积分操作成功' in post_response.text:
                    log_success("血液兑换旅程成功！", self.account_name)
                    exchange_status = True
                    credits_data, _ = self._get_credits()
                else:
                    error_msg_match = re.search(r"errorhandle_credit\('([^']+)'", post_response.text)
                    error_text = error_msg_match.group(1) if error_msg_match else "未知错误"
                    log_error(f"血液兑换失败: {error_text}", self.account_name)
            else:
                log_info(
                    f"血液 ({blood_value}) 不足{BLOOD_EXCHANGE_THRESHOLD}，不执行兑换",
                    self.account_name,
                )

        except Exception as e:
            log_error(f"获取积分或兑换出错: {e}", self.account_name)

        return credits_data, exchange_status

    def get_daily_task_summary(self) -> List[Dict[str, str]]:
        """获取任务总次数统计"""
        task_data: List[Dict[str, str]] = []

        try:
            rewards_url = (
                f'{BASE_URL}/home.php?mod=spacecp&ac=credit'
                f'&op=log&suboperation=creditrulelog'
            )
            response = self._send_request('GET', rewards_url)

            soup = BeautifulSoup(response.text, 'html.parser')
            table = soup.find('table', class_='dt')
            if not table:
                return task_data

            for row in table.find_all('tr')[1:]:
                columns = row.find_all('td')
                if len(columns) >= 3:
                    task_name = columns[0].get_text(strip=True)
                    total_count = columns[1].get_text(strip=True)
                    last_reward_time = columns[-1].get_text(strip=True)
                    task_data.append({
                        "name": task_name,
                        "count": total_count,
                        "time": last_reward_time,
                    })

        except Exception as e:
            log_warning(f"获取任务统计出错: {e}", self.account_name)

        return task_data

    # ============== 报告生成 ==============
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

        if task_summary_data:
            message += "任务总次数统计:\n"
            for task in task_summary_data:
                message += f"  - {task['name']}: {task['count']} 次\n"
            message += "\n"

        return message
