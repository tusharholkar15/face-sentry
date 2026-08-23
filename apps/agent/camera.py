"""
Camera Capture Interface and Hardware Abstraction
"""

import sys
import logging
from typing import Optional, Tuple
import cv2
import numpy as np

logger = logging.getLogger("facesentry.camera")


class CameraManager:
    """Manages OpenCV DirectShow/V4L2 camera capture stream with safe error handling."""

    def __init__(
        self,
        camera_index: int = 0,
        width: int = 640,
        height: int = 480,
        target_fps: int = 15,
    ):
        self.camera_index = camera_index
        self.width = width
        self.height = height
        self.target_fps = target_fps
        self._cap: Optional[cv2.VideoCapture] = None
        self._is_opened = False

    def open(self) -> bool:
        """Initialize and open the camera device."""
        if self._is_opened and self._cap is not None:
            return True

        # Prefer CAP_DSHOW on Windows for lower latency, fallback to default CAP_ANY
        backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY

        try:
            logger.info(f"Opening camera index {self.camera_index} with backend {backend}")
            self._cap = cv2.VideoCapture(self.camera_index, backend)
            if not self._cap.isOpened():
                logger.warning(f"Could not open camera index {self.camera_index} with primary backend. Trying fallback.")
                self._cap = cv2.VideoCapture(self.camera_index)

            if self._cap.isOpened():
                self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                self._cap.set(cv2.CAP_PROP_FPS, self.target_fps)
                self._is_opened = True
                logger.info(f"Camera index {self.camera_index} initialized successfully.")
                return True
            else:
                logger.warning(f"Camera index {self.camera_index} is unavailable.")
                self._is_opened = False
                return False
        except Exception as exc:
            logger.error(f"Error opening camera {self.camera_index}: {exc}")
            self._is_opened = False
            return False

    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Read a single frame from the camera."""
        if not self._is_opened or self._cap is None:
            return False, None

        try:
            ret, frame = self._cap.read()
            if ret and frame is not None:
                return True, frame
            return False, None
        except Exception as exc:
            logger.error(f"Error reading camera frame: {exc}")
            return False, None

    def release(self) -> None:
        """Release camera hardware resources."""
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self._is_opened = False
        logger.info(f"Camera {self.camera_index} released.")

    def is_connected(self) -> bool:
        """Check whether camera device is currently active."""
        return self._is_opened and self._cap is not None and self._cap.isOpened()
