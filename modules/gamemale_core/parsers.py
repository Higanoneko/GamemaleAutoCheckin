# -*- coding: utf-8 -*-
"""HTML, AJAX, URL, and task-list parsers."""

import json
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from .constants import BASE_URL
from .progression import UsergroupProgress


def parse_usergroup_progress(html_content: str) -> Optional[UsergroupProgress]:
    """读取用户组页面的缺口；不把积分下限、缺失或歧义当作升级缺口。"""
    soup = BeautifulSoup(html_content, 'html.parser')
    for element in reversed(soup.select('script, style, [hidden], [aria-hidden="true"]')):
        element.decompose()
    for element in reversed(soup.select('[style]')):
        if re.search(r'display\s*:\s*none|visibility\s*:\s*hidden', str(element.get('style')), re.I):
            element.decompose()
    notices = soup.select('.tscr .notice') or soup.select('.notice')
    gaps: List[int] = []
    for notice in notices:
        match = re.fullmatch(r'您升级到此用户组还需积分\s*[:：]?\s*([\d,]+)(?:\s*积分)?',
                             notice.get_text(' ', strip=True))
        if match:
            try:
                gaps.append(_parse_credit_value_int(match.group(1)))
            except ValueError:
                return None
    if len(gaps) != 1:
        return None
    current = soup.select_one('.tdat .c0 h4')
    target = soup.select_one('#tba #c2')
    current_match = re.fullmatch(r'我的主用户组\s*[-－–—:：]\s*(.+)', current.get_text(' ', strip=True)) if current else None
    target_match = re.fullmatch(r'(?:晋级|升级)用户组\s*[-－–—:：]\s*(.+)', target.get_text(' ', strip=True)) if target else None
    return UsergroupProgress(gaps[0], current_match.group(1) if current_match else None,
                             target_match.group(1) if target_match else None)


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
        hidden = soup.find('input', attrs={'name': 'seccodehash'})
        seccodehash = str(hidden.get('value', '')) if isinstance(hidden, Tag) else None
    if not seccodehash:
        seccode_tag = soup.find(id=re.compile(r'^seccode_'))
        if isinstance(seccode_tag, Tag) and seccode_tag.has_attr('id'):
            seccodehash = str(seccode_tag['id']).replace('seccode_', '', 1)
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


# ---------- 登录态 / 登录表单 ----------

def _extract_login_error_message(response_text: str) -> str:
    """从登录失败的 Discuz AJAX 响应中提取可读错误信息。"""
    content = _extract_ajax_content(response_text)
    content = re.split(r'<script\b', content, maxsplit=1, flags=re.IGNORECASE)[0]
    message = BeautifulSoup(content, 'html.parser').get_text(" ", strip=True)
    message = re.sub(r'\s+', ' ', message)
    return message or "未知登录错误"


def _is_login_response_success(response_text: str) -> bool:
    """判断 Discuz 登录 AJAX 响应是否报告登录成功。"""
    return 'succeed' in response_text or '欢迎您回来' in response_text


def _is_credit_exchange_success(response_text: str) -> bool:
    """判断积分兑换 AJAX 响应是否成功。"""
    return '积分操作成功' in response_text


def _is_profile_page_logged_in(page_text: str) -> bool:
    """从个人资料页文本判断当前 Session 是否处于登录态。"""
    return parse_login_state(page_text) == "logged_in"


def extract_logged_in_uid(page_text: str) -> Optional[int]:
    """只读取脚本中的当前会话 UID，公开空间链接不代表当前身份。"""
    soup = BeautifulSoup(page_text, 'html.parser')
    for script in soup.find_all('script'):
        match = re.search(r"\bdiscuz_uid\s*=\s*['\"]?(\d+)['\"]?\s*[;,]", script.get_text())
        if match:
            return int(match.group(1))
    return None


def parse_login_state(page_text: str) -> str:
    """返回 logged_in / guest / unknown；缺少标记不能推断 Cookie 过期。"""
    uid = extract_logged_in_uid(page_text)
    if uid is not None:
        return "logged_in" if uid > 0 else "guest"
    soup = BeautifulSoup(page_text, 'html.parser')
    for link in soup.find_all('a', href=True):
        query = parse_qs(urlparse(link['href']).query)
        if query.get('action') == ['logout'] and query.get('formhash'):
            return "logged_in"
    if '请先登录' in soup.get_text() or soup.find('form', attrs={'name': 'login'}):
        return "guest"
    return "unknown"


