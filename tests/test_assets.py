import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from modules.gamemale_core.assets import (
    asset_deltas, atomic_write_text, load_asset_records, merge_asset_record,
    parse_asset_snapshot, previous_snapshot, save_asset_records,
)


class AssetTests(unittest.TestCase):
    def test_missing_balances_are_not_zero_and_commas_are_supported(self):
        after = parse_asset_snapshot({'血液': '1,234 滴', '金币': '未知', '旅程': '0 里'})
        self.assertEqual(after, {'血液': 1234, '旅程': 0})
        self.assertEqual(asset_deltas({'血液': 1200, '金币': 99}, after), {'血液': 34})

    def test_history_preserves_missing_fields_and_isolates_accounts(self):
        records = merge_asset_record({}, 1, {'血液': 10, '金币': 20}, 'first')
        updated = merge_asset_record(records, 1, {'血液': 12}, 'second')
        updated = merge_asset_record(updated, 2, {'金币': 1}, 'second')
        self.assertEqual(previous_snapshot(updated, 1), {'血液': 12, '金币': 20})
        self.assertEqual(previous_snapshot(updated, 2), {'金币': 1})
        self.assertEqual(updated['1']['sampled_at']['金币'], 'first')
        self.assertEqual(previous_snapshot(records, 1)['血液'], 10)

    def test_damaged_history_is_first_sample_and_writes_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'assets.json'
            path.write_text('{broken', encoding='utf-8')
            self.assertEqual(load_asset_records(path), {})
            records = merge_asset_record({}, 1, {'金币': 10}, 'sample')
            save_asset_records(path, records)
            self.assertEqual(previous_snapshot(load_asset_records(path), 1), {'金币': 10})

    def test_failed_atomic_replacement_preserves_original_config(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'config.yaml'
            path.write_text('original', encoding='utf-8')
            with patch('modules.gamemale_core.assets.os.replace', side_effect=OSError('offline failure')):
                with self.assertRaises(OSError):
                    atomic_write_text(path, 'replacement')
            self.assertEqual(path.read_text(encoding='utf-8'), 'original')
            self.assertEqual(list(Path(folder).iterdir()), [path])


if __name__ == '__main__':
    unittest.main()
