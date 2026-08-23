/**
 * FaceSentry Shared TypeScript Types & Interfaces
 */

export type SystemState =
  | 'UNINITIALIZED'
  | 'IDLE'
  | 'MONITORING_AUTHENTICATED'
  | 'MONITORING_ABSENT'
  | 'MONITORING_UNKNOWN_FACE'
  | 'MONITORING_SPOOF_ATTEMPT'
  | 'LOCKED'
  | 'SNOOZED'
  | 'ENROLLING'
  | 'ERROR';

export type EventType =
  | 'SYSTEM_STARTUP'
  | 'SYSTEM_SHUTDOWN'
  | 'USER_AUTHENTICATED'
  | 'ABSENCE_DETECTED'
  | 'UNKNOWN_FACE_DETECTED'
  | 'SPOOF_DETECTED'
  | 'LOCK_TRIGGERED'
  | 'PIN_SETUP'
  | 'PIN_CHANGED'
  | 'PIN_VERIFY_STARTED'
  | 'PIN_AUTHENTICATED'
  | 'PIN_FAILED'
  | 'PIN_LOCKOUT_STARTED'
  | 'PIN_RECOVERY_STARTED'
  | 'PIN_RECOVERY_EXPIRED'
  | 'BIOMETRIC_REAUTH_REQUIRED'
  | 'ENROLLMENT_COMPLETED'
  | 'CONFIG_UPDATED'
  | 'CAMERA_STATUS_CHANGED'
  | 'BROWSER_PROTECTION_TRIGGERED'
  | 'BROWSER_DETECTED'
  | 'BROWSER_CLOSE_REQUESTED'
  | 'BROWSER_CLOSE_SUCCEEDED'
  | 'BROWSER_CLOSE_FAILED'
  | 'SESSION_CLEANUP_STARTED'
  | 'SESSION_CLEANUP_SUCCEEDED'
  | 'SESSION_CLEANUP_FAILED'
  | 'SESSION_CLEANUP_UNSUPPORTED';

export type LockReason =
  | 'ABSENCE_TIMEOUT'
  | 'UNKNOWN_FACE_TIMEOUT'
  | 'SPOOF_DETECTED'
  | 'MANUAL_LOCK'
  | 'PIN_LOCKOUT'
  | 'CAMERA_DISCONNECTED'
  | 'TAMPER_DETECTED';

export type BrowserProtectionMode =
  | 'DISABLED'
  | 'CLOSE_BROWSER'
  | 'CLOSE_BROWSER_AND_CLEAR_SESSION_COOKIES';

export interface BrowserProtectionConfig {
  enabled: boolean;
  mode: BrowserProtectionMode;
  close_timeout_seconds: number;
}

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  timestamp: string;
  database: string;
  agent_status: string;
}

export interface SystemStatusResponse {
  state: SystemState;
  profile_enrolled: boolean;
  active_camera_index: number;
  is_snoozed: boolean;
  snooze_remaining_seconds: number;
  uptime_seconds: number;
  last_event: string | null;
}

export interface HardwareConfig {
  camera_index: number;
  capture_resolution: [number, number];
  target_fps: number;
  backend_api: string;
}

export interface PolicyConfig {
  absence_timeout_seconds: number;
  unknown_face_timeout_seconds: number;
  spoof_lock_timeout_seconds: number;
  similarity_threshold: number;
  liveness_threshold: number;
  lock_on_absence: boolean;
  lock_on_unknown_face: boolean;
  lock_on_spoof: boolean;
}

export interface SystemConfig {
  hardware: HardwareConfig;
  policies: PolicyConfig;
  browser_protection: BrowserProtectionConfig;
}

export interface SecurityEvent {
  id: number;
  timestamp: string;
  event_type: EventType;
  confidence: number | null;
  liveness_score: number | null;
  action_taken: string;
  metadata: Record<string, unknown>;
}

// ==========================================
// Real-Time Telemetry Types (Phase 6)
// ==========================================

