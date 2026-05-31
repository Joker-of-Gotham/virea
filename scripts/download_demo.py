"""Download demo data from HuggingFace to the local demo/ directory.

Usage:
    python scripts/download_demo.py              # download both raw + processed
    python scripts/download_demo.py --raw-only   # download only raw (re-process locally)
    python scripts/download_demo.py --processed-only  # download only processed

Requires: pip install huggingface_hub
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HF_REPO_ID = "ChikaKomari/virea-demo"


def main() -> None:
    parser = argparse.ArgumentParser(description="Download VIREA demo data from HuggingFace")
    parser.add_argument("--raw-only", action="store_true", help="Only download raw data")
    parser.add_argument("--processed-only", action="store_true", help="Only download processed data")
    parser.add_argument("--target", type=str, default=None, help="Target directory (default: <repo_root>/demo)")
    args = parser.parse_args()

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("ERROR: huggingface_hub is required. Install with: pip install huggingface_hub")
        sys.exit(1)

    repo_root = Path(__file__).resolve().parents[1]
    target = Path(args.target) if args.target else repo_root / "demo"

    if args.raw_only:
        patterns = ["raw/**"]
        desc = "raw"
    elif args.processed_only:
        patterns = ["processed/**"]
        desc = "processed"
    else:
        patterns = None
        desc = "all (raw + processed)"

    print(f"Downloading VIREA demo data ({desc}) from HuggingFace...")
    print(f"  Repo:   https://huggingface.co/datasets/{HF_REPO_ID}")
    print(f"  Target: {target}")
    print()

    local_dir = snapshot_download(
        repo_id=HF_REPO_ID,
        repo_type="dataset",
        local_dir=str(target),
        allow_patterns=patterns,
    )

    print(f"\nDone! Demo data downloaded to: {local_dir}")
    print("\nNext steps:")
    print("  python -m virea process --data-source demo")
    print("  python -m virea serve --data-source demo")


if __name__ == "__main__":
    main()