def is_login_redirect(url: str) -> bool:
    parsed = urlparse(_resolve_gamemale_url(url))
    query = parse_qs(parsed.query)
    return parsed.path.endswith('/member.php') and query.get('mod') == ['logging'] and query.get('action') == ['login']


def parse_cookie_header(raw: str) -> Dict[str, str]:
    """归一化浏览器 Cookie 头和 JSON 导出，非法输入明确报错。"""
    text = raw.strip()
    text = re.sub(r'^Cookie\s*:\s*', '', text, flags=re.IGNORECASE)
    if not text:
        return {}
    if text.startswith('{'):
        try:
            data = json.loads(text)
        except ValueError:
            raise ValueError("Cookie JSON 格式无效") from None
        if not isinstance(data, dict) or any(not isinstance(v, str) for v in data.values()):
            raise ValueError("Cookie JSON 必须是名称到字符串值的对象")
        items = list(data.items())
    else:
        if len(text) > 1 and text[0] == text[-1] and text[0] in ('"', "'"):
            text = text[1:-1]
        items = []
        for part in re.split(r';|\r?\n', text):
            if not part.strip():
                continue
            name, separator, value = part.partition('=')
            if not separator:
                raise ValueError("Cookie 项缺少等号")
            items.append((name, value))
    cookies: Dict[str, str] = {}
    for name, value in items:
        name, value = name.strip(), value.strip()
        if not name or re.search(r'[\s;=:\x00-\x1f]', name) or re.search(r'[;\r\n\x00]', value):
            raise ValueError("Cookie 名称或值无效")
        cookies[name] = value
    return cookies


def _is_login_form_session_alive(html_content: str) -> bool:
    """判断登录弹窗 AJAX 内容是否显示“已登录，无需重新登录”。"""
    return '欢迎您回来' in html_content or 'succeedhandle_login' in html_content


def _extract_login_form_parameters(html_content: str) -> Tuple[str, str, str]:
    """兼容旧接口：该接口仍要求表单带验证码。"""
    form = parse_login_form(html_content)
    if not form.seccodehash:
        raise ValueError("未找到seccodehash")
    return form.loginhash, form.formhash, form.seccodehash


@dataclass(frozen=True)
class LoginForm:
    loginhash: str
    formhash: str
    seccodehash: Optional[str]
    modid: str
    captcha_required: bool


def parse_login_form(html_content: str) -> LoginForm:
    """解析验证码是否必需及动态参数，不读取客户端或配置状态。"""
    soup = BeautifulSoup(html_content, 'html.parser')

    action_tag = soup.find('form', {'name': 'login'})
    if not isinstance(action_tag, Tag) or not action_tag.has_attr('action'):
        raise ValueError("未找到登录表单的action URL")
    action_url = str(action_tag['action'])

    loginhash_match = re.search(r'loginhash=(\w+)', action_url)
    if not loginhash_match:
        raise ValueError("未找到loginhash")
    loginhash = loginhash_match.group(1)

    formhash_tag = soup.find('input', {'name': 'formhash'})
    if not isinstance(formhash_tag, Tag) or not formhash_tag.has_attr('value'):
        raise ValueError("未找到formhash")
    formhash = str(formhash_tag['value'])

    try:
        seccodehash = _extract_seccodehash(html_content, soup)
    except ValueError:
        seccodehash = None
    captcha_required = bool(seccodehash or soup.find('input', attrs={'name': 'seccodeverify'}))
    if captcha_required and not seccodehash:
        raise ValueError("表单要求验证码，但缺少seccodehash")
    hidden_modid = soup.find('input', attrs={'name': 'seccodemodid'})
    modid_match = re.search(r"updateseccode\([^,]+,.*?,\s*['\"]([\w:]+)['\"]\s*\)", html_content, re.DOTALL)
    modid = str(hidden_modid.get('value', '')) if isinstance(hidden_modid, Tag) else modid_match.group(1) if modid_match else ''
    return LoginForm(loginhash, str(formhash), seccodehash, modid or 'member::logging', captcha_required)


def is_captcha_check_success(response_text: str) -> bool:
    return _extract_ajax_content(response_text).strip() == 'succeed'


def is_terminal_login_error(response_text: str) -> bool:
    message = _extract_login_error_message(response_text)
    return any(token in message for token in ('密码错误', '用户名或密码错误', '账户被锁定', '登录失败次数过多', '安全问题'))


