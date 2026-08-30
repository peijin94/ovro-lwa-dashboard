export const JY_PER_SFU = 10_000;
export const STREAM_NORMALIZATION = 24;
export const RADIO_CHANNELS = {
  40: 268,
  60: 476,
  80: 685,
} as const;

export function janskyToSfu(janskys: number): number {
  return janskys / JY_PER_SFU / STREAM_NORMALIZATION;
}

export function radioFluxAt(frame: number[], frequency: keyof typeof RADIO_CHANNELS): number {
  const value = frame[RADIO_CHANNELS[frequency]];
  return Number.isFinite(value) && value > 0 ? janskyToSfu(value) : 0;
}
