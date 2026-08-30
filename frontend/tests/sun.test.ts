import assert from 'node:assert/strict';
import test from 'node:test';

import { shouldShowSunBanner } from '../src/sun.ts';

test('shows the OVRO Sun banner only below ten degrees', () => {
  assert.equal(shouldShowSunBanner(9.99), true);
  assert.equal(shouldShowSunBanner(-15), true);
  assert.equal(shouldShowSunBanner(10), false);
  assert.equal(shouldShowSunBanner(45), false);
  assert.equal(shouldShowSunBanner(null), false);
});
