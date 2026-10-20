"""Интеграционные тесты API: полный путь заявки через HTTP.

По умолчанию — временная SQLite-база. Чтобы прогнать те же тесты на PostgreSQL + PostGIS:
    HP_TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/harvestpay_test pytest
ВНИМАНИЕ: схема public этой базы очищается перед тестами — не указывайте рабочую БД.

Фоновая задача в TestClient выполняется сразу после ответа, поэтому решение видно в следующем GET."""

import os
import tempfile

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")

# Настройки задаём ДО импорта приложения: движок БД создаётся при импорте app.db
_test_url = os.environ.get("HP_TEST_DATABASE_URL")
if _test_url:
    from sqlalchemy import create_engine, text

    with create_engine(_test_url).begin() as conn:  # чистая схема перед каждым прогоном
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    os.environ["HP_DATABASE_URL"] = _test_url
else:
    os.environ["HP_DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["HP_TASK_MODE"] = "background"
os.environ["HP_SATELLITE_PROVIDER"] = "mock"
os.environ["HP_REGISTRY_PROVIDER"] = "mock"
os.environ["HP_ANALYST_TOKEN"] = "test-token"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

FIELD = {
    "type": "Polygon",
    "coordinates": [[[71.0, 51.3], [71.01435, 51.3], [71.01435, 51.309], [71.0, 51.309], [71.0, 51.3]]],
}
ANALYST = {"X-Analyst-Token": "test-token"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:  # with — чтобы отработал lifespan (таблицы + каталог)
        yield c


def submit(client, geometry=FIELD, bin_value="150343000016"):
    products = client.get("/api/products").json()
    body = {
        "bin": bin_value,
        "field": {"geometry": geometry, "crop": "Пшеница яровая"},
        "items": [{"product_id": products[0]["id"], "quantity": 10}],
    }
    return client.post("/api/applications", json=body)


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_verify_bin(client):
    r = client.post("/api/farms/verify", json={"bin": "150343000016"})
    assert r.status_code == 200 and r.json()["status"] == "verified"
    r = client.post("/api/farms/verify", json={"bin": "080740000019"})
    assert r.json()["status"] == "rejected"


def test_full_application_flow(client):
    r = submit(client)
    assert r.status_code == 201, r.text
    app_id = r.json()["id"]

    data = client.get(f"/api/applications/{app_id}").json()
    assert data["status"] in {"approved", "review"}
    assert len(data["seasons"]) == 7
    assert data["decision"]["score_class"] in {"A", "B", "C"}
    assert 98 < data["field"]["area_ha"] < 102


def test_rejected_farm_cannot_apply(client):
    r = submit(client, bin_value="080740000019")
    assert r.status_code == 422


def test_bad_geometry(client):
    bad = {"type": "Polygon", "coordinates": [[[37.6, 55.7], [37.62, 55.7], [37.62, 55.71], [37.6, 55.71]]]}
    assert submit(client, geometry=bad).status_code == 422


def test_analyst_requires_token(client):
    assert client.get("/api/analyst/applications").status_code == 401
    assert client.get("/api/analyst/applications", headers=ANALYST).status_code == 200


def test_analyst_approves_review(client):
    # Ищем поле, которое демо-спутник оценит классом C, перебирая соседние участки
    for i in range(60):
        lon = 69.0 + i * 0.05
        geom = {
            "type": "Polygon",
            "coordinates": [[[lon, 52.0], [lon + 0.01, 52.0], [lon + 0.01, 52.007], [lon, 52.007]]],
        }
        app_id = submit(client, geometry=geom).json()["id"]
        if client.get(f"/api/applications/{app_id}").json()["status"] == "review":
            break
    else:
        pytest.skip("Не нашлось поля класса C в демо-данных")

    r = client.post(
        f"/api/analyst/applications/{app_id}/decision",
        json={"action": "approve", "approved_amount": 500_000, "comment": "Проверено по выезду"},
        headers=ANALYST,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "approved" and d["decision"]["decided_by"] == "analyst"
    assert len(d["decision"]["schedule"]) == 2


# --- Антифрод: пересечение с полем другого хозяйства ------------------------------------

# Сдвинут на ~40% ширины относительно FIELD — пересекается примерно на 60% площади
SHIFTED = {
    "type": "Polygon",
    "coordinates": [[[71.0057, 51.3], [71.02005, 51.3], [71.02005, 51.309], [71.0057, 51.309], [71.0057, 51.3]]],
}
# Заходит на FIELD только краем (≈3%) — такое пересечение игнорируем
NEIGHBOUR = {
    "type": "Polygon",
    "coordinates": [[[71.0139, 51.3], [71.028, 51.3], [71.028, 51.309], [71.0139, 51.309], [71.0139, 51.3]]],
}
OTHER_FARM = "180240000011"


def test_live_check_hides_owner(client):
    r = client.post("/api/fields/check", json={"bin": OTHER_FARM, "geometry": SHIFTED})
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["overlaps"]) == 1
    o = data["overlaps"][0]
    assert 0.5 < o["share"] < 0.7
    assert o["farm_bin"] is None and o["geometry"] is None  # фермеру — без чужих данных


def test_own_fields_are_not_overlaps(client):
    r = client.post("/api/fields/check", json={"bin": "150343000016", "geometry": SHIFTED})
    assert r.json()["overlaps"] == []


def test_small_edge_overlap_ignored(client):
    r = client.post("/api/fields/check", json={"bin": OTHER_FARM, "geometry": NEIGHBOUR})
    assert r.json()["overlaps"] == []


def test_overlapping_application_goes_to_analyst(client):
    app_id = submit(client, geometry=SHIFTED, bin_value=OTHER_FARM).json()["id"]

    public = client.get(f"/api/applications/{app_id}").json()
    assert public["status"] == "review"
    assert public["decision"]["approved_amount"] == 0
    assert any("пересекается" in r for r in public["decision"]["reasons"])
    assert public["overlaps"][0]["farm_bin"] is None

    full = client.get(f"/api/analyst/applications/{app_id}", headers=ANALYST).json()
    assert full["overlaps"][0]["farm_bin"] == "150343000016"
    assert full["overlaps"][0]["geometry"]["type"] == "Polygon"

    listed = client.get("/api/analyst/applications?status=review", headers=ANALYST).json()
    assert any(a["id"] == app_id and a["has_overlaps"] for a in listed)


def test_check_rejects_bad_geometry(client):
    bad = {"type": "Polygon", "coordinates": [[[37.6, 55.7], [37.62, 55.7], [37.62, 55.71]]]}
    assert client.post("/api/fields/check", json={"geometry": bad}).status_code == 422
