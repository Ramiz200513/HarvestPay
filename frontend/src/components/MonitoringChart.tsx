// NDVI поля в течение сезона: факт по безоблачным снимкам против «нормы» — типичной кривой этого же поля.
// Одна ось (NDVI 0–1), два ряда: факт — сплошная линия с точками, норма — серый пунктир (это ориентир,
// а не ещё одна категория). Наведение — вертикальная линия и подсказка по ближайшему снимку.
import { type MouseEvent, useState } from "react";
import type { Monitoring } from "../types";

const W = 560;
const H = 220;
const PAD = { top: 16, right: 56, bottom: 28, left: 36 };
const TICKS = [0, 0.25, 0.5, 0.75, 1];
const MONTHS = ["", "", "", "", "май", "июн", "июл", "авг", "сен", "окт"];

const ms = (iso: string) => new Date(iso + "T00:00:00Z").getTime();
const short = (iso: string) => new Date(iso).toLocaleDateString("ru-RU", { day: "numeric", month: "short" });

export default function MonitoringChart({ m }: { m: Monitoring }) {
  const [hover, setHover] = useState<number | null>(null);
  const start = ms(`${m.season}-04-15`);
  const end = ms(`${m.season}-09-30`);
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;
  const xOf = (iso: string) => PAD.left + ((ms(iso) - start) / (end - start)) * plotW;
  const yOf = (v: number) => PAD.top + plotH * (1 - v);
  const path = (pts: { date: string; ndvi: number }[]) =>
    pts.map((p, i) => `${i ? "L" : "M"}${xOf(p.date).toFixed(1)},${yOf(p.ndvi).toFixed(1)}`).join("");

  // норма на дату ближайшего снимка — для подсказки
  const normAt = (iso: string) => {
    const t = ms(iso);
    return m.expected.reduce((best, p) => (Math.abs(ms(p.date) - t) < Math.abs(ms(best.date) - t) ? p : best)).ndvi;
  };

  const lastFact = m.points[m.points.length - 1];
  const lastNorm = m.expected[m.expected.length - 1];
  const h = hover !== null ? m.points[hover] : null;

  function onMove(e: MouseEvent<SVGRectElement>) {
    if (m.points.length === 0) return;
    const box = e.currentTarget.getBoundingClientRect();
    const x = PAD.left + ((e.clientX - box.left) / box.width) * plotW;
    let best = 0;
    m.points.forEach((p, i) => {
      if (Math.abs(xOf(p.date) - x) < Math.abs(xOf(m.points[best].date) - x)) best = i;
    });
    setHover(best);
  }

  return (
    <figure className="chart">
      <figcaption>
        <strong>NDVI в сезоне {m.season}</strong>
        <span className="muted"> — факт по снимкам против нормы этого поля (средний пик {m.norm_peak.toFixed(2)})</span>
      </figcaption>
      <div className="legend">
        <span className="legend-item">
          <span className="legend-line" /> Факт
        </span>
        <span className="legend-item">
          <span className="legend-line dashed" /> Норма поля
        </span>
      </div>
      <div className="chart-wrap">
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`NDVI поля в сезоне ${m.season}`}>
          {TICKS.map((t) => (
            <g key={t}>
              <line x1={PAD.left} x2={W - PAD.right} y1={yOf(t)} y2={yOf(t)} className="grid" />
              <text x={PAD.left - 6} y={yOf(t) + 4} className="axis" textAnchor="end">
                {String(t)}
              </text>
            </g>
          ))}
          {[5, 6, 7, 8, 9].map((month) => {
            const iso = `${m.season}-${String(month).padStart(2, "0")}-01`;
            return (
              <text key={month} x={xOf(iso)} y={H - 8} className="axis" textAnchor="middle">
                {MONTHS[month]}
              </text>
            );
          })}
          {/* порог «всходы есть» */}
          <line x1={PAD.left} x2={W - PAD.right} y1={yOf(0.3)} y2={yOf(0.3)} className="threshold" />
          <text x={W - PAD.right + 4} y={yOf(0.3) + 4} className="axis">
            всходы
          </text>

          <path d={path(m.expected)} className="line-norm" />
          {m.points.length > 0 && <path d={path(m.points)} className="line-fact" />}
          {m.points.map((p, i) => (
            <circle key={p.date} cx={xOf(p.date)} cy={yOf(p.ndvi)} r={hover === i ? 5 : 4} className="dot-fact" />
          ))}

          {/* прямые подписи рядов у правого края */}
          {lastFact && (
            <text x={xOf(lastFact.date) + 8} y={yOf(lastFact.ndvi) + 4} className="value">
              {lastFact.ndvi.toFixed(2)}
            </text>
          )}
          <text x={xOf(lastNorm.date) + 8} y={yOf(lastNorm.ndvi) + 16} className="axis">
            норма
          </text>

          {h && <line x1={xOf(h.date)} x2={xOf(h.date)} y1={PAD.top} y2={PAD.top + plotH} className="crosshair" />}
          <rect
            x={PAD.left}
            y={PAD.top}
            width={plotW}
            height={plotH}
            fill="transparent"
            onMouseMove={onMove}
            onMouseLeave={() => setHover(null)}
          />
        </svg>
        {h && (
          <div className="tooltip" style={{ left: `${(xOf(h.date) / W) * 100}%` }}>
            <b>{short(h.date)}</b>
            <div>Факт: {h.ndvi.toFixed(2)}</div>
            <div>Норма: {normAt(h.date).toFixed(2)}</div>
          </div>
        )}
      </div>
      <details className="chart-table">
        <summary>Показать таблицей</summary>
        <table>
          <thead>
            <tr>
              <th>Дата снимка</th>
              <th>NDVI факт</th>
              <th>Норма</th>
            </tr>
          </thead>
          <tbody>
            {m.points.map((p) => (
              <tr key={p.date}>
                <td>{short(p.date)}</td>
                <td>{p.ndvi.toFixed(3)}</td>
                <td>{normAt(p.date).toFixed(3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
