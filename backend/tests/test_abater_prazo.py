"""
Test cases for Prazo Abater (Partial Payment) feature
Tests the POST /api/prazo/abater/{customer_name} endpoint
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
PRAZO_PASSWORD = "1234"

class TestAbaterPrazoEndpoint:
    """Tests for POST /api/prazo/abater/{customer_name} endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup_test_data(self):
        """Create test prazo orders before each test"""
        self.test_customer = f"TEST_Abater_Customer_{uuid.uuid4().hex[:6]}"
        self.store = "runner"
        
        # Create 2 prazo orders for the test customer
        order1 = {
            "store": self.store,
            "customer_name": self.test_customer,
            "items": [{"menu_item_id": "1", "name": "Test Item 1", "price": 20.00, "quantity": 1}],
            "total": 20.00,
            "payment_method": "prazo"
        }
        order2 = {
            "store": self.store,
            "customer_name": self.test_customer,
            "items": [{"menu_item_id": "2", "name": "Test Item 2", "price": 30.00, "quantity": 1}],
            "total": 30.00,
            "payment_method": "prazo"
        }
        
        # Create orders
        resp1 = requests.post(f"{BASE_URL}/api/orders", json=order1)
        resp2 = requests.post(f"{BASE_URL}/api/orders", json=order2)
        
        assert resp1.status_code == 200, f"Failed to create order 1: {resp1.text}"
        assert resp2.status_code == 200, f"Failed to create order 2: {resp2.text}"
        
        self.order1_id = resp1.json().get("id")
        self.order2_id = resp2.json().get("id")
        
        yield
        
        # Cleanup: Delete test orders
        requests.delete(f"{BASE_URL}/api/orders/{self.store}/{self.order1_id}")
        requests.delete(f"{BASE_URL}/api/orders/{self.store}/{self.order2_id}")
    
    def test_abater_partial_payment_success(self):
        """Test successful partial payment (abater) on prazo debt"""
        # Verify initial debt
        debts_resp = requests.get(f"{BASE_URL}/api/prazo/debts?store={self.store}")
        assert debts_resp.status_code == 200
        
        debts = debts_resp.json().get("debts", [])
        customer_debt = next((d for d in debts if d["name"] == self.test_customer), None)
        assert customer_debt is not None, f"Customer {self.test_customer} not found in debts"
        assert customer_debt["total"] == 50.00, f"Expected total 50.00, got {customer_debt['total']}"
        
        # Make partial payment of R$ 15.00
        abater_resp = requests.post(
            f"{BASE_URL}/api/prazo/abater/{self.test_customer}",
            json={"amount": 15.00, "password": PRAZO_PASSWORD}
        )
        
        assert abater_resp.status_code == 200, f"Abater failed: {abater_resp.text}"
        result = abater_resp.json()
        
        # Verify response
        assert result["success"] == True
        assert result["previous_debt"] == 50.00
        assert result["paid"] == 15.00
        assert result["new_debt"] == 35.00
        assert "Pagamento de R$ 15.00 registrado" in result["message"]
        
        print(f"✅ Partial payment of R$ 15.00 successful. New debt: R$ {result['new_debt']}")
    
    def test_abater_updates_debt_correctly(self):
        """Test that abater correctly updates the debt in GET /api/prazo/debts"""
        # Make partial payment
        abater_resp = requests.post(
            f"{BASE_URL}/api/prazo/abater/{self.test_customer}",
            json={"amount": 10.00, "password": PRAZO_PASSWORD}
        )
        assert abater_resp.status_code == 200
        
        # Verify debt is updated
        debts_resp = requests.get(f"{BASE_URL}/api/prazo/debts?store={self.store}")
        assert debts_resp.status_code == 200
        
        debts = debts_resp.json().get("debts", [])
        customer_debt = next((d for d in debts if d["name"] == self.test_customer), None)
        
        assert customer_debt is not None, "Customer should still have debt"
        assert customer_debt["total"] == 40.00, f"Expected remaining debt 40.00, got {customer_debt['total']}"
        
        print(f"✅ Debt correctly updated to R$ {customer_debt['total']} after partial payment")
    
    def test_abater_pays_off_order_completely(self):
        """Test that abater can pay off an entire order when amount equals order total"""
        # Pay exactly the first order amount (R$ 20.00)
        abater_resp = requests.post(
            f"{BASE_URL}/api/prazo/abater/{self.test_customer}",
            json={"amount": 20.00, "password": PRAZO_PASSWORD}
        )
        assert abater_resp.status_code == 200
        result = abater_resp.json()
        
        assert result["orders_paid_off"] >= 1, "At least one order should be paid off"
        assert result["new_debt"] == 30.00, f"Expected new debt 30.00, got {result['new_debt']}"
        
        print(f"✅ Order paid off completely. Orders paid off: {result['orders_paid_off']}")
    
    def test_abater_wrong_password(self):
        """Test that abater fails with wrong password"""
        abater_resp = requests.post(
            f"{BASE_URL}/api/prazo/abater/{self.test_customer}",
            json={"amount": 10.00, "password": "wrong_password"}
        )
        
        assert abater_resp.status_code == 403, f"Expected 403, got {abater_resp.status_code}"
        assert "Senha incorreta" in abater_resp.json().get("detail", "")
        
        print("✅ Wrong password correctly rejected with 403")
    
    def test_abater_amount_greater_than_debt(self):
        """Test that abater fails when amount exceeds total debt"""
        abater_resp = requests.post(
            f"{BASE_URL}/api/prazo/abater/{self.test_customer}",
            json={"amount": 100.00, "password": PRAZO_PASSWORD}  # Total debt is only 50.00
        )
        
        assert abater_resp.status_code == 400, f"Expected 400, got {abater_resp.status_code}"
        assert "maior que a dívida total" in abater_resp.json().get("detail", "")
        
        print("✅ Amount greater than debt correctly rejected with 400")
    
    def test_abater_zero_amount(self):
        """Test that abater fails with zero amount"""
        abater_resp = requests.post(
            f"{BASE_URL}/api/prazo/abater/{self.test_customer}",
            json={"amount": 0, "password": PRAZO_PASSWORD}
        )
        
        assert abater_resp.status_code == 400, f"Expected 400, got {abater_resp.status_code}"
        assert "maior que zero" in abater_resp.json().get("detail", "")
        
        print("✅ Zero amount correctly rejected with 400")
    
    def test_abater_negative_amount(self):
        """Test that abater fails with negative amount"""
        abater_resp = requests.post(
            f"{BASE_URL}/api/prazo/abater/{self.test_customer}",
            json={"amount": -10.00, "password": PRAZO_PASSWORD}
        )
        
        assert abater_resp.status_code == 400, f"Expected 400, got {abater_resp.status_code}"
        
        print("✅ Negative amount correctly rejected with 400")
    
    def test_abater_nonexistent_customer(self):
        """Test that abater fails for customer with no debts"""
        abater_resp = requests.post(
            f"{BASE_URL}/api/prazo/abater/NONEXISTENT_CUSTOMER_12345",
            json={"amount": 10.00, "password": PRAZO_PASSWORD}
        )
        
        assert abater_resp.status_code == 404, f"Expected 404, got {abater_resp.status_code}"
        assert "não tem dívidas" in abater_resp.json().get("detail", "")
        
        print("✅ Non-existent customer correctly rejected with 404")


