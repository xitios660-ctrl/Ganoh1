"""
Iteration 3 (Jan 2026) — bug fixes:
 (1) Backend POST /api/gestor/menu adds 'Chiclete' (R$ 0,50, category 'Doces') in both stores.
 (2) Backend GET /api/prazo/customers/lookup is accent-insensitive (Paulão matches 'paulao').
 (3) Same lookup is case + diacritic insensitive (João matches 'joao').
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
AUTH = ("gestor", "ganoh2024")


# -------------------- Menu add: Chiclete, price 0.50, Doces --------------------
class TestMenuAddChiclete:
    def _list_menu(self, store):
        r = requests.get(f"{BASE_URL}/api/gestor/menu/{store}", auth=AUTH, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        return body.get("menu", body.get("items", body if isinstance(body, list) else []))

    def test_add_chiclete_in_doces(self):
        unique_name = f"TEST_Chiclete_{uuid.uuid4().hex[:8]}"
        payload = {
            "name": unique_name,
            "category": "Doces",
            "price": 0.50,
            "store": "runner",
            "description": "Teste chiclete",
            "available": True,
        }
        r = requests.post(f"{BASE_URL}/api/gestor/menu",
                          json=payload, auth=AUTH, timeout=15)
        assert r.status_code in (200, 201), f"{r.status_code} {r.text}"
        body = r.json()
        created_ids = [i.get("id") for i in body.get("items", [])]
        assert len(created_ids) >= 1, body

        try:
            # Verify the item appears in /api/gestor/menu/runner with correct price + category
            items_runner = self._list_menu("runner")
            match_runner = next((i for i in items_runner if i.get("name") == unique_name), None)
            assert match_runner is not None, f"{unique_name} not found in runner menu"
            assert match_runner.get("category") == "Doces", match_runner
            assert abs(match_runner.get("price", 0) - 0.50) < 1e-6, match_runner

            # Verify the item appears in /api/gestor/menu/gym-londres (server creates in both)
            items_gym = self._list_menu("gym-londres")
            match_gym = next((i for i in items_gym if i.get("name") == unique_name), None)
            assert match_gym is not None, f"{unique_name} not found in gym-londres menu"
            assert match_gym.get("category") == "Doces", match_gym
            assert abs(match_gym.get("price", 0) - 0.50) < 1e-6, match_gym
        finally:
            for cid in created_ids:
                requests.delete(f"{BASE_URL}/api/gestor/menu/{cid}", auth=AUTH, timeout=10)


# -------------------- Prazo lookup: accent + case insensitive --------------------
class TestPrazoLookupAccentInsensitive:
    def _create_customer(self, name, store="gym-londres"):
        r = requests.post(
            f"{BASE_URL}/api/prazo/customers",
            json={"name": name, "phone": "", "notes": "TEST_iter3", "store": store, "credit": 0},
            auth=AUTH,
            timeout=15,
        )
        assert r.status_code in (200, 201), f"{r.status_code} {r.text}"
        return r.json()

    def _delete_customer(self, cid):
        try:
            requests.delete(f"{BASE_URL}/api/prazo/customers/{cid}", auth=AUTH, timeout=10)
        except Exception:
            pass

    def _lookup(self, q, store=None):
        params = {"q": q}
        if store:
            params["store"] = store
        r = requests.get(f"{BASE_URL}/api/prazo/customers/lookup", params=params, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        return data.get("customers", data if isinstance(data, list) else [])

    def test_paulao_accent_insensitive(self):
        unique_name = f"TEST_Paulão_{uuid.uuid4().hex[:6]}"
        created = self._create_customer(unique_name, store="gym-londres")
        cid = created.get("id")
        try:
            # The query 'paulao' (no accent) should match 'Paulão'
            results = self._lookup("paulao", store="gym-londres")
            names = [c.get("name") for c in results]
            assert unique_name in names, \
                f"Accent-insensitive lookup failed: 'paulao' did not find {unique_name}. Got: {names}"

            # Uppercase query 'PAUL' should also match
            results2 = self._lookup("PAUL", store="gym-londres")
            names2 = [c.get("name") for c in results2]
            assert unique_name in names2, \
                f"Case-insensitive lookup failed: 'PAUL' did not find {unique_name}. Got: {names2}"
        finally:
            self._delete_customer(cid)

    def test_joao_accent_insensitive(self):
        unique_name = f"TEST_João_{uuid.uuid4().hex[:6]}"
        created = self._create_customer(unique_name, store="runner")
        cid = created.get("id")
        try:
            # Query 'joao' (no accent) must find 'João'
            results = self._lookup("joao", store="runner")
            names = [c.get("name") for c in results]
            assert unique_name in names, \
                f"'joao' did not match 'João' (test name {unique_name}). Got: {names}"

            # Query 'JOAO' uppercase must also match
            results2 = self._lookup("JOAO", store="runner")
            names2 = [c.get("name") for c in results2]
            assert unique_name in names2, \
                f"'JOAO' did not match 'João' (test name {unique_name}). Got: {names2}"
        finally:
            self._delete_customer(cid)

    def test_lookup_no_results_when_no_match(self):
        # Sanity: a totally bogus string returns 0
        results = self._lookup("xyzqwertynomatch12345", store="runner")
        assert results == [] or len(results) == 0, results
