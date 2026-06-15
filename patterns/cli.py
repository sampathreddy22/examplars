"""
Entry point: uv run examplars <pattern>

To add a new pattern:
  1. Create patterns/<name>/ with a main.py that exposes run()
  2. Add one line to REGISTRY below
"""

import importlib
import sys

REGISTRY: dict[str, str] = {
    "saga": "patterns.saga.main",
    # future patterns go here, e.g.:
    # "cqrs":    "patterns.cqrs.main",
    # "outbox":  "patterns.outbox.main",
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in REGISTRY:
        _print_usage()
        sys.exit(1 if len(sys.argv) < 2 else 0)

    pattern = sys.argv[1]
    module = importlib.import_module(REGISTRY[pattern])
    module.run()


def _print_usage() -> None:
    patterns = "\n".join(f"  examplars {name}" for name in REGISTRY)
    print(f"Usage: examplars <pattern>\n\nAvailable patterns:\n{patterns}")
