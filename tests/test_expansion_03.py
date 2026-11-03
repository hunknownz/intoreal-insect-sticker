import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Expansion03Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dataset = json.loads((ROOT / "data/candidates-expansion-03.json").read_text())
        cls.rows = dataset["candidates"]

    def test_four_candidates_covering_target_groups(self):
        self.assertEqual(len(self.rows), 4)
        self.assertEqual(
            {row["id"] for row in self.rows},
            {"Cetonia_aurata", "Aglais_io", "Orthetrum_cancellatum", "Araneus_diadematus"},
        )
        orders = {row["taxonomy"]["order"] for row in self.rows}
        self.assertEqual(orders, {"Coleoptera", "Lepidoptera", "Odonata", "Araneae"})

    def test_spider_is_recorded_as_araneae_not_insect(self):
        spider = next(row for row in self.rows if row["id"] == "Araneus_diadematus")
        self.assertEqual(spider["taxonomy"]["order"], "Araneae")
        self.assertEqual(spider["taxonomy"]["family"], "Araneidae")
        self.assertEqual(spider["taxonomy"]["authority"], "Clerck, 1757")

    def test_references_are_complete(self):
        for row in self.rows:
            self.assertGreaterEqual(len(row["references"]), 3)
            self.assertEqual(sum(ref["role"] == "primary-pose" for ref in row["references"]), 1)
            for reference in row["references"]:
                self.assertEqual(reference["imageReview"], "approved")
                self.assertEqual(reference["archive"], "local-only")
                self.assertRegex(reference["sha256"], r"^[0-9a-f]{64}$")
                self.assertTrue(reference["author"])
                self.assertTrue(reference["license"])
                self.assertNotIn("localPath", reference)

    def test_verified_names_and_status(self):
        for row in self.rows:
            self.assertIn(row["status"], {"pilot-ready", "published", "blocked"})
            self.assertEqual(row["reviewProtocolVersion"], 2)
            self.assertNotIn("pilot", row)
            self.assertEqual(row["batch"], "expansion-03")
            self.assertTrue(row["verification"]["gbifExactMatch"])
            self.assertTrue(row["verification"]["licenseVerified"])
            self.assertTrue(row["commonNameZhHans"])
            self.assertTrue(row["commonNameEn"])
            self.assertTrue(re.fullmatch(r"Q\d+", row["ids"]["wikidata"]))
            self.assertTrue(row["distributionSource"].startswith("https://www.gbif.org/species/"))
            self.assertEqual(row["taxonomy"]["gbif"], row["ids"]["gbif"])

    def test_local_reference_files_match_hashes(self):
        selection_path = ROOT / "production/expansion-03/expansion-03-selection.json"
        if not selection_path.exists():
            self.skipTest("local reference library is not part of the public repository")
        selection = json.loads(selection_path.read_text())
        by_id = {c["id"]: c for c in selection["candidates"]}
        self.assertEqual(set(by_id), {row["id"] for row in self.rows})
        import hashlib

        for sid, candidate in by_id.items():
            self.assertGreaterEqual(len(candidate["references"]), 3)
            for ref in candidate["references"]:
                path = ROOT / "production" / sid / ref["localPath"]
                self.assertTrue(path.is_file(), path)
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), ref["sha256"])


if __name__ == "__main__":
    unittest.main()
