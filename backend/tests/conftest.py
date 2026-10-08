import os
import tempfile
from pathlib import Path

test_url = os.environ.get('TEST_DATABASE_URL', 'sqlite:///'+str(Path(tempfile.gettempdir())/'cgpt-attendance-tests.db'))
if not test_url.startswith('sqlite:') and not test_url.rsplit('/',1)[-1].endswith('_test'):
    raise RuntimeError('TEST_DATABASE_URL must target a disposable database ending in _test')
os.environ['DATABASE_URL'] = test_url
os.environ['JWT_SECRET'] = 'integration-test-key-with-at-least-thirty-two-characters'
os.environ['COOKIE_SECURE'] = 'false'

import pytest
from fastapi.testclient import TestClient
from app.db import Base, engine, SessionLocal
from app.models import User
from app.main import app, attempts
from app.security import passwords


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    attempts.clear()
    with TestClient(app) as client:
        with SessionLocal() as db:
            db.add_all([User(username='admin',name='Test Admin',role='admin',password_hash=passwords.hash('Admin-testing-123')),
                        User(username='operator',name='Test Operator',role='operator',password_hash=passwords.hash('Operator-testing-123'))])
            db.commit()
        yield client


@pytest.fixture
def admin_client(client):
    result=client.post('/api/auth/login',json={'username':'admin','password':'Admin-testing-123'})
    assert result.status_code==200
    client.headers['X-CSRF-Token']=result.json()['csrf']
    return client


@pytest.fixture
def operator_headers(client):
    result=client.post('/api/auth/login',json={'username':'operator','password':'Operator-testing-123','client':'scanner'})
    assert result.status_code==200
    return {'Authorization':'Bearer '+result.json()['token']}
