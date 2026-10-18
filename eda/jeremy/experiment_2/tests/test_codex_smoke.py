"""Exercise CLI startup and saved outputs offline, without model requests."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CodexSmokeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="eda-cli-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name in ("run_codex_smoke.sh", "smoke_prompt.txt"):
            shutil.copyfile(ROOT / name, self.root / name)
        self.cli = self.root / "fake codex"
        self.cli.write_text('''#!/bin/bash
case "$1" in
  login)
    if [[ "${FIXTURE_LOGIN:-}" == fail ]]; then
      echo 'OFFLINE FIXTURE: Not logged in' >&2
      exit 1
    fi
    echo "Logged in using ${FIXTURE_LOGIN:-ChatGPT}"
    ;;
  --version)
    if [[ "${FIXTURE_VERSION:-}" == fail ]]; then
      echo 'OFFLINE FIXTURE: version unavailable' >&2
      exit 2
    fi
    echo 'OFFLINE FIXTURE VERSION'
    ;;
  exec)
    cat >/dev/null
    while [[ $# -gt 0 ]]; do
      if [[ "$1" == --output-last-message ]]; then
        shift
        printf '%s\\n' '{"route":"AMBER","approval_id":"R001"}' > "$1"
      fi
      shift
    done
    echo '{"type":"turn.completed","fixture":true}'
    ;;
esac
''')
        self.cli.chmod(0o700)

    def run_script(self, *args, **settings):
        env = dict(os.environ, CODEX_BIN=str(self.cli), **settings)
        return subprocess.run(
            ["/bin/bash", str(self.root / "run_codex_smoke.sh"), *args],
            env=env, capture_output=True, text=True, timeout=10,
        )

    def test_login_failure_is_visible_instead_of_silent_exit(self):
        result = self.run_script("fixture-model", FIXTURE_LOGIN="fail")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Not logged in", result.stderr)
        self.assertIn("login check failed", result.stderr)
        self.assertIn("login", result.stderr)
        self.assertFalse((self.root / "results").exists())

    def test_missing_explicit_executable_is_visible(self):
        self.cli.unlink()
        result = self.run_script("fixture-model")
        self.assertEqual(result.returncode, 127)
        self.assertIn("Codex could not be found", result.stderr)
        self.assertFalse((self.root / "results").exists())

    def test_version_failure_is_visible(self):
        result = self.run_script("fixture-model", FIXTURE_VERSION="fail")
        self.assertEqual(result.returncode, 2)
        self.assertIn("version unavailable", result.stderr)

    def test_api_login_is_rejected(self):
        result = self.run_script("fixture-model", FIXTURE_LOGIN="API key")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Sign in with ChatGPT", result.stderr)
        self.assertFalse((self.root / "results").exists())

    def test_check_only_does_not_start_collection(self):
        result = self.run_script("--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("No model request was sent", result.stdout)
        self.assertFalse((self.root / "results").exists())

    def test_successful_attempts_keep_separate_outputs(self):
        for _ in range(2):
            result = self.run_script("fixture-model", "medium")
            self.assertEqual(result.returncode, 0, result.stderr)
        runs = list((self.root / "results").iterdir())
        self.assertEqual(len(runs), 2)
        for run in runs:
            self.assertEqual((run / "prompt.txt").read_bytes(), (ROOT / "smoke_prompt.txt").read_bytes())
            self.assertIn('"route":"AMBER"', (run / "response.txt").read_text())
            self.assertIn('"fixture":true', (run / "events.jsonl").read_text())
            self.assertIn("exit_status=0", (run / "settings.txt").read_text())


if __name__ == "__main__":
    unittest.main()
