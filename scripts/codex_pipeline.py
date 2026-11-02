#!/usr/bin/env python3
import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image
from sticker_export import export_approved

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = PROJECT_ROOT / "docs/protocols/chatgpt-desktop-worker.md"
PRIMARY_REVIEWER = "Codex CLI fresh primary session"
BLIND_REVIEWER = "Codex CLI fresh ephemeral session"


def now():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def save_task(task_dir, task):
    write_json(task_dir / "task.json", task)


def record(task_dir, task, stage, status, details=None):
    task["stage"] = stage
    task["status"] = status
    save_task(task_dir, task)
    state_path = task_dir / "pipeline-state.json"
    state = read_json(state_path) if state_path.exists() else {"species": task["species"]["scientificName"], "history": []}
    state["stage"] = stage
    state["status"] = status
    state["attempt"] = task["attempt"]
    state["updatedAt"] = now()
    state["history"].append({"at": now(), "stage": stage, "status": status, "attempt": task["attempt"], "details": details})
    write_json(state_path, state)


def issue_number(task):
    return task["githubIssue"].rstrip("/").rsplit("/", 1)[-1]


def issue_comment(task, body):
    completed = subprocess.run(["gh", "issue", "comment", issue_number(task), "--repo", "hunknownz/intoreal-insect-sticker", "--body", body], cwd=PROJECT_ROOT, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr)


def close_issue(task, body):
    completed = subprocess.run(["gh", "issue", "comment", issue_number(task), "--repo", "hunknownz/intoreal-insect-sticker", "--body", body], cwd=PROJECT_ROOT, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr)
    completed = subprocess.run(["gh", "issue", "close", issue_number(task), "--repo", "hunknownz/intoreal-insect-sticker"], cwd=PROJECT_ROOT, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr)


def load(task_dir):
    task_dir = Path(task_dir).resolve()
    task = read_json(task_dir / "task.json")
    attempt = task["attempt"]
    candidate = task_dir / f"attempt-{attempt:02d}-sticker.png"
    references = read_json(task_dir / "references.json")["references"]
    reference_paths = [task_dir / row["localPath"] for row in references]
    return task_dir, task, candidate, reference_paths


def review_path(task_dir, stage, attempt):
    if stage == "primary-review":
        return task_dir / ("primary-review.json" if attempt == 1 else f"primary-review-attempt-{attempt:02d}.json")
    return task_dir / f"attempt-{attempt:02d}-blind-review.json"


def event_output(stdout, stderr):
    def text(value):
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value

    result = text(stdout)
    error = text(stderr)
    if error:
        separator = "" if not result or result.endswith("\n") else "\n"
        result += separator + json.dumps({"type": "process.stderr", "message": error}, ensure_ascii=False) + "\n"
    return result


def transient_codex_failure(completed):
    output = f"{completed.stdout}\n{completed.stderr}".casefold()
    if any(marker in output for marker in ("request timed out", "tls handshake timeout", "status 408")):
        return False
    markers = (
        "workspace routing discovery failed",
        "error sending request",
        "selected model is at capacity",
        "unexpected eof",
        "status 429",
        "status 500",
        "status 502",
        "status 503",
        "status 504",
    )
    return any(marker in output for marker in markers)


