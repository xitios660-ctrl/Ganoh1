"""Regression tests for /api/menu/{store} applying db.menu overrides on MENU_DATA defaults.

Covers:
- Editing a default MENU_DATA item's price via PUT /api/gestor/menu/{id}
  and seeing it reflected in /api/menu/runner AND /api/menu/gym-londres.
- Editing description and category likewise reflected.
- Restoring original price works.
- Creating a NEW custom item appears in both public menus.
- Editing and deleting custom items propagate.
- Regression: MENU_DATA structure (categories, image_url, prep_time, adicionais,
  milk_options) still present in public response.
- Cleanup: all TEST_ items are removed at end and MENU_DATA prices are restored.
"""

import os
import pytest
import requests

def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    # Fallback: read frontend/.env
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not configured")

BASE_URL = _load_backend_url()
AUTH = ("gestor", "test-only-value")

# Item 53 = Capuccino / Mocaccino default price 9.00
# Item 54 = Chocolate Quente default price 9.00
DEFAULT_ITEM_ID = "53"
DEFAULT_ITEM_NAME = "Capuccino / Mocaccino"
DEFAULT_ORIGINAL_PRICE = 9.00
DEFAULT_ORIGINAL_CATEGORY = "Bebidas Quentes"
DEFAULT_ORIGINAL_DESCRIPTION = "Bebida cremosa com espuma de leite"


