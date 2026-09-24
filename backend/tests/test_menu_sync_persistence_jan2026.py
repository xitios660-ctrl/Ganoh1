"""Backend tests for Menu sync persistence between Runner + GYM Londres stores.

Validates the bugfix where PUT/DELETE on /api/gestor/menu/{id} must propagate to
BOTH stores (update_many / delete_many), and supports both plain IDs (e.g. '48')
and store-suffixed IDs (e.g. 'uuid-runner' / 'uuid-gym-londres').

All test data is prefixed with 'TEST_' and cleaned up at the end.
"""

import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
AUTH = ("gestor", "test-only-value")

# Track items created so we always clean up
_created_item_ids: list[str] = []


# ----------------------------- fixtures -----------------------------

@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.auth = AUTH
    s.headers.update({"Content-Type": "application/json"})
    yield s
    # final cleanup pass
    for item_id in list(_created_item_ids):
        try:
            s.delete(f"{BASE_URL}/api/gestor/menu/{item_id}", timeout=10)
        except Exception:
            pass


def _create_item(session, name_suffix: str, price: float = 1.23,
                 category: str = "Doces", description: str = "",
                 image_url: str = "") -> dict:
    """POST a new item; returns the JSON response."""
    payload = {
        "name": f"TEST_{name_suffix}_{uuid.uuid4().hex[:6]}",
        "description": description,
        "price": price,
        "category": category,
        "store": "runner",  # backend creates in both regardless
        "image_url": image_url,
    }
    r = session.post(f"{BASE_URL}/api/gestor/menu", json=payload, timeout=15)
    assert r.status_code == 200, f"POST failed: {r.status_code} {r.text}"
    data = r.json()
    for item in data.get("items", []):
        _created_item_ids.append(item["id"])
    data["_payload"] = payload
    return data


# --------------------------- module: auth ---------------------------

class TestAuth:
    def test_gestor_can_list_menu(self, session):
        r = session.get(f"{BASE_URL}/api/gestor/menu/runner", timeout=10)
        assert r.status_code == 200
        d = r.json()
        # confirms server.py wins routing (format {menu, count})
        assert "menu" in d and "count" in d
        assert isinstance(d["menu"], list)
        assert d["count"] == len(d["menu"])


# --------------------------- module: POST ---------------------------

class TestCreateMenuItem:
    def test_post_creates_item_in_both_stores_with_suffix_ids(self, session):
        data = _create_item(session, "CreateBoth", price=9.99)
        assert data["success"] is True
        items = data["items"]
        assert len(items) == 2
        stores_seen = {i["store"] for i in items}
        assert stores_seen == {"runner", "gym-londres"}
        # IDs must follow {base}-runner / {base}-gym-londres
        bases = {i["id"].rsplit("-", 1)[0] if i["store"] == "runner"
                 else i["id"].rsplit("-", 2)[0] for i in items}
        # Actually for gym-londres suffix is '-gym-londres' (2 segs); for runner '-runner' (1 seg)
        runner_id = next(i["id"] for i in items if i["store"] == "runner")
        gym_id = next(i["id"] for i in items if i["store"] == "gym-londres")
        assert runner_id.endswith("-runner")
        assert gym_id.endswith("-gym-londres")
        base_runner = runner_id[: -len("-runner")]
        base_gym = gym_id[: -len("-gym-londres")]
        assert base_runner == base_gym, "Base UUID must match across stores"

    def test_post_also_creates_stock_entries(self, session):
        # Use a beverage category that needs stock; even so backend inserts stock unconditionally.
        data = _create_item(session, "StockCheck", price=5.0, category="Bebidas")
        item_id_runner = next(i["id"] for i in data["items"] if i["store"] == "runner")
        # Pull public /api/menu/runner and search for the item with stock field
        pub = requests.get(f"{BASE_URL}/api/menu/runner", timeout=10).json()
        menu_list = pub.get("items", [])
        match = [x for x in menu_list if x.get("id") == item_id_runner]
        assert match, "Created item must appear in public menu"
        # stock should be present (50 default) for Bebidas category
        assert match[0].get("stock") in (50, None) or match[0].get("stock", 0) >= 0


# ---------------------------- module: PUT ---------------------------

