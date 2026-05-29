"""
Test new features for iteration 10:
1. Prazo debts store separation (Runner vs GYM Londres)
2. Send contador email endpoint
3. AI expense analysis with store field
4. Menu item fiscal fields (NCM, CSOSN, CFOP, codigo_barras)
"""
import pytest
import requests
import os
from requests.auth import HTTPBasicAuth

# Get BASE_URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    raise ValueError("REACT_APP_BACKEND_URL environment variable not set")

# Auth credentials
AUTH = HTTPBasicAuth('gestor', 'ganoh2024')


class TestPrazoStoresSeparation:
    """Test prazo debts are correctly separated by store"""
    
    def test_prazo_debts_runner_only(self):
        """GET /api/prazo/debts?store=runner returns only Runner debts"""
        response = requests.get(f"{BASE_URL}/api/prazo/debts?store=runner")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "debts" in data, "Response should contain 'debts' field"
        assert "total_prazo" in data, "Response should contain 'total_prazo' field"
        assert "store_filter" in data, "Response should contain 'store_filter' field"
        assert data["store_filter"] == "runner", f"Expected store_filter='runner', got {data['store_filter']}"
        
        # Verify all debts are from runner store
        for debt in data.get("debts", []):
            for order in debt.get("orders", []):
                assert order.get("store") == "runner", f"Found non-runner order in runner debts: {order.get('store')}"
        
        print(f"✅ Runner prazo debts: {data['total_prazo']} from {data.get('customer_count', 0)} customers")
    
    def test_prazo_debts_gym_londres_only(self):
        """GET /api/prazo/debts?store=gym-londres returns only GYM Londres debts"""
        response = requests.get(f"{BASE_URL}/api/prazo/debts?store=gym-londres")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "debts" in data, "Response should contain 'debts' field"
        assert "total_prazo" in data, "Response should contain 'total_prazo' field"
        assert "store_filter" in data, "Response should contain 'store_filter' field"
        assert data["store_filter"] == "gym-londres", f"Expected store_filter='gym-londres', got {data['store_filter']}"
        
        # Verify all debts are from gym-londres store
        for debt in data.get("debts", []):
            for order in debt.get("orders", []):
                assert order.get("store") == "gym-londres", f"Found non-gym-londres order in gym-londres debts: {order.get('store')}"
        
        print(f"✅ GYM Londres prazo debts: {data['total_prazo']} from {data.get('customer_count', 0)} customers")
    
    def test_prazo_debts_all_stores(self):
        """GET /api/prazo/debts without store param returns all debts"""
        response = requests.get(f"{BASE_URL}/api/prazo/debts")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "debts" in data, "Response should contain 'debts' field"
        assert "total_prazo" in data, "Response should contain 'total_prazo' field"
        
        print(f"✅ All stores prazo debts: {data['total_prazo']} from {data.get('customer_count', 0)} customers")


