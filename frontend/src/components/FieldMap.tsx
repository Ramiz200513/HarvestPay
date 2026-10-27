// Карта со спутниковой подложкой. Два режима:
//  * редактирование (onChange передан): каждый клик добавляет вершину контура поля;
//  * просмотр (onChange нет): просто показывает сохранённый полигон и приближает к нему.
//
// Важно про порядок координат: Leaflet работает с [широта, долгота],
// а GeoJSON (и наш бэкенд) — с [долгота, широта]. Переводим на границе этого компонента.
import { useEffect } from "react";
import {
  CircleMarker,
  MapContainer,
  Polygon,
  Polyline,
  TileLayer,
  useMap,
  useMapEvents,
} from "react-leaflet";
import type { LatLngTuple } from "leaflet";
import type { GeoPolygon, LngLat } from "../types";
import type { MapFocus } from "./MapSearch";

const DEFAULT_CENTER: LatLngTuple = [51.25, 71.2]; // пашни под Астаной
const toLatLng = ([lng, lat]: LngLat): LatLngTuple => [lat, lng];

function ClickToAdd({ onAdd }: { onAdd: (p: LngLat) => void }) {
  useMapEvents({
    click(e) {
      // округляем до 6 знаков (~10 см) — больше точности спутник всё равно не даёт
      onAdd([+e.latlng.lng.toFixed(6), +e.latlng.lat.toFixed(6)]);
    },
  });
  return null;
}

function FitTo({ points }: { points: LngLat[] }) {
  const map = useMap();
  useEffect(() => {
    if (points.length >= 3) map.fitBounds(points.map(toLatLng), { padding: [24, 24] });
  }, [map]); // подгоняем один раз при открытии, иначе карта прыгала бы при каждом клике
  return null;
}

// Перелёт к найденному месту (поиск или «Я здесь»)
function FlyTo({ focus }: { focus?: MapFocus }) {
  const map = useMap();
  useEffect(() => {
    if (focus) map.flyTo([focus.lat, focus.lng], focus.zoom, { duration: 0.8 });
  }, [map, focus]);
  return null;
}

interface Props {
  points: LngLat[];
  onChange?: (points: LngLat[]) => void;
  height?: number;
  others?: GeoPolygon[]; // поля других хозяйств, с которыми есть пересечение (видит аналитик)
  focus?: MapFocus;
}

export default function FieldMap({ points, onChange, height = 420, others = [], focus }: Props) {
  const editable = Boolean(onChange);
  const latlngs = points.map(toLatLng);

  return (
    <div className={editable ? "map map-edit" : "map"} style={{ height }}>
      <MapContainer
        center={points.length ? latlngs[0] : DEFAULT_CENTER}
        zoom={13}
        style={{ height: "100%", width: "100%" }}
        scrollWheelZoom
      >
        <TileLayer
          url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
          attribution="Снимки &copy; Esri, Maxar, Earthstar Geographics"
          maxZoom={18}
        />
        {editable && onChange && <ClickToAdd onAdd={(p) => onChange([...points, p])} />}
        <FitTo points={points} />
        <FlyTo focus={focus} />

        {others.map((g, i) => (
          <Polygon
            key={`other-${i}`}
            positions={g.coordinates[0].map(toLatLng)}
            pathOptions={{ color: "#E5484D", weight: 2, dashArray: "6 6", fillOpacity: 0.12 }}
          />
        ))}

        {latlngs.length >= 3 ? (
          <Polygon positions={latlngs} pathOptions={{ color: "#E3A72F", weight: 2, fillOpacity: 0.18 }} />
        ) : (
          latlngs.length === 2 && <Polyline positions={latlngs} pathOptions={{ color: "#E3A72F", weight: 2 }} />
        )}

        {editable &&
          latlngs.map((p, i) => (
            <CircleMarker
              key={`${p[0]}-${p[1]}-${i}`}
              center={p}
              radius={5}
              pathOptions={{ color: "#FFFFFF", weight: 2, fillColor: "#E3A72F", fillOpacity: 1 }}
            />
          ))}
      </MapContainer>
    </div>
  );
}
