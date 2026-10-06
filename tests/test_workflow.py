import unittest
from unittest.mock import Mock, patch

from modules.gamemale_core.client import GamemaleAutomation


class WorkflowTests(unittest.TestCase):
    def test_successive_status_runs_keep_independent_asset_results(self):
        client = self.make_client({'run_mode': 'status'})
        client._get_credits = Mock(side_effect=[
            ({'血液': '10 滴'}, 'https://www.gamemale.com/'),
            ({'血液': '12 滴'}, 'https://www.gamemale.com/'),
        ])
        first = client.execute_all_tasks()
        second = client.execute_all_tasks()
        self.assertEqual(first.assets_after, (('血液', 10),))
        self.assertEqual(second.assets_after, (('血液', 12),))
        self.assertEqual(len(first.tasks), 2)
        self.assertEqual(len(second.tasks), 2)

    def test_stop_after_sign_prevents_later_actions_and_asset_queries(self):
        from modules.gamemale_core.stop_controller import StopController
        client = self.make_client()
        client._controller = StopController()
        client._get_credits = Mock(return_value=({'血液': '10 滴'}, 'https://www.gamemale.com/'))
        client.quick_daily_sign.side_effect = lambda: client._controller.request_stop() or True
        with patch('modules.gamemale_core.daily_tasks.interact_with_blogs',
                   side_effect=AssertionError('stopped workflow must not interact')):
            result = client.execute_all_tasks()
        self.assertTrue(result.stopped)
        self.assertFalse(result.succeeded)
        client.quick_daily_lottery.assert_not_called()
        client.quick_complete_doing_missions.assert_not_called()
        client._get_credits.assert_called_once()
        self.assertEqual(result.assets_after, ())

    def test_disabled_aliases_remain_skipped_without_mutating_configuration(self):
        from copy import deepcopy
        from modules.gamemale_core.social import BlogInteractionResult
        client = self.make_client({'auto_task_accept_enabled': '关闭', 'auto_draw_tasks': 'false'})
        original = deepcopy(client.config)
        with patch('modules.gamemale_core.daily_tasks.interact_with_blogs',
                   return_value=BlogInteractionResult(target=10, new_count=10)):
            result = client.execute_all_tasks()
        self.assertTrue(result.succeeded)
        self.assertEqual(client.config, original)
        client.quick_accept_new_tasks.assert_not_called()
        client.quick_complete_doing_missions.assert_not_called()
        statuses = {task.name: task.status for task in result.tasks}
        self.assertEqual(statuses['接取新任务'], 'skipped')
        self.assertEqual(statuses['完成任务'], 'skipped')

    def test_uncertain_exchange_submission_discards_pre_exchange_balance(self):
        import requests
        client = self.make_client({'password': 'placeholder', 'auto_exchange': True})
        client._get_credits = Mock(return_value=({'血液': '40 滴'}, 'https://www.gamemale.com/'))
        client._send_request = Mock(side_effect=requests.Timeout('offline submission uncertainty'))
        credits, exchanged = client.get_user_credits_and_exchange()
        self.assertEqual(credits, {})
        self.assertFalse(exchanged)
        client._send_request.assert_called_once()

    def test_failed_post_exchange_refresh_never_overwrites_asset_history(self):
        import tempfile
        from pathlib import Path
        from modules.gamemale_core.assets import merge_asset_record, save_asset_records
        from modules.gamemale_core.runner import run_all_accounts
        from modules.gamemale_core.social import BlogInteractionResult
        client = self.make_client({'password': 'placeholder', 'auto_exchange': True})
        client.uid = 123
        client.login = Mock(return_value=True)
        client._get_credits = Mock(side_effect=[
            ({'血液': '40 滴', '旅程': '5'}, 'https://www.gamemale.com/'),
            ({'血液': '40 滴', '旅程': '5'}, 'https://www.gamemale.com/'),
            RuntimeError('offline refresh failure'),
        ])
        client._send_request = Mock(return_value=Mock(text='积分操作成功'))
        with patch('modules.gamemale_core.daily_tasks.interact_with_blogs',
                   return_value=BlogInteractionResult(target=10, new_count=10)):
            result = client.execute_all_tasks()
        self.assertFalse(result.succeeded)
        self.assertEqual(result.assets_after, ())
        outcomes = {task.name: task.status for task in result.tasks}
        self.assertEqual(outcomes['血液兑换'], 'success')
        self.assertEqual(outcomes['资产查询'], 'failed')
        client.execute_all_tasks = Mock(return_value=result)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'assets.json'
            save_asset_records(path, merge_asset_record({}, 123, {'血液': 40, '旅程': 5}, 'earlier'))
            original = path.read_bytes()
            failed = run_all_accounts([client.config], client_factory=lambda *a, **k: client,
                                      asset_state_path=path)
            self.assertEqual(failed, 1)
            self.assertEqual(path.read_bytes(), original)

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