def run_codex(task_dir, task, stage, prompt, images, output, sandbox):
    attempt = task["attempt"]
    events = task_dir / f"attempt-{attempt:02d}-{stage}-events.jsonl"
    paths = [events, output]
    for path in paths:
        if path.exists():
            raise ValueError(f"输出已存在，拒绝覆盖: {path}")
    command = ["codex", "exec", "--skip-git-repo-check", "--ephemeral", "-s", sandbox, "--json", "-o", str(output)]
    for image in images:
        command.extend(["-i", str(image)])
    command.extend(["--", prompt])
    for technical_attempt in range(3):
        try:
            completed = subprocess.run(command, cwd=task_dir, capture_output=True, text=True, timeout=900, check=False)
        except subprocess.TimeoutExpired as exc:
            failed_events = task_dir / f"attempt-{attempt:02d}-{stage}-timeout-{technical_attempt + 1:02d}-events.jsonl"
            if failed_events.exists():
                raise ValueError(f"超时日志已存在，拒绝覆盖: {failed_events}") from exc
            failed_events.write_text(event_output(exc.stdout, exc.stderr), encoding="utf-8")
            raise
        if completed.returncode == 0:
            events.write_text(completed.stdout, encoding="utf-8")
            if not output.is_file():
                raise RuntimeError(f"Codex CLI {stage} 未交付: {output}")
            return
        if technical_attempt == 2 or not transient_codex_failure(completed):
            events.write_text(event_output(completed.stdout, completed.stderr), encoding="utf-8")
            raise RuntimeError(f"Codex CLI {stage} 失败: {completed.stderr}")
        failed_events = task_dir / f"attempt-{attempt:02d}-{stage}-network-failure-{technical_attempt + 1:02d}-events.jsonl"
        if failed_events.exists():
            raise ValueError(f"技术失败日志已存在，拒绝覆盖: {failed_events}")
        failed_events.write_text(event_output(completed.stdout, completed.stderr), encoding="utf-8")
        if output.exists():
            raise RuntimeError(f"Codex CLI {stage} 技术失败但已写出结果，必须先复核，禁止自动重试: {output}")
        if stage == "generate":
            generated_paths = [
                task_dir / f"attempt-{attempt:02d}-generated.png",
                task_dir / f"attempt-{attempt:02d}-sticker.png",
                task_dir / f"attempt-{attempt:02d}-generation.json",
            ]
            if any(path.exists() for path in generated_paths):
                raise RuntimeError("Codex CLI generate 技术失败但已有生成文件，必须先做证据恢复，禁止自动重试")
        time.sleep(15 * (technical_attempt + 1))


def generate(task_dir, task, reference_paths):
    attempt = task["attempt"]
    generated = task_dir / f"attempt-{attempt:02d}-generated.png"
    sticker = task_dir / f"attempt-{attempt:02d}-sticker.png"
    generation = task_dir / f"attempt-{attempt:02d}-generation.json"
    final_message = task_dir / f"attempt-{attempt:02d}-generate-last-message.txt"
    for path in (generated, sticker, generation):
        if path.exists():
            raise ValueError(f"生成输出已存在，拒绝覆盖: {path}")
    redo = ""
    if attempt > 1:
        redo_path = task_dir / f"redo-task-attempt-{attempt:02d}.md"
        if not redo_path.is_file():
            raise ValueError(f"缺少重画任务书: {redo_path}")
        redo = f"本轮是 redo，必须读取并遵循 {redo_path}，保留上一轮文件，不得覆盖。"
    prompt = f"""执行 {task['githubIssue']} 的 attempt {attempt} generate。先读取并遵守 {PROTOCOL_PATH}、{task_dir / 'generate-task.md'}、{task_dir / 'task.json'} 和 {task_dir / 'references.json'}。{redo}

使用 Codex CLI 实际可用的 image_generation 工具生成新的位图插画，不得用 SVG、文字、截图拼贴或占位图冒充。以任务书和三张附加参考图为准。必须在当前任务目录交付：
attempt-{attempt:02d}-generated.png
attempt-{attempt:02d}-sticker.png
attempt-{attempt:02d}-generation.json

贴纸为 RGBA，长边约1000px，白边为长边1%–1.5%，画布边缘完全透明。原始生成图不得修改，后期只处理贴纸副本。生成记录采用与任务要求一致的结构，包含 outputs.generated 和 outputs.sticker 的文件名、尺寸和 SHA-256，以及参考来源、实际工具、模型或 null、后期方法、unverifiable 和 review.status=not-performed。实际查看交付图片并重新计算哈希。不要进行独立评分或审核。最终回复只简述实际交付文件。
"""
    run_codex(task_dir, task, "generate", prompt, reference_paths, final_message, "workspace-write")
    validate_generation(task_dir, task)


