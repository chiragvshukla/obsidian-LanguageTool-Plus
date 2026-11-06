"""Build the local wordbook from the pinned sources.

Run from the repository root while the gateway is not required:

    python scripts/build_dictionary.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "gateway" / "src"))

from ltplus.wordbook_build import build_all  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and build the wordbook.")
    parser.add_argument(
        "--dir",
        type=Path,
        default=ROOT / "data" / "wordbook",
        help="Output directory (default: data/wordbook).",
    )
    args = parser.parse_args()
    build_all(args.dir, lambda pair, message: print(f"{pair}: {message}", flush=True))


if __name__ == "__main__":
    main()