# 昆虫贴纸数据说明

本目录采用与 `huashu-bird-sticker` 对应的公开数据结构。当前仅收录已经通过正式生产审核的物种，候选清单不等于已发布成品。

## 文件

| 文件 | 内容 | 许可 |
|---|---|---|
| `species.json` | 每个已发布物种的分类、名称、分布、贴纸路径、审核分数和参考来源 | 项目整理部分 MIT；第三方字段保留各自条款 |
| `species.csv` | `species.json` 的表格展开版本 | 同上 |
| `names.csv` | 物种学名与当前可用语言名称 | 项目整理部分 MIT |
| `languages.json` | 当前名称字段及来源 | MIT |
| `field-guide.zh-Hans.json` | 17 个已发布物种的中文形态、辨识和相似种说明 | CC BY-SA 4.0；basedOn 记录分类与形态依据 |
| `candidates-20.json` | 首批 20 种生产候选及参考元数据，不代表已通过审核 | 项目整理部分 MIT；参考照片保留各自许可 |

## 贴纸路径

```text
stickers/<Order>/<Family>/<Genus_species>.webp
```

贴纸为保留 alpha 透明通道的 WebP，长边约 1000px。只有一审和独立盲审均达到质量门槛的物种才会自动导出。`sticker.sourceSha256` 对应审核通过的原始 PNG 候选，便于复核同一交付对象。

## 主要字段

- `taxonomy.order`、`taxonomy.family`、`taxonomy.genus`：拉丁分类名称。
- `names.en`、`names.zh-Hans`：当前英文名和简体中文名。
- `range.distribution`：候选阶段整理的分布简述。
- `sticker.reviewScore`：独立盲审分数。
- `sticker.primaryReviewScore`：独立一审分数。
- `sticker.meetsQualityBar`：是否达到当前发布质量门槛。
- `sticker.reference`、`sticker.references`：参考页面、作者和许可；原始照片不包含在公开仓库中。
- `sticker.license`：项目贴纸许可，当前为 `PolyForm-Shield-1.0.0`；参考照片保留各自许可，不与新插画许可混同。

`taxonomy.system` 和命名权威来自 GBIF Backbone Taxonomy 的精确接受种匹配；`ids.wikidata` 与 `ids.gbif` 分别来自 Wikidata API 和 GBIF species API。无法匹配的字段保持为空，不根据模型印象编造。更多语言、生态特征和保护状态仍待可靠来源接入。
