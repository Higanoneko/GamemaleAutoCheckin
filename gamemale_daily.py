import requests
import re
import ddddocr
from bs4 import BeautifulSoup
import base64
import json
import time
import random
import os
import sys
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False
    print("警告: PyYAML 未安装，请运行 pip install pyyaml")

# ============== 配置文件路径 ==============
CONFIG_FILE_NAME = "config.yaml"
SCRIPT_DIR = Path(__file__).parent

# 配置文件模板 (YAML格式，支持注释)
CONFIG_TEMPLATE = """# GameMale 自动签到配置文件
# 支持多账户，每个账户可以单独配置

accounts:
  # 账户1
  - cookie: ""           # 登录Cookie（从浏览器F12获取）
    username: ""         # 用户名
    password: ""         # 密码（用于自动登录和血液兑换）
    notify_enabled: true # 是否发送通知（true/false）
    auto_exchange_enabled: true  # 是否自动兑换血液

  # 账户2（示例，取消注释并填写信息即可启用）
  # - cookie: ""
  #   username: ""
  #   password: ""
  #   notify_enabled: false
  #   auto_exchange_enabled: true

# 通知配置
notification:
  enabled: false         # 是否启用通知
  type: "console"        # 通知类型: console, telegram, wechat, email

  telegram:
    bot_token: ""
    chat_id: ""

  wechat:
    webhook: ""

  email:
    smtp_server: "smtp.example.com"
    smtp_port: 587
    username: ""
    password: ""
    from: ""
    to: ""
"""


def get_config_file_path():
    """获取配置文件完整路径"""
    return SCRIPT_DIR / CONFIG_FILE_NAME


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


# --- 配置加载与通知函数 ---
def load_config():
    """
    加载配置.
    优先级:
    1. 本地 config.yaml 文件 (YAML格式，推荐)
    2. 环境变量 APP_CONFIG_JSON
    3. 本地 config.json 文件 (兼容旧格式)
    """
    # 1. 优先加载 YAML 配置文件
    config_path = get_config_file_path()
    if config_path.exists() and YAML_AVAILABLE:
        print(f"从 {config_path} 加载配置")
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except yaml.YAMLError as e:
            print(f"配置文件格式错误: {e}")
            sys.exit(1)

    # 2. 环境变量
    config_json_str = os.environ.get("APP_CONFIG_JSON")
    if config_json_str:
        print("从环境变量 APP_CONFIG_JSON 加载配置")
        try:
            config = json.loads(config_json_str)
            # 兼容旧格式：将单账户转换为多账户格式
            if "gamemale" in config and "accounts" not in config:
                config["accounts"] = [config["gamemale"]]
            return config
        except json.JSONDecodeError:
            print("环境变量 APP_CONFIG_JSON 的值不是有效的 JSON")
            sys.exit(1)

    # 3. 兼容旧的 JSON 配置文件
    if os.path.exists("config.json"):
        print("从本地 config.json 文件加载配置")
        with open("config.json", "r", encoding="utf-8") as f:
            try:
                config = json.load(f)
                # 兼容旧格式：将单账户转换为多账户格式
                if "gamemale" in config and "accounts" not in config:
                    config["accounts"] = [config["gamemale"]]
                return config
            except json.JSONDecodeError:
                print("本地 config.json 文件格式无效")
                sys.exit(1)

    # 4. 未找到配置，创建模板
    if create_config_template():
        print(f"\n首次运行，已创建配置文件: {config_path}")
        print("\n请编辑 config.yaml 填写账户信息后重新运行")
        print("\n配置说明 (YAML格式，支持注释):")
        print("  cookie         - 登录Cookie（从浏览器F12获取）")
        print("  username       - 用户名")
        print("  password       - 密码（用于自动登录和血液兑换）")
        print("  notify_enabled - 是否发送通知（true/false，默认true）")
    else:
        print("错误：未找到配置文件，请创建 config.yaml")

    sys.exit(1)

