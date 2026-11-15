"""Check that the branch-protection owner handoff covers enforceable settings."""
import unittest
from pathlib import Path


class BranchProtectionHandoffTest(unittest.TestCase):
    def test_owner_handoff_names_actual_main_ci_and_review_rules(self):
        path = Path(__file__).resolve().parents[1] / 'docs/security/GITHUB_BRANCH_PROTECTION.md'
        content = path.read_text(encoding='utf-8')
        for term in ('main', 'estabilidade-main.yml', 'validar',
                     'force push', 'pull request', 'approvals',
                     'restrict deletions', 'NOT APPLIED'):
            with self.subTest(term=term):
                self.assertIn(term, content)


if __name__ == '__main__':
    unittest.main()
