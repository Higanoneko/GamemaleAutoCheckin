"""Verify extension-generated YAML against the actual Qinglong configuration loader."""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from modules.gamemale_core.configuration import load_runtime_config


ROOT = Path(__file__).resolve().parents[1]
CONFIG_MODULE = ROOT / 'extensions/gamemale-qinglong/lib/config.mjs'


@unittest.skipUnless(
    shutil.which('node') and CONFIG_MODULE.is_file(),
    'Extension interoperability check requires Node.js and the extension source',
)
class ExtensionConfigTests(unittest.TestCase):
    def test_generated_yaml_loads_with_string_credentials_and_retains_global_settings(self) -> None:
        module_url = CONFIG_MODULE.as_uri()
        javascript = """
import {buildAccount, renderConfig, mergeAccount, parseConfig} from MODULE_URL;
const account = buildAccount({cookie: 'auth=placeholder; cf_clearance=placeholder',
  username: 'true', password: ' # : " \\n 密码 ', questionid: '0', answer: '0123'});
const existing = parseConfig('cloudflare:\\n  solver: "capsolver"\\n  api_key: "placeholder"\\naccounts:\\n  - cookie: "auth=old"\\n    username: "existing"\\n');
process.stdout.write(renderConfig(mergeAccount(existing, account, null)));
""".replace('MODULE_URL', json.dumps(module_url))
        generated = subprocess.run(
            ['node', '--input-type=module', '-e', javascript], check=True,
            capture_output=True, encoding='utf-8', cwd=ROOT, timeout=15,
        ).stdout
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'GameMale_Config.yaml'
            path.write_text(generated, encoding='utf-8')
            config = load_runtime_config(path, environ={})
        self.assertEqual(config['_source'], 'GameMale_Config.yaml')
        self.assertEqual(len(config['accounts']), 2)
        self.assertEqual(config['accounts'][0]['username'], 'existing')
        account = config['accounts'][1]
        self.assertEqual(account['username'], 'true')
        self.assertEqual(account['password'], ' # : " \n 密码 ')
        self.assertEqual(account['questionid'], '0')
        self.assertEqual(account['answer'], '0123')
        self.assertIs(account['notify_enabled'], True)
        self.assertIs(account['auto_exchange'], False)
        self.assertEqual(account['online_refresh_interval_seconds'], 900)
        self.assertEqual(config['cloudflare'], {'solver': 'capsolver', 'api_key': 'placeholder'})


if __name__ == '__main__':
    unittest.main()