def send_notification(config, message):
    """发送通知消息"""
    notification_config = config.get("notification", {})
    if not notification_config.get("enabled", False):
        return

    notification_type = notification_config.get("type", "console")
    
    try:
        if notification_type == "telegram":
            telegram_config = notification_config.get("telegram", {})
            bot_token = telegram_config.get("bot_token")
            chat_id = telegram_config.get("chat_id")
            if bot_token and chat_id:
                telegram_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
                requests.post(telegram_url, json=payload, timeout=10)
                print("Telegram通知发送成功")

        elif notification_type == "wechat":
            wechat_config = notification_config.get("wechat", {})
            webhook = wechat_config.get("webhook")
            if webhook:
                payload = {"msgtype": "text", "text": {"content": message}}
                requests.post(webhook, json=payload, timeout=10)
                print("企业微信通知发送成功")

        elif notification_type == "email":
            email_config = notification_config.get("email", {})
            if all(k in email_config for k in ["smtp_server", "username", "password", "from", "to"]):
                msg = MIMEMultipart()
                msg['From'] = email_config["from"]
                msg['To'] = email_config["to"]
                msg['Subject'] = "Gamemale 每日任务完成统计"
                text_content = message.replace('🎉', '').replace('📊', '').replace('🎰', '').replace('📈', '').replace('📋', '').replace('•', '-')
                msg.attach(MIMEText(text_content, 'plain', 'utf-8'))
                
                server = smtplib.SMTP(email_config["smtp_server"], email_config.get("smtp_port", 587))
                server.starttls()
                server.login(email_config["username"], email_config["password"])
                server.sendmail(email_config["from"], email_config["to"], msg.as_string())
                server.quit()
                print("邮箱通知发送成功")
        else:
            print("::notice::" + message.replace('\n', '\n::notice::'))

    except Exception as e:
        print(f"发送通知时出错: {e}")

def interact_with_blogs_regex(session, target_interactions=10, max_pages_to_scan=10):
    """
    持续查找并与日志互动，直到达到目标次数。
    """
    print("::group::任务: 开始与日志互动 (目标: 10次成功)")
    
    successful_user_ids = set()
    processed_user_ids = set()
    processed_blog_urls = set()
    
    page_num = 1
    while len(successful_user_ids) < target_interactions and page_num <= max_pages_to_scan:
        print(f"🔄 正在扫描第 {page_num}/{max_pages_to_scan} 页以寻找新日志...")
        
        try:
            base_blog_list_url = 'https://www.gamemale.com/home.php?mod=space&do=blog&view=all'
            current_url = f"{base_blog_list_url}&page={page_num}"
            response = session.get(current_url)
            response.raise_for_status()
            
            href_matches = re.findall(r'href="([^"]*blog-\d+-\d+\.html[^"]*)"', response.text)
            if not href_matches:
                print("⏹️ 在当前页未找到任何日志链接，停止扫描。")
                break

            new_blogs_found_on_page = 0
            for href in href_matches:
                full_url = href if href.startswith('http') else "https://www.gamemale.com/" + href
                if full_url in processed_blog_urls:
                    continue
                
                new_blogs_found_on_page += 1
                processed_blog_urls.add(full_url)
                
                try:
                    print(f"  -> 正在处理新日志... (当前成功: {len(successful_user_ids)}/{target_interactions})")
                    uid_match = re.search(r'blog-(\d+)-', full_url)
                    if not uid_match:
                        print("    -> ✗ 无法从URL中解析UID，跳过。")
                        continue
                    
                    uid = uid_match.group(1)
                    processed_user_ids.add(uid)
                    
                    page_response = session.get(full_url)
                    page_response.raise_for_status()
                    page_text = page_response.text
                    
                    if "您不能访问当前内容" in page_text or "指定的主题不存在或已被删除或正在被审核" in page_text:
                        print(f"    -> ✗ 无法访问：日志有隐私设置或已删除。 (作者UID: {uid})")
                        continue

                    shock_button = BeautifulSoup(page_text, 'html.parser').select_one('a[id*="click_blogid_"][id$="_1"]')
                    if not shock_button:
                        print(f"    -> ℹ️ 已表过态或页面结构不同，跳过。 (作者UID: {uid})")
                        continue

                    click_url_raw = shock_button.get('href')
                    click_url = (click_url_raw.replace('&', '&') + '&inajax=1') if '&inajax=1' not in click_url_raw else click_url_raw.replace('&', '&')
                    if not click_url.startswith('http'):
                        click_url = "https://www.gamemale.com/" + click_url.lstrip('/')

                    ajax_headers = {'Referer': full_url, 'X-Requested-With': 'XMLHttpRequest'}
                    click_response = session.get(click_url, headers=ajax_headers)
                    response_text = click_response.text.strip()

                    if 'succeed' in response_text or '表态成功' in response_text:
                        print(f"    -> ✅ 成功点击震惊! (作者UID: {uid})")
                        successful_user_ids.add(uid)
                    elif '您已表过态' in response_text:
                        print(f"    -> ℹ️ 您已对该日志表过态，跳过。 (作者UID: {uid})")
                    else:
                        print(f"    -> ❓ 响应内容未知，跳过。 (作者UID: {uid})")

                    time.sleep(random.uniform(2, 5))

                    if len(successful_user_ids) >= target_interactions:
                        print(f"🎉 已完成 {target_interactions} 次成功互动目标！")
                        break # 跳出内层 for 循环
                
                except Exception as e:
                    print(f"    -> ✗ 处理日志 {full_url} 时出错: {e}")

            if len(successful_user_ids) >= target_interactions:
                break # 跳出外层 while 循环

            if new_blogs_found_on_page == 0:
                print("⏹️ 当前页所有日志均已处理过，停止扫描。")
                break

        except Exception as e:
            print(f"❌ 抓取第 {page_num} 页日志列表时出错: {e}")
            break # 发生严重错误时终止
            
        page_num += 1

    if page_num > max_pages_to_scan:
        print(f"⚠️ 已扫描达到最大页数 ({max_pages_to_scan}页)，但未完成目标。")

    print(f"日志互动完成。成功互动 {len(successful_user_ids)} 次，共处理 {len(processed_user_ids)} 个不同作者的日志。")
    print("::endgroup::")
    return list(successful_user_ids), list(processed_user_ids)

