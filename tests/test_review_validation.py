import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from codex_pipeline import PRIMARY_REVIEWER, sha256, validate_review


class ReviewValidationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        (self.root / "references").mkdir()
        self.candidate = self.root / "attempt-01-sticker.png"
        self.candidate.write_bytes(b"candidate")
        for name in ["a.jpg", "b.jpg"]:
            (self.root / "references" / name).write_bytes(name.encode())
        (self.root / "references.json").write_text(json.dumps({"references": [{"localPath": "references/a.jpg"}, {"localPath": "references/b.jpg"}]}))
        self.task = {"species": {"scientificName": "Example species"}, "attempt": 1, "stage": "primary-review", "reviewProtocolVersion": 2, "githubIssue": "https://github.com/hunknownz/intoreal-insect-sticker/issues/99"}
        self.review = {
            "species": "Example species",
            "attempt": 1,
            "reviewer": PRIMARY_REVIEWER,
            "reviewType": "primary-independent",
            "score": 90,
            "verdict": "pass",
            "checks": [{"id": "view-consistency", "status": "pass", "evidence": "Head, thorax and appendages share the same reference-supported perspective."}],
            "reviewedFiles": {"candidate": "attempt-01-sticker.png", "references": ["references/a.jpg", "references/b.jpg"]},
            "candidateHashCheck": {"actual": sha256(self.candidate), "matched": True},
        }
        self.checklist = {"checks": [{"id": "view-consistency", "critical": True}]}

    def validate(self, review=None, checklist=None, task=None):
        (self.root / "review-checklist.json").write_text(json.dumps(checklist or self.checklist))
        path = self.root / "review.json"
        path.write_text(json.dumps(review or self.review))
        return validate_review(path, self.root, task or self.task, "primary-review", self.candidate)

    def test_complete_v2_review_is_accepted(self):
        self.assertEqual(self.validate()["verdict"], "pass")

    def test_unverifiable_view_cannot_pass(self):
        review = copy.deepcopy(self.review)
        review["checks"][0]["status"] = "unverifiable"
        with self.assertRaisesRegex(ValueError, "view-consistency|视角一致性"):
            self.validate(review)

    def test_empty_evidence_is_rejected(self):
        review = copy.deepcopy(self.review)
        review["checks"][0]["evidence"] = ""
        with self.assertRaisesRegex(ValueError, "证据不能为空"):
            self.validate(review)

    def test_missing_reference_is_rejected(self):
        review = copy.deepcopy(self.review)
        review["reviewedFiles"]["references"] = ["references/a.jpg"]
        with self.assertRaisesRegex(ValueError, "全部指定参考"):
            self.validate(review)

    def test_missing_critical_view_check_is_rejected(self):
        checklist = {"checks": [{"id": "dorsal-view", "critical": True}]}
        review = copy.deepcopy(self.review)
        review["checks"] = [{"id": "dorsal-view", "status": "pass", "evidence": "Complete body"}]
        with self.assertRaisesRegex(ValueError, "view-consistency"):
            self.validate(review, checklist)

    def test_legacy_review_behavior_is_preserved(self):
        task = dict(self.task)
        del task["reviewProtocolVersion"]
        task["stage"] = "done"
        review = copy.deepcopy(self.review)
        review["checks"][0]["evidence"] = ""
        review["reviewedFiles"]["references"] = ["references/a.jpg"]
        self.assertEqual(self.validate(review, task=task)["verdict"], "pass")
    def test_duplicate_review_check_ids_are_rejected(self):
        review = copy.deepcopy(self.review)
        review["checks"].append({"id": "view-consistency", "status": "pass", "evidence": "A second requirement with the same id."})
        with self.assertRaisesRegex(ValueError, "重复"):
            self.validate(review)

    def test_review_prompt_does_not_hardcode_three_references(self):
        from codex_pipeline import review_prompt
        prompt = review_prompt(self.root, self.task, "primary-review", self.candidate)
        self.assertNotIn("三张参考图", prompt)
        self.assertIn("全部参考图", prompt)


if __name__ == "__main__":
    unittest.main()
