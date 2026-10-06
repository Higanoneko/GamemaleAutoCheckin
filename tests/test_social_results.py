import unittest
from unittest.mock import Mock

from modules.gamemale_core.social import interact_with_blogs


class BlogResultsTests(unittest.TestCase):
    def test_different_blogs_by_same_author_count_separately(self):
        client = Mock()
        client._controller = None
        client._is_stopped.return_value = False
        client._send_request.side_effect = [
            Mock(text='<a href="home.php?mod=space&uid=1&do=blog&id=11">one</a>'
                      '<a href="home.php?mod=space&uid=1&do=blog&id=12">two</a>'),
            Mock(text='<a id="click_blogid_11_1" href="home.php?mod=spacecp&ac=click&id=11">shock</a>'),
            Mock(text='表态成功'),
            Mock(text='<a id="click_blogid_12_1" href="home.php?mod=spacecp&ac=click&id=12">shock</a>'),
            Mock(text='表态成功'),
        ]
        result = interact_with_blogs(client, target_interactions=2, max_pages_to_scan=1)
        self.assertEqual(result.new_count, 2)
        self.assertEqual(result.scanned_count, 2)
        self.assertEqual(result.processed_uids, ('1',))

    def test_repeated_interaction_does_not_count_as_today_new_action(self):
        client = Mock()
        client._controller = None
        client._is_stopped.return_value = False
        client._send_request.side_effect = [
            Mock(text='<a href="home.php?mod=space&uid=1&do=blog&id=11">one</a>'),
            Mock(text='<a id="click_blogid_11_1" href="home.php?mod=spacecp&ac=click&id=11">shock</a>'),
            Mock(text='您已表过态'),
        ]
        result = interact_with_blogs(client, target_interactions=1, max_pages_to_scan=1)
        self.assertEqual(result.new_count, 0)
        self.assertEqual(result.already_count, 1)
        self.assertEqual(result.processed_uids, ('1',))


if __name__ == '__main__':
    unittest.main()
