#!/usr/bin/env python3
import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from sticker_export import write_csv_exports

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = PROJECT_ROOT / "data/species.json"
USER_AGENT = "IntoReal-insect-sticker/1.0 (metadata verification)"


def get_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def wikidata_id(scientific_name):
    query = urllib.parse.urlencode({"action": "wbsearchentities", "search": scientific_name, "language": "en", "format": "json", "limit": 5})
    results = get_json(f"https://www.wikidata.org/w/api.php?{query}").get("search", [])
    for row in results:
        if row.get("label", "").casefold() == scientific_name.casefold() and row.get("id", "").startswith("Q"):
            return row["id"]
    return None


def gbif_match(scientific_name):
    query = urllib.parse.urlencode({"name": scientific_name, "rank": "species"})
    row = get_json(f"https://api.gbif.org/v1/species/match?{query}")
    canonical = row.get("canonicalName", "")
    if canonical.casefold() != scientific_name.casefold() or row.get("status") != "ACCEPTED":
        return None
    return row


def enrich(row):
    scientific_name = row["scientificName"]
    result = {"id": row["id"], "wikidata": None, "gbif": None, "authority": None, "taxonomySystem": None}
    try:
        result["wikidata"] = wikidata_id(scientific_name)
    except Exception as exc:
        result["wikidataError"] = str(exc)
    time.sleep(0.15)
    try:
        match = gbif_match(scientific_name)
        if match:
            result["gbif"] = match["usageKey"]
            result["authority"] = match.get("authorship")
            if not result["authority"] and match.get("scientificName"):
                result["authority"] = match["scientificName"].split(scientific_name, 1)[-1].strip() or None
            result["taxonomySystem"] = "GBIF Backbone Taxonomy"
    except Exception as exc:
        result["gbifError"] = str(exc)
    time.sleep(0.15)
    return result


def main():
    parser = argparse.ArgumentParser(description="Enrich published species with exact-match Wikidata and GBIF metadata.")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    dataset = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    results = [enrich(row) for row in dataset["species"]]
    print(json.dumps(results, ensure_ascii=False, indent=2))
    if not args.apply:
        return 0
    by_id = {row["id"]: row for row in results}
    for row in dataset["species"]:
        result = by_id[row["id"]]
        if result["wikidata"]:
            row["ids"]["wikidata"] = result["wikidata"]
        if result["gbif"]:
            row["ids"]["gbif"] = result["gbif"]
        if result["authority"]:
            row["authority"] = result["authority"]
        if result["taxonomySystem"]:
            row["taxonomy"]["system"] = result["taxonomySystem"]
    DATA_PATH.write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv_exports(dataset["species"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
