import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import codex_pipeline as pipeline
from task_protocol import create_task_package


class PipelineGateTests(unittest.TestCase):
    def test_invalid_v2_package_stops_before_generation(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory).resolve()
            task_dir = root / "production/Example_species"
            reference = task_dir / "references/main.jpg"
            reference.parent.mkdir(parents=True)
            reference.write_bytes(b"reference")
            config = {
                "workspace": "production/Example_species",
                "githubIssue": "https://github.com/hunknownz/intoreal-insect-sticker/issues/99",
                "species": {"scientificName": "Example species", "commonNameEn": "Example", "commonNameZhHans": "示例", "order": "Order", "family": "Family", "lifeStage": "adult", "sex": "unverifiable", "view": "dorsal"},
                "generationInstructions": "Coherent full-body pose.",
                "unverifiable": ["sex"],
                "anatomyChecks": [{"id": "body-anatomy", "critical": True, "requirement": "Six attached legs."}],
                "references": [{"id": "main", "type": "photo", "view": "dorsal", "lifeStage": "adult", "sex": "unverifiable", "poseRole": "primary-pose", "page": "https://example.com/photo", "author": "A", "license": "CC0", "localPath": "references/main.jpg", "sha256": hashlib.sha256(reference.read_bytes()).hexdigest()}],
            }
            create_task_package(config, root)
            checklist_path = task_dir / "review-checklist.json"
            checklist = json.loads(checklist_path.read_text())
            checklist["checks"] = [row for row in checklist["checks"] if row["id"] != "view-consistency"]
            checklist_path.write_text(json.dumps(checklist))
            with patch.object(pipeline, "generate") as generate, patch.object(pipeline.subprocess, "run", side_effect=AssertionError("no external command should run")):
                result = pipeline.run(task_dir)
            self.assertFalse(result["ok"])
            self.assertEqual(result["stage"], "blocked")
            self.assertIn("view-consistency", result["error"])
            generate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
