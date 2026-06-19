---
name: pytest
description: Testing conventions for KitchenMaster — pytest patterns for Flask + Supabase REST API. Use when writing or running tests.
metadata:
  framework: "pytest"
  project: "KitchenMaster (Flask + Supabase)"
---

# Testing with pytest — KitchenMaster

## Setup
```bash
pip install pytest pytest-flask
```

## Test Structure
```
tests/
├── conftest.py          # Fixtures (app, client, mock Supabase)
├── test_ingredients.py
├── test_recipes.py
├── test_menu.py
├── test_pos.py
├── test_dashboard.py
├── test_precios.py
└── test_auth.py
```

## Fixtures (conftest.py)
```python
import pytest
from api.index import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

@pytest.fixture
def auth_client(client):
    """Client with demo session pre-configured."""
    with client.session_transaction() as sess:
        sess['user'] = {'email': 'demo@example.com', 'id': 'demo-id'}
    return client
```

## Testing Supabase API Routes
Mock external Supabase calls:
```python
from unittest.mock import patch

@patch('api.index.api_req')
def test_list_ingredients(mock_api_req, auth_client):
    mock_api_req.return_value = {'data': [
        {'name': 'Sal', 'classification': 'Condimentos',
         'brand': '', 'supplier': '', 'presentation': '',
         'measure': 'kg', 'count': 10, 'cost': 2000, 'notes': ''}
    ]}
    resp = auth_client.get('/api/ingredients')
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]['name'] == 'Sal'
```

## Testing Page Routes
```python
def test_ingredients_page_loads(auth_client):
    resp = auth_client.get('/ingredients')
    assert resp.status_code == 200
    assert b'Ingredientes' in resp.data
```

## Test Naming
- Files: `test_<module>.py`
- Functions: `test_<action>_<context>` (e.g., `test_create_ingredient_missing_fields`).
- Classes: `Test<Feature>` (e.g., `TestIngredientsAPI`).

## What to Test
1. **API routes** — status codes, JSON response shape, error handling.
2. **Page routes** — status 200, template renders, key content present.
3. **Auth** — redirect when not logged in, demo session injection.
4. **Edge cases** — missing fields, invalid data, non-existent records.

## Running Tests
```bash
pytest tests/ -v                    # All tests
pytest tests/test_ingredients.py    # Single file
pytest tests/ -v -k "dashboard"     # Filter by name
pytest --cov=api tests/             # With coverage
```
