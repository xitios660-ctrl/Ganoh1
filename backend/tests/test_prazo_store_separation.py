"""
Test Prazo Debts Store Separation and WhatsApp Charge Features
Tests for:
1. Prazo debts separation by store (Runner vs GYM Londres)
2. Prazo charge customer endpoint sends to customer phone
3. Prazo charge-all-whatsapp with store filter
4. PIX verification validates comprovante before WhatsApp notification
5. WhatsApp group configuration per store
"""

import pytest
import requests
import os
from requests.auth import HTTPBasicAuth

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Credentials
GESTOR_USER = "gestor"
GESTOR_PASS = "ganoh2024"
PRAZO_PASSWORD = "1234"


class TestPrazoDebtsStoreSeparation:
    """Test prazo debts are correctly separated by store"""
    
    def test_prazo_debts_runner_only(self):
        """Test GET /api/prazo/debts?store=runner returns only Runner debts"""
        response = requests.get(f"{BASE_URL}/api/prazo/debts?store=runner", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "debts" in data, "Response should contain 'debts'"
        assert "total_prazo" in data, "Response should contain 'total_prazo'"
        assert "customer_count" in data, "Response should contain 'customer_count'"
        assert data.get("store_filter") == "runner", f"Store filter should be 'runner', got {data.get('store_filter')}"
        
        # Verify all orders in debts are from runner store
        for debt in data.get("debts", []):
            for order in debt.get("orders", []):
                assert order.get("store") == "runner", f"Order store should be 'runner', got {order.get('store')}"
        
        print(f"✅ Runner prazo debts: R$ {data['total_prazo']:.2f} from {data['customer_count']} customer(s)")
        return data
    
    def test_prazo_debts_gym_londres_only(self):
        """Test GET /api/prazo/debts?store=gym-londres returns only GYM Londres debts"""
        response = requests.get(f"{BASE_URL}/api/prazo/debts?store=gym-londres", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "debts" in data, "Response should contain 'debts'"
        assert "total_prazo" in data, "Response should contain 'total_prazo'"
        assert data.get("store_filter") == "gym-londres", f"Store filter should be 'gym-londres', got {data.get('store_filter')}"
        
        # Verify all orders in debts are from gym-londres store
        for debt in data.get("debts", []):
            for order in debt.get("orders", []):
                assert order.get("store") == "gym-londres", f"Order store should be 'gym-londres', got {order.get('store')}"
        
        print(f"✅ GYM Londres prazo debts: R$ {data['total_prazo']:.2f} from {data['customer_count']} customer(s)")
        return data
    
    def test_prazo_debts_all_stores(self):
        """Test GET /api/prazo/debts without store filter returns all debts"""
        response = requests.get(f"{BASE_URL}/api/prazo/debts", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "debts" in data
        assert data.get("store_filter") == "all", f"Store filter should be 'all', got {data.get('store_filter')}"
        
        print(f"✅ All stores prazo debts: R$ {data['total_prazo']:.2f} from {data['customer_count']} customer(s)")
        return data
    
    def test_store_separation_totals_match(self):
        """Test that Runner + GYM Londres totals equal all stores total"""
        # Get all three responses
        runner_resp = requests.get(f"{BASE_URL}/api/prazo/debts?store=runner", timeout=10)
        gym_resp = requests.get(f"{BASE_URL}/api/prazo/debts?store=gym-londres", timeout=10)
        all_resp = requests.get(f"{BASE_URL}/api/prazo/debts", timeout=10)
        
        assert runner_resp.status_code == 200
        assert gym_resp.status_code == 200
        assert all_resp.status_code == 200
        
        runner_total = runner_resp.json().get("total_prazo", 0)
        gym_total = gym_resp.json().get("total_prazo", 0)
        all_total = all_resp.json().get("total_prazo", 0)
        
        # Sum of individual stores should equal total
        combined = runner_total + gym_total
        assert abs(combined - all_total) < 0.01, f"Runner ({runner_total}) + GYM ({gym_total}) = {combined} should equal All ({all_total})"
        
        print(f"✅ Store totals match: Runner R${runner_total:.2f} + GYM R${gym_total:.2f} = R${combined:.2f} (All: R${all_total:.2f})")


class TestPrazoChargeCustomer:
    """Test prazo charge customer endpoint"""
    
    def test_charge_customer_no_debts(self):
        """Test charging a customer with no debts returns appropriate message"""
        response = requests.post(
            f"{BASE_URL}/api/prazo/charge-customer/NONEXISTENT_CUSTOMER_12345",
            timeout=10
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("success") == False, "Should return success=False for non-existent customer"
        assert "não tem débitos" in data.get("message", "").lower() or "no debts" in data.get("message", "").lower(), \
            f"Message should indicate no debts: {data.get('message')}"
        
        print(f"✅ Charge non-existent customer returns: {data.get('message')}")
    
    def test_charge_customer_endpoint_exists(self):
        """Test that charge customer endpoint exists and responds"""
        # First get a customer with debts
        debts_resp = requests.get(f"{BASE_URL}/api/prazo/debts", timeout=10)
        assert debts_resp.status_code == 200
        
        debts = debts_resp.json().get("debts", [])
        if not debts:
            pytest.skip("No prazo customers with debts to test")
        
        customer_name = debts[0].get("name")
        
        # Try to charge (may fail if no phone, but endpoint should work)
        response = requests.post(
            f"{BASE_URL}/api/prazo/charge-customer/{customer_name}",
            timeout=10
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        # Either success or "no phone" message
        assert "success" in data, "Response should contain 'success' field"
        
        if data.get("success"):
            print(f"✅ Charge sent to {customer_name}: R${data.get('total_debt', 0):.2f}")
        else:
            print(f"✅ Charge endpoint works, message: {data.get('message')}")


class TestPrazoChargeAllWhatsApp:
    """Test charge all prazo customers via WhatsApp with store filter"""
    
    def test_charge_all_runner_store(self):
        """Test POST /api/prazo/charge-all-whatsapp?store=runner"""
        response = requests.post(
            f"{BASE_URL}/api/prazo/charge-all-whatsapp?store=runner",
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "success" in data
        assert "messages_sent" in data
        assert "total_customers" in data
        
        print(f"✅ Runner charge-all: {data.get('messages_sent')} sent, {len(data.get('no_phone', []))} no phone")
    
    def test_charge_all_gym_londres_store(self):
        """Test POST /api/prazo/charge-all-whatsapp?store=gym-londres"""
        response = requests.post(
            f"{BASE_URL}/api/prazo/charge-all-whatsapp?store=gym-londres",
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "success" in data
        assert "messages_sent" in data
        
        print(f"✅ GYM Londres charge-all: {data.get('messages_sent')} sent, {len(data.get('no_phone', []))} no phone")


class TestPIXVerificationFlow:
    """Test PIX verification validates comprovante before sending WhatsApp notification"""
    
    def test_pix_order_starts_pending(self):
        """Test PIX orders start with pending_payment status"""
        order_data = {
            "store": "runner",
            "customer_name": "TEST_PIX_Verification",
            "items": [
                {
                    "menu_item_id": "1",
                    "name": "Frango com Requeijão",
                    "price": 25.50,
                    "quantity": 1
                }
            ],
            "total": 25.50,
            "payment_method": "pix"
        }
        
        response = requests.post(f"{BASE_URL}/api/orders", json=order_data, timeout=10)
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "pending_payment", "PIX orders should start as pending_payment"
        
        print(f"✅ PIX order created with status: {data['status']}")
        return data["id"]
    
    def test_auto_verify_pix_endpoint_exists(self):
        """Test auto-verify PIX endpoint exists"""
        # Create a test order first
        order_data = {
            "store": "runner",
            "customer_name": "TEST_AutoVerify",
            "items": [{"menu_item_id": "1", "name": "Test Item", "price": 10.00, "quantity": 1}],
            "total": 10.00,
            "payment_method": "pix"
        }
        
        create_resp = requests.post(f"{BASE_URL}/api/orders", json=order_data, timeout=10)
        assert create_resp.status_code == 200
        order_id = create_resp.json()["id"]
        
        # Try to auto-verify (will fail without proof, but endpoint should exist)
        response = requests.post(
            f"{BASE_URL}/api/orders/runner/{order_id}/auto-verify-pix",
            timeout=10
        )
        # Should return 400 (no proof) or 200 (with result)
        assert response.status_code in [200, 400], f"Expected 200 or 400, got {response.status_code}"
        
        print(f"✅ Auto-verify PIX endpoint exists and responds")
    
    def test_pix_proof_upload_endpoint(self):
        """Test PIX proof upload endpoint exists"""
        # Create a test order
        order_data = {
            "store": "runner",
            "customer_name": "TEST_ProofUpload",
            "items": [{"menu_item_id": "1", "name": "Test Item", "price": 10.00, "quantity": 1}],
            "total": 10.00,
            "payment_method": "pix"
        }
        
        create_resp = requests.post(f"{BASE_URL}/api/orders", json=order_data, timeout=10)
        assert create_resp.status_code == 200
        order_id = create_resp.json()["id"]
        
        # Try to upload proof (with dummy base64)
        proof_data = {
            "proof_image": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAA=="
        }
        
        response = requests.post(
            f"{BASE_URL}/api/orders/runner/{order_id}/pix-proof",
            json=proof_data,
            timeout=10
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("success") == True, "Proof upload should succeed"
        
        print(f"✅ PIX proof upload endpoint works")


class TestWhatsAppGroupConfiguration:
    """Test WhatsApp group configuration per store"""
    
    def test_whatsapp_status_endpoint(self):
        """Test WhatsApp status endpoint is accessible"""
        response = requests.get(f"{BASE_URL}/api/whatsapp/status", timeout=10)
        assert response.status_code == 200
        
        data = response.json()
        assert "status" in data
        assert "connected" in data
        
        print(f"✅ WhatsApp status: {data['status']}, connected: {data['connected']}")
    
    def test_stores_endpoint(self):
        """Test stores endpoint returns both stores"""
        response = requests.get(f"{BASE_URL}/api/stores", timeout=10)
        assert response.status_code == 200
        
        data = response.json()
        assert "runner" in data["stores"]
        assert "gym-londres" in data["stores"]
        
        print(f"✅ Both stores configured: Runner and GYM Londres")


class TestKitchenPagePrazoIntegration:
    """Test Kitchen page prazo tab integration"""
    
    def test_kitchen_stats_endpoint(self):
        """Test kitchen stats endpoint for both stores"""
        for store in ["runner", "gym-londres"]:
            response = requests.get(f"{BASE_URL}/api/kitchen/{store}/stats", timeout=10)
            assert response.status_code == 200, f"Expected 200 for {store}, got {response.status_code}"
            
            data = response.json()
            assert "pending" in data
            assert "preparing" in data
            assert "ready" in data
            
            print(f"✅ Kitchen stats for {store}: pending={data['pending']}, preparing={data['preparing']}, ready={data['ready']}")
    
    def test_prazo_customers_endpoint(self):
        """Test prazo customers endpoint"""
        response = requests.get(f"{BASE_URL}/api/prazo/customers", timeout=10)
        assert response.status_code == 200
        
        data = response.json()
        assert "customers" in data
        
        print(f"✅ Prazo customers endpoint: {len(data['customers'])} customers")


class TestCreatePrazoOrdersForTesting:
    """Create test prazo orders to verify store separation"""
    
    def test_create_runner_prazo_order(self):
        """Create a prazo order for Runner store"""
        order_data = {
            "store": "runner",
            "customer_name": "TEST_Runner_Prazo",
            "items": [
                {
                    "menu_item_id": "1",
                    "name": "Frango com Requeijão",
                    "price": 25.50,
                    "quantity": 2
                }
            ],
            "total": 51.00,
            "payment_method": "prazo"
        }
        
        response = requests.post(f"{BASE_URL}/api/orders", json=order_data, timeout=10)
        assert response.status_code == 200
        
        data = response.json()
        assert data["store"] == "runner"
        assert data["payment_method"] == "prazo"
        
        print(f"✅ Created Runner prazo order: R${data['total']:.2f}")
        return data["id"]
    
    def test_create_gym_prazo_order(self):
        """Create a prazo order for GYM Londres store"""
        order_data = {
            "store": "gym-londres",
            "customer_name": "TEST_GYM_Prazo",
            "items": [
                {
                    "menu_item_id": "1",
                    "name": "Frango com Requeijão",
                    "price": 25.50,
                    "quantity": 1
                }
            ],
            "total": 25.50,
            "payment_method": "prazo"
        }
        
        response = requests.post(f"{BASE_URL}/api/orders", json=order_data, timeout=10)
        assert response.status_code == 200
        
        data = response.json()
        assert data["store"] == "gym-londres"
        assert data["payment_method"] == "prazo"
        
        print(f"✅ Created GYM Londres prazo order: R${data['total']:.2f}")
        return data["id"]
    
    def test_verify_store_separation_after_creation(self):
        """Verify store separation works after creating test orders"""
        # Get Runner debts
        runner_resp = requests.get(f"{BASE_URL}/api/prazo/debts?store=runner", timeout=10)
        assert runner_resp.status_code == 200
        runner_data = runner_resp.json()
        
        # Get GYM Londres debts
        gym_resp = requests.get(f"{BASE_URL}/api/prazo/debts?store=gym-londres", timeout=10)
        assert gym_resp.status_code == 200
        gym_data = gym_resp.json()
        
        # Check TEST_Runner_Prazo is in Runner debts
        runner_names = [d["name"] for d in runner_data.get("debts", [])]
        gym_names = [d["name"] for d in gym_data.get("debts", [])]
        
        # TEST_Runner_Prazo should be in runner, not in gym
        if "TEST_Runner_Prazo" in runner_names:
            assert "TEST_Runner_Prazo" not in gym_names, "TEST_Runner_Prazo should not appear in GYM Londres debts"
            print(f"✅ TEST_Runner_Prazo correctly appears only in Runner debts")
        
        # TEST_GYM_Prazo should be in gym, not in runner
        if "TEST_GYM_Prazo" in gym_names:
            assert "TEST_GYM_Prazo" not in runner_names, "TEST_GYM_Prazo should not appear in Runner debts"
            print(f"✅ TEST_GYM_Prazo correctly appears only in GYM Londres debts")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
