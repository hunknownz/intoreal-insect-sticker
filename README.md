# intoREAL insect stickers

<img src="previews/header.webp" alt="intoREAL insect specimen drawer" width="100%">

**A growing library of rigorously reviewed insect stickers for species worldwide. [中文说明 →](README.zh-Hans.md)**

Each published species has a transparent, white-outline WebP sticker, structured taxonomy and names, distribution notes, review scores, and traceable reference metadata. The first formal candidate set covers 20 species across 7 orders; candidates become public only after passing the complete production and review pipeline.

![Reviewed insect stickers](previews/hero.webp)

## What's inside

| Path | Contents |
|---|---|
| `stickers/<Order>/<Family>/<Genus_species>.webp` | Reviewed transparent stickers with a white outline, about 1,000 px on the long side |
| `data/species.json` | Taxonomy, names, distribution, sticker paths, review scores and reference metadata |
| `data/species.csv` | The same core data flattened for spreadsheets |
| `data/names.csv` | Scientific names and currently available common names |
| `data/languages.json` | Current language fields and their sources |
| `data/field-guide.zh-Hans.json` | Chinese appearance, identification and similar-species notes for the 17 published species |
| `data/candidates-20.json` | The first formal candidate set, not a claim of published coverage |
| `previews/` | Header, hero, order and family specimen drawers |

See [data/README.md](data/README.md) for field definitions and publication rules.

## How stickers are made

Original reference photographs are collected locally from sources with recorded authors and licenses. Codex CLI creates a new natural-history illustration, followed by deterministic image and hash checks, an independent primary review, and an isolated blind review in a fresh process. A critical identification failure or a score below 80 blocks publication. Failed attempts and targeted redraws are retained.

GitHub Issues provide the task queue and audit trail. The single-worker pipeline discovers prepared Production issues, executes them serially, exports approved stickers and closes issues automatically. Technical failures or isolation violations remain open with a blocked record instead of being reported as successful.

These are AI-assisted natural-history illustrations, not a substitute for expert taxonomic identification. Features that cannot be checked against the references are marked `unverifiable`.

## Reference photographs

Reference photographs and local reference crops are **not included in the public repository**. Each published record links to the source page and records the author and license under `sticker.reference` and `sticker.references`.

## Use the data

```python
import json
species = json.load(open("data/species.json"))["species"]
by_name = {row["scientificName"]: row for row in species}
print(by_name["Graphosoma italicum"]["sticker"]["file"])
```

Raw sticker paths follow this form:

```text
https://raw.githubusercontent.com/hunknownz/intoreal-insect-sticker/main/stickers/Hemiptera/Pentatomidae/Graphosoma_italicum.webp
```

## Current status

The repository is in its initial production phase. More species, language coverage, identification notes and preview plates will be added only with supporting data. Taxonomic authority sources, cross-database IDs and conservation fields are left empty when no verified source has been integrated.

Stickers and previews are licensed under [PolyForm Shield 1.0.0](LICENSES/PolyForm-Shield-1.0.0.md); project-compiled data is under [MIT](LICENSES/MIT.txt). Third-party material keeps its own terms, with sources and reference-photo policy documented in [LICENSE.md](LICENSE.md) and [NOTICE.md](NOTICE.md).
