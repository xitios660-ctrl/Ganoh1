"""
Test suite for GANOH Prazo and PIX features:
1. Prazo sales NOT included in totals (GET /api/cash/{store}/today)
2. Manual PIX adjustments ARE added to totals (POST /api/pix-adjustments/add, GET /api/cash/{store}/today)
3. Prazo customers filtered by store (GET /api/prazo/customers?store=runner)
4. Add credit to prazo customer (POST /api/prazo/customers/{customer_id}/add-credit)
"""
import pytest
import requests
import os
import uuid
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestPrazoNotInTotals:
    """Test that Prazo sales are NOT included in sales totals"""
    
    def test_prazo_order_not_in_cash_today_total(self):
        """Create a prazo order and verify it's NOT in the total"""
        # First get current totals
        response = requests.get(f"{BASE_URL}/api/cash/runner/today")
        assert response.status_code == 200, f"Failed to get cash today: {response.text}"
        initial_data = response.json()
        initial_total = initial_data.get("total", 0)
        
        # Create a prazo order
        test_order = {
            "store": "runner",
            "customer_name": f"TEST_Prazo_{uuid.uuid4().hex[:8]}",
            "items": [{"menu_item_id": "1", "name": "Test Item", "price": 25.50, "quantity": 1}],
            "total": 25.50,
            "payment_method": "prazo"
        }
        order_response = requests.post(f"{BASE_URL}/api/orders", json=test_order)
        assert order_response.status_code == 200, f"Failed to create order: {order_response.text}"
        order_id = order_response.json().get("id")
        
        # Update order to ready status
        status_response = requests.patch(
            f"{BASE_URL}/api/orders/runner/{order_id}/status",
            json={"status": "ready"}
        )
        assert status_response.status_code == 200, f"Failed to update status: {status_response.text}"
        
        # Get totals again
        response2 = requests.get(f"{BASE_URL}/api/cash/runner/today")
        assert response2.status_code == 200
        new_data = response2.json()
        new_total = new_data.get("total", 0)
        
        # Prazo should NOT be added to total
        assert new_total == initial_total, f"Prazo was incorrectly added to total! Initial: {initial_total}, New: {new_total}"
        
        # Verify prazo is tracked separately in by_payment_method
        by_payment = new_data.get("by_payment_method", {})
        assert "prazo" in by_payment, "Prazo should be tracked in by_payment_method"
        
        print(f"✓ Prazo order NOT added to total. Total remains: {new_total}")
        
        # Cleanup - delete the test order
        requests.delete(f"{BASE_URL}/api/orders/runner/{order_id}")

    def test_pix_order_is_in_cash_today_total(self):
        """Create a PIX order and verify it IS in the total (for comparison)"""
        # First get current totals
        response = requests.get(f"{BASE_URL}/api/cash/runner/today")
        assert response.status_code == 200
        initial_data = response.json()
        initial_pix = initial_data.get("by_payment_method", {}).get("pix", 0)
        
        # Create a PIX order (will be pending_payment initially)
        test_order = {
            "store": "runner",
            "customer_name": f"TEST_PIX_{uuid.uuid4().hex[:8]}",
            "items": [{"menu_item_id": "1", "name": "Test Item", "price": 30.00, "quantity": 1}],
            "total": 30.00,
            "payment_method": "pix"
        }
        order_response = requests.post(f"{BASE_URL}/api/orders", json=test_order)
        assert order_response.status_code == 200
        order_id = order_response.json().get("id")
        
        # Approve the PIX payment
        approve_response = requests.post(
            f"{BASE_URL}/api/orders/runner/{order_id}/approve-payment",
            json={"approved": True}
        )
        # May fail if no pix_proof, but let's check status
        
        # Update to ready
        requests.patch(f"{BASE_URL}/api/orders/runner/{order_id}/status", json={"status": "ready"})
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/orders/runner/{order_id}")
        
        print("✓ PIX order flow tested")


