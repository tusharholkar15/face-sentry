"use client";

import React, { useState } from "react";
import { Settings2, Save, Check } from "lucide-react";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { SystemConfig } from "@/types";
import { updateSystemConfig } from "@/lib/api";
import { BrowserProtectionMode } from "@/types";

interface ConfigPanelProps {
  initialConfig: SystemConfig | null;
  onConfigUpdated: (newConfig: SystemConfig) => void;
}

export function ConfigPanel({ initialConfig, onConfigUpdated }: ConfigPanelProps) {
  const [absenceTimeout, setAbsenceTimeout] = useState(
    initialConfig?.policies.absence_timeout_seconds ?? 10
  );
  const [unknownTimeout, setUnknownTimeout] = useState(
    initialConfig?.policies.unknown_face_timeout_seconds ?? 5
  );
  const [similarityThreshold, setSimilarityThreshold] = useState(
    initialConfig?.policies.similarity_threshold ?? 0.65
  );
  const [targetFps, setTargetFps] = useState(
    initialConfig?.hardware.target_fps ?? 15
  );
  
  // Browser Protection State
  const [bpEnabled, setBpEnabled] = useState(
    initialConfig?.browser_protection?.enabled ?? false
  );
  const [bpMode, setBpMode] = useState<BrowserProtectionMode>(
    initialConfig?.browser_protection?.mode ?? "DISABLED"
  );
  const [bpTimeout, setBpTimeout] = useState(
    initialConfig?.browser_protection?.close_timeout_seconds ?? 5
  );

  const [isSaving, setIsSaving] = useState(false);
  const [savedSuccess, setSavedSuccess] = useState(false);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!initialConfig) return;

    setIsSaving(true);
    setSavedSuccess(false);

    try {
      const updated: SystemConfig = {
        hardware: {
          ...initialConfig.hardware,
          target_fps: Number(targetFps),
        },
        policies: {
          ...initialConfig.policies,
          absence_timeout_seconds: Number(absenceTimeout),
          unknown_face_timeout_seconds: Number(unknownTimeout),
          similarity_threshold: Number(similarityThreshold),
        },
        browser_protection: {
          enabled: bpEnabled,
          mode: bpMode,
          close_timeout_seconds: Number(bpTimeout),
        },
      };

      const result = await updateSystemConfig(updated);
      onConfigUpdated(result);
      setSavedSuccess(true);
      setTimeout(() => setSavedSuccess(false), 3000);
    } catch (err) {
      console.error("Failed to save config:", err);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <Settings2 className="w-5 h-5 text-cyan-400" />
          Policy & Hardware Controls
        </CardTitle>
        <CardDescription>
          Fine-tune timeouts, sensitivity cutoffs, and video ingestion performance
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSave} className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Absence Timeout */}
            <div className="space-y-2">
              <div className="flex justify-between">
                <label className="text-sm font-medium text-slate-300">Absence Timeout</label>
                <span className="text-sm font-mono text-cyan-400">{absenceTimeout}s</span>
              </div>
              <input
                type="range"
                min="3"
                max="60"
                value={absenceTimeout}
                onChange={(e) => setAbsenceTimeout(Number(e.target.value))}
                className="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-cyan-400"
              />
              <p className="text-xs text-slate-500">Seconds before locking when no face is visible</p>
            </div>

            {/* Unknown Face Timeout */}
            <div className="space-y-2">
              <div className="flex justify-between">
                <label className="text-sm font-medium text-slate-300">Stranger Timeout</label>
                <span className="text-sm font-mono text-amber-400">{unknownTimeout}s</span>
              </div>
              <input
                type="range"
                min="1"
                max="30"
                value={unknownTimeout}
                onChange={(e) => setUnknownTimeout(Number(e.target.value))}
                className="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-amber-400"
              />
              <p className="text-xs text-slate-500">Seconds allowed for unrecognized faces before locking</p>
            </div>

            {/* Similarity Match Threshold */}
            <div className="space-y-2">
              <div className="flex justify-between">
                <label className="text-sm font-medium text-slate-300">Similarity Cutoff</label>
                <span className="text-sm font-mono text-emerald-400">
                  {(similarityThreshold * 100).toFixed(0)}%
                </span>
              </div>
              <input
                type="range"
                min="0.40"
                max="0.90"
                step="0.05"
                value={similarityThreshold}
                onChange={(e) => setSimilarityThreshold(Number(e.target.value))}
                className="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-emerald-400"
              />
              <p className="text-xs text-slate-500">Minimum cosine similarity required for biometric match</p>
            </div>

            {/* Target FPS */}
            <div className="space-y-2">
              <div className="flex justify-between">
                <label className="text-sm font-medium text-slate-300">Target Ingestion FPS</label>
                <span className="text-sm font-mono text-slate-200">{targetFps} FPS</span>
              </div>
              <input
                type="range"
                min="5"
                max="30"
                step="5"
                value={targetFps}
                onChange={(e) => setTargetFps(Number(e.target.value))}
                className="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-cyan-400"
              />
              <p className="text-xs text-slate-500">Higher FPS increases CPU/GPU usage</p>
            </div>
          </div>

          {/* Browser Protection */}
          <div className="pt-6 border-t border-white/5 space-y-6">
            <div className="flex flex-col gap-2">
              <h3 className="text-sm font-semibold text-slate-200">Defense-in-Depth: Safe Browser Protection</h3>
              <p className="text-xs text-amber-400/80 bg-amber-400/10 p-3 rounded-lg border border-amber-400/20 leading-relaxed">
                <strong className="text-amber-400 font-bold block mb-1">Warning:</strong>
                Browser session protection may sign you out of websites upon workstation lock. 
                Saved passwords, autofill, bookmarks, and credentials are never deleted.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-300">Protection Status</label>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => { setBpEnabled(true); if (bpMode === "DISABLED") setBpMode("CLOSE_BROWSER"); }}
                    className={`flex-1 py-2 text-xs font-semibold rounded-lg border transition-colors ${
                      bpEnabled ? "bg-cyan-500/20 text-cyan-400 border-cyan-500/50" : "bg-slate-900 border-white/10 text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    Enabled
                  </button>
                  <button
                    type="button"
                    onClick={() => { setBpEnabled(false); setBpMode("DISABLED"); }}
                    className={`flex-1 py-2 text-xs font-semibold rounded-lg border transition-colors ${
                      !bpEnabled ? "bg-slate-800 text-slate-200 border-slate-600" : "bg-slate-900 border-white/10 text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    Disabled
                  </button>
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-300">Operation Mode</label>
                <select
                  value={bpMode}
                  onChange={(e) => {
                    const val = e.target.value as BrowserProtectionMode;
                    setBpMode(val);
                    if (val !== "DISABLED") setBpEnabled(true);
                    else setBpEnabled(false);
                  }}
                  disabled={!bpEnabled}
                  className="w-full h-9 rounded-lg border border-white/10 bg-slate-900 px-3 text-xs text-slate-100 disabled:opacity-50"
                >
                  <option value="DISABLED">Disabled</option>
                  <option value="CLOSE_BROWSER">Close Browser Instances</option>
                  <option value="CLOSE_BROWSER_AND_CLEAR_SESSION_COOKIES">Close Browser + Wipe Session Cookies</option>
                </select>
                <p className="text-[11px] text-slate-500">
                  Chromium cookie wiping supported. Firefox session wipe unsupported for safety.
                </p>
              </div>
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t border-white/5">
            <Button
              type="submit"
              disabled={isSaving}
              className="gap-2"
            >
              {savedSuccess ? (
                <>
                  <Check className="w-4 h-4 text-emerald-400" />
                  Saved
                </>
              ) : (
                <>
                  <Save className="w-4 h-4" />
                  {isSaving ? "Saving..." : "Save Changes"}
                </>
              )}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
