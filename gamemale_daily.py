#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gamemale 每日任务自动化脚本 - GitHub Actions / 本地运行版
支持多账户，支持 Telegram / 企业微信 / Email / 控制台 通知
"""

import json
import os
import sys
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

import requests

# 核心模块
from modules.gamemale_core import (
    GamemaleAutomation,
    interact_with_blogs,
    log_info,
    log_success,
    log_error,
    log_warning,
)

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False
    print("警告: PyYAML 未安装，请运行 pip install pyyaml")


# ============== 配置文件路径 ==============
CONFIG_FILE_NAME = "config.yaml"
SCRIPT_DIR = Path(__file__).parent

CONFIG_TEMPLATE = """# GameMale 自动签到配置文件
# 支持多账户，每个账户可以单独配置

accounts:
  # 账户1
  - cookie: ""           # 登录Cookie（从浏览器F12获取）
    username: ""         # 用户名
    password: ""         # 密码（用于自动登录和血液兑换）
    notify_enabled: true # 是否发送通知（true/false）
    auto_exchange: true  # 是否自动兑换血液为旅程（true/false）

  # 账户2（示例，取消注释并填写信息即可启用）
  # - cookie: ""
  #   username: ""
  #   password: ""
  #   notify_enabled: false
  #   auto_exchange: true

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


# ============== 配置加载 ==============
def load_config():
    """
    加载配置.
    优先级:
    1. 本地 config.yaml 文件 (YAML格式，推荐)
    2. 环境变量 APP_CONFIG_JSON
    3. 本地 config.json 文件 (兼容旧格式)
    """
    # 1. YAML 配置文件
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
            if "gamemale" in config and "accounts" not in config:
                config["accounts"] = [config["gamemale"]]
            return config
        except json.JSONDecodeError:
            print("环境变量 APP_CONFIG_JSON 的值不是有效的 JSON")
            sys.exit(1)

    # 3. JSON 配置文件
    json_path = SCRIPT_DIR / "config.json"
    if json_path.exists():
        print("从本地 config.json 文件加载配置")
        with open(json_path, "r", encoding="utf-8") as f:
            try:
                config = json.load(f)
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
    else:
        print("错误：未找到配置文件，请创建 config.yaml")
    sys.exit(1)


# ============== Cookie 保存回调 ==============
def save_cookie_to_config(client: GamemaleAutomation) -> bool:
    """将当前 session 的 cookie 保存到配置文件"""
    try:
        # 环境变量来源无法自动保存
        config_json_str = os.environ.get("APP_CONFIG_JSON")
        if config_json_str:
            new_cookie = client._extract_cookies_string()
            if new_cookie:
                print("密码登录成功，新 Cookie 已生成。")
                print(f"由于配置来自环境变量，请手动更新 Cookie: {new_cookie[:50]}...")
            return False

        # YAML 配置文件
        config_path = get_config_file_path()
        if config_path.exists() and YAML_AVAILABLE:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            if not config:
                print("配置文件为空，无法保存 Cookie")
                return False

            accounts = config.get("accounts", [])
            if client.account_index >= len(accounts):
                print("账户索引超出范围，无法保存 Cookie")
                return False

            new_cookie = client._extract_cookies_string()
            if not new_cookie:
                print("未能提取到有效的 Cookie")
                return False

            accounts[client.account_index]["cookie"] = new_cookie
            config["accounts"] = accounts

            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

            print("✅ Cookie 已自动更新到配置文件")
            return True

        print("无法自动保存 Cookie（YAML 配置不可用）")
        return False

    except Exception as e:
        print(f"保存 Cookie 失败: {e}")
        return False


# ============== 通知功能 ==============
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
                text_content = message.replace('🎉', '').replace('📊', '').replace('🎰', '')
                text_content = text_content.replace('📈', '').replace('📋', '').replace('•', '-')
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


# ============== 主程序 ==============
def main():
    """主程序 - 支持多账户"""
    print("=" * 60)
    print("Gamemale 每日任务自动化脚本")
    print("=" * 60)

    config = load_config()

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
            print("# 通知: 已禁用")
        print(f"{'#'*60}")

        try:
            if not account_config.get("cookie") and not (account_config.get("username") and account_config.get("password")):
                print(f"❌ [{account_name}] 账户配置无效: 必须提供 cookie 或 (username + password)")
                failed_accounts += 1
                continue

            client = GamemaleAutomation(
                account_config, i,
                save_cookie_callback=save_cookie_to_config,
            )

            if not client.login():
                print(f"❌ [{account_name}] 登录失败，跳过此账户")
                failed_accounts += 1
                continue

            report = client.execute_all_tasks()

            if report:
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
            import time
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

    if all_reports:
        summary_title = f"Gamemale 每日任务 - {success_accounts}/{len(accounts)} 成功"
        summary_content = "\n".join(all_reports)

        print("\n" + "=" * 60)
        print("详细报告")
        print("=" * 60)
        print(summary_content)

        send_notification(config, summary_content)

    if failed_accounts > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
