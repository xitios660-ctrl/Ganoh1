"""
Test suite for new features:
1. Low stock system endpoints (GET /api/admin/low-stock-list, POST /api/admin/check-low-stock, POST /api/admin/send-low-stock-report)
2. Delete order permanently (DELETE /api/orders/{store}/{order_id})
3. Adicionais CRUD endpoints (GET/POST/PUT/DELETE /api/gestor/adicionais)
4. Milk options in menu response
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://prazo-accounting.preview.emergentagent.com').rstrip('/')

# Gestor credentials
GESTOR_USER = "gestor"
GESTOR_PASS = "ganoh2024"


class TestLowStockSystem:
    """Tests for low stock list and shopping list feature"""
    
    def test_get_low_stock_list(self):
        """GET /api/admin/low-stock-list - Should return current low stock items"""
        response = requests.get(f"{BASE_URL}/api/admin/low-stock-list")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "items" in data, "Response should have 'items' field"
        assert "count" in data, "Response should have 'count' field"
        assert isinstance(data["items"], list), "items should be a list"
        assert isinstance(data["count"], int), "count should be an integer"
        print(f"SUCCESS: Low stock list has {data['count']} items")
    
    def test_trigger_low_stock_check(self):
        """POST /api/admin/check-low-stock - Should trigger manual low stock check"""
        response = requests.post(f"{BASE_URL}/api/admin/check-low-stock")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "success" in data, "Response should have 'success' field"
        assert data["success"] == True, "success should be True"
        assert "items" in data, "Response should have 'items' field"
        assert "message" in data, "Response should have 'message' field"
        print(f"SUCCESS: Low stock check triggered - {data['message']}")
    
    def test_send_low_stock_report(self):
        """POST /api/admin/send-low-stock-report - Should trigger sending report to WhatsApp"""
        response = requests.post(f"{BASE_URL}/api/admin/send-low-stock-report")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "success" in data, "Response should have 'success' field"
        assert data["success"] == True, "success should be True"
        assert "message" in data, "Response should have 'message' field"
        print(f"SUCCESS: Low stock report endpoint works - {data['message']}")


class TestDeleteOrderPermanently:
    """Tests for permanent order deletion"""
    
    def test_create_and_delete_order(self):
        """Create an order and then delete it permanently"""
        # First create an order
        order_data = {
            "store": "runner",
            "customer_name": f"TEST_DELETE_{uuid.uuid4().hex[:8]}",
            "items": [
                {"menu_item_id": "48", "name": "Café Pequeno", "price": 4.50, "quantity": 1}
            ],
            "total": 4.50,
            "payment_method": "cash"
        }
        
        create_response = requests.post(f"{BASE_URL}/api/orders", json=order_data)
        assert create_response.status_code == 200, f"Failed to create order: {create_response.text}"
        
        created_order = create_response.json()
        order_id = created_order["id"]
        print(f"Created test order: {order_id}")
        
        # Now delete it permanently
        delete_response = requests.delete(f"{BASE_URL}/api/orders/runner/{order_id}")
        assert delete_response.status_code == 200, f"Expected 200, got {delete_response.status_code}: {delete_response.text}"
        
        delete_data = delete_response.json()
        assert delete_data["success"] == True, "Delete should return success=True"
        assert "permanentemente" in delete_data["message"].lower() or "apagado" in delete_data["message"].lower(), \
            f"Message should indicate permanent deletion: {delete_data['message']}"
        print(f"SUCCESS: Order {order_id} deleted permanently")
        
        # Verify order no longer exists
        get_response = requests.get(f"{BASE_URL}/api/orders/runner/{order_id}")
        assert get_response.status_code == 404, f"Order should not exist after deletion, got {get_response.status_code}"
        print("SUCCESS: Order confirmed deleted (404 on GET)")
    
    def test_delete_nonexistent_order(self):
        """DELETE /api/orders/{store}/{order_id} - Should return 404 for non-existent order"""
        fake_order_id = f"fake-{uuid.uuid4().hex}"
        response = requests.delete(f"{BASE_URL}/api/orders/runner/{fake_order_id}")
        assert response.status_code == 404, f"Expected 404 for non-existent order, got {response.status_code}"
        print("SUCCESS: 404 returned for non-existent order")


class TestAdicionaisCRUD:
    """Tests for Adicionais (extras) management in Gestor panel"""
    
    @pytest.fixture
    def auth(self):
        return (GESTOR_USER, GESTOR_PASS)
    
    def test_get_adicionais(self, auth):
        """GET /api/gestor/adicionais - Should return list of adicionais"""
        response = requests.get(f"{BASE_URL}/api/gestor/adicionais", auth=auth)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "adicionais" in data, "Response should have 'adicionais' field"
        assert isinstance(data["adicionais"], list), "adicionais should be a list"
        print(f"SUCCESS: Got {len(data['adicionais'])} adicionais")
        
        # Check structure of adicionais
        if len(data["adicionais"]) > 0:
            adicional = data["adicionais"][0]
            assert "id" in adicional, "Adicional should have 'id'"
            assert "name" in adicional, "Adicional should have 'name'"
            assert "price" in adicional, "Adicional should have 'price'"
            print(f"Sample adicional: {adicional['name']} - R${adicional['price']}")
    
    def test_create_adicional(self, auth):
        """POST /api/gestor/adicionais - Should create a new adicional"""
        test_name = f"TEST_Adicional_{uuid.uuid4().hex[:6]}"
        adicional_data = {
            "name": test_name,
            "price": 5.50
        }
        
        response = requests.post(f"{BASE_URL}/api/gestor/adicionais", json=adicional_data, auth=auth)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "success" in data or "id" in data, "Response should indicate success or return id"
        print(f"SUCCESS: Created adicional '{test_name}'")
        
        # Store the ID for cleanup
        if "id" in data:
            return data["id"]
        return None
    
    def test_create_update_delete_adicional(self, auth):
        """Full CRUD cycle for adicional"""
        # CREATE
        test_name = f"TEST_CRUD_{uuid.uuid4().hex[:6]}"
        create_data = {"name": test_name, "price": 3.00}
        
        create_response = requests.post(f"{BASE_URL}/api/gestor/adicionais", json=create_data, auth=auth)
        assert create_response.status_code == 200, f"Create failed: {create_response.text}"
        created = create_response.json()
        adicional_id = created.get("id")
        print(f"Created adicional: {adicional_id}")
        
        # Verify it exists in the list
        list_response = requests.get(f"{BASE_URL}/api/gestor/adicionais", auth=auth)
        adicionais = list_response.json().get("adicionais", [])
        found = any(a.get("name") == test_name for a in adicionais)
        assert found, f"Created adicional '{test_name}' not found in list"
        
        # Find the ID if not returned
        if not adicional_id:
            for a in adicionais:
                if a.get("name") == test_name:
                    adicional_id = a.get("id")
                    break
        
        # UPDATE
        update_data = {"name": f"{test_name}_UPDATED", "price": 4.50}
        update_response = requests.put(f"{BASE_URL}/api/gestor/adicionais/{adicional_id}", json=update_data, auth=auth)
        assert update_response.status_code == 200, f"Update failed: {update_response.text}"
        print(f"Updated adicional: {adicional_id}")
        
        # DELETE
        delete_response = requests.delete(f"{BASE_URL}/api/gestor/adicionais/{adicional_id}", auth=auth)
        assert delete_response.status_code == 200, f"Delete failed: {delete_response.text}"
        print(f"Deleted adicional: {adicional_id}")
        
        # Verify deletion
        list_response2 = requests.get(f"{BASE_URL}/api/gestor/adicionais", auth=auth)
        adicionais2 = list_response2.json().get("adicionais", [])
        found_after = any(a.get("id") == adicional_id for a in adicionais2)
        assert not found_after, "Adicional should not exist after deletion"
        print("SUCCESS: Full CRUD cycle completed for adicional")


class TestMilkOptionsInMenu:
    """Tests for milk options feature in menu"""
    
    def test_menu_includes_milk_options(self):
        """GET /api/menu/{store} - Should include milk_options in response"""
        response = requests.get(f"{BASE_URL}/api/menu/runner")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "milk_options" in data, "Menu response should include 'milk_options'"
        
        milk_options = data["milk_options"]
        assert isinstance(milk_options, list), "milk_options should be a list"
        assert len(milk_options) > 0, "milk_options should not be empty"
        
        # Check structure
        for option in milk_options:
            assert "id" in option, "Milk option should have 'id'"
            assert "name" in option, "Milk option should have 'name'"
            assert "price" in option, "Milk option should have 'price'"
        
        print(f"SUCCESS: Menu includes {len(milk_options)} milk options:")
        for opt in milk_options:
            print(f"  - {opt['name']} (R${opt['price']})")
    
    def test_milk_options_are_free(self):
        """Milk options should have price = 0"""
        response = requests.get(f"{BASE_URL}/api/menu/runner")
        data = response.json()
        
        milk_options = data.get("milk_options", [])
        for option in milk_options:
            assert option["price"] == 0, f"Milk option '{option['name']}' should be free (price=0)"
        
        print("SUCCESS: All milk options are free (price=0)")
    
    def test_menu_includes_adicionais(self):
        """GET /api/menu/{store} - Should include adicionais in response"""
        response = requests.get(f"{BASE_URL}/api/menu/runner")
        assert response.status_code == 200
        
        data = response.json()
        assert "adicionais" in data, "Menu response should include 'adicionais'"
        
        adicionais = data["adicionais"]
        assert isinstance(adicionais, list), "adicionais should be a list"
        print(f"SUCCESS: Menu includes {len(adicionais)} adicionais")


class TestGestorDashboard:
    """Tests for Gestor dashboard and charts"""
    
    @pytest.fixture
    def auth(self):
        return (GESTOR_USER, GESTOR_PASS)
    
    def test_gestor_dashboard_loads(self, auth):
        """GET /api/gestor/dashboard - Should return dashboard data"""
        response = requests.get(f"{BASE_URL}/api/gestor/dashboard", auth=auth)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Check for expected fields - data is nested under 'combined' and 'stores'
        assert "combined" in data or "stores" in data, "Dashboard should have 'combined' or 'stores' field"
        
        # Get combined totals
        combined = data.get("combined", {})
        today_total = combined.get("today_total", 0)
        month_total = combined.get("month_total", 0)
        
        print(f"SUCCESS: Dashboard loaded - Today: R${today_total:.2f}, Month: R${month_total:.2f}")
    
    def test_gestor_chart_monthly(self, auth):
        """GET /api/gestor/chart/monthly - Should return monthly chart data"""
        import datetime
        now = datetime.datetime.now()
        
        response = requests.get(
            f"{BASE_URL}/api/gestor/chart/monthly",
            params={"month": now.month, "year": now.year},
            auth=auth
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "data" in data or "labels" in data or "total" in data, "Chart response should have data"
        print(f"SUCCESS: Monthly chart data retrieved")
    
    def test_gestor_chart_daily(self, auth):
        """GET /api/gestor/chart/daily - Should return daily chart data"""
        import datetime
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        
        response = requests.get(
            f"{BASE_URL}/api/gestor/chart/daily",
            params={"date": today},
            auth=auth
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("SUCCESS: Daily chart data retrieved")


class TestKitchenDeleteOrder:
    """Tests for kitchen page delete order functionality"""
    
    def test_kitchen_can_delete_order(self):
        """Kitchen should be able to delete orders permanently"""
        # Create an order
        order_data = {
            "store": "gym-londres",
            "customer_name": f"TEST_KITCHEN_{uuid.uuid4().hex[:8]}",
            "items": [
                {"menu_item_id": "48", "name": "Café Pequeno", "price": 4.50, "quantity": 1}
            ],
            "total": 4.50,
            "payment_method": "debit"
        }
        
        create_response = requests.post(f"{BASE_URL}/api/orders", json=order_data)
        assert create_response.status_code == 200
        order_id = create_response.json()["id"]
        
        # Delete via kitchen endpoint
        delete_response = requests.delete(f"{BASE_URL}/api/orders/gym-londres/{order_id}")
        assert delete_response.status_code == 200
        
        # Verify not in orders list
        orders_response = requests.get(f"{BASE_URL}/api/orders/gym-londres")
        orders = orders_response.json().get("orders", [])
        found = any(o.get("id") == order_id for o in orders)
        assert not found, "Deleted order should not appear in orders list"
        
        # Verify not in history
        history_response = requests.get(f"{BASE_URL}/api/orders/gym-londres/history")
        history = history_response.json().get("orders", [])
        found_history = any(o.get("id") == order_id for o in history)
        assert not found_history, "Deleted order should not appear in history"
        
        print("SUCCESS: Kitchen delete removes order from both orders and history")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
