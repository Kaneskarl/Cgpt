import base64
import time
import os
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from io import BytesIO
from zoneinfo import ZoneInfo

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from pypdf import PdfReader
from sqlalchemy import select
from PIL import Image
from app.db import SessionLocal
from app.db import engine
from app.config import Settings
from pydantic import ValidationError
from app.models import Attendance, Audit, Employee, Enrollment, User

MANILA=ZoneInfo('Asia/Manila')


def test_bootstrap_rejects_example_signing_secret():
    with pytest.raises(ValidationError):
        Settings(jwt_secret='REPLACE_WITH_A_RANDOM_SECRET_OF_AT_LEAST_32_CHARACTERS',_env_file=None)


def test_philippine_time_without_system_timezone_database():
    env=os.environ.copy()
    env['PYTHONTZPATH']=''
    result=subprocess.run([sys.executable,'-c',
        "from datetime import datetime,timedelta; from zoneinfo import ZoneInfo; "
        "assert datetime(2026,10,8,tzinfo=ZoneInfo('Asia/Manila')).utcoffset()==timedelta(hours=8)"],
        env=env,capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def add_employee(client, number='EMP-001'):
    result=client.post('/api/employees',json={'employee_no':number,'name':'Juan Dela Cruz','position':'Field Officer'})
    assert result.status_code==201, result.text
    employee=result.json()
    with SessionLocal() as db:
        employee['qr_code']=db.get(Employee,employee['id']).qr_code
    return employee


def enroll(client, headers):
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    pem=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    code=client.post('/api/devices/enrollment-code').json()['code']
    result=client.post('/api/devices/enroll',json={'name':'Office phone','code':code,'public_key':pem},headers=headers)
    assert result.status_code==201,result.text
    return key,result.json()['device_id'],code,pem


def scan_body(key, device_id, qr, action='am_in',timestamp=None,intent='scan'):
    data={'request_id':str(uuid.uuid4()),'timestamp_ms':timestamp or int(time.time()*1000),'qr_code':qr,'action':action,'device_id':device_id}
    payload=f'attendance.{intent}.v1\n{data["request_id"]}\n{data["timestamp_ms"]}\n{qr}\n{action}'
    data['signature']=base64.b64encode(key.sign(payload.encode(),padding.PKCS1v15(),hashes.SHA256())).decode()
    return data


def test_login_permissions_and_csrf(client, operator_headers):
    assert client.get('/api/employees').status_code==401
    assert client.get('/api/employees',headers=operator_headers).status_code==403
    assert client.post('/api/auth/login',json={'username':'operator','password':'Operator-testing-123'}).status_code==403
    result=client.post('/api/auth/login',json={'username':'admin','password':'Admin-testing-123'})
    assert result.status_code==200
    assert 'HttpOnly' in result.headers['set-cookie']
    assert 'token' not in result.json()
    assert client.post('/api/employees',json={'employee_no':'1','name':'Name'}).status_code==403


def test_login_rate_limit_and_cross_site(client):
    assert client.post('/api/auth/login',headers={'Origin':'https://other.example'},json={'username':'admin','password':'x'}).status_code==403
    for _ in range(10):
        assert client.post('/api/auth/login',json={'username':'admin','password':'wrong'}).status_code==401
    assert client.post('/api/auth/login',json={'username':'admin','password':'Admin-testing-123'}).status_code==429


def test_employee_duplicate_and_invalid_photo(admin_client):
    emp=add_employee(admin_client)
    assert admin_client.post('/api/employees',json={'employee_no':'EMP-001','name':'Other'}).status_code==409
    assert admin_client.post(f'/api/employees/{emp["id"]}/photo',files={'file':('x.png',b'not an image','image/png')}).status_code==422
    output=BytesIO();Image.new('RGB',(100,100),'green').save(output,format='PNG')
    assert admin_client.post(f'/api/employees/{emp["id"]}/photo',files={'file':('x.png',output.getvalue(),'image/png')}).status_code==200
    assert admin_client.get(f'/api/employees/{emp["id"]}/photo').headers['content-type']=='image/jpeg'
    assert admin_client.get(f'/api/employees/{emp["id"]}/qr.png').content.startswith(b'\x89PNG')
    assert PdfReader(BytesIO(admin_client.get(f'/api/employees/{emp["id"]}/id.pdf').content)).pages[0].extract_text().find('Juan Dela Cruz')>=0


def test_enrollment_single_device_and_code_reuse(admin_client,operator_headers):
    key,device,code,pem=enroll(admin_client,operator_headers)
    assert admin_client.post('/api/devices/enrollment-code').status_code==409
    assert admin_client.post('/api/devices/enroll',headers=operator_headers,json={'code':code,'name':'Other','public_key':pem}).status_code==403
    assert admin_client.post(f'/api/devices/{device}/revoke',json={'reason':'Phone replaced'}).status_code==200
    assert admin_client.post('/api/devices/enrollment-code').status_code==200


def test_expired_enrollment(admin_client,operator_headers):
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    pem=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    code=admin_client.post('/api/devices/enrollment-code').json()['code']
    with SessionLocal() as db:
        value=db.scalar(select(Enrollment));value.expires_at=datetime.now(timezone.utc)-timedelta(minutes=1);db.commit()
    assert admin_client.post('/api/devices/enroll',headers=operator_headers,json={'code':code,'name':'Phone','public_key':pem}).status_code==403


def test_four_slots_duplicate_and_retry(admin_client,operator_headers):
    emp=add_employee(admin_client);key,device,_,_=enroll(admin_client,operator_headers)
    for action in ('am_in','am_out','pm_in','pm_out'):
        body=scan_body(key,device,emp['qr_code'],action)
        start=datetime.now(timezone.utc)
        result=admin_client.post('/api/scans',headers=operator_headers,json=body)
        assert result.status_code==200,result.text
        recorded=datetime.fromisoformat(result.json()['attendance']['recorded_at'])
        assert recorded>=start and recorded<=datetime.now(timezone.utc)
        assert recorded.utcoffset()==timedelta(hours=8)
        assert result.json()['employee']['name']=='Juan Dela Cruz'
        assert admin_client.post('/api/scans',headers=operator_headers,json=body).json()['replayed'] is True
        assert admin_client.post('/api/scans',headers=operator_headers,json=scan_body(key,device,emp['qr_code'],action)).status_code==409
    with SessionLocal() as db:
        assert len(list(db.scalars(select(Attendance))))==4


def test_scan_tampering_stale_clock_and_revocation(admin_client,operator_headers):
    emp=add_employee(admin_client);key,device,_,_=enroll(admin_client,operator_headers)
    body=scan_body(key,device,emp['qr_code']);body['action']='pm_out'
    assert admin_client.post('/api/scans',headers=operator_headers,json=body).status_code==403
    assert admin_client.post('/api/scans',headers=operator_headers,json=scan_body(key,device,emp['qr_code'],timestamp=int(time.time()*1000)-120000)).status_code==422
    assert admin_client.post('/api/scans',json=scan_body(key,device,emp['qr_code'])).status_code==403
    assert admin_client.post('/api/scans',headers=operator_headers,json=scan_body(key,'00000000-0000-0000-0000-000000000000',emp['qr_code'])).status_code==403
    admin_client.post(f'/api/devices/{device}/revoke',json={'reason':'Lost phone'})
    assert admin_client.post('/api/scans',headers=operator_headers,json=scan_body(key,device,emp['qr_code'])).status_code==403


def test_replaced_and_inactive_ids(admin_client,operator_headers):
    emp=add_employee(admin_client);key,device,_,_=enroll(admin_client,operator_headers)
    admin_client.post(f'/api/employees/{emp["id"]}/replace-qr',json={'reason':'Lost printed ID'})
    assert admin_client.post('/api/scans',headers=operator_headers,json=scan_body(key,device,emp['qr_code'])).status_code==404
    with SessionLocal() as db:
        new=db.get(Employee,emp['id']).qr_code
    admin_client.put(f'/api/employees/{emp["id"]}',json={'employee_no':'EMP-001','name':emp['name'],'active':False})
    assert admin_client.post('/api/scans',headers=operator_headers,json=scan_body(key,device,new)).status_code==404


def test_correction_audit_and_concurrent_edit(admin_client):
    emp=add_employee(admin_client)
    body={'employee_id':emp['id'],'work_date':'2026-01-05','action':'am_in','local_time':'08:00','reason':'Verified manual outage sheet','expected_version':0}
    result=admin_client.post('/api/attendance/correct',json=body);assert result.status_code==200,result.text
    assert result.json()['source']=='manual'
    body.update(local_time='08:15',expected_version=1)
    result=admin_client.post('/api/attendance/correct',json=body);assert result.status_code==200
    assert result.json()['recorded_at'][11:16]=='08:15'
    assert result.json()['original_recorded_at'][11:16]=='08:00'
    assert admin_client.post('/api/attendance/correct',json=body).status_code==409
    history=admin_client.get('/api/audit?subject='+result.json()['id']).json()
    assert len(history)==2
    assert history[0]['before']['recorded_at'][11:16]=='08:00'
    assert history[0]['after']['recorded_at'][11:16]=='08:15'
    assert history[0]['actor']=='Test Admin'


def test_future_correction_rejected(admin_client):
    emp=add_employee(admin_client)
    tomorrow=(datetime.now(MANILA)+timedelta(days=1)).date().isoformat()
    assert admin_client.post('/api/attendance/correct',json={'employee_id':emp['id'],'work_date':tomorrow,'action':'am_in','local_time':'08:00','reason':'Future entry test','expected_version':0}).status_code==422


def test_field_duty_does_not_create_attendance(admin_client):
    emp=add_employee(admin_client)
    body={'employee_id':emp['id'],'work_date':'2026-01-05','period':'full_day','location':'Site A','purpose':'Official inspection','reason':'Approved office assignment','expected_version':0}
    result=admin_client.post('/api/field-duty',json=body);assert result.status_code==200,result.text
    data=admin_client.get('/api/attendance?start=2026-01-05&end=2026-01-05').json()
    assert data['records']==[] and len(data['field_duties'])==1
    assert admin_client.post('/api/field-duty',json=body).status_code==409
    pdf=PdfReader(BytesIO(admin_client.get(f'/api/reports/{emp["id"]}/2026-01.pdf').content))
    assert len(pdf.pages)==2
    assert 'Official inspection' in pdf.pages[1].extract_text()
    assert admin_client.request('DELETE','/api/field-duty/'+result.json()['id']+'?version=1',json={'reason':'Assignment cancelled'}).status_code==200


def test_finalize_reopen_and_pdf(admin_client):
    emp=add_employee(admin_client)
    assert admin_client.post('/api/months/2026-01/finalize',json={'reason':'Records reviewed and approved'}).status_code==200
    body={'employee_id':emp['id'],'work_date':'2026-01-05','action':'am_in','local_time':'08:00','reason':'Verified outage sheet','expected_version':0}
    assert admin_client.post('/api/attendance/correct',json=body).status_code==409
    assert admin_client.post('/api/months/2026-01/reopen',json={'reason':'Correction approved by supervisor'}).status_code==200
    assert admin_client.post('/api/attendance/correct',json=body).status_code==200
    pdf=admin_client.get(f'/api/reports/{emp["id"]}/2026-01.pdf')
    assert pdf.status_code==200 and pdf.content.startswith(b'%PDF')
    assert pdf.headers['x-frame-options']=='SAMEORIGIN'
    assert pdf.headers['content-security-policy']=="frame-ancestors 'self'"
    assert admin_client.get('/').headers['x-frame-options']=='DENY'
    content=PdfReader(BytesIO(pdf.content)).pages[0].extract_text()
    for text in ('Civil Service Form No. 48','DAILY TIME RECORD','Juan Dela Cruz','January 2026','8:00','Undertime','Verified'):
        assert text in content
    current=datetime.now(MANILA).strftime('%Y-%m')
    assert admin_client.post(f'/api/months/{current}/finalize',json={'reason':'Cannot finalize current month'}).status_code==409
    assert admin_client.get(f'/api/reports/{emp["id"]}/2026-13.pdf').status_code==422


def test_account_disable_invalidates_session(admin_client,operator_headers):
    accounts=admin_client.get('/api/accounts').json();user=next(u for u in accounts if u['role']=='operator')
    assert admin_client.put('/api/accounts/'+user['id'],json={'active':False}).status_code==200
    assert admin_client.get('/api/settings',headers=operator_headers).status_code==401
    assert admin_client.post('/api/accounts',json={'username':'operator','name':'Duplicate','role':'operator','password':'Long-password-123'}).status_code==409
    me=next(u for u in accounts if u['role']=='admin')
    assert admin_client.put('/api/accounts/'+me['id'],json={'active':False}).status_code==409


def test_invalid_schedule_and_no_automatic_rules(admin_client):
    settings=admin_client.get('/api/settings').json();settings.pop('timezone')
    assert settings['pm_in']=='13:30'
    settings['am_out']='07:00'
    assert admin_client.put('/api/settings',json=settings).status_code==422
    settings['am_out']='12:00';settings['am_in']='29:00'
    assert admin_client.put('/api/settings',json=settings).status_code==422


def test_identify_requires_device_and_does_not_save(admin_client,operator_headers):
    emp=add_employee(admin_client);key,device,_,_=enroll(admin_client,operator_headers)
    body=scan_body(key,device,emp['qr_code'],intent='identify')
    result=admin_client.post('/api/scanner/identify',headers=operator_headers,json=body)
    assert result.status_code==200 and result.json()['employee']['name']==emp['name']
    assert result.json()['existing'] is None
    with SessionLocal() as db:
        assert list(db.scalars(select(Attendance)))==[]
    assert admin_client.post('/api/scans',headers=operator_headers,json=body).status_code==403
    assert admin_client.post('/api/scanner/identify',headers=operator_headers,json=scan_body(key,device,emp['qr_code'])).status_code==403


def test_void_retains_original_and_allows_new_scan(admin_client,operator_headers):
    emp=add_employee(admin_client);key,device,_,_=enroll(admin_client,operator_headers)
    body=scan_body(key,device,emp['qr_code'])
    original=admin_client.post('/api/scans',headers=operator_headers,json=body).json()['attendance']
    result=admin_client.post(f'/api/attendance/{original["id"]}/void',json={'reason':'Wrong action selected','expected_version':1})
    assert result.status_code==200 and result.json()['voided'] is True
    assert result.json()['original_recorded_at']==original['recorded_at']
    assert admin_client.post('/api/scans',headers=operator_headers,json=body).status_code==409
    identified=admin_client.post('/api/scanner/identify',headers=operator_headers,json=scan_body(key,device,emp['qr_code'],intent='identify'))
    assert identified.json()['existing'] is None
    result=admin_client.post('/api/scans',headers=operator_headers,json=scan_body(key,device,emp['qr_code']))
    assert result.status_code==200 and result.json()['attendance']['version']==3
    assert result.json()['attendance']['original_recorded_at']==original['recorded_at']


@pytest.mark.skipif(engine.dialect.name!='postgresql',reason='Requires PostgreSQL row locks')
def test_concurrent_duplicate_scan_serializes(admin_client,operator_headers):
    emp=add_employee(admin_client);key,device,_,_=enroll(admin_client,operator_headers)
    bodies=[scan_body(key,device,emp['qr_code']) for _ in range(2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda body:admin_client.post('/api/scans',headers=operator_headers,json=body),bodies))
    assert sorted(r.status_code for r in results)==[200,409]
    with SessionLocal() as db:assert len(list(db.scalars(select(Attendance))))==1


@pytest.mark.skipif(engine.dialect.name!='postgresql',reason='Requires PostgreSQL row locks')
def test_concurrent_safe_retry_returns_one_receipt(admin_client,operator_headers):
    emp=add_employee(admin_client);key,device,_,_=enroll(admin_client,operator_headers)
    body=scan_body(key,device,emp['qr_code'])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:admin_client.post('/api/scans',headers=operator_headers,json=body),range(2)))
    assert [r.status_code for r in results]==[200,200]
    assert sorted(r.json()['replayed'] for r in results)==[False,True]
