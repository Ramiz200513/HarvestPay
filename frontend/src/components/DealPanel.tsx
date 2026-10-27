// Сделка по одобренной заявке.
//  * DealSummary — фермеру: на каком шаге сделка и сколько осталось заплатить.
//  * DealPanel — аналитику: экономика сделки, движение денег, сценарий неурожая, спутниковый мониторинг
//    и кнопки следующего шага (оплатить поставщику, отгрузка, платёж, перенос).
import { useState } from "react";
import { ApiError, api } from "../api";
import { DEAL_STATUS_LABEL, MONITORING_LABEL, formatDate, formatKzt, formatPct } from "../lib/format";
import type { Application, Deal, DealAction, DealStatus } from "../types";
import MonitoringChart from "./MonitoringChart";

const TRACK: DealStatus[] = ["contracted", "supplier_paid", "delivered", "sowing_confirmed", "repaid"];

function DealTrack({ deal }: { deal: Deal }) {
  // перенос — это шаг «вбок» после сева: показываем его вместо «Погашено», пока долг не закрыт
  const track = deal.status === "restructured" ? [...TRACK.slice(0, 4), "restructured" as DealStatus] : TRACK;
  const current = track.indexOf(deal.status);
  return (
    <ol className="deal-track">
      {track.map((s, i) => (
        <li key={s} className={i < current ? "done" : i === current ? "active" : ""}>
          {DEAL_STATUS_LABEL[s]}
        </li>
      ))}
    </ol>
  );
}

