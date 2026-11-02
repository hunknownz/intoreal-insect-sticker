#!/usr/bin/env python3
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = PROJECT_ROOT / "docs/protocols/chatgpt-desktop-worker.md"
REVIEWER = "Codex CLI fresh ephemeral session"


def load_task(task_dir):
    task_dir = Path(task_dir).resolve()
    task = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
    attempt = task["attempt"]
    candidate = task_dir / f"attempt-{attempt:02d}-sticker.png"
    references = json.loads((task_dir / "references.json").read_text(encoding="utf-8"))["references"]
    reference_paths = [task_dir / row["localPath"] for row in references]
    for path in [candidate, *reference_paths, task_dir / "blind-review-task.md", task_dir / "review-checklist.json", task_dir / "review-output.schema.json"]:
        if not path.is_file():
            raise ValueError(f"缺少输入文件: {path}")
    return task_dir, task, candidate, reference_paths


def output_paths(task_dir, attempt):
    return {
        "review": task_dir / f"attempt-{attempt:02d}-blind-review.json",
        "events": task_dir / f"attempt-{attempt:02d}-codex-blind-events.jsonl",
        "blocked": task_dir / f"attempt-{attempt:02d}-codex-blind-blocked.json",
    }


def build_prompt(task_dir, task, candidate, expected_sha256):
    return f"""执行 Issue #5 的 attempt {task['attempt']} 独立盲审。你是全新 Codex CLI ephemeral 会话，reviewer 必须写 {REVIEWER!r}，reviewType 必须写 'blind-independent'。

先读取并遵守 {PROTOCOL_PATH} 和 {task_dir / 'blind-review-task.md'}。只允许再读取 {task_dir / 'review-checklist.json'} 与 {task_dir / 'review-output.schema.json'}，以及本命令附加的候选图和三张参考图。不得读取 AGENTS.md 中的历史结果、attempt-01-generation.json、primary-review.json、任何 blocked 记录、旧测试目录或其他聊天内容。

实际查看所有附加图片，逐项核对检查清单。候选是 {candidate}，Kimi 本地计算的 SHA-256 是 {expected_sha256}。可以使用只读命令重新计算候选哈希；如果无法计算，matched 写 null、status 写 delegated-to-kimi。

最终回复只输出一个符合 review-output.schema.json 的 JSON 对象，不要使用 Markdown 代码块，不要附加解释。blocked 时 score 必须为 null。不要修改任何图片或其他文件。
"""


