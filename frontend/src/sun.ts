export const SUN_BANNER_ELEVATION_DEG = 0;

export function shouldShowSunBanner(elevationDeg: number | null): boolean {
  return (
    elevationDeg !== null &&
    Number.isFinite(elevationDeg) &&
    elevationDeg < SUN_BANNER_ELEVATION_DEG
  );
}
