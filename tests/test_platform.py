from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

from midivault import platform as winplatform


class PlatformHelperTests(unittest.TestCase):
    def test_cloud_attribute_flags(self) -> None:
        class FakeStat:
            st_file_attributes = 0

        cloud = FakeStat()
        cloud.st_file_attributes = winplatform.FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS
        offline = FakeStat()
        offline.st_file_attributes = winplatform.FILE_ATTRIBUTE_OFFLINE
        local = FakeStat()
        local.st_file_attributes = 0
        self.assertTrue(winplatform.is_cloud_placeholder(cloud))
        self.assertTrue(winplatform.is_cloud_placeholder(offline))
        self.assertFalse(winplatform.is_cloud_placeholder(local))

    def test_excluded_path_prefixes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            blocked = root / "blocked"
            allowed = root / "allowed"
            blocked.mkdir()
            allowed.mkdir()
            excludes = [str(blocked)]
            self.assertTrue(winplatform.is_excluded(str(blocked / "track.mid"), excludes))
            self.assertFalse(winplatform.is_excluded(str(allowed / "track.mid"), excludes))
            self.assertFalse(winplatform.is_excluded(str(root / "blocked-sibling.mid"), excludes))

    def test_protected_system_locations(self) -> None:
        if sys.platform != "win32":
            self.skipTest("Windows-specific protection paths")
        self.assertTrue(winplatform.is_protected(os.environ.get("SystemRoot", r"C:\Windows")))
        self.assertTrue(winplatform.is_protected(os.environ.get("ProgramFiles", r"C:\Program Files")))
        self.assertFalse(winplatform.is_protected(os.path.expanduser("~")))

    def test_optional_source_heuristic(self) -> None:
        self.assertTrue(winplatform._optional_source("fixed", "sebastien@example.com - Google Drive"))
        self.assertTrue(winplatform._optional_source("removable", "USB"))
        self.assertFalse(winplatform._optional_source("fixed", "SEBA BACKUP"))
        self.assertFalse(winplatform._optional_source("fixed", "Local Disk (D:)"))


if __name__ == "__main__":
    unittest.main()
