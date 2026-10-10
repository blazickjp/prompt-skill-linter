import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import scan_explicit_links as scanner


class TrackedBoundaryTests(unittest.TestCase):
    def test_untracked_skill_ignored_and_dirty_tracked_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            scanner.git(root, 'init', '-q')
            skill = root / 'skills/tracked/SKILL.md'
            skill.parent.mkdir(parents=True)
            skill.write_text('[reference](reference.md)\n')
            (skill.parent / 'reference.md').write_text('Reference\n')
            scanner.git(root, 'add', '.')
            scanner.git(root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture')
            commit = scanner.git(root, 'rev-parse', 'HEAD').strip()
            with patch.object(scanner, 'PINNED_COMMIT', commit), patch.object(scanner, 'EXPECTED_SKILLS', 1):
                paths, skills = scanner.inspect_checkout(root)
                before = scanner.scan(root, paths, skills)
                extra = root / 'skills/untracked/SKILL.md'
                extra.parent.mkdir(parents=True)
                extra.write_text('[missing](missing.md)\n')
                paths, skills = scanner.inspect_checkout(root)
                after = scanner.scan(root, paths, skills)
                self.assertEqual(before, after)
                self.assertEqual(after['counts']['skills'], 1)
                skill.write_text('changed\n')
                with self.assertRaisesRegex(ValueError, 'Tracked working tree must be clean'):
                    scanner.inspect_checkout(root)


if __name__ == '__main__':
    unittest.main()
