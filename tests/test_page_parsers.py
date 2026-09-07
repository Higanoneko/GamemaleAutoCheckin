# -*- coding: utf-8 -*-
"""Unit tests for page/AJAX parser pure functions (inline HTML fixtures)."""

import unittest

from modules.gamemale_core.missions import _task_exclusion_reason
from modules.gamemale_core.reports import build_detailed_report, format_duration

from modules.gamemale_core.parsers import (
    _classify_sign_response,
    _classify_task_apply_message,
    _classify_task_draw_message,
    _extract_blog_uid,
    _extract_blog_urls,
    _extract_credit_exchange_error,
    _extract_formhash,
    _extract_login_form_parameters,
    _extract_page_message,
    _extract_poke_form,
    _extract_shock_click_url,
    _is_blog_unavailable,
    _is_credit_exchange_success,
    _is_login_form_session_alive,
    _is_login_response_success,
    _is_poke_already_sent,
    _is_poke_send_success,
    _is_profile_page_logged_in,
    _is_shock_click_success,
    _parse_credit_list,
    _parse_credit_value_int,
    _parse_lottery_response,
    _parse_task_usage_table,
)


class SignAndLotteryTests(unittest.TestCase):
    def test_sign_success_and_already_tokens(self):
        self.assertEqual(_classify_sign_response('succeed 签到成功'), "success")
        self.assertEqual(_classify_sign_response('var s = "succeed";'), "success")
        self.assertEqual(_classify_sign_response('今天已签，明天再来'), "already")

    def test_sign_unknown_response(self):
        self.assertEqual(_classify_sign_response('{"code": -1}'), "unknown")

    def test_lottery_won_cleans_html(self):
        status, payload = _parse_lottery_response('{"tipname": "ok", "tipvalue": "<b>金币 +5</b>"}')
        self.assertEqual(status, "won")
        self.assertEqual(payload, "金币 +5")

    def test_lottery_already_drawn(self):
        status, payload = _parse_lottery_response('{"tipname": null}')
        self.assertEqual(status, "already")
        self.assertEqual(payload, "")

    def test_lottery_other_tipname_is_failed(self):
        status, payload = _parse_lottery_response('{"tipname": "error", "tipvalue": "次数不足"}')
        self.assertEqual(status, "failed")
        self.assertEqual(payload, "error - 次数不足")

    def test_lottery_invalid_json_reports_snippet(self):
        status, payload = _parse_lottery_response("not json at all")
        self.assertEqual(status, "invalid")
        self.assertEqual(payload, "not json at all")


class LoginParserTests(unittest.TestCase):
    LOGIN_FORM_HTML = """
    <form name="login" method="post" autocomplete="off"
          action="member.php?mod=logging&amp;action=login&amp;loginsubmit=yes&amp;handlekey=login&amp;loginhash=Qx9s4Z&amp;inajax=1">
      <input type="hidden" name="formhash" value="f0e1d2c3" />
      <span id="seccode_cSAabc123"></span>
      <script>updateseccode('cSAabc123', '<div></div>', 'member::logging')</script>
    </form>
    """

    def test_is_login_form_session_alive(self):
        self.assertTrue(_is_login_form_session_alive("欢迎您回来，请稍候..."))
        self.assertTrue(_is_login_form_session_alive("succeedhandle_login"))
        self.assertFalse(_is_login_form_session_alive(self.LOGIN_FORM_HTML))

    def test_extract_login_form_parameters(self):
        loginhash, formhash, seccodehash = _extract_login_form_parameters(self.LOGIN_FORM_HTML)
        self.assertEqual(loginhash, "Qx9s4Z")
        self.assertEqual(formhash, "f0e1d2c3")
        self.assertEqual(seccodehash, "cSAabc123")

    def test_extract_login_form_parameters_missing_form_raises(self):
        with self.assertRaises(ValueError):
            _extract_login_form_parameters("<html>no form</html>")

    def test_extract_formhash_variants(self):
        self.assertEqual(_extract_formhash('<input name="formhash" value="ab12cd34" />'), "ab12cd34")
        self.assertEqual(_extract_formhash('url?formhash=ff00ff00'), "ff00ff00")
        self.assertIsNone(_extract_formhash("<html>none</html>"))

    def test_is_profile_page_logged_in(self):
        logged_in = '<a>我的资料</a><div class="avatar">uid=12345</div>'
        logged_out = "<title>登录</title><p>请先登录后访问个人资料</p>"
        self.assertTrue(_is_profile_page_logged_in(logged_in))
        self.assertFalse(_is_profile_page_logged_in(logged_out))

    def test_is_login_response_success(self):
        self.assertTrue(_is_login_response_success('<root><![CDATA[succeed]]></root>'))
        self.assertTrue(_is_login_response_success("欢迎您回来，现在将转入登录前页面"))
        self.assertFalse(_is_login_response_success("用户名或密码错误"))


