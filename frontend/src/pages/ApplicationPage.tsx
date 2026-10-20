// Страница заявки. Пока статус pending/processing — раз в 2 секунды спрашиваем сервер (polling),
// пока заявка у аналитика — раз в 15 секунд.
// Это проще WebSocket и для расчёта длиной 10–60 секунд вполне достаточно.
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, api } from "../api";
import ApplicationDetails, { StatusPill } from "../components/ApplicationDetails";
import type { Application } from "../types";

const IN_PROGRESS = new Set(["pending", "processing"]);

export default function ApplicationPage() {
  const { id = "" } = useParams();
  const [app, setApp] = useState<Application | null>(null);
  const [error, setError] = useState<string | null>(null);

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

      {IN_PROGRESS.has(app.status) && (
        <section className="card progress">
          <ul className="progress-list">
            <li className="done">Хозяйство проверено по реестру</li>
            <li className={app.status === "processing" ? "active" : ""}>
              Загружаем снимки поля за последние сезоны и считаем NDVI
            </li>
            <li>Считаем индекс стабильности и лимит</li>
          </ul>
          <p className="muted">Обычно это занимает от нескольких секунд до минуты. Страница обновится сама.</p>
        </section>
      )}

      {app.status === "error" && (
        <div className="alert">
          {app.error_message ?? "Техническая ошибка"} Мы перезапустим расчёт, когда сервис снимков станет доступен.
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