export type TelemetryMessageType =
  | 'AGENT_STATUS'
  | 'CAMERA_STATUS'
  | 'AUTH_STATUS'
  | 'LIVENESS_STATUS'
  | 'DECISION_STATUS'
  | 'LOCK_STATUS'
  | 'SECURITY_EVENT'
  | 'HEARTBEAT'
  | 'SNAPSHOT'
  | 'ENROLLMENT_STARTED'
  | 'ENROLLMENT_PROGRESS'
  | 'ENROLLMENT_GUIDANCE'
  | 'ENROLLMENT_QUALITY'
  | 'ENROLLMENT_COMPLETED'
  | 'ENROLLMENT_FAILED'
  | 'ENROLLMENT_CANCELLED'
  | 'PIN_AUTHENTICATED'
  | 'PIN_FAILED'
  | 'PIN_LOCKOUT_STARTED'
  | 'PIN_RECOVERY_STARTED'
  | 'PIN_RECOVERY_EXPIRED'
  | 'ERROR'
  | 'PONG';

export interface TelemetrySnapshot {
  timestamp: number;
  agent_status: 'RUNNING' | 'IDLE' | 'STOPPED' | 'ERROR';
  camera_status: 'CONNECTED' | 'DISCONNECTED' | 'ERROR';
  authentication_state: 'AUTHENTICATED' | 'UNRECOGNIZED' | 'NO_FACE' | 'INITIALIZING' | 'AUTHENTICATING' | 'RECOVERY';
  recognition_similarity: number;
  liveness_state: 'INITIALIZING' | 'OBSERVING' | 'BLINK_DETECTED' | 'HEAD_MOVEMENT_DETECTED' | 'VERIFIED' | 'FAILED' | 'TIMEOUT';
  liveness_verified: boolean;
  liveness_confidence: number;
  face_detected: boolean;
  face_count: number;
  absence_duration: number;
  stranger_duration: number;
  spoof_duration: number;
  decision_state: string;
  lock_requested: boolean;
  last_security_event: {
    event_type: string;
    reason: string;
    timestamp: number;
    details?: Record<string, unknown>;
  } | null;
  system_uptime: number;
  bounding_box?: [number, number, number, number] | null;
}

export interface WebSocketMessage<T = Record<string, unknown>> {
  type: TelemetryMessageType;
  timestamp: number;
  schema_version: string;
  payload: T;
}

// ==========================================
// Enrollment Types (Phase 7)
// ==========================================

export type EnrollmentState =
  | 'IDLE'
  | 'STARTING'
  | 'CAPTURING'
  | 'QUALITY_CHECK'
  | 'PROCESSING'
  | 'LIVENESS_CHECK'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED';

export type EnrollmentGuidance =
  | 'LOOK_FORWARD'
  | 'MOVE_CLOSER'
  | 'MOVE_FARTHER'
  | 'TURN_LEFT'
  | 'TURN_RIGHT'
  | 'KEEP_STILL'
  | 'IMPROVE_LIGHTING'
  | 'MULTIPLE_FACES'
  | 'FACE_NOT_DETECTED'
  | 'GOOD_SAMPLE'
  | 'PERFORM_BLINK'
  | 'READY';

export interface EnrollmentStatusResponse {
  state: EnrollmentState;
  progress: number;
  captured_samples: number;
  required_samples: number;
  quality: string;
  guidance: EnrollmentGuidance;
  liveness_verified: boolean;
  error_message: string | null;
  is_complete: boolean;
}

// ==========================================
// Secure PIN Fallback Types (Phase 8)
// ==========================================

export interface PinStatusResponse {
  is_configured: boolean;
  is_locked: boolean;
  attempts_remaining: number;
  locked_until: number | null;
  in_recovery: boolean;
  recovery_until: number | null;
  reason: string | null;
}

export interface PinVerifyResponse {
  authenticated: boolean;
  in_recovery: boolean;
  recovery_until: number | null;
  attempts_remaining: number;
  is_locked: boolean;
  locked_until: number | null;
  reason: string | null;
}
