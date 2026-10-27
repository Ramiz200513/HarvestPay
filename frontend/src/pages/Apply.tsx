// Мастер подачи заявки: 1) БИН → 2) поле на карте → 3) товары → отправка.
// Состояние всех шагов живёт здесь, в одном компоненте, поэтому при переходе «Назад» ничего не теряется.
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, api } from "../api";
import ChecksList from "../components/ChecksList";
import FieldMap from "../components/FieldMap";
import { CATEGORY_LABEL, formatHa, formatKzt } from "../lib/format";
import { closeRing, ringAreaHa } from "../lib/geo";
import { readFieldFile } from "../lib/kml";
import { rememberApplication } from "../lib/storage";
import type { Farm, FieldCheck, LngLat, Product, PublicConfig } from "../types";

const CROPS = ["Пшеница яровая", "Ячмень", "Подсолнечник", "Рапс", "Лён масличный", "Овёс"];

const DEMO_BINS = [
  { bin: "150343000016", note: "КХ, проходит проверку" },
  { bin: "180240000011", note: "ТОО, проходит проверку" },
  { bin: "250643000018", note: "молодое КХ — не выше класса B" },
  { bin: "190340000017", note: "есть суд — не выше класса B" },
  { bin: "170343000014", note: "налоговый долг — отказ" },
  { bin: "160540000019", note: "арест счетов — отказ" },
  { bin: "080740000019", note: "ликвидировано — отказ" },
  { bin: "260440000016", note: "зарегистрировано недавно — отказ" },
];

