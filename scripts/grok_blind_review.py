#!/usr/bin/env python3
import hashlib
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = PROJECT_ROOT / "docs/protocols/chatgpt-desktop-worker.md"
MODEL = "cursor/grok-4.7@256k"
THINKING = "high"


def build_command(task_path):
    task = json.loads(Path(task_path).read_text())
    return task, [
        "pi",
        "--no-session",
        "--no-context-files",
        "--no-mcp",
        "--no-extensions",
        "--no-skills",
        "--tools", "read,write",
        "--model", MODEL,
        "--thinking", THINKING,
        "--append-system-prompt", str(PROTOCOL_PATH),
        "--mode", "json",
        f"执行 {Path(task_path).name}",
    ]


def validate_review(review_path, expected_sha256, task=None, task_dir=None):
    errors = []
    try:
        review = json.loads(Path(review_path).read_text())
        if not isinstance(review, dict):
            raise ValueError("审核 JSON 顶层必须是对象")
    except Exception as exc:
        return {"ok": False, "errors": [f"无法解析审核 JSON: {exc}"]}

    score = review.get("score")
    verdict = review.get("verdict")
    if not isinstance(verdict, str):
        errors.append("verdict 必须是字符串")
    elif verdict not in {"pass", "fail", "blocked"}:
        errors.append("verdict 必须是 pass、fail 或 blocked")
    if verdict == "blocked":
        if score is not None:
            errors.append("blocked 时 score 必须为 null")
        errors.append("blocked 不能作为成功审核")
    elif not isinstance(score, (int, float)) or not 0 <= score <= 100:
        errors.append("pass/fail 时 score 必须是 0–100 的数字")
    if review.get("reviewType") != "blind-independent":
        errors.append("reviewType 必须为 blind-independent")
    if not isinstance(review.get("checks"), list) or not review["checks"]:
        errors.append("checks 必须是非空数组")

    critical_failures = []
    if task:
        if review.get("species") != task["species"]:
            errors.append("species 与任务不一致")
        if review.get("attempt") != task["attempt"]:
            errors.append("attempt 与任务不一致")
        if review.get("reviewer") != "Pi + Magpie Grok":
            errors.append("reviewer 必须为 Pi + Magpie Grok")
        try:
            checklist = json.loads(Path(task["checklistPath"]).read_text())
            required = {item["id"]: item for item in checklist["checks"]}
            seen = set()
            for check in review["checks"]:
                if not isinstance(check, dict):
                    errors.append("checks 中每项都必须是对象")
                    continue
                check_id = check.get("id")
                seen.add(check_id)
                if check.get("status") not in {"pass", "fail", "unverifiable"}:
                    errors.append(f"{check_id}: 非法审核状态")
                if check_id in required and check.get("status") == "fail" and required[check_id].get("critical"):
                    critical_failures.append(check_id)
            missing = set(required) - seen
            if missing:
                errors.append(f"缺少检查项: {sorted(missing)}")
        except Exception as exc:
            errors.append(f"无法使用检查清单: {exc}")

    if critical_failures and (verdict != "fail" or not isinstance(score, (int, float)) or score > 77):
        errors.append("关键特征失败时 verdict 必须为 fail 且 score 不得高于 77")
    if verdict == "pass" and (not isinstance(score, (int, float)) or score < 80 or critical_failures):
        errors.append("pass 要求 score 不低于 80 且没有关键特征失败")

    actual = None
    matched = None
    status = None
    check = None
    if "candidateHashCheck" in review:
        check = review["candidateHashCheck"]
    elif "candidateHashVerification" in review:
        check = review["candidateHashVerification"]
    elif "inputIntegrity" in review:
        check = review["inputIntegrity"]
    else:
        errors.append("缺少候选哈希核对字段")

    if check is not None:
        if not isinstance(check, dict):
            errors.append("候选哈希核对字段必须是对象")
        else:
            actual = check.get("actual", check.get("candidateSha256"))
            matched = check.get("matched", check.get("matches", check.get("candidateHashMatches")))
            status = check.get("status")

    if actual is not None and actual != expected_sha256:
        errors.append("候选 SHA-256 与预期不一致")
    if matched is False:
        errors.append("模型将候选哈希核对标记为失败")
    if matched is None and status != "delegated-to-kimi":
        errors.append("候选哈希核对必须成功或明确委托 delegated-to-kimi")

    candidate_path = review.get("reviewedFiles", {}).get("candidate") if isinstance(review.get("reviewedFiles"), dict) else None
    if not isinstance(candidate_path, str) or not candidate_path:
        errors.append("reviewedFiles.candidate 缺失或不是路径字符串")
    else:
        candidate = Path(candidate_path)
        if not candidate.is_absolute():
            candidate = (Path(task_dir) if task_dir else PROJECT_ROOT) / candidate
        if task and Path(candidate).resolve() != Path(task["candidatePath"]).resolve():
            errors.append("审核候选与任务授权候选不一致")
        try:
            local_sha256 = hashlib.sha256(candidate.read_bytes()).hexdigest()
            if local_sha256 != expected_sha256:
                errors.append("Kimi 本地计算的候选 SHA-256 与预期不一致")
        except Exception as exc:
            errors.append(f"Kimi 无法计算候选 SHA-256: {exc}")
    return {"ok": not errors, "errors": errors, "review": review if not errors else None}


