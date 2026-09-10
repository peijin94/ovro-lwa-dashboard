import type { FlareNowcastPayload, FlareProbabilityRecord } from './api';
import { CHART_WINDOW_MS } from './chartTime.ts';

function isProbability(value: number): boolean {
  return Number.isFinite(value) && value >= 0 && value <= 1;
}

export function nowcastToProbabilityRecord(
  payload: FlareNowcastPayload,
  receivedAt = new Date(),
): FlareProbabilityRecord | null {
  const R1p = payload['>M1']?.probability;
  const R2p = payload['>M5']?.probability;
  const R3p = payload['>X1']?.probability;
  if (
    R1p === undefined ||
    R2p === undefined ||
    R3p === undefined ||
    !isProbability(R1p) ||
    !isProbability(R2p) ||
    !isProbability(R3p)
  ) {
    return null;
  }
  const candidateTime = payload.recorded_at;
  const timeUT = candidateTime && Number.isFinite(Date.parse(candidateTime))
    ? candidateTime
    : receivedAt.toISOString();
  return {
    timeUT,
    R1p,
    R2p,
    R3p,
  };
}

export function mergeProbabilityRecords(
  current: FlareProbabilityRecord[],
  incoming: FlareProbabilityRecord[],
  nowMs = Date.now(),
): FlareProbabilityRecord[] {
  const cutoff = nowMs - CHART_WINDOW_MS;
  const byTime = new Map<string, FlareProbabilityRecord>();
  for (const point of [...current, ...incoming]) {
    const timestamp = Date.parse(point.timeUT);
    if (
      timestamp < cutoff ||
      timestamp > nowMs ||
      !isProbability(point.R1p) ||
      !isProbability(point.R2p) ||
      !isProbability(point.R3p)
    ) {
      continue;
    }
    byTime.set(point.timeUT, point);
  }
  return [...byTime.values()].sort(
    (left, right) => Date.parse(left.timeUT) - Date.parse(right.timeUT),
  );
}