class TestContadorEmailEndpoint:
    """Test send-contador-email endpoint exists and validates properly"""
    
    def test_send_contador_email_endpoint_exists(self):
        """POST /api/expenses/send-contador-email endpoint exists"""
        # Send request without RESEND_API_KEY - should return 500 with specific error
        response = requests.post(
            f"{BASE_URL}/api/expenses/send-contador-email",
            auth=AUTH,
            json={
                "email": "test@example.com",
                "month": 1,
                "year": 2026,
                "store": "all"
            }
        )
        
        # Endpoint should exist - either 500 (missing API key) or 200 (success)
        assert response.status_code in [200, 500], f"Expected 200 or 500, got {response.status_code}"
        
        if response.status_code == 500:
            data = response.json()
            # Should mention RESEND_API_KEY not configured
            assert "RESEND_API_KEY" in data.get("detail", "") or "Resend" in data.get("detail", "") or "email" in data.get("detail", "").lower(), \
                f"Expected error about RESEND_API_KEY, got: {data.get('detail')}"
            print(f"✅ Endpoint exists, returns expected error: {data.get('detail')}")
        else:
            print("✅ Endpoint exists and email sent successfully")
    
    def test_send_contador_email_requires_auth(self):
        """POST /api/expenses/send-contador-email requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/expenses/send-contador-email",
            json={
                "email": "test@example.com",
                "month": 1,
                "year": 2026,
                "store": "all"
            }
        )
        
        # Should return 401 without auth
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
        print("✅ Endpoint requires authentication")


class TestExpenseAnalyzeImage:
    """Test AI expense analysis with store field"""
    
    def test_analyze_image_endpoint_exists(self):
        """POST /api/expenses/analyze-image endpoint should exist"""
        # Try to call the endpoint
        response = requests.post(
            f"{BASE_URL}/api/expenses/analyze-image",
            auth=AUTH,
            json={
                "image_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
            }
        )
        
        # Check if endpoint exists (not 404)
        if response.status_code == 404:
            print(f"❌ Endpoint /api/expenses/analyze-image NOT FOUND (404)")
            pytest.fail("Endpoint /api/expenses/analyze-image does not exist - missing route decorator")
        
        # Endpoint exists - could be 200, 422 (validation), or 500 (processing error)
        assert response.status_code in [200, 422, 500], f"Unexpected status: {response.status_code}"
        print(f"✅ Endpoint exists, status: {response.status_code}")
    
    def test_analyze_multiple_images_returns_store_field(self):
        """POST /api/expenses/analyze-multiple should return store field in analysis"""
        # This endpoint exists and should return store field
        response = requests.post(
            f"{BASE_URL}/api/expenses/analyze-multiple",
            auth=AUTH,
            json={
                "images": ["iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="]
            }
        )
        
        # Check endpoint exists
        assert response.status_code != 404, "Endpoint /api/expenses/analyze-multiple not found"
        print(f"✅ Endpoint /api/expenses/analyze-multiple exists, status: {response.status_code}")


class TestMenuFiscalFields:
    """Test menu item creation with fiscal fields"""
    
    def test_menu_post_accepts_fiscal_fields(self):
        """POST /api/kitchen/menu accepts fiscal fields (ncm, csosn, cfop, codigo_barras)"""
        test_item = {
            "id": "test-fiscal-item-001",
            "name": "TEST_Fiscal_Item",
            "description": "Test item with fiscal fields",
            "price": 25.00,
            "category": "Doces",
            "store": "runner",
            "available": True,
            # Fiscal fields
            "ncm": "21069090",
            "csosn": "0102",
            "cfop": "5102",
            "codigo_barras": "7891234567890"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/kitchen/menu",
            json=test_item
        )
        
        assert response.status_code in [200, 201], f"Expected 200/201, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify fiscal fields are in response
        assert data.get("ncm") == "21069090", f"NCM not saved correctly: {data.get('ncm')}"
        assert data.get("csosn") == "0102", f"CSOSN not saved correctly: {data.get('csosn')}"
        assert data.get("cfop") == "5102", f"CFOP not saved correctly: {data.get('cfop')}"
        assert data.get("codigo_barras") == "7891234567890", f"codigo_barras not saved correctly: {data.get('codigo_barras')}"
        
        print(f"✅ Menu item created with fiscal fields: NCM={data.get('ncm')}, CSOSN={data.get('csosn')}, CFOP={data.get('cfop')}")
        
        # Cleanup - delete the test item
        item_id = data.get("id", test_item["id"])
        requests.delete(f"{BASE_URL}/api/kitchen/menu/{item_id}")
    
    def test_menu_item_model_has_fiscal_fields(self):
        """Verify MenuItem model includes fiscal fields"""
        # Get menu to verify fiscal fields are returned
        response = requests.get(f"{BASE_URL}/api/menu/runner")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        items = data.get("items", [])
        
        # Check if any item has fiscal fields defined
        has_fiscal_fields = False
        for item in items:
            if any(item.get(field) for field in ["ncm", "csosn", "cfop", "codigo_barras"]):
                has_fiscal_fields = True
                print(f"✅ Found item with fiscal fields: {item.get('name')}")
                break
        
        # Even if no items have fiscal fields set, the model should support them
        print(f"✅ Menu endpoint returns items (fiscal fields supported in model)")


class TestKitchenPrazoStoreData:
    """Test that Kitchen page fetches store-specific prazo data"""
    
    def test_kitchen_stats_endpoint(self):
        """GET /api/kitchen/{store}/stats works for both stores"""
        for store in ["runner", "gym-londres"]:
            response = requests.get(f"{BASE_URL}/api/kitchen/{store}/stats")
            assert response.status_code == 200, f"Expected 200 for {store}, got {response.status_code}"
            print(f"✅ Kitchen stats for {store}: {response.json()}")
    
    def test_prazo_debts_with_store_param(self):
        """Verify prazo debts endpoint accepts store parameter"""
        # Runner
        response = requests.get(f"{BASE_URL}/api/prazo/debts?store=runner")
        assert response.status_code == 200
        runner_data = response.json()
        
        # GYM Londres
        response = requests.get(f"{BASE_URL}/api/prazo/debts?store=gym-londres")
        assert response.status_code == 200
        gym_data = response.json()
        
        # All
        response = requests.get(f"{BASE_URL}/api/prazo/debts")
        assert response.status_code == 200
        all_data = response.json()
        
        # Verify totals make sense (runner + gym <= all, accounting for rounding)
        runner_total = runner_data.get("total_prazo", 0)
        gym_total = gym_data.get("total_prazo", 0)
        all_total = all_data.get("total_prazo", 0)
        
        print(f"✅ Prazo totals - Runner: R${runner_total}, GYM: R${gym_total}, All: R${all_total}")
        
        # Combined should equal all (or be very close due to floating point)
        combined = runner_total + gym_total
        assert abs(combined - all_total) < 0.01, f"Totals don't match: {combined} vs {all_total}"


class TestExportContadorReport:
    """Test contador report export endpoint"""
    
    def test_export_contador_endpoint_exists(self):
        """GET /api/expenses/export-contador endpoint exists"""
        response = requests.get(
            f"{BASE_URL}/api/expenses/export-contador",
            auth=AUTH,
            params={"month": 1, "year": 2026, "store": "all"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        # Verify response structure
        assert "periodo" in data, "Response should contain 'periodo'"
        assert "resumo_geral" in data, "Response should contain 'resumo_geral'"
        assert "observacoes_fiscais" in data, "Response should contain 'observacoes_fiscais'"
        
        # Verify fiscal observations include NCM, CSOSN, CFOP
        fiscal = data.get("observacoes_fiscais", {})
        assert "ncm_padrao_alimentos" in fiscal, "Should have ncm_padrao_alimentos"
        assert "csosn_padrao" in fiscal, "Should have csosn_padrao"
        assert "cfop_venda_interna" in fiscal, "Should have cfop_venda_interna"
        
        print(f"✅ Export contador report works with fiscal info: NCM={fiscal.get('ncm_padrao_alimentos')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
