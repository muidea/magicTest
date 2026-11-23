"""Refuse incomplete replacement acceptance before opening any owner or DB."""
import os
from pathlib import Path
import subprocess
import sys
import unittest


class ReplacementPrerequisites(unittest.TestCase):
    def test_requires_real_publication_file_consumer(self):
        driver = Path(__file__).with_name("check_published_block_lifecycle.py")
        environment = dict(os.environ)
        environment.pop("MAGIC_PUBLISHED_BLOCK_POSTGRES_DSN", None)
        with self.subTest("all other replacement prerequisites"):
            result = subprocess.run(
                [sys.executable, str(driver), "--replacement-action-retirement",
                 "--entity-actions", "--formal-review", "--submit-http", "--review-http"],
                env=environment, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("--package-assets", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
        with self.subTest("missing signed owner flow"):
            result = subprocess.run(
                [sys.executable, str(driver), "--replacement-action-retirement", "--package-assets"],
                env=environment, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("--formal-review", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
        with self.subTest("missing retained predecessor"):
            result = subprocess.run(
                [sys.executable, str(driver), "--replacement-action-retirement",
                 "--entity-actions", "--formal-review", "--submit-http", "--review-http", "--package-assets"],
                env=environment, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("--retain-model-data", result.stderr)
            self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
