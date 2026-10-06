"""Validate browser manifests and package contents without network."""

import importlib.util
import json
from pathlib import Path
import tempfile
from types import ModuleType
import unittest
from zipfile import ZipFile


SOURCE = Path(__file__).resolve().parents[1] / 'extensions/gamemale-qinglong'


def load_builder() -> ModuleType:
    spec = importlib.util.spec_from_file_location('extension_build', SOURCE / 'build.py')
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless((SOURCE / 'build.py').is_file(), 'Extension source is not included in this checkout')
class ExtensionBuildTests(unittest.TestCase):
    def test_firefox_manifest_has_identity_minimum_version_and_data_declaration(self) -> None:
        builder = load_builder()
        original = json.loads((SOURCE / 'manifest.json').read_text(encoding='utf-8'))
        serialized = json.dumps(original)
        manifest = builder.build_manifest(original, 'firefox')
        gecko = manifest['browser_specific_settings']['gecko']
        self.assertEqual(gecko['strict_min_version'], '140.0')
        self.assertEqual(manifest['browser_specific_settings']['gecko_android']['strict_min_version'], '142.0')
        self.assertEqual(gecko['id'], 'gamemale-qinglong@gamemaleautocheckin')
        self.assertEqual(gecko['data_collection_permissions']['required'], ['authenticationInfo', 'websiteContent'])
        self.assertEqual(json.dumps(original), serialized)
        self.assertNotIn('browser_specific_settings', builder.build_manifest(original, 'chrome'))
        with self.assertRaises(ValueError):
            builder.build_manifest(original, 'unsupported')

    def test_packages_include_runtime_imports_and_exclude_local_credentials(self) -> None:
        builder = load_builder()
        with tempfile.TemporaryDirectory() as folder:
            for browser in ('chrome', 'firefox'):
                output = Path(folder) / f'{browser}.zip'
                builder.build_archive(SOURCE, output, browser)
                with ZipFile(output) as archive:
                    self.assertIsNone(archive.testzip())
                    self.assertEqual(set(archive.namelist()), {'manifest.json', *builder.RUNTIME_FILES})
                    self.assertNotIn('build.py', archive.namelist())
                    self.assertIn('lib/browser-api.mjs', archive.namelist())
                    self.assertIn('PRIVACY.md', archive.namelist())
                    manifest = json.loads(archive.read('manifest.json'))
                    self.assertEqual('browser_specific_settings' in manifest, browser == 'firefox')
                    self.assertEqual(archive.read('options.mjs'), (SOURCE / 'options.mjs').read_bytes())


if __name__ == '__main__':
    unittest.main()
