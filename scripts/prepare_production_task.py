#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from task_protocol import create_task_package

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description="Create a version-2 production task package without starting generation.")
    parser.add_argument("config", type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    task_dir = create_task_package(config, PROJECT_ROOT)
    print(json.dumps({"ok": True, "taskDir": str(task_dir), "reviewProtocolVersion": 2}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
