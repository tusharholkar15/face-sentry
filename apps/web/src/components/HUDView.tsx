"use client";

import React from "react";
import {
  Camera,
  Lock,
  Eye,
  CheckCircle2,
  AlertCircle,
  Clock,
  ShieldCheck,
  ShieldAlert,
  AlertTriangle,
  UserCheck,
  UserX,
  ScanFace,
  Activity,
  Radio,
} from "lucide-react";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { SystemStatusResponse, SystemConfig, TelemetrySnapshot } from "@/types";
import { ConnectionState } from "@/lib/useTelemetry";

interface HUDViewProps {
  status: SystemStatusResponse | null;
  config: SystemConfig | null;
  telemetry: TelemetrySnapshot | null;
  connectionState: ConnectionState;
  isStale: boolean;
  onOpenEnrollment?: () => void;
}

export function HUDView({
  status,
  config,
  telemetry,
  connectionState,
  isStale,
  onOpenEnrollment,
}: HUDViewProps) {
  const profileEnrolled = status?.profile_enrolled ?? false;
  const isAgentOffline = connectionState === "AGENT_OFFLINE" || connectionState === "DISCONNECTED" || isStale;
  const isCameraOffline = telemetry?.camera_status === "DISCONNECTED";

  // 1. Determine System Protection State
  let protectionState: "Protected" | "Warning" | "Lock Pending" | "Locked" | "Agent Offline" | "Camera Offline" = "Protected";
  let protectionVariant: "success" | "warning" | "destructive" | "secondary" = "success";

  if (isAgentOffline) {
    protectionState = "Agent Offline";
    protectionVariant = "destructive";
  } else if (isCameraOffline) {
    protectionState = "Camera Offline";
    protectionVariant = "destructive";
  } else if (telemetry?.decision_state === "LOCKED_ACTION_DISPATCHED") {
    protectionState = "Locked";
    protectionVariant = "destructive";
  } else if (telemetry?.decision_state === "LOCK_PENDING" || telemetry?.lock_requested) {
    protectionState = "Lock Pending";
    protectionVariant = "destructive";
  } else if (
    telemetry?.decision_state === "ABSENCE_COUNTDOWN" ||
    telemetry?.decision_state === "STRANGER_COUNTDOWN" ||
    telemetry?.decision_state === "SPOOF_ALERT" ||
    telemetry?.decision_state === "LIVENESS_FAILURE"
  ) {
    protectionState = "Warning";
    protectionVariant = "warning";
  } else if (telemetry?.decision_state === "AUTHENTICATED_PRESENT") {
    protectionState = "Protected";
    protectionVariant = "success";
  }

  // 2. Determine Authentication State
  let authLabel = "Authenticating";
  let authVariant: "success" | "warning" | "destructive" | "secondary" = "secondary";
  if (isAgentOffline) {
    authLabel = "Offline";
    authVariant = "secondary";
  } else if (telemetry?.authentication_state === "AUTHENTICATED") {
    authLabel = "Recognized";
    authVariant = "success";
  } else if (telemetry?.authentication_state === "UNRECOGNIZED") {
    authLabel = "Unknown Face";
    authVariant = "warning";
  } else if (telemetry?.authentication_state === "NO_FACE") {
    authLabel = "No Face";
    authVariant = "secondary";
  }

  // 3. Determine Liveness State
  let livenessLabel = "Observing";
  let livenessVariant: "success" | "warning" | "destructive" | "secondary" = "secondary";
  if (isAgentOffline) {
    livenessLabel = "Offline";
    livenessVariant = "secondary";
  } else if (telemetry?.liveness_verified) {
    livenessLabel = "Verified";
    livenessVariant = "success";
  } else if (telemetry?.liveness_state === "BLINK_DETECTED") {
    livenessLabel = "Blink Detected";
    livenessVariant = "warning";
  } else if (telemetry?.liveness_state === "HEAD_MOVEMENT_DETECTED") {
    livenessLabel = "Movement Detected";
    livenessVariant = "warning";
  } else if (telemetry?.liveness_state === "FAILED" || telemetry?.liveness_state === "TIMEOUT") {
    livenessLabel = "Failed / Timeout";
    livenessVariant = "destructive";
  }

  const absenceCountdown = Math.max(
    0,
    (config?.policies.absence_timeout_seconds ?? 10) - (telemetry?.absence_duration ?? 0)
  );
  const strangerCountdown = Math.max(
    0,
    (config?.policies.unknown_face_timeout_seconds ?? 3) - (telemetry?.stranger_duration ?? 0)
  );
  const spoofCountdown = Math.max(
    0,
    (config?.policies.spoof_lock_timeout_seconds ?? 3) - (telemetry?.spoof_duration ?? 0)
  );

  const uptime = telemetry?.system_uptime ?? (status?.uptime_seconds ?? 0);

  return (
    <div className="space-y-6">
      {/* Top Banner: Real-Time Protection State */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* System Protection Card */}
        <Card className={`border ${protectionVariant === "success" ? "border-emerald-500/30 bg-emerald-950/20" : protectionVariant === "warning" ? "border-amber-500/30 bg-amber-950/20" : "border-red-500/30 bg-red-950/20"}`}>
          <CardContent className="p-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className={`p-2.5 rounded-xl ${protectionVariant === "success" ? "bg-emerald-500/20 text-emerald-400" : protectionVariant === "warning" ? "bg-amber-500/20 text-amber-400" : "bg-red-500/20 text-red-400"}`}>
                {protectionVariant === "success" ? <ShieldCheck className="w-6 h-6" /> : protectionVariant === "warning" ? <AlertTriangle className="w-6 h-6" /> : <ShieldAlert className="w-6 h-6" />}
              </div>
              <div>
                <div className="text-xs text-slate-400 font-medium uppercase tracking-wider">System Protection</div>
                <div className="text-lg font-bold text-white mt-0.5">{protectionState}</div>
              </div>
            </div>
            <Badge variant={protectionVariant}>{protectionState}</Badge>
          </CardContent>
        </Card>

        {/* Biometric Authentication Status */}
        <Card className="border border-white/5 bg-slate-900/60">
          <CardContent className="p-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-xl bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                {authLabel === "Recognized" ? <UserCheck className="w-6 h-6" /> : authLabel === "Unknown Face" ? <UserX className="w-6 h-6" /> : <ScanFace className="w-6 h-6" />}
              </div>
              <div>
                <div className="text-xs text-slate-400 font-medium uppercase tracking-wider">Authentication</div>
                <div className="text-lg font-bold text-white mt-0.5">{authLabel}</div>
              </div>
            </div>
            <div className="text-right font-mono">
              <Badge variant={authVariant}>{authLabel}</Badge>
              {telemetry && telemetry.face_detected && (
                <div className="text-[11px] text-slate-400 mt-1">
                  Match: {(telemetry.recognition_similarity * 100).toFixed(0)}%
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Liveness Verification Status */}
        <Card className="border border-white/5 bg-slate-900/60">
          <CardContent className="p-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-xl bg-purple-500/10 text-purple-400 border border-purple-500/20">
                <Eye className="w-6 h-6" />
              </div>
              <div>
                <div className="text-xs text-slate-400 font-medium uppercase tracking-wider">Liveness Engine</div>
                <div className="text-lg font-bold text-white mt-0.5">{livenessLabel}</div>
              </div>
            </div>
            <Badge variant={livenessVariant}>{livenessLabel}</Badge>
          </CardContent>
        </Card>
      </div>

      {/* Main HUD & Counters Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Visual HUD Container */}
        <Card className="lg:col-span-2 relative overflow-hidden flex flex-col justify-between min-h-[380px]">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>
                <Camera className="w-5 h-5 text-cyan-400" />
                Live Camera & Spatial Tracking HUD
              </CardTitle>
              <div className="flex items-center gap-2">
                {isStale && (
                  <Badge variant="destructive" className="animate-pulse">
                    STALE DATA
                  </Badge>
                )}
                <Badge variant={isCameraOffline ? "destructive" : "default"}>
                  {isCameraOffline ? "Camera Disconnected" : `Camera ${status?.active_camera_index ?? 0}`}
                </Badge>
              </div>
            </div>
            <CardDescription>
              Continuous privacy-preserving local biometric analysis stream
            </CardDescription>
          </CardHeader>

          <CardContent className="flex-1 flex flex-col items-center justify-center">
            <div className="w-full h-72 rounded-lg border border-cyan-500/20 bg-slate-950/80 relative flex flex-col items-center justify-center p-6 text-center overflow-hidden">
              {/* Cyber Grid Background */}
              <div className="absolute inset-0 bg-[linear-gradient(to_right,#00f0ff08_1px,transparent_1px),linear-gradient(to_bottom,#00f0ff08_1px,transparent_1px)] bg-[size:24px_24px]" />

              {/* Corner Reticles */}
              <div className="absolute top-3 left-3 w-5 h-5 border-t-2 border-l-2 border-cyan-400" />
              <div className="absolute top-3 right-3 w-5 h-5 border-t-2 border-r-2 border-cyan-400" />
              <div className="absolute bottom-3 left-3 w-5 h-5 border-b-2 border-l-2 border-cyan-400" />
              <div className="absolute bottom-3 right-3 w-5 h-5 border-b-2 border-r-2 border-cyan-400" />

              {/* Central Target Display */}
              <div className="relative z-10 space-y-3">
                <div className={`inline-flex p-4 rounded-full border ${telemetry?.face_detected ? "bg-cyan-500/10 border-cyan-400 text-cyan-400 animate-pulse" : "bg-slate-900 border-white/10 text-slate-500"}`}>
                  <ScanFace className="w-10 h-10" />
                </div>
                <div className="space-y-1">
                  <h4 className="text-base font-bold text-white font-mono">
                    {isAgentOffline
                      ? "AGENT OFFLINE / AWAITING STREAM"
                      : telemetry?.face_detected
                      ? `${telemetry.face_count} Face(s) Detected • ${authLabel}`
                      : "No Face Detected in Camera ROI"}
                  </h4>
                  <p className="text-xs text-slate-400 max-w-md mx-auto">
                    {isAgentOffline
                      ? "Start FaceSentry agent via `python -m apps.agent.main` to stream live presence."
                      : telemetry?.decision_state.replace(/_/g, " ")}
                  </p>
                </div>
              </div>

              {/* Bottom HUD Metadata */}
              <div className="absolute bottom-3 left-4 right-4 flex justify-between text-[11px] font-mono text-cyan-400/80 border-t border-white/5 pt-2">
                <span>POLICY: {telemetry?.decision_state || "READY"}</span>
                <span>FACES: {telemetry?.face_count ?? 0}</span>
                <span>LIVENESS CONF: {telemetry ? `${(telemetry.liveness_confidence * 100).toFixed(0)}%` : "N/A"}</span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Presence Countdown Timers & System Info */}
        <div className="space-y-6">
          {/* Active Policy Countdowns */}
          <Card>
            <CardHeader>
              <CardTitle>
                <Clock className="w-5 h-5 text-cyan-400" />
                Presence Countdowns
              </CardTitle>
              <CardDescription>Real-time policy lock threshold timers</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 text-sm font-sans">
              {/* Absence Timer */}
              <div className="space-y-1.5 py-2 border-b border-white/5">
                <div className="flex justify-between items-center text-xs">
                  <span className="text-slate-400 flex items-center gap-1.5">
                    <Clock className="w-3.5 h-3.5 text-slate-500" />
                    Absence Lockout
                  </span>
                  <span className={`font-mono font-bold ${(telemetry?.absence_duration ?? 0) > 0 ? "text-amber-400" : "text-slate-400"}`}>
                    {(telemetry?.absence_duration ?? 0) > 0 ? `${absenceCountdown.toFixed(1)}s remaining` : `${config?.policies.absence_timeout_seconds ?? 10}s (Idle)`}
                  </span>
                </div>
                <div className="w-full bg-slate-900 rounded-full h-1.5 overflow-hidden">
                  <div
                    className="bg-amber-400 h-1.5 transition-all duration-200"
                    style={{
                      width: `${Math.min(100, ((telemetry?.absence_duration ?? 0) / (config?.policies.absence_timeout_seconds ?? 10)) * 100)}%`,
                    }}
                  />
                </div>
              </div>

              {/* Stranger Timer */}
              <div className="space-y-1.5 py-2 border-b border-white/5">
                <div className="flex justify-between items-center text-xs">
                  <span className="text-slate-400 flex items-center gap-1.5">
                    <AlertCircle className="w-3.5 h-3.5 text-red-400" />
                    Stranger Lockout
                  </span>
                  <span className={`font-mono font-bold ${(telemetry?.stranger_duration ?? 0) > 0 ? "text-red-400" : "text-slate-400"}`}>
                    {(telemetry?.stranger_duration ?? 0) > 0 ? `${strangerCountdown.toFixed(1)}s remaining` : `${config?.policies.unknown_face_timeout_seconds ?? 3}s (Idle)`}
                  </span>
                </div>
                <div className="w-full bg-slate-900 rounded-full h-1.5 overflow-hidden">
                  <div
                    className="bg-red-400 h-1.5 transition-all duration-200"
                    style={{
                      width: `${Math.min(100, ((telemetry?.stranger_duration ?? 0) / (config?.policies.unknown_face_timeout_seconds ?? 3)) * 100)}%`,
                    }}
                  />
                </div>
              </div>

              {/* Spoof Timer */}
              <div className="space-y-1.5 py-2">
                <div className="flex justify-between items-center text-xs">
                  <span className="text-slate-400 flex items-center gap-1.5">
                    <Lock className="w-3.5 h-3.5 text-purple-400" />
                    Spoof Alert Lockout
                  </span>
                  <span className={`font-mono font-bold ${(telemetry?.spoof_duration ?? 0) > 0 ? "text-purple-400" : "text-slate-400"}`}>
                    {(telemetry?.spoof_duration ?? 0) > 0 ? `${spoofCountdown.toFixed(1)}s remaining` : `${config?.policies.spoof_lock_timeout_seconds ?? 3}s (Idle)`}
                  </span>
                </div>
                <div className="w-full bg-slate-900 rounded-full h-1.5 overflow-hidden">
                  <div
                    className="bg-purple-400 h-1.5 transition-all duration-200"
                    style={{
                      width: `${Math.min(100, ((telemetry?.spoof_duration ?? 0) / (config?.policies.spoof_lock_timeout_seconds ?? 3)) * 100)}%`,
                    }}
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* System Telemetry & Uptime Card */}
          <Card>
            <CardHeader>
              <CardTitle>
                <Activity className="w-5 h-5 text-cyan-400" />
                Live Telemetry
              </CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-2 gap-3 text-xs">
              <div className="bg-slate-950/60 p-3 rounded-lg border border-white/5 font-sans">
                <div className="text-slate-400 uppercase text-[10px] tracking-wider">Uptime</div>
                <div className="text-base font-mono font-bold text-white mt-1">
                  {uptime > 60 ? `${Math.floor(uptime / 60)}m ${Math.floor(uptime % 60)}s` : `${Math.floor(uptime)}s`}
                </div>
              </div>

              <div className="bg-slate-950/60 p-3 rounded-lg border border-white/5 font-sans">
                <div className="text-slate-400 uppercase text-[10px] tracking-wider">Profile</div>
                <div className="text-sm font-semibold mt-1">
                  {profileEnrolled ? <span className="text-emerald-400">Enrolled</span> : <span className="text-slate-400">Not Enrolled</span>}
                </div>
              </div>

              <div className="bg-slate-950/60 p-3 rounded-lg border border-white/5 font-sans col-span-2">
                <div className="text-slate-400 uppercase text-[10px] tracking-wider">Last Event</div>
                <div className="text-xs font-mono text-cyan-300 truncate mt-1">
                  {telemetry?.last_security_event?.reason || status?.last_event || "System nominal"}
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
