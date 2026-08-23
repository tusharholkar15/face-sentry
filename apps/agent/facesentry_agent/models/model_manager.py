"""
FaceSentry Model Manager
Manages path resolution, cryptographic integrity verification, and explicit setup checks for ONNX models.
"""

import os
import hashlib
import logging
from pathlib import Path
from typing import Dict, Optional, NamedTuple
import urllib.request

logger = logging.getLogger("facesentry.models.manager")


class ModelSpec(NamedTuple):
    """Specification for a required deep learning ONNX model."""
    name: str
    filename: str
    official_url: str
    sha256_hash: str
    expected_size_bytes: int
    description: str


# Pinned Official OpenCV Zoo Model Artifacts
PINNED_MODELS: Dict[str, ModelSpec] = {
    "face_detection_yunet": ModelSpec(
        name="face_detection_yunet",
        filename="face_detection_yunet_2023mar.onnx",
        official_url="https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        sha256_hash="8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
        expected_size_bytes=232589,  # ~232 KB
        description="YuNet lightweight face detector (OpenCV Zoo 2023-Mar release)",
    ),
    "face_recognition_sface": ModelSpec(
        name="face_recognition_sface",
        filename="face_recognition_sface_2021dec.onnx",
        official_url="https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        sha256_hash="0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
        expected_size_bytes=38696353,  # ~36.9 MB
        description="SFace deep metric learning face recognizer (OpenCV Zoo 2021-Dec release)",
    ),
}


class ModelNotFoundError(FileNotFoundError):
    """Raised when a required ONNX model file does not exist locally."""
    pass


class ModelCorruptedError(ValueError):
    """Raised when an ONNX model file exists but fails SHA-256 cryptographic verification."""
    pass


class ModelManager:
    """Manages local model directory, path resolution, and integrity checks."""

    def __init__(self, models_dir: Optional[str] = None):
        if models_dir:
            self.models_dir = Path(models_dir)
        else:
            # Default to data/models relative to project root
            project_root = Path(__file__).resolve().parents[4]
            self.models_dir = project_root / "data" / "models"

        self.models_dir.mkdir(parents=True, exist_ok=True)

    def get_spec(self, model_key: str) -> ModelSpec:
        """Retrieve model specification by key."""
        if model_key not in PINNED_MODELS:
            raise KeyError(f"Unknown model key: '{model_key}'. Available models: {list(PINNED_MODELS.keys())}")
        return PINNED_MODELS[model_key]

    def get_model_path(self, model_key: str) -> Path:
        """Resolve absolute path to a model file."""
        spec = self.get_spec(model_key)
        return self.models_dir / spec.filename

    def is_model_present(self, model_key: str) -> bool:
        """Check if model file exists on disk."""
        path = self.get_model_path(model_key)
        return path.is_file()

    def compute_sha256(self, file_path: Path) -> str:
        """Compute SHA-256 hash of a local file."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def verify_model(self, model_key: str) -> bool:
        """
        Verify that a local model file exists, is non-empty, and matches its expected SHA-256.
        Raises ModelNotFoundError or ModelCorruptedError if verification fails.
        """
        spec = self.get_spec(model_key)
        path = self.get_model_path(model_key)

        if not path.is_file():
            raise ModelNotFoundError(
                f"Required model '{spec.filename}' not found in {self.models_dir}.\n"
                f"Please run `python scripts/download_models.py` to provision official model files."
            )

        actual_hash = self.compute_sha256(path)
        if actual_hash.lower() != spec.sha256_hash.lower():
            raise ModelCorruptedError(
                f"Model file '{spec.filename}' failed SHA-256 integrity check.\n"
                f"Expected: {spec.sha256_hash}\n"
                f"Actual:   {actual_hash}\n"
                f"Please re-download the model via `python scripts/download_models.py --force`."
            )

        logger.info(f"Model '{spec.filename}' verified successfully (SHA256: {actual_hash[:8]}...)")
        return True

    def check_all_models(self) -> Dict[str, bool]:
        """Check presence and integrity of all required models."""
        status = {}
        for key in PINNED_MODELS:
            try:
                self.verify_model(key)
                status[key] = True
            except (ModelNotFoundError, ModelCorruptedError) as exc:
                logger.warning(f"Model check failed for '{key}': {exc}")
                status[key] = False
        return status

    def download_model(self, model_key: str, force: bool = False) -> Path:
        """
        Explicitly download an official model artifact from pinned URL and verify its SHA-256.
        This must only be called via dedicated setup scripts or CLI commands, never silently at runtime.
        """
        spec = self.get_spec(model_key)
        dest_path = self.get_model_path(model_key)

        if dest_path.is_file() and not force:
            try:
                self.verify_model(model_key)
                logger.info(f"Model '{spec.filename}' already exists and is verified.")
                return dest_path
            except ModelCorruptedError:
                logger.warning(f"Existing model '{spec.filename}' is corrupted. Re-downloading...")

        logger.info(f"Downloading '{spec.filename}' from official source: {spec.official_url}")
        
        # Download to a temporary file first
        temp_dest = dest_path.with_suffix(".tmp")
        try:
            req = urllib.request.Request(
                spec.official_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) FaceSentry-ModelManager/1.0"}
            )
            with urllib.request.urlopen(req) as response, open(temp_dest, "wb") as out_file:
                chunk_size = 65536
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    out_file.write(chunk)

            # Validate hash before finalizing
            hasher = hashlib.sha256()
            with open(temp_dest, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    hasher.update(chunk)
            downloaded_hash = hasher.hexdigest()

            if downloaded_hash.lower() != spec.sha256_hash.lower():
                if temp_dest.exists():
                    temp_dest.unlink()
                raise ModelCorruptedError(
                    f"Downloaded model '{spec.filename}' failed SHA-256 verification.\n"
                    f"Expected: {spec.sha256_hash}\n"
                    f"Received: {downloaded_hash}"
                )

            # Atomic rename
            temp_dest.replace(dest_path)
            logger.info(f"Successfully downloaded and verified '{spec.filename}' at {dest_path}")
            return dest_path
        except Exception as exc:
            if temp_dest.exists():
                temp_dest.unlink()
            raise RuntimeError(f"Failed to download model '{spec.filename}': {exc}") from exc