def _extract_formhash(page_text: str) -> Optional[str]:
    """从页面 HTML 中提取 formhash（依次尝试三种常见形态）。"""
    match = (
        re.search(r'formhash" value="([a-f0-9]+)"', page_text)
        or re.search(r'formhash=([a-f0-9]+)', page_text)
        or re.search(r'"formhash":"([a-f0-9]+)"', page_text)
    )
    return match.group(1) if match else None


# ---------- 签到 / 抽奖结果分类 ----------

def _classify_sign_response(response_text: str) -> str:
    """对签到 AJAX 响应分类，返回 success / already / unknown。"""
    if 'succeed' in response_text or '签到成功' in response_text:
        return "success"
    if '已签' in response_text:
        return "already"
    return "unknown"


def _parse_lottery_response(response_text: str) -> Tuple[str, str]:
    """解析抽奖 AJAX 响应。

    Returns:
        (状态, 展示内容)：状态 ∈ {won, already, failed, invalid}；
        invalid 时内容为响应文本截断（用于“结果未知”日志）。
    """
    try:
        data = json.loads(response_text)
    except (ValueError, json.JSONDecodeError):
        return "invalid", response_text[:100]
    tip_name = data.get("tipname")
    tip_value = data.get("tipvalue", "")
    if tip_name == "ok":
        clean_tip_value = re.sub(r'<.*?>', '', tip_value).strip()
        return "won", clean_tip_value
    if not tip_name:
        return "already", ""
    return "failed", f"{tip_name} - {tip_value}"


# ---------- 任务页提示与结果分类 ----------

def _extract_page_message(page_text: str) -> str:
    """从 Discuz 提示页中提取简短可读消息。"""
    soup = BeautifulSoup(page_text, 'html.parser')
    message_node = (
        soup.select_one('#messagetext')
        or soup.select_one('.alert_info')
        or soup.select_one('.alert_right')
    )
    message = (
        message_node.get_text(" ", strip=True)
        if message_node
        else soup.get_text(" ", strip=True)
    )
    return re.sub(r'\s+', ' ', message).strip()


def _classify_task_apply_message(message: str) -> str:
    """判断任务“申请”结果消息，返回 accepted / already_doing / failed。"""
    if any(token in message for token in (
        "任务已成功申请",
        "任务申请成功",
        "任务已成功完成",
        "任务完成",
    )):
        return "accepted"
    if "已经申请" in message or "正在进行" in message:
        return "already_doing"
    return "failed"


def _classify_task_draw_message(message: str) -> str:
    """判断任务“领奖”结果消息，返回 completed / failed。"""
    if any(token in message for token in (
        "任务已成功完成",
        "任务完成",
        "您将收到奖励通知",
        "奖励",
    )):
        return "completed"
    return "failed"


# ---------- 积分页 / 兑换 ----------

def _parse_credit_list(page_text: str) -> Dict[str, str]:
    """从积分页解析 `ul.creditl li` 各项积分名称与数值。"""
    soup = BeautifulSoup(page_text, 'html.parser')
    credits_data: Dict[str, str] = {}
    for item in soup.select('ul.creditl li'):
        text = item.get_text(" ", strip=True)
        match = re.match(r'(.+?)[:：]\s*([\d,]+)(?![\d,.])(?:\s*([^\s()（）]+))?', text)
        if match:
            name, amount, unit = match.groups()
            value = f'{amount} {unit}'.strip() if unit else amount
            try:
                _parse_credit_value_int(value)
            except ValueError:
                continue
            credits_data[name.strip()] = value
    return credits_data


def _extract_credit_exchange_error(response_text: str) -> Optional[str]:
    """从兑换失败的 Discuz AJAX 响应中提取错误文本。"""
    match = re.search(r"errorhandle_credit\('([^']+)'", response_text)
    return match.group(1) if match else None


def _parse_credit_value_int(credit_value: str) -> int:
    """读取整数或合法千位格式；非法数字不能作为有效余额。"""
    parts = credit_value.split()
    if (not parts or not re.fullmatch(r'[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)', parts[0])
            or (len(parts) > 1 and re.match(r'[eE][+-]?\d', parts[1]))):
        raise ValueError('积分值必须为整数或合法千位格式')
    return int(parts[0].replace(',', ''))


def _parse_task_usage_table(page_text: str) -> List[Dict[str, str]]:
    """解析“任务总次数统计”表（table.dt），跳过表头行。"""
    soup = BeautifulSoup(page_text, 'html.parser')
    table = soup.find('table', class_='dt')
    if not isinstance(table, Tag):
        return []

    task_data: List[Dict[str, str]] = []
    for row in table.find_all('tr')[1:]:
        columns = row.find_all('td')
        if len(columns) >= 3:
            task_data.append({
                "name": columns[0].get_text(strip=True),
                "count": columns[1].get_text(strip=True),
                "time": columns[-1].get_text(strip=True),
            })
    return task_data


