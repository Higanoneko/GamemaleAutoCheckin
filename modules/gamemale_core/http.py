# -*- coding: utf-8 -*-
"""HTTP session factory for GameMale requests."""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .constants import BASE_URL


def create_session() -> requests.Session:
    """创建带有重试策略和默认头的 requests Session"""
    session = requests.Session()

    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET", "POST", "HEAD"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': f'{BASE_URL}/forum.php',
    })

    return session
