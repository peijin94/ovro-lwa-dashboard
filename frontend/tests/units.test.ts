import assert from 'node:assert/strict';
import test from 'node:test';

import { janskyToSfu } from '../src/units.ts';

test('converts janskys to solar flux units', () => {
  assert.equal(janskyToSfu(10_000), 1);
  assert.equal(janskyToSfu(250_000), 25);
  assert.equal(janskyToSfu(0), 0);
});
