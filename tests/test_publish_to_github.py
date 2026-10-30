from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.publish_to_github import _accessible_history_files


class PublishHistoryTests(unittest.TestCase):
    def test_unreadable_history_folder_does_not_block_accessible_months(self):
        with tempfile.TemporaryDirectory() as temp:
            history = Path(temp)
            protected = history / "2026-09"
            accessible = history / "2026-10"
            protected.mkdir()
            accessible.mkdir()
            (accessible / "report_data.csv").write_text("ok", encoding="utf-8")

            original_is_file = Path.is_file

            def guarded_is_file(path: Path) -> bool:
                if path.parent == protected:
                    raise PermissionError("protected")
                return original_is_file(path)

            with patch.object(Path, "is_file", guarded_is_file):
                files = _accessible_history_files(history)

            self.assertEqual(files, [accessible / "report_data.csv"])


if __name__ == "__main__":
    unittest.main()