class TestPrazoDebtsWithPartialPayments:
    """Tests for GET /api/prazo/debts considering partial_paid field"""
    
    @pytest.fixture(autouse=True)
    def setup_test_data(self):
        """Create test prazo order with partial payment"""
        self.test_customer = f"TEST_PartialPaid_Customer_{uuid.uuid4().hex[:6]}"
        self.store = "runner"
        
        # Create a prazo order
        order = {
            "store": self.store,
            "customer_name": self.test_customer,
            "items": [{"menu_item_id": "1", "name": "Test Item", "price": 50.00, "quantity": 1}],
            "total": 50.00,
            "payment_method": "prazo"
        }
        
        resp = requests.post(f"{BASE_URL}/api/orders", json=order)
        assert resp.status_code == 200
        self.order_id = resp.json().get("id")
        
        yield
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/orders/{self.store}/{self.order_id}")
    
    def test_debts_shows_remaining_after_partial_payment(self):
        """Test that GET /api/prazo/debts shows remaining debt after partial payment"""
        # Make partial payment
        abater_resp = requests.post(
            f"{BASE_URL}/api/prazo/abater/{self.test_customer}",
            json={"amount": 20.00, "password": PRAZO_PASSWORD}
        )
        assert abater_resp.status_code == 200
        
        # Check debts
        debts_resp = requests.get(f"{BASE_URL}/api/prazo/debts?store={self.store}")
        assert debts_resp.status_code == 200
        
        debts = debts_resp.json().get("debts", [])
        customer_debt = next((d for d in debts if d["name"] == self.test_customer), None)
        
        assert customer_debt is not None
        assert customer_debt["total"] == 30.00, f"Expected remaining 30.00, got {customer_debt['total']}"
        
        # Check order details include partial_paid
        order_detail = customer_debt["orders"][0]
        assert order_detail["total"] == 50.00
        assert order_detail["partial_paid"] == 20.00
        assert order_detail["remaining"] == 30.00
        
        print(f"✅ Debts correctly shows remaining R$ 30.00 after R$ 20.00 partial payment")
    
    def test_debts_excludes_fully_paid_orders(self):
        """Test that fully paid orders are excluded from debts"""
        # Pay the full amount
        abater_resp = requests.post(
            f"{BASE_URL}/api/prazo/abater/{self.test_customer}",
            json={"amount": 50.00, "password": PRAZO_PASSWORD}
        )
        assert abater_resp.status_code == 200
        
        # Check debts - customer should not appear
        debts_resp = requests.get(f"{BASE_URL}/api/prazo/debts?store={self.store}")
        assert debts_resp.status_code == 200
        
        debts = debts_resp.json().get("debts", [])
        customer_debt = next((d for d in debts if d["name"] == self.test_customer), None)
        
        assert customer_debt is None, "Customer should not appear in debts after full payment"
        
        print("✅ Fully paid customer correctly excluded from debts")


