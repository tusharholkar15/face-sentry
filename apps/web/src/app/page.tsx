"use client";

import React, { useEffect, useState, useCallback } from "react";
import { Header } from "@/components/Header";
import { HUDView } from "@/components/HUDView";
import { ConfigPanel } from "@/components/ConfigPanel";
import { EventsLog } from "@/components/EventsLog";
import { EnrollmentWizard } from "@/components/EnrollmentWizard";
import { PinModal } from "@/components/PinModal";
import {
  fetchHealth,
  fetchSystemStatus,
  fetchSystemConfig,
  fetchSecurityEvents,
} from "@/lib/api";
import { useTelemetry } from "@/lib/useTelemetry";
import {
  HealthResponse,
  SystemStatusResponse,
  SystemConfig,
  SecurityEvent,
} from "@/types";

export default function DashboardPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [status, setStatus] = useState<SystemStatusResponse | null>(null);
  const [config, setConfig] = useState<SystemConfig | null>(null);
  const [events, setEvents] = useState<SecurityEvent[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isEnrollmentOpen, setIsEnrollmentOpen] = useState<boolean>(false);
  const [isPinOpen, setIsPinOpen] = useState<boolean>(false);

  // Connect Real-Time Telemetry Hook
  const {
    snapshot: liveTelemetry,
    connectionState,
    isStale,
    lastReceivedTime,
    liveEvents,
    reconnect,
  } = useTelemetry();

  const loadData = useCallback(async () => {
    setIsLoading(true);
    try {
      const [healthData, statusData, configData, eventsData] = await Promise.all([
        fetchHealth().catch(() => null),
        fetchSystemStatus().catch(() => null),
        fetchSystemConfig().catch(() => null),
        fetchSecurityEvents(10).catch(() => []),
      ]);

      setHealth(healthData);
      setStatus(statusData);
      setConfig(configData);
      setEvents(eventsData);
    } catch (err) {
      console.error("Dashboard data load error:", err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 5000);
    return () => clearInterval(interval);
  }, [loadData]);

  return (
    <div className="min-h-screen flex flex-col bg-[#080c14] text-slate-100 font-sans">
      {/* Top Header with Live Stream State, PIN, & Enrollment Trigger */}
      <Header
        health={health}
        status={status}
        connectionState={connectionState}
        isLoading={isLoading}
        onRefresh={loadData}
        onOpenEnrollment={() => setIsEnrollmentOpen(true)}
        onOpenPin={() => setIsPinOpen(true)}
      />

      {/* Main Content Body */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-6 py-8 space-y-8">
        {/* Banner notification if API offline */}
        {!health && !isLoading && (
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-amber-300 text-sm flex items-center justify-between font-sans">
            <div>
              <span className="font-semibold">Local API Offline:</span> Start the API server with{" "}
              <code className="bg-slate-900 px-1.5 py-0.5 rounded text-xs font-mono text-cyan-300">
                python -m uvicorn apps.api.main:app --port 8000
              </code>{" "}
              to enable live biometric state telemetry.
            </div>
            <button
              onClick={loadData}
              className="px-3 py-1 bg-amber-500/20 hover:bg-amber-500/30 rounded-lg text-xs font-medium"
            >
              Retry
            </button>
          </div>
        )}

        {/* Live HUD & Telemetry */}
        <HUDView
          status={status}
          config={config}
          telemetry={liveTelemetry}
          connectionState={connectionState}
          isStale={isStale}
          onOpenEnrollment={() => setIsEnrollmentOpen(true)}
        />

        {/* Policy Configuration Controls */}
        <ConfigPanel initialConfig={config} onConfigUpdated={(c) => setConfig(c)} />

        {/* Security Audit Event Log */}
        <EventsLog events={events} liveEvents={liveEvents} />
      </main>

      {/* Multi-Step Enrollment Wizard Modal */}
      <EnrollmentWizard
        isOpen={isEnrollmentOpen}
        onClose={() => setIsEnrollmentOpen(false)}
        onEnrollmentCompleted={() => {
          setIsEnrollmentOpen(false);
          loadData();
        }}
        telemetry={liveTelemetry}
        connectionState={connectionState}
      />

      {/* Secure Local PIN Fallback Modal */}
      <PinModal
        isOpen={isPinOpen}
        onClose={() => setIsPinOpen(false)}
        onSuccess={() => {
          loadData();
        }}
      />

      {/* Footer */}
      <footer className="border-t border-white/5 py-6 px-6 text-center text-xs text-slate-500 font-sans">
        <p>
          FaceSentry v0.1.0 • Privacy-First On-Device Biometric Security • Real-Time Localhost Telemetry Active
          {lastReceivedTime && ` • Last Telemetry: ${new Date(lastReceivedTime).toLocaleTimeString()}`}
        </p>
      </footer>
    </div>
  );
}