def validate_generation(task_dir, task):
    attempt = task["attempt"]
    record_path = task_dir / f"attempt-{attempt:02d}-generation.json"
    generation = read_json(record_path)
    if generation.get("review", {}).get("status") != "not-performed":
        raise ValueError("生成记录必须明确 review.status=not-performed")
    for kind in ("generated", "sticker"):
        expected = generation["outputs"][kind]
        filename = expected.get("file") or expected.get("filename")
        if not filename:
            raise ValueError(f"生成记录缺少文件名: {kind}")
        dimensions = expected.get("dimensions")
        if dimensions is None and "width" in expected and "height" in expected:
            dimensions = [expected["width"], expected["height"]]
        elif isinstance(dimensions, dict):
            dimensions = [dimensions["width"], dimensions["height"]]
        if not isinstance(dimensions, list) or len(dimensions) != 2:
            raise ValueError(f"生成记录缺少有效尺寸: {kind}")
        path = task_dir / filename
        if not path.is_file():
            raise ValueError(f"缺少生成图片: {path}")
        if sha256(path) != expected["sha256"]:
            raise ValueError(f"生成记录哈希不一致: {path}")
        with Image.open(path) as image:
            if list(image.size) != dimensions:
                raise ValueError(f"生成记录尺寸不一致: {path}")
            if image.mode != "RGBA":
                raise ValueError(f"图片不是 RGBA: {path}")
            if kind == "sticker":
                if max(image.size) != 1000:
                    raise ValueError("贴纸长边必须为1000px")
                alpha = image.getchannel("A")
                width, height = image.size
                values = list(alpha.getdata())
                edges = [*values[:width], *values[-width:], *values[::width], *values[width - 1::width]]
                if max(edges) != 0:
                    raise ValueError("贴纸画布边缘不完全透明")
    return True


def review_prompt(task_dir, task, stage, candidate):
    attempt = task["attempt"]
    expected = sha256(candidate)
    if stage == "primary-review":
        reviewer = PRIMARY_REVIEWER
        allowed = f"允许读取 {task_dir / f'attempt-{attempt:02d}-generation.json'}、检查清单和 schema。"
        review_type = "primary-independent"
    else:
        reviewer = BLIND_REVIEWER
        allowed = "禁止读取 generation.json、primary-review.json、任何一审分数或评论、redoNote、blocked 记录、旧聊天和其他任务目录。"
        review_type = "blind-independent"
    return f"""执行 {task['githubIssue']} 的 attempt {attempt} {stage}。你是独立新进程，reviewer 写 {reviewer!r}，reviewType 写 {review_type!r}。先读取 {PROTOCOL_PATH}、{task_dir / 'review-checklist.json'} 和 {task_dir / 'review-output.schema.json'}。{allowed}

实际查看命令附加的三张参考图和候选图 {candidate}，逐项核对检查清单。候选 SHA-256 为 {expected}，用只读命令复核。按协议从100分开始扣分，不预设目标分数；关键项失败必须 fail 且封顶77，pass 至少80且无关键项失败，非关键项失败按规则扣分但不自动阻塞 pass。

最终回复只输出符合 schema 的 JSON 对象，不用 Markdown。必须包含 reviewedFiles.candidate、reviewedFiles.references、candidateHashCheck、checks、issues、redoNote 和 unverifiable。不要修改图片或其他文件。
"""


def run_review(task_dir, task, stage, candidate, reference_paths):
    output = review_path(task_dir, stage, task["attempt"])
    prompt = review_prompt(task_dir, task, stage, candidate)
    run_codex(task_dir, task, stage, prompt, [*reference_paths, candidate], output, "read-only")
    review = validate_review(output, task_dir, task, stage, candidate)
    return review


