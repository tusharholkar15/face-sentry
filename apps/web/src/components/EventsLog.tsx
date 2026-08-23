"use client";

import React from "react";
import { History, Shield, AlertTriangle, Key, Terminal, Radio } from "lucide-react";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { SecurityEvent } from "@/types";

interface EventsLogProps {
  events: SecurityEvent[];
  liveEvents?: SecurityEvent[];
}

export function EventsLog({ events, liveEvents = [] }: EventsLogProps) {
  // Merge and deduplicate live events with database history
  const allEventsMap = new Map<string, SecurityEvent>();

  // Add live events first
  liveEvents.forEach((ev) => {
    const key = `${ev.event_type}_${ev.timestamp}_${ev.action_taken}`;
    allEventsMap.set(key, ev);
  });

  // Add database events
  events.forEach((ev) => {
    const key = `${ev.event_type}_${ev.timestamp}_${ev.action_taken}`;
    if (!allEventsMap.has(key)) {
      allEventsMap.set(key, ev);
    }
  });

  const mergedEvents = Array.from(allEventsMap.values()).slice(0, 20);

  const getEventIcon = (eventType: string) => {
    switch (eventType) {
      case "USER_AUTHENTICATED":
      case "FACE_AUTHENTICATED":
        return <Shield className="w-4 h-4 text-emerald-400" />;
      case "ABSENCE_DETECTED":
      case "ABSENCE_STARTED":
      case "UNKNOWN_FACE_DETECTED":
      case "UNKNOWN_FACE_STARTED":
      case "SPOOF_DETECTED":
      case "SPOOF_ALERT":
        return <AlertTriangle className="w-4 h-4 text-amber-400" />;
      case "PIN_VERIFIED":
      case "PIN_FAILED":
        return <Key className="w-4 h-4 text-cyan-400" />;
      default:
        return <Terminal className="w-4 h-4 text-slate-400" />;
    }
  };

  const getEventBadgeVariant = (eventType: string) => {
    if (eventType.includes("AUTHENTICATED") || eventType.includes("SUCCESS")) return "success";
    if (eventType.includes("DETECTED") || eventType.includes("STARTED") || eventType.includes("FAILED")) return "warning";
    if (eventType.includes("LOCK")) return "destructive";
    return "secondary";
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>
            <History className="w-5 h-5 text-cyan-400" />
            Security Event Audit History
          </CardTitle>
          <div className="flex items-center gap-2">
            {liveEvents.length > 0 && (
              <Badge variant="outline" className="text-cyan-400 border-cyan-500/30 gap-1 font-mono text-[10px]">
                <Radio className="w-3 h-3 animate-pulse" />
                Live Stream Active
              </Badge>
            )}
            <Badge variant="outline">{mergedEvents.length} Records</Badge>
          </div>
        </div>
        <CardDescription>
          Immutable local security log of system actions, presence transitions, and locks
        </CardDescription>
      </CardHeader>
      <CardContent>
        {mergedEvents.length === 0 ? (
          <div className="text-center py-8 text-slate-500 text-sm font-sans">
            No security events recorded yet.
          </div>
        ) : (
          <div className="divide-y divide-white/5 font-sans">
            {mergedEvents.map((event, idx) => (
              <div key={`${event.id}_${idx}`} className="py-3 flex items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded-lg bg-slate-950 border border-white/5">
                    {getEventIcon(event.event_type)}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-slate-200">
                        {event.event_type.replace(/_/g, " ")}
                      </span>
                      <Badge variant={getEventBadgeVariant(event.event_type)}>
                        {event.action_taken}
                      </Badge>
                    </div>
                    <p className="text-xs text-slate-400 font-mono mt-0.5">
                      {new Date(event.timestamp).toLocaleString()}
                    </p>
                  </div>
                </div>

                {event.confidence !== null && (
                  <div className="text-right font-mono text-xs text-slate-400">
                    Confidence: {(event.confidence * 100).toFixed(0)}%
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
