"""Import preset hand sign samples into the local dataset and train a model.

Expected input files (placed at repo root or provide via CLI args):
- keypoint.csv (label_id,x1,y1,x2,y2,... for 21 landmarks -> 42 values)
- keypoint_classifier_label.csv (one label per line, in order of label_id)

This script pads missing Z values with 0 to produce 63-dim frame features,
tiles each frame to a window (default 30) to match our MLP input shape,
adds a small NONE class, and retrains the model for the given user_id.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Iterable

import numpy as np

# Ensure project root is on path when run as a script
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from video_module.gesture_ml import GestureDataset, GestureTrainer


def load_labels(path: Path) -> list[str]:
    labels: list[str] = []
    with path.open() as fh:
        for row in csv.reader(fh):
            if not row:
                continue
            labels.append(row[0].lstrip("\ufeff").strip())
    return labels


def frame_to_63(row: list[str]) -> np.ndarray:
    """Convert 42-value x/y list to 63-value x/y/z list (z padded to 0)."""
    coords = [float(v) for v in row]
    if len(coords) != 42:
        raise ValueError(f"Expected 42 coords, got {len(coords)}")
    triplets: list[float] = []
    for i in range(0, 42, 2):
        triplets.extend([coords[i], coords[i + 1], 0.0])
    return np.array(triplets, dtype=np.float32)


def tile_window(features: np.ndarray, window_size: int) -> np.ndarray:
    """Repeat a single frame feature vector to fill the model window."""
    tiled = np.tile(features, (window_size, 1))
    return tiled.flatten().astype(np.float32)


def import_keypoints(
    keypoint_csv: Path,
    label_csv: Path,
    dataset: GestureDataset,
    *,
    window_size: int,
    none_samples: int = 30,
) -> None:
    labels = load_labels(label_csv)
    samples_by_label: dict[str, list[np.ndarray]] = {lbl: [] for lbl in labels}

    with keypoint_csv.open() as fh:
        reader = csv.reader(fh)
        for row in reader:
            if not row:
                continue
            label_idx = int(row[0])
            if label_idx >= len(labels):
                continue
            label = labels[label_idx]
            feats = frame_to_63(row[1:])
            window_feats = tile_window(feats, window_size)
            samples_by_label[label].append(window_feats)

    for label, samples in samples_by_label.items():
        if samples:
            dataset.add_samples(label, samples)

    # Add simple NONE samples (zero-vector windows) for idle baseline.
    if none_samples > 0:
        none_feat = np.zeros(63, dtype=np.float32)
        none_window = tile_window(none_feat, window_size)
        dataset.add_samples("NONE", [none_window for _ in range(none_samples)])

    dataset.save()


def main() -> None:
    parser = argparse.ArgumentParser(description="Import preset hand sign samples and train model.")
    parser.add_argument(
        "--keypoint_csv", type=Path, default=ROOT / "data" / "presets" / "keypoint.csv"
    )
    parser.add_argument(
        "--label_csv",
        type=Path,
        default=ROOT / "data" / "presets" / "keypoint_classifier_label.csv",
    )
    parser.add_argument("--user_id", type=str, default="default")
    parser.add_argument("--window_size", type=int, default=30)
    args = parser.parse_args()

    if not args.keypoint_csv.exists() or not args.label_csv.exists():
        raise SystemExit("Missing keypoint.csv or keypoint_classifier_label.csv in the working directory.")

    dataset = GestureDataset(user_id=args.user_id)
    import_keypoints(
        args.keypoint_csv,
        args.label_csv,
        dataset,
        window_size=args.window_size,
    )

    trainer = GestureTrainer(window_size=args.window_size)
    artifacts = trainer.train(dataset)
    dataset.save_model(artifacts)
    print(f"Imported presets and trained model for user '{args.user_id}'")


if __name__ == "__main__":
    main()
