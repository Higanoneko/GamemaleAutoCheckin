#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 青龙面板任务配置
# new Env('GameMale 自动签到')
# cron 0 8 * * * gamemale_daily_ql.py
"""
Gamemale 每日任务自动化脚本 - 青龙面板适配版
支持多账户运行

配置方式：在青龙面板「配置文件」中编辑 GameMale_Config.yaml
首次运行会自动创建配置文件模板
"""

import json
import os
import sys
import signal
import random
from pathlib import Path

# 核心模块
from modules.gamemale_core import (
    GamemaleAutomation,
    interact_with_blogs,
    stop_controller,
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


# ============== 信号处理 ==============
def signal_handler(signum, frame):
    """处理停止信号 — 仅设标志，不调 sys.exit"""
    stop_controller.request_stop()
    print("\n⚠️ 收到停止信号，正在优雅退出...")


signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


# ============== 配置文件路径 ==============
CONFIG_FILE_NAME = "GameMale_Config.yaml"

QL_CONFIG_PATHS = [
    "/ql/data/config",
    "/ql/config",
    Path(__file__).parent,
]

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
    return get_ql_config_dir() / CONFIG_FILE_NAME


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
    1. 青龙配置文件 GameMale_Config.yaml
    2. 环境变量 GAMEMALE_ACCOUNTS
    3. 环境变量 GAMEMALE_COOKIE
    4. 环境变量 APP_CONFIG_JSON (兼容旧格式)
    """
    accounts = []

    # 1. 优先从配置文件加载
    file_accounts = load_config_file()
    if file_accounts:
        return file_accounts

    # 2. GAMEMALE_ACCOUNTS 环境变量
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

    # 3. GAMEMALE_COOKIE 环境变量（简单格式）
    cookie_str = os.environ.get("GAMEMALE_COOKIE", "").strip()
    if cookie_str:
        if '\n' in cookie_str:
            cookies = [c.strip() for c in cookie_str.split('\n') if c.strip()]
        elif '&' in cookie_str and len(cookie_str.split('&')) > 1:
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
                "auto_exchange": True,
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


# ============== Cookie 保存回调 ==============
def save_cookie_to_config(client: GamemaleAutomation) -> bool:
    """将当前 session 的 cookie 保存到配置文件"""
    try:
        if not YAML_AVAILABLE:
            log_warning("PyYAML 未安装，无法保存 Cookie 到配置文件", client.account_name)
            return False

        config_path = get_config_file_path()
        if not config_path.exists():
            log_warning("配置文件不存在，无法保存 Cookie", client.account_name)
            return False

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        if not config:
            log_warning("配置文件为空，无法保存 Cookie", client.account_name)
            return False

        accounts = config.get("accounts", [])
        if client.account_index >= len(accounts):
            log_warning("账户索引超出范围，无法保存 Cookie", client.account_name)
            return False

        new_cookie = client._extract_cookies_string()
        if not new_cookie:
            log_warning("未能提取到有效的 Cookie", client.account_name)
            return False

        accounts[client.account_index]["cookie"] = new_cookie
        config["accounts"] = accounts

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

        log_success("Cookie 已自动更新到配置文件", client.account_name)
        return True

    except Exception as e:
        log_warning(f"保存 Cookie 失败: {e}", client.account_name)
        return False


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
        print(f"\n{'='*50}")
        print(f"【{title}】")
        print(content)
        print('='*50)


# ============== 主程序 ==============
def main():
    """主程序入口"""
    print("=" * 60)
    print("Gamemale 每日任务自动化脚本 - 青龙面板版")
    print("=" * 60)

    accounts = load_accounts()

    if not accounts:
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
    notify_skipped_accounts = 0

    for i, account_config in enumerate(accounts):
        if stop_controller.is_stopped():
            log_warning("收到停止信号，停止处理后续账户")
            break

        account_name = account_config.get("username", f"账户{i+1}")
        notify_enabled = account_config.get("notify_enabled", True)

        print(f"\n{'#'*60}")
        print(f"# 开始处理: {account_name} ({i+1}/{len(accounts)})")
        if not notify_enabled:
            print("# 通知: 已禁用")
        print(f"{'#'*60}")

        try:
            if not account_config.get("cookie") and not (account_config.get("username") and account_config.get("password")):
                log_error("账户配置无效: 必须提供 cookie 或 (username + password)", account_name)
                failed_accounts += 1
                continue

            client = GamemaleAutomation(
                account_config, i,
                controller=stop_controller,
                save_cookie_callback=save_cookie_to_config,
            )

            if not client.login():
                log_error("登录失败，跳过此账户", account_name)
                failed_accounts += 1
                continue

            report = client.execute_all_tasks()

            if report:
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

        # 多账户间延迟（可中断）
        if i < len(accounts) - 1 and not stop_controller.is_stopped():
            delay = random.uniform(5, 10)
            print(f"\n等待 {delay:.1f} 秒后处理下一个账户...")
            stop_controller.interruptible_sleep(delay)

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

        send_notification(summary_title, summary_content)

    if failed_accounts > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
