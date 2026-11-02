import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from sticker_export import candidate_distribution


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


if __name__ == "__main__":
    unittest.main()
