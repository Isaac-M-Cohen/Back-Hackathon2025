"""Copy preset keypoint CSV + labels into the user_data directory."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure project root is on path when run as a script
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from video_module.gesture_ml import GestureDataset
from utils.log_utils import tprint


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy preset keypoint samples into user_data.")
    parser.add_argument(
        "--keypoint_csv", type=Path, default=ROOT / "data" / "presets" / "keypoint.csv"
    )
    parser.add_argument(
        "--label_csv",
        type=Path,
        default=ROOT / "data" / "presets" / "keypoint_classifier_label.csv",
    )
    parser.add_argument("--user_id", type=str, default="default")
    args = parser.parse_args()

    if not args.keypoint_csv.exists() or not args.label_csv.exists():
        raise SystemExit("Missing keypoint.csv or keypoint_classifier_label.csv.")

    dataset = GestureDataset(user_id=args.user_id)
    dataset.keypoint_dir.mkdir(parents=True, exist_ok=True)
    dataset.keypoint_csv.write_text(args.keypoint_csv.read_text())
    dataset.keypoint_labels_path.write_text(args.label_csv.read_text())
    tprint(f"Copied presets into {dataset.keypoint_dir}")


if __name__ == "__main__":
    main()
