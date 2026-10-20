// Полная карточка заявки: решение, из чего сложился балл, график NDVI, поле, товары.
// Используется и на странице фермера, и в кабинете аналитика — поэтому вынесено в компонент.
import type { Application } from "../types";
import { CLASS_LABEL, STATUS_LABEL, formatDate, formatHa, formatKzt } from "../lib/format";
import FieldMap from "./FieldMap";
import NdviChart from "./NdviChart";

export function StatusPill({ status }: { status: Application["status"] }) {
  return <span className={`pill pill-${status}`}>{STATUS_LABEL[status]}</span>;
}

export function ClassBadge({ value }: { value: "A" | "B" | "C" }) {
  return (
    <span className={`class-badge class-${value}`} title={CLASS_LABEL[value]}>
      {value}
    </span>
  );
}

// Три компоненты индекса стабильности — показываем, сколько баллов принесла каждая.
function ScoreBreakdown({ app }: { app: Application }) {
  const c = app.decision?.components ?? {};
  if (c.mean_norm === undefined) return null;
  const rows = [
    { label: "Уровень NDVI", weight: 0.5, value: c.mean_norm, hint: `средний пик ${c.mean_ndvi?.toFixed(2)}` },
    {
      label: "Стабильность по годам",
      weight: 0.3,
      value: 100 - (c.volatility_norm ?? 0),
      hint: `разброс ${((c.volatility_cv ?? 0) * 100).toFixed(0)}%`,
    },
    {
      label: "Тренд",
      weight: 0.2,
      value: c.trend_norm ?? 0,
      hint: `${(c.trend_slope ?? 0) >= 0 ? "+" : ""}${(c.trend_slope ?? 0).toFixed(3)} NDVI/год`,
    },
  ];
  return (
    <div className="breakdown">
      {rows.map((r) => (
        <div key={r.label} className="breakdown-row">
          <div className="breakdown-label">
            {r.label} <span className="muted">· вес {r.weight * 100}% · {r.hint}</span>
          </div>
          <div className="meter" aria-hidden>
            <div className="meter-fill" style={{ width: `${r.value}%` }} />
          </div>
          <div className="breakdown-value">
            {(r.value * r.weight).toFixed(1)} <span className="muted">балла</span>
          </div>
        </div>
      ))}
      {!!c.moisture_penalty && (
        <div className="breakdown-row">
          <div className="breakdown-label">Сухая почва в последнем сезоне</div>
          <div className="meter" style={{ background: "transparent" }} />
          <div className="breakdown-value">−{c.moisture_penalty}</div>
        </div>
      )}
    </div>
  );
}

export default function ApplicationDetails({ app }: { app: Application }) {
  const d = app.decision;
  const ring = app.field.geometry.coordinates[0];

  return (
    <div className="details">
      {d && (
        <section className="card decision">
          <div className="decision-head">
            <ClassBadge value={d.score_class} />
            <div>
              <div className="decision-title">
                {CLASS_LABEL[d.score_class]}
                {d.score !== null && <span className="muted"> · индекс стабильности {d.score} / 100</span>}
              </div>
              <div className="muted">
                {d.decided_by === "analyst" ? "Решение принял кредитный аналитик" : "Решение принято автоматически"}
              </div>
            </div>
          </div>

          <div className="kpis">
            <div className="kpi">
              <div className="kpi-label">Одобрено</div>
              <div className="kpi-value">{formatKzt(d.approved_amount)}</div>
            </div>
            <div className="kpi">
              <div className="kpi-label">Запрошено</div>
              <div className="kpi-value">{formatKzt(app.requested_amount)}</div>
            </div>
            <div className="kpi">
              <div className="kpi-label">Лимит по полю</div>
              <div className="kpi-value">{formatKzt(d.limit_amount)}</div>
            </div>
          </div>

          {d.schedule.length > 0 && (
            <>
              <h3>График платежей</h3>
              <table className="table">
                <tbody>
                  {d.schedule.map((p) => (
                    <tr key={p.date}>
                      <td>{formatDate(p.date)}</td>
                      <td className="num">{formatKzt(p.amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}

          <h3>Почему такое решение</h3>
          <ul className="reasons">
            {d.reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
            {d.analyst_comment && <li>Комментарий аналитика: {d.analyst_comment}</li>}
          </ul>
          <ScoreBreakdown app={app} />
        </section>
      )}

      {app.seasons.length > 0 && (
        <section className="card">
          <NdviChart seasons={app.seasons} />
        </section>
      )}

      <section className="card two-col">
        <div>
          <h3>Поле</h3>
          <p>
            {app.field.crop} · {formatHa(app.field.area_ha)}
          </p>
          <p className="muted">
            {app.farm.name} · БИН {app.farm.bin}
          </p>
          <h3>Товары в рассрочку</h3>
          <table className="table">
            <tbody>
              {app.items.map((i) => (
                <tr key={i.product_id}>
                  <td>{i.name}</td>
                  <td className="num">
                    {i.quantity} {i.unit}
                  </td>
                  <td className="num">{formatKzt(i.total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {/* key: при выборе другой заявки карта создаётся заново и приближается к новому полю */}
        <FieldMap key={app.id} points={ring.slice(0, -1)} height={300} />
      </section>
    </div>
  );
}
