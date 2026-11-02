#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_ROOT = PROJECT_ROOT / "production"
PIPELINE_PATH = PROJECT_ROOT / "scripts/codex_pipeline.py"
STATE_PATH = PRODUCTION_ROOT / "worker-state.json"
LOCK_PATH = PRODUCTION_ROOT / ".codex-issue-worker.lock"
REPOSITORY = "hunknownz/intoreal-insect-sticker"


def now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def acquire_lock():
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    if LOCK_PATH.exists():
        try:
            pid = int(LOCK_PATH.read_text().strip())
            os.kill(pid, 0)
            raise RuntimeError(f"另一个 worker 正在运行: pid={pid}")
        except ProcessLookupError:
            LOCK_PATH.unlink()
        except ValueError:
            LOCK_PATH.unlink()
    descriptor = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(descriptor, "w") as handle:
        handle.write(str(os.getpid()))


def release_lock():
    if LOCK_PATH.exists() and LOCK_PATH.read_text().strip() == str(os.getpid()):
        LOCK_PATH.unlink()


def workspace_from_body(body):
    match = re.search(r"\*\*Workspace:\*\*\s*`([^`]+)`", body or "")
    if not match:
        return None
    candidate = (PROJECT_ROOT / match.group(1)).resolve()
    if candidate.parent != PRODUCTION_ROOT.resolve():
        return None
    if not (candidate / "task.json").is_file():
        return None
    return candidate


def eligible(issue):
    if not issue.get("title", "").startswith("[Production]"):
        return None
    task_dir = workspace_from_body(issue.get("body", ""))
    if task_dir is None:
        return None
    task = read_json(task_dir / "task.json")
    expected_issue = str(issue["number"])
    if task.get("githubIssue", "").rstrip("/").rsplit("/", 1)[-1] != expected_issue:
        return None
    if task.get("stage") in {"done", "blocked"}:
        return None
    return {"number": issue["number"], "taskDir": task_dir, "updatedAt": issue.get("updatedAt")}


def discover(number=None):
    if number is None:
        command = ["gh", "issue", "list", "--repo", REPOSITORY, "--state", "open", "--limit", "100", "--json", "number,title,body,updatedAt"]
    else:
        command = ["gh", "issue", "view", str(number), "--repo", REPOSITORY, "--json", "number,title,body,updatedAt,state"]
    completed = subprocess.run(command, cwd=PROJECT_ROOT, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr)
    payload = json.loads(completed.stdout)
    issues = payload if isinstance(payload, list) else [payload]
    if number is not None and issues[0].get("state") != "OPEN":
        return []
    eligible_issues = [item for item in (eligible(issue) for issue in issues) if item is not None]
    eligible_issues.sort(key=lambda item: item["number"])
    return eligible_issues


def record_run(issue, result):
    state = read_json(STATE_PATH) if STATE_PATH.exists() else {"runs": []}
    state["updatedAt"] = now()
    state["runs"].append({"at": now(), "issue": issue["number"], "taskDir": str(issue["taskDir"]), "result": result})
    write_json(STATE_PATH, state)


def run_issue(issue):
    completed = subprocess.run([sys.executable, str(PIPELINE_PATH), str(issue["taskDir"])], cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=3600, check=False)
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError:
        result = {"ok": False, "error": "pipeline 输出不是 JSON", "stdout": completed.stdout, "stderr": completed.stderr}
    if completed.returncode != 0 and result.get("ok"):
        result = {"ok": False, "error": "pipeline 返回码与输出不一致"}
    result["returnCode"] = completed.returncode
    record_run(issue, result)
    return result


def run_cycle(number=None):
    issues = discover(number)
    results = []
    for issue in issues:
        result = run_issue(issue)
        results.append({"issue": issue["number"], **result})
        if number is not None:
            break
    return {"ok": all(item.get("ok") for item in results), "processed": len(results), "results": results}


def main():
    parser = argparse.ArgumentParser(description="Discover and run prepared Production issues through the Codex CLI pipeline.")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--issue", type=int)
    parser.add_argument("--poll-interval", type=int, default=15)
    args = parser.parse_args()
    if args.poll_interval < 1:
        parser.error("--poll-interval must be positive")
    acquire_lock()
    try:
        while True:
            try:
                result = run_cycle(args.issue)
            except Exception as exc:
                if args.once or args.issue is not None:
                    raise
                print(json.dumps({"ok": False, "retry": True, "error": str(exc)}, ensure_ascii=False), flush=True)
                time.sleep(args.poll_interval)
                continue
            print(json.dumps(result, ensure_ascii=False), flush=True)
            if args.once or args.issue is not None:
                return 0 if result["ok"] else 1
            time.sleep(args.poll_interval)
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), flush=True)
        return 1
    finally:
        release_lock()


if __name__ == "__main__":
    sys.exit(main())
