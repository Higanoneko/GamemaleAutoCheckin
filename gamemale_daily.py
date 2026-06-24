#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gamemale 每日任务自动化脚本 - GitHub Actions / 本地运行版
支持多账户，支持 Telegram / 企业微信 / Email / 控制台 通知
"""

import json
import logging
import os
import sys
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

import requests

from modules.gamemale_core import (
    GamemaleAutomation,
    run_all_accounts,
)

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False
    print("警告: PyYAML 未安装，请运行 pip install pyyaml")


# ============== 配置 ==============
SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE_NAME = "config.yaml"

CONFIG_TEMPLATE = """# GameMale 自动签到配置文件
accounts:
  - cookie: ""
    username: ""
    password: ""
    notify_enabled: true
    auto_exchange: true
    auto_accept_tasks: true
    auto_complete_tasks: true
    task_exclude_ids: []
    task_exclude_names: []
    task_exclude_keywords: []

notification:
  enabled: false
  type: "console"
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


def load_config():
    """
    加载配置
    优先级: config.yaml > APP_CONFIG_JSON > config.json
    """
    config_path = SCRIPT_DIR / CONFIG_FILE_NAME
    if config_path.exists() and YAML_AVAILABLE:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    config_json_str = os.environ.get("APP_CONFIG_JSON")
    if config_json_str:
        config = json.loads(config_json_str)
        if "gamemale" in config and "accounts" not in config:
            config["accounts"] = [config["gamemale"]]
        return config

    json_path = SCRIPT_DIR / "config.json"
    if json_path.exists():
        with open(json_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            if "gamemale" in config and "accounts" not in config:
                config["accounts"] = [config["gamemale"]]
            return config

    # 创建模板
    with open(config_path, 'w', encoding='utf-8') as f:
        f.write(CONFIG_TEMPLATE)
    print(f"首次运行，已创建配置文件: {config_path}")
    print("请编辑 config.yaml 填写账户信息后重新运行")
    sys.exit(1)


def save_cookie_to_config(client: GamemaleAutomation) -> bool:
    """将 cookie 保存到配置文件"""
    if not YAML_AVAILABLE:
        return False
    try:
        config_path = SCRIPT_DIR / CONFIG_FILE_NAME
        if not config_path.exists():
            return False
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        if not config or client.account_index >= len(config.get("accounts", [])):
            return False
        new_cookie = client.extract_cookies_string()
        if not new_cookie:
            return False
        config["accounts"][client.account_index]["cookie"] = new_cookie
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        print("✅ Cookie 已自动更新到配置文件")
        return True
    except Exception as e:
        print(f"保存 Cookie 失败: {e}")
        return False


# ============== 通知 ==============
def _create_notifier(config):
    """根据配置创建通知回调"""
    nc = config.get("notification", {})
    if not nc.get("enabled", False):
        return None

    ntype = nc.get("type", "console")

    def send(title, content):
        try:
            if ntype == "telegram":
                tc = nc.get("telegram", {})
                if tc.get("bot_token") and tc.get("chat_id"):
                    requests.post(
                        f"https://api.telegram.org/bot{tc['bot_token']}/sendMessage",
                        json={"chat_id": tc["chat_id"], "text": content, "parse_mode": "HTML"},
                        timeout=10,
                    )
            elif ntype == "wechat":
                wc = nc.get("wechat", {})
                if wc.get("webhook"):
                    requests.post(wc["webhook"], json={"msgtype": "text", "text": {"content": content}}, timeout=10)
            elif ntype == "email":
                ec = nc.get("email", {})
                if all(k in ec for k in ["smtp_server", "username", "password", "from", "to"]):
                    msg = MIMEMultipart()
                    msg['From'], msg['To'], msg['Subject'] = ec["from"], ec["to"], title
                    msg.attach(MIMEText(content, 'plain', 'utf-8'))
                    server = smtplib.SMTP(ec["smtp_server"], ec.get("smtp_port", 587))
                    server.starttls()
                    server.login(ec["username"], ec["password"])
                    server.sendmail(ec["from"], ec["to"], msg.as_string())
                    server.quit()
            else:
                print(f"::notice::{title}")
        except Exception as e:
            print(f"通知发送失败: {e}")

    return send


# ============== 主程序 ==============
def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(message)s",
        datefmt="%H:%M:%S",
    )
    config = load_config()
    accounts = config.get("accounts", [])
    if not accounts:
        print("错误：未找到账户配置")
        sys.exit(1)

    failed = run_all_accounts(
        accounts,
        save_cookie_callback=save_cookie_to_config,
        send_notification=_create_notifier(config),
        script_title="Gamemale 每日任务自动化脚本",
    )
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
