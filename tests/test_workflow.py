import unittest
from unittest.mock import Mock, patch

from modules.gamemale_core.client import GamemaleAutomation


class WorkflowTests(unittest.TestCase):
    def make_client(self, config=None):
        client = GamemaleAutomation(dict({'username': 'offline', 'auto_exchange': False}, **(config or {})))
        client.is_logged_in = True
        client.formhash = 'placeholder'
        client._sleep = lambda _: None
        client._send_request = Mock(side_effect=AssertionError('offline test must not access network'))
        client._get_credits = lambda: ({'血液': '10 滴'}, 'https://www.gamemale.com/')
        client.get_daily_task_summary = lambda: []
        for method in ('quick_daily_sign', 'quick_daily_lottery', 'quick_accept_new_tasks',
                       'quick_complete_doing_missions', 'quick_visit_spaces', 'quick_poke_users'):
            setattr(client, method, Mock(return_value=True))
        return client

    def test_rewards_are_checked_after_social_actions(self):
        from modules.gamemale_core.social import BlogInteractionResult
        client = self.make_client()
        calls = []
        client.quick_poke_users.side_effect = lambda _: calls.append('poke') or True
        client.quick_complete_doing_missions.side_effect = lambda: calls.append('draw') or True
        with patch('modules.gamemale_core.daily_tasks.interact_with_blogs', return_value=BlogInteractionResult(
            target=10, new_count=10, successful_uids=('1',), processed_uids=('1',),
        )):
            result = client.execute_all_tasks()
        self.assertEqual(calls, ['poke', 'draw'])
        self.assertTrue(result.succeeded)

    def test_status_mode_does_not_exchange_or_run_daily_actions(self):
        client = self.make_client({'run_mode': 'status', 'auto_exchange': True})
        client.get_user_credits_and_exchange = Mock(side_effect=AssertionError('must not exchange'))
        result = client.execute_all_tasks()
        self.assertTrue(result.succeeded)
        client.quick_daily_sign.assert_not_called()
        client.quick_accept_new_tasks.assert_not_called()
        client.quick_complete_doing_missions.assert_not_called()
        client.get_user_credits_and_exchange.assert_not_called()

    def test_failed_sign_makes_account_fail_even_when_report_exists(self):
        from modules.gamemale_core.social import BlogInteractionResult
        client = self.make_client()
        client.quick_daily_sign.return_value = False
        with patch('modules.gamemale_core.daily_tasks.interact_with_blogs', return_value=BlogInteractionResult(target=10)):
            result = client.execute_all_tasks()
        self.assertFalse(result.succeeded)
        self.assertIn('签到: ❌ 失败', result.report)


if __name__ == '__main__':
    unittest.main()
