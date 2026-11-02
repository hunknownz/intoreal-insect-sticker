import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ExpansionNextBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dataset = json.loads((ROOT / "data/candidates-expansion-30.json").read_text())
        cls.rows = [row for row in dataset["candidates"] if row.get("batch") == "expansion-02"]

    def test_three_new_candidates_with_new_orders(self):
        self.assertEqual(len(self.rows), 3)
        self.assertEqual({row["id"] for row in self.rows}, {"Mantispa_styriaca", "Limnephilus_lunatus", "Gromphadorhina_portentosa"})
        orders = {row["taxonomy"]["order"] for row in self.rows}
        self.assertIn("Neuroptera", orders)
        self.assertIn("Trichoptera", orders)
        for row in self.rows:
            self.assertIn(row["status"], {"pilot-ready", "published", "blocked"})
            self.assertEqual(row["reviewProtocolVersion"], 2)
            if row["status"] == "published":
                self.assertGreaterEqual(row["reviewScore"], 80)
                self.assertGreaterEqual(row["primaryReviewScore"], 80)
                self.assertTrue(row["sticker"].startswith("stickers/"))
            elif row["status"] == "blocked":
                self.assertNotIn("sticker", row)
            self.assertNotIn("pilot", row)
            self.assertTrue(row["distributionSource"].startswith("https://www.gbif.org/species/"))

    def test_next_batch_references_are_complete(self):
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


if __name__ == "__main__":
    unittest.main()
