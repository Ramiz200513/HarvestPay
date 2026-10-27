// Портфель маркетплейса: кредитная линия банка, деньги в сделках, ожидаемые поступления и список сделок.
import { useEffect, useState } from "react";
import { ApiError, api } from "../api";
import { DEAL_STATUS_LABEL, MONITORING_LABEL, formatHa, formatKzt, formatMln, formatPct } from "../lib/format";
import type { Payment, Portfolio } from "../types";
import { ClassBadge } from "./ApplicationDetails";

const monthLabel = (iso: string) => new Date(iso).toLocaleDateString("ru-RU", { month: "short", year: "numeric" });

// Ожидаемые поступления от фермеров по месяцам: один ряд — один цвет, подписи у столбцов.
function UpcomingChart({ months }: { months: Payment[] }) {
  const [hover, setHover] = useState<number | null>(null);
  if (months.length === 0) return <p className="muted">Ожидаемых платежей нет</p>;
  const W = 560;
  const H = 180;
  const pad = { top: 22, bottom: 26, left: 8, right: 8 };
  const max = Math.max(...months.map((m) => m.amount));
  const band = (W - pad.left - pad.right) / months.length;
  const barW = Math.min(36, band * 0.6);
  const plotH = H - pad.top - pad.bottom;
  return (
    <figure className="chart">
      <figcaption>
        <strong>Ожидаемые поступления от фермеров</strong>
        <span className="muted"> — по месяцам, с учётом уже внесённых платежей</span>
      </figcaption>
      <div className="chart-wrap">
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Ожидаемые поступления по месяцам">
          <line x1={pad.left} x2={W - pad.right} y1={pad.top + plotH} y2={pad.top + plotH} className="grid" />
          {months.map((m, i) => {
            const h = Math.max(2, (m.amount / max) * plotH);
            const cx = pad.left + band * i + band / 2;
            const y = pad.top + plotH - h;
            const r = Math.min(4, h, barW / 2);
            return (
              <g key={m.date}>
                <path
                  d={`M${cx - barW / 2},${y + h}V${y + r}Q${cx - barW / 2},${y} ${cx - barW / 2 + r},${y}H${cx + barW / 2 - r}Q${cx + barW / 2},${y} ${cx + barW / 2},${y + r}V${y + h}Z`}
                  className={hover === null || hover === i ? "bar" : "bar dim"}
                />
                <text x={cx} y={y - 6} className="value" textAnchor="middle">
                  {formatMln(m.amount)}
                </text>
                <text x={cx} y={H - 8} className="axis" textAnchor="middle">
                  {monthLabel(m.date)}
                </text>
                <rect
                  x={pad.left + band * i}
                  y={pad.top}
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
          <div className="tooltip" style={{ left: `${((pad.left + band * hover + band / 2) / W) * 100}%` }}>
            <b>{monthLabel(months[hover].date)}</b>
            <div>{formatKzt(months[hover].amount)}</div>
          </div>
        )}
      </div>
    </figure>
  );
}

export default function PortfolioView({ token, onOpen }: { token: string; onOpen: (id: string) => void }) {
  const [data, setData] = useState<Portfolio | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.analyst
      .portfolio(token)
      .then(setData)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Сервер недоступен"));
  }, [token]);

  if (error) return <div className="alert">{error}</div>;
  if (!data) return <p className="muted">Загружаем портфель…</p>;

  const line = data.credit_line;
  const usedShare = line.limit ? line.used / line.limit : 0;

  return (
    <div className="portfolio">
      <section className="card">
        <div className="section-head">
          <h3 className="first">Кредитная линия · {line.bank}</h3>
          <span className="muted">{formatPct(line.rate)} годовых</span>
        </div>
        <div className="line-meter" aria-hidden>
          <div className="line-meter-fill" style={{ width: `${Math.min(100, usedShare * 100)}%` }} />
        </div>
        <div className="line-legend">
          <span>
            В сделках <b>{formatMln(line.used)}</b> ({formatPct(usedShare, 1)})
          </span>
          <span>
            Свободно <b>{formatMln(line.available)}</b> из {formatMln(line.limit)}
          </span>
        </div>
        <div className="kpis">
          <div className="kpi">
            <div className="kpi-label">Сделок</div>
            <div className="kpi-value">{data.deals_count}</div>
          </div>
          <div className="kpi">
            <div className="kpi-label">Товара продано в рассрочку</div>
            <div className="kpi-value">{formatMln(data.goods_amount)}</div>
          </div>
          <div className="kpi">
            <div className="kpi-label">Фермеры вернули</div>
            <div className="kpi-value">
              {formatMln(data.paid_amount)} <span className="muted small">из {formatMln(data.farmer_total)}</span>
            </div>
          </div>
          <div className="kpi">
            <div className="kpi-label">Ожидаемый доход платформы</div>
            <div className="kpi-value">{formatMln(data.expected_margin)}</div>
            <div className="muted small">уже за вычетом ожидаемых потерь {formatMln(data.expected_loss)}</div>
          </div>
        </div>
      </section>

      <section className="card">
        <UpcomingChart months={data.upcoming} />
      </section>

      <section className="card">
        <h3 className="first">Сделки</h3>
        {data.deals.length === 0 ? (
          <p className="muted">Одобренных заявок пока нет — сделка открывается в момент одобрения.</p>
        ) : (
          <div className="table-scroll">
            <table className="table deals-table">
              <thead>
                <tr>
                  <th>Хозяйство</th>
                  <th>Класс</th>
                  <th>Статус</th>
                  <th>Поле</th>
                  <th className="num">Товар</th>
                  <th className="num">Вернули</th>
                  <th className="num">Доход</th>
                </tr>
              </thead>
              <tbody>
                {data.deals.map((d) => (
                  <tr key={d.application_id} className="clickable" onClick={() => onOpen(d.application_id)}>
                    <td>
                      <b>{d.farm_name}</b>
                      <div className="muted small">{d.crop}</div>
                    </td>
                    <td>
                      <ClassBadge value={d.score_class} />
                    </td>
                    <td>
                      {DEAL_STATUS_LABEL[d.status]}
                      {d.overdue && <div className="danger small">просрочка</div>}
                      {d.monitoring_status && (
                        <div className="muted small">спутник: {MONITORING_LABEL[d.monitoring_status]}</div>
                      )}
                    </td>
                    <td>{formatHa(d.area_ha)}</td>
                    <td className="num">{formatKzt(d.goods_amount)}</td>
                    <td className="num">{formatPct(d.farmer_total ? d.paid_amount / d.farmer_total : 0)}</td>
                    <td className={d.margin < 0 ? "num danger" : "num"}>{formatKzt(d.margin)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
