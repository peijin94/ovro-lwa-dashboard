import assert from 'node:assert/strict';
import test from 'node:test';

import type { FlareNowcastPayload } from '../src/api.ts';
import {
  mergeProbabilityRecords,
  nowcastToProbabilityRecord,
} from '../src/flareProbability.ts';

const nowcast: FlareNowcastPayload = {
  feature_sfu: 12,
  horizon_min: 10,
  '>M1': { probability: 0.7, p_low: 0.6, p_high: 0.8, n_total: 100, feature_sfu: 12 },
  '>M5': { probability: 0.3, p_low: 0.2, p_high: 0.4, n_total: 100, feature_sfu: 12 },
  '>X1': { probability: 0.1, p_low: 0.05, p_high: 0.15, n_total: 100, feature_sfu: 12 },
  frequencies_mhz: [40, 60, 80],
  model_version: 'v0.3',
  created_utc: '2026-09-10T00:00:00Z',
  recorded_at: '2026-09-10T19:30:00.000Z',
};

test('converts a nowcast response into a plot record', () => {
  assert.deepEqual(nowcastToProbabilityRecord(nowcast), {
    timeUT: '2026-09-10T19:30:00.000Z',
    R1p: 0.7,
    R2p: 0.3,
    R3p: 0.1,
  });
});

test('keeps merged plot records inside the trailing thirty-minute window', () => {
  const merged = mergeProbabilityRecords(
    [
      { timeUT: '2026-09-10T18:59:59.000Z', R1p: 0.1, R2p: 0.1, R3p: 0.1 },
      { timeUT: '2026-09-10T19:20:00.000Z', R1p: 0.2, R2p: 0.1, R3p: 0.05 },
    ],
    [{ timeUT: '2026-09-10T19:30:00.000Z', R1p: 0.7, R2p: 0.3, R3p: 0.1 }],
    Date.parse('2026-09-10T19:30:00.000Z'),
  );

  assert.deepEqual(merged.map((point) => point.timeUT), [
    '2026-09-10T19:20:00.000Z',
    '2026-09-10T19:30:00.000Z',
  ]);
});
