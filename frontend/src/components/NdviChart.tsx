// Скоринг по годам: пиковый NDVI каждого сезона на чистом SVG, без библиотек.
// Цвет столбца — оценка сезона (статус), и рядом всегда подпись балла: цвет никогда не единственный носитель смысла.
// Пунктирные линии — пороги, при которых средний уровень NDVI тянет поле в класс A или B; серая линия — тренд.
// Балл сезона — та же нормировка, что у «уровня NDVI» в backend/app/services/scoring.py (0.25 → 0, 0.75 → 100).
import { useState } from "react";
import type { Season } from "../types";

const W = 640;
const H = 260;
const PAD = { top: 20, right: 64, bottom: 56, left: 36 };
const BAR_MAX = 34;
const TICKS = [0, 0.25, 0.5, 0.75, 1];

// Синхронно с scoring.py: MIN_SCENES и нормировка уровня NDVI
const MIN_SCENES = 3;
const NDVI_LOW = 0.25;
const NDVI_HIGH = 0.75;
const NDVI_FOR_A = NDVI_LOW + (NDVI_HIGH - NDVI_LOW) * 0.75; // балл 75
const NDVI_FOR_B = NDVI_LOW + (NDVI_HIGH - NDVI_LOW) * 0.5; // балл 50

export type Grade = "good" | "mid" | "weak" | "skip";
export const GRADE_LABEL: Record<Grade, string> = {
  good: "сильный сезон",
  mid: "средний сезон",
  weak: "слабый сезон",
  skip: "не учтён",
};

export function seasonScore(peak: number) {
  return Math.round(Math.max(0, Math.min(1, (peak - NDVI_LOW) / (NDVI_HIGH - NDVI_LOW))) * 100);
}

export function seasonGrade(s: Season): Grade {
  if (s.ndvi_peak === null || s.scenes < MIN_SCENES) return "skip";
  const score = seasonScore(s.ndvi_peak);
  return score >= 75 ? "good" : score >= 50 ? "mid" : "weak";
}

// Столбец со скруглённым верхом (4px) и прямым основанием.
function barPath(x: number, y: number, w: number, h: number) {
  const r = Math.min(4, h, w / 2);
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
}

// Наклон и сдвиг прямой по методу наименьших квадратов — как linear_slope в scoring.py
function trendLine(points: { x: number; y: number }[]) {
  const n = points.length;
  const mx = points.reduce((a, p) => a + p.x, 0) / n;
  const my = points.reduce((a, p) => a + p.y, 0) / n;
  const den = points.reduce((a, p) => a + (p.x - mx) ** 2, 0);
  const slope = den ? points.reduce((a, p) => a + (p.x - mx) * (p.y - my), 0) / den : 0;
  return { slope, at: (x: number) => my + slope * (x - mx) };
}

function sourceLabel(source: string | null | undefined) {
  if (!source) return null;
  if (source === "mock") return "демо-данные";
  if (source === "cdse") return "Sentinel-2 · Copernicus Data Space";
  if (source === "gee") return "Sentinel-2 · Google Earth Engine";
  return source;
}

