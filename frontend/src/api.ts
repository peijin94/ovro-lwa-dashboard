export type SpectrumFrame = number[];

export interface SpectrumHistory {
  data: SpectrumFrame[];
  buffer_length: number;
  buffer_index: number;
  timestamp: number;
}

export interface GoesPoint {
  time: string;
  short?: number;
  long?: number;
}

export interface GoesPayload {
  satellite: number | null;
  points: GoesPoint[];
  current_flux: number | null;
  peak_flux: number | null;
  updated: string | null;
}

export interface Detection {
  class?: string;
  class_id?: number;
  confidence?: number;
}

export interface EventPayload {
  detections: Detection[];
  count: number;
  timestamp: number;
}

export interface HealthPayload {
  status: 'ok' | 'degraded';
  live_spectrum: boolean;
  spectrum_channels: number;
  timestamp: number;
}

export function apiUrl(path: string): string {
  const prefix = import.meta.env.BASE_URL.replace(/\/$/, '');
  return `${prefix}${path}`.replace(/\/{2,}/g, '/');
}

export async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(apiUrl(path), { cache: 'no-store' });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

export function fluxClass(flux: number | null): string {
  if (!flux || !Number.isFinite(flux)) return '—';
  const bands = [
    { letter: 'X', base: 1e-4 },
    { letter: 'M', base: 1e-5 },
    { letter: 'C', base: 1e-6 },
    { letter: 'B', base: 1e-7 },
    { letter: 'A', base: 1e-8 },
  ];
  const band = bands.find(({ base }) => flux >= base) ?? bands[4];
  return `${band.letter}${Math.max(flux / band.base, 0.1).toFixed(1)}`;
}

