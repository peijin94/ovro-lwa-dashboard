import { useEffect, useMemo, useState } from 'react';
import {
  fetchJson,
  type EventPayload,
  type GoesPayload,
  type HealthPayload,
  type SpectrumFrame,
  type SpectrumHistory,
} from './api';

const MAX_FRAMES = 600;
const MID_CHANNEL = 384;

export function useDashboardData() {
  const [frames, setFrames] = useState<SpectrumFrame[]>([]);
  const [goes, setGoes] = useState<GoesPayload | null>(null);
  const [events, setEvents] = useState<EventPayload | null>(null);
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [lastFrameAt, setLastFrameAt] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [frameCount, setFrameCount] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function loadHistory() {
      try {
        const payload = await fetchJson<SpectrumHistory>(
          '/api/spectrum/history?n_frames=600',
        );
        if (cancelled) return;
        setFrames(payload.data.filter((frame) => frame.length === 768));
        setFrameCount(payload.data.length);
        setLastFrameAt(new Date());
        setError(null);
      } catch {
        if (!cancelled) setError('Waiting for spectrum stream');
      }
    }

    async function pollFrame() {
      try {
        const frame = await fetchJson<SpectrumFrame>(
          '/api/spectrum/latest',
        );
        if (cancelled || frame.length !== 768) return;
        setFrames((current) => [...current.slice(-(MAX_FRAMES - 1)), frame]);
        setFrameCount((count) => count + 1);
        setLastFrameAt(new Date());
        setError(null);
      } catch {
        if (!cancelled) setError('Spectrum stream interrupted');
      }
    }

    void loadHistory();
    const timer = window.setInterval(() => void pollFrame(), 512);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function pollSlowData() {
      const results = await Promise.allSettled([
        fetchJson<GoesPayload>('/api/goes/xray'),
        fetchJson<EventPayload>('/api/events'),
        fetchJson<HealthPayload>('/api/health'),
      ]);
      if (cancelled) return;
      if (results[0].status === 'fulfilled') setGoes(results[0].value);
      if (results[1].status === 'fulfilled') setEvents(results[1].value);
      if (results[2].status === 'fulfilled') setHealth(results[2].value);
    }

    void pollSlowData();
    const timer = window.setInterval(() => void pollSlowData(), 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  const lightCurve = useMemo(
    () =>
      frames.map((frame) => {
        const value = frame[MID_CHANNEL] ?? 0;
        return value > 0 ? 10 * Math.log10(value) : 0;
      }),
    [frames],
  );

  return {
    frames,
    lightCurve,
    goes,
    events,
    health,
    lastFrameAt,
    frameCount,
    error,
  };
}