class GamemaleAutomation:
    """Gamemale 自动化任务客户端"""

    def __init__(self, account_config, account_index=0):
        self.config = account_config  # 单个账户配置
        self.account_index = account_index
        self.account_name = account_config.get("username", f"账户{account_index+1}")
        self.session = requests.Session()
        self.formhash = None
        self.is_logged_in = False
        self.ocr = ddddocr.DdddOcr(show_ad=False)

        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://www.gamemale.com/forum.php',
        })
    
    def _send_request(self, method, url, **kwargs):
        """统一的请求发送方法，包含错误处理和日志记录"""
        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            if e.response is not None:
                print(f"请求失败: {url}, 状态码: {e.response.status_code}")
            else:
                print(f"请求失败: {url}, 错误: {e}")
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
            # 检查配置来源
            config_json_str = os.environ.get("APP_CONFIG_JSON")
            if config_json_str:
                # 配置来自环境变量，无法自动保存
                new_cookie = self._extract_cookies_string()
                if new_cookie:
                    print("::notice::密码登录成功，新 Cookie 已生成。")
                    print(f"::notice::由于配置来自环境变量，请手动更新 Cookie: {new_cookie[:50]}...")
                return False

            config_path = "config.json"
            if not os.path.exists(config_path):
                print("::warning::配置文件不存在，无法保存 Cookie")
                return False

            # 读取当前配置
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            # 提取并更新 cookie
            new_cookie = self._extract_cookies_string()
            if not new_cookie:
                print("::warning::未能提取到有效的 Cookie")
                return False

            if "gamemale" not in config:
                config["gamemale"] = {}
            config["gamemale"]["cookie"] = new_cookie

            # 写回配置文件
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)

            print("✅ Cookie 已自动更新到配置文件")
            return True

        except Exception as e:
            print(f"::warning::保存 Cookie 失败: {e}")
            return False

    def login(self):
        """统一的登录管理"""
        print("::group::登录流程")

        login_successful = False
        if self.config.get("cookie"):
            if self._login_with_cookie():
                print("✅ Cookie 登录成功")
                login_successful = True
            else:
                # Cookie登录失败，清除session中的cookies，避免干扰密码登录
                self.session.cookies.clear()
                print("Cookie 已过期或无效，尝试密码登录")

        if not login_successful and self._login_with_password():
            print("✅ 密码登录成功")
            # 密码登录成功后自动保存 Cookie 到配置文件
            self._save_cookie_to_config()
            login_successful = True

        if login_successful:
            self.is_logged_in = True
            self.get_and_store_formhash()
        else:
            print("❌ 所有登录方式均失败")

        print("::endgroup::")
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
            print(f"::warning::Cookie登录验证过程中出错: {e}")
            return False

    def _login_with_password(self):
        """使用密码进行登录"""
        username = self.config.get("username")
        password = self.config.get("password")

        if not all([username, password]):
            print("::warning::密码登录所需信息不完整 (用户名或密码缺失)。")
            return False
        
        max_retries = 8
        for attempt in range(max_retries):
            print(f"\n尝试密码登录 ({attempt + 1}/{max_retries})...")
            
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
                print(f"登录尝试失败: {e}")
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
            print("::warning::在 _get_login_parameters 中未能从响应中提取到 CDATA 内容。")
            print(f"::debug::响应文本预览: {response.text[:500]}")
            raise ValueError("无法从登录弹窗响应中提取HTML内容。")
        html_content = html_content_match.group(1)

        # 检测是否已经登录成功（服务器返回欢迎消息而非登录表单）
        if '欢迎您回来' in html_content or 'succeedhandle_login' in html_content:
            print("检测到已登录状态，无需重新登录")
            return "ALREADY_LOGGED_IN", None, None, None

        soup = BeautifulSoup(html_content, 'html.parser')

        action_tag = soup.find('form', {'name': 'login'})
        if not action_tag or not action_tag.has_attr('action'):
             raise ValueError("未找到登录表单的action URL。")
        action_url = action_tag['action']

        loginhash_match = re.search(r'loginhash=(\w+)', action_url)
        if not loginhash_match:
            raise ValueError("未找到loginhash。")
        loginhash = loginhash_match.group(1)

        formhash_tag = soup.find('input', {'name': 'formhash'})
        if not formhash_tag or not formhash_tag.has_attr('value'):
            raise ValueError("未找到formhash。")
        formhash = formhash_tag['value']

        seccodehash_match = re.search(r"updateseccode\('([a-zA-Z0-9]+)'", html_content)
        if not seccodehash_match:
            raise ValueError("未找到seccodehash。")
        seccodehash = seccodehash_match.group(1)
        
        js_url = f"https://www.gamemale.com/misc.php?mod=seccode&action=update&idhash={seccodehash}&inajax=1"
        js_response = self._send_request('GET', js_url, headers=ajax_headers)
        img_path_match = re.search(r'src="([^"]+mod=seccode[^"]+)"', js_response.text)
        if not img_path_match:
            raise ValueError("无法解析验证码URL。")
        
        img_path = img_path_match.group(1).replace('&', '&')
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
            print(f"ddddocr 识别结果: {res}")
            return res
        except Exception as e:
            print(f"::warning::ddddocr 识别验证码失败: {e}")
            return None

    def get_and_store_formhash(self):
        """一次性获取并存储 formhash，供所有任务复用"""
        print("::group::获取全局 FormHash")
        try:
            home_url = 'https://www.gamemale.com/home.php?mod=spacecp'
            response = self._send_request('GET', home_url)
            formhash_match = re.search(r'formhash" value="([a-f0-9]+)"', response.text) or \
                             re.search(r'formhash=([a-f0-9]+)', response.text) or \
                             re.search(r'"formhash":"([a-f0-9]+)"', response.text)
            
            if formhash_match:
                self.formhash = formhash_match.group(1)
                print("✅ FormHash 获取成功")
                return True
            else:
                print("❌ FormHash 获取失败")
                return False
        except Exception as e:
            print(f"❌ FormHash 获取异常: {e}")
            return False
        finally:
            print("::endgroup::")

    def execute_all_tasks(self):
        """执行所有任务并生成详细报告"""
        if not self.is_logged_in:
            print("❌ 未登录，无法执行任务")
            return None
        
        if not self.formhash:
            print("⚠ 未能获取到有效的 formhash，任务可能失败")
        
        print("::group::开始执行任务")
        task_results = {}
        
        tasks = [
            ("签到", self.quick_daily_sign),
            ("抽奖", self.quick_daily_lottery),
        ]
        
        for name, func in tasks:
            print(f"🔄 执行任务: {name}")
            task_results[name] = func()
            time.sleep(random.uniform(1, 2))
        
        print("🔄 执行任务: 震惊互动")
        successful_uids, processed_uids = interact_with_blogs_regex(self.session, 10)
        task_results["震惊互动"] = len(successful_uids) > 0
        
        if processed_uids:
            # 根据要求，只对3个用户进行后续操作
            target_uids = processed_uids[:3]
            print(f"选择 {len(target_uids)} 个用户进行空间访问和打招呼: {target_uids}")
            
            print("🔄 执行任务: 空间访问")
            task_results["空间访问"] = self.quick_visit_spaces(target_uids)
            
            print("🔄 执行任务: 打招呼")
            task_results["打招呼"] = self.quick_poke_users(target_uids)

        print("🔄 收集统计信息")
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
        print(f"📊 任务完成: {success_count}/{total_count} 成功")
        print("::endgroup::")
        
        return report_message

    def quick_daily_sign(self):
        """快速签到"""
        print("::group::快速签到")
        try:
            if not self.formhash: return False
            url = f"https://www.gamemale.com/k_misign-sign.html?operation=qiandao&format=button&formhash={self.formhash}"
            response = self._send_request('GET', url, headers={'X-Requested-With': 'XMLHttpRequest'})
            text = response.text
            if 'succeed' in text or '签到成功' in text:
                print("✅ 签到成功")
                return True
            if '已签' in text:
                print("ℹ️ 今日已签到")
                return True
            print(f"⚠ 签到状态未知")
            return False
        except Exception as e:
            print(f"❌ 签到失败: {e}")
            return False
        finally:
            print("::endgroup::")

    def quick_daily_lottery(self):
        """快速抽奖 - 使用JSON解析"""
        print("::group::快速抽奖")
        try:
            if not self.formhash: return False
            url = f"https://www.gamemale.com/plugin.php?id=it618_award:ajax&ac=getaward&formhash={self.formhash}&_={int(time.time() * 1000)}"
            response = self._send_request('GET', url, headers={'X-Requested-With': 'XMLHttpRequest'})
            
            # 优先使用JSON解析
            try:
                res_json = response.json()
                tip_name = res_json.get("tipname")
                tip_value = res_json.get("tipvalue", "")
    
                if tip_name == "ok":
                    clean_tip_value = re.sub(r'<.*?>', '', tip_value).strip()
                    print(f"🎉 抽奖成功: {clean_tip_value}")
                    return True
                elif not tip_name: # tipname 为空字符串 ""
                    print("ℹ️ 今日已抽奖")
                    return True
                else:
                    # 捕获其他非预期的API返回情况，例如金币不足等
                    print(f"❓ 抽奖返回非预期结果: {tip_name} - {tip_value}")
                    return False
            except (ValueError, json.JSONDecodeError):
                # 如果API返回的不是有效的JSON
                print(f"❓ 抽奖结果未知，无法解析响应: {response.text[:100]}")
                return False
                
        except Exception as e:
            print(f"❌ 抽奖失败: {e}")
            return False
        finally:
            print("::endgroup::")

    def quick_visit_spaces(self, user_ids):
        """快速空间访问"""
        if not user_ids: return True
        print("::group::空间访问")
        success = 0
        for uid in user_ids:
            try:
                url = f"https://www.gamemale.com/space-uid-{uid}.html"
                if self.session.head(url, allow_redirects=True).status_code == 200:
                    success += 1
                time.sleep(1)
            except: pass
        print(f"  ✅ 空间访问: {success}/{len(user_ids)} 成功")
        print("::endgroup::")
        return success > 0

    def quick_poke_users(self, user_ids):
        """对一组用户执行“打招呼”操作"""
        if not user_ids: return True
        print("::group::打招呼")
        success_count = 0
        for uid in user_ids:
            try:
                print(f"--- 正在对 UID: {uid} 打招呼 ---")
                get_url = f"https://www.gamemale.com/home.php?mod=spacecp&ac=poke&op=send&uid={uid}&inajax=1"
                headers = {'X-Requested-With': 'XMLHttpRequest'}
                response = self._send_request('GET', get_url, headers=headers)
                
                if '今天您已经打过招呼了' in response.text:
                    print(f"ℹ️ 今天已对 UID: {uid} 打过招呼")
                    success_count += 1
                    continue

                content_match = re.search(r'<!\[CDATA\[(.*)\]\]>', response.text, re.DOTALL)
                if not content_match:
                    raise ValueError("无法从响应中提取弹窗内容")
                
                soup = BeautifulSoup(content_match.group(1), 'html.parser')
                form = soup.find('form', id=f'pokeform_{uid}')
                if not form:
                    raise ValueError("未找到打招呼表单")

                action_url_raw = form['action']
                action_url = action_url_raw.replace('&', '&')
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
                    print(f"✅ 对 UID: {uid} 打招呼成功！")
                    success_count += 1
                else:
                    print(f"❌ 对 UID: {uid} 打招呼失败")
            except Exception as e:
                print(f"❌ 对 UID: {uid} 打招呼时发生异常: {e}")
            finally:
                time.sleep(random.uniform(2, 4))
        
        print(f"📊 打招呼完成: {success_count}/{len(user_ids)} 成功")
        print("::endgroup::")
        return success_count > 0

    def _get_credits(self):
        """辅助函数：访问页面并解析返回所有积分。"""
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
        """获取用户所有积分，并根据条件执行血液兑换旅程"""
        print("::group::获取积分并检查兑换")
        exchange_status = None # None: 未执行, True: 成功, False: 失败

        try:
            # 1. 首次获取积分
            credits_data, credit_page_url = self._get_credits()
            print("首次积分获取成功:", credits_data)

            # 2. 检查并执行兑换
            if not self.config.get("auto_exchange_enabled", True):
                print("ℹ️ 自动兑换功能已禁用，跳过。")
                return credits_data, None

            blood_value_str = credits_data.get("血液", "0 滴").split()[0]
            blood_value = int(blood_value_str)

            if blood_value > 34:
                password = self.config.get("password")
                if not password:
                    print(f"ℹ️ 检测到血液 ({blood_value}) > 34，但未配置密码，无法执行兑换。")
                    return credits_data, None

                print(f"检测到血液 ({blood_value}) > 34，尝试兑换1旅程...")
                exchange_status = False # 默认为失败
                
                payload = {
                    'formhash': self.formhash,
                    'exchangeamount': '1',
                    'fromcredits': '3', # 血液
                    'tocredits': '1', # 旅程
                    'exchangesubmit': 'true',
                    'password': password
                }
                exchange_url = 'https://www.gamemale.com/home.php?mod=spacecp&ac=credit&op=exchange&handlekey=credit&inajax=1'
                headers = {'X-Requested-With': 'XMLHttpRequest', 'Referer': credit_page_url}
                
                post_response = self._send_request('POST', exchange_url, data=payload, headers=headers)
                
                # 修正：使用正确的成功标识
                if '积分操作成功' in post_response.text:
                    print("✅ 血液兑换旅程成功！")
                    exchange_status = True
                    # 刷新：兑换成功后，再次获取积分以更新数据
                    print("🔄 兑换成功，正在刷新积分...")
                    credits_data, _ = self._get_credits()
                    print("刷新后积分:", credits_data)
                else:
                    error_msg_match = re.search(r"errorhandle_credit\('([^']+)'", post_response.text)
                    if error_msg_match:
                        error_text = error_msg_match.group(1)
                    else:
                        error_text = post_response.text.strip()
                    print(f"❌ 血液兑换失败: {error_text}")

            else:
                print(f"血液 ({blood_value}) 不足34，不执行兑换。")

        except Exception as e:
            print(f"❌ 获取积分或执行兑换时出错: {e}")
        finally:
            print("::endgroup::")
            
        return credits_data, exchange_status

    def get_daily_task_summary(self):
        """获取任务总次数统计"""
        print("::group::获取任务总次数统计")
        task_data = []
        
        try:
            rewards_url = 'https://www.gamemale.com/home.php?mod=spacecp&ac=credit&op=log&suboperation=creditrulelog'
            response = self._send_request('GET', rewards_url)
            
            soup = BeautifulSoup(response.text, 'html.parser')
            table = soup.find('table', class_='dt')
            if not table:
                print("未找到任务统计表格")
                return task_data

            print("任务总次数:")
            for row in table.find_all('tr')[1:]:
                columns = row.find_all('td')
                if len(columns) >= 3: # 确保有足够列
                    task_name = columns[0].get_text(strip=True)
                    total_count = columns[1].get_text(strip=True)
                    last_reward_time = columns[-1].get_text(strip=True) # 最后一列
                    task_data.append({
                        "name": task_name,
                        "count": total_count,
                        "time": last_reward_time
                    })
                    print(f"  - {task_name}: {total_count} 次 (最后: {last_reward_time})")
                    
        except Exception as e:
            print(f"获取任务总次数时出错: {e}")
        finally:
            print("::endgroup::")
        
        return task_data

    def generate_detailed_report(self, task_results, user_credits=None, task_summary_data=None):
        """生成详细的统计报告"""
        message = f"【{self.account_name}】 Gamemale 每日任务完成统计\n\n"
        
        if user_credits:
            message += "💳 当前积分:\n"
            for name, value in user_credits.items():
                message += f"  • {name}: {value}\n"
            message += "\n"

        success_count = sum(1 for result in task_results.values() if result)
        total_count = len(task_results)
        message += f"📊 任务执行概况: {success_count}/{total_count} 成功\n\n"
        
        message += "📋 任务详情:\n"
        status_map = {True: "✅", False: "❌", None: "⏸️"}
        # 对任务详情进行排序，确保“血液兑换”在最后
        sorted_tasks = sorted(task_results.items(), key=lambda item: item[0] == "血液兑换")
        for task_name, result in sorted_tasks:
            status = status_map.get(result, "❓")
            message += f"  • {task_name}: {status}\n"
        message += "\n"
        
        if task_summary_data:
            message += "📈 任务总次数统计:\n"
            for task in task_summary_data:
                message += f"  • {task['name']}: {task['count']} 次 (最后: {task['time']})\n"
            message += "\n"
        
        return message

