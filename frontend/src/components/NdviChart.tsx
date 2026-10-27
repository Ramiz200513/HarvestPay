// Столбчатая диаграмма пикового NDVI по сезонам — без библиотек, на чистом SVG.
// Один ряд данных → один цвет, легенда не нужна (заголовок говорит, что изображено).
// Подписи только у последнего сезона и у худшего — остальное видно по оси и во всплывающей подсказке.
import { useState } from "react";
import type { Season } from "../types";

const W = 560;
const H = 220;
const PAD = { top: 24, right: 12, bottom: 28, left: 36 };
const BAR_MAX = 24;
const TICKS = [0, 0.25, 0.5, 0.75, 1];

// Столбец со скруглённым верхом (4px) и прямым основанием.
function barPath(x: number, y: number, w: number, h: number) {
  const r = Math.min(4, h, w / 2);
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
}

export default function NdviChart({ seasons }: { seasons: Season[] }) {
  const [hover, setHover] = useState<number | null>(null);
  if (seasons.length === 0) return null;

  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;
  const band = plotW / seasons.length;
  const barW = Math.min(BAR_MAX, band * 0.55);
  const yOf = (v: number) => PAD.top + plotH * (1 - v);

  const valued = seasons.filter((s) => s.ndvi_peak !== null);
  const worst = valued.reduce<Season | null>(
    (m, s) => (m === null || (s.ndvi_peak ?? 1) < (m.ndvi_peak ?? 1) ? s : m),
    null,
  );
  const latest = valued[valued.length - 1];

  return (
    <figure className="chart">
      <figcaption>
        <strong>Пиковый NDVI по сезонам</strong>
        <span className="muted"> — чем выше столбец, тем гуще была растительность на пике сезона</span>
      </figcaption>
      <div className="chart-wrap">
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Пиковый NDVI по годам">
          {TICKS.map((t) => (
            <g key={t}>
              <line x1={PAD.left} x2={W - PAD.right} y1={yOf(t)} y2={yOf(t)} className="grid" />
              <text x={PAD.left - 6} y={yOf(t) + 4} className="axis" textAnchor="end">
                {String(t)}
              </text>
            </g>
          ))}
          {seasons.map((s, i) => {
            const cx = PAD.left + band * i + band / 2;
            const x = cx - barW / 2;
            const hasValue = s.ndvi_peak !== null;
            const v = s.ndvi_peak ?? 0;
            const showLabel = hasValue && (s === latest || s === worst);
            return (
              <g key={s.year}>
                {hasValue ? (
                  <path
                    d={barPath(x, yOf(v), barW, plotH * v)}
                    className={hover === null || hover === i ? "bar" : "bar dim"}
                  />
                ) : (
                  <text x={cx} y={yOf(0) - 6} className="axis" textAnchor="middle">
                    н/д
                  </text>
                )}
                {showLabel && (
                  <text x={cx} y={yOf(v) - 6} className="value" textAnchor="middle">
                    {v.toFixed(2)}
                  </text>
                )}
                <text x={cx} y={H - 8} className="axis" textAnchor="middle">
                  {s.year}
                </text>
                {/* Невидимая зона наведения — шире самого столбца, чтобы легко попасть мышкой */}
                <rect
                  x={PAD.left + band * i}
                  y={PAD.top}
                  width={band}
                  height={plotH}
                  fill="transparent"
                  onMouseEnter={() => setHover(i)}
                  onMouseLeave={() => setHover(null)}
                />
              </g>
            );
          })}
        </svg>
        {hover !== null && (
          <div
            className="tooltip"
            style={{ left: `${((PAD.left + band * hover + band / 2) / W) * 100}%` }}
          >
            <b>{seasons[hover].year}</b>
            <div>NDVI пик: {seasons[hover].ndvi_peak?.toFixed(3) ?? "нет данных"}</div>
            <div>NDVI средний: {seasons[hover].ndvi_mean?.toFixed(3) ?? "—"}</div>
            <div>Влажность: {seasons[hover].soil_moisture?.toFixed(2) ?? "—"}</div>
            <div>
              Заморозки: {seasons[hover].frost_days ?? "—"} дн. · жара: {seasons[hover].heat_days ?? "—"} дн.
            </div>
            <div>Безоблачных снимков: {seasons[hover].scenes}</div>
          </div>
        )}
      </div>
      <details className="chart-table">
        <summary>Показать таблицей</summary>
        <table>
          <thead>
            <tr>
              <th>Сезон</th>
              <th>NDVI пик</th>
              <th>NDVI средний</th>
              <th>Влажность</th>
              <th>Заморозки, дн.</th>
              <th>Жара ≥35 °C, дн.</th>
              <th>Снимков</th>
            </tr>
          </thead>
          <tbody>
            {seasons.map((s) => (
              <tr key={s.year}>
                <td>{s.year}</td>
                <td>{s.ndvi_peak?.toFixed(3) ?? "—"}</td>
                <td>{s.ndvi_mean?.toFixed(3) ?? "—"}</td>
                <td>{s.soil_moisture?.toFixed(2) ?? "—"}</td>
                <td>{s.frost_days ?? "—"}</td>
                <td>{s.heat_days ?? "—"}</td>
                <td>{s.scenes}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
