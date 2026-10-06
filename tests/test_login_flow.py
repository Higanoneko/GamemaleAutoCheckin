import unittest
from unittest.mock import Mock

from modules.gamemale_core.client import GamemaleAutomation


def response(text, content=b'', content_type='text/html'):
    return Mock(text=text, content=content, status_code=200,
                headers={'Content-Type': content_type})


class LoginFlowTests(unittest.TestCase):
    def test_form_without_captcha_logs_in_without_ocr(self):
        client = GamemaleAutomation({'username': 'offline', 'password': 'placeholder'})
        client._init_ocr = Mock(side_effect=AssertionError('OCR must be optional'))
        client._send_request = Mock(side_effect=[
            response('<form name="login" action="member.php?loginhash=abc"><input name="formhash" value="ab12cd34"></form>'),
            response('<root><![CDATA[succeed]]></root>'),
            response('<script>var discuz_uid=123;</script>'),
            response('<input name="formhash" value="ab12cd34">'),
        ])
        self.assertTrue(client.login())
        self.assertEqual(client.uid, 123)
        self.assertEqual(client.formhash, "ab12cd34")
        client._init_ocr.assert_not_called()

    def test_unknown_cookie_page_does_not_trigger_password_login(self):
        client = GamemaleAutomation({'username': 'offline', 'password': 'placeholder', 'cookie': 'Cookie: auth=placeholder'})
        client._send_request = Mock(return_value=response('<html>unexpected page</html>'))
        client._login_with_password = Mock(side_effect=AssertionError('must not discard unknown session'))
        self.assertFalse(client.login())
        self.assertEqual(client.session.cookies.get('auth'), 'placeholder')
        client._login_with_password.assert_not_called()

    def test_explicit_guest_redirect_allows_password_fallback(self):
        client = GamemaleAutomation({'username': 'offline', 'password': 'placeholder', 'cookie': 'TV_auth=expired'})
        guest = response('')
        guest.status_code = 302
        guest.headers['Location'] = 'member.php?mod=logging&action=login'
        client._send_request = Mock(side_effect=[guest, response('<input name="formhash" value="ab12cd34">')])
        client._login_with_password = Mock(return_value=True)
        self.assertTrue(client.login())
        client._login_with_password.assert_called_once()
        self.assertIsNone(client.session.cookies.get('TV_auth'))

    def test_captcha_modid_and_server_precheck_are_used_before_login(self):
        client = GamemaleAutomation({'username': 'offline', 'password': 'placeholder', 'captcha_max_retries': 1})
        client._init_ocr = Mock(return_value=True)
        client._ocr = Mock(classification=Mock(return_value='AB12'))
        client._send_request = Mock(side_effect=[
            response('<form name="login" action="member.php?loginhash=abc"><input name="formhash" value="ab12cd34">'
                     '<span id="seccode_xyz"></span><script>updateseccode("xyz", "", "custom::logging")</script></form>'),
            response('<img src="misc.php?mod=seccode&amp;idhash=xyz&amp;update=1">'),
            response('', b'fake-image', 'image/png'),
            response('<root><![CDATA[succeed]]></root>'),
            response('succeed'),
            response('<script>var discuz_uid=123;</script>'),
            response('<input name="formhash" value="ab12cd34">'),
        ])
        self.assertTrue(client.login())
        calls = client._send_request.call_args_list
        self.assertEqual(calls[1].kwargs['params']['modid'], 'custom::logging')
        self.assertEqual(calls[3].kwargs['params']['secverify'], 'AB12')
        self.assertEqual(calls[4].args[0], 'POST')

    def test_non_image_captcha_does_not_reach_ocr_or_password_submission(self):
        client = GamemaleAutomation({'username': 'offline', 'password': 'placeholder', 'captcha_max_retries': 1})
        client._init_ocr = Mock(return_value=True)
        client._ocr = Mock()
        client._send_request = Mock(side_effect=[
            response('<form name="login" action="member.php?loginhash=abc"><input name="formhash" value="ab12cd34">'
                     '<span id="seccode_xyz"></span></form>'),
            response('<img src="misc.php?mod=seccode&idhash=xyz&update=1">'),
            response('<html>not an image</html>', b'not an image', 'text/html'),
        ])
        self.assertFalse(client.login())
        client._ocr.classification.assert_not_called()
        self.assertEqual(client._send_request.call_count, 3)


if __name__ == '__main__':
    unittest.main()
