import hashlib
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def protocol_version(task):
    if "reviewProtocolVersion" in task:
        version = task["reviewProtocolVersion"]
        if type(version) is not int or version not in {1, 2}:
            raise ValueError("reviewProtocolVersion 必须为整数 1 或 2")
        return version
    return 1 if task.get("stage") in {"done", "blocked"} else 2


def validate_references(task_dir, references):
    if not isinstance(references, list) or not references:
        raise ValueError("v2 至少需要一个批准的参考")
    primary = [row for row in references if row.get("poseRole") == "primary-pose"]
    if len(primary) != 1:
        raise ValueError("v2 必须恰好指定一个 primary-pose 参考")
    reference_root = (task_dir / "references").resolve()
    for row in references:
        for field in ("type", "view", "lifeStage", "sex", "page", "author", "license", "localPath", "sha256"):
            if not row.get(field):
                raise ValueError(f"参考缺少字段: {field}")
        relative = Path(row["localPath"])
        if relative.is_absolute() or len(relative.parts) != 2 or relative.parts[0] != "references":
            raise ValueError(f"参考必须直接位于 references/ 内: {relative}")
        path = (task_dir / relative).resolve()
        if path.parent != reference_root or not path.is_file():
            raise ValueError(f"参考文件不存在: {path}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError(f"参考 SHA-256 不一致: {path}")
    return True


def validate_task_package(task_dir, task=None):
    task_dir = Path(task_dir).resolve()
    task = task or json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
    if protocol_version(task) != 2:
        return True
    checklist = json.loads((task_dir / "review-checklist.json").read_text(encoding="utf-8"))
    check_ids = [row.get("id") for row in checklist["checks"]]
    if len(check_ids) != len(set(check_ids)):
        raise ValueError("v2 checklist 检查 ID 不得重复")
    required = {row["id"]: row for row in checklist["checks"]}
    if required.get("view-consistency", {}).get("critical") is not True:
        raise ValueError("v2 缺少关键 view-consistency 检查")
    if required.get("unknowns", {}).get("critical") is not True:
        raise ValueError("v2 缺少关键 unknowns 检查")
    generic = {"view-consistency", "requested-view", "presentation", "unknowns"}
    if not set(required) - generic:
        raise ValueError("v2 至少需要一项物种专属 anatomyChecks")
    references = json.loads((task_dir / "references.json").read_text(encoding="utf-8"))["references"]
    return validate_references(task_dir, references)


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def create_task_package(config, project_root=PROJECT_ROOT):
    project_root = Path(project_root).resolve()
    task_dir = (project_root / config["workspace"]).resolve()
    if task_dir.parent != (project_root / "production").resolve():
        raise ValueError("workspace 必须是 production/ 的直接子目录")
    filenames = [
        "task.json", "references.json", "review-checklist.json", "review-output.schema.json",
        "generate-task.md", "blind-review-task.md",
    ]
    for filename in filenames:
        if (task_dir / filename).exists():
            raise ValueError(f"任务包文件已存在，拒绝覆盖: {task_dir / filename}")
    species = config["species"]
    for field in ("scientificName", "commonNameEn", "commonNameZhHans", "order", "family", "lifeStage", "sex", "view"):
        if not species.get(field):
            raise ValueError(f"species 缺少字段: {field}")
    anatomy = config.get("anatomyChecks")
    if not isinstance(anatomy, list) or not anatomy:
        raise ValueError("anatomyChecks 必须包含物种专属结构检查")
    reserved = {"view-consistency", "requested-view", "presentation", "unknowns"}
    for check in anatomy:
        if not check.get("id") or check["id"] in reserved or not check.get("requirement"):
            raise ValueError("anatomyChecks 的 id 和 requirement 必须有效")
        check.setdefault("critical", True)
    check_ids = [check["id"] for check in anatomy]
    if len(check_ids) != len(set(check_ids)):
        raise ValueError("anatomyChecks 的 id 必须唯一")
    unverifiable = config.get("unverifiable")
    if not isinstance(unverifiable, list) or not unverifiable or not all(isinstance(item, str) and item.strip() for item in unverifiable):
        raise ValueError("unverifiable 必须列出无法核实的必要事项")
    instructions = config.get("generationInstructions")
    if not isinstance(instructions, str) or not instructions.strip():
        raise ValueError("generationInstructions 必须说明目标形态和主姿态")
    references = [dict(row) for row in config["references"]]
    for row in references:
        row.setdefault("poseRole", "local-detail-only")
    validate_references(task_dir, references)
    task_dir.mkdir(parents=True, exist_ok=True)
    issue = config["githubIssue"]
    task = {
        "taskType": "codex-cli-formal-production",
        "githubIssue": issue,
        "species": species,
        "reviewProtocolVersion": 2,
        "stage": "generate",
        "attempt": 1,
        "retryLimit": 2,
        "generationOutput": "attempt-01-generation.json",
        "status": "ready",
    }
    checklist = {
        "species": species["scientificName"],
        "reviewProtocolVersion": 2,
        "passScore": 80,
        "criticalFailureScoreCap": 77,
        "checks": [
            *anatomy,
            {"id": "view-consistency", "critical": True, "requirement": "All visible body parts and joints must form one physically coherent pose and perspective supported by the approved references; no incompatible view compositing, fused appendages or unsupported attachment points."},
            {"id": "requested-view", "critical": True, "requirement": f"Complete individual in the requested {species['view']} view, with all required appendages and diagnostic features inside the canvas."},
            {"id": "presentation", "critical": False, "requirement": "Natural-history illustration with restrained texture, no environment, text, watermark, opaque background or isolated speckles."},
            {"id": "unknowns", "critical": True, "requirement": "Report unverifiable details rather than inferring them: " + "; ".join(unverifiable)},
        ],
    }
    schema = {
        "species": species["scientificName"],
        "attempt": 1,
        "reviewer": "",
        "reviewType": "primary-independent | blind-independent",
        "score": 0,
        "verdict": "pass | fail | blocked",
        "checks": [{"id": "", "status": "pass | fail | unverifiable", "evidence": ""}],
        "issues": [],
        "redoNote": "",
        "unverifiable": [],
        "reviewedFiles": {
            "candidate": "attempt-01-sticker.png",
            "references": [row["localPath"] for row in references],
        },
        "candidateHashCheck": {"algorithm": "SHA-256", "expected": "", "actual": "", "matched": None},
    }
    write_json(task_dir / "task.json", task)
    write_json(task_dir / "references.json", {
        "species": species["scientificName"],
        "referencePolicy": "Original photographs are local-only working assets and must not be published to the repository.",
        "references": references,
    })
    write_json(task_dir / "review-checklist.json", checklist)
    write_json(task_dir / "review-output.schema.json", schema)
    (task_dir / "generate-task.md").write_text(
        f"# {species['scientificName']} 正式生产：生成任务\n\n"
        f"- **Issue:** {issue}\n- **工作目录:** `{config['workspace']}`\n- **协议:** `reviewProtocolVersion = 2`\n\n"
        "遵守 `docs/protocols/chatgpt-desktop-worker.md` 和 `docs/protocols/view-consistency-review.md`。"
        "以唯一的 primary-pose 全身参考确定姿态；局部参考只能补充对应部位细节，不得拼接不同视角。\n\n"
        f"{instructions.strip()}\n\n"
        "必须交付 `attempt-01-generated.png`、`attempt-01-sticker.png`、`attempt-01-generation.json`。"
        "贴纸为 RGBA，长边 1000px，白边约为长边 1%–1.5%，画布边缘完全透明。"
        "生成记录包含实际工具、模型或 null、参考来源与许可、输出尺寸和 SHA-256、后期方法、无法核对事项及 `review.status = \"not-performed\"`。不要在本进程进行独立评分。\n",
        encoding="utf-8",
    )
    (task_dir / "blind-review-task.md").write_text(
        f"# {species['scientificName']} 独立盲审\n\n"
        f"- **Issue:** {issue}\n- **协议:** `reviewProtocolVersion = 2`\n\n"
        "在未参与生图、未接触一审信息的 Codex CLI 全新 ephemeral 进程中执行。"
        "只允许使用指定参考、当前候选、检查清单、输出 schema 和候选哈希。"
        "禁止读取生成记录、任何一审结论或分数、redoNote、blocked 记录、旧聊天和其他任务目录。\n\n"
        "必须实际核对全部指定参考，并为每项提供证据。总体 pass 时 view-consistency 必须明确为 pass。"
        "关键项失败则 fail 且封顶 77；至少 80 且无关键项失败才可通过。\n",
        encoding="utf-8",
    )
    validate_task_package(task_dir, task)
    return task_dir
