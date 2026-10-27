// Поиск места на карте: село / район через OpenStreetMap (Nominatim) или координаты «51.12, 71.43».
// Плюс кнопка «Я здесь» — геолокация браузера (удобно, когда фермер стоит на своём поле).
import { useState } from "react";

export interface MapFocus {
  lat: number;
  lng: number;
  zoom: number;
  seq: number; // меняется при каждом поиске — карта перелетает, даже если место то же
}

interface Place {
  name: string;
  lat: number;
  lng: number;
  zoom: number;
}

const COORDS = /^\s*(-?\d{1,2}(?:[.,]\d+)?)\s*[,;\s]\s*(-?\d{1,3}(?:[.,]\d+)?)\s*$/;

// Населённый пункт — ближе, область или район — дальше
function zoomFor(type: string) {
  if (["state", "region", "province"].includes(type)) return 8;
  if (["county", "district", "municipality"].includes(type)) return 10;
  if (["city", "town"].includes(type)) return 12;
  return 14;
}

export default function MapSearch({ onFocus }: { onFocus: (f: Omit<MapFocus, "seq">) => void }) {
  const [query, setQuery] = useState("");
  const [places, setPlaces] = useState<Place[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function search() {
    setPlaces([]);
    setStatus(null);
    const coords = query.match(COORDS);
    if (coords) {
      const lat = Number(coords[1].replace(",", "."));
      const lng = Number(coords[2].replace(",", "."));
      if (Math.abs(lat) <= 90 && Math.abs(lng) <= 180) {
        onFocus({ lat, lng, zoom: 15 });
        return;
      }
    }
    if (query.trim().length < 2) return;
    setBusy(true);
    try {
      const params = new URLSearchParams({
        q: query.trim(),
        format: "jsonv2",
        countrycodes: "kz",
        limit: "5",
        "accept-language": "ru",
      });
      const res = await fetch(`https://nominatim.openstreetmap.org/search?${params}`);
      if (!res.ok) throw new Error(String(res.status));
      const found = (await res.json()) as { display_name: string; lat: string; lon: string; addresstype?: string; type: string }[];
      const list = found.map((p) => ({
        name: p.display_name.split(", ").slice(0, 3).join(", "),
        lat: Number(p.lat),
        lng: Number(p.lon),
        zoom: zoomFor(p.addresstype ?? p.type),
      }));
      if (list.length === 0) setStatus("Ничего не нашли. Попробуйте название села или района, или координаты.");
      else if (list.length === 1) onFocus(list[0]);
      else setPlaces(list);
    } catch {
      setStatus("Поиск сейчас недоступен — найдите поле на карте вручную или введите координаты.");
    } finally {
      setBusy(false);
    }
  }

  function locate() {
    setStatus(null);
    if (!navigator.geolocation) {
      setStatus("Браузер не умеет определять местоположение.");
      return;
    }
    setBusy(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setBusy(false);
        onFocus({ lat: pos.coords.latitude, lng: pos.coords.longitude, zoom: 15 });
      },
      () => {
        setBusy(false);
        setStatus("Не удалось определить местоположение — разрешите доступ к геолокации в браузере.");
      },
      { enableHighAccuracy: true, timeout: 10000 },
    );
  }

  return (
    <div className="map-search">
      <form
        className="row"
        onSubmit={(e) => {
          e.preventDefault();
          search();
        }}
      >
        <input
          className="input"
          placeholder="Село, район или координаты: 51.12, 71.43"
          aria-label="Найти место на карте"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button className="btn btn-ghost" type="submit" disabled={busy || query.trim().length < 2}>
          {busy ? "Ищем…" : "Найти"}
        </button>
        <button className="btn btn-ghost" type="button" onClick={locate} disabled={busy} title="Показать, где я сейчас">
          Я здесь
        </button>
      </form>
      {places.length > 0 && (
        <ul className="map-search-results">
          {places.map((p) => (
            <li key={`${p.lat},${p.lng}`}>
              <button
                type="button"
                onClick={() => {
                  onFocus(p);
                  setPlaces([]);
                }}
              >
                {p.name}
              </button>
            </li>
          ))}
        </ul>
      )}
      {status && <p className="muted small">{status}</p>}
    </div>
  );
}
