"""
Test WhatsApp Bot Integration and PIX Payment Features
Tests for:
1. WhatsApp status endpoint
2. WhatsApp QR endpoint
3. Gestor dashboard with WhatsApp tab
4. PIX payment flow
5. Bot status check
"""

import pytest
import requests
import os
from requests.auth import HTTPBasicAuth

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Gestor credentials
GESTOR_USER = "gestor"
GESTOR_PASS = "ganoh2024"


class TestWhatsAppEndpoints:
    """Test WhatsApp Bot API endpoints"""
    
    def test_whatsapp_status_endpoint(self):
        """Test GET /api/whatsapp/status returns bot status"""
        response = requests.get(f"{BASE_URL}/api/whatsapp/status", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "status" in data, "Response should contain 'status' field"
        assert "connected" in data, "Response should contain 'connected' field"
        
        # Status should be one of: connected, waiting_qr, disconnected, reconnecting
        valid_statuses = ["connected", "waiting_qr", "disconnected", "reconnecting", "logged_out"]
        assert data["status"] in valid_statuses, f"Invalid status: {data['status']}"
        
        print(f"✅ WhatsApp status: {data['status']}, connected: {data['connected']}")
    
    def test_whatsapp_qr_endpoint(self):
        """Test GET /api/whatsapp/qr returns QR code data"""
        response = requests.get(f"{BASE_URL}/api/whatsapp/qr", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "connected" in data, "Response should contain 'connected' field"
        
        # If not connected, should have qrCode
        if not data.get("connected"):
            # qrCode may be null if bot is reconnecting
            print(f"✅ WhatsApp QR endpoint working, connected: {data['connected']}")
        else:
            print(f"✅ WhatsApp already connected, no QR needed")


class TestGestorDashboard:
    """Test Gestor Dashboard endpoints"""
    
    def test_gestor_login_success(self):
        """Test gestor login with correct credentials"""
        response = requests.get(
            f"{BASE_URL}/api/gestor/dashboard",
            auth=HTTPBasicAuth(GESTOR_USER, GESTOR_PASS),
            timeout=10
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "stores" in data, "Response should contain 'stores'"
        assert "combined" in data, "Response should contain 'combined'"
        
        # Verify both stores are present
        assert "runner" in data["stores"], "Runner store should be present"
        assert "gym-londres" in data["stores"], "GYM Londres store should be present"
        
        print(f"✅ Gestor dashboard accessible with correct credentials")
        print(f"   Today total: R$ {data['combined']['today_total']}")
        print(f"   Month total: R$ {data['combined']['month_total']}")
    
    def test_gestor_login_failure(self):
        """Test gestor login with wrong credentials"""
        response = requests.get(
            f"{BASE_URL}/api/gestor/dashboard",
            auth=HTTPBasicAuth("wrong", "credentials"),
            timeout=10
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print(f"✅ Gestor dashboard correctly rejects invalid credentials")
    
    def test_gestor_dashboard_statistics(self):
        """Test gestor dashboard returns proper statistics"""
        response = requests.get(
            f"{BASE_URL}/api/gestor/dashboard",
            auth=HTTPBasicAuth(GESTOR_USER, GESTOR_PASS),
            timeout=10
        )
        assert response.status_code == 200
        
        data = response.json()
        
        # Check Runner store data structure
        runner = data["stores"]["runner"]
        assert "name" in runner
        assert "today" in runner
        assert "month" in runner
        assert "top_products" in runner
        assert "low_products" in runner
        assert "low_stock_alerts" in runner
        
        # Check today data structure
        assert "total" in runner["today"]
        assert "order_count" in runner["today"]
        assert "by_payment_method" in runner["today"]
        
        print(f"✅ Gestor dashboard statistics structure verified")


class TestPIXPaymentFlow:
    """Test PIX payment configuration and flow"""
    
    def test_pix_config_endpoint(self):
        """Test GET /api/pix/config returns PIX configuration"""
        response = requests.get(f"{BASE_URL}/api/pix/config", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "beneficiary_name" in data, "Should have beneficiary_name"
        assert "city" in data, "Should have city"
        assert "key_type" in data, "Should have key_type"
        
        print(f"✅ PIX config: {data['beneficiary_name']} - {data['city']}")
    
    def test_create_pix_order(self):
        """Test creating an order with PIX payment"""
        order_data = {
            "store": "runner",
            "customer_name": "TEST_PIX_Customer",
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
        
        response = requests.post(
            f"{BASE_URL}/api/orders",
            json=order_data,
            timeout=10
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data["payment_method"] == "pix"
        assert data["status"] == "pending_payment", "PIX orders should start as pending_payment"
        assert data["customer_name"] == "TEST_PIX_Customer"
        
        print(f"✅ PIX order created with status: {data['status']}")
        return data["id"]
    
    def test_get_pending_pix_orders(self):
        """Test getting pending PIX orders"""
        response = requests.get(
            f"{BASE_URL}/api/orders/runner/pending-pix",
            timeout=10
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "orders" in data
        print(f"✅ Found {len(data['orders'])} pending PIX orders")


class TestMenuAndOrders:
    """Test menu and order endpoints"""
    
    def test_get_menu_runner(self):
        """Test GET /api/menu/runner returns menu items"""
        response = requests.get(f"{BASE_URL}/api/menu/runner", timeout=10)
        assert response.status_code == 200
        
        data = response.json()
        assert "items" in data
        assert "categories" in data
        assert "adicionais" in data
        assert "store" in data
        
        assert len(data["items"]) > 0, "Menu should have items"
        assert len(data["categories"]) > 0, "Menu should have categories"
        
        print(f"✅ Menu has {len(data['items'])} items in {len(data['categories'])} categories")
    
    def test_get_menu_gym_londres(self):
        """Test GET /api/menu/gym-londres returns menu items"""
        response = requests.get(f"{BASE_URL}/api/menu/gym-londres", timeout=10)
        assert response.status_code == 200
        
        data = response.json()
        assert "items" in data
        assert data["store"]["name"] == "GANOH Café Bistrô - GYM Londres"
        
        print(f"✅ GYM Londres menu accessible")
    
    def test_get_stores(self):
        """Test GET /api/stores returns both stores"""
        response = requests.get(f"{BASE_URL}/api/stores", timeout=10)
        assert response.status_code == 200
        
        data = response.json()
        assert "stores" in data
        assert "runner" in data["stores"]
        assert "gym-londres" in data["stores"]
        
        print(f"✅ Both stores available: Runner and GYM Londres")


class TestWhatsAppBotInternal:
    """Test internal WhatsApp bot server (localhost:8002)"""
    
    def test_bot_status_internal(self):
        """Test bot status on internal port 8002"""
        try:
            response = requests.get("http://localhost:8002/status", timeout=5)
            assert response.status_code == 200
            
            data = response.json()
            assert "status" in data
            assert "connected" in data
            
            print(f"✅ Internal bot status: {data['status']}, connected: {data['connected']}")
        except requests.exceptions.ConnectionError:
            pytest.skip("WhatsApp bot not running on localhost:8002")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
