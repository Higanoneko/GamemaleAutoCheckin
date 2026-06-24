# -*- coding: utf-8 -*-
"""Credit lookup, exchange, and reward log parsing."""

import re
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

from .constants import BASE_URL, BLOOD_EXCHANGE_THRESHOLD
from .logging_utils import log_error, log_info, log_success, log_warning


class CreditsMixin:
    def _get_credits(self) -> Tuple[Dict[str, str], str]:
        """获取所有积分"""
        credit_page_url = f'{BASE_URL}/home.php?mod=spacecp&ac=credit&op=base'
        response = self._send_request('GET', credit_page_url)
        soup = BeautifulSoup(response.text, 'html.parser')

        credits_data: Dict[str, str] = {}
        credit_list_items = soup.select('ul.creditl li')
        for item in credit_list_items:
            text = item.get_text(" ", strip=True)
            match = re.match(r'(.+?):\s*([\d,]+\s*\S+)', text)
            if match:
                name, value = match.groups()
                value = re.sub(r'\s*[()]+\s*$', '', value.strip())
                credits_data[name.strip()] = value
        return credits_data, credit_page_url
    def get_user_credits_and_exchange(self) -> Tuple[Dict[str, str], Optional[bool]]:
        """获取用户积分并执行血液兑换"""
        log_info("获取积分并检查兑换...", self.account_name)
        exchange_status: Optional[bool] = None
        credits_data: Dict[str, str] = {}

        try:
            credits_data, credit_page_url = self._get_credits()
            log_info(f"当前积分: {credits_data}", self.account_name)

            if not self._get_config_bool(["auto_exchange", "auto_exchange_enabled"], default=True):
                log_info("自动兑换功能已禁用", self.account_name)
                return credits_data, None

            blood_value_str = credits_data.get("血液", "0 滴").split()[0]
            blood_value = int(blood_value_str)

            if blood_value > BLOOD_EXCHANGE_THRESHOLD:
                password = self.config.get("password")
                if not password:
                    log_info(
                        f"血液 ({blood_value}) > {BLOOD_EXCHANGE_THRESHOLD}，但未配置密码，无法兑换",
                        self.account_name,
                    )
                    return credits_data, None

                log_info(f"血液 ({blood_value}) > {BLOOD_EXCHANGE_THRESHOLD}，尝试兑换1旅程...", self.account_name)
                exchange_status = False

                payload = {
                    'formhash': self.formhash,
                    'exchangeamount': '1',
                    'fromcredits': '3',
                    'tocredits': '1',
                    'exchangesubmit': 'true',
                    'password': password,
                }
                exchange_url = (
                    f'{BASE_URL}/home.php?mod=spacecp&ac=credit'
                    f'&op=exchange&handlekey=credit&inajax=1'
                )
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
                log_info(
                    f"血液 ({blood_value}) 不足{BLOOD_EXCHANGE_THRESHOLD}，不执行兑换",
                    self.account_name,
                )

        except Exception as e:
            log_error(f"获取积分或兑换出错: {e}", self.account_name)

        return credits_data, exchange_status
    def get_daily_task_summary(self) -> List[Dict[str, str]]:
        """获取任务总次数统计"""
        task_data: List[Dict[str, str]] = []

        try:
            rewards_url = (
                f'{BASE_URL}/home.php?mod=spacecp&ac=credit'
                f'&op=log&suboperation=creditrulelog'
            )
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
                        "time": last_reward_time,
                    })

        except Exception as e:
            log_warning(f"获取任务统计出错: {e}", self.account_name)

        return task_data