def validate_events(events_path, task, task_path):
    errors = []
    task_dir = Path(task_path).parent
    review_output = (task_dir / task["reviewOutput"]).resolve()
    allowed_reads = {str(Path(path).resolve()) for path in task["allowedRead"]}
    allowed_reads.update({str(Path(task_path).resolve()), str(PROTOCOL_PATH.resolve()), str(review_output)})
    candidate = str(Path(task["candidatePath"]).resolve())
    reference_images = {
        str(Path(path).resolve()) for path in task["allowedRead"]
        if path.lower().endswith((".jpg", ".jpeg", ".png", ".webp")) and str(Path(path).resolve()) != candidate
    }
    image_reads = set()
    write_paths = []
    read_calls = {}
    model_verified = False
    try:
        for line in Path(events_path).read_text().splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            message = event.get("message", {})
            if isinstance(message, dict):
                provider = message.get("provider")
                model = message.get("model") or message.get("responseModel")
                thinking = message.get("thinkingLevel")
                if provider is not None and provider != "magpie":
                    errors.append(f"检测到非 Magpie 提供方: {provider}")
                if model is not None and model != MODEL:
                    errors.append(f"检测到非指定模型: {model}")
                if thinking is not None and thinking != THINKING:
                    errors.append(f"检测到非指定 thinking: {thinking}")
                if provider == "magpie" and model == MODEL and thinking == THINKING:
                    model_verified = True
                for item in message.get("content", []):
                    if not isinstance(item, dict) or item.get("type") != "toolCall":
                        continue
                    name = item.get("name")
                    path = item.get("arguments", {}).get("path")
                    if not path:
                        continue
                    resolved = str((task_dir / path).resolve()) if not Path(path).is_absolute() else str(Path(path).resolve())
                    if name == "read":
                        read_calls[item.get("id")] = resolved
                        if resolved not in allowed_reads:
                            errors.append(f"读取了未授权文件: {resolved}")
                    if name == "write":
                        write_paths.append(resolved)
                        if resolved != str(review_output):
                            errors.append(f"写入了未授权文件: {resolved}")
            if event.get("type") == "tool_execution_end" and event.get("toolName") == "read":
                path = event.get("args", {}).get("path") or read_calls.get(event.get("toolCallId"))
                if not path:
                    continue
                resolved = str((task_dir / path).resolve()) if not Path(path).is_absolute() else str(Path(path).resolve())
                result = event.get("result", {})
                contents = result.get("content", []) if isinstance(result, dict) else []
                if any(isinstance(item, dict) and item.get("type") == "image" for item in contents):
                    image_reads.add(resolved)
    except Exception as exc:
        errors.append(f"无法解析 Pi 事件日志: {exc}")

    if not model_verified:
        errors.append("未找到匹配的 Magpie/Grok 模型和 thinking 记录")
    if candidate not in image_reads:
        errors.append("事件日志没有候选图片的实际图像读取记录")
    missing_references = reference_images - image_reads
    if missing_references:
        errors.append(f"缺少指定参考图片的实际图像读取记录: {sorted(missing_references)}")
    if not write_paths:
        errors.append("事件日志没有审核结果写入记录")
    return errors


def write_blocked(task_path, reason, details=""):
    task = json.loads(Path(task_path).read_text())
    blocked_path = Path(task_path).parent / task.get("blockedOutput", "blocked.json")
    blocked_path.write_text(json.dumps({
        "verdict": "blocked",
        "stage": "blind-review",
        "reason": reason,
        "details": details,
        "task": str(task_path),
    }, ensure_ascii=False, indent=2) + "\n")
    return blocked_path


def run_review(task_path):
    task, command = build_command(task_path)
    task_path = Path(task_path)
    review_path = task_path.parent / task["reviewOutput"]
    events_path = task_path.parent / task["eventsOutput"]
    blocked_path = task_path.parent / task.get("blockedOutput", "blocked.json")
    for path in (review_path, events_path, blocked_path):
        if path.exists():
            return {"ok": False, "errors": [f"输出已存在，拒绝覆盖: {path}"]}

    try:
        result = subprocess.run(
            command,
            cwd=task_path.parent,
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )
    except Exception as exc:
        blocked = write_blocked(task_path, "Pi 调用异常", str(exc))
        return {"ok": False, "errors": [str(exc)], "blocked": str(blocked)}

    events_path.write_text(result.stdout)
    if result.returncode != 0:
        blocked = write_blocked(task_path, "Pi 或 Grok 调用失败", result.stderr)
        return {"ok": False, "errors": [result.stderr], "blocked": str(blocked)}

    event_errors = validate_events(events_path, task, task_path)
    if event_errors:
        blocked = write_blocked(task_path, "事件校验失败", "; ".join(event_errors))
        return {"ok": False, "errors": event_errors, "blocked": str(blocked)}

    validation = validate_review(review_path, task["expectedCandidateSha256"], task, task_path.parent)
    if not validation["ok"]:
        blocked = write_blocked(task_path, "审核结果校验失败", "; ".join(validation["errors"]))
        return {"ok": False, "errors": validation["errors"], "blocked": str(blocked)}
    return {"ok": True, "review": str(review_path), "events": str(events_path), "validation": validation}


def main():
    if len(sys.argv) < 3:
        print("用法: run <task.json> | validate <review.json> <expected-sha256> [task.json]", file=sys.stderr)
        return 2
    if sys.argv[1] == "validate":
        task = json.loads(Path(sys.argv[4]).read_text()) if len(sys.argv) > 4 else None
        result = validate_review(sys.argv[2], sys.argv[3], task, Path(sys.argv[4]).parent if task else None)
    elif sys.argv[1] == "run":
        result = run_review(sys.argv[2])
    else:
        print(f"未知子命令: {sys.argv[1]}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