export default function Apply() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [config, setConfig] = useState<PublicConfig | null>(null);

  // шаг 1
  const [bin, setBin] = useState("");
  const [farm, setFarm] = useState<Farm | null>(null);
  const [checking, setChecking] = useState(false);

  // шаг 2
  const [points, setPoints] = useState<LngLat[]>([]);
  const [crop, setCrop] = useState(CROPS[0]);
  const [cadastral, setCadastral] = useState("");
  const [importNote, setImportNote] = useState<string | null>(null);
  const [mapKey, setMapKey] = useState(0); // смена key пересоздаёт карту — она приблизится к загруженному полю
  const [fieldCheck, setFieldCheck] = useState<FieldCheck | null>(null);
  const [fieldError, setFieldError] = useState<string | null>(null);

  // шаг 3
  const [products, setProducts] = useState<Product[]>([]);
  const [qty, setQty] = useState<Record<number, number>>({});

  const [error, setError] = useState<{ message: string; reasons: string[] } | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api.config().then(setConfig).catch(() => setConfig(null));
    api.products().then(setProducts).catch(() => setProducts([]));
  }, []);

  const areaHa = useMemo(() => ringAreaHa(points), [points]);

  // Пока фермер рисует, спрашиваем сервер: корректен ли контур и не заявлен ли участок другим
  // хозяйством. Запрос уходит через 600 мс после последнего клика (debounce), а не на каждый клик.
  useEffect(() => {
    setFieldCheck(null);
    setFieldError(null);
    if (points.length < 3) return;
    const timer = window.setTimeout(() => {
      api
        .checkField({ type: "Polygon", coordinates: closeRing(points) }, farm?.bin)
        .then(setFieldCheck)
        .catch((e) => setFieldError(e instanceof ApiError ? e.message : null));
    }, 600);
    return () => window.clearTimeout(timer);
  }, [points, farm?.bin]);
  const total = products.reduce((sum, p) => sum + (qty[p.id] ?? 0) * p.price, 0);
  const estimatedLimit = config ? Math.round((areaHa * config.limit_per_ha) / 1000) * 1000 : 0;

  async function importFile(file: File | undefined) {
    if (!file) return;
    setImportNote(null);
    try {
      const imported = await readFieldFile(file);
      setPoints(imported.points);
      setMapKey((k) => k + 1);
      setImportNote(
        imported.polygons > 1
          ? `В файле ${imported.polygons} полигонов — загружен первый. Для других полей подайте отдельные заявки.`
          : `Контур загружен из файла ${file.name}: ${imported.points.length} точек.`,
      );
    } catch (e) {
      setImportNote(`Не удалось прочитать файл: ${e instanceof Error ? e.message : "неизвестная ошибка"}`);
    }
  }

  function showError(e: unknown) {
    if (e instanceof ApiError) setError({ message: e.message, reasons: e.reasons });
    else setError({ message: "Сервер недоступен. Запущен ли бэкенд?", reasons: [] });
  }

  async function checkBin(value = bin) {
    setError(null);
    setChecking(true);
    setFarm(null);
    try {
      setFarm(await api.verifyBin(value.replace(/\s/g, "")));
    } catch (e) {
      showError(e);
    } finally {
      setChecking(false);
    }
  }

  async function submit() {
    if (!farm) return;
    setError(null);
    setSubmitting(true);
    try {
      const items = Object.entries(qty)
        .filter(([, q]) => q > 0)
        .map(([id, q]) => ({ product_id: Number(id), quantity: q }));
      const res = await api.createApplication({
        bin: farm.bin,
        field: {
          geometry: { type: "Polygon", coordinates: closeRing(points) },
          crop,
          cadastral_number: cadastral.trim() || undefined,
        },
        items,
      });
      rememberApplication({ id: res.id, farm: farm.name ?? farm.bin, createdAt: new Date().toISOString() });
      navigate(`/applications/${res.id}`);
    } catch (e) {
      showError(e);
      setSubmitting(false);
    }
  }

  const grouped = products.reduce<Record<string, Product[]>>((acc, p) => {
    (acc[p.category] ??= []).push(p);
    return acc;
  }, {});

  return (
    <div className="container page">
      <h1>Заявка на рассрочку</h1>
      <ol className="stepper">
        {["Хозяйство", "Поле", "Товары"].map((label, i) => (
          <li key={label} className={step === i + 1 ? "active" : step > i + 1 ? "done" : ""}>
            <span>{i + 1}</span> {label}
          </li>
        ))}
      </ol>

      {config?.satellite_provider === "mock" && (
        <p className="notice">
          Демо-режим: спутниковые данные синтетические (детерминированы по координатам поля)
          {config.climate_provider === "openmeteo" && ", климат района — настоящий (Open-Meteo)"}. Для реальных
          снимков подключите Copernicus Data Space или Google Earth Engine — см. README.
        </p>
      )}

      {error && (
        <div className="alert">
          <b>{error.message}</b>
          {error.reasons.length > 0 && (
            <ul>
              {error.reasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {step === 1 && (
        <section className="card">
          <label className="label" htmlFor="bin">
            БИН хозяйства
          </label>
          <div className="row">
            <input
              id="bin"
              className="input mono"
              inputMode="numeric"
              maxLength={14}
              placeholder="12 цифр"
              value={bin}
              onChange={(e) => setBin(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && checkBin()}
            />
            <button className="btn btn-primary" disabled={checking || bin.replace(/\s/g, "").length !== 12} onClick={() => checkBin()}>
              {checking ? "Проверяем…" : "Проверить"}
            </button>
          </div>

          {config?.registry_provider === "mock" && (
            <div className="demo-bins">
              <span className="muted">Демо-БИН:</span>
              {DEMO_BINS.map((d) => (
                <button
                  key={d.bin}
                  className="chip"
                  onClick={() => {
                    setBin(d.bin);
                    checkBin(d.bin);
                  }}
                >
                  <span className="mono">{d.bin}</span> <span className="muted">{d.note}</span>
                </button>
              ))}
            </div>
          )}

          {farm && (
            <div className={farm.status === "verified" ? "farm-card ok" : "farm-card bad"}>
              <div className="farm-name">{farm.name ?? "Организация"}</div>
              <div className="muted">
                {farm.legal_form}
                {farm.registered_at && ` · зарегистрировано ${new Date(farm.registered_at).getFullYear()}`}
              </div>
              {farm.status === "verified" ? (
                <div className="ok-text">✓ Хозяйство прошло проверку</div>
              ) : (
                <ul>
                  {farm.reasons.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
              )}
              <ChecksList checks={farm.checks} />
            </div>
          )}

          <div className="actions">
            <button className="btn btn-primary" disabled={farm?.status !== "verified"} onClick={() => setStep(2)}>
              Дальше: поле
            </button>
          </div>
        </section>
      )}

      {step === 2 && (
        <section className="card">
          <div className="field-intro">
            <p>
              Кликайте по углам поля на снимке — контур замкнётся автоматически. Колесо мыши — приблизить. Или
              загрузите готовые границы из Google Earth или агросервиса.
            </p>
            <label className="btn btn-ghost file-btn">
              Загрузить KML / GeoJSON
              <input
                type="file"
                accept=".kml,.geojson,.json"
                onChange={(e) => {
                  importFile(e.target.files?.[0]);
                  e.target.value = ""; // тот же файл можно выбрать повторно
                }}
              />
            </label>
          </div>
          {importNote && <p className="notice">{importNote}</p>}
          <FieldMap key={mapKey} points={points} onChange={setPoints} />
          <div className="map-toolbar">
            <span>
              Точек: <b>{points.length}</b> · Площадь: <b>{formatHa(areaHa)}</b>
            </span>
            <button className="btn btn-ghost" disabled={!points.length} onClick={() => setPoints(points.slice(0, -1))}>
              Отменить точку
            </button>
            <button className="btn btn-ghost" disabled={!points.length} onClick={() => setPoints([])}>
              Очистить
            </button>
          </div>
          {fieldError && <div className="alert">{fieldError}</div>}
          {fieldCheck && fieldCheck.overlaps.length > 0 && (
            <div className="notice warn">
              <b>Этот участок уже заявлен другим хозяйством</b> — пересечение{" "}
              {formatHa(fieldCheck.overlaps[0].overlap_ha)} ({Math.round(fieldCheck.overlaps[0].share * 100)}% поля).
              Заявку можно подать, но автоматически её не одобрят: аналитик попросит документы на землю (договор
              аренды или акт на право пользования). Если контур залез на соседа случайно — поправьте точки.
            </div>
          )}
          <label className="label" htmlFor="crop">
            Культура в этом сезоне
          </label>
          <select id="crop" className="input" value={crop} onChange={(e) => setCrop(e.target.value)}>
            {CROPS.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
          <label className="label" htmlFor="cadastral">
            Кадастровый номер участка <span className="muted">(необязательно)</span>
          </label>
          <input
            id="cadastral"
            className="input mono"
            placeholder="например 01:011:002:345"
            maxLength={32}
            value={cadastral}
            onChange={(e) => setCadastral(e.target.value)}
          />
          <p className="muted small">Ускорит проверку: аналитик сверит контур с данными ГосКадастра.</p>
          <div className="actions">
            <button className="btn btn-ghost" onClick={() => setStep(1)}>
              Назад
            </button>
            <button className="btn btn-primary" disabled={points.length < 3 || areaHa < 1 || Boolean(fieldError)}
              onClick={() => setStep(3)}>
              Дальше: товары
            </button>
          </div>
        </section>
      )}

      {step === 3 && (
        <section className="card">
          {Object.entries(grouped).map(([category, list]) => (
            <div key={category} className="catalog-group">
              <h3>{CATEGORY_LABEL[category] ?? category}</h3>
              {list.map((p) => (
                <div key={p.id} className="product">
                  <div>
                    <div>{p.name}</div>
                    <div className="muted">
                      {p.supplier} · {formatKzt(p.price)} за {p.unit}
                    </div>
                  </div>
                  <input
                    className="input qty"
                    type="number"
                    min={0}
                    value={qty[p.id] ?? ""}
                    placeholder="0"
                    aria-label={`Количество: ${p.name}`}
                    onChange={(e) => setQty({ ...qty, [p.id]: Math.max(0, Math.floor(Number(e.target.value) || 0)) })}
                  />
                </div>
              ))}
            </div>
          ))}

          <div className="summary">
            <div>
              Итого к рассрочке: <b>{formatKzt(total)}</b>
            </div>
            {estimatedLimit > 0 && (
              <div className="muted">
                Максимальный лимит для {formatHa(areaHa)} при классе A —{" "}
                {formatKzt(Math.min(estimatedLimit, config?.max_limit_a ?? estimatedLimit))}
                {config && estimatedLimit > config.max_limit_a && " (потолок на одну заявку)"}
              </div>
            )}
            <div className="muted small">
              Товар поставщики отгружают перед севом, а вы платите двумя платежами после уборки — 15 октября и
              15 ноября.
            </div>
          </div>

          <div className="actions">
            <button className="btn btn-ghost" onClick={() => setStep(2)}>
              Назад
            </button>
            <button className="btn btn-primary" disabled={total <= 0 || submitting} onClick={submit}>
              {submitting ? "Отправляем…" : "Отправить заявку"}
            </button>
          </div>
        </section>
      )}
    </div>
  );
}
