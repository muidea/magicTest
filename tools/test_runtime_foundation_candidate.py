import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class FoundationCandidatePreflightTests(unittest.TestCase):
    def run_driver(self, directory, arguments):
        root = Path(directory)
        binary = root / "bin"
        binary.mkdir()
        sentinel = root / "owner-command-called"
        for name in ("docker", "go"):
            command = binary / name
            command.write_text('#!/bin/sh\nprintf called > "$OWNER_COMMAND_SENTINEL"\nexit 99\n')
            command.chmod(0o700)
        output = root / "evidence"
        result = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("check_runtime_foundation.py")),
             "--evidence", str(output), *arguments],
            env=dict(os.environ, PATH=str(binary), OWNER_COMMAND_SENTINEL=str(sentinel)),
            capture_output=True, text=True,
        )
        self.assertFalse(sentinel.exists(), "invalid candidate reached owner or database commands")
        return result, output

    def test_incomplete_candidate_arguments_refused_before_commands(self):
        for arguments in (["--candidate-delivery", "/missing"],
                          ["--candidate-image-evidence", "/missing"]):
            with self.subTest(arguments=arguments), tempfile.TemporaryDirectory() as directory:
                result, output = self.run_driver(directory, arguments)
                self.assertEqual(result.returncode, 2)
                self.assertIn("both candidate", result.stderr)
                self.assertFalse(output.exists())

    def test_missing_candidate_records_failure_before_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            result, output = self.run_driver(directory, ["--candidate-delivery", "/missing",
                                                        "--candidate-image-evidence", "/missing"])
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("before owner or database calls", result.stderr)
            self.assertEqual(json.loads((output / "result.json").read_text())["status"], "failed")

    def test_panel_declarations_cannot_override_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            result, output = self.run_driver(directory, ["--candidate-delivery", "/missing",
                                                        "--candidate-image-evidence", "/missing",
                                                        "--panel-inputs", "/elsewhere"])
            self.assertEqual(result.returncode, 2)
            self.assertIn("cannot be overridden", result.stderr)
            self.assertFalse((output / "candidate-before.json").exists())


if __name__ == "__main__":
    unittest.main()