class CreditParserTests(unittest.TestCase):
    CREDIT_HTML = """
    <ul class="creditl">
      <li><em>血液</em>: 123 滴 (下周清零)</li>
      <li><em>旅程</em>: 45 里</li>
      <li>积分: 1,234 点</li>
    </ul>
    """

    def test_parse_credit_list(self):
        credits = _parse_credit_list(self.CREDIT_HTML)
        self.assertEqual(credits["血液"], "123 滴")
        self.assertEqual(credits["旅程"], "45 里")
        self.assertEqual(credits["积分"], "1,234 点")

    def test_parse_credit_value_int(self):
        self.assertEqual(_parse_credit_value_int("0 滴"), 0)
        self.assertEqual(_parse_credit_value_int("34 滴"), 34)
        with self.assertRaises(ValueError):
            _parse_credit_value_int("未知")

    def test_is_credit_exchange_success(self):
        self.assertTrue(_is_credit_exchange_success("积分操作成功，请稍候"))
        self.assertFalse(_is_credit_exchange_success("余额不足"))

    def test_extract_credit_exchange_error(self):
        text = "var errorhandle_credit = '密码错误';<script>errorhandle_credit('兑换失败')</script>"
        self.assertEqual(_extract_credit_exchange_error(text), "兑换失败")
        self.assertIsNone(_extract_credit_exchange_error("<html>ok</html>"))

    def test_parse_task_usage_table_skips_header(self):
        html = """
        <table class="dt">
          <tr><th>任务</th><th>次数</th><th>上次奖励</th></tr>
          <tr><td>每日签到</td><td>12</td><td>2025-01-01</td></tr>
          <tr><td>访问别人空间</td><td>3</td><td>2025-01-02</td></tr>
        </table>
        """
        rows = _parse_task_usage_table(html)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0], {"name": "每日签到", "count": "12", "time": "2025-01-01"})

    def test_parse_task_usage_table_without_table(self):
        self.assertEqual(_parse_task_usage_table("<html>no table</html>"), [])


class MissionMessageParserTests(unittest.TestCase):
    def test_page_message_priority_selectors(self):
        html = '<div id="messagetext">恭喜您，任务已成功申请</div><div class="alert_info">ignored</div>'
        self.assertEqual(_extract_page_message(html), "恭喜您，任务已成功申请")

    def test_page_message_falls_back_to_whole_text(self):
        html = "<html><body><p>未知响应  内容</p></body></html>"
        self.assertEqual(_extract_page_message(html), "未知响应 内容")

    def test_classify_task_apply_message(self):
        self.assertEqual(_classify_task_apply_message("任务已成功申请，请完成后续操作"), "accepted")
        self.assertEqual(_classify_task_apply_message("任务申请成功"), "accepted")
        self.assertEqual(_classify_task_apply_message("您已经申请过该任务"), "already_doing")
        self.assertEqual(_classify_task_apply_message("该任务正在进行中"), "already_doing")
        self.assertEqual(_classify_task_apply_message("需要先完成任务 A"), "failed")

    def test_classify_task_draw_message(self):
        self.assertEqual(_classify_task_draw_message("任务已成功完成，您将收到奖励通知"), "completed")
        self.assertEqual(_classify_task_draw_message("奖励已发放到账户"), "completed")
        self.assertEqual(_classify_task_draw_message("还没有完成呢"), "failed")


