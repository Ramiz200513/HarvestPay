// Мастер подачи заявки: 1) БИН → 2) поле на карте → 3) товары → 4) проверка и отправка.
// Состояние всех шагов живёт здесь, в одном компоненте, поэтому при переходе «Назад» ничего не теряется,
// а черновик сохраняется в браузере — после обновления страницы фермер продолжит с того же места.
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, api } from "../api";
import ChecksList from "../components/ChecksList";
import FieldMap from "../components/FieldMap";
import MapSearch, { type MapFocus } from "../components/MapSearch";
import { CATEGORY_LABEL, formatHa, formatKzt } from "../lib/format";
import { closeRing, ringAreaHa } from "../lib/geo";
import { readFieldFile } from "../lib/kml";
import { loadDraft, rememberApplication, saveDraft } from "../lib/storage";
import type { Farm, FieldCheck, LngLat, Product, PublicConfig } from "../types";

const CROPS = ["Пшеница яровая", "Ячмень", "Подсолнечник", "Рапс", "Лён масличный", "Овёс"];
const STEPS = ["Хозяйство", "Поле", "Товары", "Проверка"];
const CLASS_B_SHARE = 0.6; // класс B получает 60% лимита — как в backend/app/services/limits.py

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

// Сумма заявки на фоне лимитов: видно заранее, уложится ли фермер в лимит при классе A и B
function LimitMeter({ total, limitA, limitB }: { total: number; limitA: number; limitB: number }) {
  const scale = Math.max(total, limitA) * 1.08 || 1;
  const pct = (v: number) => `${Math.min(100, (v / scale) * 100)}%`;
  const state = total <= limitB ? "ok" : total <= limitA ? "mid" : "over";
  return (
    <div className="limit-meter">
      <div className="limit-track">
        <div className={`limit-fill ${state}`} style={{ width: pct(total) }} />
        <div className="limit-mark below" style={{ left: pct(limitB) }}>
          <span>B · {formatKzt(limitB)}</span>
        </div>
        <div className="limit-mark" style={{ left: pct(limitA) }}>
          <span>A · {formatKzt(limitA)}</span>
        </div>
      </div>
      <p className={`small limit-note ${state}`}>
        {state === "ok" && "Сумма укладывается в лимит и при классе A, и при классе B."}
        {state === "mid" &&
          "При классе A одобрим всю сумму, при классе B — только до отметки B. Можно уменьшить заказ или подать как есть."}
        {state === "over" &&
          "Сумма больше максимального лимита для этого поля: одобрим не больше отметки A. Уменьшите заказ или добавьте поле отдельной заявкой."}
      </p>
    </div>
  );
}

