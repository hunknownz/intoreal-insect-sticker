#!/usr/bin/env python3
import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMMON_NAMES_EN = {
    "Papilio xuthus": "Asian swallowtail",
    "Papilio machaon": "Old World swallowtail",
    "Pieris rapae": "Small white",
    "Aeshna cyanea": "Southern hawker",
    "Actias selene": "Indian moon moth",
    "Danaus plexippus": "Monarch",
    "Vanessa cardui": "Painted lady",
    "Coccinella septempunctata": "Seven-spot ladybird",
    "Harmonia axyridis": "Harlequin ladybird",
    "Carabus auratus": "Golden ground beetle",
    "Coccinella undecimpunctata": "Eleven-spot ladybird",
    "Pantala flavescens": "Wandering glider",
    "Anax imperator": "Emperor dragonfly",
    "Ischnura elegans": "Blue-tailed damselfly",
    "Tenodera sinensis": "Chinese mantis",
    "Mantis religiosa": "European mantis",
    "Apis mellifera": "Western honey bee",
    "Bombus terrestris": "Buff-tailed bumblebee",
    "Vespa mandarinia": "Asian giant hornet",
    "Nezara viridula": "Southern green stink bug",
    "Graphosoma italicum": "Italian striped bug",
    "Eristalis tenax": "Drone fly",
    "Lucilia sericata": "Common green bottle fly",
}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def review_path(task_dir, stage, attempt):
    if stage == "primary":
        return task_dir / ("primary-review.json" if attempt == 1 else f"primary-review-attempt-{attempt:02d}.json")
    return task_dir / f"attempt-{attempt:02d}-blind-review.json"


def candidate_distribution(scientific_name):
    for filename in ("candidates-20.json", "candidates-next.json"):
        for row in read_json(PROJECT_ROOT / "data" / filename)["candidates"]:
            if row["scientificName"] == scientific_name:
                return row["distribution"]
    return ""


def public_reference(row):
    return {key: row[key] for key in ("type", "view", "page", "author", "license") if key in row}


def export_approved(task_dir):
    task_dir = Path(task_dir).resolve()
    task = read_json(task_dir / "task.json")
    species = task["species"]
    scientific_name = species["scientificName"]
    attempt = task["attempt"]
    candidate = task_dir / f"attempt-{attempt:02d}-sticker.png"
    from codex_pipeline import validate_done
    validate_done(task_dir, task)
    primary = read_json(review_path(task_dir, "primary", attempt))
    blind = read_json(review_path(task_dir, "blind", attempt))
    if primary.get("verdict") != "pass" or blind.get("verdict") != "pass":
        raise ValueError("两级审核未全部通过，禁止导出")
    if primary.get("score", 0) < 80 or blind.get("score", 0) < 80:
        raise ValueError("审核分数低于质量门槛，禁止导出")
    source_sha256 = sha256(candidate)
    if blind.get("candidateHashCheck", {}).get("actual") != source_sha256:
        raise ValueError("候选与盲审哈希不一致，禁止导出")

    order = species["order"]
    family = species["family"]
    species_id = scientific_name.replace(" ", "_")
    relative_sticker = Path("stickers") / order / family / f"{species_id}.webp"
    target = PROJECT_ROOT / relative_sticker
    data_path = PROJECT_ROOT / "data/species.json"
    existing = None
    if target.exists():
        dataset = read_json(data_path) if data_path.exists() else {"species": []}
        existing = next((row for row in dataset["species"] if row["id"] == species_id), None)
        if existing and existing["sticker"].get("sourceSha256") == source_sha256:
            return existing
        revision = task.get("revisionOf")
        authorized_revision = (
            existing is not None
            and isinstance(revision, dict)
            and isinstance(revision.get("issue"), str)
            and re.fullmatch(r"https://github\.com/hunknownz/intoreal-insect-sticker/issues/[1-9]\d*", revision["issue"]) is not None
            and type(revision.get("attempt")) is int
            and revision["attempt"] > 0
            and isinstance(revision.get("sourceSha256"), str)
            and len(revision["sourceSha256"]) == 64
            and all(character in "0123456789abcdef" for character in revision["sourceSha256"])
            and revision["sourceSha256"] == existing["sticker"].get("sourceSha256")
        )
        if not authorized_revision:
            raise ValueError(f"公开贴纸已存在且来源不同，拒绝覆盖: {target}")
    elif task.get("revisionOf"):
        raise ValueError("修订替换缺少现有公开贴纸，拒绝作为新物种发布")

    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(candidate) as image:
        if image.mode != "RGBA" or max(image.size) != 1000:
            raise ValueError("导出候选必须为长边1000px的RGBA图片")
        temporary = target.with_suffix(".webp.tmp")
        image.save(temporary, "WEBP", quality=92, method=6, exact=True)
    with Image.open(temporary) as exported:
        if exported.mode != "RGBA" or exported.size != image.size:
            temporary.unlink()
            raise ValueError("WebP 导出核验失败")
    temporary.replace(target)

    references = read_json(task_dir / "references.json")["references"]
    record = {
        "id": species_id,
        "scientificName": scientific_name,
        "authority": None,
        "taxonomy": {
            "system": None,
            "order": order,
            "family": family,
            "genus": scientific_name.split()[0],
        },
        "names": {
            "en": species.get("commonNameEn") or COMMON_NAMES_EN.get(scientific_name, scientific_name),
            "zh-Hans": species["commonNameZhHans"],
        },
        "ids": {},
        "range": {"distribution": candidate_distribution(scientific_name)},
        "traits": {},
        "conservation": {},
        "sticker": {
            "file": relative_sticker.as_posix(),
            "kind": "ai-illustration",
            "reviewScore": blind["score"],
            "primaryReviewScore": primary["score"],
            "meetsQualityBar": True,
            "license": "PolyForm-Shield-1.0.0",
            "sourceSha256": source_sha256,
            "reference": public_reference(references[0]),
            "references": [public_reference(row) for row in references],
        },
    }
    if existing is not None:
        record["sticker"]["revisionOf"] = task["revisionOf"]
        existing["sticker"] = record["sticker"]
        record = existing
    dataset = read_json(data_path) if data_path.exists() else {"species": []}
    dataset["species"] = [row for row in dataset["species"] if row["id"] != species_id]
    dataset["species"].append(record)
    dataset["species"].sort(key=lambda row: row["scientificName"])
    write_json(data_path, dataset)
    write_csv_exports(dataset["species"])
    languages_path = PROJECT_ROOT / "data/languages.json"
    if not languages_path.exists():
        write_json(languages_path, [
            {"code": "en", "source": "project metadata"},
            {"code": "zh-Hans", "source": "project metadata"},
        ])
    return record


