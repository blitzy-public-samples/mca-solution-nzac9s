import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

# Test cases for application endpoints
def test_create_application():
    response = client.post("/applications/", json={"merchant_id": "123", "amount": 5000})
    assert response.status_code == 201
    assert "id" in response.json()

def test_get_application():
    response = client.get("/applications/1")
    assert response.status_code == 200
    assert "id" in response.json()

def test_update_application():
    response = client.put("/applications/1", json={"status": "approved"})
    assert response.status_code == 200
    assert response.json()["status"] == "approved"

def test_delete_application():
    response = client.delete("/applications/1")
    assert response.status_code == 204

# Test cases for merchant endpoints
def test_create_merchant():
    response = client.post("/merchants/", json={"name": "Test Merchant", "email": "test@example.com"})
    assert response.status_code == 201
    assert "id" in response.json()

def test_get_merchant():
    response = client.get("/merchants/1")
    assert response.status_code == 200
    assert "id" in response.json()

def test_update_merchant():
    response = client.put("/merchants/1", json={"name": "Updated Merchant"})
    assert response.status_code == 200
    assert response.json()["name"] == "Updated Merchant"

def test_delete_merchant():
    response = client.delete("/merchants/1")
    assert response.status_code == 204

# Test cases for attachment endpoints
def test_upload_attachment():
    # HUMAN ASSISTANCE NEEDED
    # Implement file upload test using appropriate library (e.g., pytest-mock or io.BytesIO)
    pass

def test_get_attachment():
    response = client.get("/attachments/1")
    assert response.status_code == 200
    assert "id" in response.json()

def test_delete_attachment():
    response = client.delete("/attachments/1")
    assert response.status_code == 204

# Test cases for webhook endpoints
def test_create_webhook():
    response = client.post("/webhooks/", json={"url": "https://example.com/webhook", "events": ["application.created"]})
    assert response.status_code == 201
    assert "id" in response.json()

def test_get_webhook():
    response = client.get("/webhooks/1")
    assert response.status_code == 200
    assert "id" in response.json()

def test_update_webhook():
    response = client.put("/webhooks/1", json={"events": ["application.created", "application.updated"]})
    assert response.status_code == 200
    assert "application.updated" in response.json()["events"]

def test_delete_webhook():
    response = client.delete("/webhooks/1")
    assert response.status_code == 204