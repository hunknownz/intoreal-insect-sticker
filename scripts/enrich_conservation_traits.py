#!/usr/bin/env python3
import argparse
import json
import urllib.parse
import urllib.request
from decimal import Decimal
from pathlib import Path
from sticker_export import write_csv_exports

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = PROJECT_ROOT / "data/species.json"
USER_AGENT = "IntoReal-insect-sticker/1.0 (conservation and trait verification)"
UNIT_SCALE = {"Q174789": 1, "Q174728": 10, "Q11573": 1000, "Q218593": 25.4, "Q3710": 304.8}
IUCN_CODES = {
    "least concern": "LC",
    "near threatened": "NT",
    "vulnerable": "VU",
    "endangered": "EN",
    "critically endangered": "CR",
    "extinct in the wild": "EW",
    "extinct": "EX",
    "data deficient": "DD",
    "not evaluated": "NE",
}


def get_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def get_entities(ids, props):
    if not ids:
        return {}
    query = urllib.parse.urlencode({"action": "wbgetentities", "ids": "|".join(sorted(ids)), "props": props, "languages": "en", "format": "json"})
    return get_json(f"https://www.wikidata.org/w/api.php?{query}")["entities"]


def item_ids(statements):
    result = set()
    for statement in statements:
        value = statement.get("mainsnak", {}).get("datavalue", {}).get("value", {})
        if value.get("entity-type") == "item" and value.get("id"):
            result.add(value["id"])
    return result


def labels_for(ids):
    entities = get_entities(ids, "labels")
    return {qid: row.get("labels", {}).get("en", {}).get("value") for qid, row in entities.items()}


def quantities(statements):
    values = []
    for statement in statements:
        value = statement.get("mainsnak", {}).get("datavalue", {}).get("value", {})
        unit = value.get("unit", "").rsplit("/", 1)[-1]
        if unit not in UNIT_SCALE or "amount" not in value:
            continue
        values.append(float(Decimal(value["amount"]) * UNIT_SCALE[unit]))
    return sorted(set(values))


def main():
    parser = argparse.ArgumentParser(description="Enrich conservation and traits from exact Wikidata claims.")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    dataset = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    ids = {row["ids"]["wikidata"] for row in dataset["species"] if row["ids"].get("wikidata")}
    entities = get_entities(ids, "claims")
    referenced = set()
    for entity in entities.values():
        claims = entity.get("claims", {})
        for prop in ("P141", "P7603", "P2974"):
            referenced |= item_ids(claims.get(prop, []))
    labels = labels_for(referenced)
    summary = {"iucn": {}, "cites": {}, "traits": {}}
    for row in dataset["species"]:
        qid = row["ids"]["wikidata"]
        claims = entities[qid].get("claims", {})
        if claims.get("P141"):
            status = next((labels.get(qid) for qid in item_ids(claims["P141"]) if labels.get(qid) in IUCN_CODES), None)
            if status:
                row["conservation"]["iucn"] = IUCN_CODES[status]
                row["conservation"].setdefault("sources", {})["iucn"] = "Wikidata P141"
                summary["iucn"][row["id"]] = row["conservation"]["iucn"]
        if claims.get("P7603"):
            status = next((labels.get(qid) for qid in item_ids(claims["P7603"]) if labels.get(qid, "").lower().startswith("appendix")), None)
            if status:
                row["conservation"]["cites"] = status
                row["conservation"].setdefault("sources", {})["cites"] = "Wikidata P7603"
                summary["cites"][row["id"]] = status
        if claims.get("P2974"):
            habitats = sorted({labels[qid] for qid in item_ids(claims["P2974"]) if labels.get(qid)})
            if habitats:
                row["traits"]["habitat"] = ", ".join(habitats)
                row["traits"].setdefault("sources", {})["habitat"] = "Wikidata P2974"
                summary["traits"].setdefault(row["id"], {})["habitat"] = row["traits"]["habitat"]
        for prop, field, source in (("P2043", "bodyLengthMm", "Wikidata P2043"), ("P2050", "wingspanMm", "Wikidata P2050"), ("P2067", "massG", "Wikidata P2067")):
            values = quantities(claims.get(prop, []))
            if values:
                row["traits"][field] = values[0] if len(values) == 1 else {"min": values[0], "max": values[-1]}
                row["traits"].setdefault("sources", {})[field] = source
                summary["traits"].setdefault(row["id"], {})[field] = row["traits"][field]
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.apply:
        DATA_PATH.write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_csv_exports(dataset["species"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
