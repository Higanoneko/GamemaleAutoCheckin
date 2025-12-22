#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 青龙面板任务配置
# new Env('GameMale 自动签到')
# cron 0 8 * * *
"""
Gamemale 每日任务自动化脚本 - 青龙面板适配版
支持多账户运行

配置方式：在青龙面板「配置文件」中编辑 GameMale_Config.yaml
首次运行会自动创建配置文件模板
"""

import requests
import re
import json
import time
import random
import os
import sys
from pathlib import Path

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False
    print("警告: PyYAML 未安装，请在青龙面板依赖管理中添加 pyyaml")

# 尝试导入青龙面板通知模块
try:
    from notify import send as ql_send
    QL_NOTIFY_AVAILABLE = True
except ImportError:
    try:
        from sendNotify import send as ql_send
        QL_NOTIFY_AVAILABLE = True
    except ImportError:
        QL_NOTIFY_AVAILABLE = False

# 尝试导入ddddocr（验证码识别）
try:
    import ddddocr
    DDDDOCR_AVAILABLE = True
except ImportError:
    DDDDOCR_AVAILABLE = False
    print("警告: ddddocr 未安装，密码登录功能将不可用")

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("错误: beautifulsoup4 未安装，请在青龙面板依赖管理中添加 beautifulsoup4")
    sys.exit(1)


# ============== 日志工具 ==============
def log_info(msg, account_name=""):
    prefix = f"[{account_name}] " if account_name else ""
    print(f"{prefix}{msg}")

def log_success(msg, account_name=""):
    log_info(f"✅ {msg}", account_name)

def log_error(msg, account_name=""):
    log_info(f"❌ {msg}", account_name)

def log_warning(msg, account_name=""):
    log_info(f"⚠️ {msg}", account_name)

def log_section(title, account_name=""):
    log_info(f"\n{'='*20} {title} {'='*20}", account_name)


# ============== 配置文件路径 ==============
CONFIG_FILE_NAME = "GameMale_Config.yaml"

# 青龙面板可能的配置目录
QL_CONFIG_PATHS = [
    "/ql/data/config",      # 新版青龙
    "/ql/config",           # 旧版青龙
    Path(__file__).parent,  # 脚本所在目录
]

# 配置文件模板 (YAML格式，支持注释)
CONFIG_TEMPLATE = """# GameMale 自动签到配置文件
# 支持多账户，每个账户可以单独配置

accounts:
  # 账户1
  - cookie: ""           # 登录Cookie（从浏览器F12获取）
    username: ""         # 用户名
    password: ""         # 密码（用于自动登录和血液兑换）
    notify_enabled: true # 是否发送通知（true/false）

  # 账户2（示例，取消注释并填写信息即可启用）
  # - cookie: ""
  #   username: ""
  #   password: ""
  #   notify_enabled: false
"""


def get_ql_config_dir():
    """获取青龙面板配置目录"""
    for path in QL_CONFIG_PATHS:
        path = Path(path)
        if path.exists() and path.is_dir():
            return path
    return Path(__file__).parent


def get_config_file_path():
    """获取配置文件完整路径"""
    config_dir = get_ql_config_dir()
    return config_dir / CONFIG_FILE_NAME


def create_config_template():
    """创建配置文件模板"""
    config_path = get_config_file_path()

    if config_path.exists():
        return False

    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write(CONFIG_TEMPLATE)
        return True
    except Exception as e:
        print(f"创建配置文件失败: {e}")
        return False


def load_config_file():
    """从配置文件加载账户"""
    if not YAML_AVAILABLE:
        print("错误: PyYAML 未安装，无法加载配置文件")
        return None

    config_path = get_config_file_path()

    if not config_path.exists():
        return None

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        if not config:
            return None

        accounts = config.get("accounts", [])

        if accounts:
            print(f"从配置文件加载了 {len(accounts)} 个账户: {config_path}")
            return accounts
        return None

    except yaml.YAMLError as e:
        print(f"配置文件格式错误: {e}")
        print(f"请检查配置文件: {config_path}")
        return None
    except Exception as e:
        print(f"读取配置文件失败: {e}")
        return None


