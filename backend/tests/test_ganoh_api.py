"""
GANOH Café Bistrô API Tests
Tests for: Menu, Orders, Kitchen, Cash Register (with shifts), Gestor Dashboard
"""
import pytest
import requests
import os
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Gestor credentials
GESTOR_USER = "gestor"
GESTOR_PASS = "ganoh2024"


class TestHealthAndBasicEndpoints:
    """Basic API health and root endpoint tests"""
    
    def test_api_root(self):
        """Test API root endpoint"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "GANOH" in data["message"]
        print(f"✓ API root working: {data['message']}")
    
    def test_get_stores(self):
        """Test stores endpoint"""
        response = requests.get(f"{BASE_URL}/api/stores")
        assert response.status_code == 200
        data = response.json()
        assert "stores" in data
        assert "runner" in data["stores"]
        assert "gym-londres" in data["stores"]
        print(f"✓ Stores endpoint working: {list(data['stores'].keys())}")


class TestMenuEndpoints:
    """Menu API tests for both stores"""
    
    def test_get_menu_runner(self):
        """Test menu for Runner store"""
        response = requests.get(f"{BASE_URL}/api/menu/runner")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "categories" in data
        assert "adicionais" in data
        assert len(data["items"]) > 0
        assert len(data["categories"]) > 0
        print(f"✓ Runner menu: {len(data['items'])} items, {len(data['categories'])} categories")
    
    def test_get_menu_gym_londres(self):
        """Test menu for GYM Londres store"""
        response = requests.get(f"{BASE_URL}/api/menu/gym-londres")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "categories" in data
        print(f"✓ GYM Londres menu: {len(data['items'])} items")
    
    def test_get_categories(self):
        """Test categories endpoint"""
        response = requests.get(f"{BASE_URL}/api/categories")
        assert response.status_code == 200
        data = response.json()
        assert "categories" in data
        assert len(data["categories"]) > 0
        print(f"✓ Categories: {data['categories'][:3]}...")


class TestCashRegisterWithShifts:
    """Cash register tests - specifically testing shifts feature (P0)"""
    
    def test_cash_today_runner_has_shifts(self):
        """Test that /cash/runner/today returns shifts data (morning/afternoon)"""
        response = requests.get(f"{BASE_URL}/api/cash/runner/today")
        assert response.status_code == 200
        data = response.json()
        
        # Verify basic structure
        assert "total" in data
        assert "by_payment_method" in data
        assert "order_count" in data
        
        # CRITICAL: Verify shifts structure exists
        assert "shifts" in data, "shifts field missing from cash response"
        shifts = data["shifts"]
        
        # Verify morning shift
        assert "morning" in shifts, "morning shift missing"
        morning = shifts["morning"]
        assert "label" in morning
        assert "total" in morning
        assert "count" in morning
        assert "by_payment" in morning
        assert morning["label"] == "06:00 - 14:00"
        
        # Verify afternoon shift
        assert "afternoon" in shifts, "afternoon shift missing"
        afternoon = shifts["afternoon"]
        assert "label" in afternoon
        assert "total" in afternoon
        assert "count" in afternoon
        assert "by_payment" in afternoon
        assert afternoon["label"] == "14:00 - 22:00"
        
        print(f"✓ Cash with shifts - Morning: R${morning['total']:.2f} ({morning['count']} orders), Afternoon: R${afternoon['total']:.2f} ({afternoon['count']} orders)")
    
    def test_cash_today_gym_londres_has_shifts(self):
        """Test that /cash/gym-londres/today returns shifts data"""
        response = requests.get(f"{BASE_URL}/api/cash/gym-londres/today")
        assert response.status_code == 200
        data = response.json()
        
        assert "shifts" in data
        assert "morning" in data["shifts"]
        assert "afternoon" in data["shifts"]
        print(f"✓ GYM Londres cash with shifts working")
    
    def test_shifts_payment_breakdown(self):
        """Test that shifts have payment method breakdown"""
        response = requests.get(f"{BASE_URL}/api/cash/runner/today")
        assert response.status_code == 200
        data = response.json()
        
        for shift_name in ["morning", "afternoon"]:
            shift = data["shifts"][shift_name]
            assert "by_payment" in shift
            by_payment = shift["by_payment"]
            assert "pix" in by_payment
            assert "debit" in by_payment
            assert "credit" in by_payment
            assert "cash" in by_payment
        
        print(f"✓ Shifts have payment breakdown (pix, debit, credit, cash)")


class TestKitchenEndpoints:
    """Kitchen API tests"""
    
    def test_kitchen_stats_runner(self):
        """Test kitchen stats for Runner"""
        response = requests.get(f"{BASE_URL}/api/kitchen/runner/stats")
        assert response.status_code == 200
        data = response.json()
        assert "pending" in data
        assert "preparing" in data
        assert "ready" in data
        print(f"✓ Kitchen stats: pending={data['pending']}, preparing={data['preparing']}, ready={data['ready']}")
    
    def test_get_orders_runner(self):
        """Test orders endpoint for Runner"""
        response = requests.get(f"{BASE_URL}/api/orders/runner")
        assert response.status_code == 200
        data = response.json()
        assert "orders" in data
        print(f"✓ Orders endpoint: {len(data['orders'])} orders")


class TestStockEndpoints:
    """Stock management tests"""
    
    def test_get_stock_runner(self):
        """Test stock endpoint for Runner"""
        response = requests.get(f"{BASE_URL}/api/stock/runner")
        assert response.status_code == 200
        data = response.json()
        assert "stock" in data
        print(f"✓ Stock endpoint: {len(data['stock'])} items")
    
    def test_initialize_stock(self):
        """Test stock initialization"""
        response = requests.post(f"{BASE_URL}/api/stock/runner/initialize")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        print(f"✓ Stock initialization: {data['message']}")


class TestGestorAuthentication:
    """Gestor authentication tests (P0)"""
    
    def test_gestor_login_success(self):
        """Test gestor login with correct credentials"""
        response = requests.get(
            f"{BASE_URL}/api/gestor/dashboard",
            auth=(GESTOR_USER, GESTOR_PASS)
        )
        assert response.status_code == 200
        data = response.json()
        assert "stores" in data
        assert "combined" in data
        print(f"✓ Gestor login successful with {GESTOR_USER}/{GESTOR_PASS}")
    
    def test_gestor_login_failure(self):
        """Test gestor login with wrong credentials"""
        response = requests.get(
            f"{BASE_URL}/api/gestor/dashboard",
            auth=("wrong", "credentials")
        )
        assert response.status_code == 401
        print(f"✓ Gestor login correctly rejects invalid credentials")


class TestGestorDashboard:
    """Gestor dashboard tests - products clickable feature (P0)"""
    
    def test_dashboard_has_top_products(self):
        """Test that dashboard returns top_products for each store"""
        response = requests.get(
            f"{BASE_URL}/api/gestor/dashboard",
            auth=(GESTOR_USER, GESTOR_PASS)
        )
        assert response.status_code == 200
        data = response.json()
        
        for store_key in ["runner", "gym-londres"]:
            store = data["stores"][store_key]
            assert "top_products" in store, f"top_products missing for {store_key}"
            # Verify structure if products exist
            if len(store["top_products"]) > 0:
                product = store["top_products"][0]
                assert "name" in product
                assert "count" in product
                assert "revenue" in product
        
        print(f"✓ Dashboard has top_products for both stores")
    
    def test_dashboard_has_low_products(self):
        """Test that dashboard returns low_products for each store"""
        response = requests.get(
            f"{BASE_URL}/api/gestor/dashboard",
            auth=(GESTOR_USER, GESTOR_PASS)
        )
        assert response.status_code == 200
        data = response.json()
        
        for store_key in ["runner", "gym-londres"]:
            store = data["stores"][store_key]
            assert "low_products" in store, f"low_products missing for {store_key}"
        
        print(f"✓ Dashboard has low_products for both stores")
    
    def test_dashboard_combined_totals(self):
        """Test combined totals in dashboard"""
        response = requests.get(
            f"{BASE_URL}/api/gestor/dashboard",
            auth=(GESTOR_USER, GESTOR_PASS)
        )
        assert response.status_code == 200
        data = response.json()
        
        combined = data["combined"]
        assert "today_total" in combined
        assert "month_total" in combined
        assert "today_orders" in combined
        assert "month_orders" in combined
        
        print(f"✓ Dashboard combined: Today R${combined['today_total']:.2f}, Month R${combined['month_total']:.2f}")


class TestOrderCreation:
    """Order creation and flow tests"""
    
    def test_create_order_with_payment_method(self):
        """Test creating an order with payment method"""
        order_data = {
            "store": "runner",
            "customer_name": "TEST_User",
            "items": [
                {
                    "menu_item_id": "1",
                    "name": "Frango com Requeijão",
                    "price": 25.50,
                    "quantity": 1
                }
            ],
            "total": 25.50,
            "payment_method": "pix",
            "pickup_time": None
        }
        
        response = requests.post(f"{BASE_URL}/api/orders", json=order_data)
        assert response.status_code == 200
        data = response.json()
        
        assert "id" in data
        assert data["payment_method"] == "pix"
        assert data["customer_name"] == "TEST_User"
        
        print(f"✓ Order created with payment method: {data['id']}")
        return data["id"]
    
    def test_create_order_with_pickup_time(self):
        """Test creating an order with scheduled pickup time"""
        order_data = {
            "store": "runner",
            "customer_name": "TEST_Scheduled",
            "items": [
                {
                    "menu_item_id": "2",
                    "name": "Frango, Mussarela, Tomate e Orégano",
                    "price": 26.00,
                    "quantity": 1
                }
            ],
            "total": 26.00,
            "payment_method": "credit",
            "pickup_time": "15:30"
        }
        
        response = requests.post(f"{BASE_URL}/api/orders", json=order_data)
        assert response.status_code == 200
        data = response.json()
        
        assert data["pickup_time"] == "15:30"
        print(f"✓ Order created with pickup time: {data['pickup_time']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
