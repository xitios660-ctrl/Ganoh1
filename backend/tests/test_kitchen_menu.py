"""
Test cases for Kitchen Menu API endpoints
Tests: POST /api/kitchen/menu, GET /api/kitchen/menu/{store}
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://prazo-accounting.preview.emergentagent.com').rstrip('/')


class TestKitchenMenuAPI:
    """Test Kitchen Menu CRUD operations"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test data"""
        self.test_item_id = None
        yield
        # Cleanup: Delete test items created during tests
        if self.test_item_id:
            try:
                requests.delete(f"{BASE_URL}/api/kitchen/menu/{self.test_item_id}")
            except:
                pass
    
    def test_get_menu_runner_store(self):
        """Test GET /api/kitchen/menu/runner returns items for Runner store"""
        response = requests.get(f"{BASE_URL}/api/kitchen/menu/runner")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "items" in data, "Response should contain 'items' key"
        assert isinstance(data["items"], list), "Items should be a list"
        
        # Verify all items have store=runner
        for item in data["items"]:
            assert item.get("store") == "runner", f"Item {item.get('name')} has wrong store: {item.get('store')}"
        
        print(f"SUCCESS: Runner store has {len(data['items'])} menu items")
    
    def test_get_menu_gym_londres_store(self):
        """Test GET /api/kitchen/menu/gym-londres returns items for GYM Londres store"""
        response = requests.get(f"{BASE_URL}/api/kitchen/menu/gym-londres")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "items" in data, "Response should contain 'items' key"
        assert isinstance(data["items"], list), "Items should be a list"
        
        # Verify all items have store=gym-londres
        for item in data["items"]:
            assert item.get("store") == "gym-londres", f"Item {item.get('name')} has wrong store: {item.get('store')}"
        
        print(f"SUCCESS: GYM Londres store has {len(data['items'])} menu items")
    
    def test_create_menu_item_runner(self):
        """Test POST /api/kitchen/menu creates item with correct store field for Runner"""
        test_name = f"TEST_Pytest_Runner_{uuid.uuid4().hex[:8]}"
        
        payload = {
            "name": test_name,
            "description": "Test item created by pytest",
            "price": 15.50,
            "category": "Doces",
            "store": "runner",
            "available": True
        }
        
        response = requests.post(f"{BASE_URL}/api/kitchen/menu", json=payload)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("name") == test_name, f"Name mismatch: {data.get('name')}"
        assert data.get("store") == "runner", f"Store should be 'runner', got: {data.get('store')}"
        assert data.get("price") == 15.50, f"Price mismatch: {data.get('price')}"
        assert "id" in data, "Response should contain 'id'"
        
        self.test_item_id = data.get("id")
        
        # Verify item appears in Runner menu
        get_response = requests.get(f"{BASE_URL}/api/kitchen/menu/runner")
        assert get_response.status_code == 200
        
        items = get_response.json().get("items", [])
        item_names = [i.get("name") for i in items]
        assert test_name in item_names, f"Created item not found in Runner menu"
        
        # Verify item does NOT appear in GYM Londres menu
        gym_response = requests.get(f"{BASE_URL}/api/kitchen/menu/gym-londres")
        gym_items = gym_response.json().get("items", [])
        gym_item_names = [i.get("name") for i in gym_items]
        assert test_name not in gym_item_names, f"Runner item should not appear in GYM Londres menu"
        
        print(f"SUCCESS: Created menu item '{test_name}' for Runner store")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/kitchen/menu/{self.test_item_id}")
        self.test_item_id = None
    
    def test_create_menu_item_gym_londres(self):
        """Test POST /api/kitchen/menu creates item with correct store field for GYM Londres"""
        test_name = f"TEST_Pytest_GYM_{uuid.uuid4().hex[:8]}"
        
        payload = {
            "name": test_name,
            "description": "Test item created by pytest for GYM",
            "price": 22.00,
            "category": "Salgados",
            "store": "gym-londres",
            "available": True
        }
        
        response = requests.post(f"{BASE_URL}/api/kitchen/menu", json=payload)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("name") == test_name, f"Name mismatch: {data.get('name')}"
        assert data.get("store") == "gym-londres", f"Store should be 'gym-londres', got: {data.get('store')}"
        assert data.get("price") == 22.00, f"Price mismatch: {data.get('price')}"
        
        self.test_item_id = data.get("id")
        
        # Verify item appears in GYM Londres menu
        get_response = requests.get(f"{BASE_URL}/api/kitchen/menu/gym-londres")
        assert get_response.status_code == 200
        
        items = get_response.json().get("items", [])
        item_names = [i.get("name") for i in items]
        assert test_name in item_names, f"Created item not found in GYM Londres menu"
        
        # Verify item does NOT appear in Runner menu
        runner_response = requests.get(f"{BASE_URL}/api/kitchen/menu/runner")
        runner_items = runner_response.json().get("items", [])
        runner_item_names = [i.get("name") for i in runner_items]
        assert test_name not in runner_item_names, f"GYM Londres item should not appear in Runner menu"
        
        print(f"SUCCESS: Created menu item '{test_name}' for GYM Londres store")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/kitchen/menu/{self.test_item_id}")
        self.test_item_id = None
    
    def test_delete_menu_item(self):
        """Test DELETE /api/kitchen/menu/{item_id} removes item"""
        # First create an item
        test_name = f"TEST_Delete_{uuid.uuid4().hex[:8]}"
        
        create_response = requests.post(f"{BASE_URL}/api/kitchen/menu", json={
            "name": test_name,
            "description": "Item to be deleted",
            "price": 10.00,
            "category": "Doces",
            "store": "runner",
            "available": True
        })
        
        assert create_response.status_code == 200
        item_id = create_response.json().get("id")
        
        # Delete the item
        delete_response = requests.delete(f"{BASE_URL}/api/kitchen/menu/{item_id}")
        assert delete_response.status_code == 200, f"Delete failed: {delete_response.text}"
        
        # Verify item no longer appears in menu
        get_response = requests.get(f"{BASE_URL}/api/kitchen/menu/runner")
        items = get_response.json().get("items", [])
        item_ids = [i.get("id") for i in items]
        assert item_id not in item_ids, "Deleted item should not appear in menu"
        
        print(f"SUCCESS: Deleted menu item '{test_name}'")
    
    def test_store_separation(self):
        """Test that menu items are properly separated by store"""
        # Get Runner items
        runner_response = requests.get(f"{BASE_URL}/api/kitchen/menu/runner")
        runner_items = runner_response.json().get("items", [])
        
        # Get GYM Londres items
        gym_response = requests.get(f"{BASE_URL}/api/kitchen/menu/gym-londres")
        gym_items = gym_response.json().get("items", [])
        
        # Verify no overlap in item IDs
        runner_ids = set(i.get("id") for i in runner_items)
        gym_ids = set(i.get("id") for i in gym_items)
        
        overlap = runner_ids.intersection(gym_ids)
        assert len(overlap) == 0, f"Found overlapping items between stores: {overlap}"
        
        print(f"SUCCESS: Store separation verified - Runner: {len(runner_items)} items, GYM Londres: {len(gym_items)} items")


class TestKitchenMenuValidation:
    """Test input validation for menu endpoints"""
    
    def test_create_item_missing_name(self):
        """Test that creating item without name fails"""
        payload = {
            "description": "Test",
            "price": 10.00,
            "category": "Doces",
            "store": "runner"
        }
        
        response = requests.post(f"{BASE_URL}/api/kitchen/menu", json=payload)
        # Should fail validation
        assert response.status_code in [400, 422], f"Expected validation error, got {response.status_code}"
    
    def test_create_item_missing_price(self):
        """Test that creating item without price fails"""
        payload = {
            "name": "Test Item",
            "description": "Test",
            "category": "Doces",
            "store": "runner"
        }
        
        response = requests.post(f"{BASE_URL}/api/kitchen/menu", json=payload)
        # Should fail validation
        assert response.status_code in [400, 422], f"Expected validation error, got {response.status_code}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
