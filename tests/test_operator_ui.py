import unittest

from local_tts.audio import PREVIEW_TEXT
from local_tts.operator_ui import OPERATOR_UI


class OperatorUiTests(unittest.TestCase):
    def test_preview_copy_and_voice_names_do_not_show_ready_suffix(self):
        self.assertIn(PREVIEW_TEXT, OPERATOR_UI)
        self.assertIn("▶ Nghe thử 10s", OPERATOR_UI)
        self.assertNotIn("Mỗi giọng READY", OPERATOR_UI)
        self.assertNotIn("${x.display_name} — ${x.status}", OPERATOR_UI)
        self.assertNotIn("chọn giọng READY", OPERATOR_UI)


if __name__ == "__main__":
    unittest.main()
