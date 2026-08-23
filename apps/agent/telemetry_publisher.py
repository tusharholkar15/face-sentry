"""
FaceSentry Agent Telemetry Publisher
Formats, rate-limits, deduplicates, and transmits non-biometric operational telemetry
and transition security events from the Windows Agent to the local FastAPI broker.
"""

import time
import json
import logging
import threading
import urllib.request
import urllib.error
from typing import Optional, Dict, Any, List, Tuple

from packages.shared.schemas import TelemetrySnapshot, TelemetryPublishRequest
from apps.agent.facesentry_agent.recognition import RecognitionResult
from apps.agent.facesentry_agent.liveness import LivenessResult
from apps.agent.facesentry_agent.decision_engine import DecisionResult, DecisionEvent
from apps.agent.facesentry_agent.lock_manager import LockEvent

logger = logging.getLogger("facesentry.agent.telemetry")


class AgentTelemetryPublisher:
    """
    Publishes rate-limited, deduplicated telemetry snapshots and immediate
    transition security events to the local FaceSentry API.
    """

    def __init__(
        self,
        api_url: str = "http://127.0.0.1:8000/api/v1/telemetry/publish",
        max_updates_per_second: float = 5.0,
        enable_network_publish: bool = True,
        clock_fn=time.time,
    ):
        self.api_url = api_url
        self.min_interval = 1.0 / max_updates_per_second if max_updates_per_second > 0 else 0.2
        self.enable_network_publish = enable_network_publish
        self.clock_fn = clock_fn

        self._last_publish_time: float = 0.0
        self._last_state_hash: Optional[str] = None
        self._last_snapshot: Optional[TelemetrySnapshot] = None
        self._lock = threading.Lock()

    def create_snapshot(
        self,
        decision: Optional[DecisionResult],
        recognition: Optional[RecognitionResult],
        liveness: Optional[LivenessResult],
        camera_available: bool,
        uptime_seconds: float,
        last_event: Optional[Dict[str, Any]] = None,
    ) -> TelemetrySnapshot:
        """Construct non-biometric TelemetrySnapshot from pipeline stage results."""
        now = self.clock_fn()

        # Extract bounding box safely without landmarks
        bbox = None
        if recognition and recognition.detected_face:
            bbox = list(recognition.detected_face.bbox)

        # Determine aggregate authentication state
        if not camera_available:
            auth_state = "NO_FACE"
            cam_status = "DISCONNECTED"
        else:
            cam_status = "CONNECTED"
            if recognition and recognition.face_count == 0:
                auth_state = "NO_FACE"
            elif recognition and recognition.recognized:
                auth_state = "AUTHENTICATED"
            elif recognition and not recognition.recognized and recognition.face_count > 0:
                auth_state = "UNRECOGNIZED"
            else:
                auth_state = "AUTHENTICATING"

        return TelemetrySnapshot(
            timestamp=now,
            agent_status="RUNNING",
            camera_status=cam_status,
            authentication_state=auth_state,
            recognition_similarity=round(recognition.similarity, 3) if recognition else 0.0,
            liveness_state=liveness.state.value if liveness else "INITIALIZING",
            liveness_verified=liveness.verified if liveness else False,
            liveness_confidence=round(liveness.confidence, 3) if liveness else 0.0,
            face_detected=bool(recognition and recognition.face_count > 0),
            face_count=recognition.face_count if recognition else 0,
            absence_duration=round(decision.absence_duration, 1) if decision else 0.0,
            stranger_duration=round(decision.stranger_duration, 1) if decision else 0.0,
            spoof_duration=round(decision.spoof_duration, 1) if decision else 0.0,
            decision_state=decision.state.value if decision else "INITIALIZING",
            lock_requested=decision.lock_requested if decision else False,
            last_security_event=last_event,
            system_uptime=round(uptime_seconds, 1),
            bounding_box=bbox,
        )

    def should_publish(self, snapshot: TelemetrySnapshot) -> bool:
        """
        Evaluate rate limit and state deduplication.
        Returns True if snapshot should be broadcast.
        """
        now = self.clock_fn()
        elapsed = now - self._last_publish_time

        # Always enforce max update rate limit
        if elapsed < self.min_interval:
            return False

        # State hash for deduplication
        state_key = (
            f"{snapshot.agent_status}:{snapshot.camera_status}:{snapshot.authentication_state}:"
            f"{snapshot.liveness_state}:{snapshot.decision_state}:{snapshot.face_count}:"
            f"{snapshot.lock_requested}"
        )

        # Publish if state changed OR if 1.0s elapsed (heartbeat sync)
        if state_key != self._last_state_hash or elapsed >= 1.0:
            self._last_state_hash = state_key
            return True

        return False

    def publish_cycle(
        self,
        decision: Optional[DecisionResult],
        recognition: Optional[RecognitionResult],
        liveness: Optional[LivenessResult],
        camera_available: bool,
        uptime_seconds: float,
        last_event: Optional[Dict[str, Any]] = None,
        force: bool = False,
    ) -> Optional[TelemetrySnapshot]:
        """Process and transmit operational snapshot if conditions are met."""
        snapshot = self.create_snapshot(
            decision=decision,
            recognition=recognition,
            liveness=liveness,
            camera_available=camera_available,
            uptime_seconds=uptime_seconds,
            last_event=last_event,
        )
        self._last_snapshot = snapshot

        if force or self.should_publish(snapshot):
            self._last_publish_time = self.clock_fn()
            req = TelemetryPublishRequest(snapshot=snapshot, message_type="SNAPSHOT")
            self._send_payload_async(req)
            return snapshot

        return None

    def publish_event(self, event_data: Dict[str, Any]) -> None:
        """Immediately transmit a transition-level security or lock event."""
        req = TelemetryPublishRequest(event=event_data, message_type="SECURITY_EVENT")
        self._send_payload_async(req)

    def _send_payload_async(self, request_payload: TelemetryPublishRequest) -> None:
        """Send payload in a daemon background thread with short timeout."""
        if not self.enable_network_publish:
            return

        def _do_send():
            try:
                data_bytes = request_payload.model_dump_json().encode("utf-8")
                req = urllib.request.Request(
                    self.api_url,
                    data=data_bytes,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=0.15) as resp:
                    pass
            except (urllib.error.URLError, TimeoutError, OSError):
                # API offline or busy — non-critical, agent proceeds safely
                pass
            except Exception as exc:
                logger.debug(f"Telemetry publish exception: {exc}")

        t = threading.Thread(target=_do_send, daemon=True)
        t.start()
