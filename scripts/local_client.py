#!/usr/bin/env python3

import subprocess
import sys
from pathlib import Path


def main() -> int:
    # Keep backward compatibility: old script defaulted to --action get.
    forwarded_args = sys.argv[1:]
    if not any(arg == "--action" or arg.startswith("--action=") for arg in forwarded_args):
        forwarded_args = ["--action", "get", *forwarded_args]

    repo_root = Path(__file__).resolve().parents[1]
    command = [
        "docker",
        "compose",
        "exec",
        "-T",
        "energy_server",
        "energy-server",
        *forwarded_args,
    ]
    return subprocess.call(command, cwd=repo_root)


if __name__ == "__main__":
    raise SystemExit(main())
