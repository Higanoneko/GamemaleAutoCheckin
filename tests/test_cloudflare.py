# -*- coding: utf-8 -*-
"""Tests for Cloudflare Turnstile challenge detection and auto-solving flow."""

import unittest
from unittest.mock import Mock, patch

from requests.cookies import RequestsCookieJar

from modules.gamemale_core import cloudflare
from modules.gamemale_core.client import GamemaleAutomation

CHALLENGE_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>请稍候...</title>
    <script src="https://challenges.cloudflare.com/turnstile/v0/api.js" type="text/javascript"></script>
    <script src="source/plugin/dev8133_cloudflare/static/js/jquery-3.3.1.min.js" type="text/javascript"></script>
</head>
<body>
<div class="verify-card">
    <div class="domain-title">www.gamemale.com</div>
    <div id="turnstile"></div>
</div>
<script>
turnstile.ready(function () {
    widgetId = turnstile.render("#turnstile", {
        sitekey: "0x4AAAAAAEqRGyPbvEznAcKy",
        appearance: "always",
        callback: function (token) { /* post to plugin.php?id=dev8133_cloudflare */ }
    });
});
</script>
</body>
</html>"""

NORMAL_HTML = """<html><head><title>GameMale 论坛</title></head>
<body><form><input type="hidden" name="formhash" value="a1b2c3d4" /></form></body></html>"""


class ChallengeDetectionTests(unittest.TestCase):
    def test_detects_dev8133_challenge_page(self):
        self.assertTrue(cloudflare.is_turnstile_challenge(CHALLENGE_HTML))

    def test_normal_forum_page_is_not_challenge(self):
        self.assertFalse(cloudflare.is_turnstile_challenge(NORMAL_HTML))

    def test_empty_or_none_text_is_not_challenge(self):
        self.assertFalse(cloudflare.is_turnstile_challenge(""))
        self.assertFalse(cloudflare.is_turnstile_challenge(None))

    def test_extracts_sitekey(self):
        self.assertEqual(
            cloudflare.extract_turnstile_sitekey(CHALLENGE_HTML),
            "0x4AAAAAAEqRGyPbvEznAcKy",
        )

    def test_extract_sitekey_returns_none_without_match(self):
        self.assertIsNone(cloudflare.extract_turnstile_sitekey(NORMAL_HTML))

    def test_normalize_solver_aliases(self):
        self.assertEqual(cloudflare.normalize_solver("2captcha"), "2captcha")
        self.assertEqual(cloudflare.normalize_solver("Capsolver"), "capsolver")
        self.assertEqual(cloudflare.normalize_solver("yes-captcha"), "yescaptcha")
        self.assertEqual(cloudflare.normalize_solver("cap_monster"), "capsolver")

    def test_normalize_solver_rejects_unknown(self):
        with self.assertRaises(ValueError):
            cloudflare.normalize_solver("unknown-service")


class SolverApiErrorTests(unittest.TestCase):
    @patch("modules.gamemale_core.cloudflare.requests.post")
    def test_captcha2_create_task_error_raises(self, mock_post):
        mock_post.return_value = Mock(
            status_code=200,
            json=lambda: {"status": 0, "error_text": "ERROR_ZERO_BALANCE"},
            raise_for_status=lambda: None,
        )
        with self.assertRaises(cloudflare.CloudflareSolverError) as ctx:
            cloudflare._create_captcha2_task("key", "sitekey", "https://www.gamemale.com/")
        self.assertIn("ERROR_ZERO_BALANCE", str(ctx.exception))

    @patch("modules.gamemale_core.cloudflare.requests.post")
    def test_capsolver_create_task_error_raises(self, mock_post):
        mock_post.return_value = Mock(
            status_code=400,
            json=lambda: {"errorId": 1, "errorCode": "ERROR_ACCOUNT_SUSPENDED"},
            raise_for_status=lambda: None,
        )
        with self.assertRaises(cloudflare.CloudflareSolverError) as ctx:
            cloudflare._create_task(
                cloudflare.CAPSOLVER_BASE, "key", "sitekey", "https://www.gamemale.com/"
            )
        self.assertIn("ERROR_ACCOUNT_SUSPENDED", str(ctx.exception))
        self.assertIn("400", str(ctx.exception))

    def test_solve_requires_api_key(self):
        with self.assertRaises(cloudflare.CloudflareSolverError):
            cloudflare.solve_turnstile("2captcha", "", "sitekey", "https://www.gamemale.com/")


class SubmitTokenTests(unittest.TestCase):
    def test_submit_accepts_valid_token(self):
        session = Mock()
        session.post.return_value = Mock(
            json=lambda: {"code": 200, "message": "ok"},
            raise_for_status=lambda: None,
        )
        self.assertTrue(
            cloudflare.submit_turnstile_token(session, "token123", "https://www.gamemale.com/forum.php")
        )
        url = session.post.call_args[0][0]
        self.assertIn("plugin.php?id=dev8133_cloudflare", url)

    def test_submit_rejects_fail_code(self):
        session = Mock()
        session.post.return_value = Mock(
            json=lambda: {"code": -1, "message": "fail"},
            raise_for_status=lambda: None,
        )
        self.assertFalse(
            cloudflare.submit_turnstile_token(session, "bad", "https://www.gamemale.com/forum.php")
        )


class ChallengeAutoSolveFlowTests(unittest.TestCase):
    def _make_client(
        self,
        first_challenge=True,
        config=None,
        challenge_twice=False,
        pool=None,
        cf_config=None,
    ):
        config = dict(config or {})
        config.setdefault("username", "test")
        client = GamemaleAutomation(
            config, cf_share=pool, cloudflare_config=cf_config,
        )

        responses = []

        def make_response(text):
            resp = Mock()
            resp.text = text
            resp.url = "https://www.gamemale.com/forum.php"
            resp.status_code = 200
            resp.raise_for_status = lambda: None
            return resp

        if first_challenge:
            responses.append(make_response(CHALLENGE_HTML))
        if challenge_twice:
            responses.append(make_response(CHALLENGE_HTML))
        responses.append(make_response(NORMAL_HTML))

        class FakeSession:
            def __init__(self):
                self.calls = []
                self.cookies = RequestsCookieJar()

            def request(self, method, url, **kwargs):
                self.calls.append((method, url))
                resp = responses.pop(0)
                return resp

            def post(self, url, data=None, **kwargs):
                # 模拟论坛验证接口：验证成功(code==200)时种下放行 Cookie，
                # 同时刷新常规会话 Cookie（saltkey），用于测试放行 Cookie 收集过滤
                self.cookies.set("dev8133_cf_pass", "ok", domain=".gamemale.com")
                self.cookies.set("TVj0_2132_saltkey", "abc", domain="www.gamemale.com")
                return Mock(
                    json=lambda: {"code": 200, "message": "ok"},
                    raise_for_status=lambda: None,
                )

        fake_session = FakeSession()
        client.session = fake_session
        return client

    @patch("modules.gamemale_core.client.solve_turnstile", return_value="fake-token")
    def test_send_request_solves_challenge_and_replays(self, mock_solve):
        client = self._make_client(
            cf_config={"solver": "2captcha", "api_key": "secret-key"}
        )

        response = client._send_request("GET", "https://www.gamemale.com/forum.php")

        self.assertEqual(response.text, NORMAL_HTML)
        self.assertEqual(len(client.session.calls), 2)
        self.assertEqual(client._cf_solved_count, 1)
        mock_solve.assert_called_once()
        args, kwargs = mock_solve.call_args
        self.assertEqual(args[:3], ("2captcha", "secret-key", "0x4AAAAAAEqRGyPbvEznAcKy"))
        self.assertIn("should_stop", kwargs)

    def test_send_request_without_solver_config_does_not_replay(self):
        client = self._make_client()

        response = client._send_request("GET", "https://www.gamemale.com/forum.php")

        self.assertEqual(response.text, CHALLENGE_HTML)
        self.assertEqual(len(client.session.calls), 1)
        self.assertEqual(client._cf_solved_count, 0)

    @patch("modules.gamemale_core.client.solve_turnstile", return_value="fake-token")
    def test_send_request_stops_after_max_solves(self, mock_solve):
        client = self._make_client(
            challenge_twice=True,
            cf_config={"solver": "capsolver", "api_key": "k", "max_solves": 1},
        )

        response = client._send_request("GET", "https://www.gamemale.com/forum.php")

        # 第一次命中挑战 → 解算 → 重放仍命中挑战 → 解算次数已达上限 → 返回验证页
        self.assertEqual(response.text, CHALLENGE_HTML)
        self.assertEqual(client._cf_solved_count, 1)
        self.assertEqual(len(client.session.calls), 2)

    def test_env_fallback_config_resolution(self):
        with patch.dict(
            "os.environ",
            {"GAMEMALE_CF_SOLVER": "yescaptcha", "GAMEMALE_CF_API_KEY": "env-key"},
        ):
            client = GamemaleAutomation({"username": "t"})
            solver, api_key = client._get_cloudflare_solver_config()
            self.assertEqual(solver, "yescaptcha")
            self.assertEqual(api_key, "env-key")

    def test_top_level_cloudflare_config_takes_priority_over_env(self):
        with patch.dict(
            "os.environ",
            {"GAMEMALE_CF_SOLVER": "yescaptcha", "GAMEMALE_CF_API_KEY": "env-key"},
        ):
            client = GamemaleAutomation(
                {"username": "t"},
                cloudflare_config={"solver": "capsolver", "api_key": "cfg-key"},
            )
            solver, api_key = client._get_cloudflare_solver_config()
            self.assertEqual(solver, "capsolver")
            self.assertEqual(api_key, "cfg-key")

    def test_max_solves_from_top_level_cloudflare_config(self):
        client = GamemaleAutomation(
            {"username": "t"},
            cloudflare_config={"max_solves": 5},
        )
        self.assertEqual(client._cf_max_solves, 5)
        client = GamemaleAutomation({"username": "t"})
        self.assertEqual(client._cf_max_solves, 2)


class SharedPassPoolTests(unittest.TestCase):
    """多账户共享放行 Cookie：第一个账户打码，后续账户复用，避免重复打码。"""

    API_CONFIG = {"solver": "2captcha", "api_key": "api-key"}

    @patch("modules.gamemale_core.client.solve_turnstile", return_value="token-1")
    def test_second_account_reuses_pool_and_skips_api(self, mock_api):
        from modules.gamemale_core.cloudflare import CloudflarePassPool

        pool = CloudflarePassPool()
        # 账户 A：命中挑战 → 打码成功 → 放行 Cookie 进入共享池
        client_a = ChallengeAutoSolveFlowTests._make_client(
            self, cf_config=dict(self.API_CONFIG), pool=pool,
        )
        response_a = client_a._send_request("GET", "https://www.gamemale.com/forum.php")
        self.assertEqual(response_a.text, NORMAL_HTML)
        self.assertEqual(client_a._cf_solved_count, 1)

        # 池里应只有放行 Cookie，常规会话 Cookie（saltkey 等）被过滤
        pool_names = [item[0] for item in pool.items()]
        self.assertIn("dev8133_cf_pass", pool_names)
        self.assertNotIn("TVj0_2132_saltkey", pool_names)

        # 账户 B（同一池）：命中挑战 → 直接复用池中 Cookie，不再打码
        client_b = ChallengeAutoSolveFlowTests._make_client(
            self, cf_config=dict(self.API_CONFIG), pool=pool,
        )
        mock_api.reset_mock()
        response_b = client_b._send_request("GET", "https://www.gamemale.com/forum.php")
        self.assertEqual(response_b.text, NORMAL_HTML)
        self.assertEqual(client_b._cf_solved_count, 0)
        mock_api.assert_not_called()
        # B 的会话确实拿到了共享的放行 Cookie
        self.assertIsNotNone(client_b.session.cookies.get("dev8133_cf_pass"))

    @patch("modules.gamemale_core.client.solve_turnstile", return_value="token-2")
    def test_account_uses_own_solve_when_shared_cookie_does_not_pass(self, mock_api):
        from modules.gamemale_core.cloudflare import CloudflarePassPool

        pool = CloudflarePassPool()
        # 账户 A：打码成功并共享
        client_a = ChallengeAutoSolveFlowTests._make_client(
            self, cf_config=dict(self.API_CONFIG), pool=pool,
        )
        client_a._send_request("GET", "https://www.gamemale.com/forum.php")
        self.assertEqual(mock_api.call_count, 1)

        # 账户 B：复用共享 Cookie 后重放仍命中挑战（放行失效/不适用）→ 自己打码兜底
        mock_api.reset_mock()
        client_b = ChallengeAutoSolveFlowTests._make_client(
            self, cf_config=dict(self.API_CONFIG), pool=pool, challenge_twice=True,
        )
        response_b = client_b._send_request("GET", "https://www.gamemale.com/forum.php")
        self.assertEqual(response_b.text, NORMAL_HTML)  # 兜底打码成功后放行
        self.assertEqual(mock_api.call_count, 1)  # 仅尝试一次打码（受次数上限保护）
        self.assertEqual(client_b._cf_solved_count, 1)


class CookieSelectionTests(unittest.TestCase):
    """放行 Cookie 选取/过滤纯函数。"""

    def test_select_pass_cookies_filters_session_and_known_cookies(self):
        cookies = [
            ("dev8133_cf_pass", "ok", ".gamemale.com"),
            ("TVj0_2132_saltkey", "abc", "www.gamemale.com"),
            ("server_name_session", "x", "www.gamemale.com"),
            ("other_site", "v", "example.com"),
        ]
        selected = cloudflare.select_pass_cookies({"TVj0_2132_saltkey"}, cookies)
        self.assertEqual(selected, [("dev8133_cf_pass", "ok", ".gamemale.com")])

    def test_select_pass_cookies_drops_cookies_present_before_solve(self):
        cookies = [
            ("pre_existing", "1", "www.gamemale.com"),
            ("new_marker", "2", "www.gamemale.com"),
        ]
        selected = cloudflare.select_pass_cookies({"pre_existing"}, cookies)
        self.assertEqual(selected, [("new_marker", "2", "www.gamemale.com")])

    def test_filter_gamemale_cookies_keeps_only_domain_and_named(self):
        cookies = [
            ("", "empty-name", ".gamemale.com"),
            ("keep", "v", "www.gamemale.com"),
            ("skip", "v", "example.com"),
        ]
        self.assertEqual(
            cloudflare.filter_gamemale_cookies(cookies),
            [("keep", "v", "www.gamemale.com")],
        )


class LoginCookieRewriteTests(unittest.TestCase):
    def _client(self, cf_solved):
        client = GamemaleAutomation({"username": "u", "cookie": "a=1; b=2"})
        client._login_with_cookie = Mock(return_value=True)
        client.get_and_store_formhash = Mock(return_value=True)
        client._cf_solved_count = cf_solved
        saved = []
        client._save_cookie_callback = lambda c: saved.append(True)
        return client, saved

    def test_cookie_login_saves_cookie_after_cf_solve(self):
        client, saved = self._client(cf_solved=1)
        self.assertTrue(client.login())
        self.assertEqual(len(saved), 1)

    def test_cookie_login_without_cf_solve_keeps_original_behavior(self):
        client, saved = self._client(cf_solved=0)
        self.assertTrue(client.login())
        self.assertEqual(len(saved), 0)


if __name__ == "__main__":
    unittest.main()