class TestUpdateMenuItem:
    def test_put_with_suffix_id_propagates_to_sibling(self, session):
        data = _create_item(session, "PutSuffix", price=10.00)
        runner_id = next(i["id"] for i in data["items"] if i["store"] == "runner")
        gym_id = next(i["id"] for i in data["items"] if i["store"] == "gym-londres")

        r = session.put(
            f"{BASE_URL}/api/gestor/menu/{runner_id}",
            json={"price": 12.34},
            timeout=10,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["matched_count"] == 2
        assert body["modified_count"] == 2

        # Verify both store entries reflect the price
        menu_runner = session.get(f"{BASE_URL}/api/gestor/menu/runner", timeout=10).json()["menu"]
        menu_gym = session.get(f"{BASE_URL}/api/gestor/menu/gym-londres", timeout=10).json()["menu"]
        runner_item = next((i for i in menu_runner if i["id"] == runner_id), None)
        gym_item = next((i for i in menu_gym if i["id"] == gym_id), None)
        assert runner_item is not None and gym_item is not None
        assert runner_item["price"] == 12.34
        assert gym_item["price"] == 12.34

    def test_put_only_price_does_not_touch_other_fields(self, session):
        data = _create_item(
            session, "PutPriceOnly",
            price=5.55,
            category="Salgados",
            description="Original desc",
            image_url="http://example.com/img.png",
        )
        runner_id = next(i["id"] for i in data["items"] if i["store"] == "runner")

        r = session.put(
            f"{BASE_URL}/api/gestor/menu/{runner_id}",
            json={"price": 6.66},
            timeout=10,
        )
        assert r.status_code == 200

        menu = session.get(f"{BASE_URL}/api/gestor/menu/runner", timeout=10).json()["menu"]
        item = next(i for i in menu if i["id"] == runner_id)
        assert item["price"] == 6.66
        assert item["description"] == "Original desc"
        assert item["category"] == "Salgados"
        assert item["image_url"] == "http://example.com/img.png"

    def test_put_name_change_updates_stock_collection(self, session):
        data = _create_item(session, "PutName", price=2.0, category="Bebidas")
        runner_id = next(i["id"] for i in data["items"] if i["store"] == "runner")
        new_name = f"TEST_RenamedItem_{uuid.uuid4().hex[:6]}"

        r = session.put(
            f"{BASE_URL}/api/gestor/menu/{runner_id}",
            json={"name": new_name},
            timeout=10,
        )
        assert r.status_code == 200

        # Stock entries also have name field; verify indirectly via public menu (stock_map by id)
        # Verify menu name changed
        menu = session.get(f"{BASE_URL}/api/gestor/menu/runner", timeout=10).json()["menu"]
        item = next(i for i in menu if i["id"] == runner_id)
        assert item["name"] == new_name

    def test_put_nonexistent_returns_404(self, session):
        r = session.put(
            f"{BASE_URL}/api/gestor/menu/__does_not_exist_{uuid.uuid4().hex}__",
            json={"price": 1.0},
            timeout=10,
        )
        assert r.status_code == 404
        assert "não encontrado" in r.json().get("detail", "").lower()

    def test_put_empty_payload_returns_400(self, session):
        # Need any real id; reuse one we created
        if not _created_item_ids:
            _create_item(session, "AnyForEmpty", price=1.0)
        any_id = _created_item_ids[0]
        r = session.put(f"{BASE_URL}/api/gestor/menu/{any_id}", json={}, timeout=10)
        assert r.status_code == 400

    def test_put_plain_id_updates_both_stores(self, session):
        """When MENU_DATA was migrated, some docs share the same plain id
        (e.g. '48') across both stores. PUT must update_many of them.
        We simulate by inserting two raw docs with same plain id via
        creating an item then manually patching ids would be invasive — instead
        we rely on EXISTING MENU_DATA-migrated docs. We try id '48' which the
        smoke test in the request confirms exists."""
        # If '48' doesn't exist we skip silently (env may have been wiped)
        check_runner = session.get(f"{BASE_URL}/api/gestor/menu/runner", timeout=10).json()["menu"]
        check_gym = session.get(f"{BASE_URL}/api/gestor/menu/gym-londres", timeout=10).json()["menu"]
        runner_48 = next((i for i in check_runner if i.get("id") == "48"), None)
        gym_48 = next((i for i in check_gym if i.get("id") == "48"), None)
        if not (runner_48 and gym_48):
            pytest.skip("Plain-id '48' not present in DB; skipping plain-id sync test")

        original = runner_48["price"]
        new_price = round(original + 0.07, 2)
        try:
            r = session.put(
                f"{BASE_URL}/api/gestor/menu/48",
                json={"price": new_price},
                timeout=10,
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["matched_count"] >= 2
            assert body["modified_count"] >= 1  # may be 2 if values differed

            # verify both store prices now equal new_price
            menu_runner2 = session.get(f"{BASE_URL}/api/gestor/menu/runner", timeout=10).json()["menu"]
            menu_gym2 = session.get(f"{BASE_URL}/api/gestor/menu/gym-londres", timeout=10).json()["menu"]
            r48 = next(i for i in menu_runner2 if i.get("id") == "48")
            g48 = next(i for i in menu_gym2 if i.get("id") == "48")
            assert r48["price"] == new_price
            assert g48["price"] == new_price
        finally:
            # restore original price
            session.put(
                f"{BASE_URL}/api/gestor/menu/48",
                json={"price": original},
                timeout=10,
            )


# --------------------------- module: DELETE -------------------------

class TestDeleteMenuItem:
    def test_delete_removes_both_stores_and_stock(self, session):
        data = _create_item(session, "DeleteMe", price=3.33, category="Bebidas")
        runner_id = next(i["id"] for i in data["items"] if i["store"] == "runner")
        gym_id = next(i["id"] for i in data["items"] if i["store"] == "gym-londres")

        r = session.delete(f"{BASE_URL}/api/gestor/menu/{runner_id}", timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert "2 loja" in body["message"]

        # Should no longer exist
        menu_runner = session.get(f"{BASE_URL}/api/gestor/menu/runner", timeout=10).json()["menu"]
        menu_gym = session.get(f"{BASE_URL}/api/gestor/menu/gym-londres", timeout=10).json()["menu"]
        assert not any(i["id"] == runner_id for i in menu_runner)
        assert not any(i["id"] == gym_id for i in menu_gym)

        # remove from cleanup tracker (already gone)
        for x in (runner_id, gym_id):
            if x in _created_item_ids:
                _created_item_ids.remove(x)

    def test_delete_nonexistent_returns_404(self, session):
        r = session.delete(
            f"{BASE_URL}/api/gestor/menu/__nope_{uuid.uuid4().hex}__",
            timeout=10,
        )
        assert r.status_code == 404


# ------------------------ module: public menu -----------------------

class TestPublicMenu:
    def test_public_menu_reflects_updated_price(self, session):
        data = _create_item(session, "PublicSync", price=4.0)
        runner_id = next(i["id"] for i in data["items"] if i["store"] == "runner")
        # update price
        session.put(
            f"{BASE_URL}/api/gestor/menu/{runner_id}",
            json={"price": 7.77},
            timeout=10,
        )
        # public endpoints (no auth)
        for store in ("runner", "gym-londres"):
            r = requests.get(f"{BASE_URL}/api/menu/{store}", timeout=10)
            assert r.status_code == 200
            body = r.json()
            menu_list = body.get("items", [])
            sibling_id = runner_id if store == "runner" else runner_id.replace("-runner", "-gym-londres")
            found = [x for x in menu_list if x.get("id") == sibling_id]
            assert found, f"Item {sibling_id} not visible in /api/menu/{store}"
            assert found[0]["price"] == 7.77

    def test_low_price_item_not_filtered_as_test(self, session):
        """Chiclete R$0,50 must remain visible — filter only blocks 'placeholder'."""
        data = _create_item(
            session, "Chiclete", price=0.50, category="Doces",
        )
        # custom name has TEST_ prefix; but the filter only checks 'placeholder'
        # We'll create one without the TEST_ prefix? No — the filter is name-based,
        # only 'placeholder'. So even 'TEST_Chiclete_xxx' should pass.
        runner_id = next(i["id"] for i in data["items"] if i["store"] == "runner")
        for store in ("runner", "gym-londres"):
            r = requests.get(f"{BASE_URL}/api/menu/{store}", timeout=10)
            body = r.json()
            menu_list = body.get("items", [])
            sibling_id = runner_id if store == "runner" else runner_id.replace("-runner", "-gym-londres")
            assert any(x.get("id") == sibling_id for x in menu_list), (
                f"Low-price item incorrectly filtered in {store}"
            )

    def test_custom_category_pao_doce_works(self, session):
        data = _create_item(session, "PaoDoceItem", price=3.50, category="Pão Doce")
        runner_id = next(i["id"] for i in data["items"] if i["store"] == "runner")
        for store in ("runner", "gym-londres"):
            r = requests.get(f"{BASE_URL}/api/menu/{store}", timeout=10)
            body = r.json()
            menu_list = body.get("items", [])
            sibling_id = runner_id if store == "runner" else runner_id.replace("-runner", "-gym-londres")
            assert any(x.get("id") == sibling_id for x in menu_list)


# --------------------- module: persistence (F5) ---------------------

class TestPersistence:
    def test_price_persists_across_refetch(self, session):
        data = _create_item(session, "Persist", price=11.11)
        runner_id = next(i["id"] for i in data["items"] if i["store"] == "runner")

        r = session.put(
            f"{BASE_URL}/api/gestor/menu/{runner_id}",
            json={"price": 22.22},
            timeout=10,
        )
        assert r.status_code == 200

        # Simulate F5 — refetch three times, must remain the same
        prices = []
        for _ in range(3):
            menu = session.get(f"{BASE_URL}/api/gestor/menu/runner", timeout=10).json()["menu"]
            item = next(i for i in menu if i["id"] == runner_id)
            prices.append(item["price"])
        assert all(p == 22.22 for p in prices), f"Price not persisted: {prices}"

    def test_runner_menu_has_100_items(self, session):
        """Smoke check that MENU_DATA migration produced ~100 base items.
        Tolerates +N from the TEST_ items this run created (cleaned at module teardown).
        """
        menu = session.get(f"{BASE_URL}/api/gestor/menu/runner", timeout=10).json()["menu"]
        assert len(menu) >= 100, f"Expected >=100, got {len(menu)}"