# ============== 配置加载 ==============
def load_accounts():
    """
    加载账户配置
    优先级:
    1. 青龙配置文件 GameMale_Config.json
    2. 环境变量 GAMEMALE_ACCOUNTS
    3. 环境变量 GAMEMALE_COOKIE
    """
    accounts = []

    # 1. 优先从配置文件加载
    file_accounts = load_config_file()
    if file_accounts:
        return file_accounts

    # 2. 使用 GAMEMALE_ACCOUNTS 环境变量
    accounts_json = os.environ.get("GAMEMALE_ACCOUNTS", "").strip()
    if accounts_json:
        try:
            accounts = json.loads(accounts_json)
            if isinstance(accounts, dict):
                accounts = [accounts]
            print(f"从环境变量 GAMEMALE_ACCOUNTS 加载了 {len(accounts)} 个账户")
            return accounts
        except json.JSONDecodeError as e:
            print(f"环境变量 GAMEMALE_ACCOUNTS 格式无效: {e}")

    # 3. 使用 GAMEMALE_COOKIE 环境变量（简单格式）
    cookie_str = os.environ.get("GAMEMALE_COOKIE", "").strip()
    if cookie_str:
        if '\n' in cookie_str:
            cookies = [c.strip() for c in cookie_str.split('\n') if c.strip()]
        elif '&' in cookie_str and len(cookie_str.split('&')) > 1:
            # 检查是否是多账户分隔
            parts = cookie_str.split('&')
            if len(parts[1]) > 10 and 'TVj0' not in parts[1][:10]:
                cookies = [c.strip() for c in parts if c.strip()]
            else:
                cookies = [cookie_str]
        else:
            cookies = [cookie_str]

        for i, cookie in enumerate(cookies):
            accounts.append({
                "cookie": cookie,
                "username": f"账户{i+1}",
                "password": "",
                "auto_exchange_enabled": True
            })
        print(f"从环境变量 GAMEMALE_COOKIE 加载了 {len(accounts)} 个账户")
        return accounts

    # 4. 兼容旧格式
    config_json = os.environ.get("APP_CONFIG_JSON", "").strip()
    if config_json:
        try:
            config = json.loads(config_json)
            gamemale_config = config.get("gamemale", {})
            if gamemale_config:
                accounts.append(gamemale_config)
                print("从环境变量 APP_CONFIG_JSON 加载了 1 个账户")
                return accounts
        except json.JSONDecodeError:
            pass

    return accounts


# ============== 通知功能 ==============
def send_notification(title, content):
    """发送通知，优先使用青龙面板通知"""
    if QL_NOTIFY_AVAILABLE:
        try:
            ql_send(title, content)
            print("青龙面板通知发送成功")
        except Exception as e:
            print(f"青龙面板通知发送失败: {e}")
    else:
        # 回退到控制台输出
        print(f"\n{'='*50}")
        print(f"【{title}】")
        print(content)
        print('='*50)


