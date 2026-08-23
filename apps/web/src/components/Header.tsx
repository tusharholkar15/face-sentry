"use client";

import React from "react";
import { Shield, Cpu, Activity, RefreshCw, Radio, UserPlus, Key } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { HealthResponse, SystemStatusResponse } from "@/types";
import { ConnectionState } from "@/lib/useTelemetry";

interface HeaderProps {
  health: HealthResponse | null;
  status: SystemStatusResponse | null;
  connectionState: ConnectionState;
  isLoading: boolean;
  onRefresh: () => void;
  onOpenEnrollment: () => void;
  onOpenPin: () => void;
}

export function Header({
  health,
  status,
  connectionState,
  isLoading,
  onRefresh,
  onOpenEnrollment,
  onOpenPin,
}: HeaderProps) {
  const isHealthy = health?.status === "healthy";
  const state = status?.state || "UNINITIALIZED";

  const getConnectionBadgeVariant = () => {
    switch (connectionState) {
      case "CONNECTED":
        return "success";
      case "CONNECTING":
      case "RECONNECTING":
        return "warning";
      case "AGENT_OFFLINE":
      case "DISCONNECTED":
      default:
        return "destructive";
    }
  };

  return (
    <header className="border-b border-white/10 bg-slate-950/80 backdrop-blur-xl sticky top-0 z-50 px-6 py-4">
      <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
        {/* Brand Logo & Name */}
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-400 shadow-lg shadow-cyan-500/20">
            <Shield className="w-6 h-6" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold tracking-tight text-white font-mono">
                Face<span className="text-cyan-400">Sentry</span>
              </h1>
              <span className="text-[10px] font-mono uppercase px-1.5 py-0.5 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
                v{health?.version || "0.1.0"}
              </span>
            </div>
            <p className="text-xs text-slate-400">Privacy-First Windows Face Authentication</p>
          </div>
        </div>

        {/* Live Status & Action Buttons */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Live Telemetry Socket State */}
          <div className="flex items-center gap-2 bg-slate-900/80 border border-white/5 px-3 py-1.5 rounded-lg">
            <Radio className="w-4 h-4 text-cyan-400 animate-pulse" />
            <span className="text-xs text-slate-400">Stream:</span>
            <Badge variant={getConnectionBadgeVariant()}>{connectionState.replace(/_/g, " ")}</Badge>
          </div>

          {/* Engine State */}
          <div className="flex items-center gap-2 bg-slate-900/80 border border-white/5 px-3 py-1.5 rounded-lg">
            <Activity className="w-4 h-4 text-slate-400" />
            <span className="text-xs text-slate-400">Daemon:</span>
            <Badge variant={isHealthy ? "default" : "secondary"}>{state}</Badge>
          </div>

          {/* Emergency PIN Fallback Button */}
          <Button
            variant="outline"
            size="sm"
            onClick={onOpenPin}
            className="gap-1.5 border-cyan-500/30 text-cyan-300 hover:bg-cyan-500/10"
          >
            <Key className="w-4 h-4" />
            PIN Fallback
          </Button>

          {/* Enroll Face Profile Button */}
          <Button
            size="sm"
            onClick={onOpenEnrollment}
            className="gap-1.5 bg-cyan-500 hover:bg-cyan-600 text-slate-950 font-bold"
          >
            <UserPlus className="w-4 h-4" />
            Enroll Profile
          </Button>

          {/* Refresh Action */}
          <Button
            variant="outline"
            size="sm"
            onClick={onRefresh}
            disabled={isLoading}
            className="gap-1.5"
            aria-label="Refresh Status"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin" : ""}`} />
            Sync
          </Button>
        </div>
      </div>
    </header>
  );
}
