# -*- coding: utf-8 -*-
"""Multi-account runner for local, Actions, and QingLong entrypoints."""

import random
import time
from typing import Any, Callable, Dict, List, Optional

from .client import GamemaleAutomation
from .logging_utils import log_error, log_info, log_success, log_warning
from .stop_controller import StopController


def run_all_accounts(
    accounts: List[Dict[str, Any]],
    controller: Optional[StopController] = None,
    save_cookie_callback: Optional[Callable[[GamemaleAutomation], bool]] = None,
    send_notification: Optional[Callable[[str, str], None]] = None,
    script_title: str = "Gamemale 每日任务自动化脚本",
) -> int:
    """
    多账户统一运行器。

    Args:
        accounts: 账户配置列表
        controller: 停止控制器（可选，青龙版使用）
        save_cookie_callback: Cookie 保存回调
        send_notification: 通知发送回调 (title, content) -> None
        script_title: 脚本标题

    Returns:
        失败的账户数（0 = 全部成功）
    """
    print("=" * 60)
    print(script_title)
    print("=" * 60)
    print(f"\n共加载 {len(accounts)} 个账户\n")

    all_reports: List[str] = []
    success_accounts = 0
    failed_accounts = 0
    notify_skipped_accounts = 0

    for i, account_config in enumerate(accounts):
        if controller and controller.is_stopped():
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
            if not account_config.get("cookie") and not (
                account_config.get("username") and account_config.get("password")
            ):
                log_error("账户配置无效: 必须提供 cookie 或 (username + password)", account_name)
                failed_accounts += 1
                continue

            client = GamemaleAutomation(
                account_config, i,
                controller=controller,
                save_cookie_callback=save_cookie_callback,
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
        if i < len(accounts) - 1:
            if controller and controller.is_stopped():
                continue
            delay = random.uniform(5, 10)
            print(f"\n等待 {delay:.1f} 秒后处理下一个账户...")
            if controller:
                controller.interruptible_sleep(delay)
            else:
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

    if all_reports and send_notification:
        summary_title = f"Gamemale 每日任务 - {success_accounts}/{len(accounts)} 成功"
        summary_content = "\n".join(all_reports)

        print("\n" + "=" * 60)
        print("详细报告")
        print("=" * 60)
        print(summary_content)

        send_notification(summary_title, summary_content)

    return failed_accounts
