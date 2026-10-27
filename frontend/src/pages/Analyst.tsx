// Кабинет кредитного аналитика: вход по токену, очередь заявок, ручное решение по классу C,
// портфель сделок и кредитная линия, шаги сделки и спутниковый мониторинг.
import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "../api";
import ApplicationDetails, { ClassBadge, StatusPill } from "../components/ApplicationDetails";
import { DealPanel } from "../components/DealPanel";
import PortfolioView from "../components/PortfolioView";
import { DEAL_STATUS_LABEL, formatDate, formatHa, formatKzt } from "../lib/format";
import { getAnalystToken, setAnalystToken } from "../lib/storage";
import type { Application, ApplicationListItem } from "../types";

const FILTERS = [
  { value: "review", label: "На проверке" },
  { value: "", label: "Все" },
  { value: "approved", label: "Одобренные" },
  { value: "rejected", label: "Отказы" },
  { value: "error", label: "С ошибкой" },
];

export default function Analyst() {
  const [token, setToken] = useState(getAnalystToken());
  const [tokenInput, setTokenInput] = useState("");
  const [tab, setTab] = useState<"queue" | "portfolio">("queue");
  const [filter, setFilter] = useState("review");
  const [list, setList] = useState<ApplicationListItem[]>([]);
  const [selected, setSelected] = useState<Application | null>(null);
  const [amount, setAmount] = useState("");
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const handleError = useCallback((e: unknown) => {
    if (e instanceof ApiError && e.status === 401) {
      setAnalystToken(null);
      setToken("");
      setError("Неверный токен — войдите заново");
    } else setError(e instanceof ApiError ? e.message : "Сервер недоступен");
  }, []);

  const reload = useCallback(() => {
    if (!token) return;
    api.analyst.list(token, filter || undefined).then(setList).catch(handleError);
  }, [token, filter, handleError]);

  useEffect(reload, [reload]);

  async function open(id: string) {
    setError(null);
    try {
      const app = await api.analyst.get(token, id);
      setSelected(app);
      setAmount(String(app.requested_amount));
      setComment("");
    } catch (e) {
      handleError(e);
    }
  }

  async function decide(action: "approve" | "reject") {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await api.analyst.decide(token, selected.id, {
        action,
        approved_amount: action === "approve" ? Number(amount) : undefined,
        comment: comment || undefined,
      });
      setSelected(updated);
      reload();
    } catch (e) {
      handleError(e);
    } finally {
      setBusy(false);
    }
  }

  async function retry() {
    if (!selected) return;
    try {
      setSelected(await api.analyst.retry(token, selected.id));
      reload();
    } catch (e) {
      handleError(e);
    }
  }

  if (!token) {
    return (
      <div className="container page narrow">
        <h1>Кабинет аналитика</h1>
        {error && <div className="alert">{error}</div>}
        <section className="card">
          <label className="label" htmlFor="token">
            Токен доступа
          </label>
          <div className="row">
            <input
              id="token"
              className="input"
              type="password"
              value={tokenInput}
              onChange={(e) => setTokenInput(e.target.value)}
            />
            <button
              className="btn btn-primary"
              disabled={!tokenInput}
              onClick={() => {
                setAnalystToken(tokenInput);
                setToken(tokenInput);
                setError(null);
              }}
            >
              Войти
            </button>
          </div>
          <p className="muted">Токен задаётся переменной HP_ANALYST_TOKEN на сервере (в демо — analyst-demo-token).</p>
        </section>
      </div>
    );
  }

  return (
    <div className="container page wide">
      <div className="page-head">
        <h1>Кабинет аналитика</h1>
        <button
          className="btn btn-ghost"
          onClick={() => {
            setAnalystToken(null);
            setToken("");
          }}
        >
          Выйти
        </button>
      </div>
      {error && <div className="alert">{error}</div>}

      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={tab === "queue"} className={tab === "queue" ? "tab active" : "tab"}
          onClick={() => setTab("queue")}>
          Заявки
        </button>
        <button role="tab" aria-selected={tab === "portfolio"} className={tab === "portfolio" ? "tab active" : "tab"}
          onClick={() => setTab("portfolio")}>
          Портфель и деньги
        </button>
      </div>

      {tab === "portfolio" && (
        <PortfolioView
          token={token}
          onOpen={(id) => {
            setTab("queue");
            setFilter("approved");
            open(id);
          }}
        />
      )}

      {tab === "queue" && (
      <>
      <div className="filters">
        {FILTERS.map((f) => (
          <button
            key={f.value}
            className={filter === f.value ? "chip active" : "chip"}
            onClick={() => {
              setFilter(f.value);
              setSelected(null);
            }}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className="analyst-layout">
        <div className="card list">
          {list.length === 0 && <p className="muted">Заявок нет</p>}
          {list.map((a) => (
            <button
              key={a.id}
              className={selected?.id === a.id ? "list-item active" : "list-item"}
              onClick={() => open(a.id)}
            >
              <div className="list-item-head">
                <b>{a.farm_name}</b>
                <span className="list-item-badges">
                  {a.has_overlaps && <span className="pill pill-rejected">пересечение</span>}
                  {a.score_class && <ClassBadge value={a.score_class} />}
                </span>
              </div>
              <div className="muted">
                {a.crop} · {formatHa(a.area_ha)} · {formatKzt(a.requested_amount)}
              </div>
              <div className="list-item-foot">
                <StatusPill status={a.status} />
                <span className="muted">{formatDate(a.created_at)}</span>
              </div>
              {a.deal_status && <div className="muted small">Сделка: {DEAL_STATUS_LABEL[a.deal_status]}</div>}
            </button>
          ))}
        </div>

        <div>
          {!selected && <p className="muted">Выберите заявку слева</p>}
          {selected && (
            <>
              {selected.status === "review" && (
                <section className="card">
                  <h3>Решение аналитика</h3>
                  <div className="row">
                    <label className="label" htmlFor="amount">
                      Сумма, ₸
                    </label>
                    <input
                      id="amount"
                      className="input"
                      type="number"
                      min={1}
                      max={selected.requested_amount}
                      value={amount}
                      onChange={(e) => setAmount(e.target.value)}
                    />
                  </div>
                  <textarea
                    className="input"
                    rows={2}
                    placeholder="Комментарий (например: проверено выездом, есть страховка урожая)"
                    value={comment}
                    onChange={(e) => setComment(e.target.value)}
                  />
                  <div className="actions">
                    <button className="btn btn-danger" disabled={busy} onClick={() => decide("reject")}>
                      Отказать
                    </button>
                    <button className="btn btn-primary" disabled={busy || !Number(amount)} onClick={() => decide("approve")}>
                      Одобрить
                    </button>
                  </div>
                </section>
              )}
              {selected.status === "error" && (
                <section className="card">
                  <p>{selected.error_message}</p>
                  <button className="btn btn-primary" onClick={retry}>
                    Перезапустить расчёт
                  </button>
                </section>
              )}
              {selected.deal && (
                <DealPanel
                  app={selected}
                  token={token}
                  onChange={(updated) => {
                    setSelected(updated);
                    reload();
                  }}
                />
              )}
              <ApplicationDetails app={selected} />
            </>
          )}
        </div>
      </div>
      </>
      )}
    </div>
  );
}