export default function NdviChart({ seasons }: { seasons: Season[] }) {
  const [hover, setHover] = useState<number | null>(null);
  if (seasons.length === 0) return null;

  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;
  const band = plotW / seasons.length;
  const barW = Math.min(BAR_MAX, band * 0.55);
  const yOf = (v: number) => PAD.top + plotH * (1 - v);
  const cxOf = (i: number) => PAD.left + band * i + band / 2;

  const grades = seasons.map(seasonGrade);
  const used = seasons.map((s, i) => ({ s, i })).filter(({ i }) => grades[i] !== "skip");
  const trend = used.length >= 2 ? trendLine(used.map(({ s }) => ({ x: s.year, y: s.ndvi_peak as number }))) : null;
  const first = used[0];
  const last = used[used.length - 1];
  const counts = { good: 0, mid: 0, weak: 0, skip: 0 };
  grades.forEach((g) => counts[g]++);
  const source = sourceLabel(seasons.find((s) => s.source)?.source);

  const hs = hover !== null ? seasons[hover] : null;

  return (
    <figure className="chart">
      <figcaption>
        <strong>Скоринг по годам</strong>
        <span className="muted">
          {" "}
          — пиковый NDVI каждого сезона: насколько густой была растительность на поле
          {source && <> · источник: {source}</>}
        </span>
      </figcaption>

      <div className="season-summary">
        <span>
          <i className="swatch grade-good" /> сильных: <b>{counts.good}</b>
        </span>
        <span>
          <i className="swatch grade-mid" /> средних: <b>{counts.mid}</b>
        </span>
        <span>
          <i className="swatch grade-weak" /> слабых: <b>{counts.weak}</b>
        </span>
        {counts.skip > 0 && (
          <span>
            <i className="swatch grade-skip" /> не учтено: <b>{counts.skip}</b>
          </span>
        )}
        {trend && (
          <span>
            <i className="swatch-line" /> тренд:{" "}
            <b>
              {trend.slope >= 0 ? "+" : "−"}
              {Math.abs(trend.slope).toFixed(3)} NDVI/год
            </b>
          </span>
        )}
      </div>

      <div className="chart-wrap">
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Пиковый NDVI и оценка каждого сезона">
          {TICKS.map((t) => (
            <g key={t}>
              <line x1={PAD.left} x2={W - PAD.right} y1={yOf(t)} y2={yOf(t)} className="grid" />
              <text x={PAD.left - 6} y={yOf(t) + 4} className="axis" textAnchor="end">
                {String(t)}
              </text>
            </g>
          ))}
          {[
            { v: NDVI_FOR_A, label: "уровень A" },
            { v: NDVI_FOR_B, label: "уровень B" },
          ].map((l) => (
            <g key={l.label}>
              <line x1={PAD.left} x2={W - PAD.right} y1={yOf(l.v)} y2={yOf(l.v)} className="threshold" />
              <text x={W - PAD.right + 6} y={yOf(l.v) + 4} className="axis">
                {l.label}
              </text>
            </g>
          ))}

          {seasons.map((s, i) => {
            const g = grades[i];
            const cx = cxOf(i);
            const v = s.ndvi_peak ?? 0;
            const dim = hover !== null && hover !== i ? " dim" : "";
            const climate = [
              (s.frost_days ?? 0) >= 1 ? `❄${s.frost_days}` : "",
              (s.heat_days ?? 0) >= 5 ? `☀${s.heat_days}` : "",
            ]
              .filter(Boolean)
              .join(" ");
            return (
              <g key={s.year}>
                {s.ndvi_peak !== null ? (
                  <path d={barPath(cx - barW / 2, yOf(v), barW, plotH * v)} className={`bar grade-${g}${dim}`} />
                ) : (
                  <text x={cx} y={yOf(0) - 6} className="axis" textAnchor="middle">
                    н/д
                  </text>
                )}
                <text x={cx} y={H - PAD.bottom + 16} className="axis year" textAnchor="middle">
                  {s.year}
                </text>
                <text x={cx} y={H - PAD.bottom + 32} className="value" textAnchor="middle">
                  {g === "skip" ? "—" : seasonScore(v)}
                </text>
                {climate && (
                  <text x={cx} y={H - PAD.bottom + 48} className="axis" textAnchor="middle">
                    {climate}
                  </text>
                )}
                {/* Невидимая зона наведения — шире самого столбца, чтобы легко попасть мышкой */}
                <rect
                  x={PAD.left + band * i}
                  y={PAD.top}
                  width={band}
                  height={H - PAD.top}
                  fill="transparent"
                  onMouseEnter={() => setHover(i)}
                  onMouseLeave={() => setHover(null)}
                />
              </g>
            );
          })}

          {trend && first && last && (
            <line
              x1={cxOf(first.i)}
              x2={cxOf(last.i)}
              y1={yOf(trend.at(first.s.year))}
              y2={yOf(trend.at(last.s.year))}
              className="trend"
              pointerEvents="none"
            />
          )}
          <text x={PAD.left - 6} y={H - PAD.bottom + 32} className="axis" textAnchor="end">
            балл
          </text>
        </svg>
        {hs && hover !== null && (
          <div className="tooltip" style={{ left: `${(cxOf(hover) / W) * 100}%` }}>
            <b>
              {hs.year} · {GRADE_LABEL[grades[hover]]}
            </b>
            <div>
              Балл сезона: {grades[hover] === "skip" ? "не учтён" : `${seasonScore(hs.ndvi_peak ?? 0)} / 100`}
            </div>
            <div>NDVI пик: {hs.ndvi_peak?.toFixed(3) ?? "нет данных"}</div>
            <div>NDVI средний: {hs.ndvi_mean?.toFixed(3) ?? "—"}</div>
            <div>Влажность: {hs.soil_moisture?.toFixed(2) ?? "—"}</div>
            <div>
              Заморозки: {hs.frost_days ?? "—"} дн. · жара: {hs.heat_days ?? "—"} дн.
            </div>
            <div>
              Безоблачных снимков: {hs.scenes}
              {hs.scenes < MIN_SCENES && ` (нужно ≥ ${MIN_SCENES})`}
            </div>
          </div>
        )}
      </div>
      <p className="muted chart-note">
        Под годом — балл сезона 0–100 по уровню NDVI; ❄ — дни заморозков по всходам, ☀ — дни жары ≥ 35 °C. Итоговый
        индекс учитывает не только уровень, но и разброс между годами и тренд — разбивка выше.
      </p>
      <details className="chart-table">
        <summary>Показать таблицей</summary>
        <table>
          <thead>
            <tr>
              <th>Сезон</th>
              <th>Оценка</th>
              <th>Балл</th>
              <th>NDVI пик</th>
              <th>NDVI средний</th>
              <th>Влажность</th>
              <th>Заморозки, дн.</th>
              <th>Жара ≥35 °C, дн.</th>
              <th>Снимков</th>
            </tr>
          </thead>
          <tbody>
            {seasons.map((s, i) => (
              <tr key={s.year}>
                <td>{s.year}</td>
                <td>{GRADE_LABEL[grades[i]]}</td>
                <td>{grades[i] === "skip" ? "—" : seasonScore(s.ndvi_peak ?? 0)}</td>
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