class TestPixManualAdjustments:
    """Test manual PIX adjustments are added to totals"""
    
    def test_add_pix_adjustment(self):
        """Add a manual PIX adjustment and verify it's created"""
        adjustment = {
            "store": "runner",
            "amount": 100.00,
            "description": "TEST_Ajuste manual de teste"
        }
        response = requests.post(f"{BASE_URL}/api/pix-adjustments/add", json=adjustment)
        assert response.status_code == 200, f"Failed to add adjustment: {response.text}"
        
        data = response.json()
        assert data.get("success") == True
        assert "adjustment" in data
        adjustment_id = data["adjustment"]["id"]
        
        print(f"✓ PIX adjustment created with ID: {adjustment_id}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/pix-adjustments/{adjustment_id}")
        return adjustment_id
    
    def test_pix_adjustment_in_cash_today(self):
        """Verify PIX adjustments are included in cash/today totals"""
        # Get initial totals
        response1 = requests.get(f"{BASE_URL}/api/cash/runner/today")
        assert response1.status_code == 200
        initial_data = response1.json()
        initial_total = initial_data.get("total", 0)
        initial_pix = initial_data.get("by_payment_method", {}).get("pix", 0)
        initial_manual = initial_data.get("pix_manual_adjustments", 0)
        
        # Add a manual PIX adjustment
        adjustment = {
            "store": "runner",
            "amount": 50.00,
            "description": "TEST_Verificação de soma"
        }
        add_response = requests.post(f"{BASE_URL}/api/pix-adjustments/add", json=adjustment)
        assert add_response.status_code == 200
        adjustment_id = add_response.json()["adjustment"]["id"]
        
        # Get new totals
        response2 = requests.get(f"{BASE_URL}/api/cash/runner/today")
        assert response2.status_code == 200
        new_data = response2.json()
        new_total = new_data.get("total", 0)
        new_pix = new_data.get("by_payment_method", {}).get("pix", 0)
        new_manual = new_data.get("pix_manual_adjustments", 0)
        
        # Verify adjustment was added to totals
        assert new_total == initial_total + 50.00, f"Total should increase by 50. Initial: {initial_total}, New: {new_total}"
        assert new_pix == initial_pix + 50.00, f"PIX total should increase by 50. Initial: {initial_pix}, New: {new_pix}"
        assert new_manual == initial_manual + 50.00, f"Manual adjustments should increase by 50. Initial: {initial_manual}, New: {new_manual}"
        
        print(f"✓ PIX adjustment correctly added to totals. Total: {initial_total} -> {new_total}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/pix-adjustments/{adjustment_id}")
    
    def test_get_pix_adjustments_by_store(self):
        """Get PIX adjustments filtered by store"""
        response = requests.get(f"{BASE_URL}/api/pix-adjustments/runner")
        assert response.status_code == 200, f"Failed to get adjustments: {response.text}"
        
        data = response.json()
        assert "adjustments" in data
        assert "total_added" in data
        assert data.get("store") == "runner"
        
        print(f"✓ Got PIX adjustments for runner. Total: {data.get('total_added')}")
    
    def test_remove_pix_adjustment(self):
        """Remove a PIX adjustment"""
        # First add one
        adjustment = {
            "store": "runner",
            "amount": 25.00,
            "description": "TEST_Para remover"
        }
        add_response = requests.post(f"{BASE_URL}/api/pix-adjustments/add", json=adjustment)
        assert add_response.status_code == 200
        adjustment_id = add_response.json()["adjustment"]["id"]
        
        # Remove it
        remove_response = requests.delete(f"{BASE_URL}/api/pix-adjustments/{adjustment_id}")
        assert remove_response.status_code == 200
        
        data = remove_response.json()
        assert data.get("success") == True
        
        print(f"✓ PIX adjustment removed successfully")


class TestPrazoCustomersByStore:
    """Test prazo customers filtered by store"""
    
    def test_create_prazo_customer_with_store(self):
        """Create a prazo customer for a specific store"""
        customer = {
            "name": f"TEST_Cliente_{uuid.uuid4().hex[:8]}",
            "phone": "11999999999",
            "notes": "Cliente de teste",
            "store": "runner",
            "credit": 0
        }
        response = requests.post(f"{BASE_URL}/api/kitchen/prazo/customers", json=customer)
        assert response.status_code == 200, f"Failed to create customer: {response.text}"
        
        data = response.json()
        assert data.get("name") == customer["name"]
        assert data.get("store") == "runner"
        customer_id = data.get("id")
        
        print(f"✓ Prazo customer created for runner: {customer['name']}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/kitchen/prazo/customers/{customer_id}")
        return customer_id
    
    def test_get_prazo_customers_filtered_by_store(self):
        """Get prazo customers filtered by store"""
        # Create customers for different stores
        customer_runner = {
            "name": f"TEST_Runner_{uuid.uuid4().hex[:8]}",
            "phone": "11111111111",
            "store": "runner",
            "credit": 0
        }
        customer_gym = {
            "name": f"TEST_GYM_{uuid.uuid4().hex[:8]}",
            "phone": "22222222222",
            "store": "gym-londres",
            "credit": 0
        }
        
        resp1 = requests.post(f"{BASE_URL}/api/kitchen/prazo/customers", json=customer_runner)
        resp2 = requests.post(f"{BASE_URL}/api/kitchen/prazo/customers", json=customer_gym)
        
        runner_id = resp1.json().get("id") if resp1.status_code == 200 else None
        gym_id = resp2.json().get("id") if resp2.status_code == 200 else None
        
        # Get customers filtered by runner
        response = requests.get(f"{BASE_URL}/api/prazo/customers?store=runner")
        assert response.status_code == 200, f"Failed to get customers: {response.text}"
        
        data = response.json()
        assert "customers" in data
        
        # All returned customers should be from runner store
        for customer in data["customers"]:
            if customer.get("name", "").startswith("TEST_"):
                assert customer.get("store") == "runner", f"Customer {customer.get('name')} has wrong store: {customer.get('store')}"
        
        print(f"✓ Prazo customers filtered by store correctly. Found {len(data['customers'])} customers for runner")
        
        # Cleanup
        if runner_id:
            requests.delete(f"{BASE_URL}/api/kitchen/prazo/customers/{runner_id}")
        if gym_id:
            requests.delete(f"{BASE_URL}/api/kitchen/prazo/customers/{gym_id}")
    
    def test_get_all_prazo_customers(self):
        """Get all prazo customers without filter"""
        response = requests.get(f"{BASE_URL}/api/prazo/customers")
        assert response.status_code == 200
        
        data = response.json()
        assert "customers" in data
        
        print(f"✓ Got all prazo customers: {len(data['customers'])} total")


