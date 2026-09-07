import unittest
from argparse import Namespace

from bs4 import BeautifulSoup

from gamemale_daily import apply_runtime_overrides
from modules.gamemale_core.core import (
    _clean_captcha_text,
    _coerce_config_bool,
    _coerce_config_list,
    _extract_ajax_content,
    _extract_seccode_image_url,
    _extract_seccodehash,
    _parse_doing_task_list,
    _parse_new_task_list,
    _resolve_gamemale_url,
    GamemaleAutomation,
)
from modules.gamemale_core.parsers import _extract_login_error_message


class LoginHelperTests(unittest.TestCase):
    def test_extract_ajax_content_returns_cdata_body(self):
        response_text = '<?xml version="1.0"?><root><![CDATA[<form>login</form>]]></root>'

        self.assertEqual(_extract_ajax_content(response_text), "<form>login</form>")

    def test_extract_ajax_content_falls_back_to_raw_text(self):
        self.assertEqual(_extract_ajax_content("<html>login</html>"), "<html>login</html>")

    def test_resolve_gamemale_url_handles_relative_absolute_and_escaped_urls(self):
        self.assertEqual(
            _resolve_gamemale_url("misc.php?mod=seccode&amp;idhash=abc"),
            "https://www.gamemale.com/misc.php?mod=seccode&idhash=abc",
        )
        self.assertEqual(
            _resolve_gamemale_url("/misc.php?mod=seccode"),
            "https://www.gamemale.com/misc.php?mod=seccode",
        )
        self.assertEqual(
            _resolve_gamemale_url("https://www.gamemale.com/misc.php?mod=seccode"),
            "https://www.gamemale.com/misc.php?mod=seccode",
        )

    def test_extract_seccodehash_prefers_updateseccode_call(self):
        html = "<script>updateseccode('cSAabc123', '<div></div>', 'member::logging')</script>"
        soup = BeautifulSoup(html, "html.parser")

        self.assertEqual(_extract_seccodehash(html, soup), "cSAabc123")

    def test_extract_seccodehash_falls_back_to_seccode_element_id(self):
        html = '<span id="seccode_cSAfallback"></span>'
        soup = BeautifulSoup(html, "html.parser")

        self.assertEqual(_extract_seccodehash(html, soup), "cSAfallback")

    def test_extract_seccode_image_url_ignores_non_captcha_images(self):
        js = (
            "<img src=\"' + STATICURL + 'image/common/none.gif\" />"
            '<img src="misc.php?mod=seccode&amp;update=123&amp;idhash=cSAabc" />'
        )

        self.assertEqual(
            _extract_seccode_image_url(js),
            "https://www.gamemale.com/misc.php?mod=seccode&update=123&idhash=cSAabc",
        )

    def test_clean_captcha_text_removes_ocr_noise(self):
        self.assertEqual(_clean_captcha_text(" A b-3_9 "), "Ab39")

    def test_extract_login_error_message_strips_scripts(self):
        response_text = "<root><![CDATA[bad captcha<script>hideWindow()</script>]]></root>"

        self.assertEqual(_extract_login_error_message(response_text), "bad captcha")

    def test_parse_new_task_list_extracts_applyable_tasks(self):
        page_html = """
        <table>
          <tr>
            <td><img alt="每周发帖任务" /></td>
            <td class="bbda ptm pbm">
              <h3><a href="https://www.gamemale.com/home.php?mod=task&amp;do=view&amp;id=25">每周发帖任务</a></h3>
              <p class="xg2">每周可做1次该任务</p>
            </td>
            <td class="xi1 bbda hm">积分 金币 25 枚</td>
            <td><a href="https://www.gamemale.com/home.php?mod=task&amp;do=apply&amp;id=25"><img alt="apply" /></a></td>
          </tr>
          <tr>
            <td></td>
            <td class="bbda ptm pbm">
              <h3><a href="home.php?mod=task&amp;do=view&amp;id=6">给标题漆上色彩！</a></h3>
              <p class="xg2">变色卡免费大赠送</p>
            </td>
            <td class="xi1 bbda hm">道具 亮色刷 1 张</td>
            <td><a href="home.php?mod=task&amp;do=apply&amp;id=6"><img alt="apply" /></a></td>
          </tr>
        </table>
        """

        tasks = _parse_new_task_list(page_html)

        self.assertEqual(len(tasks), 2)
        self.assertEqual(tasks[0]["id"], "25")
        self.assertEqual(tasks[0]["name"], "每周发帖任务")
        self.assertEqual(tasks[0]["reward"], "积分 金币 25 枚")
        self.assertEqual(
            tasks[1]["apply_url"],
            "https://www.gamemale.com/home.php?mod=task&do=apply&id=6",
        )

    def test_parse_doing_task_list_marks_rewardless_tasks_not_ready(self):
        page_html = """
        <table>
          <tr>
            <td class="bbda ptm pbm">
              <h3><a href="home.php?mod=task&amp;do=view&amp;id=28">使用道具熟悉论坛！</a></h3>
              <p class="xg2">使用道具即可完成任务</p>
              <div class="xs0">已完成 <span id="csc_28">0</span>%</div>
            </td>
            <td class="xi1 bbda hm">积分 旅程 1 里</td>
            <td><a href="home.php?mod=task&amp;do=draw&amp;id=28"><img src="static/image/task/rewardless.gif" /></a></td>
          </tr>
        </table>
        """

        tasks = _parse_doing_task_list(page_html)

        self.assertEqual(tasks[0]["id"], "28")
        self.assertEqual(tasks[0]["progress"], "0")
        self.assertEqual(tasks[0]["can_draw"], "false")

    def test_parse_doing_task_list_marks_completed_tasks_drawable(self):
        page_html = """
        <table>
          <tr>
            <td class="bbda ptm pbm">
              <h3><a href="home.php?mod=task&amp;do=view&amp;id=28">使用道具熟悉论坛！</a></h3>
              <p class="xg2">使用道具即可完成任务</p>
              <div class="xs0">已完成 <span id="csc_28">100</span>%</div>
            </td>
            <td class="xi1 bbda hm">积分 旅程 1 里</td>
            <td><a href="home.php?mod=task&amp;do=draw&amp;id=28"><img src="static/image/task/reward.gif" /></a></td>
          </tr>
        </table>
        """

        tasks = _parse_doing_task_list(page_html)

        self.assertEqual(tasks[0]["can_draw"], "true")
        self.assertEqual(
            tasks[0]["draw_url"],
            "https://www.gamemale.com/home.php?mod=task&do=draw&id=28",
        )

    def test_task_exclusion_supports_id_name_and_keyword(self):
        task = {
            "id": "25",
            "name": "每周发帖任务",
            "description": "领取任务用以水贴套取奖励将被警告",
        }

        self.assertIn(
            "ID 25",
            GamemaleAutomation({"task_exclude_ids": ["25"]})._get_task_exclusion_reason(task),
        )
        self.assertIn(
            "任务名",
            GamemaleAutomation({"task_exclude_names": ["每周发帖任务"]})._get_task_exclusion_reason(task),
        )
        self.assertIn(
            "关键词",
            GamemaleAutomation({"task_exclude_keywords": ["水贴"]})._get_task_exclusion_reason(task),
        )

    def test_generic_task_exclude_splits_ids_and_keywords(self):
        id_task = {"id": "28", "name": "使用道具熟悉论坛！", "description": ""}
        keyword_task = {"id": "6", "name": "给标题漆上色彩！", "description": ""}
        client = GamemaleAutomation({"task_exclude": ["28", "标题"]})

        self.assertIn("ID 28", client._get_task_exclusion_reason(id_task))
        self.assertIn("关键词", client._get_task_exclusion_reason(keyword_task))

    def test_coerce_config_values(self):
        self.assertEqual(_coerce_config_list("25, 28；标题"), ["25", "28", "标题"])
        self.assertTrue(_coerce_config_bool("true"))
        self.assertFalse(_coerce_config_bool("关闭", default=True))

    def test_quick_accept_new_tasks_applies_non_excluded_tasks(self):
        page_html = """
        <table>
          <tr>
            <td class="bbda ptm pbm">
              <h3><a href="home.php?mod=task&amp;do=view&amp;id=6">给标题漆上色彩！</a></h3>
              <p class="xg2">变色卡免费大赠送</p>
            </td>
            <td class="xi1 bbda hm">道具 亮色刷 1 张</td>
            <td><a href="home.php?mod=task&amp;do=apply&amp;id=6"><img alt="apply" /></a></td>
          </tr>
        </table>
        """
        apply_calls = []
        client = GamemaleAutomation({"auto_accept_tasks": True})

        class FakeResponse:
            def __init__(self, text):
                self.text = text

        def fake_send_request(method, url, **kwargs):
            if "item=new" in url:
                return FakeResponse(page_html)
            apply_calls.append((method, url, kwargs))
            return FakeResponse('<div id="messagetext">恭喜您，任务已成功申请，请继续完成</div>')

        client._send_request = fake_send_request
        client._sleep = lambda seconds: None

        self.assertTrue(client.quick_accept_new_tasks())
        self.assertEqual(len(apply_calls), 1)
        self.assertEqual(apply_calls[0][0], "GET")
        self.assertEqual(
            apply_calls[0][1],
            "https://www.gamemale.com/home.php?mod=task&do=apply&id=6",
        )
        self.assertEqual(client.mission_summary["detected"], 1)
        self.assertEqual(client.mission_summary["accepted"], 1)
        self.assertEqual(client.mission_results[0]["id"], "6")
        self.assertEqual(client.mission_results[0]["status"], "accepted")

    def test_report_includes_accepted_missions(self):
        client = GamemaleAutomation({"username": "test"})
        client.mission_summary = {
            "detected": 2,
            "accepted": 1,
            "skipped": 1,
            "failed": 0,
        }
        client.mission_results = [
            {"id": "6", "name": "给标题漆上色彩！", "status": "accepted", "message": "ok"},
            {"id": "25", "name": "每周发帖任务", "status": "skipped", "message": "excluded"},
        ]

        report = client.generate_detailed_report({"接取新任务": True})

        self.assertIn("新任务接取:", report)
        self.assertIn("检测: 2 个", report)
        self.assertIn("[6] 给标题漆上色彩！: 已接取", report)
        self.assertNotIn("[25] 每周发帖任务", report)

    def test_quick_complete_doing_missions_draws_completed_tasks(self):
        doing_html = """
        <table>
          <tr>
            <td class="bbda ptm pbm">
              <h3><a href="home.php?mod=task&amp;do=view&amp;id=28">使用道具熟悉论坛！</a></h3>
              <p class="xg2">使用道具即可完成任务</p>
              <div class="xs0">已完成 <span id="csc_28">100</span>%</div>
            </td>
            <td class="xi1 bbda hm">积分 旅程 1 里</td>
            <td><a href="home.php?mod=task&amp;do=draw&amp;id=28"><img src="static/image/task/reward.gif" /></a></td>
          </tr>
        </table>
        """
        draw_calls = []
        client = GamemaleAutomation({"auto_complete_tasks": True})

        class FakeResponse:
            def __init__(self, text):
                self.text = text

        def fake_send_request(method, url, **kwargs):
            if "item=doing" in url:
                return FakeResponse(doing_html)
            draw_calls.append((method, url, kwargs))
            return FakeResponse('<div id="messagetext">恭喜您，任务已成功完成，您将收到奖励通知</div>')

        client._send_request = fake_send_request
        client._sleep = lambda seconds: None

        self.assertTrue(client.quick_complete_doing_missions())
        self.assertEqual(len(draw_calls), 1)
        self.assertEqual(
            draw_calls[0][1],
            "https://www.gamemale.com/home.php?mod=task&do=draw&id=28",
        )
        self.assertEqual(client.mission_summary["completed"], 1)
        self.assertEqual(client.mission_results[0]["status"], "completed")

    def test_quick_accumulate_online_time_refreshes_until_duration(self):
        calls = []
        sleeps = []
        client = GamemaleAutomation({
            "online_runtime_enabled": True,
            "online_time_seconds": 4,
            "online_refresh_interval_seconds": 2,
        })

        class FakeResponse:
            text = "ok"

        def fake_send_request(method, url, **kwargs):
            calls.append((method, url, kwargs))
            return FakeResponse()

        client._send_request = fake_send_request
        client._sleep = lambda seconds: sleeps.append(seconds)

        self.assertTrue(client.quick_accumulate_online_time())
        self.assertEqual(len(calls), 3)
        self.assertEqual(sleeps, [2, 2])
        self.assertEqual(client.online_time_summary["status"], "completed")
        self.assertEqual(client.online_time_summary["refresh_count"], 3)

    def test_online_time_report_is_included(self):
        client = GamemaleAutomation({"username": "test"})
        client.online_time_summary = {
            "enabled": True,
            "status": "completed",
            "duration_seconds": 900,
            "interval_seconds": 300,
            "refresh_count": 4,
        }

        report = client.generate_detailed_report({"挂机时长": True})

        self.assertIn("挂机时长:", report)
        self.assertIn("计划时长: 00:15:00", report)
        self.assertIn("刷新次数: 4", report)

    def test_runtime_online_time_args_enable_hang_for_this_run(self):
        accounts = [{"username": "a", "online_time_enabled": False}]
        args = Namespace(
            online_time_minutes=30,
            online_time_seconds=None,
            online_refresh_interval_seconds=60,
            enable_online=True,
            only_online=False,
        )

        apply_runtime_overrides(accounts, args)

        self.assertTrue(accounts[0]["online_runtime_enabled"])
        self.assertEqual(accounts[0]["online_time_seconds"], 1800)
        self.assertEqual(accounts[0]["online_refresh_interval_seconds"], 60)

    def test_runtime_online_config_is_ignored_without_enable_flag(self):
        accounts = [{
            "username": "a",
            "online_time_enabled": True,
            "online_time_seconds": 600,
            "online_refresh_interval_seconds": 60,
        }]
        args = Namespace(
            online_time_minutes=None,
            online_time_seconds=None,
            online_refresh_interval_seconds=60,
            enable_online=False,
            only_online=False,
        )

        apply_runtime_overrides(accounts, args)

        self.assertFalse(accounts[0]["online_runtime_enabled"])
        self.assertEqual(accounts[0]["online_time_seconds"], 600)

        client = GamemaleAutomation(accounts[0])
        client._send_request = lambda *args, **kwargs: self.fail("挂机未显式启用时不应刷新")
        self.assertTrue(client.quick_accumulate_online_time())
        self.assertEqual(client.online_time_summary["status"], "disabled")

    def test_runtime_online_duration_arg_alone_does_not_enable_hang(self):
        accounts = [{"username": "a"}]
        args = Namespace(
            online_time_minutes=30,
            online_time_seconds=None,
            online_refresh_interval_seconds=None,
            enable_online=False,
            only_online=False,
        )

        apply_runtime_overrides(accounts, args)

        self.assertFalse(accounts[0]["online_runtime_enabled"])
        self.assertNotIn("online_time_seconds", accounts[0])

    def test_enable_online_arg_can_use_configured_duration(self):
        accounts = [{"username": "a", "online_time_minutes": 15}]
        args = Namespace(
            online_time_minutes=None,
            online_time_seconds=None,
            online_refresh_interval_seconds=None,
            enable_online=True,
            only_online=False,
        )

        apply_runtime_overrides(accounts, args)

        self.assertTrue(accounts[0]["online_runtime_enabled"])
        client = GamemaleAutomation(accounts[0])
        enabled, duration_seconds, interval_seconds, _ = client._get_online_time_config()
        self.assertTrue(enabled)
        self.assertEqual(duration_seconds, 900)
        self.assertEqual(interval_seconds, 900)

    def test_runtime_only_online_arg_marks_accounts_for_online_only(self):
        accounts = [{"username": "a", "online_time_enabled": False}]
        args = Namespace(
            online_time_minutes=15,
            online_time_seconds=None,
            online_refresh_interval_seconds=None,
            enable_online=False,
            only_online=True,
        )

        apply_runtime_overrides(accounts, args)

        self.assertTrue(accounts[0]["only_online"])
        self.assertTrue(accounts[0]["online_runtime_enabled"])
        self.assertEqual(accounts[0]["online_time_seconds"], 900)

    def test_execute_all_tasks_only_online_runs_no_other_tasks(self):
        calls = []
        client = GamemaleAutomation({
            "username": "test",
            "only_online": True,
            "online_runtime_enabled": True,
            "online_time_seconds": 1,
            "online_refresh_interval_seconds": 1,
        })
        client.is_logged_in = True
        client.formhash = "abc123"
        client.quick_accumulate_online_time = lambda: calls.append("online") or True
        client.quick_daily_sign = lambda: calls.append("sign") or True
        client.quick_daily_lottery = lambda: calls.append("lottery") or True
        client._sleep = lambda seconds: None

        report = client.execute_all_tasks()

        self.assertEqual(calls, ["online"])
        self.assertIn("挂机时长", report)


if __name__ == "__main__":
    unittest.main()
