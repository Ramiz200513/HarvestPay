// Снимки поля со спутника Sentinel-2 за выбранный год и дату — рядом статистика сезона.
// Сверху выбираем сезон и режим (цвет / NDVI), под снимком — все безоблачные даты сезона точками
// по NDVI: клик по точке открывает снимок этого дня. Контур поля рисуем поверх снимка сами,
// по рамке (bbox), которую вернул сервер.
import { useEffect, useMemo, useState } from "react";
import { ApiError, api } from "../api";
import { formatDate } from "../lib/format";
import type { Application, FieldImagery, ImageryScene } from "../types";
import { seasonGrade, seasonScore, GRADE_LABEL } from "./NdviChart";

type Mode = "color" | "ndvi";

// Снимок по умолчанию — пик сезона: самый зелёный среди тех, где поле видно почти целиком
function pickDefault(scenes: ImageryScene[]): string | null {
  if (scenes.length === 0) return null;
  const clean = scenes.filter((s) => s.clear >= 0.9);
  const pool = clean.length ? clean : scenes;
  return pool.reduce((best, s) => (s.ndvi > best.ndvi ? s : best)).date;
}

const T_W = 560;
const T_H = 96;
const T_PAD = { top: 10, right: 10, bottom: 22, left: 30 };
const MONTHS = ["апр", "май", "июн", "июл", "авг", "сен"];

function Timeline({
  year,
  scenes,
  selected,
  onSelect,
}: {
  year: number;
  scenes: ImageryScene[];
  selected: string | null;
  onSelect: (d: string) => void;
}) {
  const start = Date.UTC(year, 3, 1);
  const end = Date.UTC(year, 9, 1);
  const plotW = T_W - T_PAD.left - T_PAD.right;
  const plotH = T_H - T_PAD.top - T_PAD.bottom;
  const xOf = (iso: string) => T_PAD.left + ((Date.parse(iso) - start) / (end - start)) * plotW;
  const yOf = (v: number) => T_PAD.top + plotH * (1 - Math.max(0, Math.min(1, v)));
  const line = scenes.map((s, i) => `${i ? "L" : "M"}${xOf(s.date).toFixed(1)},${yOf(s.ndvi).toFixed(1)}`).join("");

  return (
    <svg viewBox={`0 0 ${T_W} ${T_H}`} className="sat-timeline" role="img" aria-label={`NDVI поля по датам ${year} года`}>
      {[0, 0.5, 1].map((t) => (
        <g key={t}>
          <line x1={T_PAD.left} x2={T_W - T_PAD.right} y1={yOf(t)} y2={yOf(t)} className="grid" />
          <text x={T_PAD.left - 5} y={yOf(t) + 4} className="axis" textAnchor="end">
            {t}
          </text>
        </g>
      ))}
      {MONTHS.map((m, i) => (
        <text key={m} x={xOf(new Date(Date.UTC(year, 3 + i, 15)).toISOString())} y={T_H - 6} className="axis" textAnchor="middle">
          {m}
        </text>
      ))}
      <path d={line} className="line-fact" />
      {scenes.map((s) => {
        const active = s.date === selected;
        return (
          <g key={s.date} className="sat-dot" onClick={() => onSelect(s.date)}>
            <circle cx={xOf(s.date)} cy={yOf(s.ndvi)} r={12} fill="transparent" />
            <circle cx={xOf(s.date)} cy={yOf(s.ndvi)} r={active ? 6 : 4} className={active ? "dot-active" : "dot-fact"} />
            <title>
              {formatDate(s.date)} · NDVI {s.ndvi.toFixed(2)} · видно {Math.round(s.clear * 100)}% поля
            </title>
          </g>
        );
      })}
    </svg>
  );
}

