import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import sticker_export as exporter


class RevisionExportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        patcher = patch.object(exporter, "PROJECT_ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.task = self.root / "production/Mantis_religiosa_revision-01"
        self.task.mkdir(parents=True)
        (self.root / "data").mkdir()
        (self.root / "stickers/Mantodea/Mantidae").mkdir(parents=True)
        old = self.root / "old.png"
        new = self.task / "attempt-01-sticker.png"
        image = Image.new("RGBA", (1000, 800), (0, 0, 0, 0))
        image.putpixel((500, 400), (1, 2, 3, 255))
        image.save(old)
        image.putpixel((500, 400), (10, 20, 30, 255))
        image.save(new)
        self.old_sha = hashlib.sha256(old.read_bytes()).hexdigest()
        self.new_sha = hashlib.sha256(new.read_bytes()).hexdigest()
        self.target = self.root / "stickers/Mantodea/Mantidae/Mantis_religiosa.webp"
        with Image.open(old) as source:
            source.save(self.target, "WEBP", exact=True)
        self.old_bytes = self.target.read_bytes()
        self.revision = {
            "issue": "https://github.com/hunknownz/intoreal-insect-sticker/issues/21",
            "attempt": 1,
            "sourceSha256": self.old_sha,
        }
        self.base_task = {
            "attempt": 1,
            "species": {
                "scientificName": "Mantis religiosa", "commonNameEn": "European mantis",
                "commonNameZhHans": "欧洲螳螂", "order": "Mantodea", "family": "Mantidae",
            },
            "revisionOf": self.revision,
            "reviewProtocolVersion": 1,
            "stage": "blind-review",
        }
        reference = self.task / "references/main.jpg"
        reference.parent.mkdir()
        reference.write_bytes(b"reference")
        self.reference_metadata = {
            "id": "main", "type": "photo", "view": "anterolateral", "poseRole": "primary-pose",
            "lifeStage": "adult", "sex": "unverifiable", "page": "https://example.com/photo",
            "author": "A", "license": "CC-BY-4.0", "localPath": "references/main.jpg",
            "sha256": hashlib.sha256(reference.read_bytes()).hexdigest(),
        }
        (self.task / "references.json").write_text(json.dumps({"references": [self.reference_metadata]}))
        self.checklist = {"checks": [
            {"id": "body-anatomy", "critical": True, "requirement": "Natural anatomy and attachment."},
            {"id": "view-consistency", "critical": True, "requirement": "One coherent pose and perspective."},
            {"id": "requested-view", "critical": True, "requirement": "Complete requested view."},
            {"id": "unknowns", "critical": True, "requirement": "Report unverifiable details."},
        ]}
        (self.task / "review-checklist.json").write_text(json.dumps(self.checklist))
        with Image.open(new) as source:
            source.save(self.task / "attempt-01-generated.png")
        generation = {
            "review": {"status": "not-performed"},
            "outputs": {
                "generated": {"filename": "attempt-01-generated.png", "width": 1000, "height": 800, "mode": "RGBA", "sha256": hashlib.sha256((self.task / "attempt-01-generated.png").read_bytes()).hexdigest()},
                "sticker": {"filename": "attempt-01-sticker.png", "width": 1000, "height": 800, "mode": "RGBA", "sha256": self.new_sha},
            },
        }
        (self.task / "attempt-01-generation.json").write_text(json.dumps(generation))
        self.write_review("primary-review.json", {"verdict": "pass", "score": 85})
        self.write_review("attempt-01-blind-review.json", {"verdict": "pass", "score": 86, "candidateHashCheck": {"actual": self.new_sha, "matched": True}})
        for name in ["candidates-20.json", "candidates-next.json"]:
            (self.root / "data" / name).write_text('{"candidates":[]}')
        self.existing = {
            "id": "Mantis_religiosa", "scientificName": "Mantis religiosa", "authority": "(Linnaeus, 1758)",
            "taxonomy": {"system": "GBIF Backbone Taxonomy", "order": "Mantodea", "family": "Mantidae", "genus": "Mantis"},
            "names": {"en": "European mantis", "zh-Hans": "欧洲螳螂", "de": "Gottesanbeterin"},
            "ids": {"wikidata": "Q131736", "gbif": 123}, "range": {"distribution": "欧洲"},
            "traits": {"habitat": "meadow"}, "conservation": {"iucn": "LC"},
            "sticker": {
                "file": "stickers/Mantodea/Mantidae/Mantis_religiosa.webp", "kind": "ai-illustration",
                "sourceSha256": self.old_sha, "reviewScore": 91, "primaryReviewScore": 82,
                "meetsQualityBar": True, "license": "PolyForm-Shield-1.0.0",
                "reference": {"page": "https://example.com/photo"}, "references": [],
            },
        }
        self.languages = [{"code": "en", "source": "project metadata"}, {"code": "de", "source": "Wikidata labels (CC0)"}]
        (self.root / "data/languages.json").write_text(json.dumps(self.languages))
        self.names = b"id,scientificName,en,zh-Hans,de\n"
        (self.root / "data/names.csv").write_bytes(self.names)
        self.reset_public()

    def write_review(self, filename, value):
        primary = filename == "primary-review.json"
        payload = {
            "species": "Mantis religiosa",
            "attempt": 1,
            "reviewer": "Codex CLI fresh primary session" if primary else "Codex CLI fresh ephemeral session",
            "reviewType": "primary-independent" if primary else "blind-independent",
            "score": 85,
            "verdict": "pass",
            "checks": [{"id": row["id"], "status": "pass", "evidence": f"Evidence for {row['id']}"} for row in self.checklist["checks"]],
            "reviewedFiles": {"candidate": "attempt-01-sticker.png", "references": [self.reference_metadata["localPath"]]},
            "candidateHashCheck": {"actual": self.new_sha, "matched": True},
        }
        payload.update(value)
        (self.task / filename).write_text(json.dumps(payload))

    def write_task(self, revision, version=1):
        (self.task / "task.json").write_text(json.dumps({**self.base_task, "revisionOf": revision, "reviewProtocolVersion": version, "stage": "blind-review"}))

    def reset_public(self):
        self.target.write_bytes(self.old_bytes)
        (self.root / "data/species.json").write_text(json.dumps({"species": [copy.deepcopy(self.existing)]}))
        self.write_task(self.revision)

    def assert_rejected_without_changes(self, revision):
        self.reset_public()
        self.write_task(revision)
        with self.assertRaises(ValueError):
            exporter.export_approved(self.task)
        self.assertEqual(self.target.read_bytes(), self.old_bytes)
        self.assertEqual(json.loads((self.root / "data/species.json").read_text())["species"], [self.existing])

    def test_direct_v2_export_requires_complete_review_evidence(self):
        self.write_task(self.revision, version=2)
        incomplete = {"checks": [{"id": "body-anatomy", "status": "pass"}]}
        self.write_review("primary-review.json", incomplete)
        self.write_review("attempt-01-blind-review.json", incomplete)
        with self.assertRaises(ValueError):
            exporter.export_approved(self.task)
        self.assertEqual(self.target.read_bytes(), self.old_bytes)

    def test_direct_v2_export_accepts_complete_validation(self):
        self.write_task(self.revision, version=2)
        result = exporter.export_approved(self.task)
        self.assertEqual(result["sticker"]["sourceSha256"], self.new_sha)
        self.assertEqual(result["sticker"]["revisionOf"], self.revision)

    def test_authorized_revision_preserves_metadata_and_is_idempotent(self):
        result = exporter.export_approved(self.task)
        self.assertNotEqual(self.target.read_bytes(), self.old_bytes)
        for field in ["scientificName", "authority", "taxonomy", "names", "ids", "range", "traits", "conservation"]:
            self.assertEqual(result[field], self.existing[field])
        self.assertEqual(result["sticker"]["sourceSha256"], self.new_sha)
        self.assertEqual(result["sticker"]["revisionOf"], self.revision)
        self.assertEqual(json.loads((self.root / "data/languages.json").read_text()), self.languages)
        self.assertEqual((self.root / "data/names.csv").read_bytes(), self.names)
        before = self.target.read_bytes()
        self.assertEqual(exporter.export_approved(self.task)["sticker"]["sourceSha256"], self.new_sha)
        self.assertEqual(self.target.read_bytes(), before)

    def test_missing_and_stale_lineage_are_rejected(self):
        for revision in [None, {**self.revision, "sourceSha256": "0" * 64}]:
            self.assert_rejected_without_changes(revision)

    def test_nonconcrete_issue_urls_are_rejected(self):
        for suffix in ["", "not-a-number", "0", "21/"]:
            self.assert_rejected_without_changes({**self.revision, "issue": "https://github.com/hunknownz/intoreal-insect-sticker/issues/" + suffix})

    def test_revision_requires_existing_baseline(self):
        self.target.unlink()
        with self.assertRaises(ValueError):
            exporter.export_approved(self.task)
        self.assertFalse(self.target.exists())

    def test_low_score_cannot_replace(self):
        self.write_review("primary-review.json", {"verdict": "pass", "score": 79})
        with self.assertRaises(ValueError):
            exporter.export_approved(self.task)
        self.assertEqual(self.target.read_bytes(), self.old_bytes)

    def test_new_species_export_seeds_identifiers_from_verified_candidates(self):
        self.target.unlink()
        (self.root / "data/species.json").write_text('{"species":[]}')
        (self.root / "data/candidates-expansion-03.json").write_text(json.dumps({"candidates": [
            {
                "scientificName": "Mantis religiosa",
                "taxonomy": {"system": "GBIF Backbone Taxonomy", "order": "Mantodea", "family": "Mantidae", "genus": "Mantis", "authority": "(Linnaeus, 1758)", "gbif": 6258028},
                "ids": {"gbif": 6258028, "wikidata": "Q268319"},
            },
        ]}))
        self.write_task(None)
        result = exporter.export_approved(self.task)
        self.assertEqual(result["authority"], "(Linnaeus, 1758)")
        self.assertEqual(result["taxonomy"]["system"], "GBIF Backbone Taxonomy")
        self.assertEqual(result["ids"], {"gbif": 6258028, "wikidata": "Q268319"})

    def test_new_species_export_preserves_language_files(self):
        self.target.unlink()
        (self.root / "data/species.json").write_text('{"species":[]}')
        self.write_task(None)
        result = exporter.export_approved(self.task)
        self.assertTrue(self.target.is_file())
        self.assertNotIn("revisionOf", result["sticker"])
        self.assertEqual(json.loads((self.root / "data/languages.json").read_text()), self.languages)
        self.assertEqual((self.root / "data/names.csv").read_bytes(), self.names)


if __name__ == "__main__":
    unittest.main()
