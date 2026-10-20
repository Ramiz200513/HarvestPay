// Площадь полигона на сфере — та же формула, что на сервере (backend/app/services/geo.py).
// На фронтенде нужна, чтобы фермер видел площадь сразу, пока рисует поле.
// Окончательную площадь всё равно считает сервер — данным из браузера не доверяем.
import type { LngLat } from "../types";

const EARTH_RADIUS_M = 6378137;
const rad = (deg: number) => (deg * Math.PI) / 180;

export function ringAreaHa(points: LngLat[]): number {
  if (points.length < 3) return 0;
  let total = 0;
  for (let i = 0; i < points.length; i++) {
    const [lon1, lat1] = points[i];
    const [lon2, lat2] = points[(i + 1) % points.length];
    total += rad(lon2 - lon1) * (2 + Math.sin(rad(lat1)) + Math.sin(rad(lat2)));
  }
  return Math.abs((total * EARTH_RADIUS_M ** 2) / 2) / 10000;
}

export function closeRing(points: LngLat[]): LngLat[][] {
  return [[...points, points[0]]];
}