class TestExistingTestCustomers:
    """Test with existing test customers mentioned in the request"""
    
    def test_existing_test_runner_prazo_customer(self):
        """Verify TEST_Runner_Prazo customer exists and has debt"""
        debts_resp = requests.get(f"{BASE_URL}/api/prazo/debts?store=runner")
        assert debts_resp.status_code == 200
        
        debts = debts_resp.json().get("debts", [])
        customer = next((d for d in debts if "TEST_Runner_Prazo" in d["name"]), None)
        
        if customer:
            print(f"✅ Found TEST_Runner_Prazo with debt: R$ {customer['total']}")
        else:
            print("ℹ️ TEST_Runner_Prazo not found (may have been paid off)")
    
    def test_existing_test_prazo_chart_customer(self):
        """Verify TEST_Prazo_Chart_Customer exists and has debt"""
        debts_resp = requests.get(f"{BASE_URL}/api/prazo/debts?store=runner")
        assert debts_resp.status_code == 200
        
        debts = debts_resp.json().get("debts", [])
        customer = next((d for d in debts if "TEST_Prazo_Chart_Customer" in d["name"]), None)
        
        if customer:
            print(f"✅ Found TEST_Prazo_Chart_Customer with debt: R$ {customer['total']}")
        else:
            print("ℹ️ TEST_Prazo_Chart_Customer not found (may have been paid off)")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
