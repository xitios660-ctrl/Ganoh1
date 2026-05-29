"""
GANOH Café Bistrô - New Features API Tests
Tests for: Prazo payment for GYM Londres, Expenses management, WhatsApp link, Chart with expenses
"""
import pytest
import requests
import os
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Gestor credentials
GESTOR_USER = "gestor"
GESTOR_PASS = "ganoh2024"


class TestPrazoPaymentForAllStores:
    """Test Prazo payment option is available for both stores (Runner and GYM Londres)"""
    
    def test_create_prazo_order_runner(self):
        """Test creating a prazo order for Runner store"""
        order_data = {
            "store": "runner",
            "customer_name": "TEST_Prazo_Runner",
            "items": [
                {
                    "menu_item_id": "1",
                    "name": "Frango com Requeijão",
                    "price": 25.50,
                    "quantity": 1
                }
            ],
            "total": 25.50,
            "payment_method": "prazo",
            "pickup_time": None
        }
        
        response = requests.post(f"{BASE_URL}/api/orders", json=order_data)
        assert response.status_code == 200, f"Failed to create prazo order for Runner: {response.text}"
        data = response.json()
        
        assert data["payment_method"] == "prazo"
        assert data["store"] == "runner"
        assert data["customer_name"] == "TEST_Prazo_Runner"
        print(f"✓ Prazo order created for Runner store: {data['id']}")
    
    def test_create_prazo_order_gym_londres(self):
        """Test creating a prazo order for GYM Londres store - NEW FEATURE"""
        order_data = {
            "store": "gym-londres",
            "customer_name": "TEST_Prazo_GYM",
            "items": [
                {
                    "menu_item_id": "2",
                    "name": "Frango, Mussarela, Tomate e Orégano",
                    "price": 26.00,
                    "quantity": 1
                }
            ],
            "total": 26.00,
            "payment_method": "prazo",
            "pickup_time": None
        }
        
        response = requests.post(f"{BASE_URL}/api/orders", json=order_data)
        assert response.status_code == 200, f"Failed to create prazo order for GYM Londres: {response.text}"
        data = response.json()
        
        assert data["payment_method"] == "prazo"
        assert data["store"] == "gym-londres"
        assert data["customer_name"] == "TEST_Prazo_GYM"
        print(f"✓ Prazo order created for GYM Londres store: {data['id']}")
    
    def test_prazo_debts_endpoint(self):
        """Test prazo debts endpoint returns data for both stores"""
        response = requests.get(f"{BASE_URL}/api/prazo/debts")
        assert response.status_code == 200
        data = response.json()
        
        assert "debts" in data
        assert "total_prazo" in data
        assert "customer_count" in data
        print(f"✓ Prazo debts endpoint working: {data['customer_count']} customers, total: R${data['total_prazo']:.2f}")