# ============== 日志互动功能 ==============
def interact_with_blogs_regex(session, account_name, target_interactions=10, max_pages_to_scan=10):
    """持续查找并与日志互动，直到达到目标次数"""
    log_section(f"日志互动 (目标: {target_interactions}次)", account_name)

    successful_user_ids = set()
    processed_user_ids = set()
    processed_blog_urls = set()

    page_num = 1
    while len(successful_user_ids) < target_interactions and page_num <= max_pages_to_scan:
        log_info(f"扫描第 {page_num}/{max_pages_to_scan} 页...", account_name)

        try:
            base_blog_list_url = 'https://www.gamemale.com/home.php?mod=space&do=blog&view=all'
            current_url = f"{base_blog_list_url}&page={page_num}"
            response = session.get(current_url)
            response.raise_for_status()

            href_matches = re.findall(r'href="([^"]*blog-\d+-\d+\.html[^"]*)"', response.text)
            if not href_matches:
                log_info("当前页未找到日志链接，停止扫描", account_name)
                break

            new_blogs_found_on_page = 0
            for href in href_matches:
                full_url = href if href.startswith('http') else "https://www.gamemale.com/" + href
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

                    page_response = session.get(full_url)
                    page_response.raise_for_status()
                    page_text = page_response.text

                    if "您不能访问当前内容" in page_text or "指定的主题不存在或已被删除或正在被审核" in page_text:
                        continue

                    shock_button = BeautifulSoup(page_text, 'html.parser').select_one('a[id*="click_blogid_"][id$="_1"]')
                    if not shock_button:
                        continue

                    click_url_raw = shock_button.get('href')
                    click_url = (click_url_raw.replace('&amp;', '&') + '&inajax=1') if '&inajax=1' not in click_url_raw else click_url_raw.replace('&amp;', '&')
                    if not click_url.startswith('http'):
                        click_url = "https://www.gamemale.com/" + click_url.lstrip('/')

                    ajax_headers = {'Referer': full_url, 'X-Requested-With': 'XMLHttpRequest'}
                    click_response = session.get(click_url, headers=ajax_headers)
                    response_text = click_response.text.strip()

                    if 'succeed' in response_text or '表态成功' in response_text:
                        log_success(f"震惊成功 (UID:{uid}) [{len(successful_user_ids)+1}/{target_interactions}]", account_name)
                        successful_user_ids.add(uid)

                    time.sleep(random.uniform(2, 5))

                    if len(successful_user_ids) >= target_interactions:
                        break

                except Exception as e:
                    pass

            if len(successful_user_ids) >= target_interactions:
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

    def __init__(self, account_config, account_index=0):
        self.config = account_config
        self.account_index = account_index
        self.account_name = account_config.get("username", f"账户{account_index+1}")
        self.session = requests.Session()
        self.formhash = None
        self.is_logged_in = False

        # 仅在需要密码登录时初始化OCR
        self.ocr = None

        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://www.gamemale.com/forum.php',
        })

    def _init_ocr(self):
        """延迟初始化OCR"""
        if self.ocr is None and DDDDOCR_AVAILABLE:
            self.ocr = ddddocr.DdddOcr(show_ad=False)
        return self.ocr is not None

    def _send_request(self, method, url, **kwargs):
        """统一的请求发送方法"""
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

    def _extract_cookies_string(self):
        """从当前 session 提取 cookie 字符串"""
        cookies = []
        for cookie in self.session.cookies:
            if cookie.domain and 'gamemale.com' in cookie.domain:
                cookies.append(f"{cookie.name}={cookie.value}")
        return '; '.join(cookies)

    def _save_cookie_to_config(self):
        """将当前 session 的 cookie 保存到配置文件"""
        try:
            config_path = get_config_file_path()
            if not config_path.exists():
                log_warning("配置文件不存在，无法保存 Cookie", self.account_name)
                return False

            # 读取当前配置
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            accounts = config.get("accounts", [])
            if self.account_index >= len(accounts):
                log_warning("账户索引超出范围，无法保存 Cookie", self.account_name)
                return False

            # 提取并更新 cookie
            new_cookie = self._extract_cookies_string()
            if not new_cookie:
                log_warning("未能提取到有效的 Cookie", self.account_name)
                return False

            accounts[self.account_index]["cookie"] = new_cookie
            config["accounts"] = accounts

            # 写回配置文件
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)

            log_success("Cookie 已自动更新到配置文件", self.account_name)
            return True

        except Exception as e:
            log_warning(f"保存 Cookie 失败: {e}", self.account_name)
            return False

    def login(self):
        """统一的登录管理"""
        log_section("登录流程", self.account_name)

        login_successful = False

        # 优先尝试Cookie登录
        if self.config.get("cookie"):
            if self._login_with_cookie():
                log_success("Cookie 登录成功", self.account_name)
                login_successful = True
            else:
                # Cookie登录失败，清除session中的cookies，避免干扰密码登录
                self.session.cookies.clear()
                log_info("Cookie 已过期或无效，尝试密码登录", self.account_name)

        # Cookie登录失败则尝试密码登录
        if not login_successful and self.config.get("username") and self.config.get("password"):
            if self._login_with_password():
                log_success("密码登录成功", self.account_name)
                # 密码登录成功后自动保存 Cookie 到配置文件
                self._save_cookie_to_config()
                login_successful = True

        if login_successful:
            self.is_logged_in = True
            self.get_and_store_formhash()
        else:
            log_error("所有登录方式均失败", self.account_name)

        return self.is_logged_in

    def _login_with_cookie(self):
        """使用Cookie尝试登录"""
        cookie_string = self.config.get("cookie")
        if not cookie_string:
            return False

        for cookie in cookie_string.split(';'):
            cookie = cookie.strip()
            if '=' in cookie:
                name, value = cookie.split('=', 1)
                self.session.cookies.set(name.strip(), value.strip(), domain='www.gamemale.com')

        try:
            test_url = 'https://www.gamemale.com/home.php?mod=space&do=profile'
            response = self.session.get(test_url, allow_redirects=False)

            # 只要页面能访问且不需要登录就认为成功
            if response.status_code == 200:
                # 检查是否是登录页面或需要登录的提示
                if '登录' in response.text and '请先登录' in response.text:
                    return False
                # 检查是否有用户相关内容（说明已登录）
                if '我的资料' in response.text or '个人空间' in response.text or 'uid=' in response.text:
                    return True
            return False
        except Exception as e:
            log_warning(f"Cookie登录验证出错: {e}", self.account_name)
            return False

    def _login_with_password(self):
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

        max_retries = 8
        for attempt in range(max_retries):
            log_info(f"尝试密码登录 ({attempt + 1}/{max_retries})...", self.account_name)

            try:
                loginhash, formhash, seccodehash, seccode_verify = self._get_login_parameters()

                # 检测是否已经登录
                if loginhash == "ALREADY_LOGGED_IN":
                    return True

                if not all([loginhash, formhash, seccodehash, seccode_verify]):
                    raise ValueError("获取登录参数失败")

                login_url = f"https://www.gamemale.com/member.php?mod=logging&action=login&loginsubmit=yes&handlekey=login&loginhash={loginhash}&inajax=1"
                payload = {
                    'formhash': formhash,
                    'referer': 'https://www.gamemale.com/forum.php',
                    'loginfield': 'username',
                    'username': username,
                    'password': password,
                    'questionid': self.config.get("questionid", "0"),
                    'answer': self.config.get("answer", ""),
                    'seccodehash': seccodehash,
                    'seccodeverify': seccode_verify
                }

                login_response = self._send_request('POST', login_url, data=payload, headers={'X-Requested-With': 'XMLHttpRequest'})
                if 'succeed' in login_response.text or '欢迎您回来' in login_response.text:
                    return True
                else:
                    error_match = re.search(r'<!\[CDATA\[(.*?)(?:<script|\]\])', login_response.text)
                    raise ValueError(error_match.group(1).strip() if error_match else "未知登录错误")

            except Exception as e:
                log_warning(f"登录尝试失败: {e}", self.account_name)
                if attempt < max_retries - 1:
                    time.sleep(random.uniform(2, 5))

        return False

    def _get_login_parameters(self):
        """获取登录所需的动态参数和验证码"""
        ajax_headers = {'X-Requested-With': 'XMLHttpRequest'}
        login_popup_url = 'https://www.gamemale.com/member.php?mod=logging&action=login&infloat=yes&handlekey=login&inajax=1'
        response = self._send_request('GET', login_popup_url, headers=ajax_headers)

        html_content_match = re.search(r'<!\[CDATA\[(.*)\]\]>', response.text, re.DOTALL)
        if not html_content_match:
            raise ValueError("无法从登录弹窗响应中提取HTML内容")
        html_content = html_content_match.group(1)

        # 检测是否已经登录成功（服务器返回欢迎消息而非登录表单）
        if '欢迎您回来' in html_content or 'succeedhandle_login' in html_content:
            log_info("检测到已登录状态，无需重新登录", self.account_name)
            # 返回特殊标记表示已登录
            return "ALREADY_LOGGED_IN", None, None, None

        soup = BeautifulSoup(html_content, 'html.parser')

        # 查找登录表单
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

        js_url = f"https://www.gamemale.com/misc.php?mod=seccode&action=update&idhash={seccodehash}&inajax=1"
        js_response = self._send_request('GET', js_url, headers=ajax_headers)
        img_path_match = re.search(r'src="([^"]+mod=seccode[^"]+)"', js_response.text)
        if not img_path_match:
            raise ValueError("无法解析验证码URL")

        img_path = img_path_match.group(1).replace('&amp;', '&')
        img_url = "https://www.gamemale.com/" + img_path
        img_response = self._send_request('GET', img_url)

        seccode_verify = self._recognize_captcha_ddddocr(img_response.content)
        if not seccode_verify:
            raise ValueError("验证码识别失败")

        return loginhash, formhash, seccodehash, seccode_verify

    def _recognize_captcha_ddddocr(self, image_bytes):
        """使用 ddddocr 识别验证码"""
        try:
            res = self.ocr.classification(image_bytes)
            log_info(f"验证码识别结果: {res}", self.account_name)
            return res
        except Exception as e:
            log_warning(f"验证码识别失败: {e}", self.account_name)
            return None

    def get_and_store_formhash(self):
        """获取并存储 formhash"""
        log_info("获取 FormHash...", self.account_name)
        try:
            home_url = 'https://www.gamemale.com/home.php?mod=spacecp'
            response = self._send_request('GET', home_url)
            formhash_match = re.search(r'formhash" value="([a-f0-9]+)"', response.text) or \
                             re.search(r'formhash=([a-f0-9]+)', response.text) or \
                             re.search(r'"formhash":"([a-f0-9]+)"', response.text)

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

    def execute_all_tasks(self):
        """执行所有任务并生成详细报告"""
        if not self.is_logged_in:
            log_error("未登录，无法执行任务", self.account_name)
            return None

        if not self.formhash:
            log_warning("未能获取有效的 formhash，任务可能失败", self.account_name)

        log_section("开始执行任务", self.account_name)
        task_results = {}

        # 基础任务
        tasks = [
            ("签到", self.quick_daily_sign),
            ("抽奖", self.quick_daily_lottery),
        ]

        for name, func in tasks:
            log_info(f"执行任务: {name}", self.account_name)
            task_results[name] = func()
            time.sleep(random.uniform(1, 2))

        # 日志互动
        log_info("执行任务: 震惊互动", self.account_name)
        successful_uids, processed_uids = interact_with_blogs_regex(self.session, self.account_name, 10)
        task_results["震惊互动"] = len(successful_uids) > 0

        if processed_uids:
            target_uids = processed_uids[:3]
            log_info(f"选择 {len(target_uids)} 个用户进行空间访问和打招呼", self.account_name)

            log_info("执行任务: 空间访问", self.account_name)
            task_results["空间访问"] = self.quick_visit_spaces(target_uids)

            log_info("执行任务: 打招呼", self.account_name)
            task_results["打招呼"] = self.quick_poke_users(target_uids)

        log_info("收集统计信息", self.account_name)
        user_credits, exchange_result = self.get_user_credits_and_exchange()
        if exchange_result is not None:
            task_results["血液兑换"] = exchange_result

        task_summary_data = self.get_daily_task_summary()

        report_message = self.generate_detailed_report(
            task_results,
            user_credits=user_credits,
            task_summary_data=task_summary_data
        )

        success_count = sum(1 for result in task_results.values() if result)
        total_count = len(task_results)
        log_success(f"任务完成: {success_count}/{total_count} 成功", self.account_name)

        return report_message

    def quick_daily_sign(self):
        """快速签到"""
        try:
            if not self.formhash:
                return False
            url = f"https://www.gamemale.com/k_misign-sign.html?operation=qiandao&format=button&formhash={self.formhash}"
            response = self._send_request('GET', url, headers={'X-Requested-With': 'XMLHttpRequest'})
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

    def quick_daily_lottery(self):
        """快速抽奖"""
        try:
            if not self.formhash:
                return False
            url = f"https://www.gamemale.com/plugin.php?id=it618_award:ajax&ac=getaward&formhash={self.formhash}&_={int(time.time() * 1000)}"
            response = self._send_request('GET', url, headers={'X-Requested-With': 'XMLHttpRequest'})

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

    def quick_visit_spaces(self, user_ids):
        """快速空间访问"""
        if not user_ids:
            return True
        success = 0
        for uid in user_ids:
            try:
                url = f"https://www.gamemale.com/space-uid-{uid}.html"
                if self.session.head(url, allow_redirects=True).status_code == 200:
                    success += 1
                time.sleep(1)
            except:
                pass
        log_info(f"空间访问: {success}/{len(user_ids)} 成功", self.account_name)
        return success > 0

    def quick_poke_users(self, user_ids):
        """对一组用户执行"打招呼"操作"""
        if not user_ids:
            return True
        success_count = 0
        for uid in user_ids:
            try:
                get_url = f"https://www.gamemale.com/home.php?mod=spacecp&ac=poke&op=send&uid={uid}&inajax=1"
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
                    action_url = f"https://www.gamemale.com/{action_url.lstrip('/')}"

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
                    'Referer': f'https://www.gamemale.com/space-uid-{uid}.html'
                })

                post_response = self._send_request('POST', action_url, data=payload, headers=final_headers)

                if '已发送' in post_response.text and '下次访问时会收到通知' in post_response.text:
                    success_count += 1
            except Exception as e:
                pass
            finally:
                time.sleep(random.uniform(2, 4))

        log_info(f"打招呼完成: {success_count}/{len(user_ids)} 成功", self.account_name)
        return success_count > 0

    def _get_credits(self):
        """辅助函数：获取所有积分"""
        credit_page_url = 'https://www.gamemale.com/home.php?mod=spacecp&ac=credit&op=base'
        response = self._send_request('GET', credit_page_url)
        soup = BeautifulSoup(response.text, 'html.parser')

        credits_data = {}
        credit_list_items = soup.select('ul.creditl li')
        for item in credit_list_items:
            text = item.get_text(" ", strip=True)
            match = re.match(r'(.+?):\s*([\d,]+\s*\S+)', text)
            if match:
                name, value = match.groups()
                credits_data[name.strip()] = value.strip()
        return credits_data, credit_page_url

    def get_user_credits_and_exchange(self):
        """获取用户积分并执行血液兑换"""
        log_info("获取积分并检查兑换...", self.account_name)
        exchange_status = None
        credits_data = {}

        try:
            credits_data, credit_page_url = self._get_credits()
            log_info(f"当前积分: {credits_data}", self.account_name)

            if not self.config.get("auto_exchange_enabled", True):
                log_info("自动兑换功能已禁用", self.account_name)
                return credits_data, None

            blood_value_str = credits_data.get("血液", "0 滴").split()[0]
            blood_value = int(blood_value_str)

            if blood_value > 34:
                password = self.config.get("password")
                if not password:
                    log_info(f"血液 ({blood_value}) > 34，但未配置密码，无法兑换", self.account_name)
                    return credits_data, None

                log_info(f"血液 ({blood_value}) > 34，尝试兑换1旅程...", self.account_name)
                exchange_status = False

                payload = {
                    'formhash': self.formhash,
                    'exchangeamount': '1',
                    'fromcredits': '3',
                    'tocredits': '1',
                    'exchangesubmit': 'true',
                    'password': password
                }
                exchange_url = 'https://www.gamemale.com/home.php?mod=spacecp&ac=credit&op=exchange&handlekey=credit&inajax=1'
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
                log_info(f"血液 ({blood_value}) 不足34，不执行兑换", self.account_name)

        except Exception as e:
            log_error(f"获取积分或兑换出错: {e}", self.account_name)

        return credits_data, exchange_status

    def get_daily_task_summary(self):
        """获取任务总次数统计"""
        task_data = []

        try:
            rewards_url = 'https://www.gamemale.com/home.php?mod=spacecp&ac=credit&op=log&suboperation=creditrulelog'
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
                        "time": last_reward_time
                    })

        except Exception as e:
            log_warning(f"获取任务统计出错: {e}", self.account_name)

        return task_data

    def generate_detailed_report(self, task_results, user_credits=None, task_summary_data=None):
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
        status_map = {True: "成功", False: "失败", None: "跳过"}
        sorted_tasks = sorted(task_results.items(), key=lambda item: item[0] == "血液兑换")
        for task_name, result in sorted_tasks:
            status = status_map.get(result, "未知")
            message += f"  - {task_name}: {status}\n"
        message += "\n"

        if task_summary_data:
            message += "任务总次数统计:\n"
            for task in task_summary_data:
                message += f"  - {task['name']}: {task['count']} 次\n"
            message += "\n"

        return message


