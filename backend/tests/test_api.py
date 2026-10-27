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
os.environ["HP_CLIMATE_PROVIDER"] = "off"  # тесты не ходят в интернет
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


# --- Версия 0.3: проверка юрлица, кадастр, сделки и деньги ---------------------------------------


def test_verify_returns_checklist(client):
    data = client.post("/api/farms/verify", json={"bin": "150343000016"}).json()
    labels = [c["label"] for c in data["checks"]]
    assert "Налоги" in labels and "Аресты и запреты" in labels and "Суды" in labels


def test_tax_debtor_cannot_apply(client):
    assert client.post("/api/farms/verify", json={"bin": "170343000014"}).json()["status"] == "rejected"
    assert submit(client, bin_value="170343000014").status_code == 422


def test_products_hide_supplier_discount(client):
    p = client.get("/api/products").json()[0]
    assert isinstance(p["supplier"], str) and "discount" not in p


def find_approved(client, start_lon=74.0):
    """Подаёт заявки на разные участки, пока одна не одобрится автоматически."""
    for i in range(40):
        lon = start_lon + i * 0.05
        geom = {
            "type": "Polygon",
            "coordinates": [[[lon, 51.0], [lon + 0.01, 51.0], [lon + 0.01, 51.007], [lon, 51.007]]],
        }
        app_id = submit(client, geometry=geom).json()["id"]
        if client.get(f"/api/applications/{app_id}").json()["status"] == "approved":
            return app_id
    pytest.skip("Не нашлось автоматически одобряемого поля в демо-данных")


def test_cadastral_number_is_stored(client):
    products = client.get("/api/products").json()
    body = {
        "bin": "150343000016",
        "field": {"geometry": FIELD, "crop": "Ячмень", "cadastral_number": "01:011:002:345"},
        "items": [{"product_id": products[0]["id"], "quantity": 1}],
    }
    app_id = client.post("/api/applications", json=body).json()["id"]
    assert client.get(f"/api/applications/{app_id}").json()["field"]["cadastral_number"] == "01:011:002:345"
    body["field"]["cadastral_number"] = "abc"
    assert client.post("/api/applications", json=body).status_code == 422


def test_approval_opens_deal_and_farmer_sees_only_his_part(client):
    app_id = find_approved(client)
    public = client.get(f"/api/applications/{app_id}").json()
    deal = public["deal"]
    assert deal["status"] == "contracted"
    assert deal["farmer_total"] == sum(p["amount"] for p in public["decision"]["schedule"])
    assert deal["economics"] is None and deal["discount_rate"] is None  # экономику фермер не видит

    full = client.get(f"/api/analyst/applications/{app_id}", headers=ANALYST).json()["deal"]
    eco = full["economics"]
    assert eco["supplier_payout"] < eco["goods_amount"]  # поставщику — со скидкой
    assert full["flow"][0]["kind"] == "money" and len(full["scenario"]) == 5


def test_deal_steps_monitoring_and_portfolio(client):
    app_id = find_approved(client, start_lon=76.0)
    url = f"/api/analyst/deals/{app_id}"

    # нельзя перепрыгнуть шаг
    assert client.post(f"{url}/action", json={"action": "confirm_delivery"}, headers=ANALYST).status_code == 409
    for action in ("pay_supplier", "confirm_delivery"):
        r = client.post(f"{url}/action", json={"action": action}, headers=ANALYST)
        assert r.status_code == 200, r.text
    assert r.json()["deal"]["status"] == "delivered"

    r = client.post(f"{url}/monitoring", headers=ANALYST)
    assert r.status_code == 200, r.text
    m = r.json()["deal"]["monitoring"]
    assert m["status"] in {"normal", "stress", "not_sown", "growing", "waiting", "no_data"}
    assert m["points"] and m["expected"]

    total = r.json()["deal"]["farmer_total"]
    r = client.post(f"{url}/action", json={"action": "record_payment", "amount": total}, headers=ANALYST)
    assert r.json()["deal"]["status"] == "repaid"

    p = client.get("/api/analyst/portfolio", headers=ANALYST).json()
    assert p["deals_count"] >= 2
    assert p["credit_line"]["used"] + p["credit_line"]["available"] == p["credit_line"]["limit"]
    assert any(d["application_id"] == app_id and d["status"] == "repaid" for d in p["deals"])


def test_deal_endpoints_require_token(client):
    assert client.get("/api/analyst/portfolio").status_code == 401


def test_imagery_in_demo_mode_explains_why_unavailable(client):
    app_id = submit(client).json()["id"]
    data = client.get(f"/api/applications/{app_id}/imagery", params={"year": 2024}).json()
    assert data["available"] is False and "Copernicus" in data["message"]
    assert client.get(f"/api/applications/{app_id}/imagery/2024-07-01.png").status_code == 409


def test_imagery_validates_input(client):
    app_id = submit(client).json()["id"]
    assert client.get(f"/api/applications/{app_id}/imagery", params={"year": 2010}).status_code == 422
    assert client.get(f"/api/applications/{app_id}/imagery/2010-07-01.png").status_code == 422
    assert client.get(f"/api/applications/{app_id}/imagery/2024-07-01.png", params={"mode": "x"}).status_code == 422
    assert client.get("/api/applications/nope/imagery", params={"year": 2024}).status_code == 404