def validate_review(path, task_dir, task, stage, candidate):
    review = read_json(path)
    errors = []
    expected_reviewer = PRIMARY_REVIEWER if stage == "primary-review" else BLIND_REVIEWER
    expected_type = "primary-independent" if stage == "primary-review" else "blind-independent"
    score = review.get("score")
    verdict = review.get("verdict")
    if review.get("species") != task["species"]["scientificName"]:
        errors.append("species 不一致")
    if review.get("attempt") != task["attempt"]:
        errors.append("attempt 不一致")
    if review.get("reviewer") != expected_reviewer:
        errors.append("reviewer 不一致")
    if review.get("reviewType") != expected_type:
        errors.append("reviewType 不一致")
    if verdict not in {"pass", "fail", "blocked"}:
        errors.append("verdict 非法")
    if verdict == "blocked":
        errors.append("审核 blocked")
        if score is not None:
            errors.append("blocked 分数必须为 null")
    elif not isinstance(score, (int, float)) or not 0 <= score <= 100:
        errors.append("分数必须为0–100")
    checks = review.get("checks")
    if not isinstance(checks, list) or not checks:
        errors.append("checks 必须非空")
        checks = []
    checklist = read_json(task_dir / "review-checklist.json")
    required = {row["id"]: row for row in checklist["checks"]}
    seen = set()
    critical_failures = []
    for check in checks:
        check_id = check.get("id")
        seen.add(check_id)
        if check.get("status") not in {"pass", "fail", "unverifiable"}:
            errors.append(f"{check_id}: 状态非法")
        if check_id in required and check.get("status") == "fail" and required[check_id].get("critical"):
            critical_failures.append(check_id)
    if set(required) - seen:
        errors.append(f"缺少检查项: {sorted(set(required) - seen)}")
    if critical_failures and (verdict != "fail" or not isinstance(score, (int, float)) or score > 77):
        errors.append("关键项失败分数规则不一致")
    if verdict == "pass" and (not isinstance(score, (int, float)) or score < 80 or critical_failures):
        errors.append("pass 分数规则不一致")
    hash_check = review.get("candidateHashCheck")
    expected = sha256(candidate)
    if not isinstance(hash_check, dict):
        errors.append("缺少 candidateHashCheck")
    else:
        if hash_check.get("actual") != expected or hash_check.get("matched") is not True:
            errors.append("候选哈希未正确核验")
    reviewed = review.get("reviewedFiles", {})
    reviewed_candidate = reviewed.get("candidate") if isinstance(reviewed, dict) else None
    if not reviewed_candidate:
        errors.append("缺少 reviewedFiles.candidate")
    else:
        reviewed_path = Path(reviewed_candidate)
        if not reviewed_path.is_absolute():
            reviewed_path = task_dir / reviewed_path
        if reviewed_path.resolve() != candidate.resolve():
            errors.append("审核候选路径不一致")
    if task.get("reviewProtocolVersion") == 2:
        if required.get("view-consistency", {}).get("critical") is not True:
            errors.append("v2 缺少关键 view-consistency 检查")
        for check in checks:
            if not isinstance(check.get("evidence"), str) or not check["evidence"].strip():
                errors.append(f"{check.get('id')}: v2 证据不能为空")
        if verdict == "pass" and any(check.get("id") == "view-consistency" and check.get("status") != "pass" for check in checks):
            errors.append("v2 视角一致性必须明确 pass 才能发布")
        reviewed_references = reviewed.get("references") if isinstance(reviewed, dict) else None
        if not isinstance(reviewed_references, list) or not all(isinstance(item, str) for item in reviewed_references):
            errors.append("v2 reviewedFiles.references 必须是路径列表")
            reviewed_references = []
        actual_references = set()
        for item in reviewed_references:
            reference_path = Path(item)
            if not reference_path.is_absolute():
                reference_path = task_dir / reference_path
            actual_references.add(reference_path.resolve())
        declared_references = {(task_dir / row["localPath"]).resolve() for row in read_json(task_dir / "references.json")["references"]}
        if actual_references != declared_references or len(reviewed_references) != len(declared_references):
            errors.append("v2 必须逐项核对全部指定参考")
    if errors:
        raise ValueError("; ".join(errors))
    return review


def prepare_redo(task_dir, task, stage, review):
    attempt = task["attempt"]
    if attempt > task.get("retryLimit", 2):
        raise RuntimeError("已达到最大重画次数")
    note = task_dir / f"attempt-{attempt:02d}-{stage}-redo-note.txt"
    if note.exists():
        raise ValueError(f"redoNote 已存在，拒绝覆盖: {note}")
    note.write_text(review.get("redoNote") or json.dumps(review.get("issues", []), ensure_ascii=False), encoding="utf-8")
    next_attempt = attempt + 1
    redo_task = task_dir / f"redo-task-attempt-{next_attempt:02d}.md"
    if redo_task.exists():
        raise ValueError(f"重画任务书已存在，拒绝覆盖: {redo_task}")
    previous = task_dir / f"attempt-{attempt:02d}-sticker.png"
    redo_task.write_text(f"# Attempt {next_attempt} 重画任务\n\n读取上一轮候选 {previous} 和明确提供的 {note}。只根据其中指出的生成或形态问题重画，保留全部历史文件，输出新的 attempt {next_attempt:02d} 文件。不得读取另一审核阶段的结果。\n", encoding="utf-8")
    task["attempt"] = next_attempt
    task["generationOutput"] = f"attempt-{next_attempt:02d}-generation.json"
    record(task_dir, task, "generate", "ready-for-redo", f"from attempt {attempt} {stage}")
    issue_comment(task, f"Stage: {stage} → redo. attempt {attempt} 未通过，已生成定向 redoNote，自动进入 attempt {next_attempt}。")


