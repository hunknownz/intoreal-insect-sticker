import csv
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class PublishedMetadataTests(unittest.TestCase):
    """Published dataset invariants. README claims every species carries exact-match
    GBIF/Wikidata IDs and GBIF taxonomic authority; these tests hold the exports to it."""

    @classmethod
    def setUpClass(cls):
        cls.dataset = json.loads((ROOT / "data/species.json").read_text(encoding="utf-8"))
        cls.rows = cls.dataset["species"]
        with (ROOT / "data/species.csv").open(encoding="utf-8", newline="") as handle:
            cls.csv_rows = {row["id"]: row for row in csv.DictReader(handle)}

    def test_every_species_has_required_metadata(self):
        for row in self.rows:
            with self.subTest(species=row["id"]):
                self.assertTrue(row.get("authority"), "authority missing")
                self.assertEqual(row["taxonomy"].get("system"), "GBIF Backbone Taxonomy")
                self.assertIsInstance(row["ids"].get("gbif"), int)
                self.assertRegex(str(row["ids"].get("wikidata", "")), r"^Q\d+$")
                self.assertTrue(row["names"].get("en"))
                self.assertTrue(row["names"].get("zh-Hans"))
                self.assertTrue(row["range"].get("distribution"))

    def test_csv_covers_every_species(self):
        self.assertEqual(set(self.csv_rows), {row["id"] for row in self.rows})

    def test_csv_metadata_columns_match_json(self):
        for row in self.rows:
            with self.subTest(species=row["id"]):
                csv_row = self.csv_rows[row["id"]]
                self.assertEqual(csv_row["authority"], row.get("authority") or "")
                self.assertEqual(csv_row["taxonomy_system"], row["taxonomy"].get("system") or "")
                self.assertEqual(csv_row["wikidata"], str(row["ids"].get("wikidata", "")))
                self.assertEqual(csv_row["gbif"], str(row["ids"].get("gbif", "")))
                self.assertEqual(csv_row["distribution"], row["range"].get("distribution") or "")


if __name__ == "__main__":
    unittest.main()