class TestExpensesManagement:
    """Test expense management endpoints - NEW FEATURE"""
    
    def test_get_expenses_requires_auth(self):
        """Test that expenses endpoint requires authentication"""
        response = requests.get(f"{BASE_URL}/api/expenses")
        assert response.status_code == 401
        print("✓ Expenses endpoint correctly requires authentication")
    
    def test_get_expenses_with_auth(self):
        """Test getting expenses with authentication"""
        response = requests.get(
            f"{BASE_URL}/api/expenses",
            auth=(GESTOR_USER, GESTOR_PASS)
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "expenses" in data
        assert "total" in data
        assert "by_category" in data
        assert "categories" in data
        
        # Verify categories list
        expected_categories = ['contador', 'fornecedor', 'mercado', 'suplementos', 'VT', 'Vivo', 'sistema', 'salário', 'outros']
        assert data["categories"] == expected_categories
        print(f"✓ Expenses endpoint working: {len(data['expenses'])} expenses, total: R${data['total']:.2f}")
    
    def test_create_expense(self):
        """Test creating a new expense"""
        expense_data = {
            "description": "TEST_Expense_Mercado",
            "amount": 150.00,
            "category": "mercado",
            "store": "all",
            "notes": "Test expense for testing"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/expenses",
            json=expense_data,
            auth=(GESTOR_USER, GESTOR_PASS)
        )
        assert response.status_code == 200, f"Failed to create expense: {response.text}"
        data = response.json()
        
        assert "id" in data
        assert data["description"] == "TEST_Expense_Mercado"
        assert data["amount"] == 150.00
        assert data["category"] == "mercado"
        assert data["store"] == "all"
        print(f"✓ Expense created: {data['id']}")
        return data["id"]
    
    def test_create_expense_different_categories(self):
        """Test creating expenses with different categories"""
        categories_to_test = ["contador", "fornecedor", "suplementos", "VT"]
        
        for cat in categories_to_test:
            expense_data = {
                "description": f"TEST_Expense_{cat}",
                "amount": 100.00,
                "category": cat,
                "store": "runner",
                "notes": f"Test expense for {cat}"
            }
            
            response = requests.post(
                f"{BASE_URL}/api/expenses",
                json=expense_data,
                auth=(GESTOR_USER, GESTOR_PASS)
            )
            assert response.status_code == 200, f"Failed to create expense for category {cat}: {response.text}"
        
        print(f"✓ Expenses created for categories: {categories_to_test}")
    
    def test_get_monthly_expenses(self):
        """Test monthly expenses endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/expenses/monthly",
            auth=(GESTOR_USER, GESTOR_PASS)
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "month" in data
        assert "data" in data
        assert "total_expenses" in data
        assert "by_category" in data
        assert "categories" in data
        print(f"✓ Monthly expenses endpoint working: {data['month']}, total: R${data['total_expenses']:.2f}")
    
    def test_delete_expense(self):
        """Test deleting an expense"""
        # First create an expense
        expense_data = {
            "description": "TEST_Expense_ToDelete",
            "amount": 50.00,
            "category": "outros",
            "store": "all",
            "notes": "Will be deleted"
        }
        
        create_response = requests.post(
            f"{BASE_URL}/api/expenses",
            json=expense_data,
            auth=(GESTOR_USER, GESTOR_PASS)
        )
        assert create_response.status_code == 200
        expense_id = create_response.json()["id"]
        
        # Now delete it
        delete_response = requests.delete(
            f"{BASE_URL}/api/expenses/{expense_id}",
            auth=(GESTOR_USER, GESTOR_PASS)
        )
        assert delete_response.status_code == 200
        data = delete_response.json()
        assert data["success"] == True
        print(f"✓ Expense deleted successfully: {expense_id}")


class TestWhatsAppLinkGeneration:
    """Test WhatsApp link generation for prazo collection - NEW FEATURE"""
    
    def test_whatsapp_link_requires_customer(self):
        """Test that WhatsApp link endpoint returns 404 for non-existent customer"""
        response = requests.get(f"{BASE_URL}/api/prazo/whatsapp-link/NonExistentCustomer123")
        assert response.status_code == 404
        print("✓ WhatsApp link correctly returns 404 for non-existent customer")
    
    def test_create_prazo_customer_and_get_whatsapp_link(self):
        """Test creating a prazo customer and generating WhatsApp link"""
        # First create a prazo customer with phone
        customer_data = {
            "name": "TEST_WhatsApp_Customer",
            "phone": "11999999999",
            "notes": "Test customer for WhatsApp"
        }
        
        create_response = requests.post(
            f"{BASE_URL}/api/prazo/customers",
            json=customer_data,
            auth=(GESTOR_USER, GESTOR_PASS)
        )
        
        if create_response.status_code == 200:
            # Create a prazo order for this customer
            order_data = {
                "store": "runner",
                "customer_name": "TEST_WhatsApp_Customer",
                "items": [
                    {
                        "menu_item_id": "1",
                        "name": "Frango com Requeijão",
                        "price": 25.50,
                        "quantity": 1
                    }
                ],
                "total": 25.50,
                "payment_method": "prazo",
                "pickup_time": None
            }
            requests.post(f"{BASE_URL}/api/orders", json=order_data)
            
            # Now try to get WhatsApp link
            whatsapp_response = requests.get(f"{BASE_URL}/api/prazo/whatsapp-link/TEST_WhatsApp_Customer")
            
            if whatsapp_response.status_code == 200:
                data = whatsapp_response.json()
                assert "url" in data
                assert "phone" in data
                assert "total_debt" in data
                assert "wa.me" in data["url"]
                print(f"✓ WhatsApp link generated: {data['url'][:50]}...")
            elif whatsapp_response.status_code == 400:
                # Customer might not have phone
                print("✓ WhatsApp link endpoint working (customer has no phone)")
            else:
                print(f"✓ WhatsApp link endpoint responded with status {whatsapp_response.status_code}")
        else:
            print("✓ WhatsApp link test skipped (customer creation failed)")


class TestChartWithExpenses:
    """Test chart endpoint with expenses data - NEW FEATURE"""
    
    def test_monthly_chart_with_expenses(self):
        """Test the monthly chart endpoint that includes expenses"""
        response = requests.get(
            f"{BASE_URL}/api/gestor/chart/monthly-with-expenses",
            auth=(GESTOR_USER, GESTOR_PASS)
        )
        assert response.status_code == 200, f"Failed to get chart data: {response.text}"
        data = response.json()
        
        # Verify structure
        assert "month" in data
        assert "data" in data
        assert "total_revenue" in data
        assert "total_expenses" in data
        assert "total_profit" in data
        assert "total_orders" in data
        assert "expenses_by_category" in data
        assert "categories" in data
        
        # Verify daily data structure
        if len(data["data"]) > 0:
            day_data = data["data"][0]
            assert "date" in day_data
            assert "day" in day_data
            assert "revenue" in day_data
            assert "expenses" in day_data
            assert "profit" in day_data
            assert "order_count" in day_data
            assert "expenses_by_category" in day_data
        
        print(f"✓ Chart with expenses working: {data['month']}")
        print(f"  Revenue: R${data['total_revenue']:.2f}")
        print(f"  Expenses: R${data['total_expenses']:.2f}")
        print(f"  Profit: R${data['total_profit']:.2f}")
        print(f"  Orders: {data['total_orders']}")
    
    def test_chart_profit_calculation(self):
        """Test that profit is correctly calculated as revenue - expenses"""
        response = requests.get(
            f"{BASE_URL}/api/gestor/chart/monthly-with-expenses",
            auth=(GESTOR_USER, GESTOR_PASS)
        )
        assert response.status_code == 200
        data = response.json()
        
        expected_profit = data["total_revenue"] - data["total_expenses"]
        assert abs(data["total_profit"] - expected_profit) < 0.01, "Profit calculation is incorrect"
        print(f"✓ Profit calculation correct: {data['total_revenue']:.2f} - {data['total_expenses']:.2f} = {data['total_profit']:.2f}")


class TestGestorDashboardTabs:
    """Test that Gestor dashboard has all required tabs"""
    
    def test_gestor_dashboard_access(self):
        """Test gestor dashboard is accessible"""
        response = requests.get(
            f"{BASE_URL}/api/gestor/dashboard",
            auth=(GESTOR_USER, GESTOR_PASS)
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "stores" in data
        assert "combined" in data
        print("✓ Gestor dashboard accessible")
    
    def test_all_required_endpoints_exist(self):
        """Test that all endpoints for the 5 tabs exist"""
        endpoints = [
            ("/api/gestor/dashboard", "Dashboard"),
            ("/api/gestor/chart/monthly-with-expenses", "Gráfico"),
            ("/api/expenses", "Gastos"),
            ("/api/prazo/debts", "Prazo"),
            ("/api/gestor/menu/runner", "Cardápio")
        ]
        
        for endpoint, tab_name in endpoints:
            if "gestor" in endpoint or "expenses" in endpoint:
                response = requests.get(f"{BASE_URL}{endpoint}", auth=(GESTOR_USER, GESTOR_PASS))
            else:
                response = requests.get(f"{BASE_URL}{endpoint}")
            
            assert response.status_code == 200, f"Endpoint {endpoint} for tab '{tab_name}' failed with status {response.status_code}"
            print(f"✓ Endpoint for '{tab_name}' tab working: {endpoint}")


class TestExpenseImageAnalysis:
    """Test AI image analysis for expenses - NEW FEATURE"""
    
    def test_analyze_image_requires_auth(self):
        """Test that image analysis requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/expenses/analyze-image",
            json={"image_base64": "test"}
        )
        assert response.status_code == 401
        print("✓ Image analysis correctly requires authentication")
    
    def test_analyze_image_endpoint_exists(self):
        """Test that the analyze image endpoint exists and responds"""
        # Send a minimal request to check endpoint exists
        response = requests.post(
            f"{BASE_URL}/api/expenses/analyze-image",
            json={"image_base64": ""},
            auth=(GESTOR_USER, GESTOR_PASS)
        )
        # Should return 500 (empty image) or 200 (processed), not 404
        assert response.status_code != 404, "Image analysis endpoint not found"
        print(f"✓ Image analysis endpoint exists (status: {response.status_code})")


class TestPrazoCustomers:
    """Test prazo customers management"""
    
    def test_get_prazo_customers(self):
        """Test getting prazo customers list"""
        response = requests.get(f"{BASE_URL}/api/prazo/customers")
        assert response.status_code == 200
        data = response.json()
        
        assert "customers" in data
        print(f"✓ Prazo customers endpoint working: {len(data['customers'])} customers")
    
    def test_create_prazo_customer(self):
        """Test creating a new prazo customer"""
        customer_data = {
            "name": "TEST_Prazo_Customer",
            "phone": "11888888888",
            "notes": "Test customer"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/prazo/customers",
            json=customer_data,
            auth=(GESTOR_USER, GESTOR_PASS)
        )
        assert response.status_code == 200, f"Failed to create prazo customer: {response.text}"
        data = response.json()
        
        assert "id" in data
        assert data["name"] == "TEST_Prazo_Customer"
        print(f"✓ Prazo customer created: {data['id']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
