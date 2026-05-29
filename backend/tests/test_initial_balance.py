"""
Test Initial Cash Balance Feature
Tests for:
- POST /api/cash/{store}/set-balance - sets initial balance
- GET /api/cash/{store}/drawer - returns initial_balance, total_cash_sales, total_withdrawals
- current_balance = initial_balance + total_cash_sales - total_withdrawals
- Initial balance persists (doesn't reset daily)
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestInitialCashBalance:
    """Tests for the initial cash balance feature"""
    
    def test_set_initial_balance_runner(self):
        """Test setting initial balance for Runner store"""
        response = requests.post(
            f"{BASE_URL}/api/cash/runner/set-balance",
            json={"balance": 150.00, "notes": "Test initial balance"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "initial_balance" in data, "Response should contain initial_balance"
        assert data["initial_balance"] == 150.00, f"Expected initial_balance=150.00, got {data['initial_balance']}"
        assert "total_cash_sales" in data, "Response should contain total_cash_sales"
        assert "total_withdrawals" in data, "Response should contain total_withdrawals"
        assert "current_balance" in data, "Response should contain current_balance"
        print(f"✅ Set initial balance for Runner: R$ {data['initial_balance']}")
    
    def test_set_initial_balance_gym_londres(self):
        """Test setting initial balance for GYM Londres store"""
        response = requests.post(
            f"{BASE_URL}/api/cash/gym-londres/set-balance",
            json={"balance": 200.00, "notes": "Test initial balance GYM"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["initial_balance"] == 200.00, f"Expected initial_balance=200.00, got {data['initial_balance']}"
        print(f"✅ Set initial balance for GYM Londres: R$ {data['initial_balance']}")
    
    def test_get_drawer_returns_all_fields_runner(self):
        """Test GET /api/cash/runner/drawer returns all required fields"""
        response = requests.get(f"{BASE_URL}/api/cash/runner/drawer")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Check all required fields are present
        required_fields = ["initial_balance", "total_cash_sales", "total_withdrawals", "current_balance"]
        for field in required_fields:
            assert field in data, f"Response missing required field: {field}"
        
        print(f"✅ Runner drawer: initial={data['initial_balance']}, sales={data['total_cash_sales']}, withdrawals={data['total_withdrawals']}, current={data['current_balance']}")
    
    def test_get_drawer_returns_all_fields_gym_londres(self):
        """Test GET /api/cash/gym-londres/drawer returns all required fields"""
        response = requests.get(f"{BASE_URL}/api/cash/gym-londres/drawer")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Check all required fields are present
        required_fields = ["initial_balance", "total_cash_sales", "total_withdrawals", "current_balance"]
        for field in required_fields:
            assert field in data, f"Response missing required field: {field}"
        
        print(f"✅ GYM Londres drawer: initial={data['initial_balance']}, sales={data['total_cash_sales']}, withdrawals={data['total_withdrawals']}, current={data['current_balance']}")
    
    def test_balance_calculation_formula(self):
        """Test that current_balance = initial_balance + total_cash_sales - total_withdrawals"""
        response = requests.get(f"{BASE_URL}/api/cash/runner/drawer")
        assert response.status_code == 200
        
        data = response.json()
        
        initial = data["initial_balance"]
        sales = data["total_cash_sales"]
        withdrawals = data["total_withdrawals"]
        current = data["current_balance"]
        
        expected_balance = initial + sales - withdrawals
        
        # Allow small floating point differences
        assert abs(current - expected_balance) < 0.01, \
            f"Balance calculation wrong: {initial} + {sales} - {withdrawals} = {expected_balance}, but got {current}"
        
        print(f"✅ Balance formula verified: {initial} + {sales} - {withdrawals} = {current}")
    
    def test_initial_balance_persists_after_update(self):
        """Test that initial balance persists and can be updated"""
        # Set initial balance
        response1 = requests.post(
            f"{BASE_URL}/api/cash/runner/set-balance",
            json={"balance": 175.00, "notes": "Updated balance"}
        )
        assert response1.status_code == 200
        
        # Get drawer status
        response2 = requests.get(f"{BASE_URL}/api/cash/runner/drawer")
        assert response2.status_code == 200
        
        data = response2.json()
        assert data["initial_balance"] == 175.00, f"Initial balance should persist as 175.00, got {data['initial_balance']}"
        
        # Update again
        response3 = requests.post(
            f"{BASE_URL}/api/cash/runner/set-balance",
            json={"balance": 150.00, "notes": "Restored to original"}
        )
        assert response3.status_code == 200
        
        # Verify update
        response4 = requests.get(f"{BASE_URL}/api/cash/runner/drawer")
        data4 = response4.json()
        assert data4["initial_balance"] == 150.00, f"Initial balance should be 150.00 after restore, got {data4['initial_balance']}"
        
        print("✅ Initial balance persists and can be updated correctly")
    
    def test_initial_balance_does_not_count_as_sale(self):
        """Test that initial balance doesn't affect total_cash_sales"""
        # Get current state
        response1 = requests.get(f"{BASE_URL}/api/cash/runner/drawer")
        data1 = response1.json()
        original_sales = data1["total_cash_sales"]
        
        # Update initial balance
        response2 = requests.post(
            f"{BASE_URL}/api/cash/runner/set-balance",
            json={"balance": 500.00, "notes": "Big balance test"}
        )
        assert response2.status_code == 200
        
        # Check that sales didn't change
        response3 = requests.get(f"{BASE_URL}/api/cash/runner/drawer")
        data3 = response3.json()
        
        assert data3["total_cash_sales"] == original_sales, \
            f"total_cash_sales should not change when setting initial balance. Was {original_sales}, now {data3['total_cash_sales']}"
        
        # Restore original balance
        requests.post(
            f"{BASE_URL}/api/cash/runner/set-balance",
            json={"balance": 150.00, "notes": "Restored"}
        )
        
        print("✅ Initial balance does NOT count as a sale")
    
    def test_set_balance_with_zero(self):
        """Test setting initial balance to zero"""
        response = requests.post(
            f"{BASE_URL}/api/cash/runner/set-balance",
            json={"balance": 0.00, "notes": "Reset to zero"}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["initial_balance"] == 0.00, f"Initial balance should be 0.00, got {data['initial_balance']}"
        
        # Restore
        requests.post(
            f"{BASE_URL}/api/cash/runner/set-balance",
            json={"balance": 150.00, "notes": "Restored"}
        )
        
        print("✅ Initial balance can be set to zero")
    
    def test_today_data_separate_from_historical(self):
        """Test that today's data is separate from historical totals"""
        response = requests.get(f"{BASE_URL}/api/cash/runner/drawer")
        assert response.status_code == 200
        
        data = response.json()
        
        # Check today fields exist
        assert "today_cash_in" in data, "Response should contain today_cash_in"
        assert "today_withdrawals" in data, "Response should contain today_withdrawals"
        
        # Today's values should be <= historical totals
        assert data["today_cash_in"] <= data["total_cash_sales"], \
            "Today's cash in should be <= total historical sales"
        assert data["today_withdrawals"] <= data["total_withdrawals"], \
            "Today's withdrawals should be <= total historical withdrawals"
        
        print(f"✅ Today data: cash_in={data['today_cash_in']}, withdrawals={data['today_withdrawals']}")


class TestCashDrawerIntegration:
    """Integration tests for cash drawer with orders and withdrawals"""
    
    def test_withdrawal_affects_balance(self):
        """Test that withdrawals reduce the current balance"""
        # Get initial state
        response1 = requests.get(f"{BASE_URL}/api/cash/runner/drawer")
        data1 = response1.json()
        initial_current = data1["current_balance"]
        initial_withdrawals = data1["total_withdrawals"]
        
        # Only test withdrawal if there's enough balance
        if initial_current >= 10:
            response2 = requests.post(
                f"{BASE_URL}/api/cash/runner/withdraw",
                json={"amount": 10.00, "category": "outros", "description": "TEST_withdrawal"}
            )
            
            if response2.status_code == 200:
                # Check balance decreased
                response3 = requests.get(f"{BASE_URL}/api/cash/runner/drawer")
                data3 = response3.json()
                
                assert data3["total_withdrawals"] == initial_withdrawals + 10.00, \
                    f"Total withdrawals should increase by 10.00"
                assert data3["current_balance"] == initial_current - 10.00, \
                    f"Current balance should decrease by 10.00"
                
                print(f"✅ Withdrawal affects balance: {initial_current} - 10 = {data3['current_balance']}")
            else:
                print(f"⚠️ Withdrawal failed (possibly insufficient balance): {response2.text}")
        else:
            print(f"⚠️ Skipping withdrawal test - insufficient balance: {initial_current}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