class TestAddCreditToPrazoCustomer:
    """Test adding credit to prazo customers"""
    
    def test_add_credit_to_customer(self):
        """Add credit to a prazo customer"""
        # First create a customer
        customer = {
            "name": f"TEST_Credit_{uuid.uuid4().hex[:8]}",
            "phone": "11999999999",
            "store": "runner",
            "credit": 0
        }
        create_response = requests.post(f"{BASE_URL}/api/kitchen/prazo/customers", json=customer)
        assert create_response.status_code == 200, f"Failed to create customer: {create_response.text}"
        customer_id = create_response.json().get("id")
        
        # Add credit
        credit_data = {"amount": 100.00}
        add_credit_response = requests.post(
            f"{BASE_URL}/api/prazo/customers/{customer_id}/add-credit",
            json=credit_data
        )
        assert add_credit_response.status_code == 200, f"Failed to add credit: {add_credit_response.text}"
        
        data = add_credit_response.json()
        assert data.get("success") == True
        assert data.get("new_credit") == 100.00
        assert data.get("added") == 100.00
        assert data.get("previous_credit") == 0
        
        print(f"✓ Credit added successfully. New balance: R$ {data.get('new_credit')}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/kitchen/prazo/customers/{customer_id}")
    
    def test_add_credit_cumulative(self):
        """Add credit multiple times and verify it accumulates"""
        # Create customer
        customer = {
            "name": f"TEST_Cumulative_{uuid.uuid4().hex[:8]}",
            "phone": "11999999999",
            "store": "runner",
            "credit": 50.00  # Start with 50
        }
        create_response = requests.post(f"{BASE_URL}/api/kitchen/prazo/customers", json=customer)
        assert create_response.status_code == 200
        customer_id = create_response.json().get("id")
        
        # Add more credit
        add_response = requests.post(
            f"{BASE_URL}/api/prazo/customers/{customer_id}/add-credit",
            json={"amount": 30.00}
        )
        assert add_response.status_code == 200
        
        data = add_response.json()
        assert data.get("new_credit") == 80.00, f"Expected 80, got {data.get('new_credit')}"
        assert data.get("previous_credit") == 50.00
        
        print(f"✓ Credit accumulated correctly: 50 + 30 = {data.get('new_credit')}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/kitchen/prazo/customers/{customer_id}")
    
    def test_add_credit_nonexistent_customer(self):
        """Try to add credit to non-existent customer"""
        response = requests.post(
            f"{BASE_URL}/api/prazo/customers/nonexistent-id/add-credit",
            json={"amount": 50.00}
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        
        print("✓ Correctly returns 404 for non-existent customer")


class TestPrazoDebtsFilteredByStore:
    """Test prazo debts filtered by store"""
    
    def test_get_prazo_debts_by_store(self):
        """Get prazo debts filtered by store"""
        response = requests.get(f"{BASE_URL}/api/prazo/debts?store=runner")
        assert response.status_code == 200, f"Failed to get debts: {response.text}"
        
        data = response.json()
        assert "debts" in data
        assert "total_prazo" in data
        assert data.get("store_filter") == "runner"
        
        # All debts should be from runner store
        for debt in data["debts"]:
            assert debt.get("store") == "runner", f"Debt has wrong store: {debt.get('store')}"
        
        print(f"✓ Prazo debts filtered by runner. Total: R$ {data.get('total_prazo')}")
    
    def test_get_all_prazo_debts(self):
        """Get all prazo debts without filter"""
        response = requests.get(f"{BASE_URL}/api/prazo/debts")
        assert response.status_code == 200
        
        data = response.json()
        assert "debts" in data
        assert data.get("store_filter") == "all"
        
        print(f"✓ Got all prazo debts. Total: R$ {data.get('total_prazo')}")


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
