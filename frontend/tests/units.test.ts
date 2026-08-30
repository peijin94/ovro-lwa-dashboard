import assert from 'node:assert/strict';
import test from 'node:test';

import { janskyToSfu, radioFluxAt } from '../src/units.ts';

test('converts normalized stream janskys to solar flux units', () => {
  assert.equal(janskyToSfu(240_000), 1);
  assert.equal(janskyToSfu(6_000_000), 25);
  assert.equal(janskyToSfu(0), 0);
});

test('reads calibrated radio flux from the requested spectrum channels', () => {
  const frame = Array<number>(768).fill(0);
  frame[268] = 240_000;
  frame[476] = 480_000;
  frame[685] = 720_000;

  assert.equal(radioFluxAt(frame, 40), 1);
  assert.equal(radioFluxAt(frame, 60), 2);
  assert.equal(radioFluxAt(frame, 80), 3);
});
