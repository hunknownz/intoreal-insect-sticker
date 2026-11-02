# Notice / 第三方来源说明

The AI-illustrated stickers and previews are licensed under PolyForm Shield 1.0.0 and the data compiled by this project under MIT, to the extent that we hold rights in them (see [LICENSE.md](LICENSE.md)). The items below come from third parties and keep their own terms.

AI 绘制的贴纸与预览图按 PolyForm Shield 1.0.0 授权，本项目整理的数据按 MIT 授权，均限于我们拥有的权利（见 [LICENSE.md](LICENSE.md)）。以下来源沿用各自条款。

## Taxonomy and names / 分类与名称

The initial order, family and species selection was curated by this project using Wikimedia Commons taxon pages and related public taxonomic sources. No IOC, AVONET or other third-party taxonomic dataset has been redistributed. `taxonomy.system`, `authority`, cross-database IDs, traits and conservation fields remain empty unless a verified source has been integrated.

首批目、科、种由本项目依据 Wikimedia Commons 分类页及相关公开分类资料整理。未再分发 IOC、AVONET 或其他第三方分类数据集。只有接入并核实来源后，才填写 `taxonomy.system`、命名权威、跨数据库 ID、形态生态与保护状态字段。

GBIF identifiers, taxonomic authority and `taxonomy.system` were matched through the [GBIF species API](https://www.gbif.org/developer/species), using accepted species whose canonical names match exactly. GBIF Backbone Taxonomy terms: <https://www.gbif.org/terms>. Wikidata identifiers were matched through the [Wikidata API](https://www.wikidata.org/w/api.php) (CC0). Fields that could not be matched remain empty rather than inferred.

GBIF 的标识、命名权威和 `taxonomy.system` 通过 GBIF species API 获取，仅采用学名精确匹配的接受种，相关条款见上述链接。Wikidata 标识通过 Wikidata API 获取（CC0）。无法匹配的字段保持为空，不作猜测。

## Chinese field-guide notes / 中文图鉴

`data/field-guide.zh-Hans.json` contains original Chinese notes written from project-approved reference photographs, GBIF taxonomic records and independent review evidence, and is shared under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). `basedOn` records the taxonomic page and principal morphology reference for each species. No Wikipedia article text is redistributed.

`data/field-guide.zh-Hans.json` 中的中文图鉴文字依据项目批准的参考照片、GBIF 分类信息和独立审核证据改写，按 CC BY-SA 4.0 共享。`basedOn` 记录每个物种的分类页面和主要形态依据，不再分发维基百科正文。

## Reference photos / 参考照片

Each sticker is a new AI illustration constrained by one or more reference photographs or scientific figure crops. **Original reference photographs and local crops are not included in the public repository.** Source pages, authors and licenses are recorded per species in `data/species.json` under `sticker.reference` and `sticker.references`. Rights in those works remain with their original authors.

每张 AI 贴纸都以一张或多张参考照片或科研图版局部约束形态。**原始参考照片及本地裁剪不进入公开仓库。** 每个物种的来源页面、作者和许可均记录在 `data/species.json` 的 `sticker.reference` 与 `sticker.references` 中，相关权利仍归原作者所有。

Whether a new illustration made from a reference image is bound by that image's license depends on the jurisdiction and the nature of the use. The project records reference licenses so users can filter and review them; no reference-photo license is claimed as the license of the new illustrations.

参考图的许可是否约束新插画取决于司法辖区和具体使用方式。本项目记录参考许可以便筛选和核对，不把参考照片的许可直接当作新插画的许可。

If you are the author of a reference image and object to its use in this project, open an issue at https://github.com/hunknownz/intoreal-insect-sticker/issues. We will review and replace or remove the affected material within 7 days.

如果你是参考图作者，不希望本项目使用相关材料，请通过上述 Issue 联系我们。我们将在 7 天内复核并替换或撤下相关内容。

## Review and automation / 审核与自动化

Stickers are produced with Codex CLI image generation and reviewed in separate primary and blind-review processes. These are AI-assisted illustrations, not expert taxonomic determinations. Uncertain features are recorded as `unverifiable`.

贴纸由 Codex CLI 生成，并通过相互独立的一审和盲审。它们属于 AI 辅助自然史插画，不等同于专家分类鉴定，无法核实的特征均标为 `unverifiable`。