def main():
    """主程序 - 支持多账户"""
    print("=" * 60)
    print("Gamemale 每日任务自动化脚本")
    print("=" * 60)

    config = load_config()

    # 获取账户列表
    accounts = config.get("accounts", [])
    if not accounts:
        print("错误：未找到账户配置，请在 config.yaml 中配置 accounts")
        sys.exit(1)

    print(f"\n共加载 {len(accounts)} 个账户\n")

    all_reports = []
    success_accounts = 0
    failed_accounts = 0
    notify_skipped_accounts = 0

    for i, account_config in enumerate(accounts):
        account_name = account_config.get("username", f"账户{i+1}")
        notify_enabled = account_config.get("notify_enabled", True)

        print(f"\n{'#'*60}")
        print(f"# 开始处理: {account_name} ({i+1}/{len(accounts)})")
        if not notify_enabled:
            print(f"# 通知: 已禁用")
        print(f"{'#'*60}")

        try:
            # 验证账户配置
            if not account_config.get("cookie") and not (account_config.get("username") and account_config.get("password")):
                print(f"❌ [{account_name}] 账户配置无效: 必须提供 cookie 或 (username + password)")
                failed_accounts += 1
                continue

            # 创建自动化实例
            client = GamemaleAutomation(account_config, i)

            # 登录
            if not client.login():
                print(f"❌ [{account_name}] 登录失败，跳过此账户")
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
                    print(f"ℹ️ [{account_name}] 任务完成，但通知已禁用，不发送结果")
                success_accounts += 1
                print(f"✅ [{account_name}] 所有任务执行完成")
            else:
                failed_accounts += 1
                print(f"❌ [{account_name}] 任务执行失败")

        except Exception as e:
            print(f"❌ [{account_name}] 处理账户时发生异常: {e}")
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
        summary_title = f"Gamemale 每日任务 - {success_accounts}/{len(accounts)} 成功"
        summary_content = "\n".join(all_reports)

        print("\n" + "=" * 60)
        print("详细报告")
        print("=" * 60)
        print(summary_content)

        send_notification(config, summary_content)

    # 如果有失败的账户，以非零状态退出
    if failed_accounts > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
