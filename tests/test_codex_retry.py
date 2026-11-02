import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import codex_pipeline as pipeline


class CodexRetryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.output = self.root / "last-message.txt"
        self.task = {"attempt": 2}

    def test_transient_failures_retry_and_preserve_diagnostics(self):
        calls = []
        def run(command, **kwargs):
            calls.append(command)
            if len(calls) < 3:
                return SimpleNamespace(returncode=1, stdout='{"type":"error","message":"workspace routing discovery failed"}', stderr="error sending request")
            Path(command[command.index("-o") + 1]).write_text("completed")
            return SimpleNamespace(returncode=0, stdout="success", stderr="")
        with patch.object(pipeline.subprocess, "run", side_effect=run), patch.object(pipeline.time, "sleep") as sleep:
            pipeline.run_codex(self.root, self.task, "generate", "prompt", [], self.output, "workspace-write")
        self.assertEqual(len(calls), 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [15, 30])
        self.assertEqual(self.output.read_text(), "completed")
        for number in [1, 2]:
            log = (self.root / f"attempt-02-generate-network-failure-{number:02d}-events.jsonl").read_text()
            self.assertIn("workspace routing discovery failed", log)
            self.assertIn("error sending request", log)

    def test_timeout_text_is_never_retried(self):
        for index, message in enumerate(["request timed out", "TLS handshake timeout", "unexpected status 408 Request Timeout"]):
            with self.subTest(message=message):
                root = self.root / str(index)
                root.mkdir()
                with patch.object(pipeline.subprocess, "run", return_value=SimpleNamespace(returncode=1, stdout="", stderr=message)) as run, patch.object(pipeline.time, "sleep") as sleep:
                    with self.assertRaises(RuntimeError):
                        pipeline.run_codex(root, {"attempt": 1}, "generate", "prompt", [], root / "output.txt", "workspace-write")
                self.assertEqual(run.call_count, 1)
                sleep.assert_not_called()
                self.assertIn(message, (root / "attempt-01-generate-events.jsonl").read_text())

    def test_local_timeout_preserves_partial_stdout_and_stderr(self):
        error = subprocess.TimeoutExpired("codex", 900, output=b"partial stdout", stderr=b"partial stderr")
        with patch.object(pipeline.subprocess, "run", side_effect=error) as run, patch.object(pipeline.time, "sleep") as sleep:
            with self.assertRaises(subprocess.TimeoutExpired):
                pipeline.run_codex(self.root, self.task, "generate", "prompt", [], self.output, "workspace-write")
        self.assertEqual(run.call_count, 1)
        sleep.assert_not_called()
        log = (self.root / "attempt-02-generate-timeout-01-events.jsonl").read_text()
        self.assertIn("partial stdout", log)
        self.assertIn("partial stderr", log)

    def test_non_transient_failure_is_not_retried(self):
        with patch.object(pipeline.subprocess, "run", return_value=SimpleNamespace(returncode=1, stdout="", stderr="permission denied")) as run, patch.object(pipeline.time, "sleep") as sleep:
            with self.assertRaises(RuntimeError):
                pipeline.run_codex(self.root, self.task, "primary-review", "prompt", [], self.root / "review.json", "read-only")
        self.assertEqual(run.call_count, 1)
        sleep.assert_not_called()

    def test_existing_generation_artifact_blocks_retry(self):
        generated = self.root / "attempt-02-generated.png"
        generated.write_bytes(b"original")
        result = SimpleNamespace(returncode=1, stdout="workspace routing discovery failed", stderr="error sending request")
        with patch.object(pipeline.subprocess, "run", return_value=result) as run, patch.object(pipeline.time, "sleep") as sleep:
            with self.assertRaises(RuntimeError):
                pipeline.run_codex(self.root, self.task, "generate", "prompt", [], self.output, "workspace-write")
        self.assertEqual(run.call_count, 1)
        sleep.assert_not_called()
        self.assertEqual(generated.read_bytes(), b"original")

    def test_transient_retries_are_bounded(self):
        result = SimpleNamespace(returncode=1, stdout="", stderr="status 500")
        with patch.object(pipeline.subprocess, "run", return_value=result) as run, patch.object(pipeline.time, "sleep") as sleep:
            with self.assertRaises(RuntimeError):
                pipeline.run_codex(self.root, self.task, "primary-review", "prompt", [], self.root / "review.json", "read-only")
        self.assertEqual(run.call_count, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [15, 30])
        self.assertIn("status 500", (self.root / "attempt-02-primary-review-events.jsonl").read_text())


if __name__ == "__main__":
    unittest.main()
