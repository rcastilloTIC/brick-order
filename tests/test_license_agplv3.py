"""License regression checks, independent of Flask and deployment settings."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AGPLLicenseTest(unittest.TestCase):
    def test_full_agpl_v3_license_is_bundled(self):
        content = (ROOT / 'LICENSE').read_text(encoding='utf-8')
        self.assertIn('GNU AFFERO GENERAL PUBLIC LICENSE', content)
        self.assertIn('Version 3, 19 November 2007', content)
        self.assertIn('13. Remote Network Interaction; Use with the GNU General Public License.', content)
        self.assertIn('END OF TERMS AND CONDITIONS', content)
        self.assertNotIn('MIT License', content)

    def test_explicit_spdx_and_copyright_notice(self):
        notice = (ROOT / 'NOTICE').read_text(encoding='utf-8')
        readme = (ROOT / 'README.md').read_text(encoding='utf-8')
        self.assertIn('SPDX-License-Identifier: AGPL-3.0-only', notice)
        self.assertIn('Copyright (C) 2026 VALBRICK', notice)
        self.assertNotIn('Valbrick contributors', notice)
        self.assertIn('seudonimo del autor unico', notice)
        self.assertIn('AGPL-3.0-only', readme)
        self.assertIn('`LICENSE`', readme)
        self.assertNotIn('MIT: consultar `LICENSE`', readme)


if __name__ == '__main__':
    unittest.main()
