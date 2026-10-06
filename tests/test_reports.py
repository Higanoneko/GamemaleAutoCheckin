import unittest

from modules.gamemale_core.reports import build_asset_history_report, build_detailed_report


class ReportTests(unittest.TestCase):
    def test_threshold_boundaries_missing_values_and_reference_maximum(self):
        at_threshold = build_detailed_report('offline', {}, user_credits={'积分': '70', '血液': '1,700 滴'})
        self.assertIn('当前等级预估: Lvl. 4', at_threshold)
        self.assertIn('还需 50 积分', at_threshold)
        self.assertIn('按估算已足够', at_threshold)
        zero = build_detailed_report('offline', {}, user_credits={'积分': '0', '血液': '0 滴'})
        self.assertIn('距 Lvl. 1 还需 3 积分', zero)
        self.assertIn('尚差 102 滴', zero)
        missing = build_detailed_report('offline', {}, user_credits={'积分': '无法解析', '血液': '800 滴'})
        self.assertIn('未解析到有效积分，无法预估', missing)
        self.assertNotIn('当前等级预估', missing)
        missing_blood = build_detailed_report('offline', {}, user_credits={'积分': '40'})
        self.assertIn('约需 1020 滴血液；当前血液未解析到', missing_blood)
        maximum = build_detailed_report('offline', {}, user_credits={'积分': '1,000'})
        self.assertIn('当前等级预估: Lvl. 10', maximum)
        self.assertIn('已达到参考门槛表最高等级', maximum)
        self.assertNotIn('距 Lvl. 11', maximum)

    def test_upgrade_estimate_follows_current_credits_and_shows_shortfall(self):
        report = build_detailed_report('offline', {'签到': True},
                                       user_credits={'积分': '40', '血液': '800 滴'})
        self.assertLess(report.index('当前积分:'), report.index('升级预估:'))
        self.assertLess(report.index('升级预估:'), report.index('任务执行概况:'))
        self.assertIn('当前等级预估: Lvl. 3', report)
        self.assertIn('距 Lvl. 4 还需 30 积分（门槛 70）', report)
        self.assertIn('约需 1020 滴血液；当前 800 滴，尚差 220 滴', report)
        self.assertIn('1 积分 ≈ 34 血液', report)

    def test_partial_history_keeps_distinct_times_grouped_at_the_end(self):
        report = build_asset_history_report(
            {'金币': 20, '血液': 10, '积分': 40}, {'金币': 22, '血液': 13, '积分': 41, '旅程': 2},
            {'金币': 'old', '血液': 'new', '积分': 'old'},
        )
        self.assertIn('  - 旅程: 2（首次记录）', report)
        self.assertEqual(report.splitlines()[-1], '上次记录时间: old（金币、积分）；new（血液）')

    def test_history_time_is_one_final_line_for_shared_sample(self):
        report = build_asset_history_report(
            {'金币': 20, '血液': 10}, {'金币': 22, '血液': 13},
            {'金币': '2026-10-05T08:00:00+08:00', '血液': '2026-10-05T08:00:00+08:00'},
        )
        self.assertIn('  - 金币: +2\n', report)
        self.assertIn('  - 血液: +3\n', report)
        self.assertEqual(report.count('2026-10-05T08:00:00+08:00'), 1)
        self.assertEqual(report.splitlines()[-1], '上次记录时间: 2026-10-05T08:00:00+08:00')


if __name__ == '__main__':
    unittest.main()
