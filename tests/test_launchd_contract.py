import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN_SH = ROOT / "run.sh"
RUNNER = ROOT / "launchd" / "osm-ad-bot-runner.sh"


class LaunchdContractTests(unittest.TestCase):
    def test_shell_scripts_are_syntactically_valid(self):
        for script in (RUN_SH, RUNNER):
            result = subprocess.run(
                ["bash", "-n", str(script)], capture_output=True, text=True
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_launchagent_contract_keeps_bot_alive_without_blocking_sleep(self):
        source = RUN_SH.read_text(encoding="utf-8")
        self.assertIn("plutil -insert KeepAlive -bool YES", source)
        self.assertIn("plutil -insert RunAtLoad -bool YES", source)
        self.assertIn("ProcessType -string Background", source)
        self.assertNotIn("caffeinate", source)
        self.assertIn("launchctl bootout", source)
        self.assertIn("launchctl kickstart -k", source)
        self.assertIn('STAGED_DUMP="${RUNTIME_DIR}/launchd-storage-dump.zip"', source)
        self.assertIn('chmod 600 "${candidate}"', source)

    def test_runner_execs_conductor_and_does_not_tail_or_daemonize(self):
        source = RUNNER.read_text(encoding="utf-8")
        self.assertIn('exec "${PYTHON_BIN}" osm_ad_bot_conductor.py', source)
        self.assertNotIn("nohup", source)
        self.assertNotIn("tail -f", source)

    def test_launchd_files_do_not_embed_session_credentials(self):
        combined = (
            RUN_SH.read_text(encoding="utf-8")
            + RUNNER.read_text(encoding="utf-8")
        ).lower()
        for forbidden in ("access_token", "refresh_token", "authorization: bearer"):
            self.assertNotIn(forbidden, combined)


if __name__ == "__main__":
    unittest.main()
