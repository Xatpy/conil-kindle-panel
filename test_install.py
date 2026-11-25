import unittest
from install import configure_sleep


class ConfigureSleepTests(unittest.TestCase):
    def test_preserves_other_settings_and_adds_missing_keys(self):
        source = '-- saved settings\nreturn {\n    ["language"] = "es",\n    ["screensaver_type"] = "cover",\n}\n'
        result = configure_sleep(source)
        self.assertIn('["language"] = "es"', result)
        self.assertIn('["screensaver_type"] = "document_cover"', result)
        self.assertIn('["screensaver_document_cover"] = "/mnt/us/koreader/conil.png"', result)
        self.assertIn('["screensaver_show_message"] = false', result)
        self.assertEqual(configure_sleep(result), result)

    def test_rejects_unexpected_file_format(self):
        for source in ('return nil', 'return {\n    ["screensaver_type"] = {},\n}\n'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                configure_sleep(source)
