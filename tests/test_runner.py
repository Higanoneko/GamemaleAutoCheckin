import unittest
import tempfile
from pathlib import Path
from unittest.mock import Mock

from modules.gamemale_core.results import AccountRunResult, TaskResult
from modules.gamemale_core.runner import run_all_accounts


class RunnerTests(unittest.TestCase):
    def test_task_result_boolean_reflects_status_for_existing_callers(self):
        for status in ('failed', 'unknown', 'stopped'):
            self.assertFalse(bool(TaskResult('签到', status)))
        for status in ('success', 'already_done', 'skipped'):
            self.assertTrue(bool(TaskResult('签到', status)))

    def test_failed_task_report_is_not_counted_as_success(self):
        client = Mock()
        client.login.return_value = True
        client.execute_all_tasks.return_value = AccountRunResult(
            'offline', (TaskResult('签到', 'failed'),), 'failed sign report',
        )
        notifications = []
        failed = run_all_accounts([{'cookie': 'placeholder'}], client_factory=lambda *a, **k: client,
                                  send_notification=lambda title, text: notifications.append(text))
        self.assertEqual(failed, 1)
        self.assertEqual(notifications, ['failed sign report'])
        client.close.assert_called_once()

    def test_login_failure_is_reported_and_session_closed(self):
        client = Mock()
        client.login.return_value = False
        notifications = []
        failed = run_all_accounts([{'username': 'offline', 'cookie': 'placeholder'}],
                                  client_factory=lambda *a, **k: client,
                                  send_notification=lambda title, text: notifications.append(text))
        self.assertEqual(failed, 1)
        self.assertIn('登录失败', notifications[0])
        client.close.assert_called_once()

    def test_disabled_notifications_and_skipped_tasks_are_respected(self):
        client = Mock()
        client.login.return_value = True
        client.execute_all_tasks.return_value = AccountRunResult(
            'offline', (TaskResult('挂机', 'skipped'),), 'skipped',
        )
        notify = Mock()
        failed = run_all_accounts([{'cookie': 'placeholder', 'notify_enabled': False}],
                                  client_factory=lambda *a, **k: client, send_notification=notify)
        self.assertEqual(failed, 0)
        notify.assert_not_called()

    def test_check_mode_never_saves_cookie_or_asset_history(self):
        client = Mock(uid=123)
        client.login.return_value = True
        client.execute_all_tasks.return_value = AccountRunResult(
            'offline', (TaskResult('资产查询', 'success'),), 'check report', assets_after=(('血液', 10),),
        )
        factory = Mock(return_value=client)
        saver = Mock()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'assets.json'
            self.assertEqual(run_all_accounts([{'cookie': 'placeholder', 'run_mode': 'check'}],
                             client_factory=factory, save_cookie_callback=saver, asset_state_path=path), 0)
            self.assertFalse(path.exists())
        self.assertIsNone(factory.call_args.kwargs['save_cookie_callback'])

    def test_history_uses_verified_uid_and_retains_other_accounts(self):
        from modules.gamemale_core.assets import load_asset_records, merge_asset_record, save_asset_records, previous_snapshot
        client = Mock(uid=123)
        client.login.return_value = True
        client.execute_all_tasks.return_value = AccountRunResult(
            'offline', (TaskResult('资产查询', 'success'),), 'status report', assets_after=(('血液', 12),),
        )
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'assets.json'
            records = merge_asset_record({}, 999, {'金币': 99}, 'earlier')
            records = merge_asset_record(records, 123, {'血液': 10}, 'earlier')
            save_asset_records(path, records)
            notifications = []
            run_all_accounts([{'cookie': 'placeholder', 'run_mode': 'status'}],
                             client_factory=lambda *a, **k: client, asset_state_path=path,
                             send_notification=lambda title, text: notifications.append(text))
            self.assertEqual(previous_snapshot(load_asset_records(path), 999), {'金币': 99})
            self.assertIn('血液: +2', notifications[0])


if __name__ == '__main__':
    unittest.main()