def validate_done(task_dir, task):
    attempt = task["attempt"]
    candidate = task_dir / f"attempt-{attempt:02d}-sticker.png"
    validate_generation(task_dir, task)
    validate_review(review_path(task_dir, "primary-review", attempt), task_dir, task, "primary-review", candidate)
    validate_review(review_path(task_dir, "blind-review", attempt), task_dir, task, "blind-review", candidate)
    return True


def run(task_dir):
    task_dir, task, candidate, reference_paths = load(task_dir)
    if task["stage"] == "done":
        validate_done(task_dir, task)
        return {"ok": True, "stage": "done", "attempt": task["attempt"]}
    try:
        while True:
            task_dir, task, candidate, reference_paths = load(task_dir)
            stage = task["stage"]
            if stage == "generate":
                record(task_dir, task, "generate", "running")
                issue_comment(task, f"Stage: generate. Codex CLI 自动启动 attempt {task['attempt']}。")
                generate(task_dir, task, reference_paths)
                record(task_dir, task, "primary-review", "ready", "technical checks passed")
            elif stage == "primary-review":
                record(task_dir, task, "primary-review", "running")
                review = run_review(task_dir, task, stage, candidate, reference_paths)
                if review["verdict"] == "pass":
                    record(task_dir, task, "blind-review", "ready", "primary passed")
                    issue_comment(task, f"Stage: primary-review → blind-review. attempt {task['attempt']} 一审 {review['score']} / pass；共享入口不记录该结论供盲审读取。")
                else:
                    prepare_redo(task_dir, task, stage, review)
            elif stage == "blind-review":
                record(task_dir, task, "blind-review", "running")
                review = run_review(task_dir, task, stage, candidate, reference_paths)
                if review["verdict"] == "pass":
                    validate_done(task_dir, task)
                    exported = export_approved(task_dir)
                    record(task_dir, task, "done", "done", f"blind {review['score']}/pass; exported {exported['sticker']['file']}")
                    close_issue(task, f"Stage: blind-review → done. attempt {task['attempt']} 盲审 {review['score']} / pass。候选哈希、图片技术检查、一审和盲审均已由本地程序复验，公开交付为 `{exported['sticker']['file']}`，Issue 自动关闭。")
                    return {"ok": True, "stage": "done", "attempt": task["attempt"], "score": review["score"]}
                prepare_redo(task_dir, task, stage, review)
            else:
                raise ValueError(f"不支持的阶段: {stage}")
    except Exception as exc:
        task_dir, task, _, _ = load(task_dir)
        blocked = task_dir / f"attempt-{task['attempt']:02d}-{task['stage']}-blocked.json"
        if not blocked.exists():
            write_json(blocked, {"verdict": "blocked", "stage": task["stage"], "attempt": task["attempt"], "score": None, "reason": str(exc), "at": now()})
        record(task_dir, task, "blocked", "blocked", str(exc))
        issue_comment(task, f"Stage: {task['stage']} → blocked. {exc}")
        return {"ok": False, "stage": "blocked", "error": str(exc)}


def main():
    parser = argparse.ArgumentParser(description="Run one formal insect issue through isolated Codex CLI stages.")
    parser.add_argument("task_dir", nargs="?")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if not args.task_dir:
        parser.print_help()
        return 0
    try:
        if args.validate_only:
            task_dir, task, _, _ = load(args.task_dir)
            validate_done(task_dir, task)
            result = {"ok": True, "stage": task["stage"], "attempt": task["attempt"]}
        else:
            result = run(args.task_dir)
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
