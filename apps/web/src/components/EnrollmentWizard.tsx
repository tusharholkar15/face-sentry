"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  Shield,
  ShieldCheck,
  Camera,
  Eye,
  CheckCircle2,
  AlertCircle,
  AlertTriangle,
  ScanFace,
  Lock,
  ArrowRight,
  ArrowLeft,
  X,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import {
  startEnrollment,
  fetchEnrollmentStatus,
  cancelEnrollment,
  finalizeEnrollment,
} from "@/lib/api";
import { EnrollmentStatusResponse, TelemetrySnapshot } from "@/types";
import { ConnectionState } from "@/lib/useTelemetry";

export interface EnrollmentWizardProps {
  isOpen: boolean;
  onClose: () => void;
  onEnrollmentCompleted: () => void;
  telemetry: TelemetrySnapshot | null;
  connectionState: ConnectionState;
}

export function EnrollmentWizard({
  isOpen,
  onClose,
  onEnrollmentCompleted,
  telemetry,
  connectionState,
}: EnrollmentWizardProps) {
  const [step, setStep] = useState<number>(1);
  const [enrollStatus, setEnrollStatus] = useState<EnrollmentStatusResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const isAgentOffline = connectionState === "AGENT_OFFLINE" || connectionState === "DISCONNECTED";

  // Polling / WebSocket sync during active capture
  const syncStatus = useCallback(async () => {
    try {
      const res = await fetchEnrollmentStatus();
      setEnrollStatus(res);

      if (res.state === "LIVENESS_CHECK" && step === 5) {
        setStep(7); // Jump to liveness confirmation
      } else if (res.state === "PROCESSING" && step < 8) {
        setStep(8);
      } else if (res.state === "COMPLETED") {
        setStep(9);
      } else if (res.state === "FAILED") {
        setErrorMessage(res.error_message || "Enrollment quality criteria not met.");
      }
    } catch (err) {
      console.debug("Enrollment status polling error:", err);
    }
  }, [step]);

  useEffect(() => {
    if (!isOpen) return;

    if (step >= 5 && step <= 8) {
      const interval = setInterval(syncStatus, 300);
      return () => clearInterval(interval);
    }
  }, [isOpen, step, syncStatus]);

  const handleStartCapture = async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const res = await startEnrollment("default_user", 15);
      setEnrollStatus(res);
      setStep(5); // Enter Capturing step
    } catch (err) {
      setErrorMessage("Failed to start enrollment session. Ensure API and Agent are running.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleCancel = async () => {
    try {
      await cancelEnrollment();
    } catch (err) {
      console.debug("Cancel call error:", err);
    }
    setStep(1);
    setEnrollStatus(null);
    onClose();
  };

  const handleFinalize = async () => {
    setIsLoading(true);
    try {
      const res = await finalizeEnrollment();
      setEnrollStatus(res);
      setStep(9);
      onEnrollmentCompleted();
    } catch (err) {
      setErrorMessage("Failed to finalize biometric template. Please retry.");
    } finally {
      setIsLoading(false);
    }
  };

  if (!isOpen) return null;

  const captured = enrollStatus?.captured_samples ?? 0;
  const required = enrollStatus?.required_samples ?? 15;
  const progressPercent = Math.min(100, Math.round((captured / required) * 100));

  const getGuidanceText = (guidance: string) => {
    switch (guidance) {
      case "LOOK_FORWARD":
        return "Look straight into the camera lens";
      case "MOVE_CLOSER":
        return "Move slightly closer to the webcam";
      case "MOVE_FARTHER":
        return "Step back slightly from the webcam";
      case "TURN_LEFT":
        return "Tilt head slightly to your left";
      case "TURN_RIGHT":
        return "Tilt head slightly to your right";
      case "KEEP_STILL":
        return "Hold still for sharp focal clarity";
      case "IMPROVE_LIGHTING":
        return "Adjust room lighting (avoid shadows)";
      case "MULTIPLE_FACES":
        return "Multiple faces detected — ensure only you are visible";
      case "FACE_NOT_DETECTED":
        return "Position your face inside the center frame";
      case "PERFORM_BLINK":
        return "Blink your eyes naturally to confirm liveness";
      case "GOOD_SAMPLE":
        return "Great position! Capturing samples...";
      default:
        return "Position your face in the camera view";
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4">
      <Card className="w-full max-w-2xl bg-slate-950 border border-cyan-500/30 shadow-2xl shadow-cyan-500/10 overflow-hidden font-sans">
        {/* Wizard Header Bar */}
        <CardHeader className="border-b border-white/10 pb-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="p-2 rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
                <ScanFace className="w-5 h-5" />
              </div>
              <div>
                <CardTitle className="text-lg font-bold text-white">Biometric Face Enrollment</CardTitle>
                <CardDescription className="text-xs">Step {step} of 9 • Local DPAPI Protection</CardDescription>
              </div>
            </div>
            <Button variant="ghost" size="sm" onClick={handleCancel} className="text-slate-400 hover:text-white">
              <X className="w-4 h-4" />
            </Button>
          </div>

          {/* Step Progress Dots */}
          <div className="flex gap-1.5 mt-4">
            {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((s) => (
              <div
                key={s}
                className={`h-1 flex-1 rounded-full transition-all duration-300 ${
                  s === step ? "bg-cyan-400" : s < step ? "bg-emerald-400" : "bg-white/10"
                }`}
              />
            ))}
          </div>
        </CardHeader>

        {/* Wizard Body by Step */}
        <CardContent className="py-6 space-y-6">
          {/* Step 1: Welcome */}
          {step === 1 && (
            <div className="space-y-4 text-center py-4">
              <div className="inline-flex p-4 rounded-full bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
                <Shield className="w-10 h-10 animate-pulse" />
              </div>
              <div className="space-y-2 max-w-md mx-auto">
                <h3 className="text-xl font-bold text-white">Welcome to FaceSentry</h3>
                <p className="text-sm text-slate-400">
                  Register your facial biometric profile to enable seamless on-device authentication and automatic Windows lockouts.
                </p>
              </div>
            </div>
          )}

          {/* Step 2: Privacy */}
          {step === 2 && (
            <div className="space-y-4 py-2">
              <div className="flex items-center gap-3 p-3.5 rounded-xl bg-emerald-950/20 border border-emerald-500/30 text-emerald-400">
                <ShieldCheck className="w-6 h-6 flex-shrink-0" />
                <div className="text-xs space-y-1">
                  <div className="font-bold text-white text-sm">100% On-Device Privacy Guaranteed</div>
                  <p className="text-emerald-300/80">
                    Your photographs and video frames are never stored on disk or transmitted to cloud servers.
                  </p>
                </div>
              </div>

              <div className="space-y-2.5 text-xs text-slate-300">
                <div className="flex items-start gap-2">
                  <CheckCircle2 className="w-4 h-4 text-cyan-400 mt-0.5" />
                  <span>Only mathematical embedding vectors (512-dimensional unit numbers) are retained.</span>
                </div>
                <div className="flex items-start gap-2">
                  <CheckCircle2 className="w-4 h-4 text-cyan-400 mt-0.5" />
                  <span>Encrypted at rest using Windows DPAPI, tied exclusively to your Windows user account.</span>
                </div>
                <div className="flex items-start gap-2">
                  <CheckCircle2 className="w-4 h-4 text-cyan-400 mt-0.5" />
                  <span>Images in memory are purged immediately following template generation.</span>
                </div>
              </div>
            </div>
          )}

          {/* Step 3: Camera Check */}
          {step === 3 && (
            <div className="space-y-4 py-2 text-center">
              <div className="inline-flex p-4 rounded-full bg-slate-900 border border-white/10 text-cyan-400">
                <Camera className="w-8 h-8" />
              </div>
              <div className="space-y-1 max-w-md mx-auto">
                <h4 className="text-base font-bold text-white">Camera & Subsystem Check</h4>
                <p className="text-xs text-slate-400">
                  {isAgentOffline
                    ? "FaceSentry Agent is offline. Start `python -m apps.agent.main` first."
                    : "Camera hardware connected and ready for calibration."}
                </p>
              </div>

              <div className="p-3 rounded-lg bg-slate-900/60 border border-white/5 flex justify-between items-center text-xs font-mono">
                <span className="text-slate-400">Agent Stream:</span>
                <Badge variant={isAgentOffline ? "destructive" : "success"}>
                  {connectionState.replace(/_/g, " ")}
                </Badge>
              </div>
            </div>
          )}

          {/* Step 4: Position Face */}
          {step === 4 && (
            <div className="space-y-4 py-2 text-center">
              <div className="inline-flex p-4 rounded-full bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
                <ScanFace className="w-8 h-8" />
              </div>
              <div className="space-y-1 max-w-md mx-auto">
                <h4 className="text-base font-bold text-white">Position Your Face</h4>
                <p className="text-xs text-slate-400">
                  Center your face in good room lighting, remove heavy sunglasses, and maintain a direct gaze.
                </p>
              </div>
            </div>
          )}

          {/* Step 5: Capture Samples (Live Multi-Sample Flow) */}
          {step === 5 && (
            <div className="space-y-5 py-2">
              {/* Central Target Display with dynamic guidance */}
              <div className="w-full h-48 rounded-xl border border-cyan-500/30 bg-slate-950/80 relative flex flex-col items-center justify-center p-4 text-center overflow-hidden">
                <div className="absolute inset-0 bg-[linear-gradient(to_right,#00f0ff08_1px,transparent_1px),linear-gradient(to_bottom,#00f0ff08_1px,transparent_1px)] bg-[size:20px_20px]" />
                
                {/* HUD Corner Reticles */}
                <div className="absolute top-2 left-2 w-4 h-4 border-t-2 border-l-2 border-cyan-400" />
                <div className="absolute top-2 right-2 w-4 h-4 border-t-2 border-r-2 border-cyan-400" />
                <div className="absolute bottom-2 left-2 w-4 h-4 border-b-2 border-l-2 border-cyan-400" />
                <div className="absolute bottom-2 right-2 w-4 h-4 border-b-2 border-r-2 border-cyan-400" />

                <div className="relative z-10 space-y-2">
                  <div className="inline-flex p-3 rounded-full bg-cyan-500/10 border border-cyan-500/30 text-cyan-400 animate-pulse">
                    <ScanFace className="w-8 h-8" />
                  </div>
                  <div className="text-sm font-bold text-white font-mono">
                    {getGuidanceText(enrollStatus?.guidance || "LOOK_FORWARD")}
                  </div>
                  <Badge variant={enrollStatus?.quality === "GOOD" ? "success" : "warning"}>
                    Quality: {enrollStatus?.quality || "PENDING"}
                  </Badge>
                </div>
              </div>

              {/* Real-time Progress Bar */}
              <div className="space-y-2">
                <div className="flex justify-between text-xs font-mono">
                  <span className="text-slate-400">Capturing Multi-Angle Vectors:</span>
                  <span className="text-cyan-400 font-bold">{captured} / {required} Samples</span>
                </div>
                <div className="w-full bg-slate-900 rounded-full h-2 overflow-hidden border border-white/5">
                  <div
                    className="bg-cyan-400 h-2 transition-all duration-300"
                    style={{ width: `${progressPercent}%` }}
                  />
                </div>
              </div>
            </div>
          )}

          {/* Step 6: Quality Verification */}
          {step === 6 && (
            <div className="space-y-4 py-2 text-center">
              <div className="inline-flex p-4 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400">
                <CheckCircle2 className="w-8 h-8" />
              </div>
              <div className="space-y-1 max-w-md mx-auto">
                <h4 className="text-base font-bold text-white">Sample Quality Verified</h4>
                <p className="text-xs text-slate-400">
                  {required} high-quality feature vectors captured across illumination and pose angles.
                </p>
              </div>
            </div>
          )}

          {/* Step 7: Liveness Confirmation */}
          {step === 7 && (
            <div className="space-y-4 py-2 text-center">
              <div className="inline-flex p-4 rounded-full bg-purple-500/10 border border-purple-500/30 text-purple-400 animate-pulse">
                <Eye className="w-8 h-8" />
              </div>
              <div className="space-y-1 max-w-md mx-auto">
                <h4 className="text-base font-bold text-white">Liveness Confirmation Gate</h4>
                <p className="text-xs text-slate-400">
                  Please blink your eyes naturally or turn your head slightly to confirm active physical presence.
                </p>
              </div>
              <Badge variant={enrollStatus?.liveness_verified ? "success" : "warning"}>
                {enrollStatus?.liveness_verified ? "Liveness Verified" : "Awaiting Natural Blink"}
              </Badge>
            </div>
          )}

          {/* Step 8: Processing & Encryption */}
          {step === 8 && (
            <div className="space-y-4 py-4 text-center">
              <div className="inline-flex p-4 rounded-full bg-cyan-500/10 border border-cyan-500/30 text-cyan-400 animate-spin">
                <RefreshCw className="w-8 h-8" />
              </div>
              <div className="space-y-1 max-w-md mx-auto">
                <h4 className="text-base font-bold text-white">Generating Centroid Template</h4>
                <p className="text-xs text-slate-400">
                  Encrypting reference vector with Windows DPAPI and purging raw video cache...
                </p>
              </div>
            </div>
          )}

          {/* Step 9: Complete */}
          {step === 9 && (
            <div className="space-y-4 py-4 text-center">
              <div className="inline-flex p-4 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 shadow-lg shadow-emerald-500/20">
                <ShieldCheck className="w-10 h-10" />
              </div>
              <div className="space-y-2 max-w-md mx-auto">
                <h3 className="text-xl font-bold text-white">Enrollment Completed!</h3>
                <p className="text-sm text-slate-300">
                  Your biometric profile is now encrypted and active. FaceSentry will now monitor your workstation presence.
                </p>
              </div>
            </div>
          )}

          {/* Error Banner */}
          {errorMessage && (
            <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-300 text-xs flex items-center gap-2">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              <span>{errorMessage}</span>
            </div>
          )}
        </CardContent>

        {/* Wizard Footer Navigation */}
        <CardFooter className="border-t border-white/10 pt-4 flex justify-between">
          {step > 1 && step < 5 ? (
            <Button variant="outline" size="sm" onClick={() => setStep(step - 1)} className="gap-1.5">
              <ArrowLeft className="w-3.5 h-3.5" />
              Back
            </Button>
          ) : (
            <Button variant="ghost" size="sm" onClick={handleCancel}>
              Cancel
            </Button>
          )}

          {step === 1 && (
            <Button size="sm" onClick={() => setStep(2)} className="gap-1.5 bg-cyan-500 hover:bg-cyan-600 text-slate-950 font-bold">
              Get Started
              <ArrowRight className="w-3.5 h-3.5" />
            </Button>
          )}

          {step === 2 && (
            <Button size="sm" onClick={() => setStep(3)} className="gap-1.5 bg-cyan-500 hover:bg-cyan-600 text-slate-950 font-bold">
              I Understand
              <ArrowRight className="w-3.5 h-3.5" />
            </Button>
          )}

          {step === 3 && (
            <Button
              size="sm"
              disabled={isAgentOffline}
              onClick={() => setStep(4)}
              className="gap-1.5 bg-cyan-500 hover:bg-cyan-600 text-slate-950 font-bold"
            >
              Continue
              <ArrowRight className="w-3.5 h-3.5" />
            </Button>
          )}

          {step === 4 && (
            <Button
              size="sm"
              onClick={handleStartCapture}
              disabled={isLoading}
              className="gap-1.5 bg-cyan-500 hover:bg-cyan-600 text-slate-950 font-bold"
            >
              {isLoading ? "Starting..." : "Start Capture"}
              <Camera className="w-3.5 h-3.5" />
            </Button>
          )}

          {step === 7 && (
            <Button
              size="sm"
              onClick={handleFinalize}
              disabled={isLoading || !enrollStatus?.liveness_verified}
              className="gap-1.5 bg-emerald-500 hover:bg-emerald-600 text-slate-950 font-bold"
            >
              {isLoading ? "Finalizing..." : "Finalize Profile"}
              <CheckCircle2 className="w-3.5 h-3.5" />
            </Button>
          )}

          {step === 9 && (
            <Button size="sm" onClick={onClose} className="bg-emerald-500 hover:bg-emerald-600 text-slate-950 font-bold">
              Done & Start Protection
            </Button>
          )}
        </CardFooter>
      </Card>
    </div>
  );
}