export default function SatelliteViewer({ app }: { app: Application }) {
  const years = app.seasons.map((s) => s.year);
  const [year, setYear] = useState(years[years.length - 1]);
  const [mode, setMode] = useState<Mode>("color");
  const [data, setData] = useState<FieldImagery | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [imgState, setImgState] = useState<"loading" | "ok" | "error">("loading");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .imagery(app.id, year)
      .then((d) => {
        if (cancelled) return;
        setData(d);
        setSelected(pickDefault(d.scenes));
      })
      .catch((e) => !cancelled && setError(e instanceof ApiError ? e.message : "Не удалось загрузить снимки"))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [app.id, year]);

  useEffect(() => setImgState("loading"), [selected, mode]);

  const season = app.seasons.find((s) => s.year === year);
  const scene = data?.scenes.find((s) => s.date === selected) ?? null;
  const index = data && selected ? data.scenes.findIndex((s) => s.date === selected) : -1;

  // Контур поля в долях рамки снимка: x — от западного края, y — от северного
  const outline = useMemo(() => {
    if (!data?.bbox) return "";
    const [minLon, minLat, maxLon, maxLat] = data.bbox;
    return app.field.geometry.coordinates[0]
      .map(([lon, lat]) => `${((lon - minLon) / (maxLon - minLon)) * 100},${((maxLat - lat) / (maxLat - minLat)) * 100}`)
      .join(" ");
  }, [data?.bbox, app.field.geometry]);

  if (years.length === 0) return null;
  if (data && !data.available) {
    return (
      <section className="card">
        <h3>Снимки поля со спутника</h3>
        <p className="notice">{data.message}</p>
      </section>
    );
  }

  const grade = season ? seasonGrade(season) : "skip";
  const step = (d: number) => data && index >= 0 && setSelected(data.scenes[index + d]?.date ?? selected);

  return (
    <section className="card sat">
      <div className="sat-head">
        <h3>Снимки поля со спутника</h3>
        <div className="segmented" role="group" aria-label="Режим снимка">
          <button className={mode === "color" ? "on" : ""} onClick={() => setMode("color")}>
            Как видит глаз
          </button>
          <button className={mode === "ndvi" ? "on" : ""} onClick={() => setMode("ndvi")}>
            NDVI
          </button>
        </div>
      </div>

      <div className="year-tabs" role="tablist" aria-label="Сезон">
        {app.seasons.map((s) => (
          <button
            key={s.year}
            role="tab"
            aria-selected={s.year === year}
            className={s.year === year ? "year-tab on" : "year-tab"}
            onClick={() => setYear(s.year)}
          >
            <i className={`swatch grade-${seasonGrade(s)}`} />
            {s.year}
          </button>
        ))}
      </div>

      {error && <div className="alert">{error}</div>}

      <div className="sat-body">
        <div className="sat-image-col">
          <div className="sat-image">
            {loading && <div className="sat-placeholder">Ищем безоблачные снимки за {year} год…</div>}
            {!loading && data && data.scenes.length === 0 && (
              <div className="sat-placeholder">За {year} год нет снимков, где поле видно без облаков</div>
            )}
            {!loading && selected && (
              <>
                <img
                  key={`${selected}-${mode}`}
                  src={api.imageUrl(app.id, selected, mode)}
                  alt={`Снимок поля ${formatDate(selected)}, режим ${mode === "color" ? "цвет" : "NDVI"}`}
                  onLoad={() => setImgState("ok")}
                  onError={() => setImgState("error")}
                />
                {imgState === "ok" && (
                  <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="sat-outline" aria-hidden>
                    <polygon points={outline} vectorEffect="non-scaling-stroke" />
                  </svg>
                )}
                {imgState === "loading" && <div className="sat-placeholder overlay">Загружаем снимок…</div>}
                {imgState === "error" && (
                  <div className="sat-placeholder overlay">Не удалось загрузить снимок — выберите другую дату</div>
                )}
              </>
            )}
          </div>
          {mode === "ndvi" && (
            <div className="ndvi-legend">
              <span>голая почва</span>
              <i />
              <span>густая растительность</span>
              <span className="muted">· серым — облака и тени, голубым — вода</span>
            </div>
          )}
          {data && data.scenes.length > 0 && (
            <>
              <div className="sat-nav">
                <button className="btn btn-ghost" disabled={index <= 0} onClick={() => step(-1)}>
                  ← Раньше
                </button>
                <span className="muted small">
                  {data.scenes.length} безоблачных снимков за сезон · нажмите на точку, чтобы открыть дату
                </span>
                <button className="btn btn-ghost" disabled={index >= data.scenes.length - 1} onClick={() => step(1)}>
                  Позже →
                </button>
              </div>
              <Timeline year={year} scenes={data.scenes} selected={selected} onSelect={setSelected} />
            </>
          )}
        </div>

        <aside className="sat-stats">
          <div className="sat-date">{selected ? formatDate(selected) : `Сезон ${year}`}</div>
          {scene && (
            <dl>
              <dt>NDVI поля в этот день</dt>
              <dd>{scene.ndvi.toFixed(2)}</dd>
              <dt>Видно без облаков</dt>
              <dd>{Math.round(scene.clear * 100)}% поля</dd>
            </dl>
          )}
          {season && (
            <>
              <h4>Сезон {year}</h4>
              <div className={`grade-chip grade-${grade}`}>
                {GRADE_LABEL[grade]}
                {grade !== "skip" && season.ndvi_peak !== null && <b> · {seasonScore(season.ndvi_peak)} / 100</b>}
              </div>
              <dl>
                <dt>Пик NDVI</dt>
                <dd>{season.ndvi_peak?.toFixed(2) ?? "—"}</dd>
                <dt>Средний NDVI</dt>
                <dd>{season.ndvi_mean?.toFixed(2) ?? "—"}</dd>
                <dt>Безоблачных снимков</dt>
                <dd>{season.scenes}</dd>
                <dt>Влажность почвы</dt>
                <dd>{season.soil_moisture?.toFixed(2) ?? "—"}</dd>
                <dt>Заморозки по всходам</dt>
                <dd>{season.frost_days ?? "—"} дн.</dd>
                <dt>Жара ≥ 35 °C</dt>
                <dd>{season.heat_days ?? "—"} дн.</dd>
              </dl>
            </>
          )}
          <p className="muted small">Sentinel-2 L2A, 10 м/пиксель · Copernicus Data Space Ecosystem</p>
        </aside>
      </div>
    </section>
  );
}
