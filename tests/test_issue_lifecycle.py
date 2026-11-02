import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import codex_pipeline as pipeline


class IssueLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.task = {
            "taskType": "codex-cli-formal-production",
            "githubIssue": "https://github.com/hunknownz/intoreal-insect-sticker/issues/27",
            "species": {"scientificName": "Mantis religiosa"},
            "attempt": 1,
        }
        (self.root / "references.json").write_text(json.dumps({"references": []}))

    def write_task(self, stage):
        self.task["stage"] = stage
        self.task["status"] = "ready"
        self.task["closureMessage"] = "completion evidence"
        (self.root / "task.json").write_text(json.dumps(self.task))

    def test_notification_failure_is_logged_without_changing_stage(self):
        self.task["stage"] = "primary-review"
        (self.root / "pipeline-state.json").write_text(json.dumps({"species": "Mantis religiosa", "history": []}))
        with patch.object(pipeline, "issue_comment", side_effect=RuntimeError("GraphQL EOF")):
            self.assertFalse(pipeline.notify_issue(self.root, self.task, "Stage: primary-review"))
        self.assertEqual(self.task["stage"], "primary-review")
        state = json.loads((self.root / "pipeline-state.json").read_text())
        self.assertEqual(len(state["notifications"]), 1)
        self.assertFalse(state["notifications"][0]["delivered"])
        self.assertIn("GraphQL EOF", state["notifications"][0]["error"])

    def test_close_issue_does_not_duplicate_existing_comment(self):
        calls = []
        def gh(command, **kwargs):
            calls.append(command)
            if command[:3] == ["gh", "issue", "view"]:
                return SimpleNamespace(returncode=0, stdout=json.dumps({"state": "CLOSED", "comments": [{"body": "completion evidence"}]}), stderr="")
            raise AssertionError("duplicate comment or close was attempted")
        with patch.object(pipeline.subprocess, "run", side_effect=gh):
            pipeline.close_issue(self.task, "completion evidence")
        self.assertEqual(len(calls), 1)

    def test_close_issue_posts_missing_comment_before_closing(self):
        calls = []
        def gh(command, **kwargs):
            calls.append(command[:3])
            if command[:3] == ["gh", "issue", "view"]:
                return SimpleNamespace(returncode=0, stdout=json.dumps({"state": "OPEN", "comments": []}), stderr="")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        with patch.object(pipeline.subprocess, "run", side_effect=gh):
            pipeline.close_issue(self.task, "completion evidence")
        self.assertEqual(calls, [["gh", "issue", "view"], ["gh", "issue", "comment"], ["gh", "issue", "close"]])

    def test_default_protocol_version_is_persisted_before_done(self):
        from task_protocol import protocol_version
        self.write_task("close-issue")
        self.assertNotIn("reviewProtocolVersion", self.task)
        with patch.object(pipeline, "close_issue", return_value=None), \
             patch.object(pipeline, "export_approved", side_effect=AssertionError("must not export again")):
            result = pipeline.run(self.root)
        self.assertTrue(result["ok"])
        saved = json.loads((self.root / "task.json").read_text())
        self.assertEqual(saved["reviewProtocolVersion"], 2)
        self.assertEqual(protocol_version(saved), 2)

    def test_close_failure_retries_only_finalization(self):
        self.write_task("close-issue")
        with patch.object(pipeline, "export_approved", side_effect=AssertionError("must not export again")), \
             patch.object(pipeline, "close_issue", side_effect=[RuntimeError("GraphQL EOF"), None]) as close, \
             patch.object(pipeline, "issue_comment", return_value=None):
            first = pipeline.run(self.root)
            self.assertFalse(first["ok"])
            self.assertEqual(first["stage"], "close-issue")
            task = json.loads((self.root / "task.json").read_text())
            self.assertEqual(task["stage"], "close-issue")
            self.assertEqual(task["status"], "retry")
            second = pipeline.run(self.root)
            self.assertTrue(second["ok"])
            self.assertEqual(second["stage"], "done")
            self.assertEqual(close.call_count, 2)

    def test_close_failures_are_bounded(self):
        self.write_task("close-issue")
        with patch.object(pipeline, "export_approved", side_effect=AssertionError("must not export again")), \
             patch.object(pipeline, "close_issue", side_effect=RuntimeError("GraphQL EOF")) as close, \
             patch.object(pipeline, "issue_comment", return_value=None):
            results = [pipeline.run(self.root) for _ in range(3)]
        self.assertEqual(results[-1]["stage"], "blocked")
        self.assertEqual(close.call_count, 3)
        self.assertEqual(json.loads((self.root / "task.json").read_text())["stage"], "blocked")


if __name__ == "__main__":
    unittest.main()
