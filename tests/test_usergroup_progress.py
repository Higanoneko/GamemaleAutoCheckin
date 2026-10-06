import unittest

from modules.gamemale_core.parsers import parse_usergroup_progress


USERGROUP_HTML = '''
<table class="tdat"><tr><th class="c0"><h4>我的主用户组 - Lvl. 3</h4></th></tr></table>
<ul id="tba"><li id="c2">晋级用户组 - Lvl. 4</li></ul>
<div class="tscr"><table><tr><th><span class="notice">
您升级到此用户组还需积分 <b>17</b>
</span></th></tr></table></div>
'''


class UsergroupProgressTests(unittest.TestCase):
    def test_parses_zero_and_thousands_without_requiring_group_titles(self):
        for value, expected in (('0', 0), ('1,234', 1234)):
            with self.subTest(value=value):
                progress = parse_usergroup_progress(f'<span class="notice">您升级到此用户组还需积分：{value}</span>')
                self.assertEqual(progress.points_needed, expected)
                self.assertIsNone(progress.target_group)

    def test_missing_malformed_and_ambiguous_gaps_are_unavailable(self):
        for html in (
            '<span class="notice">积分下限 70</span>',
            '<form>请先登录</form>',
            USERGROUP_HTML + USERGROUP_HTML,
            *('<span class="notice">您升级到此用户组还需积分 ' + value + '</span>'
              for value in ('-1', '1,2', '1e3', '1.5', '未知')),
        ):
            with self.subTest(html=html):
                self.assertIsNone(parse_usergroup_progress(html))

    def test_hidden_notices_and_script_text_do_not_override_visible_gap(self):
        hidden = '''
        <script>var message = "您升级到此用户组还需积分 999";</script>
        <div style="display: none"><span style="display:none" class="notice">您升级到此用户组还需积分 999</span></div>
        <div hidden><span hidden class="notice">您升级到此用户组还需积分 999</span></div>
        '''
        progress = parse_usergroup_progress(hidden + USERGROUP_HTML)
        self.assertEqual(progress.points_needed, 17)

    def test_reads_site_gap_and_selected_group_instead_of_reference_threshold(self):
        progress = parse_usergroup_progress(USERGROUP_HTML)
        self.assertIsNotNone(progress)
        self.assertEqual(progress.points_needed, 17)
        self.assertEqual(progress.current_group, 'Lvl. 3')
        self.assertEqual(progress.target_group, 'Lvl. 4')


if __name__ == '__main__':
    unittest.main()
