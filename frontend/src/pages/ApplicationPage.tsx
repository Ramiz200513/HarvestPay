// Страница заявки. Пока статус pending/processing — раз в 2 секунды спрашиваем сервер (polling),
// пока заявка у аналитика — раз в 15 секунд.
// Это проще WebSocket и для расчёта длиной 10–60 секунд вполне достаточно.
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, api } from "../api";
import ApplicationDetails, { StatusPill } from "../components/ApplicationDetails";
import type { Application, PublicConfig } from "../types";

const IN_PROGRESS = new Set(["pending", "processing"]);
const EXPECTED_SECONDS = 40; // типичный расчёт с настоящим спутником — 10–60 с

// Экран ожидания: этапы, прошедшее время и честная полоса прогресса (по времени, а не по факту —
// сервер не сообщает долю выполнения, поэтому полоса замедляется и не доходит до конца сама)
function Waiting({ app, config }: { app: Application; config: PublicConfig | null }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 500);
    return () => window.clearInterval(t);
  }, []);
  // SQLite отдаёт время без часового пояса — это UTC
  const started = Date.parse(/(Z|[+-]\d\d:\d\d)$/.test(app.created_at) ? app.created_at : `${app.created_at}Z`);
  const elapsed = Math.max(0, Math.round((now - started) / 1000));
  const progress = Math.min(95, 100 * (1 - Math.exp(-elapsed / EXPECTED_SECONDS)));
  const seasons = config?.seasons ?? 7;
  const lastYear = new Date().getMonth() >= 9 ? new Date().getFullYear() : new Date().getFullYear() - 1;
  const source =
    config?.satellite_provider === "cdse"
      ? "Sentinel-2 (Copernicus)"
      : config?.satellite_provider === "gee"
        ? "Sentinel-2 (Google Earth Engine)"
        : "демо-данные";
  const processing = app.status === "processing";

  return (
    <section className="card progress">
      <h3>Считаем решение по вашему полю</h3>
      <div className="progress-bar" role="progressbar" aria-valuenow={Math.round(progress)} aria-valuemin={0} aria-valuemax={100}>
        <div style={{ width: `${progress}%` }} />
      </div>
      <ul className="progress-list">
        <li className="done">Хозяйство проверено по реестру, контур поля принят</li>
        <li className={processing ? "active" : ""}>
          {processing ? "Загружаем снимки" : "Ставим в очередь загрузку снимков"} поля за {seasons} сезонов (
          {lastYear - seasons + 1}–{lastYear}) · {source}
        </li>
        <li className={processing && elapsed > 8 ? "active" : ""}>Убираем облака и считаем NDVI по каждому снимку</li>
        <li>Считаем индекс стабильности, класс риска и лимит</li>
      </ul>
      <p className="muted">
        Прошло {elapsed} с · обычно 10–60 секунд. Страницу можно не обновлять — результат появится сам.
        {elapsed > 90 && " Сервис снимков сегодня отвечает медленно, расчёт продолжается."}
      </p>
    </section>
  );
}

export default function ApplicationPage() {
  const { id = "" } = useParams();
  const [app, setApp] = useState<Application | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [config, setConfig] = useState<PublicConfig | null>(null);

  useEffect(() => {
    api.config().then(setConfig).catch(() => setConfig(null));
  }, []);

  useEffect(() => {
    let timer: number | undefined;
    let cancelled = false;

    async function load() {
      try {
        const data = await api.application(id);
        if (cancelled) return;
        setApp(data);
        setError(null);
        // в работе — опрашиваем часто; ждёт аналитика — редко; финальный статус — перестаём
        if (IN_PROGRESS.has(data.status)) timer = window.setTimeout(load, 2000);
        else if (data.status === "review") timer = window.setTimeout(load, 15000);
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof ApiError ? e.message : "Сервер недоступен");
        // 404 — такой заявки нет, повторять бессмысленно; иначе сеть моргнула — пробуем ещё раз
        if (!(e instanceof ApiError && e.status === 404)) timer = window.setTimeout(load, 5000);
      }
    }
    load();

    // при уходе со страницы останавливаем опрос, иначе запросы продолжат идти в фоне
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [id]);

  if (error && !app) {
    return (
      <div className="container page">
        <div className="alert">{error}</div>
        <Link to="/">На главную</Link>
      </div>
    );
  }
  if (!app) return <div className="container page muted">Загружаем заявку…</div>;

  return (
    <div className="container page">
      <div className="page-head">
        <div>
          <h1>Заявка {app.farm.name}</h1>
          <p className="muted mono">№ {app.id}</p>
        </div>
        <StatusPill status={app.status} />
      </div>

      {IN_PROGRESS.has(app.status) && <Waiting app={app} config={config} />}

      {app.status === "error" && (
        <div className="alert">
          <b>Не получилось посчитать решение.</b> {app.error_message ?? "Техническая ошибка."} Заявка сохранена — аналитик перезапустит расчёт, как только сервис снимков снова заработает.
        </div>
      )}

      {app.status === "review" && (
        <p className="notice">
          Автоматической оценки недостаточно — заявку проверит кредитный аналитик. Страница обновится сама, когда
          решение будет принято.
        </p>
      )}

      <ApplicationDetails app={app} />
    </div>
  );
}
