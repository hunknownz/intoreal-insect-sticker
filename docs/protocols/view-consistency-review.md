# 结构与视角一致性审核（v2）

## 目的

防止“每个部位都像，但组合起来不成立”的生成图通过审核。该检查适用于新任务和明确修订任务，不改写历史审核结果。

## 生成要求

1. 在任务书中明确一张全身主姿态参考，并写出目标视角。
2. 局部参考只用于对应部位的结构、纹理和色彩，不得把其视角强行移植到主姿态。
3. 头、颈、前胸、胸部、腹部及可见关节必须属于同一身体、同一姿态和同一透视关系。
4. 活动范围不能替代同姿态证据。不能从一张正面头照和一张背面躯干照推断组合姿态成立。
5. 未由参考证明的精细结构继续标为 `unverifiable`，不得凭印象补造。

## 审核要求

`review-checklist.json` 必须包含：

```json
{"id": "view-consistency", "critical": true, "requirement": "Head, neck, thorax, abdomen and visible joints must form one physically coherent pose and perspective, supported by the approved references; no incompatible view compositing."}
```

按物种补充具体关节和辨识结构。例如螳螂必须明确核对头、颈与细长前胸的连接，不能只看是否存在三角头。

一审和盲审都必须：

- 实际查看全部指定参考，不挑选有利于通过的参考；
- 在 `reviewedFiles.references` 中列出全部参考，且与任务声明一致；
- 在 `view-consistency.evidence` 中写明候选和参考的具体姿态、连接及透视证据；
- 其他检查项也必须提供非空证据；
- 总体 `pass` 时，该项必须明确为 `pass`。无法核对整体姿态时，不能将其当作已通过；
- 明确不支持该项时，按关键项 `fail`，总分不超过 77，并进入定向修订。

## 已发布物种修订

新 Issue 和任务目录记录 `revisionOf.issue`、`revisionOf.attempt`、`revisionOf.sourceSha256`。`revisionOf.issue` 必须是本仓库带正整数编号的完整 Issue URL，不能使用 Issue 列表根路径、非数字编号或尾随斜杠。旧图和旧审核保留。只有新候选双审通过、候选哈希一致且公开原图哈希仍与血缘匹配时，才允许原子替换公开 WebP。替换后保留分类、名称、ID、分布、形态与保护状态元数据。

## 新任务默认与任务包生成

未声明版本的新任务默认使用 v2；历史 `done`、`blocked` 任务在未显式声明版本时仍按 v1 复核，不改写旧审核。显式版本声明只接受整数 1 或 2，其他值立即拒绝。新任务首次执行时把解析出的版本写入 `task.json`，不会在进入终态后退回 v1。

任务清单中的检查 ID 和审核结果中的检查 ID 都不得重复。独立调用 `sticker_export.py` 与正常流水线一样，在写出公开文件前必须完整校验任务包、生成记录、一审和盲审，不能用独立入口绕过 v2 证据要求。

先把批准的原始参考放入任务目录的 `references/`，再按 `docs/protocols/production-task-config.example.json` 准备配置，运行：

```bash
python3 scripts/prepare_production_task.py path/to/config.json
```

生成器只创建任务包，不启动生图、不创建 Issue。任务进入 worker 前还会再次检查：一个且仅一个 `primary-pose`、物种专属 `anatomyChecks`、关键 `view-consistency` 和 `unknowns`，以及全部参考的类型、视角、生活阶段、性别、作者、许可、来源、本地路径和 SHA-256。任一条件不满足都会在调用生成模型前停止。

## 通知与关闭故障

普通阶段通知失败只记录到本地 `pipeline-state.json` 的 `notifications`，不得把已完成的图像阶段误标为质量失败。导出后先进入 `close-issue`，再核对评论和关闭状态；关闭失败只重试收尾，不重新生成、审核或导出。最多执行三次关闭尝试，评论已存在时不得重复发布。

## 回归测试

```bash
python3 -m unittest discover -s tests -v
```

测试使用临时目录和进程替身，不调用生图，不修改真实 Issue，也不需要原始照片公开。
