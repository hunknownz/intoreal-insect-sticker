#!/usr/bin/env python3
import argparse
import csv
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from sticker_export import write_csv_exports

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = PROJECT_ROOT / "data/species.json"
USER_AGENT = "intoREAL-insect-sticker/1.0 (multilingual metadata)"
LANGUAGES = [
    "en", "ca", "zh-Hans", "zh-Hant", "hr", "cs", "da", "nl", "eo", "fi",
    "fr", "de", "it", "ja", "lt", "no", "pl", "pt-x-lusophone", "pt-PT", "ru",
    "sr", "sk", "es", "sv", "tr", "uk", "af", "ar", "be", "bg", "et",
    "fr-x-gaudin", "el", "he", "hu", "is", "id", "ko", "lv", "mk", "ml",
    "se", "fa", "ro", "sl", "th",
]


def get_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def taxon_name(qid):
    query = urllib.parse.urlencode({"action": "wbgetentities", "ids": qid, "props": "claims", "format": "json"})
    claims = get_json(f"https://www.wikidata.org/w/api.php?{query}")["entities"][qid].get("claims", {})
    for statement in claims.get("P225", []):
        value = statement.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, str):
            return value
    return None


def resolve_wikidata(scientific_name):
    query = urllib.parse.urlencode({"action": "wbsearchentities", "search": scientific_name, "language": "en", "format": "json", "limit": 5})
    candidates = get_json(f"https://www.wikidata.org/w/api.php?{query}").get("search", [])
    for candidate in candidates:
        qid = candidate.get("id", "")
        if candidate.get("label", "").casefold() == scientific_name.casefold():
            return qid
        if "species of insect" in candidate.get("description", "").casefold() and taxon_name(qid) == scientific_name:
            return qid
    return None


def label_value(value):
    return value[0]["value"] if isinstance(value, list) else value["value"]


def fetch_labels(ids):
    if not ids:
        return {}
    query = urllib.parse.urlencode({
        "action": "wbgetentities",
        "ids": "|".join(sorted(ids)),
        "props": "labels",
        "languages": "|".join(LANGUAGES),
        "format": "json",
    })
    entities = get_json(f"https://www.wikidata.org/w/api.php?{query}")["entities"]
    return {qid: {code: label_value(values) for code, values in row.get("labels", {}).items() if values} for qid, row in entities.items()}


def write_names_csv(rows):
    path = PROJECT_ROOT / "data/names.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "scientificName", *LANGUAGES])
        writer.writeheader()
        for row in rows:
            writer.writerow({"id": row["id"], "scientificName": row["scientificName"], **{code: row["names"].get(code, "") for code in LANGUAGES}})


def main():
    parser = argparse.ArgumentParser(description="Fill missing Wikidata IDs and exact multilingual labels.")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    dataset = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    missing = [row for row in dataset["species"] if not row["ids"].get("wikidata")]
    resolved = {}
    for row in missing:
        try:
            qid = resolve_wikidata(row["scientificName"])
            if qid:
                resolved[row["id"]] = qid
        except Exception as exc:
            resolved[row["id"]] = f"ERROR: {exc}"
        time.sleep(0.5)
    all_ids = {row["ids"].get("wikidata") for row in dataset["species"]} | set(resolved.values())
    labels = fetch_labels({qid for qid in all_ids if qid and not qid.startswith("ERROR:")})
    summary = {"resolved": resolved, "labelCounts": {code: 0 for code in LANGUAGES}, "errors": []}
    for row in dataset["species"]:
        qid = row["ids"].get("wikidata") or resolved.get(row["id"])
        entity_labels = labels.get(qid, {})
        for code in LANGUAGES:
            if code in {"en", "zh-Hans"}:
                continue
            if code in entity_labels:
                row["names"][code] = entity_labels[code]
        if qid and not qid.startswith("ERROR:"):
            row["ids"]["wikidata"] = qid
        for code in LANGUAGES:
            if row["names"].get(code):
                summary["labelCounts"][code] += 1
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not args.apply:
        return 0
    DATA_PATH.write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv_exports(dataset["species"])
    write_names_csv(dataset["species"])
    (PROJECT_ROOT / "data/languages.json").write_text(json.dumps([
        {"code": code, "source": "project metadata" if code in {"en", "zh-Hans"} else "Wikidata labels (CC0)"}
        for code in LANGUAGES
    ], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
