#!/usr/bin/env python3
"""Prototype firearm-in-image detector.

This research model is not validated for safety or security decisions. Review
its license and verify all results with a person before acting on them.

Usage (place the image beside this script):
    python3 image-detect.py some-image.png

The model weights are downloaded from Hugging Face on the first run and then
cached by huggingface_hub.
"""

import argparse
from pathlib import Path
import sys

from huggingface_hub import hf_hub_download
from PIL import Image, UnidentifiedImageError
from ultralytics import YOLO


MODEL_REPOSITORY = "Subh775/Firearm_Detection_Yolov8n"
MODEL_FILENAME = "weights/best.pt"
CONFIDENCE_THRESHOLD = 0.4
SUPPORTED_FORMATS = {
    ".bmp",
    ".gif",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check an image for a firearm using a prototype detection model."
    )
    parser.add_argument(
        "image",
        help="Image path (relative paths are resolved beside this script).",
    )
    return parser.parse_args()


def resolve_image_path(image_arg: str) -> Path:
    image_path = Path(image_arg).expanduser()
    if not image_path.is_absolute():
        image_path = Path(__file__).resolve().parent / image_path
    return image_path.resolve()


def main() -> int:
    args = parse_args()
    image_path = resolve_image_path(args.image)

    if image_path.suffix.lower() not in SUPPORTED_FORMATS:
        supported = ", ".join(sorted(SUPPORTED_FORMATS))
        print(f"Unsupported image format. Supported extensions: {supported}", file=sys.stderr)
        return 2
    if not image_path.is_file():
        print(f"Image file not found: {image_path}", file=sys.stderr)
        return 2

    try:
        with Image.open(image_path) as image:
            image.verify()
        with Image.open(image_path) as image_file:
            image = image_file.convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        print(f"Could not read image '{image_path}': {exc}", file=sys.stderr)
        return 2

    print("Loading firearm detection model (first run downloads weights)...")
    try:
        weights_path = hf_hub_download(
            repo_id=MODEL_REPOSITORY,
            filename=MODEL_FILENAME,
        )
        model = YOLO(weights_path)
        results = model.predict(
            source=image,
            conf=CONFIDENCE_THRESHOLD,
            verbose=False,
        )
    except Exception as exc:
        print(f"Could not load model or analyze image: {exc}", file=sys.stderr)
        return 1
    finally:
        image.close()

    detections = []
    for result in results:
        for box in result.boxes:
            class_id = int(box.cls[0].item())
            label = result.names[class_id]
            confidence = float(box.conf[0].item())
            coordinates = [int(round(value)) for value in box.xyxy[0].tolist()]
            detections.append((label, confidence, coordinates))

    if not detections:
        print("No firearm detections above the confidence threshold.")
        return 0

    print(f"Found {len(detections)} detection(s) in {image_path.name}:")
    for label, confidence, (x1, y1, x2, y2) in detections:
        print(f"- {label}: confidence {confidence:.1%}, box [x1={x1}, y1={y1}, x2={x2}, y2={y2}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())