def write_csv_exports(rows):
    fieldnames = [
        "id", "scientificName", "authority", "taxonomy_system", "order", "family", "genus", "name_en",
        "name_zh-Hans", "distribution", "wikidata", "gbif", "sticker_file", "review_score",
        "meets_quality_bar", "iucn", "cites", "body_length_mm", "wingspan_mm", "mass_g", "habitat", "reference_page", "reference_author", "reference_license",
    ]
    path = PROJECT_ROOT / "data/species.csv"
    temporary = path.with_suffix(".csv.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "id": row["id"],
                "scientificName": row["scientificName"],
                "authority": row.get("authority") or "",
                "taxonomy_system": row["taxonomy"].get("system") or "",
                "order": row["taxonomy"]["order"],
                "family": row["taxonomy"]["family"],
                "genus": row["taxonomy"]["genus"],
                "name_en": row["names"]["en"],
                "name_zh-Hans": row["names"]["zh-Hans"],
                "distribution": row["range"]["distribution"],
                "wikidata": row["ids"].get("wikidata", ""),
                "gbif": row["ids"].get("gbif", ""),
                "sticker_file": row["sticker"]["file"],
                "review_score": row["sticker"]["reviewScore"],
                "meets_quality_bar": str(row["sticker"]["meetsQualityBar"]).lower(),
                "iucn": row["conservation"].get("iucn", ""),
                "cites": row["conservation"].get("cites", ""),
                "body_length_mm": json.dumps(row["traits"]["bodyLengthMm"], ensure_ascii=False) if isinstance(row["traits"].get("bodyLengthMm"), dict) else row["traits"].get("bodyLengthMm", ""),
                "wingspan_mm": json.dumps(row["traits"]["wingspanMm"], ensure_ascii=False) if isinstance(row["traits"].get("wingspanMm"), dict) else row["traits"].get("wingspanMm", ""),
                "mass_g": json.dumps(row["traits"]["massG"], ensure_ascii=False) if isinstance(row["traits"].get("massG"), dict) else row["traits"].get("massG", ""),
                "habitat": row["traits"].get("habitat", ""),
                "reference_page": row["sticker"]["reference"].get("page", ""),
                "reference_author": row["sticker"]["reference"].get("author", ""),
                "reference_license": row["sticker"]["reference"].get("license", ""),
            })
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description="Export an approved formal insect task to the public bird-sticker-compatible layout.")
    parser.add_argument("task_dirs", nargs="+")
    args = parser.parse_args()
    try:
        records = [export_approved(path) for path in args.task_dirs]
        result = {"ok": True, "exported": [row["sticker"]["file"] for row in records]}
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
