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
import argparse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests

from modules.gamemale_core.configuration import load_runtime_config, create_cookie_saver
from modules.gamemale_core.runtime import add_runtime_arguments, apply_runtime_overrides, configuration_diagnostics

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
# Cloudflare Turnstile 人机验证，支持 全局 + 账户局部 两档：
#   全局：下面顶层的 cloudflare 块（与 accounts 同级），对所有账户生效；
#   局部（可选）：把顶层 cloudflare 块复制到某个账户内、改缩进即可，
#   该账户非空字段优先于全局（只覆盖想改的字段，其余回落到全局）。
# 两处都未配置时，回落到环境变量 GAMEMALE_CF_SOLVER / GAMEMALE_CF_API_KEY。
# solver: 2captcha / capsolver / yescaptcha；留空则该层不使用。
cloudflare:
  solver: ""
  api_key: ""
  max_solves: 2    # 单次运行最多解算次数（控制成本）

accounts:
  - cookie: ""
    username: ""
    password: ""
    notify_enabled: true
    auto_exchange: true
    auto_accept_tasks: true
    auto_complete_tasks: true
    captcha_max_retries: 3
    captcha_precheck: true
    asset_history_enabled: true
    online_time_minutes: 0
    online_refresh_interval_seconds: 900
    task_exclude_ids: []
    task_exclude_names: []
    task_exclude_keywords: []
    # 可选：账户局部 cloudflare（与顶层同结构，局部优先）
    # cloudflare:
    #   solver: ""
    #   api_key: ""
    #   max_solves: 2

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


def load_config() -> Dict[str, Any]:
    """通过共享加载器读取配置，缺少配置时生成模板。"""
    config_path = SCRIPT_DIR / CONFIG_FILE_NAME
    config = load_runtime_config(config_path, SCRIPT_DIR / "config.json")
    if config:
        return config
    config_path.write_text(CONFIG_TEMPLATE, encoding="utf-8")
    print(f"首次运行，已创建配置文件: {config_path}")
    raise ValueError("请填写账户信息后重新运行")


def parse_args() -> argparse.Namespace:
    """解析本次运行的参数。"""
    parser = argparse.ArgumentParser(description="Gamemale 每日任务自动化脚本")
    add_runtime_arguments(parser)
    return parser.parse_args()


def save_cookie_to_config(client: GamemaleAutomation) -> bool:
    """兼容旧接口，新主流程捕获配置来源后使用共享写入器。"""
    config = load_config()
    saver = create_cookie_saver(config, SCRIPT_DIR / CONFIG_FILE_NAME, Path(__file__).parent / "config.json")
    return saver(client) if saver else False


# ============== 通知 ==============
def _create_notifier(
    config: Dict[str, Any],
) -> Optional[Callable[[str, str], None]]:
    """根据配置创建通知回调"""
    nc = config.get("notification", {})
    if not nc.get("enabled", False):
        return None

    ntype = nc.get("type", "console")

    def send(title: str, content: str) -> None:
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
def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(message)s",
        datefmt="%H:%M:%S",
    )
    args = parse_args()
    try:
        config = load_runtime_config(SCRIPT_DIR / CONFIG_FILE_NAME, SCRIPT_DIR / "config.json") if args.check or args.check_config else load_config()
        accounts = config.get("accounts", [])
        if args.check_config:
            valid, lines = configuration_diagnostics(config, os.environ)
            print("\n".join(lines))
            if not valid:
                sys.exit(1)
            return
        if not accounts:
            config_path = SCRIPT_DIR / CONFIG_FILE_NAME
            if not config_path.exists() and not args.check:
                config_path.parent.mkdir(parents=True, exist_ok=True)
                config_path.write_text(CONFIG_TEMPLATE, encoding="utf-8")
                print(f"已创建配置模板: {config_path}")
            raise ValueError("未找到账户配置，请填写配置文件或环境变量")
        accounts = apply_runtime_overrides(accounts, args)
    except (ValueError, OSError) as error:
        print(f"配置错误: {error}")
        sys.exit(1)

    failed = run_all_accounts(
        accounts,
        save_cookie_callback=create_cookie_saver(config, SCRIPT_DIR / CONFIG_FILE_NAME, Path(__file__).parent / "config.json"),
        send_notification=None if args.check else _create_notifier(config),
        cloudflare_config=config.get("cloudflare"),
        asset_state_path=Path(__file__).parent / ".gamemale-state" / "assets.json",
        script_title="Gamemale 每日任务自动化脚本",
    )
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
