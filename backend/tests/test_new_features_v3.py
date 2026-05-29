"""
Test suite for new features:
1. DELETE /api/prazo/debt/{customer_name} - Clear prazo debt with password
2. POST /api/cash/{store}/set-balance - Set initial cash balance
3. GET /api/gestor/chart/daily?store=runner - Daily chart filtered by store
"""
import pytest
import requests
import os
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
GESTOR_USERNAME = "gestor"
GESTOR_PASSWORD = "ganoh2024"
PRAZO_PASSWORD = "1234"


class TestDeletePrazoDebt:
    """Test DELETE /api/prazo/debt/{customer_name} endpoint"""
    
    def test_delete_prazo_debt_with_correct_password(self):
        """Test deleting prazo debt with correct password"""
        # First, create a test prazo order
        test_customer = f"TEST_PrazoDelete_{datetime.now().strftime('%H%M%S')}"
        
        # Create a prazo order
        order_data = {
            "store": "runner",
            "customer_name": test_customer,
            "items": [{"menu_item_id": "1", "name": "Test Item", "price": 25.0, "quantity": 1}],
            "total": 25.0,
            "payment_method": "prazo"
        }
        create_response = requests.post(f"{BASE_URL}/api/orders", json=order_data)
        assert create_response.status_code == 200, f"Failed to create test order: {create_response.text}"
        
        # Verify debt exists
        debts_response = requests.get(f"{BASE_URL}/api/prazo/debts?store=runner")
        assert debts_response.status_code == 200
        debts_data = debts_response.json()
        customer_debt = next((d for d in debts_data.get("debts", []) if d["name"] == test_customer), None)
        assert customer_debt is not None, f"Test customer debt not found in debts list"
        
        # Delete the debt with correct password
        delete_response = requests.delete(
            f"{BASE_URL}/api/prazo/debt/{test_customer}?password={PRAZO_PASSWORD}"
        )
        assert delete_response.status_code == 200, f"Delete failed: {delete_response.text}"
        
        # Verify response structure
        delete_data = delete_response.json()
        assert delete_data.get("success") == True
        assert "message" in delete_data
        assert "orders_cleared" in delete_data
        
        # Verify debt is cleared
        debts_after = requests.get(f"{BASE_URL}/api/prazo/debts?store=runner")
        debts_after_data = debts_after.json()
        customer_debt_after = next((d for d in debts_after_data.get("debts", []) if d["name"] == test_customer), None)
        assert customer_debt_after is None, "Debt should be cleared after delete"
    
    def test_delete_prazo_debt_with_wrong_password(self):
        """Test deleting prazo debt with wrong password returns 403"""
        response = requests.delete(
            f"{BASE_URL}/api/prazo/debt/TestCustomer?password=wrongpassword"
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        assert "Senha incorreta" in response.json().get("detail", "")
    
    def test_delete_prazo_debt_without_password(self):
        """Test deleting prazo debt without password returns 403"""
        response = requests.delete(f"{BASE_URL}/api/prazo/debt/TestCustomer")
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"


class TestSetCashBalance:
    """Test POST /api/cash/{store}/set-balance endpoint"""
    
    def test_set_cash_balance_runner(self):
        """Test setting initial cash balance for Runner store"""
        test_balance = 250.00
        
        response = requests.post(
            f"{BASE_URL}/api/cash/runner/set-balance",
            json={"balance": test_balance, "notes": "Test balance adjustment"}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        # Verify response contains expected fields
        assert "initial_balance" in data, "Response should contain initial_balance"
        assert data["initial_balance"] == test_balance, f"Expected {test_balance}, got {data['initial_balance']}"
        assert "current_balance" in data, "Response should contain current_balance"
        assert "total_cash_sales" in data, "Response should contain total_cash_sales"
        assert "total_withdrawals" in data, "Response should contain total_withdrawals"
    
    def test_set_cash_balance_gym_londres(self):
        """Test setting initial cash balance for GYM Londres store"""
        test_balance = 300.00
        
        response = requests.post(
            f"{BASE_URL}/api/cash/gym-londres/set-balance",
            json={"balance": test_balance, "notes": "Test GYM balance"}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert data["initial_balance"] == test_balance
    
    def test_set_cash_balance_zero(self):
        """Test setting cash balance to zero"""
        response = requests.post(
            f"{BASE_URL}/api/cash/runner/set-balance",
            json={"balance": 0, "notes": "Reset to zero"}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert data["initial_balance"] == 0
    
    def test_get_cash_drawer_after_set_balance(self):
        """Test that GET /api/cash/{store}/drawer returns updated balance"""
        test_balance = 175.50
        
        # Set balance
        set_response = requests.post(
            f"{BASE_URL}/api/cash/runner/set-balance",
            json={"balance": test_balance}
        )
        assert set_response.status_code == 200
        
        # Get drawer status
        get_response = requests.get(f"{BASE_URL}/api/cash/runner/drawer")
        assert get_response.status_code == 200
        
        data = get_response.json()
        assert data["initial_balance"] == test_balance
        # current_balance = initial_balance + total_cash_sales - total_withdrawals
        expected_current = test_balance + data.get("total_cash_sales", 0) - data.get("total_withdrawals", 0)
        assert abs(data["current_balance"] - expected_current) < 0.01, f"Balance calculation mismatch"


class TestDailyChartStoreFilter:
    """Test GET /api/gestor/chart/daily with store filter"""
    
    def test_daily_chart_all_stores(self):
        """Test daily chart without store filter (all stores)"""
        response = requests.get(
            f"{BASE_URL}/api/gestor/chart/daily",
            auth=(GESTOR_USERNAME, GESTOR_PASSWORD)
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert "date" in data
        assert "data" in data
        assert "total_day" in data
        assert "store_filter" in data
        assert data["store_filter"] == "all" or data["store_filter"] is None
    
    def test_daily_chart_runner_filter(self):
        """Test daily chart filtered by Runner store"""
        response = requests.get(
            f"{BASE_URL}/api/gestor/chart/daily?store=runner",
            auth=(GESTOR_USERNAME, GESTOR_PASSWORD)
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert data["store_filter"] == "runner", f"Expected store_filter='runner', got {data.get('store_filter')}"
        assert "data" in data
        assert "total_day" in data
        assert "by_payment" in data
    
    def test_daily_chart_gym_londres_filter(self):
        """Test daily chart filtered by GYM Londres store"""
        response = requests.get(
            f"{BASE_URL}/api/gestor/chart/daily?store=gym-londres",
            auth=(GESTOR_USERNAME, GESTOR_PASSWORD)
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert data["store_filter"] == "gym-londres", f"Expected store_filter='gym-londres', got {data.get('store_filter')}"
        assert "data" in data
        assert "total_day" in data
    
    def test_daily_chart_with_date_and_store(self):
        """Test daily chart with both date and store filter"""
        today = datetime.now().strftime("%Y-%m-%d")
        
        response = requests.get(
            f"{BASE_URL}/api/gestor/chart/daily?date={today}&store=runner",
            auth=(GESTOR_USERNAME, GESTOR_PASSWORD)
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert data["store_filter"] == "runner"
        assert "date" in data
    
    def test_daily_chart_response_structure(self):
        """Test that daily chart response has all expected fields"""
        response = requests.get(
            f"{BASE_URL}/api/gestor/chart/daily?store=runner",
            auth=(GESTOR_USERNAME, GESTOR_PASSWORD)
        )
        assert response.status_code == 200
        
        data = response.json()
        
        # Check required fields
        required_fields = ["date", "date_iso", "store_filter", "data", "total_day", "total_orders", "by_store", "by_payment"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        
        # Check data array structure
        assert isinstance(data["data"], list), "data should be a list"
        if len(data["data"]) > 0:
            hour_data = data["data"][0]
            assert "hour" in hour_data
            assert "total" in hour_data
            assert "count" in hour_data
        
        # Check by_payment structure
        by_payment = data["by_payment"]
        payment_methods = ["pix", "debito", "credito", "dinheiro", "prazo", "voucher"]
        for method in payment_methods:
            assert method in by_payment, f"Missing payment method: {method}"


class TestPrazoDebtsStoreFilter:
    """Test GET /api/prazo/debts with store filter"""
    
    def test_prazo_debts_all_stores(self):
        """Test prazo debts without store filter"""
        response = requests.get(f"{BASE_URL}/api/prazo/debts")
        assert response.status_code == 200
        
        data = response.json()
        assert "debts" in data
        assert "total_prazo" in data
    
    def test_prazo_debts_runner_filter(self):
        """Test prazo debts filtered by Runner store"""
        response = requests.get(f"{BASE_URL}/api/prazo/debts?store=runner")
        assert response.status_code == 200
        
        data = response.json()
        assert "debts" in data
        assert "total_prazo" in data
        assert "store_filter" in data
        assert data["store_filter"] == "runner"
    
    def test_prazo_debts_gym_londres_filter(self):
        """Test prazo debts filtered by GYM Londres store"""
        response = requests.get(f"{BASE_URL}/api/prazo/debts?store=gym-londres")
        assert response.status_code == 200
        
        data = response.json()
        assert "debts" in data
        assert data["store_filter"] == "gym-londres"


# Cleanup fixture
@pytest.fixture(autouse=True)
def cleanup_test_data():
    """Cleanup test data after tests"""
    yield
    # Cleanup: Reset cash balance to reasonable value
    requests.post(
        f"{BASE_URL}/api/cash/runner/set-balance",
        json={"balance": 150.00, "notes": "Test cleanup"}
    )
    requests.post(
        f"{BASE_URL}/api/cash/gym-londres/set-balance",
        json={"balance": 200.00, "notes": "Test cleanup"}
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
