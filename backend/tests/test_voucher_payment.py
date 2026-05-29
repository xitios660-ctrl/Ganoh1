"""
Test Voucher Payment Method Integration
Tests that 'voucher' payment method appears in all sales and dashboard endpoints
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://prazo-accounting.preview.emergentagent.com').rstrip('/')

class TestVoucherPaymentMethod:
    """Tests for voucher payment method in backend APIs"""
    
    def test_cash_today_returns_voucher_in_by_payment_method(self):
        """Test /api/cash/{store}/today returns 'voucher' in by_payment_method"""
        response = requests.get(f"{BASE_URL}/api/cash/runner/today")
        assert response.status_code == 200
        
        data = response.json()
        assert "by_payment_method" in data
        assert "voucher" in data["by_payment_method"], "voucher should be in by_payment_method"
        # Verify all 6 payment methods are present
        expected_methods = ["pix", "debit", "credit", "cash", "prazo", "voucher"]
        for method in expected_methods:
            assert method in data["by_payment_method"], f"{method} should be in by_payment_method"
    
    def test_cash_today_returns_voucher_in_morning_shift(self):
        """Test /api/cash/{store}/today returns 'voucher' in shifts.morning.by_payment"""
        response = requests.get(f"{BASE_URL}/api/cash/runner/today")
        assert response.status_code == 200
        
        data = response.json()
        assert "shifts" in data
        assert "morning" in data["shifts"]
        assert "by_payment" in data["shifts"]["morning"]
        assert "voucher" in data["shifts"]["morning"]["by_payment"], "voucher should be in morning shift by_payment"
    
    def test_cash_today_returns_voucher_in_afternoon_shift(self):
        """Test /api/cash/{store}/today returns 'voucher' in shifts.afternoon.by_payment"""
        response = requests.get(f"{BASE_URL}/api/cash/runner/today")
        assert response.status_code == 200
        
        data = response.json()
        assert "shifts" in data
        assert "afternoon" in data["shifts"]
        assert "by_payment" in data["shifts"]["afternoon"]
        assert "voucher" in data["shifts"]["afternoon"]["by_payment"], "voucher should be in afternoon shift by_payment"
    
    def test_gestor_dashboard_returns_voucher_in_today_by_payment_method(self):
        """Test /api/gestor/dashboard returns 'voucher' in today.by_payment_method"""
        response = requests.get(
            f"{BASE_URL}/api/gestor/dashboard",
            auth=("gestor", "ganoh2024")
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "stores" in data
        
        # Check Runner store
        assert "runner" in data["stores"]
        assert "today" in data["stores"]["runner"]
        assert "by_payment_method" in data["stores"]["runner"]["today"]
        assert "voucher" in data["stores"]["runner"]["today"]["by_payment_method"], "voucher should be in Runner today by_payment_method"
        
        # Check GYM Londres store
        assert "gym-londres" in data["stores"]
        assert "today" in data["stores"]["gym-londres"]
        assert "by_payment_method" in data["stores"]["gym-londres"]["today"]
        assert "voucher" in data["stores"]["gym-londres"]["today"]["by_payment_method"], "voucher should be in GYM Londres today by_payment_method"
    
    def test_gestor_dashboard_returns_prazo_in_today_by_payment_method(self):
        """Test /api/gestor/dashboard returns 'prazo' in today.by_payment_method"""
        response = requests.get(
            f"{BASE_URL}/api/gestor/dashboard",
            auth=("gestor", "ganoh2024")
        )
        assert response.status_code == 200
        
        data = response.json()
        
        # Check Runner store
        assert "prazo" in data["stores"]["runner"]["today"]["by_payment_method"], "prazo should be in Runner today by_payment_method"
        
        # Check GYM Londres store
        assert "prazo" in data["stores"]["gym-londres"]["today"]["by_payment_method"], "prazo should be in GYM Londres today by_payment_method"
    
    def test_create_order_with_voucher_payment(self):
        """Test creating an order with voucher payment method"""
        order_data = {
            "store": "runner",
            "customer_name": "TEST_Voucher_Order",
            "items": [{"menu_item_id": "1", "name": "Frango com Requeijão", "price": 25.50, "quantity": 1}],
            "total": 25.50,
            "payment_method": "voucher"
        }
        
        response = requests.post(f"{BASE_URL}/api/orders", json=order_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["payment_method"] == "voucher"
        assert data["status"] == "received"
        assert data["total"] == 25.50
        
        # Clean up - delete the test order
        order_id = data["id"]
        delete_response = requests.delete(f"{BASE_URL}/api/orders/runner/{order_id}")
        assert delete_response.status_code == 200
    
    def test_all_six_payment_methods_in_cash_endpoint(self):
        """Test that all 6 payment methods are present in cash endpoint"""
        response = requests.get(f"{BASE_URL}/api/cash/runner/today")
        assert response.status_code == 200
        
        data = response.json()
        expected_methods = ["pix", "debit", "credit", "cash", "prazo", "voucher"]
        
        # Check by_payment_method
        for method in expected_methods:
            assert method in data["by_payment_method"], f"{method} missing from by_payment_method"
        
        # Check morning shift
        for method in expected_methods:
            assert method in data["shifts"]["morning"]["by_payment"], f"{method} missing from morning shift"
        
        # Check afternoon shift
        for method in expected_methods:
            assert method in data["shifts"]["afternoon"]["by_payment"], f"{method} missing from afternoon shift"
    
    def test_all_six_payment_methods_in_dashboard_endpoint(self):
        """Test that all 6 payment methods are present in dashboard endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/gestor/dashboard",
            auth=("gestor", "ganoh2024")
        )
        assert response.status_code == 200
        
        data = response.json()
        expected_methods = ["pix", "debit", "credit", "cash", "prazo", "voucher"]
        
        for store in ["runner", "gym-londres"]:
            for method in expected_methods:
                assert method in data["stores"][store]["today"]["by_payment_method"], f"{method} missing from {store} today by_payment_method"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
