// OPSpilot - frontend/lib/sse.ts
// Real SSE client for the live agent run stream.
//
// Connects to GET /api/runs/{id}/stream (backend EventBus), parses
// text/event-stream frames, and yields typed SSEEvent objects exactly as
// the orchestrator produced them. No simulated events, no animation timers.
import { useState, useEffect, useCallback, useRef } from "react";
import type { SSEEvent } from "@/types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export const runStreamUrl = (runId: string, lastEventId?: string): string => {
  const base = `${API_BASE}/api/runs/${encodeURIComponent(runId)}/stream`;
  return lastEventId
    ? `${base}?last_event_id=${encodeURIComponent(lastEventId)}`
    : base;
};

export const runTrajectoryUrl = (runId: string): string =>
  `${API_BASE}/api/runs/${encodeURIComponent(runId)}/trajectory`;

export interface UseAgentRunStreamResult {
  events: SSEEvent[];
  isConnected: boolean;
  error: string | null;
  reconnect: () => void;
  finished: boolean;
}

const MAX_RECONNECT_ATTEMPTS = 3;

export function useAgentRunStream(runId: string): UseAgentRunStreamResult {
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [finished, setFinished] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  const attemptRef = useRef(0);
  const lastEventIdRef = useRef<string>();
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = useCallback(() => {
    if (abortRef.current) abortRef.current.abort();
    if (timerRef.current) clearTimeout(timerRef.current);

    const controller = new AbortController();
    abortRef.current = controller;
    setError(null);

    const url = runStreamUrl(runId, lastEventIdRef.current);
    let buffer = "";
    let done = false;

    const pushEvent = (event: SSEEvent) => {
      if (event.event_id) lastEventIdRef.current = event.event_id;
      setEvents((prev) => [...prev, event]);
    };

    const finish = () => {
      if (done) return;
      done = true;
      setFinished(true);
      setIsConnected(false);
      pushEvent({
        run_id: runId,
        timestamp: new Date().toISOString(),
        event_type: "stream_end",
        data: { reason: "stream ended" },
      });
    };

    const retry = (reason: string) => {
      if (done) return;
      attemptRef.current += 1;
      setIsConnected(false);
      if (attemptRef.current > MAX_RECONNECT_ATTEMPTS) {
        finish();
        setError(
          `Stream disconnected (${reason}); reconnected max ${MAX_RECONNECT_ATTEMPTS} times.`
        );
        return;
      }
      // Backoff before reconnecting. This is a real retry — never a fake event.
      timerRef.current = setTimeout(() => connect(), 1200 * attemptRef.current);
    };

    (async () => {
      let res: Response;
      try {
        res = await fetch(url, { cache: "no-store", signal: controller.signal });
      } catch (err) {
        if (controller.signal.aborted) return;
        retry(err instanceof Error ? err.message : "network error");
        return;
      }
      if (!res.ok || !res.body) {
        if (controller.signal.aborted) return;
        finish();
        setError(`Stream failed (HTTP ${res.status})`);
        return;
      }
      setIsConnected(true);
      setFinished(false);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      try {
        while (true) {
          const { value, done: chunkDone } = await reader.read();
          if (chunkDone) break;
          buffer += decoder.decode(value, { stream: true });
          let split;
          while ((split = buffer.indexOf("\n\n")) !== -1) {
            const frame = buffer.slice(0, split);
            buffer = buffer.slice(split + 2);
            const dataLine = frame
              .split("\n")
              .find((line) => line.startsWith("data:"));
            if (!dataLine) continue; // comment (keep-alive) frame
            const raw = dataLine.slice(5).trim();
            if (!raw) continue;
            try {
              const parsed = JSON.parse(raw) as SSEEvent;
              pushEvent(parsed);
            } catch {
              // malformed frame: ignore, never fabricate an event
            }
          }
        }
      } catch (err) {
        if (controller.signal.aborted) return;
        retry(err instanceof Error ? err.message : "stream error");
        return;
      }
      if (controller.signal.aborted) return;
      finish();
    })();

    return () => controller.abort();
  }, [runId]);

  useEffect(() => {
    setEvents([]);
    setFinished(false);
    setError(null);
    attemptRef.current = 0;
    lastEventIdRef.current = undefined;
    pushConnected();

    function pushConnected() {
      setEvents((prev) => [
        ...prev,
        {
          run_id: runId,
          timestamp: new Date().toISOString(),
          event_type: "connected",
          data: { runId, timestamp: new Date().toISOString() },
        },
      ]);
    }

    const cleanup = connect();
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      if (abortRef.current) abortRef.current.abort();
      cleanup();
    };
  }, [runId, connect]);

  const reconnect = useCallback(() => {
    setEvents([]);
    setFinished(false);
    setError(null);
    attemptRef.current = 0;
    lastEventIdRef.current = undefined;
    setEvents((prev) => [
      ...prev,
      {
        run_id: runId,
        timestamp: new Date().toISOString(),
        event_type: "connected",
        data: { runId, timestamp: new Date().toISOString() },
      },
    ]);
    connect();
  }, [runId, connect]);

  return { events, isConnected, error, reconnect, finished };
}