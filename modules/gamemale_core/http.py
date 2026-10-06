# -*- coding: utf-8 -*-
"""HTTP session factory for GameMale requests."""

import requests
from requests.adapters import HTTPAdapter

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

    # Discuz 的 GET 也可能兑换/抽奖。重试由客户端按操作语义决定，
    # 同时让 503 验证页能够先被识别，并让等待接入停止控制器。
    adapter = HTTPAdapter(max_retries=0)
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
