"use client";

import React, { useState, useEffect } from "react";
import {
  Key,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Lock,
  Unlock,
  AlertTriangle,
  CheckCircle2,
  X,
  Clock,
} from "lucide-react";
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import {
  fetchPinStatus,
  setupPin,
  changePin,
  verifyPin,
} from "@/lib/api";
import { PinStatusResponse, PinVerifyResponse } from "@/types";

export interface PinModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void;
  initialMode?: "VERIFY" | "SETUP" | "CHANGE";
}

export function PinModal({
  isOpen,
  onClose,
  onSuccess,
  initialMode = "VERIFY",
}: PinModalProps) {
  const [mode, setMode] = useState<"VERIFY" | "SETUP" | "CHANGE">(initialMode);
  const [pinStatus, setPinStatus] = useState<PinStatusResponse | null>(null);

  // Form Inputs
  const [currentPin, setCurrentPin] = useState<string>("");
  const [newPin, setNewPin] = useState<string>("");
  const [confirmPin, setConfirmPin] = useState<string>("");

  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;

    // Reset inputs
    setCurrentPin("");
    setNewPin("");
    setConfirmPin("");
    setErrorMessage(null);
    setSuccessMessage(null);
    setMode(initialMode);

    loadStatus();
  }, [isOpen, initialMode]);

  const loadStatus = async () => {
    try {
      const status = await fetchPinStatus();
      setPinStatus(status);
      if (!status.is_configured && mode === "VERIFY") {
        setMode("SETUP");
      }
    } catch (err) {
      console.debug("PIN status error:", err);
    }
  };

  const handleClose = () => {
    // Clear inputs on close for privacy
    setCurrentPin("");
    setNewPin("");
    setConfirmPin("");
    onClose();
  };

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    try {
      const res: PinVerifyResponse = await verifyPin(currentPin);
      setCurrentPin(""); // Wipe volatile state

      if (res.authenticated) {
        setSuccessMessage("Emergency PIN authenticated! Temporary recovery mode activated.");
        loadStatus();
        if (onSuccess) onSuccess();
        setTimeout(() => {
          handleClose();
        }, 1200);
      } else {
        setErrorMessage(res.reason || "Invalid PIN entered.");
        loadStatus();
      }
    } catch (err: any) {
      setErrorMessage(err.message || "PIN verification failed.");
      loadStatus();
    } finally {
      setIsLoading(false);
    }
  };

  const handleSetup = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    if (newPin !== confirmPin) {
      setErrorMessage("New PIN and confirmation PIN do not match.");
      setIsLoading(false);
      return;
    }

    try {
      await setupPin(newPin, confirmPin);
      setNewPin("");
      setConfirmPin("");
      setSuccessMessage("PIN configured successfully!");
      loadStatus();
      setTimeout(() => {
        setMode("VERIFY");
      }, 1000);
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to setup PIN.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleChange = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    if (newPin !== confirmPin) {
      setErrorMessage("New PIN and confirmation PIN do not match.");
      setIsLoading(false);
      return;
    }

    try {
      await changePin(currentPin, newPin, confirmPin);
      setCurrentPin("");
      setNewPin("");
      setConfirmPin("");
      setSuccessMessage("PIN changed successfully!");
      loadStatus();
      setTimeout(() => {
        setMode("VERIFY");
      }, 1000);
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to change PIN.");
    } finally {
      setIsLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4">
      <Card className="w-full max-w-md bg-slate-950 border border-cyan-500/30 shadow-2xl shadow-cyan-500/10 overflow-hidden font-sans">
        <CardHeader className="border-b border-white/10 pb-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="p-2 rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
                <Key className="w-5 h-5" />
              </div>
              <div>
                <CardTitle className="text-lg font-bold text-white">
                  {mode === "SETUP" ? "Setup Emergency PIN" : mode === "CHANGE" ? "Change Fallback PIN" : "Emergency PIN Fallback"}
                </CardTitle>
                <CardDescription className="text-xs">
                  {mode === "SETUP"
                    ? "Configure an emergency PIN fallback"
                    : mode === "CHANGE"
                    ? "Update your existing PIN credentials"
                    : "Temporary unlock recovery (60s)"}
                </CardDescription>
              </div>
            </div>
            <Button variant="ghost" size="sm" onClick={handleClose} className="text-slate-400 hover:text-white">
              <X className="w-4 h-4" />
            </Button>
          </div>

          {/* Mode Switch Tabs */}
          {pinStatus?.is_configured && (
            <div className="flex gap-2 mt-3 pt-3 border-t border-white/5">
              <button
                type="button"
                onClick={() => { setMode("VERIFY"); setErrorMessage(null); setSuccessMessage(null); }}
                className={`text-xs px-3 py-1.5 rounded-lg font-medium transition-all ${
                  mode === "VERIFY" ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Verify PIN
              </button>
              <button
                type="button"
                onClick={() => { setMode("CHANGE"); setErrorMessage(null); setSuccessMessage(null); }}
                className={`text-xs px-3 py-1.5 rounded-lg font-medium transition-all ${
                  mode === "CHANGE" ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Change PIN
              </button>
            </div>
          )}
        </CardHeader>

        <CardContent className="py-5 space-y-4">
          {/* Recovery Status Banner */}
          {pinStatus?.in_recovery && (
            <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs flex items-center justify-between">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-emerald-400 flex-shrink-0" />
                <span>Emergency recovery mode active</span>
              </div>
              <Badge variant="success">Active</Badge>
            </div>
          )}

          {/* Lockout Warning Banner */}
          {pinStatus?.is_locked && (
            <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-300 text-xs flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 text-red-400 flex-shrink-0" />
              <div>
                <div className="font-bold">PIN Subsystem Temporarily Locked</div>
                <div>Multiple failed attempts recorded. Please wait for lockout cooldown.</div>
              </div>
            </div>
          )}

          {/* 1. Mode: VERIFY */}
          {mode === "VERIFY" && (
            <form onSubmit={handleVerify} className="space-y-4">
              <div className="space-y-2">
                <label className="text-xs text-slate-300 font-medium flex justify-between">
                  <span>Enter Fallback PIN:</span>
                  <span className="text-slate-500 font-mono text-[11px]">
                    Attempts: {pinStatus?.attempts_remaining ?? 5} / 5
                  </span>
                </label>
                <Input
                  type="password"
                  inputMode="numeric"
                  placeholder="••••"
                  value={currentPin}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setCurrentPin(e.target.value)}
                  disabled={isLoading || pinStatus?.is_locked}
                  autoFocus
                  maxLength={12}
                  className="font-mono text-center tracking-widest text-lg bg-slate-900 border-white/10"
                />
              </div>

              <p className="text-[11px] text-slate-400 leading-relaxed">
                Emergency PIN provides temporary 60-second recovery for camera or lighting issues. Standard continuous biometric authentication resumes automatically afterwards.
              </p>

              <Button
                type="submit"
                disabled={isLoading || !currentPin || pinStatus?.is_locked}
                className="w-full bg-cyan-500 hover:bg-cyan-600 text-slate-950 font-bold gap-2"
              >
                <Unlock className="w-4 h-4" />
                {isLoading ? "Verifying..." : "Authenticate Emergency PIN"}
              </Button>
            </form>
          )}

          {/* 2. Mode: SETUP */}
          {mode === "SETUP" && (
            <form onSubmit={handleSetup} className="space-y-4">
              <div className="space-y-2">
                <label className="text-xs text-slate-300 font-medium">Create Numeric PIN (4-12 digits):</label>
                <Input
                  type="password"
                  inputMode="numeric"
                  placeholder="New PIN"
                  value={newPin}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewPin(e.target.value)}
                  disabled={isLoading}
                  maxLength={12}
                  className="font-mono text-center tracking-widest text-lg bg-slate-900 border-white/10"
                />
              </div>

              <div className="space-y-2">
                <label className="text-xs text-slate-300 font-medium">Confirm PIN:</label>
                <Input
                  type="password"
                  inputMode="numeric"
                  placeholder="Confirm PIN"
                  value={confirmPin}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setConfirmPin(e.target.value)}
                  disabled={isLoading}
                  maxLength={12}
                  className="font-mono text-center tracking-widest text-lg bg-slate-900 border-white/10"
                />
              </div>

              <p className="text-[11px] text-slate-400 leading-relaxed">
                PIN is hashed locally with salted PBKDF2-HMAC-SHA256. It is never stored in plaintext or transmitted off this device.
              </p>

              <Button
                type="submit"
                disabled={isLoading || !newPin || !confirmPin}
                className="w-full bg-cyan-500 hover:bg-cyan-600 text-slate-950 font-bold gap-2"
              >
                <Lock className="w-4 h-4" />
                {isLoading ? "Saving..." : "Configure Emergency PIN"}
              </Button>
            </form>
          )}

          {/* 3. Mode: CHANGE */}
          {mode === "CHANGE" && (
            <form onSubmit={handleChange} className="space-y-4">
              <div className="space-y-2">
                <label className="text-xs text-slate-300 font-medium">Current PIN:</label>
                <Input
                  type="password"
                  inputMode="numeric"
                  placeholder="Current PIN"
                  value={currentPin}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setCurrentPin(e.target.value)}
                  disabled={isLoading}
                  maxLength={12}
                  className="font-mono text-center tracking-widest text-lg bg-slate-900 border-white/10"
                />
              </div>

              <div className="space-y-2">
                <label className="text-xs text-slate-300 font-medium">New PIN (4-12 digits):</label>
                <Input
                  type="password"
                  inputMode="numeric"
                  placeholder="New PIN"
                  value={newPin}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewPin(e.target.value)}
                  disabled={isLoading}
                  maxLength={12}
                  className="font-mono text-center tracking-widest text-lg bg-slate-900 border-white/10"
                />
              </div>

              <div className="space-y-2">
                <label className="text-xs text-slate-300 font-medium">Confirm New PIN:</label>
                <Input
                  type="password"
                  inputMode="numeric"
                  placeholder="Confirm New PIN"
                  value={confirmPin}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setConfirmPin(e.target.value)}
                  disabled={isLoading}
                  maxLength={12}
                  className="font-mono text-center tracking-widest text-lg bg-slate-900 border-white/10"
                />
              </div>

              <Button
                type="submit"
                disabled={isLoading || !currentPin || !newPin || !confirmPin}
                className="w-full bg-cyan-500 hover:bg-cyan-600 text-slate-950 font-bold gap-2"
              >
                <Lock className="w-4 h-4" />
                {isLoading ? "Updating..." : "Update PIN"}
              </Button>
            </form>
          )}

          {/* Success Banner */}
          {successMessage && (
            <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
              <span>{successMessage}</span>
            </div>
          )}

          {/* Error Banner */}
          {errorMessage && (
            <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-300 text-xs flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 flex-shrink-0" />
              <span>{errorMessage}</span>
            </div>
          )}
        </CardContent>

        <CardFooter className="border-t border-white/10 pt-3 flex justify-between text-xs text-slate-500">
          <span>FaceSentry PIN Module</span>
          <span>Constant-time HMAC Verification</span>
        </CardFooter>
      </Card>
    </div>
  );
}