function Remaining({ deal }: { deal: Deal }) {
  const left = deal.farmer_total - deal.paid_amount;
  return (
    <>
      <div className="kpis">
        <div className="kpi">
          <div className="kpi-label">Товар по розничной цене</div>
          <div className="kpi-value">{formatKzt(deal.goods_amount)}</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Вернуть всего</div>
          <div className="kpi-value">{formatKzt(deal.farmer_total)}</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Осталось{deal.overdue ? " · есть просрочка" : ""}</div>
          <div className={deal.overdue ? "kpi-value danger" : "kpi-value"}>{formatKzt(left)}</div>
        </div>
      </div>
      <h3>График платежей</h3>
      <table className="table">
        <tbody>
          {deal.schedule.map((p) => (
            <tr key={p.date + p.amount}>
              <td>
                {formatDate(p.date)} {p.note && <span className="muted">· {p.note}</span>}
              </td>
              <td className="num">{formatKzt(p.amount)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

export function DealSummary({ deal }: { deal: Deal }) {
  return (
    <section className="card">
      <h3 className="first">Ваша рассрочка</h3>
      <DealTrack deal={deal} />
      <Remaining deal={deal} />
      <p className="muted small">
        Поставщики получают оплату от нас и отгружают товар перед севом — {formatDate(deal.payout_date)}. Мы видим
        всходы на поле со спутника, поэтому выезжать на проверку не нужно. Если год окажется неурожайным, страховка и
        перенос платежа на следующий сезон защищают хозяйство от просрочки.
      </p>
    </section>
  );
}

// --- аналитику ---------------------------------------------------------------------------------

const NEXT_ACTION: Partial<Record<DealStatus, { action: DealAction; label: string }>> = {
  contracted: { action: "pay_supplier", label: "Банк оплатил поставщикам" },
  supplier_paid: { action: "confirm_delivery", label: "Товар отгружен" },
  delivered: { action: "confirm_sowing", label: "Подтвердить сев вручную" },
};

function Economics({ deal }: { deal: Deal }) {
  const e = deal.economics;
  if (!e) return null;
  const rows: [string, number, string][] = [
    ["Фермер вернёт осенью", e.farmer_total, `товар + наценка ${formatPct(deal.fee_rate ?? 0, 1)}`],
    ["Банк платит поставщикам", -e.supplier_payout, `скидка поставщиков ${formatPct(deal.discount_rate ?? 0, 1)}`],
    ["Проценты банку", -e.funding_cost, `${formatPct(deal.funding_rate ?? 0)} годовых × ${e.funding_days} дн.`],
    ["Ожидаемые потери", -e.expected_loss, "вероятность дефолта по классу × доля потерь 45%"],
  ];
  return (
    <>
      <h3>Экономика сделки</h3>
      <table className="table">
        <tbody>
          {rows.map(([label, value, hint]) => (
            <tr key={label}>
              <td>
                {label} <span className="muted">· {hint}</span>
              </td>
              <td className="num">{formatKzt(value)}</td>
            </tr>
          ))}
          <tr className="total">
            <td>Доход платформы</td>
            <td className={e.margin < 0 ? "num danger" : "num"}>
              {formatKzt(e.margin)} <span className="muted">({formatPct(e.margin_pct, 1)} от товара)</span>
            </td>
          </tr>
        </tbody>
      </table>
    </>
  );
}

function Flow({ deal }: { deal: Deal }) {
  if (!deal.flow) return null;
  return (
    <>
      <h3>Как движутся деньги и товар</h3>
      <ol className="flow">
        {deal.flow.map((s, i) => (
          <li key={i} className={`flow-${s.kind}`}>
            <div className="flow-when">{formatDate(s.when)}</div>
            <div>
              <b>{s.source}</b> → <b>{s.target}</b>
              <span className="flow-kind">{s.kind === "goods" ? "товар" : "деньги"}</span>
              <div className="muted small">{s.note}</div>
            </div>
            <div className="num">{formatKzt(s.amount)}</div>
          </li>
        ))}
      </ol>
    </>
  );
}

function Scenario({ deal }: { deal: Deal }) {
  if (!deal.scenario) return null;
  return (
    <>
      <h3>Если случится неурожай</h3>
      <p className="muted small">
        Кто закрывает долг при разной потере урожая. Порядок: выручка фермера (до 60% идёт на долг) → страховка урожая
        с франшизой 30% → остаток переносится на следующий сезон с доплатой 8%. Банку платформа гасит вовремя в любом
        случае — первый убыток на ней.
      </p>
      <div className="table-scroll">
        <table className="table scenario">
          <thead>
            <tr>
              <th>Потеря урожая</th>
              <th className="num">Платит фермер</th>
              <th className="num">Страховка</th>
              <th className="num">Перенос</th>
              <th className="num">Итог платформы</th>
              <th className="num">Итог без страховки</th>
            </tr>
          </thead>
          <tbody>
            {deal.scenario.map((r) => (
              <tr key={r.loss}>
                <td>{formatPct(r.loss)}</td>
                <td className="num">{formatKzt(r.from_farmer)}</td>
                <td className="num">{formatKzt(r.insurance)}</td>
                <td className="num">{formatKzt(r.rollover)}</td>
                <td className={r.platform_result < 0 ? "num danger" : "num"}>{formatKzt(r.platform_result)}</td>
                <td className={r.platform_result_uninsured < 0 ? "num danger" : "num"}>
                  {formatKzt(r.platform_result_uninsured)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function MonitoringBlock({ deal, busy, onRefresh }: { deal: Deal; busy: boolean; onRefresh: () => void }) {
  const m = deal.monitoring;
  return (
    <>
      <div className="section-head">
        <h3>Спутниковый мониторинг сезона</h3>
        <button className="btn btn-ghost" disabled={busy} onClick={onRefresh}>
          {busy ? "Загружаем снимки…" : m ? "Обновить" : "Проверить поле"}
        </button>
      </div>
      {!m && <p className="muted">Проверьте, засеяно ли поле и как развивается посев относительно его нормы.</p>}
      {m && (
        <>
          {m.note && <p className="notice">{m.note}</p>}
          <p className={`monitor-status monitor-${m.status}`}>
            <b>{MONITORING_LABEL[m.status]}.</b> {m.message}
          </p>
          <MonitoringChart m={m} />
          <p className="muted small">
            Проверено {formatDate(m.checked_at)} · источник: {m.source === "mock" ? "демо-данные" : "Sentinel-2"}
          </p>
        </>
      )}
    </>
  );
}

export function DealPanel({
  app,
  token,
  onChange,
}: {
  app: Application;
  token: string;
  onChange: (app: Application) => void;
}) {
  const deal = app.deal!;
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [payment, setPayment] = useState("");

  async function run(key: string, call: () => Promise<Application>) {
    setBusy(key);
    setError(null);
    try {
      onChange(await call());
      setPayment("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Сервер недоступен");
    } finally {
      setBusy(null);
    }
  }

  const act = (action: DealAction, amount?: number) =>
    run(action, () => api.analyst.dealAction(token, app.id, action, amount));
  const next = NEXT_ACTION[deal.status];
  const canPay = ["delivered", "sowing_confirmed", "restructured"].includes(deal.status);
  const left = deal.farmer_total - deal.paid_amount;

  return (
    <section className="card deal">
      <h3 className="first">Сделка</h3>
      <DealTrack deal={deal} />
      <Remaining deal={deal} />
      {error && <div className="alert">{error}</div>}

      {deal.status !== "repaid" && (
        <div className="deal-actions">
          {next && (
            <button className="btn btn-primary" disabled={!!busy} onClick={() => act(next.action)}>
              {next.label}
            </button>
          )}
          {canPay && (
            <div className="row">
              <input
                className="input"
                type="number"
                min={1}
                max={left}
                placeholder={`Платёж фермера, до ${left}`}
                value={payment}
                onChange={(e) => setPayment(e.target.value)}
              />
              <button
                className="btn btn-ghost"
                disabled={!!busy || !Number(payment)}
                onClick={() => act("record_payment", Number(payment))}
              >
                Внести платёж
              </button>
            </div>
          )}
          {(deal.status === "delivered" || deal.status === "sowing_confirmed") && (
            <button className="btn btn-danger" disabled={!!busy} onClick={() => act("restructure")}>
              Неурожай: перенести остаток на след. сезон
            </button>
          )}
        </div>
      )}

      <MonitoringBlock
        deal={deal}
        busy={busy === "monitoring"}
        onRefresh={() => run("monitoring", () => api.analyst.refreshMonitoring(token, app.id))}
      />
      <Economics deal={deal} />
      <Flow deal={deal} />
      <Scenario deal={deal} />

      {deal.events.length > 0 && (
        <>
          <h3>Журнал сделки</h3>
          <ul className="events">
            {deal.events.map((e, i) => (
              <li key={i}>
                <span className="muted">{formatDate(e.at)}</span> · {e.note}
                {e.amount !== null && <b> · {formatKzt(e.amount)}</b>}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
