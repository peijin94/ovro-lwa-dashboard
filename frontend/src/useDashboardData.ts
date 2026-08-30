import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  fetchJson,
  type EphemerisPayload,
  type FlareNowcastPayload,
  type GoesPayload,
  type HealthPayload,
  type SpectrumFrame,
  type SpectrumHistory,
} from './api';
import { janskyToSfu } from './units';

const MAX_FRAMES = 600;
const MID_CHANNEL = 384;
const GOES_XRAY_POLL_INTERVAL_MS = 30_000;
const FLARE_NOWCAST_POLL_INTERVAL_MS = 30_000;
const GOES_IMAGE_REFRESH_INTERVAL_MS = 5 * 60_000;

export function useDashboardData() {
  const [frames, setFrames] = useState<SpectrumFrame[]>([]);
  const [goes, setGoes] = useState<GoesPayload | null>(null);
  const [flareNowcast, setFlareNowcast] = useState<FlareNowcastPayload | null>(null);
  const [flareUpdatedAt, setFlareUpdatedAt] = useState<Date | null>(null);
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [ephemeris, setEphemeris] = useState<EphemerisPayload | null>(null);
  const [goesImageRefreshToken, setGoesImageRefreshToken] = useState(() => Date.now());
  const [lastFrameAt, setLastFrameAt] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [frameCount, setFrameCount] = useState(0);
  const [spectrumSyncing, setSpectrumSyncing] = useState(false);

  const syncSpectrum = useCallback(async () => {
    setSpectrumSyncing(true);
    try {
      const payload = await fetchJson<SpectrumHistory>(
        '/api/spectrum/history?n_frames=600',
      );
      setFrames(payload.data.filter((frame) => frame.length === 768));
      setFrameCount(payload.data.length);
      setLastFrameAt(new Date());
      setError(null);
    } catch {
      setError('Waiting for spectrum stream');
    } finally {
      setSpectrumSyncing(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadInitialHistory() {
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

    void loadInitialHistory();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
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
        fetchJson<HealthPayload>('/api/health'),
        fetchJson<EphemerisPayload>('/api/ephemeris'),
      ]);
      if (cancelled) return;
      if (results[0].status === 'fulfilled') setHealth(results[0].value);
      if (results[1].status === 'fulfilled') setEphemeris(results[1].value);
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

    async function refreshFlareNowcast() {
      try {
        const payload = await fetchJson<FlareNowcastPayload>('/api/flare/nowcast');
        if (cancelled) return;
        setFlareNowcast(payload);
        setFlareUpdatedAt(new Date());
      } catch {
        // Retain the last successful forecast while the stream or model recovers.
      }
    }

    void refreshFlareNowcast();
    const timer = window.setInterval(
      () => void refreshFlareNowcast(),
      FLARE_NOWCAST_POLL_INTERVAL_MS,
    );
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
    flareNowcast,
    flareUpdatedAt,
    health,
    ephemeris,
    lastFrameAt,
    frameCount,
    error,
    syncSpectrum,
    spectrumSyncing,
  };
}
