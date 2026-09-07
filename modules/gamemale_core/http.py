# -*- coding: utf-8 -*-
"""HTTP session factory for GameMale requests."""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .constants import BASE_URL

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def create_session() -> requests.Session:
    """创建带有重试策略和默认头的 requests Session。

    默认请求头按真实浏览器补齐（User-Agent / Accept / Accept-Language），
    以尽量降低论坛 Cloudflare 人机验证对脚本请求的误判概率。
    """
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
        'User-Agent': DEFAULT_USER_AGENT,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,'
                  'image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7',
        'Cache-Control': 'no-cache',
        'Referer': f'{BASE_URL}/forum.php',
    })

    return session
