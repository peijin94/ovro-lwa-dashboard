import assert from 'node:assert/strict';
import test from 'node:test';

import { shouldShowSunBanner } from '../src/sun.ts';

test('shows the OVRO Sun banner only below the horizon', () => {
  assert.equal(shouldShowSunBanner(-0.01), true);
  assert.equal(shouldShowSunBanner(-15), true);
  assert.equal(shouldShowSunBanner(0), false);
  assert.equal(shouldShowSunBanner(9.99), false);
  assert.equal(shouldShowSunBanner(45), false);
  assert.equal(shouldShowSunBanner(null), false);
});
