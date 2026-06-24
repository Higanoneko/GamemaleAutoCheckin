# -*- coding: utf-8 -*-
"""HTML, AJAX, URL, and task-list parsers."""

import re
from typing import Dict, List, Optional, Set
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

from .constants import BASE_URL


def _extract_ajax_content(response_text: str) -> str:
    """提取 Discuz AJAX 响应中的 CDATA 内容，非 XML 响应原样返回。"""
    content_match = re.search(r'<!\[CDATA\[(.*?)\]\]>', response_text, re.DOTALL)
    return content_match.group(1) if content_match else response_text


def _resolve_gamemale_url(raw_url: str) -> str:
    """将页面中的相对链接可靠地解析为绝对 URL。"""
    return urljoin(f"{BASE_URL}/", raw_url.replace('&amp;', '&'))


def _clean_captcha_text(raw_text: str) -> str:
    """清洗 OCR 结果，只保留验证码可能使用的字母和数字。"""
    return re.sub(r'[^0-9A-Za-z]', '', raw_text or '')


def _extract_seccodehash(html_content: str, soup: BeautifulSoup) -> str:
    """从登录弹窗 HTML 中提取验证码 idhash。"""
    seccodehash_match = re.search(r"updateseccode\(['\"]([a-zA-Z0-9]+)['\"]", html_content)
    seccodehash = seccodehash_match.group(1) if seccodehash_match else None
    if not seccodehash:
        seccode_tag = soup.find(id=re.compile(r'^seccode_'))
        if seccode_tag and seccode_tag.has_attr('id'):
            seccodehash = seccode_tag['id'].replace('seccode_', '', 1)
    if not seccodehash:
        raise ValueError("未找到seccodehash")
    return seccodehash


def _extract_seccode_image_url(js_response_text: str) -> str:
    """从验证码刷新 JS 中提取真实验证码图片 URL。"""
    img_path_match = re.search(r"""src=(["'])(?P<src>[^"']*mod=seccode[^"']*)\1""", js_response_text)
    if not img_path_match:
        raise ValueError("无法解析验证码URL")
    return _resolve_gamemale_url(img_path_match.group('src'))


def _get_query_param(url: str, name: str) -> Optional[str]:
    """从 URL 查询参数中取单个值。"""
    values = parse_qs(urlparse(_resolve_gamemale_url(url)).query).get(name)
    return values[0] if values else None


def _parse_new_task_list(page_text: str) -> List[Dict[str, str]]:
    """解析“新任务”页面中的可接取任务。"""
    soup = BeautifulSoup(page_text, 'html.parser')
    tasks: List[Dict[str, str]] = []
    seen_task_ids: Set[str] = set()

    for apply_link in soup.find_all('a', href=True):
        apply_href = apply_link['href'].replace('&amp;', '&')
        if 'mod=task' not in apply_href or 'do=apply' not in apply_href:
            continue

        task_id = _get_query_param(apply_href, 'id')
        if not task_id or task_id in seen_task_ids:
            continue

        task_row = apply_link.find_parent('tr')
        task_scope = task_row or apply_link.find_parent(['li', 'div']) or apply_link
        view_link = task_scope.find('a', href=re.compile(r'mod=task.*do=view.*id=')) if task_scope else None
        title = view_link.get_text(" ", strip=True) if view_link else apply_link.get_text(" ", strip=True)
        description_tag = task_scope.find('p', class_='xg2') if task_scope else None
        reward_tag = task_scope.find('td', class_=re.compile(r'\bxi1\b')) if task_scope else None

        tasks.append({
            "id": task_id,
            "name": title or f"任务 {task_id}",
            "description": description_tag.get_text(" ", strip=True) if description_tag else "",
            "reward": reward_tag.get_text(" ", strip=True) if reward_tag else "",
            "view_url": _resolve_gamemale_url(view_link['href']) if view_link and view_link.has_attr('href') else "",
            "apply_url": _resolve_gamemale_url(apply_href),
        })
        seen_task_ids.add(task_id)

    return tasks


def _parse_doing_task_list(page_text: str) -> List[Dict[str, str]]:
    """解析“进行中的任务”页面，标记哪些任务已经可领取奖励。"""
    soup = BeautifulSoup(page_text, 'html.parser')
    tasks: List[Dict[str, str]] = []
    seen_task_ids: Set[str] = set()

    for draw_link in soup.find_all('a', href=True):
        draw_href = draw_link['href'].replace('&amp;', '&')
        if 'mod=task' not in draw_href or 'do=draw' not in draw_href:
            continue

        task_id = _get_query_param(draw_href, 'id')
        if not task_id or task_id in seen_task_ids:
            continue

        task_row = draw_link.find_parent('tr')
        task_scope = task_row or draw_link.find_parent(['li', 'div']) or draw_link
        view_link = task_scope.find('a', href=re.compile(r'mod=task.*do=view.*id=')) if task_scope else None
        title = view_link.get_text(" ", strip=True) if view_link else f"任务 {task_id}"
        description_tag = task_scope.find('p', class_='xg2') if task_scope else None
        reward_tag = task_scope.find('td', class_=re.compile(r'\bxi1\b')) if task_scope else None
        progress_tag = task_scope.find(id=f"csc_{task_id}") if task_scope else None
        progress = int(progress_tag.get_text(strip=True)) if progress_tag and progress_tag.get_text(strip=True).isdigit() else 0
        draw_image = ""
        image_tag = draw_link.find('img')
        if image_tag and image_tag.has_attr('src'):
            draw_image = image_tag['src']

        tasks.append({
            "id": task_id,
            "name": title or f"任务 {task_id}",
            "description": description_tag.get_text(" ", strip=True) if description_tag else "",
            "reward": reward_tag.get_text(" ", strip=True) if reward_tag else "",
            "progress": str(progress),
            "can_draw": str(progress >= 100 and "rewardless" not in draw_image).lower(),
            "draw_image": draw_image,
            "view_url": _resolve_gamemale_url(view_link['href']) if view_link and view_link.has_attr('href') else "",
            "draw_url": _resolve_gamemale_url(draw_href),
        })
        seen_task_ids.add(task_id)

    return tasks
