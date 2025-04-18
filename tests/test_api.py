import pytest
import json
from app import app as flask_app
import os
import sys

# Add parent directory to path so we can import app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

@pytest.fixture
def app():
    flask_app.config.update({
        "TESTING": True,
    })
    yield flask_app

@pytest.fixture
def client(app):
    return app.test_client()

def test_health_check(client):
    response = client.get('/health')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['status'] == 'healthy'
    assert data['service'] == 'flask-mysql-api'

def test_get_items(client, monkeypatch):
    # This test uses monkeypatching to avoid actual database connections
    class MockCursor:
        def execute(self, query, params=None):
            pass
        
        def fetchall(self):
            return [{'id': 1, 'name': 'Test Item', 'description': 'A test item'}]
        
        def fetchone(self):
            return {'count': 1}
        
        def close(self):
            pass
    
    class MockConnection:
        def cursor(self, dictionary=False):
            return MockCursor()
        
        def close(self):
            pass
    
    def mock_get_db_connection():
        return MockConnection()
    
    # Apply the monkeypatch
    monkeypatch.setattr('app.get_db_connection', mock_get_db_connection)
    
    response = client.get('/api/items')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert 'items' in data
    assert len(data['items']) == 1
    assert data['items'][0]['name'] == 'Test Item'
    assert 'pagination' in data

def test_create_item_validation(client):
    # Test with missing required field
    response = client.post('/api/items', 
                          data=json.dumps({'description': 'Missing name'}),
                          content_type='application/json')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data
    assert 'details' in data
    assert 'name' in data['details']
    
    # Test with invalid content type
    response = client.post('/api/items', 
                          data="This is not JSON",
                          content_type='text/plain')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data

def test_update_item_validation(client):
    # Test with empty update data
    response = client.put('/api/items/1', 
                         data=json.dumps({}),
                         content_type='application/json')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data
    assert 'No valid fields to update' in data['error']
    
    # Test with invalid item ID
    response = client.put('/api/items/0', 
                         data=json.dumps({'name': 'New name'}),
                         content_type='application/json')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data
    assert 'Item ID must be a positive integer' in data['error']

def test_delete_item_validation(client):
    # Test with invalid item ID
    response = client.delete('/api/items/-5')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data
    assert 'Item ID must be a positive integer' in data['error']

# Add more tests as needed