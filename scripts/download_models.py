"""
FaceSentry Official Model Download and Verification Utility
Downloads pinned, official OpenCV Zoo ONNX models to data/models/ and validates SHA-256 integrity.
"""

import sys
import os
import argparse
import logging
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apps.agent.facesentry_agent.models.model_manager import (
    ModelManager,
    PINNED_MODELS,
    ModelNotFoundError,
    ModelCorruptedError,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [ModelSetup] %(message)s",
)
logger = logging.getLogger("facesentry.model_setup")


def main():
    parser = argparse.ArgumentParser(description="Download and verify official FaceSentry ONNX models")
    parser.add_argument("--check", action="store_true", help="Only verify existing models without downloading")
    parser.add_argument("--force", action="store_true", help="Force re-download even if files exist")
    parser.add_argument("--models-dir", type=str, default=None, help="Target models directory")
    args = parser.parse_args()

    manager = ModelManager(models_dir=args.models_dir)
    print("==========================================================")
    print(" FaceSentry Pinned Model Verification & Provisioning Tool ")
    print("==========================================================")
    print(f"Target Directory: {manager.models_dir}\n")

    all_valid = True

    for key, spec in PINNED_MODELS.items():
        print(f"[*] Checking model: {spec.name} ({spec.filename})")
        print(f"    Description: {spec.description}")
        print(f"    Source URL:  {spec.official_url}")
        print(f"    Expected SHA256: {spec.sha256_hash}")

        if args.check:
            try:
                manager.verify_model(key)
                print("    Status: [VERIFIED OK]\n")
            except (ModelNotFoundError, ModelCorruptedError) as exc:
                print(f"    Status: [MISSING / INVALID] - {exc}\n")
                all_valid = False
        else:
            try:
                manager.download_model(key, force=args.force)
                print("    Status: [DOWNLOADED & VERIFIED OK]\n")
            except Exception as exc:
                print(f"    Status: [DOWNLOAD FAILED] - {exc}\n")
                all_valid = False

    print("==========================================================")
    if all_valid:
        print("[SUCCESS] All required ONNX model artifacts are verified.")
        sys.exit(0)
    else:
        print("[WARNING] One or more models are missing or unverified.")
        if args.check:
            print("Run `python scripts/download_models.py` to download them.")
        sys.exit(1)


if __name__ == "__main__":
    main()
