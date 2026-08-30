export const JY_PER_SFU = 10_000;

export function janskyToSfu(janskys: number): number {
  return janskys / JY_PER_SFU;
}
