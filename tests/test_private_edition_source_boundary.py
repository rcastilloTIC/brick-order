"""Keep private extension features out of the public runtime source tree."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKERS = ('extension_interest', 'final_extension_interest', 'final_extension', 'extension_vote', 'ampliación voluntaria')
RUNTIME_PATHS = ('app', 'templates', 'static')


class SourceEditionBoundaryTest(unittest.TestCase):
    def test_private_functional_markers_are_edition_specific(self):
        hits = []
        for dirname in RUNTIME_PATHS:
            for file in (ROOT / dirname).rglob('*'):
                if file.is_file() and file.suffix.lower() in {'.py', '.html', '.js', '.css', '.json'}:
                    data = file.read_text(encoding='utf-8', errors='replace').lower()
                    if any(marker in data for marker in MARKERS):
                        hits.append(str(file.relative_to(ROOT)))
        if 'class ExtensionInterest' in (ROOT / 'app' / 'models.py').read_text(encoding='utf-8'):
            self.assertTrue(hits, 'Extended edition must retain private features')
        else:
            self.assertEqual(hits, [], 'Public edition contains private feature references: ' + ', '.join(hits))


if __name__ == '__main__':
    unittest.main()
