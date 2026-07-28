#!/usr/bin/env python3

import os
import subprocess
import sys
from pathlib import Path
def main() -> int:
    # Keep backward compatibility: old script defaulted to --action get.
    forwarded_args = sys.argv[1:]
    if "--action" not in forwarded_args:
        forwarded_args = ["--action", "get", *forwarded_args]

    command = [sys.executable, "-m", "energy_server", *forwarded_args]
    repo_root = Path(__file__).resolve().parents[1]
    generated_path = repo_root / "src" / "energy_server" / "generated"
    src_path = repo_root / "src"

    env = dict(os.environ)
    existing_pythonpath = env.get("PYTHONPATH")
    forward_pythonpath = f"{src_path}:{generated_path}"
    env["PYTHONPATH"] = (
        f"{forward_pythonpath}:{existing_pythonpath}" if existing_pythonpath else forward_pythonpath
    )
    return subprocess.call(command, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