def _get_public_item(store: str, name: str):
    r = requests.get(f"{BASE_URL}/api/menu/{store}", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    for it in data["items"]:
        if it.get("name", "").strip().lower() == name.strip().lower():
            return it, data
    return None, data


@pytest.fixture(scope="module")
def created_custom_id():
    """Create a custom TEST_ item once, share id across tests, cleanup at end."""
    payload = {
        "name": "TEST_ProdutoNovo",
        "description": "Item de teste automatizado",
        "price": 5.50,
        "category": "Doces",
        "store": "runner",  # ignored by backend, both stores are created
    }
    r = requests.post(f"{BASE_URL}/api/gestor/menu", json=payload, auth=AUTH, timeout=15)
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    # runner-suffixed id
    runner_id = next(i["id"] for i in items if i["store"] == "runner")
    yield runner_id
    # Cleanup - delete both stores via one call
    requests.delete(f"{BASE_URL}/api/gestor/menu/{runner_id}", auth=AUTH, timeout=15)
    # Delete stray TEST_ docs by name just in case
    for store in ("runner", "gym-londres"):
        r = requests.get(f"{BASE_URL}/api/gestor/menu/{store}", auth=AUTH, timeout=15)
        if r.status_code == 200:
            for m in r.json().get("menu", []):
                if (m.get("name", "").startswith("TEST_")):
                    requests.delete(f"{BASE_URL}/api/gestor/menu/{m['id']}", auth=AUTH, timeout=15)


# ---------- MENU_DATA override tests ----------

def test_edit_default_price_reflects_in_both_public_menus():
    """PUT price on id=53 should reflect in /api/menu/runner AND /api/menu/gym-londres."""
    try:
        r = requests.put(
            f"{BASE_URL}/api/gestor/menu/{DEFAULT_ITEM_ID}",
            json={"price": 10.0},
            auth=AUTH,
            timeout=15,
        )
        assert r.status_code == 200, r.text

        for store in ("runner", "gym-londres"):
            it, _ = _get_public_item(store, DEFAULT_ITEM_NAME)
            assert it is not None, f"{DEFAULT_ITEM_NAME} not found in {store}"
            assert it["price"] == 10.0, f"{store}: expected 10.0 got {it['price']}"
    finally:
        # restore
        requests.put(
            f"{BASE_URL}/api/gestor/menu/{DEFAULT_ITEM_ID}",
            json={"price": DEFAULT_ORIGINAL_PRICE},
            auth=AUTH,
            timeout=15,
        )


def test_edit_default_description_and_category_reflect():
    new_desc = "TEST_desc override"
    new_cat = "Bebidas Geladas"  # move category
    try:
        r = requests.put(
            f"{BASE_URL}/api/gestor/menu/{DEFAULT_ITEM_ID}",
            json={"description": new_desc, "category": new_cat},
            auth=AUTH,
            timeout=15,
        )
        assert r.status_code == 200, r.text

        for store in ("runner", "gym-londres"):
            it, _ = _get_public_item(store, DEFAULT_ITEM_NAME)
            assert it is not None
            assert it["description"] == new_desc, f"{store}: desc {it['description']}"
            assert it["category"] == new_cat, f"{store}: category {it['category']}"
    finally:
        requests.put(
            f"{BASE_URL}/api/gestor/menu/{DEFAULT_ITEM_ID}",
            json={
                "description": DEFAULT_ORIGINAL_DESCRIPTION,
                "category": DEFAULT_ORIGINAL_CATEGORY,
                "price": DEFAULT_ORIGINAL_PRICE,
            },
            auth=AUTH,
            timeout=15,
        )


def test_restore_default_price_shows_original():
    # Change then restore, verify original visible
    requests.put(
        f"{BASE_URL}/api/gestor/menu/{DEFAULT_ITEM_ID}",
        json={"price": 12.0},
        auth=AUTH,
        timeout=15,
    )
    requests.put(
        f"{BASE_URL}/api/gestor/menu/{DEFAULT_ITEM_ID}",
        json={"price": DEFAULT_ORIGINAL_PRICE},
        auth=AUTH,
        timeout=15,
    )
    for store in ("runner", "gym-londres"):
        it, _ = _get_public_item(store, DEFAULT_ITEM_NAME)
        assert it["price"] == DEFAULT_ORIGINAL_PRICE


# ---------- Custom item tests ----------

def test_custom_item_appears_in_both_public_menus(created_custom_id):
    for store in ("runner", "gym-londres"):
        it, _ = _get_public_item(store, "TEST_ProdutoNovo")
        assert it is not None, f"TEST_ProdutoNovo missing in {store}"
        assert it["price"] == 5.50
        assert it["category"] == "Doces"


def test_edit_custom_item_reflects(created_custom_id):
    r = requests.put(
        f"{BASE_URL}/api/gestor/menu/{created_custom_id}",
        json={"price": 7.25},
        auth=AUTH,
        timeout=15,
    )
    assert r.status_code == 200, r.text
    for store in ("runner", "gym-londres"):
        it, _ = _get_public_item(store, "TEST_ProdutoNovo")
        assert it is not None
        assert it["price"] == 7.25, f"{store}: expected 7.25 got {it['price']}"


def test_delete_custom_item_removes_from_both():
    # Create a dedicated one to delete
    r = requests.post(
        f"{BASE_URL}/api/gestor/menu",
        json={
            "name": "TEST_ToDelete",
            "description": "x",
            "price": 3.0,
            "category": "Doces",
            "store": "runner",
        },
        auth=AUTH,
        timeout=15,
    )
    assert r.status_code == 200
    item_id = r.json()["items"][0]["id"]

    r = requests.delete(f"{BASE_URL}/api/gestor/menu/{item_id}", auth=AUTH, timeout=15)
    assert r.status_code == 200, r.text
    assert r.json().get("deleted_count", 0) if "deleted_count" in r.json() else True

    for store in ("runner", "gym-londres"):
        it, _ = _get_public_item(store, "TEST_ToDelete")
        assert it is None, f"TEST_ToDelete still present in {store}"


# ---------- Regression tests ----------

def test_public_menu_structure_intact():
    for store in ("runner", "gym-londres"):
        r = requests.get(f"{BASE_URL}/api/menu/{store}", timeout=15)
        assert r.status_code == 200
        data = r.json()
        # Required top-level keys
        for k in ("items", "categories", "adicionais", "milk_options", "store"):
            assert k in data, f"{store} missing key {k}"
        # Non-empty
        assert len(data["items"]) > 50, f"{store} has too few items"
        assert len(data["categories"]) > 0
        assert len(data["adicionais"]) > 0
        assert len(data["milk_options"]) == 4
        # Sample item should have prep_time key
        sample = next((i for i in data["items"] if i.get("id") == "1"), None)
        assert sample is not None
        assert "prep_time" in sample
        assert sample["prep_time"] == 15


def test_cleanup_no_residual_test_items():
    """Final: ensure no TEST_ items remain and default price is restored."""
    # Restore default just in case previous test failed mid-way
    requests.put(
        f"{BASE_URL}/api/gestor/menu/{DEFAULT_ITEM_ID}",
        json={
            "price": DEFAULT_ORIGINAL_PRICE,
            "description": DEFAULT_ORIGINAL_DESCRIPTION,
            "category": DEFAULT_ORIGINAL_CATEGORY,
        },
        auth=AUTH,
        timeout=15,
    )

    # Delete any TEST_ items
    for store in ("runner", "gym-londres"):
        r = requests.get(f"{BASE_URL}/api/gestor/menu/{store}", auth=AUTH, timeout=15)
        assert r.status_code == 200
        for m in r.json().get("menu", []):
            if m.get("name", "").startswith("TEST_"):
                requests.delete(f"{BASE_URL}/api/gestor/menu/{m['id']}", auth=AUTH, timeout=15)

    # Verify none remain in public menu
    for store in ("runner", "gym-londres"):
        r = requests.get(f"{BASE_URL}/api/menu/{store}", timeout=15)
        data = r.json()
        residual = [i for i in data["items"] if i.get("name", "").startswith("TEST_")]
        assert not residual, f"{store} has residual TEST_ items: {[i['name'] for i in residual]}"

        # Verify default restored
        it, _ = _get_public_item(store, DEFAULT_ITEM_NAME)
        assert it is not None
        assert it["price"] == DEFAULT_ORIGINAL_PRICE, f"{store}: default price not restored ({it['price']})"
        assert it["category"] == DEFAULT_ORIGINAL_CATEGORY
