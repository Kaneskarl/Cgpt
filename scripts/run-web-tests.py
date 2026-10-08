"""Disposable web-test server; never initialize production with this script."""
import os
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
url=os.environ.get('WEB_TEST_DATABASE_URL','sqlite:///'+str(Path(tempfile.gettempdir())/'attendance.web-test.db'))
if not url.startswith('sqlite:') and not url.rsplit('/',1)[-1].endswith('_test'):
    raise SystemExit('Use a disposable WEB_TEST_DATABASE_URL ending in _test')
os.environ['DATABASE_URL']=url
os.environ['JWT_SECRET']='web-tests-only-not-a-real-deployment-secret-123456'
os.environ['COOKIE_SECURE']='false'
from app.db import Base,engine,SessionLocal
from app.models import User,OfficeSettings
from app.security import passwords
import uvicorn

Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)
with SessionLocal() as db:
    db.add(OfficeSettings(id=1,office_name='Municipal Office'))
    db.add(User(username='webtester',name='Test Administrator',role='admin',password_hash=passwords.hash('Web-test-password-123!')))
    db.commit()
uvicorn.run('app.main:app',host='127.0.0.1',port=8765,log_level='warning')
