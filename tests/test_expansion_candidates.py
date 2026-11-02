import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data/candidates-expansion-30.json"


class ExpansionCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        cls.rows = cls.dataset["candidates"]

    def test_thirty_unique_species(self):
        self.assertEqual(self.dataset["count"], 30)
        self.assertEqual(len(self.rows), 30)
        names = [row["scientificName"] for row in self.rows]
        self.assertEqual(len(set(names)), 30)
        self.assertEqual(names, sorted(names))

    def test_exact_gbif_taxonomy(self):
        for row in self.rows:
            taxonomy = row["taxonomy"]
            self.assertEqual(taxonomy["system"], "GBIF Backbone Taxonomy")
            self.assertIsInstance(taxonomy["gbif"], int)
            self.assertTrue(taxonomy["order"])
            self.assertTrue(taxonomy["family"])
            self.assertTrue(taxonomy["genus"])
            self.assertTrue(row["verification"]["gbifExactMatch"])

    def test_sampling_regions_cover_six_continents(self):
        regions = {region for row in self.rows for region in row["samplingRegions"]}
        self.assertTrue({"非洲", "亚洲", "欧洲", "北美洲", "南美洲", "大洋洲"} <= regions)
        for row in self.rows:
            self.assertEqual(row["lifeStage"], "adult")
            self.assertTrue(row["unverifiable"])

    def test_reference_sources_and_licenses(self):
        for row in self.rows:
            self.assertTrue(row["verification"]["licenseVerified"])
            primary = [ref for ref in row["references"] if ref["role"] in {"primary-pose-candidate", "primary-pose"}]
            self.assertEqual(len(primary), 1)
            for reference in row["references"]:
                self.assertTrue(reference["page"].startswith("https://commons.wikimedia.org/wiki/File:"))
                self.assertTrue(reference["author"])
                self.assertTrue(reference["license"])
                self.assertTrue(reference["view"])
                self.assertEqual(reference["lifeStage"], "adult")
                self.assertIn("sex", reference)
                self.assertIn(reference["imageReview"], {"pending", "approved"})
                self.assertNotIn("localPath", reference)

    def test_three_pilot_ready_candidates(self):
        pilots = [row for row in self.rows if row.get("pilot") is True]
        self.assertEqual(len(pilots), 3)
        for row in pilots:
            self.assertEqual(row["status"], "pilot-ready")
            self.assertEqual(row["reviewProtocolVersion"], 2)
            self.assertGreaterEqual(len(row["references"]), 2)
            self.assertEqual(sum(ref["role"] == "primary-pose" for ref in row["references"]), 1)
            for reference in row["references"]:
                self.assertEqual(reference["imageReview"], "approved")
                self.assertEqual(reference["archive"], "local-only")
                self.assertRegex(reference["sha256"], r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
