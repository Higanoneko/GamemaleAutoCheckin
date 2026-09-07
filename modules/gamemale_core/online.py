# -*- coding: utf-8 -*-
"""Online-time keepalive refresh loop."""

from typing import Dict, Tuple

from .constants import BASE_URL
from .logging_utils import log_error, log_info, log_success, log_warning


class OnlineTimeMixin:
    def _get_online_time_config(self) -> Tuple[bool, int, int, str]:
        """读取挂机配置；只有运行参数注入闸门时才启用。"""
        enabled = self._get_config_bool(["online_runtime_enabled"], default=False)

        duration_seconds = self._get_config_int([
            "online_time_seconds",
            "hang_time_seconds",
            "keepalive_seconds",
        ], default=0)
        if duration_seconds <= 0:
            duration_minutes = self._get_config_int([
                "online_time_minutes",
                "hang_time_minutes",
                "keepalive_minutes",
            ], default=0)
            duration_seconds = max(0, duration_minutes * 60)

        interval_seconds = self._get_config_int([
            "online_refresh_interval_seconds",
            "online_refresh_interval",
            "hang_refresh_interval_seconds",
            "keepalive_interval_seconds",
        ], default=900)
        interval_seconds = max(1, interval_seconds)

        target_url = self._get_config_str(
            ["online_time_url", "hang_time_url"],
            default=f"{BASE_URL}/forum.php",
        )
        return enabled, duration_seconds, interval_seconds, target_url

    def quick_accumulate_online_time(self) -> bool:
        """按固定间隔刷新页面，累计论坛在线/挂机时长。"""
        enabled, duration_seconds, interval_seconds, target_url = self._get_online_time_config()
        self.online_time_summary: Dict[str, object] = {
            "enabled": enabled,
            "duration_seconds": duration_seconds,
            "interval_seconds": interval_seconds,
            "target_url": target_url,
            "refresh_count": 0,
            "elapsed_seconds": 0,
            "status": "disabled" if not enabled else "pending",
        }

        if not enabled:
            log_info("挂机时长功能已禁用", self.account_name)
            return True

        if duration_seconds <= 0:
            self.online_time_summary["status"] = "skipped"
            log_info("挂机时长未配置，跳过", self.account_name)
            return True

        log_info(
            f"开始挂机刷新: 总时长 {duration_seconds} 秒，刷新间隔 {interval_seconds} 秒",
            self.account_name,
        )

        elapsed_seconds = 0
        refresh_count = 0
        try:
            while elapsed_seconds <= duration_seconds:
                if self._is_stopped():
                    self.online_time_summary["status"] = "stopped"
                    log_warning("收到停止信号，中断挂机刷新", self.account_name)
                    break

                self._send_request('GET', target_url, headers={'Referer': f'{BASE_URL}/forum.php'})
                refresh_count += 1
                self.online_time_summary["refresh_count"] = refresh_count
                self.online_time_summary["elapsed_seconds"] = elapsed_seconds
                log_info(
                    f"挂机刷新完成 [{refresh_count}]，已累计约 {elapsed_seconds}/{duration_seconds} 秒",
                    self.account_name,
                )

                if elapsed_seconds >= duration_seconds:
                    break

                wait_seconds = min(interval_seconds, duration_seconds - elapsed_seconds)
                self._sleep(wait_seconds)
                elapsed_seconds += wait_seconds

            if self.online_time_summary.get("status") != "stopped":
                self.online_time_summary["status"] = "completed"
                self.online_time_summary["elapsed_seconds"] = duration_seconds
                log_success(f"挂机刷新完成: 共刷新 {refresh_count} 次", self.account_name)
            return True

        except Exception as e:
            self.online_time_summary["status"] = "failed"
            self.online_time_summary["error"] = str(e)
            log_error(f"挂机刷新失败: {e}", self.account_name)
            return False
