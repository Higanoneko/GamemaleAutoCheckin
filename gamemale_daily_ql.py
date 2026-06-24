#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 青龙面板任务配置
# new Env('GameMale 自动签到')
# cron 0 8 * * * gamemale_daily_ql.py
"""
Gamemale 每日任务自动化脚本 - 青龙面板适配版
"""

import json
import logging
import os
import signal
import sys
from pathlib import Path

from modules.gamemale_core import (
    GamemaleAutomation,
    run_all_accounts,
    stop_controller,
)

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False
    print("警告: PyYAML 未安装，请在青龙面板依赖管理中添加 pyyaml")

try:
    from notify import send as ql_send
    QL_NOTIFY_AVAILABLE = True
except ImportError:
    try:
        from sendNotify import send as ql_send
        QL_NOTIFY_AVAILABLE = True
    except ImportError:
        QL_NOTIFY_AVAILABLE = False


# ============== 信号处理 ==============
def signal_handler(signum, frame):
    """处理停止信号 — 仅设标志，不调 sys.exit"""
    stop_controller.request_stop()
    print("\n⚠️ 收到停止信号，正在优雅退出...")


signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


# ============== 配置 ==============
CONFIG_FILE_NAME = "GameMale_Config.yaml"
QL_CONFIG_PATHS = ["/ql/data/config", "/ql/config", Path(__file__).parent]

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
"""


def get_config_file_path():
    """获取配置文件完整路径"""
    for path in QL_CONFIG_PATHS:
        path = Path(path)
        if path.exists() and path.is_dir():
            return path / CONFIG_FILE_NAME
    return Path(__file__).parent / CONFIG_FILE_NAME


def load_accounts():
    """
    加载账户配置
    优先级: 配置文件 > GAMEMALE_ACCOUNTS > GAMEMALE_COOKIE > APP_CONFIG_JSON
    """
    # 1. 配置文件
    if YAML_AVAILABLE:
        config_path = get_config_file_path()
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                accounts = config.get("accounts", []) if config else []
                if accounts:
                    print(f"从配置文件加载了 {len(accounts)} 个账户: {config_path}")
                    return accounts
            except yaml.YAMLError as e:
                print(f"配置文件格式错误: {e}")
                return []

    # 2. GAMEMALE_ACCOUNTS
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

    # 3. GAMEMALE_COOKIE
    cookie_str = os.environ.get("GAMEMALE_COOKIE", "").strip()
    if cookie_str:
        cookies = [c.strip() for c in cookie_str.split('\n') if c.strip()] if '\n' in cookie_str else [cookie_str]
        accounts = [{"cookie": c, "username": f"账户{i+1}", "password": "", "auto_exchange": True}
                     for i, c in enumerate(cookies)]
        print(f"从环境变量 GAMEMALE_COOKIE 加载了 {len(accounts)} 个账户")
        return accounts

    # 4. APP_CONFIG_JSON
    config_json = os.environ.get("APP_CONFIG_JSON", "").strip()
    if config_json:
        try:
            config = json.loads(config_json)
            gamemale_config = config.get("gamemale", {})
            if gamemale_config:
                return [gamemale_config]
        except json.JSONDecodeError:
            pass

    return []


def save_cookie_to_config(client: GamemaleAutomation) -> bool:
    """将 cookie 保存到配置文件"""
    if not YAML_AVAILABLE:
        return False
    try:
        config_path = get_config_file_path()
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


def send_notification(title, content):
    """发送通知"""
    if QL_NOTIFY_AVAILABLE:
        try:
            ql_send(title, content)
        except Exception as e:
            print(f"通知发送失败: {e}")
    else:
        print(f"\n{'='*50}\n【{title}】\n{content}\n{'='*50}")


# ============== 主程序 ==============
def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(message)s",
        datefmt="%H:%M:%S",
    )
    accounts = load_accounts()
    if not accounts:
        config_path = get_config_file_path()
        if not config_path.exists():
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(CONFIG_TEMPLATE)
            print(f"首次运行，已创建配置文件: {config_path}")
        print("请编辑配置文件填写账户信息后重新运行")
        sys.exit(1)

    failed = run_all_accounts(
        accounts,
        controller=stop_controller,
        save_cookie_callback=save_cookie_to_config,
        send_notification=send_notification,
        script_title="Gamemale 每日任务自动化脚本 - 青龙面板版",
    )
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
