// Загрузка границ поля из файла вместо рисования кликами.
// KML выгружают Google Earth, агро-сервисы и навигаторы техники; GeoJSON — ГИС-программы (QGIS).
// Берём первый полигон из файла: заявка подаётся под одно поле.
import type { LngLat } from "../types";

export interface ImportedField {
  points: LngLat[]; // без замыкающей точки — так же, как при рисовании кликами
  polygons: number; // сколько полигонов было в файле (если больше одного — предупредим)
}

function dropClosingPoint(ring: LngLat[]): LngLat[] {
  const [first, last] = [ring[0], ring[ring.length - 1]];
  return ring.length > 1 && first[0] === last[0] && first[1] === last[1] ? ring.slice(0, -1) : ring;
}

function round(p: number[]): LngLat {
  return [+p[0].toFixed(6), +p[1].toFixed(6)];
}

function parseKml(text: string): ImportedField {
  const doc = new DOMParser().parseFromString(text, "application/xml");
  if (doc.querySelector("parsererror")) throw new Error("Файл не похож на KML");
  // getElementsByTagNameNS("*") — KML бывает и с пространством имён, и без
  const polygons = Array.from(doc.getElementsByTagNameNS("*", "Polygon"));
  if (polygons.length === 0) throw new Error("В файле нет полигонов — нужен контур поля, а не точка или линия");
  const outer = polygons[0].getElementsByTagNameNS("*", "outerBoundaryIs")[0] ?? polygons[0];
  const coords = outer.getElementsByTagNameNS("*", "coordinates")[0]?.textContent ?? "";
  // формат KML: «долгота,широта[,высота]» через пробелы
  const ring = coords
    .trim()
    .split(/\s+/)
    .map((t) => t.split(",").map(Number))
    .filter((p) => p.length >= 2 && p.every((n) => Number.isFinite(n)))
    .map(round);
  return { points: dropClosingPoint(ring), polygons: polygons.length };
}

function parseGeoJson(text: string): ImportedField {
  const data = JSON.parse(text);
  const geometries: { type: string; coordinates: number[][][] | number[][][][] }[] = [];
  const collect = (g: { type: string; geometry?: unknown; features?: unknown[]; coordinates?: unknown }) => {
    if (!g) return;
    if (g.type === "FeatureCollection") (g.features as never[]).forEach(collect);
    else if (g.type === "Feature") collect(g.geometry as never);
    else if (g.type === "Polygon" || g.type === "MultiPolygon") geometries.push(g as never);
  };
  collect(data);
  if (geometries.length === 0) throw new Error("В файле нет полигонов");
  const g = geometries[0];
  const outer = (g.type === "Polygon" ? g.coordinates[0] : (g.coordinates as number[][][][])[0][0]) as number[][];
  return { points: dropClosingPoint(outer.map(round)), polygons: geometries.length };
}

export async function readFieldFile(file: File): Promise<ImportedField> {
  const text = await file.text();
  const result = /\.(geo)?json$/i.test(file.name) ? parseGeoJson(text) : parseKml(text);
  if (result.points.length < 3) throw new Error("В контуре меньше трёх точек");
  return result;
}
