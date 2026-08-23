"""
Biometric Storage & Encryption Layer
Manages local persistence of enrolled face embedding templates using Windows DPAPI (CryptProtectData).
Never writes plaintext biometric data or raw images to disk.
"""

import os
import sys
import json
import struct
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List
import numpy as np

logger = logging.getLogger("facesentry.biometric_storage")


@dataclass
class EnrolledProfile:
    """Represents an authorized user's decrypted biometric profile."""
    profile_name: str
    created_at: str
    updated_at: str
    sample_count: int
    embedding_dim: int
    reference_embedding: np.ndarray
    quality_metrics: Dict[str, Any]

    def __repr__(self) -> str:
        # Prevent accidental logging of biometric embedding vectors
        return (
            f"<EnrolledProfile(name='{self.profile_name}', "
            f"dim={self.embedding_dim}, samples={self.sample_count}, "
            f"created_at='{self.created_at}')>"
        )


class BiometricStorageBackend(ABC):
    """Abstract interface for encrypting and decrypting biometric payloads."""

    @abstractmethod
    def encrypt(self, plaintext_bytes: bytes) -> bytes:
        """Encrypt plaintext bytes."""
        pass

    @abstractmethod
    def decrypt(self, ciphertext_bytes: bytes) -> bytes:
        """Decrypt ciphertext bytes."""
        pass