# ---------- 日志互动 / 空间打招呼 ----------

def _extract_blog_urls(page_text: str) -> List[str]:
    """从日志列表页提取所有 blog 详情页 URL（原文 href，未解析相对链接）。"""
    soup = BeautifulSoup(page_text, 'html.parser')
    return [str(link['href']) for link in soup.find_all('a', href=True) if blog_identity(str(link['href']))]


def _extract_blog_uid(full_url: str) -> Optional[str]:
    """从日志详情 URL 提取博主 UID（形如 blog-123-1.html）。"""
    identity = blog_identity(full_url)
    return identity[0] if identity else None


def blog_identity(url: str) -> Optional[Tuple[str, str]]:
    """同一日志的 SEO/查询参数 URL 使用同一个去重标识。"""
    parsed = urlparse(_resolve_gamemale_url(url))
    if parsed.hostname not in ('www.gamemale.com', 'gamemale.com'):
        return None
    match = re.search(r'blog-(\d+)-(\d+)\.html', parsed.path)
    if match:
        return match.group(1), match.group(2)
    query = parse_qs(parsed.query)
    uid, blog_id = query.get('uid', [''])[0], query.get('id', [''])[0]
    if query.get('do') == ['blog'] and uid.isdigit() and blog_id.isdigit():
        return uid, blog_id
    return None


def _is_blog_unavailable(page_text: str) -> bool:
    """判断日志页是否提示无权限访问或内容不存在。"""
    return (
        "您不能访问当前内容" in page_text
        or "指定的主题不存在或已被删除或正在被审核" in page_text
    )


def _extract_shock_click_url(page_text: str) -> Optional[str]:
    """从日志正文页提取“表态（震惊）”按钮的 AJAX 提交 URL。"""
    shock_button = BeautifulSoup(page_text, 'html.parser').select_one(
        'a[id*="click_blogid_"][id$="_1"]'
    )
    if not shock_button or not shock_button.has_attr('href'):
        return None
    click_url_raw = str(shock_button['href'])
    click_url = click_url_raw.replace('&amp;', '&')
    if '&inajax=1' not in click_url:
        click_url += '&inajax=1'
    if not click_url.startswith('http'):
        click_url = f"{BASE_URL}/{click_url.lstrip('/')}"
    return click_url


def _is_shock_click_success(response_text: str) -> bool:
    """判断表态 AJAX 响应是否成功。"""
    return 'succeed' in response_text or '表态成功' in response_text


def classify_shock_response(response_text: str) -> str:
    """重复操作不代表今日完成额度；失败与未知单独统计。"""
    if '已表过态' in response_text or '已表态' in response_text:
        return 'already_done'
    if _is_shock_click_success(response_text):
        return 'success'
    if any(token in response_text for token in ('失败', '错误', '请先登录', '无权')):
        return 'failed'
    return 'unknown'


def _extract_poke_form(response_text: str, uid: str) -> Optional[Dict[str, str]]:
    """从打招呼弹窗 AJAX 响应中解析提交表单，返回 {action, formhash}。"""
    content_match = re.search(r'<!\[CDATA\[(.*)\]\]>', response_text, re.DOTALL)
    if not content_match:
        return None
    soup = BeautifulSoup(content_match.group(1), 'html.parser')
    form = soup.find('form', id=f'pokeform_{uid}')
    if not isinstance(form, Tag) or not form.has_attr('action'):
        return None
    action_url = str(form['action']).replace('&amp;', '&')
    if not action_url.startswith('http'):
        action_url = f"{BASE_URL}/{action_url.lstrip('/')}"
    formhash_tag = form.find('input', {'name': 'formhash'})
    if not isinstance(formhash_tag, Tag) or not formhash_tag.has_attr('value'):
        return None
    return {"action": action_url, "formhash": str(formhash_tag['value'])}


def _is_poke_already_sent(response_text: str) -> bool:
    """判断打招呼响应是否为“今天已打过招呼”。"""
    return '今天您已经打过招呼了' in response_text


def _is_poke_send_success(response_text: str) -> bool:
    """判断打招呼提交响应是否成功。"""
    return (
        '已发送' in response_text
        and '下次访问时会收到通知' in response_text
    )