def validate_review(review_path, task_dir, task, candidate, expected_sha256):
    errors = []
    try:
        review = json.loads(Path(review_path).read_text(encoding="utf-8"))
        if not isinstance(review, dict):
            raise ValueError("顶层必须是对象")
    except Exception as exc:
        return {"ok": False, "errors": [f"无法解析审核 JSON: {exc}"]}

    score = review.get("score")
    verdict = review.get("verdict")
    if review.get("species") != task["species"]["scientificName"]:
        errors.append("species 与任务不一致")
    if review.get("attempt") != task["attempt"]:
        errors.append("attempt 与任务不一致")
    if review.get("reviewer") != REVIEWER:
        errors.append("reviewer 不是指定的独立 Codex CLI 会话")
    if review.get("reviewType") != "blind-independent":
        errors.append("reviewType 必须为 blind-independent")
    if verdict not in {"pass", "fail", "blocked"}:
        errors.append("verdict 非法")
    if verdict == "blocked":
        errors.append("blocked 不能作为成功审核")
        if score is not None:
            errors.append("blocked 时 score 必须为 null")
    elif not isinstance(score, (int, float)) or not 0 <= score <= 100:
        errors.append("pass/fail 时 score 必须是 0–100 的数字")

    checklist = json.loads((task_dir / "review-checklist.json").read_text(encoding="utf-8"))
    required = {row["id"]: row for row in checklist["checks"]}
    checks = review.get("checks")
    if not isinstance(checks, list) or not checks:
        errors.append("checks 必须是非空数组")
        checks = []
    seen = set()
    critical_failures = []
    for check in checks:
        if not isinstance(check, dict):
            errors.append("checks 中每项必须是对象")
            continue
        check_id = check.get("id")
        seen.add(check_id)
        if check.get("status") not in {"pass", "fail", "unverifiable"}:
            errors.append(f"{check_id}: 审核状态非法")
        if check_id in required and check.get("status") == "fail" and required[check_id].get("critical"):
            critical_failures.append(check_id)
    missing = set(required) - seen
    if missing:
        errors.append(f"缺少检查项: {sorted(missing)}")
    if critical_failures and (verdict != "fail" or not isinstance(score, (int, float)) or score > 77):
        errors.append("关键特征失败时必须 fail 且分数封顶 77")
    if verdict == "pass" and (not isinstance(score, (int, float)) or score < 80 or critical_failures):
        errors.append("pass 要求至少 80 分且无关键特征失败")

    hash_check = review.get("candidateHashCheck")
    if not isinstance(hash_check, dict):
        errors.append("缺少 candidateHashCheck")
    else:
        actual = hash_check.get("actual")
        matched = hash_check.get("matched")
        status = hash_check.get("status")
        if actual is not None and actual != expected_sha256:
            errors.append("审核记录中的候选哈希与本地预期不一致")
        if matched is False:
            errors.append("审核记录将候选哈希标为不匹配")
        if matched is None and status != "delegated-to-kimi":
            errors.append("哈希未核对时必须明确 delegated-to-kimi")

    reviewed = review.get("reviewedFiles", {})
    reviewed_candidate = reviewed.get("candidate") if isinstance(reviewed, dict) else None
    if not isinstance(reviewed_candidate, str) or not reviewed_candidate:
        errors.append("reviewedFiles.candidate 缺失")
    else:
        reviewed_path = Path(reviewed_candidate)
        if not reviewed_path.is_absolute():
            reviewed_path = task_dir / reviewed_path
        if reviewed_path.resolve() != candidate.resolve():
            errors.append("审核对象路径与任务候选不一致")
    if hashlib.sha256(candidate.read_bytes()).hexdigest() != expected_sha256:
        errors.append("候选文件当前哈希与审核前不一致")
    return {"ok": not errors, "errors": errors, "review": review if not errors else None}


def write_blocked(path, reason, details=""):
    path.write_text(json.dumps({
        "verdict": "blocked",
        "stage": "blind-review",
        "reviewer": REVIEWER,
        "score": None,
        "reason": reason,
        "details": details,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("task_dir")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    try:
        task_dir, task, candidate, reference_paths = load_task(args.task_dir)
        paths = output_paths(task_dir, task["attempt"])
        expected_sha256 = hashlib.sha256(candidate.read_bytes()).hexdigest()
        if args.validate_only:
            result = validate_review(paths["review"], task_dir, task, candidate, expected_sha256)
        else:
            for path in paths.values():
                if path.exists():
                    raise ValueError(f"输出已存在，拒绝覆盖: {path}")
            command = [
                "codex", "exec", "--skip-git-repo-check", "--ephemeral",
                "-s", "read-only", "--json",
                "-o", str(paths["review"]),
            ]
            for image in [*reference_paths, candidate]:
                command.extend(["-i", str(image)])
            command.extend(["--", build_prompt(task_dir, task, candidate, expected_sha256)])
            completed = subprocess.run(command, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=900, check=False)
            paths["events"].write_text(completed.stdout, encoding="utf-8")
            if completed.returncode != 0:
                write_blocked(paths["blocked"], "Codex CLI 调用失败", completed.stderr)
                result = {"ok": False, "errors": [completed.stderr], "blocked": str(paths["blocked"])}
            else:
                result = validate_review(paths["review"], task_dir, task, candidate, expected_sha256)
                if not result["ok"]:
                    write_blocked(paths["blocked"], "审核结果校验失败", "; ".join(result["errors"]))
                    result["blocked"] = str(paths["blocked"])
    except Exception as exc:
        result = {"ok": False, "errors": [str(exc)]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
