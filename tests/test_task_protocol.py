import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from codex_pipeline import PRIMARY_REVIEWER, sha256, validate_review
from task_protocol import create_task_package, protocol_version, validate_task_package


class TaskProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.task_dir = self.root / "production/Example_species"
        references = self.task_dir / "references"
        references.mkdir(parents=True)
        rows = []
        for filename, role, view in [
            ("main.jpg", "primary-pose", "dorsal full body"),
            ("detail.jpg", "local-detail-only", "head detail"),
        ]:
            path = references / filename
            path.write_bytes(filename.encode())
            rows.append({
                "id": filename,
                "type": "photo",
                "view": view,
                "poseRole": role,
                "lifeStage": "adult",
                "sex": "unverifiable",
                "page": f"https://example.com/{filename}",
                "author": "Example photographer",
                "license": "CC-BY-4.0",
                "localPath": f"references/{filename}",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            })
        self.config = {
            "workspace": "production/Example_species",
            "githubIssue": "https://github.com/hunknownz/intoreal-insect-sticker/issues/99",
            "species": {
                "scientificName": "Example species",
                "commonNameEn": "Example insect",
                "commonNameZhHans": "示例昆虫",
                "order": "Exampleorder",
                "family": "Examplefamily",
                "lifeStage": "adult",
                "sex": "unverifiable",
                "view": "dorsal",
            },
            "generationInstructions": "Use the main full-body pose and keep all appendages coherent with it.",
            "unverifiable": ["sex", "fine appendage segmentation"],
            "anatomyChecks": [
                {"id": "body-anatomy", "critical": True, "requirement": "Exactly six naturally attached legs; no fused or duplicated appendages."}
            ],
            "references": rows,
        }

    def test_new_tasks_default_to_v2_while_legacy_tasks_stay_v1(self):
        self.assertEqual(protocol_version({"stage": "generate"}), 2)
        self.assertEqual(protocol_version({"stage": "primary-review"}), 2)
        self.assertEqual(protocol_version({"stage": "done"}), 1)
        self.assertEqual(protocol_version({"stage": "blocked"}), 1)
        self.assertEqual(protocol_version({"stage": "generate", "reviewProtocolVersion": 1}), 1)

    def test_builder_creates_complete_v2_task_package(self):
        task_dir = create_task_package(self.config, self.root)
        task = json.loads((task_dir / "task.json").read_text())
        checklist = json.loads((task_dir / "review-checklist.json").read_text())
        self.assertEqual(task["reviewProtocolVersion"], 2)
        self.assertEqual(task["stage"], "generate")
        self.assertEqual(task["attempt"], 1)
        self.assertTrue(any(row["id"] == "view-consistency" and row["critical"] for row in checklist["checks"]))
        self.assertIn("body-anatomy", {row["id"] for row in checklist["checks"]})
        for filename in [
            "task.json", "references.json", "review-checklist.json",
            "review-output.schema.json", "generate-task.md", "blind-review-task.md",
        ]:
            self.assertTrue((task_dir / filename).is_file(), filename)
        self.assertTrue(validate_task_package(task_dir))
        with self.assertRaises(ValueError):
            create_task_package(self.config, self.root)

    def test_builder_requires_species_anatomy_checks(self):
        config = copy.deepcopy(self.config)
        config["anatomyChecks"] = []
        with self.assertRaisesRegex(ValueError, "anatomyChecks"):
            create_task_package(config, self.root)

    def test_builder_requires_main_pose_and_matching_hash(self):
        config = copy.deepcopy(self.config)
        config["references"][0]["poseRole"] = "local-detail-only"
        with self.assertRaisesRegex(ValueError, "primary-pose"):
            create_task_package(config, self.root)
        config = copy.deepcopy(self.config)
        config["references"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            create_task_package(config, self.root)

    def test_reference_requires_life_stage_and_sex(self):
        for field in ["lifeStage", "sex"]:
            with self.subTest(field=field):
                config = copy.deepcopy(self.config)
                del config["references"][0][field]
                with self.assertRaisesRegex(ValueError, field):
                    create_task_package(config, self.root)

    def test_invalid_explicit_versions_fail_closed(self):
        for value in ["2", 3, None, True]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    protocol_version({"stage": "generate", "reviewProtocolVersion": value})

    def test_builder_rejects_duplicate_anatomy_check_ids(self):
        config = copy.deepcopy(self.config)
        config["anatomyChecks"].append({"id": "body-anatomy", "critical": True, "requirement": "Two distinct antennae; no duplicated appendages."})
        with self.assertRaisesRegex(ValueError, "唯一|重复"):
            create_task_package(config, self.root)

    def test_gate_rejects_missing_view_consistency(self):
        task_dir = create_task_package(self.config, self.root)
        path = task_dir / "review-checklist.json"
        checklist = json.loads(path.read_text())
        checklist["checks"] = [row for row in checklist["checks"] if row["id"] != "view-consistency"]
        path.write_text(json.dumps(checklist))
        with self.assertRaisesRegex(ValueError, "view-consistency"):
            validate_task_package(task_dir)

    def test_review_validation_uses_default_v2_for_new_task(self):
        task_dir = create_task_package(self.config, self.root)
        task = json.loads((task_dir / "task.json").read_text())
        del task["reviewProtocolVersion"]
        task["stage"] = "primary-review"
        candidate = task_dir / "attempt-01-sticker.png"
        candidate.write_bytes(b"candidate")
        checklist = json.loads((task_dir / "review-checklist.json").read_text())
        checks = [
            {"id": row["id"], "status": "unverifiable" if row["id"] == "view-consistency" else "pass", "evidence": "Checked"}
            for row in checklist["checks"]
        ]
        review = {
            "species": "Example species",
            "attempt": 1,
            "reviewer": PRIMARY_REVIEWER,
            "reviewType": "primary-independent",
            "score": 90,
            "verdict": "pass",
            "checks": checks,
            "reviewedFiles": {
                "candidate": "attempt-01-sticker.png",
                "references": [row["localPath"] for row in self.config["references"]],
            },
            "candidateHashCheck": {"actual": sha256(candidate), "matched": True},
        }
        path = task_dir / "review.json"
        path.write_text(json.dumps(review))
        with self.assertRaisesRegex(ValueError, "view-consistency|视角一致性"):
            validate_review(path, task_dir, task, "primary-review", candidate)


if __name__ == "__main__":
    unittest.main()