export default function Apply() {
  const navigate = useNavigate();
  const draft = useMemo(loadDraft, []);
  const [step, setStep] = useState(draft?.step ?? 1);
  const [config, setConfig] = useState<PublicConfig | null>(null);

  // шаг 1
  const [bin, setBin] = useState(draft?.bin ?? "");
  const [farm, setFarm] = useState<Farm | null>(draft?.farm ?? null);
  const [checking, setChecking] = useState(false);

  // шаг 2
  const [points, setPoints] = useState<LngLat[]>(draft?.points ?? []);
  const [crop, setCrop] = useState(draft?.crop ?? CROPS[0]);
  const [cadastral, setCadastral] = useState(draft?.cadastral ?? "");
  const [importNote, setImportNote] = useState<string | null>(null);
  const [mapKey, setMapKey] = useState(0); // смена key пересоздаёт карту — она приблизится к загруженному полю
  const [focus, setFocus] = useState<MapFocus | undefined>();
  const [fieldCheck, setFieldCheck] = useState<FieldCheck | null>(null);
  const [fieldError, setFieldError] = useState<string | null>(null);

  // шаг 3
  const [products, setProducts] = useState<Product[]>([]);
  const [qty, setQty] = useState<Record<number, number>>(draft?.qty ?? {});

  const [error, setError] = useState<{ message: string; reasons: string[] } | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api.config().then(setConfig).catch(() => setConfig(null));
    api.products().then(setProducts).catch(() => setProducts([]));
  }, []);

  useEffect(() => {
    if (!submitting) saveDraft({ step, bin, farm, points, crop, cadastral, qty });
  }, [step, bin, farm, points, crop, cadastral, qty, submitting]);

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

  const chosen = products.filter((p) => (qty[p.id] ?? 0) > 0);
  const total = chosen.reduce((sum, p) => sum + qty[p.id] * p.price, 0);
  const rawLimit = config ? Math.round((areaHa * config.limit_per_ha) / 1000) * 1000 : 0;
  const limitA = config ? Math.min(rawLimit, config.max_limit_a) : 0;
  const limitB = config ? Math.min(Math.round((rawLimit * CLASS_B_SHARE) / 1000) * 1000, config.max_limit_b) : 0;

  // На какой шаг можно перейти прямо сейчас: только на пройденные и следующий за ними
  const canOpen = (n: number) =>
    n === 1 ||
    (n === 2 && farm?.status === "verified") ||
    (n === 3 && farm?.status === "verified" && points.length >= 3 && areaHa >= 1 && !fieldError) ||
    (n === 4 && farm?.status === "verified" && points.length >= 3 && total > 0);

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
    else setError({ message: "Нет связи с сервером. Проверьте интернет и попробуйте ещё раз.", reasons: [] });
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

  function startOver() {
    saveDraft(null);
    setStep(1);
    setBin("");
    setFarm(null);
    setPoints([]);
    setCrop(CROPS[0]);
    setCadastral("");
    setQty({});
    setError(null);
    setMapKey((k) => k + 1);
  }

  async function submit() {
    if (!farm) return;
    setError(null);
    setSubmitting(true);
    try {
      const res = await api.createApplication({
        bin: farm.bin,
        field: {
          geometry: { type: "Polygon", coordinates: closeRing(points) },
          crop,
          cadastral_number: cadastral.trim() || undefined,
        },
        items: chosen.map((p) => ({ product_id: p.id, quantity: qty[p.id] })),
      });
      saveDraft(null);
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
  const hasDraft = Boolean(bin || points.length || chosen.length);

  return (
    <div className="container page">
      <div className="page-head">
        <h1>Заявка на рассрочку</h1>
        {hasDraft && (
          <button className="btn btn-ghost small-btn" onClick={startOver}>
            Начать заново
          </button>
        )}
      </div>
      <ol className="stepper">
        {STEPS.map((label, i) => {
          const n = i + 1;
          const state = step === n ? "active" : step > n ? "done" : "";
          return (
            <li key={label} className={state}>
              <button type="button" disabled={step === n || !canOpen(n)} onClick={() => setStep(n)}>
                <span>{step > n ? "✓" : n}</span> {label}
              </button>
            </li>
          );
        })}
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
            <button
              className="btn btn-primary"
              disabled={checking || bin.replace(/\s/g, "").length !== 12}
              onClick={() => checkBin()}
            >
              {checking ? "Проверяем…" : "Проверить"}
            </button>
          </div>
          <p className="muted small">БИН есть в свидетельстве о регистрации и на egov.kz — 12 цифр.</p>

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
              Найдите своё поле — по названию села или координатам — и кликайте по его углам на снимке: контур замкнётся
              автоматически. Или загрузите готовые границы из Google Earth или агросервиса.
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
          <MapSearch onFocus={(f) => setFocus({ ...f, seq: Date.now() })} />
          {importNote && <p className="notice">{importNote}</p>}
          <FieldMap key={mapKey} points={points} onChange={setPoints} focus={focus} />
          <div className="map-toolbar">
            <span>
              Точек: <b>{points.length}</b> · Площадь: <b>{formatHa(areaHa)}</b>
              {points.length > 0 && points.length < 3 && <span className="muted"> · нужно ещё {3 - points.length}</span>}
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
          <div className="two-col form-cols">
            <div>
              <label className="label" htmlFor="crop">
                Культура в этом сезоне
              </label>
              <select id="crop" className="input" value={crop} onChange={(e) => setCrop(e.target.value)}>
                {CROPS.map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="label" htmlFor="cadastral">
                Кадастровый номер <span className="muted">(необязательно)</span>
              </label>
              <input
                id="cadastral"
                className="input mono"
                placeholder="например 01:011:002:345"
                maxLength={32}
                value={cadastral}
                onChange={(e) => setCadastral(e.target.value)}
              />
            </div>
          </div>
          <p className="muted small">Кадастровый номер ускорит проверку: аналитик сверит контур с ГосКадастром.</p>
          <div className="actions">
            <button className="btn btn-ghost" onClick={() => setStep(1)}>
              Назад
            </button>
            <button className="btn btn-primary" disabled={!canOpen(3)} onClick={() => setStep(3)}>
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
                <div key={p.id} className={(qty[p.id] ?? 0) > 0 ? "product picked" : "product"}>
                  <div>
                    <div>{p.name}</div>
                    <div className="muted">
                      {p.supplier} · {formatKzt(p.price)} за {p.unit}
                    </div>
                  </div>
                  <div className="qty-cell">
                    <input
                      className="input qty"
                      type="number"
                      min={0}
                      value={qty[p.id] ?? ""}
                      placeholder="0"
                      aria-label={`Количество: ${p.name}`}
                      onChange={(e) =>
                        setQty({ ...qty, [p.id]: Math.max(0, Math.floor(Number(e.target.value) || 0)) })
                      }
                    />
                    <span className="muted small">{(qty[p.id] ?? 0) > 0 ? formatKzt(qty[p.id] * p.price) : p.unit}</span>
                  </div>
                </div>
              ))}
            </div>
          ))}

          <div className="summary sticky-summary">
            <div className="summary-total">
              Итого к рассрочке: <b>{formatKzt(total)}</b>
            </div>
            {rawLimit > 0 && <LimitMeter total={total} limitA={limitA} limitB={limitB} />}
          </div>

          <div className="actions">
            <button className="btn btn-ghost" onClick={() => setStep(2)}>
              Назад
            </button>
            <button className="btn btn-primary" disabled={!canOpen(4)} onClick={() => setStep(4)}>
              Дальше: проверить заявку
            </button>
          </div>
        </section>
      )}

      {step === 4 && farm && (
        <section className="card review">
          <h2>Проверьте заявку перед отправкой</h2>
          <div className="two-col">
            <div>
              <div className="review-block">
                <div className="review-head">
                  <h3>Хозяйство</h3>
                  <button className="link-btn" onClick={() => setStep(1)}>
                    Изменить
                  </button>
                </div>
                <p>
                  {farm.name} <span className="muted mono">· БИН {farm.bin}</span>
                </p>
              </div>
              <div className="review-block">
                <div className="review-head">
                  <h3>Поле</h3>
                  <button className="link-btn" onClick={() => setStep(2)}>
                    Изменить
                  </button>
                </div>
                <p>
                  {crop} · {formatHa(areaHa)}
                  {cadastral.trim() && <span className="muted mono"> · {cadastral.trim()}</span>}
                </p>
              </div>
              <div className="review-block">
                <div className="review-head">
                  <h3>Товары</h3>
                  <button className="link-btn" onClick={() => setStep(3)}>
                    Изменить
                  </button>
                </div>
                <table className="table">
                  <tbody>
                    {chosen.map((p) => (
                      <tr key={p.id}>
                        <td>{p.name}</td>
                        <td className="num">
                          {qty[p.id]} {p.unit}
                        </td>
                        <td className="num">{formatKzt(qty[p.id] * p.price)}</td>
                      </tr>
                    ))}
                    <tr className="total">
                      <td colSpan={2}>Итого</td>
                      <td className="num">{formatKzt(total)}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
            <FieldMap key={`review-${mapKey}`} points={points} height={300} />
          </div>
          <ul className="review-next">
            <li>Решение придёт через 10–60 секунд: мы загрузим снимки поля за 7 сезонов и посчитаем индекс.</li>
            <li>Товар поставщики отгружают перед севом, а платите вы после уборки — 15 октября и 15 ноября.</li>
          </ul>
          <div className="actions">
            <button className="btn btn-ghost" onClick={() => setStep(3)}>
              Назад
            </button>
            <button className="btn btn-primary" disabled={submitting} onClick={submit}>
              {submitting ? "Отправляем…" : "Отправить заявку"}
            </button>
          </div>
        </section>
      )}
    </div>
  );
}
