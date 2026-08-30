import { useEffect, useMemo, useState } from 'react';
import {
  fetchJson,
  type EventPayload,
  type GoesPayload,
  type HealthPayload,
  type SpectrumFrame,
  type SpectrumHistory,
} from './api';
import { janskyToSfu } from './units';

const MAX_FRAMES = 600;
const MID_CHANNEL = 384;
const GOES_XRAY_POLL_INTERVAL_MS = 30_000;
const GOES_IMAGE_REFRESH_INTERVAL_MS = 5 * 60_000;

export function useDashboardData() {
  const [frames, setFrames] = useState<SpectrumFrame[]>([]);
  const [goes, setGoes] = useState<GoesPayload | null>(null);
  const [events, setEvents] = useState<EventPayload | null>(null);
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [goesImageRefreshToken, setGoesImageRefreshToken] = useState(() => Date.now());
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

    async function pollOperationalData() {
      const results = await Promise.allSettled([
        fetchJson<EventPayload>('/api/events'),
        fetchJson<HealthPayload>('/api/health'),
      ]);
      if (cancelled) return;
      if (results[0].status === 'fulfilled') setEvents(results[0].value);
      if (results[1].status === 'fulfilled') setHealth(results[1].value);
    }

    void pollOperationalData();
    const timer = window.setInterval(() => void pollOperationalData(), 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function refreshGoesData() {
      try {
        const payload = await fetchJson<GoesPayload>('/api/goes/xray');
        if (cancelled) return;
        setGoes(payload);
      } catch {
        // Keep the last successful GOES snapshot visible until the next cycle.
      }
    }

    void refreshGoesData();
    const timer = window.setInterval(
      () => void refreshGoesData(),
      GOES_XRAY_POLL_INTERVAL_MS,
    );
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    const timer = window.setInterval(
      () => setGoesImageRefreshToken(Date.now()),
      GOES_IMAGE_REFRESH_INTERVAL_MS,
    );
    return () => window.clearInterval(timer);
  }, []);

  const lightCurve = useMemo(
    () =>
      frames.map((frame) => {
        const value = frame[MID_CHANNEL] ?? 0;
        return value > 0 ? janskyToSfu(value) : 0;
      }),
    [frames],
  );

  return {
    frames,
    lightCurve,
    goes,
    goesImageRefreshToken,
    events,
    health,
    lastFrameAt,
    frameCount,
    error,
  };
}
