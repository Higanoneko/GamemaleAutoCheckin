import json
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from gamemale_daily import apply_runtime_overrides
from modules.gamemale_core.config_utils import normalize_config
from modules.gamemale_core.configuration import load_runtime_config, create_cookie_saver, save_cookie_to_file


class ConfigurationTests(unittest.TestCase):
    def test_cloudflare_diagnostics_match_client_normalization(self):
        from modules.gamemale_core.client import GamemaleAutomation
        from modules.gamemale_core.runtime import configuration_diagnostics
        cases = (
            ({'solver': ' Capsolver ', 'api_key': ' key '}, {}, True),
            ({'solver': 'yes-captcha', 'api_key': 'key'}, {}, True),
            ({'solver': 'unknown', 'api_key': 'key'}, {}, False),
            ({'solver': 'capsolver', 'api_key': '   '}, {}, False),
            ({'solver': '   ', 'api_key': '   '}, {'CF_SOLVER': 'capsolver', 'CF_API_KEY': 'key'}, True),
        )
        for cf, environment, expected in cases:
            with self.subTest(cf=cf), patch.dict('os.environ', environment, clear=True):
                account = {'cookie': 'auth=placeholder', 'cloudflare': cf}
                client = GamemaleAutomation(account)
                try:
                    solver, key = client._get_cloudflare_solver_config()
                    _, lines = configuration_diagnostics({'accounts': [account]}, environment)
                    self.assertEqual(bool(solver and key), expected)
                    self.assertEqual('兜底 已配置' in lines[-1], expected)
                finally:
                    client.close()

    def test_json_accounts_and_global_cloudflare_travel_together(self):
        with tempfile.TemporaryDirectory() as folder:
            config = load_runtime_config(Path(folder) / 'absent.yaml', environ={
                'APP_CONFIG_JSON': json.dumps({
                    'accounts': [{'username': 'offline', 'cookie': 'placeholder'}],
                    'cloudflare': {'solver': 'capsolver', 'api_key': 'placeholder'},
                }),
            })
        self.assertEqual(config['accounts'][0]['username'], 'offline')
        self.assertEqual(config['cloudflare']['solver'], 'capsolver')

    def test_legacy_and_direct_environment_accounts_are_supported(self):
        self.assertEqual(normalize_config({'gamemale': {'username': 'offline'}})['accounts'], [{'username': 'offline'}])
        with tempfile.TemporaryDirectory() as folder:
            config = load_runtime_config(Path(folder) / 'absent.yaml', environ={
                'GAMEMALE_ACCOUNTS': '[{"username":"offline","cookie":"placeholder"}]',
            })
        self.assertEqual(len(config['accounts']), 1)

    def test_invalid_roots_and_account_types_have_explicit_errors(self):
        for raw in (None, [], {'accounts': 'bad'}, {'accounts': [False]}, {'cloudflare': []}):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                normalize_config(raw)

    def test_overrides_return_new_values_without_mutating_config(self):
        original = [{'username': 'offline', 'online_time_minutes': 5}]
        args = Namespace(online_time_seconds=7, online_time_minutes=None,
                         enable_online=True, only_online=False, online_refresh_interval_seconds=None)
        updated = apply_runtime_overrides(original, args)
        self.assertNotIn('online_runtime_enabled', original[0])
        self.assertEqual(updated[0]['online_time_seconds'], 7)

    def test_yaml_takes_priority_over_environment_and_empty_yaml_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'config.yaml'
            path.write_text('accounts:\n  - username: file-account\n', encoding='utf-8')
            config = load_runtime_config(path, environ={'APP_CONFIG_JSON': '{broken'})
            self.assertEqual(config['accounts'][0]['username'], 'file-account')
            path.write_text('', encoding='utf-8')
            with self.assertRaises(ValueError):
                load_runtime_config(path, environ={})

    def test_legacy_json_cookie_save_preserves_structure_and_checks_owner(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'config.json'
            path.write_text(json.dumps({'gamemale': {'username': 'one', 'cookie': 'old'}, 'extra': 1}), encoding='utf-8')
            self.assertFalse(save_cookie_to_file(path, 0, 'new', {'username': 'two'}))
            self.assertTrue(save_cookie_to_file(path, 0, 'new', {'username': 'one'}))
            saved = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(saved, {'gamemale': {'username': 'one', 'cookie': 'new'}, 'extra': 1})
            self.assertIsNone(create_cookie_saver({'_source': 'APP_CONFIG_JSON', 'accounts': []}, path.with_suffix('.yaml'), path))

    def test_both_entrypoints_offline_diagnostics_do_not_run_accounts_or_leak_values(self):
        import gamemale_daily
        with patch('signal.signal'):
            import gamemale_daily_ql
        config = {'_source': 'APP_CONFIG_JSON', 'accounts': [{'cookie': 'auth=private-cookie-value',
                  'username': 'offline', 'password': 'private-password'}],
                  'cloudflare': {'solver': 'capsolver', 'api_key': 'private-api-key'}}
        for module in (gamemale_daily, gamemale_daily_ql):
            with self.subTest(module=module.__name__), patch('sys.argv', ['program', '--check-config']), \
                    patch.object(module, 'load_runtime_config', return_value=config), \
                    patch.object(module, 'run_all_accounts', side_effect=AssertionError('no network')), \
                    redirect_stdout(io.StringIO()) as output:
                module.main()
                text = output.getvalue()
                self.assertIn('账户数量: 1', text)
                for credential in ('private-cookie-value', 'private-password', 'private-api-key'):
                    self.assertNotIn(credential, text)


if __name__ == '__main__':
    unittest.main()
