"""Tests for /api/prazo/customers/lookup cross-store fallback + accent-insensitive search.

Covers iteration-4 review request (Jan 2026):
- Listing by store
- Cross-store fallback when current-store search returns empty
- Accent-insensitive match (paulao -> Paulão)
"""
import os
import pytest
import requests

def _read_frontend_env():
    try:
        with open("/app/frontend/.env", "r") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return None

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _read_frontend_env() or "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL not set"
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _get(session, params):
    r = session.get(f"{API}/prazo/customers/lookup", params=params, timeout=15)
    assert r.status_code == 200, f"Lookup failed: {r.status_code} {r.text}"
    return r.json().get("customers", [])


# --- Test 1: store filter returns only that store's customers ----------------
def test_lookup_store_filter_only_gym_londres(session):
    customers = _get(session, {"store": "gym-londres"})
    assert len(customers) > 0, "Expected gym-londres seed customers"
    stores = {c.get("store") for c in customers}
    assert stores == {"gym-londres"}, f"Expected only gym-londres customers, got: {stores}"


def test_lookup_store_filter_only_runner(session):
    customers = _get(session, {"store": "runner"})
    assert len(customers) > 0, "Expected runner seed customers"
    stores = {c.get("store") for c in customers}
    assert stores == {"runner"}, f"Expected only runner customers, got: {stores}"


# --- Test 2: Cross-store fallback: searching 'Pau' in gym-londres ------------
def test_lookup_cross_store_fallback_pau_in_gym(session):
    """gym-londres has no 'Pau' customers; runner has PATY DE PAULA + PAULO HENRIQUE.
    Cross-store fallback should kick in.
    """
    customers = _get(session, {"q": "Pau", "store": "gym-londres"})
    names_upper = [c["name"].upper() for c in customers]
    assert any("PAU" in n for n in names_upper), (
        f"Cross-store fallback failed: searching 'Pau' in gym-londres returned: {names_upper}"
    )
    # All returned should be from runner (since gym-londres had none)
    for c in customers:
        assert c.get("store") == "runner", (
            f"Fallback should return runner customers, got {c.get('name')} from {c.get('store')}"
        )


# --- Test 3: Cross-store fallback: 'bonine' from gym-londres while in runner -
def test_lookup_cross_store_fallback_bonine_in_runner(session):
    customers = _get(session, {"q": "BONINE", "store": "runner"})
    names_upper = [c["name"].upper() for c in customers]
    assert any("BONINE" in n for n in names_upper), (
        f"Cross-store fallback failed: 'BONINE' in runner returned: {names_upper}"
    )


# --- Test 4: Accent-insensitive search (paulao -> Paulão) --------------------
def test_lookup_accent_insensitive_paulao(session):
    """Create TEST_paulao customer in gym-londres, search 'paulao' (no accent), then clean up."""
    create_payload = {
        "name": "TEST_Paulão",
        "phone": "43999999999",
        "store": "gym-londres",
    }
    created = session.post(
        f"{API}/prazo/customers",
        json=create_payload,
        auth=("gestor", "ganoh2024"),
        timeout=15,
    )
    assert created.status_code == 200, f"Create failed: {created.status_code} {created.text}"
    customer_id = created.json().get("id")
    assert customer_id, "No id on created customer"

    try:
        # Search without accent + lowercase
        customers = _get(session, {"q": "paulao", "store": "gym-londres"})
        names = [c["name"] for c in customers]
        assert any("Paulão" in n or "paulao" in n.lower() for n in names), (
            f"Accent-insensitive match failed for 'paulao': {names}"
        )

        # Also confirm it works with different casing
        customers_upper = _get(session, {"q": "PAULAO", "store": "gym-londres"})
        names_upper = [c["name"] for c in customers_upper]
        assert any("Paulão" in n for n in names_upper), (
            f"Case-insensitive failed for 'PAULAO': {names_upper}"
        )
    finally:
        # Cleanup
        session.delete(
            f"{API}/prazo/customers/{customer_id}",
            auth=("gestor", "ganoh2024"),
            timeout=15,
        )


# --- Test 5: No results returns empty array ---------------------------------
def test_lookup_no_results_returns_empty(session):
    customers = _get(session, {"q": "ZZZ_NO_MATCH_XYZ_QWERTY", "store": "gym-londres"})
    assert customers == [], f"Expected empty list for impossible query, got: {customers}"


# --- Test 6: Phone is masked -------------------------------------------------
def test_lookup_phone_masked(session):
    customers = _get(session, {"store": "runner"})
    # Any customer with a phone should have phone_masked (no raw digits revealed at start)
    for c in customers:
        if c.get("phone_masked"):
            # Should contain bullet/dot or be short
            pm = c["phone_masked"]
            # Only the last up to 4 digits should be plain digits
            assert "•" in pm or len(pm) <= 4, f"Phone not masked properly: {pm}"
            break