class BlogInteractionParserTests(unittest.TestCase):
    LISTING_HTML = """
    <div><a href="https://www.gamemale.com/blog-10-100.html">日志A</a></div>
    <div><a href="blog-11-2.html">日志B</a></div>
    <a href="forum.php?mod=forumdisplay">不是日志</a>
    """

    BLOG_HTML = """
    <html><body>
      <a id="click_blogid_10_2" href="home.php?mod=space&amp;uid=10&amp;do=blog&amp;id=100">路过</a>
      <a id="click_blogid_10_1" href="home.php?mod=space&amp;uid=10&amp;do=blog&amp;id=100">震惊</a>
    </body></html>
    """

    def test_extract_blog_urls(self):
        urls = _extract_blog_urls(self.LISTING_HTML)
        self.assertEqual(len(urls), 2)
        self.assertEqual(urls[0], "https://www.gamemale.com/blog-10-100.html")
        self.assertEqual(urls[1], "blog-11-2.html")

    def test_extract_blog_uid(self):
        self.assertEqual(_extract_blog_uid("https://www.gamemale.com/blog-123-1.html"), "123")
        self.assertIsNone(_extract_blog_uid("https://www.gamemale.com/space-uid-5.html"))

    def test_is_blog_unavailable(self):
        self.assertTrue(_is_blog_unavailable("您不能访问当前内容"))
        self.assertTrue(_is_blog_unavailable("指定的主题不存在或已被删除或正在被审核"))
        self.assertFalse(_is_blog_unavailable("<html>normal</html>"))

    def test_extract_shock_click_url(self):
        url = _extract_shock_click_url(self.BLOG_HTML)
        self.assertEqual(
            url,
            "https://www.gamemale.com/home.php?mod=space&uid=10&do=blog&id=100&inajax=1",
        )

    def test_extract_shock_click_url_missing_button(self):
        self.assertIsNone(_extract_shock_click_url("<html>no button</html>"))

    def test_is_shock_click_success(self):
        self.assertTrue(_is_shock_click_success("<root><![CDATA[succeed]]></root>"))
        self.assertTrue(_is_shock_click_success("表态成功"))
        self.assertFalse(_is_shock_click_success("failed"))


class PokeParserTests(unittest.TestCase):
    POKE_HTML = """
    <root><![CDATA[
      <form id="pokeform_99" action="home.php?mod=spacecp&amp;ac=poke&amp;op=send&amp;uid=99&amp;inajax=1">
        <input type="hidden" name="formhash" value="h1h2h3h4" />
      </form>
    ]]></root>
    """

    def test_extract_poke_form(self):
        form = _extract_poke_form(self.POKE_HTML, "99")
        self.assertEqual(
            form,
            {
                "action": "https://www.gamemale.com/home.php?mod=spacecp&ac=poke&op=send&uid=99&inajax=1",
                "formhash": "h1h2h3h4",
            },
        )

    def test_extract_poke_form_missing_uid_form(self):
        self.assertIsNone(_extract_poke_form(self.POKE_HTML, "123"))

    def test_poke_state_classifiers(self):
        self.assertTrue(_is_poke_already_sent("今天您已经打过招呼了"))
        self.assertFalse(_is_poke_already_sent("ok"))
        self.assertTrue(_is_poke_send_success("已发送，下次访问时会收到通知"))
        self.assertFalse(_is_poke_send_success("网络错误"))


class ExclusionRuleTests(unittest.TestCase):
    def test_reason_hit_id_name_keyword(self):
        task = {"id": "25", "name": "每周发帖任务", "description": "用于水贴将被警告"}
        self.assertEqual(
            _task_exclusion_reason(task, {"25"}, set(), []), "ID 25 在排除列表中"
        )
        self.assertEqual(
            _task_exclusion_reason(task, set(), {"每周发帖任务"}, []),
            "任务名“每周发帖任务”在排除列表中",
        )
        self.assertEqual(
            _task_exclusion_reason(task, set(), set(), ["水贴"]), "命中排除关键词“水贴”"
        )

    def test_reason_none_when_not_excluded(self):
        task = {"id": "6", "name": "给标题漆上色彩！", "description": "使用变色卡"}
        self.assertIsNone(_task_exclusion_reason(task, {"25"}, set(), ["水贴"]))


class ReportBuilderTests(unittest.TestCase):
    def test_format_duration(self):
        self.assertEqual(format_duration(0), "00:00:00")
        self.assertEqual(format_duration(3661), "01:01:01")

    def test_build_detailed_report_sections(self):
        report = build_detailed_report(
            account_name="tester",
            task_results={"签到": True, "抽奖": False},
            user_credits={"血液": "12 滴"},
            mission_summary={"detected": 1, "accepted": 1, "skipped": 0, "failed": 0},
            mission_results=[{"id": "6", "name": "色彩任务", "status": "accepted"}],
            online_time_summary={"enabled": True, "status": "completed", "duration_seconds": 900},
        )
        self.assertIn("【tester】", report)
        self.assertIn("1/2 成功", report)
        self.assertIn("血液: 12 滴", report)
        self.assertIn("检测: 1 个", report)
        self.assertIn("[6] 色彩任务: 已接取", report)
        self.assertIn("计划时长: 00:15:00", report)

    def test_build_detailed_report_no_optional_data(self):
        report = build_detailed_report("tester", {"签到": True})
        self.assertNotIn("新任务接取", report)
        self.assertNotIn("挂机时长", report)


if __name__ == "__main__":
    unittest.main()
