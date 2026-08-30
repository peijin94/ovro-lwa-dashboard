import assert from 'node:assert/strict';
import test from 'node:test';

import { janskyToSfu } from '../src/units.ts';

test('converts normalized stream janskys to solar flux units', () => {
  assert.equal(janskyToSfu(240_000), 1);
  assert.equal(janskyToSfu(6_000_000), 25);
  assert.equal(janskyToSfu(0), 0);
});
