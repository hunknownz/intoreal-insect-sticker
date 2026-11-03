import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from sticker_export import candidate_distribution, candidate_identifiers


class CandidateDistributionTests(unittest.TestCase):
    def test_expansion_distribution_is_explicit_not_inferred_from_sampling_regions(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            (root / "data").mkdir()
            (root / "data/candidates-20.json").write_text(json.dumps({"candidates": [{"scientificName": "Apis mellifera", "distribution": "全球养殖"}]}))
            (root / "data/candidates-next.json").write_text('{"candidates":[]}')
            (root / "data/candidates-expansion-30.json").write_text(json.dumps({"candidates": [
                {"scientificName": "Schistocerca gregaria", "distribution": "非洲、亚洲", "samplingRegions": ["非洲", "亚洲"]},
                {"scientificName": "Example species", "samplingRegions": ["欧洲"]},
            ]}))
            with patch("sticker_export.PROJECT_ROOT", root):
                self.assertEqual(candidate_distribution("Schistocerca gregaria"), "非洲、亚洲")
                self.assertEqual(candidate_distribution("Example species"), "")
                self.assertEqual(candidate_distribution("Apis mellifera"), "全球养殖")

    def test_future_candidate_batches_are_discovered_automatically(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            (root / "data").mkdir()
            (root / "data/candidates-expansion-20.json").write_text(json.dumps({"candidates": [
                {"scientificName": "Cetonia aurata", "distribution": "欧洲、中亚"},
            ]}))
            with patch("sticker_export.PROJECT_ROOT", root):
                self.assertEqual(candidate_distribution("Cetonia aurata"), "欧洲、中亚")

    def test_candidate_identifiers_prefers_verified_candidate_metadata(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            (root / "data").mkdir()
            (root / "data/candidates-expansion-03.json").write_text(json.dumps({"candidates": [
                {
                    "scientificName": "Cetonia aurata",
                    "taxonomy": {"system": "GBIF Backbone Taxonomy", "order": "Coleoptera", "family": "Scarabaeidae", "genus": "Cetonia", "authority": "(Linnaeus, 1758)", "gbif": 1077829},
                    "ids": {"gbif": 1077829, "wikidata": "Q731970"},
                },
                {"scientificName": "Legacy species", "taxonomy": None},
            ]}))
            with patch("sticker_export.PROJECT_ROOT", root):
                self.assertEqual(
                    candidate_identifiers("Cetonia aurata"),
                    {"system": "GBIF Backbone Taxonomy", "authority": "(Linnaeus, 1758)", "gbif": 1077829, "wikidata": "Q731970"},
                )
                self.assertEqual(candidate_identifiers("Legacy species"), {})
                self.assertEqual(candidate_identifiers("Missing species"), {})


if __name__ == "__main__":
    unittest.main()