# ============== 主程序 ==============
def main():
    """主程序入口"""
    print("=" * 60)
    print("Gamemale 每日任务自动化脚本 - 青龙面板版")
    print("=" * 60)

    # 加载账户配置
    accounts = load_accounts()

    if not accounts:
        # 没有找到配置，尝试创建模板
        config_path = get_config_file_path()

        if create_config_template():
            print(f"\n首次运行，已创建配置文件: {config_path}")
            print("\n请在青龙面板「配置文件」中编辑 GameMale_Config.yaml，填写账户信息后重新运行")
            print("\n配置说明 (YAML格式，支持注释):")
            print("  cookie         - 登录Cookie（从浏览器F12获取）")
            print("  username       - 用户名")
            print("  password       - 密码（用于自动登录和血液兑换）")
            print("  notify_enabled - 是否发送通知（true/false，默认true）")
        else:
            print("\n错误: 未找到配置，请在青龙配置目录创建 GameMale_Config.yaml")

        sys.exit(1)

    print(f"\n共加载 {len(accounts)} 个账户\n")

    all_reports = []
    success_accounts = 0
    failed_accounts = 0
    notify_skipped_accounts = 0  # 跳过通知的账户数

    for i, account_config in enumerate(accounts):
        account_name = account_config.get("username", f"账户{i+1}")
        notify_enabled = account_config.get("notify_enabled", True)  # 默认启用通知

        print(f"\n{'#'*60}")
        print(f"# 开始处理: {account_name} ({i+1}/{len(accounts)})")
        if not notify_enabled:
            print(f"# 通知: 已禁用")
        print(f"{'#'*60}")

        try:
            # 验证账户配置
            if not account_config.get("cookie") and not (account_config.get("username") and account_config.get("password")):
                log_error("账户配置无效: 必须提供 cookie 或 (username + password)", account_name)
                failed_accounts += 1
                continue

            # 创建自动化实例
            client = GamemaleAutomation(account_config, i)

            # 登录
            if not client.login():
                log_error("登录失败，跳过此账户", account_name)
                failed_accounts += 1
                continue

            # 执行任务
            report = client.execute_all_tasks()

            if report:
                # 只有启用通知的账户才添加到报告列表
                if notify_enabled:
                    all_reports.append(report)
                else:
                    notify_skipped_accounts += 1
                    log_info("任务完成，但通知已禁用，不发送结果", account_name)
                success_accounts += 1
                log_success("所有任务执行完成", account_name)
            else:
                failed_accounts += 1
                log_error("任务执行失败", account_name)

        except Exception as e:
            log_error(f"处理账户时发生异常: {e}", account_name)
            failed_accounts += 1

        # 多账户间延迟
        if i < len(accounts) - 1:
            delay = random.uniform(5, 10)
            print(f"\n等待 {delay:.1f} 秒后处理下一个账户...")
            time.sleep(delay)

    # 汇总报告
    print("\n" + "=" * 60)
    print("执行汇总")
    print("=" * 60)
    print(f"成功: {success_accounts} 个账户")
    print(f"失败: {failed_accounts} 个账户")
    if notify_skipped_accounts > 0:
        print(f"通知已禁用: {notify_skipped_accounts} 个账户")
    print(f"总计: {len(accounts)} 个账户")

    # 发送通知
    if all_reports:
        # 通知标题显示实际成功的账户数
        summary_title = f"Gamemale 每日任务 - {success_accounts}/{len(accounts)} 成功"
        summary_content = "\n".join(all_reports)

        print("\n" + "=" * 60)
        print("详细报告")
        print("=" * 60)
        print(summary_content)

        send_notification(summary_title, summary_content)

    # 如果有失败的账户，以非零状态退出
    if failed_accounts > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