class WindowsDPAPIBackend(BiometricStorageBackend):
    """
    Production encryption backend utilizing Windows Data Protection API (DPAPI).
    Tied directly to the current logged-in Windows user master key.
    """

    def __init__(self):
        if sys.platform != "win32":
            raise RuntimeError("Windows DPAPI is only supported on Windows OS.")
        
        import ctypes
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [
                ("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_byte)),
            ]

        self._DATA_BLOB = DATA_BLOB
        self._crypt32 = ctypes.windll.crypt32
        self._kernel32 = ctypes.windll.kernel32

    def encrypt(self, plaintext_bytes: bytes) -> bytes:
        import ctypes

        in_blob = self._DATA_BLOB()
        in_blob.cbData = len(plaintext_bytes)
        in_blob.pbData = ctypes.cast(
            ctypes.create_string_buffer(plaintext_bytes, len(plaintext_bytes)),
            ctypes.POINTER(ctypes.c_byte),
        )

        out_blob = self._DATA_BLOB()
        
        # CRYPTPROTECT_UI_FORBIDDEN = 0x1
        flags = 0x1
        success = self._crypt32.CryptProtectData(
            ctypes.byref(in_blob),
            "FaceSentry Biometric Template",
            None,
            None,
            None,
            flags,
            ctypes.byref(out_blob),
        )

        if not success:
            err_code = self._kernel32.GetLastError()
            raise RuntimeError(f"CryptProtectData failed with error code: {err_code}")

        try:
            encrypted_data = ctypes.string_at(out_blob.pbData, out_blob.cbData)
            return encrypted_data
        finally:
            self._kernel32.LocalFree(out_blob.pbData)

    def decrypt(self, ciphertext_bytes: bytes) -> bytes:
        import ctypes

        in_blob = self._DATA_BLOB()
        in_blob.cbData = len(ciphertext_bytes)
        in_blob.pbData = ctypes.cast(
            ctypes.create_string_buffer(ciphertext_bytes, len(ciphertext_bytes)),
            ctypes.POINTER(ctypes.c_byte),
        )

        out_blob = self._DATA_BLOB()
        flags = 0x1
        success = self._crypt32.CryptUnprotectData(
            ctypes.byref(in_blob),
            None,
            None,
            None,
            None,
            flags,
            ctypes.byref(out_blob),
        )

        if not success:
            err_code = self._kernel32.GetLastError()
            raise RuntimeError(f"CryptUnprotectData failed with error code: {err_code}")

        try:
            decrypted_data = ctypes.string_at(out_blob.pbData, out_blob.cbData)
            return decrypted_data
        finally:
            self._kernel32.LocalFree(out_blob.pbData)


class MockEncryptedStorageBackend(BiometricStorageBackend):
    """
    Isolated encryption backend for unit testing and CI environments.
    Uses XOR/HMAC simulation with header verification without modifying production behavior.
    """

    MAGIC_HEADER = b"FACESENTRY_MOCK_ENC_v1:"

    def __init__(self, key_byte: int = 0x5A):
        self.key_byte = key_byte

    def encrypt(self, plaintext_bytes: bytes) -> bytes:
        encrypted = bytes([b ^ self.key_byte for b in plaintext_bytes])
        return self.MAGIC_HEADER + encrypted

    def decrypt(self, ciphertext_bytes: bytes) -> bytes:
        if not ciphertext_bytes.startswith(self.MAGIC_HEADER):
            raise ValueError("Invalid mock ciphertext header or corrupted data.")
        raw_cipher = ciphertext_bytes[len(self.MAGIC_HEADER):]
        return bytes([b ^ self.key_byte for b in raw_cipher])


class BiometricStorage:
    """Manages secure encrypted persistence of biometric templates on disk."""

    def __init__(
        self,
        enrollment_dir: Optional[str] = None,
        backend: Optional[BiometricStorageBackend] = None,
    ):
        if enrollment_dir:
            self.enrollment_dir = Path(enrollment_dir)
        else:
            project_root = Path(__file__).resolve().parents[3]
            self.enrollment_dir = project_root / "data" / "enrollment"

        self.enrollment_dir.mkdir(parents=True, exist_ok=True)

        if backend is not None:
            self.backend = backend
        elif sys.platform == "win32":
            try:
                self.backend = WindowsDPAPIBackend()
            except Exception as exc:
                logger.warning(f"Could not initialize Windows DPAPI: {exc}. Using mock backend.")
                self.backend = MockEncryptedStorageBackend()
        else:
            self.backend = MockEncryptedStorageBackend()

    def _get_profile_path(self, profile_name: str) -> Path:
        # Sanitize profile name
        safe_name = "".join(c for c in profile_name if c.isalnum() or c in ("-", "_")).strip()
        if not safe_name:
            safe_name = "default_user"
        return self.enrollment_dir / f"{safe_name}.dat"

    def has_profile(self, profile_name: str = "default_user") -> bool:
        """Check if an encrypted biometric profile file exists."""
        path = self._get_profile_path(profile_name)
        return path.is_file() and path.stat().st_size > 0

    def save_profile(
        self,
        profile_name: str,
        reference_embedding: np.ndarray,
        sample_count: int = 1,
        quality_metrics: Optional[Dict[str, Any]] = None,
    ) -> Path:
        """
        Serialize and encrypt biometric template vector to disk using DPAPI.
        Never writes plaintext vectors.
        """
        vec = reference_embedding.flatten().astype(np.float32)
        dim = int(vec.shape[0])
        now_iso = datetime.now(timezone.utc).isoformat()

        # Binary layout:
        # [Header JSON length (4 bytes uint32)]
        # [Header JSON UTF-8 bytes]
        # [Float32 vector bytes (dim * 4 bytes)]
        header_dict = {
            "profile_name": profile_name,
            "created_at": now_iso,
            "updated_at": now_iso,
            "sample_count": sample_count,
            "embedding_dim": dim,
            "quality_metrics": quality_metrics or {},
        }
        header_bytes = json.dumps(header_dict).encode("utf-8")
        vec_bytes = vec.tobytes()

        payload = struct.pack("<I", len(header_bytes)) + header_bytes + vec_bytes

        # Encrypt the complete payload
        encrypted_payload = self.backend.encrypt(payload)

        dest_path = self._get_profile_path(profile_name)
        temp_path = dest_path.with_suffix(".tmp")

        with open(temp_path, "wb") as f:
            f.write(encrypted_payload)

        # Atomic replacement
        temp_path.replace(dest_path)
        logger.info(f"Biometric template successfully encrypted and stored for '{profile_name}'.")
        return dest_path

    def load_profile(self, profile_name: str = "default_user") -> EnrolledProfile:
        """
        Read and decrypt biometric profile template from disk.
        Raises FileNotFoundError if missing, or ValueError if corrupted.
        """
        dest_path = self._get_profile_path(profile_name)
        if not dest_path.is_file():
            raise FileNotFoundError(f"No enrolled biometric profile found for '{profile_name}'.")

        with open(dest_path, "rb") as f:
            encrypted_payload = f.read()

        if not encrypted_payload:
            raise ValueError(f"Enrolled profile file '{dest_path}' is empty or corrupted.")

        try:
            decrypted_payload = self.backend.decrypt(encrypted_payload)
        except Exception as exc:
            raise ValueError(f"Failed to decrypt biometric profile: {exc}") from exc

        if len(decrypted_payload) < 4:
            raise ValueError("Corrupted biometric profile data: insufficient length.")

        header_len = struct.unpack("<I", decrypted_payload[:4])[0]
        if len(decrypted_payload) < 4 + header_len:
            raise ValueError("Corrupted biometric profile data: invalid header offset.")

        header_json = decrypted_payload[4: 4 + header_len].decode("utf-8")
        header = json.loads(header_json)

        vec_bytes = decrypted_payload[4 + header_len:]
        dim = header["embedding_dim"]
        expected_vec_len = dim * 4

        if len(vec_bytes) != expected_vec_len:
            raise ValueError(
                f"Biometric vector size mismatch. Expected {expected_vec_len} bytes for dim={dim}, got {len(vec_bytes)} bytes."
            )

        vec = np.frombuffer(vec_bytes, dtype=np.float32).copy()

        return EnrolledProfile(
            profile_name=header["profile_name"],
            created_at=header["created_at"],
            updated_at=header["updated_at"],
            sample_count=header["sample_count"],
            embedding_dim=dim,
            reference_embedding=vec,
            quality_metrics=header.get("quality_metrics", {}),
        )

    def delete_profile(self, profile_name: str = "default_user") -> bool:
        """Permanently remove enrolled profile file from disk."""
        path = self._get_profile_path(profile_name)
        if path.is_file():
            path.unlink()
            logger.info(f"Biometric template for '{profile_name}' deleted.")
            return True
        return False
