import requests
import re
import ddddocr
from bs4 import BeautifulSoup
import base64
import json
import time
import random
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- 配置加载与通知函数 ---
def load_config():
    """
    加载配置.
    优先级: 环境变量 APP_CONFIG_JSON > 本地 config.json 文件.
    """
    config_json_str = os.environ.get("APP_CONFIG_JSON")
    if config_json_str:
        print("::notice::从环境变量 APP_CONFIG_JSON 加载配置。")
        try:
            return json.loads(config_json_str)
        except json.JSONDecodeError:
            print("::error::环境变量 APP_CONFIG_JSON 的值不是有效的 JSON。")
            exit(1)
    
    if os.path.exists("config.json"):
        print("::notice::从本地 config.json 文件加载配置。")
        with open("config.json", "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                print("::error::本地 config.json 文件格式无效。")
                exit(1)

    print("::error::错误：未找到配置。请设置 APP_CONFIG_JSON 环境变量或创建 config.json 文件。")
    exit(1)

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
    
    def __init__(self, config):
        self.config = config
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

    def login(self):
        """统一的登录管理"""
        print("::group::登录流程")
        
        login_successful = False
        if self.config.get("gamemale", {}).get("cookie"):
            if self._login_with_cookie():
                print("✅ Cookie 登录成功")
                login_successful = True
        
        if not login_successful and self._login_with_password():
            print("✅ 密码登录成功") 
            login_successful = True
        
        if login_successful:
            self.is_logged_in = True
            self.get_and_store_formhash()
        else:
            print("❌ 所有登录方式均失败")
        
        print("::endgroup::")
        return self.is_logged_in

    def _login_with_cookie(self):
        """使用Cookie尝试登录 (版本B的可靠实现)"""
        cookie_string = self.config.get("gamemale", {}).get("cookie")
        username = self.config.get("gamemale", {}).get("username")
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

            if response.status_code == 200 and '登录' not in response.text:
                # 如果提供了用户名，则额外验证用户名是否存在于页面中
                if username and username.lower() in response.text.lower():
                    return True
                # 如果没有提供用户名，则检查通用登录标识
                elif '我的资料' in response.text:
                    return True
            return False
        except Exception as e:
            print(f"::warning::Cookie登录验证过程中出错: {e}")
            return False

    def _login_with_password(self):
        """使用密码进行登录"""
        gamemale_config = self.config.get("gamemale", {})
        username = gamemale_config.get("username")
        password = gamemale_config.get("password")

        if not all([username, password]):
            print("::warning::密码登录所需信息不完整 (用户名或密码缺失)。")
            return False
        
        max_retries = 8
        for attempt in range(max_retries):
            print(f"\n尝试密码登录 ({attempt + 1}/{max_retries})...")
            
            try:
                loginhash, formhash, seccodehash, seccode_verify = self._get_login_parameters()
                
                if not all([loginhash, formhash, seccodehash, seccode_verify]):
                    raise ValueError("获取登录参数失败")

                login_url = f"https://www.gamemale.com/member.php?mod=logging&action=login&loginsubmit=yes&handlekey=login&loginhash={loginhash}&inajax=1"
                payload = {
                    'formhash': formhash,
                    'referer': 'https://www.gamemale.com/forum.php',
                    'loginfield': 'username',
                    'username': username,
                    'password': password,
                    'questionid': gamemale_config.get("questionid", "0"),
                    'answer': gamemale_config.get("answer", ""),
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
            # 增加日志，帮助调试
            print("::warning::在 _get_login_parameters 中未能从响应中提取到 CDATA 内容。")
            print(f"::debug::响应文本预览: {response.text[:500]}")
            raise ValueError("无法从登录弹窗响应中提取HTML内容。")
        html_content = html_content_match.group(1)

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
            gamemale_config = self.config.get("gamemale", {})
            if not gamemale_config.get("auto_exchange_enabled", True):
                print("ℹ️ 自动兑换功能已禁用，跳过。")
                return credits_data, None

            blood_value_str = credits_data.get("血液", "0 滴").split()[0]
            blood_value = int(blood_value_str)
            
            if blood_value > 34:
                password = gamemale_config.get("password")
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
        message = "🎉 Gamemale 每日任务完成统计\n\n"
        
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
    """主程序"""
    try:
        config = load_config()
        
        gamemale_config = config.get("gamemale", {})
        if not gamemale_config.get("cookie") and not (gamemale_config.get("username") and gamemale_config.get("password")):
            print("::error::错误：必须配置 gamemale.cookie 或 (gamemale.username 和 gamemale.password)。")
            exit(1)

        client = GamemaleAutomation(config)
        
        if not client.login():
            raise Exception("登录失败")
        
        detailed_report = client.execute_all_tasks()
        
        if detailed_report:
            print("🎉 所有任务执行完成！")
            print("\n" + "="*50)
            print("详细报告:")
            print(detailed_report)
            print("="*50)
            
            send_notification(config, detailed_report)
        else:
            print("⚠ 任务执行失败或未生成报告。")
            
    except Exception as e:
        error_message = f"❌ 脚本执行失败: {e}"
        print(error_message)
        send_notification(config, error_message)
        exit(1)

if __name__ == "__main__":
    main()
