import base64
import calendar
import hashlib
import json
import re
import secrets
import time as clock
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import qrcode
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select, update, text
from sqlalchemy.exc import IntegrityError

from .config import settings
from .db import Base, engine, SessionLocal, get_db
from .models import Attendance, Audit, Device, Employee, Enrollment, FieldDuty, MonthLock, OfficeSettings, ScanReceipt, User, now
from .reports import form48, local
from .schemas import AccountInput, AccountUpdate, CorrectionInput, DutyInput, EmployeeInput, EnrollInput, Login, OfficeInput, ReasonInput, ScanInput, VersionReasonInput
from .security import admin, current_user, dummy_hash, operator, passwords, token_for

MANILA = ZoneInfo('Asia/Manila')
ACTIONS = ('am_in', 'am_out', 'pm_in', 'pm_out')
STATIC = Path(__file__).resolve().parents[2] / 'web'
attempts = defaultdict(deque)


@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if not db.get(OfficeSettings, 1):
            db.add(OfficeSettings(id=1))
            db.commit()
    yield


app = FastAPI(title='Office Attendance', version='0.1.0', lifespan=lifespan)


@app.middleware('http')
async def secure_headers(request, call_next):
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    # The admin dashboard embeds authenticated PDFs from this same server.
    is_pdf = response.headers.get('content-type', '').split(';', 1)[0] == 'application/pdf'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN' if is_pdf else 'DENY'
    if is_pdf:
        response.headers['Content-Security-Policy'] = "frame-ancestors 'self'"
    if request.url.path.startswith('/api'):
        response.headers['Cache-Control'] = 'no-store'
    else:
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self'; frame-src 'self' blob:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    return response


def audit(db, user, kind, subject, reason, before=None, after=None):
    db.add(Audit(actor_id=user.id, kind=kind, subject=subject, reason=reason,
                 before=json.dumps(before or {}, default=str), after=json.dumps(after or {}, default=str)))


def commit(db):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'A record already exists or changed. Refresh and try again.')


def flush(db):
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'A record already exists. Refresh and try again.')


def write_lock(db):
    # One small office: serialize writes to protect month locks and single-device enrollment.
    db.execute(select(OfficeSettings).where(OfficeSettings.id == 1).with_for_update()).scalar_one()


def employee(db, employee_id):
    value = db.get(Employee, employee_id)
    if not value:
        raise HTTPException(404, 'Employee not found')
    return value


def employee_json(value):
    return {'id': value.id, 'employee_no': value.employee_no, 'name': value.name,
            'position': value.position, 'active': value.active, 'has_photo': bool(value.photo)}


def attendance_json(value):
    return {'id': value.id, 'employee_id': value.employee_id, 'work_date': value.work_date.isoformat(),
            'action': value.action, 'recorded_at': local(value.recorded_at).isoformat(),
            'original_recorded_at': local(value.original_recorded_at).isoformat(),
            'source': value.source, 'corrected': value.corrected, 'voided':value.voided, 'version': value.version}


def duty_json(value):
    return {'id': value.id, 'employee_id': value.employee_id, 'work_date': str(value.work_date),
            'period': value.period, 'location': value.location, 'purpose': value.purpose, 'version': value.version}


def require_open_month(db, work_date):
    locked = db.get(MonthLock, work_date.strftime('%Y-%m'))
    if locked and locked.finalized:
        raise HTTPException(409, 'This month is finalized. An admin must reopen it before changes.')


def parse_month(month):
    try:
        value = datetime.strptime(month, '%Y-%m').date()
        if value.strftime('%Y-%m') != month or value.year < 2000 or value.year > 2100:
            raise ValueError()
    except ValueError:
        raise HTTPException(422, 'Use a month in YYYY-MM format (2000–2100)')
    return value, value.replace(day=calendar.monthrange(value.year, value.month)[1])


@app.get('/api/health')
def health(db=Depends(get_db)):
    db.execute(text('SELECT 1'))
    return {'status': 'ok', 'timezone': 'Asia/Manila', 'server_time': now().isoformat()}


@app.post('/api/auth/login')
def login(data: Login, request: Request, response: Response, db=Depends(get_db)):
    origin = request.headers.get('origin')
    if origin and urlsplit(origin).netloc != request.headers.get('host'):
        raise HTTPException(403, 'Cross-site login is not allowed')
    ip = request.client.host if request.client else 'unknown'
    ticks = clock.monotonic()
    history = attempts[ip]
    while history and history[0] < ticks-300:
        history.popleft()
    if len(history) >= 10:
        raise HTTPException(429, 'Too many login attempts. Wait five minutes.')
    history.append(ticks)
    if len(attempts) > 10000:
        for key in list(attempts):
            if not attempts[key] or attempts[key][-1] < ticks-300:
                del attempts[key]
    user = db.scalar(select(User).where(User.username == data.username))
    valid = passwords.verify(data.password, user.password_hash if user else dummy_hash)
    if not user or not valid or not user.active:
        raise HTTPException(401, 'Invalid username or password')
    if data.client == 'web' and user.role != 'admin':
        raise HTTPException(403, 'The web dashboard is for administrators')
    if data.client == 'scanner' and user.role != 'operator':
        raise HTTPException(403, 'Use an operator account on the scanner')
    attempts.pop(ip, None)
    token, csrf = token_for(user)
    result = {'id': user.id, 'name': user.name, 'role': user.role, 'csrf': csrf}
    if data.client == 'scanner':
        result['token'] = token
    else:
        response.set_cookie('attendance_session', token, httponly=True, secure=settings().cookie_secure,
                            samesite='strict', max_age=settings().session_hours*3600, path='/')
    return result


@app.get('/api/auth/me')
def me(request: Request, user=Depends(current_user)):
    return {'id': user.id, 'name': user.name, 'role': user.role, 'csrf': request.state.csrf}


@app.post('/api/auth/logout')
def logout(response: Response, user=Depends(current_user)):
    response.delete_cookie('attendance_session', path='/', secure=settings().cookie_secure, httponly=True, samesite='strict')
    return {'ok': True}


@app.get('/api/employees')
def employees(user=Depends(admin), db=Depends(get_db)):
    return [employee_json(e) for e in db.scalars(select(Employee).order_by(Employee.name))]


@app.post('/api/employees', status_code=201)
def add_employee(data: EmployeeInput, user=Depends(admin), db=Depends(get_db)):
    write_lock(db)
    value = Employee(**data.model_dump(), qr_code='dtr:v1:'+secrets.token_urlsafe(32))
    db.add(value)
    flush(db)
    audit(db, user, 'employee.created', value.id, 'Employee registered', after=employee_json(value))
    commit(db)
    return employee_json(value)


@app.put('/api/employees/{employee_id}')
def edit_employee(employee_id: str, data: EmployeeInput, user=Depends(admin), db=Depends(get_db)):
    write_lock(db)
    value = employee(db, employee_id)
    before = employee_json(value)
    for key, val in data.model_dump().items():
        setattr(value, key, val)
    audit(db, user, 'employee.updated', value.id, 'Employee details updated', before, employee_json(value))
    commit(db)
    return employee_json(value)


@app.post('/api/employees/{employee_id}/photo')
async def upload_photo(employee_id: str, file: UploadFile, user=Depends(admin), db=Depends(get_db)):
    raw = await file.read(2*1024*1024+1)
    if len(raw) > 2*1024*1024:
        raise HTTPException(413, 'Photo must be smaller than 2 MB')
    try:
        image = Image.open(BytesIO(raw))
        if image.format not in ('JPEG', 'PNG', 'WEBP') or image.width*image.height > 16_000_000:
            raise ValueError()
        image.load()
        from PIL import ImageOps
        image = ImageOps.exif_transpose(image).convert('RGB')
        image.thumbnail((640,640))
        output = BytesIO()
        image.save(output, format='JPEG', quality=85)
    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError):
        raise HTTPException(422, 'Upload a valid JPEG, PNG, or WebP photo (up to 16 megapixels)')
    write_lock(db)
    value = employee(db, employee_id)
    value.photo = output.getvalue()
    audit(db, user, 'employee.photo', value.id, 'Employee photo replaced')
    commit(db)
    return {'ok': True}


@app.get('/api/employees/{employee_id}/photo')
def photo(employee_id: str, user=Depends(current_user), db=Depends(get_db)):
    value = employee(db, employee_id)
    if not value.photo:
        raise HTTPException(404, 'No photo available')
    return Response(value.photo, media_type='image/jpeg')


@app.post('/api/employees/{employee_id}/replace-qr')
def replace_qr(employee_id: str, data: ReasonInput, user=Depends(admin), db=Depends(get_db)):
    write_lock(db)
    value = employee(db, employee_id)
    value.qr_code = 'dtr:v1:'+secrets.token_urlsafe(32)
    audit(db, user, 'employee.qr_replaced', value.id, data.reason)
    commit(db)
    return {'ok': True}


@app.get('/api/employees/{employee_id}/qr.png')
def qr_png(employee_id: str, user=Depends(admin), db=Depends(get_db)):
    output=BytesIO()
    qrcode.make(employee(db, employee_id).qr_code).save(output, format='PNG')
    return Response(output.getvalue(), media_type='image/png')


@app.get('/api/employees/{employee_id}/id.pdf')
def id_pdf(employee_id: str, user=Depends(admin), db=Depends(get_db)):
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    from reportlab.lib.units import mm
    from reportlab.lib.pagesizes import A4
    from .reports import fit
    value = employee(db, employee_id)
    output = BytesIO()
    c = canvas.Canvas(output, pagesize=A4)
    x, y = 20*mm, 230*mm
    c.roundRect(x, y, 86*mm, 54*mm, 3*mm)
    fit(c, db.get(OfficeSettings,1).office_name, x+4*mm, y+46*mm, 78*mm, 11)
    if value.photo:
        c.drawImage(ImageReader(BytesIO(value.photo)), x+4*mm, y+16*mm, width=23*mm, height=26*mm, preserveAspectRatio=True, anchor='c')
    qr = BytesIO()
    qrcode.make(value.qr_code).save(qr, format='PNG')
    c.drawImage(ImageReader(BytesIO(qr.getvalue())), x+52*mm, y+12*mm, width=30*mm, height=30*mm)
    fit(c, value.name, x+4*mm, y+10*mm, 78*mm, 10)
    fit(c, value.employee_no+' | '+value.position, x+4*mm, y+5*mm, 78*mm, 8)
    c.setFont('OfficeSans',9)
    c.drawString(x, y-9*mm, 'Print at actual size (100%). Cut along the border.')
    c.save()
    number=re.sub(r'[^A-Za-z0-9_-]','',value.employee_no) or value.id[:8]
    return Response(output.getvalue(), media_type='application/pdf', headers={'Content-Disposition': f'inline; filename="employee-id-{number}.pdf"'})


@app.get('/api/accounts')
def accounts(user=Depends(admin), db=Depends(get_db)):
    return [{'id': u.id,'username':u.username,'name':u.name,'role':u.role,'active':u.active} for u in db.scalars(select(User).order_by(User.name))]


@app.post('/api/accounts', status_code=201)
def add_account(data: AccountInput, user=Depends(admin), db=Depends(get_db)):
    write_lock(db)
    value = User(username=data.username, name=data.name, role=data.role, password_hash=passwords.hash(data.password))
    db.add(value)
    flush(db)
    audit(db, user, 'account.created', value.id, 'Account created', after={'username':value.username,'role':value.role})
    commit(db)
    return {'id': value.id}


@app.put('/api/accounts/{account_id}')
def update_account(account_id: str, data: AccountUpdate, user=Depends(admin), db=Depends(get_db)):
    write_lock(db)
    value = db.get(User, account_id)
    if not value:
        raise HTTPException(404, 'Account not found')
    if value.id == user.id and not data.active:
        raise HTTPException(409, 'You cannot disable your own account')
    value.active = data.active
    value.auth_version += 1
    if data.password:
        value.password_hash = passwords.hash(data.password)
    audit(db, user, 'account.updated', value.id, data.reason, after={'active':value.active,'password_reset':bool(data.password)})
    commit(db)
    return {'ok': True}


@app.get('/api/devices')
def devices(user=Depends(admin), db=Depends(get_db)):
    return [{'id':d.id,'name':d.name,'active':d.active,'enrolled_at':local(d.enrolled_at).isoformat()} for d in db.scalars(select(Device).order_by(Device.enrolled_at.desc()))]


@app.post('/api/devices/enrollment-code')
def enrollment_code(user=Depends(admin), db=Depends(get_db)):
    write_lock(db)
    if db.scalar(select(Device).where(Device.active)):
        raise HTTPException(409, 'Revoke the current scanner before enrolling another phone')
    db.execute(update(Enrollment).where(Enrollment.used == False).values(used=True))
    code = secrets.token_urlsafe(24)
    expiry = now()+timedelta(minutes=10)
    db.add(Enrollment(token_hash=hashlib.sha256(code.encode()).hexdigest(), expires_at=expiry, created_by=user.id))
    audit(db, user, 'device.enrollment_code', 'scanner', 'One-time enrollment authorized')
    commit(db)
    return {'code':code,'expires_at':expiry.isoformat()}


@app.post('/api/devices/enroll', status_code=201)
def enroll(data: EnrollInput, user=Depends(operator), db=Depends(get_db)):
    try:
        key = serialization.load_pem_public_key(data.public_key.encode())
        if not isinstance(key, rsa.RSAPublicKey) or key.key_size not in (2048, 3072, 4096):
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(422, 'Use a valid RSA public key (2048–4096 bits)')
    write_lock(db)
    token = db.scalar(select(Enrollment).where(Enrollment.token_hash == hashlib.sha256(data.code.encode()).hexdigest()))
    if not token or token.used or local(token.expires_at) <= now().astimezone(MANILA):
        raise HTTPException(403, 'Enrollment code is invalid, expired, or already used')
    if db.scalar(select(Device).where(Device.active)):
        raise HTTPException(409, 'An authorized scanner already exists')
    value = Device(name=data.name, public_key=data.public_key, enrolled_by=user.id)
    db.add(value)
    token.used = True
    flush(db)
    audit(db, user, 'device.enrolled', value.id, 'Scanner enrolled', after={'name':value.name})
    commit(db)
    return {'device_id':value.id}


@app.post('/api/devices/{device_id}/revoke')
def revoke(device_id: str, data: ReasonInput, user=Depends(admin), db=Depends(get_db)):
    write_lock(db)
    value = db.get(Device,device_id)
    if not value:
        raise HTTPException(404, 'Device not found')
    value.active = False
    audit(db,user,'device.revoked',value.id,data.reason)
    commit(db)
    return {'ok':True}


@app.post('/api/scans')
def scan(data: ScanInput, user=Depends(operator), db=Depends(get_db)):
    write_lock(db)
    device = db.get(Device,data.device_id)
    if not device or not device.active:
        raise HTTPException(403, 'This phone is not an authorized scanner')
    payload = f'attendance.scan.v1\n{data.request_id}\n{data.timestamp_ms}\n{data.qr_code}\n{data.action}'
    try:
        key = serialization.load_pem_public_key(device.public_key.encode())
        key.verify(base64.b64decode(data.signature, validate=True), payload.encode(), padding.PKCS1v15(), hashes.SHA256())
    except (ValueError, InvalidSignature):
        raise HTTPException(403, 'Device signature is invalid')
    payload_hash = hashlib.sha256(payload.encode()).hexdigest()
    receipt = db.get(ScanReceipt,data.request_id)
    if receipt:
        if receipt.device_id != device.id or receipt.operator_id != user.id or receipt.payload_hash != payload_hash:
            raise HTTPException(409, 'Scan request identifier was already used')
        value = db.get(Attendance,receipt.attendance_id)
        if value.voided or value.version != receipt.attendance_version:
            raise HTTPException(409, 'The original scan was changed by an admin. Review its current record in the dashboard.')
        return {'attendance':attendance_json(value), 'employee':employee_json(employee(db,value.employee_id)), 'replayed':True}
    if abs(clock.time()*1000-data.timestamp_ms) > 90_000:
        raise HTTPException(422, 'Phone clock differs from the server. Enable automatic date and time, then rescan.')
    value = db.scalar(select(Employee).where(Employee.qr_code == data.qr_code))
    if not value or not value.active:
        raise HTTPException(404, 'ID is unknown, replaced, or inactive')
    stamp = now()
    work_date = stamp.astimezone(MANILA).date()
    require_open_month(db,work_date)
    previous = db.scalar(select(Attendance).where(Attendance.employee_id==value.id,Attendance.work_date==work_date,Attendance.action==data.action))
    if previous and not previous.voided:
        raise HTTPException(409, f'{data.action.replace("_"," ").upper()} already recorded at {local(previous.recorded_at):%I:%M %p}. No new entry was saved.')
    before=attendance_json(previous) if previous else {}
    if previous:
        record=previous
        record.recorded_at=stamp
        record.voided=False
        record.corrected=True
        record.source='scan'
        record.operator_id=user.id
        record.device_id=device.id
        record.version+=1
    else:
        record = Attendance(employee_id=value.id,work_date=work_date,action=data.action,recorded_at=stamp,
                            original_recorded_at=stamp,source='scan',operator_id=user.id,device_id=device.id)
        db.add(record)
    flush(db)
    db.add(ScanReceipt(request_id=data.request_id,device_id=device.id,operator_id=user.id,payload_hash=payload_hash,attendance_id=record.id,attendance_version=record.version))
    audit(db,user,'attendance.scanned',record.id,'QR scan recorded',before,attendance_json(record))
    commit(db)
    return {'attendance':attendance_json(record),'employee':employee_json(value),'replayed':False}


@app.post('/api/scanner/identify')
def identify(data: ScanInput, user=Depends(operator), db=Depends(get_db)):
    device=db.get(Device,data.device_id)
    if not device or not device.active:
        raise HTTPException(403,'This phone is not an authorized scanner')
    payload=f'attendance.identify.v1\n{data.request_id}\n{data.timestamp_ms}\n{data.qr_code}\n{data.action}'
    try:
        key=serialization.load_pem_public_key(device.public_key.encode())
        key.verify(base64.b64decode(data.signature,validate=True),payload.encode(),padding.PKCS1v15(),hashes.SHA256())
    except (ValueError,InvalidSignature):
        raise HTTPException(403,'Device signature is invalid')
    if abs(clock.time()*1000-data.timestamp_ms)>90_000:
        raise HTTPException(422,'Enable automatic date and time on this phone, then rescan.')
    value=db.scalar(select(Employee).where(Employee.qr_code==data.qr_code))
    if not value or not value.active:
        raise HTTPException(404,'ID is unknown, replaced, or inactive')
    day=now().astimezone(MANILA).date()
    previous=db.scalar(select(Attendance).where(Attendance.employee_id==value.id,Attendance.work_date==day,Attendance.action==data.action))
    return {'employee':employee_json(value),'existing':attendance_json(previous) if previous and not previous.voided else None}


@app.get('/api/attendance')
def attendance(start: date, end: date, employee_id: str|None=None, user=Depends(admin), db=Depends(get_db)):
    if end < start or (end-start).days > 366:
        raise HTTPException(422, 'Select a date range of at most one year')
    records = select(Attendance).where(Attendance.work_date>=start,Attendance.work_date<=end)
    duties = select(FieldDuty).where(FieldDuty.work_date>=start,FieldDuty.work_date<=end)
    if employee_id:
        records=records.where(Attendance.employee_id==employee_id)
        duties=duties.where(FieldDuty.employee_id==employee_id)
    return {'records':[attendance_json(r) for r in db.scalars(records.order_by(Attendance.work_date,Attendance.recorded_at))],
            'field_duties':[duty_json(d) for d in db.scalars(duties.order_by(FieldDuty.work_date))]}


@app.post('/api/attendance/correct')
def correct(data: CorrectionInput, user=Depends(admin), db=Depends(get_db)):
    write_lock(db)
    employee(db,data.employee_id)
    require_open_month(db,data.work_date)
    stamp = datetime.combine(data.work_date,data.local_time,MANILA).astimezone(timezone.utc)
    if stamp > now() or data.local_time.tzinfo is not None:
        raise HTTPException(422,'Enter a past or current local office time, without a timezone suffix')
    value = db.scalar(select(Attendance).where(Attendance.employee_id==data.employee_id,Attendance.work_date==data.work_date,Attendance.action==data.action))
    if (value.version if value else 0) != data.expected_version:
        raise HTTPException(409,'This entry changed. Refresh before editing.')
    before = attendance_json(value) if value else {}
    if not value:
        value = Attendance(employee_id=data.employee_id,work_date=data.work_date,action=data.action,
                           recorded_at=stamp,original_recorded_at=stamp,source='manual',operator_id=user.id,corrected=True)
        db.add(value)
        flush(db)
    else:
        value.recorded_at=stamp
        value.corrected=True
        value.voided=False
        value.version+=1
    audit(db,user,'attendance.corrected',value.id,data.reason,before,attendance_json(value))
    commit(db)
    return attendance_json(value)


@app.post('/api/attendance/{attendance_id}/void')
def void_attendance(attendance_id: str,data: VersionReasonInput,user=Depends(admin),db=Depends(get_db)):
    write_lock(db)
    value=db.get(Attendance,attendance_id)
    if not value:
        raise HTTPException(404,'Attendance entry not found')
    require_open_month(db,value.work_date)
    if value.version!=data.expected_version or value.voided:
        raise HTTPException(409,'Record changed. Refresh before editing.')
    before=attendance_json(value)
    value.voided=True
    value.corrected=True
    value.version+=1
    audit(db,user,'attendance.voided',value.id,data.reason,before,attendance_json(value))
    commit(db)
    return attendance_json(value)


@app.post('/api/field-duty')
def field_duty(data: DutyInput, user=Depends(admin), db=Depends(get_db)):
    write_lock(db)
    employee(db,data.employee_id)
    require_open_month(db,data.work_date)
    value = db.scalar(select(FieldDuty).where(FieldDuty.employee_id==data.employee_id,FieldDuty.work_date==data.work_date))
    if (value.version if value else 0) != data.expected_version:
        raise HTTPException(409,'Field-duty record changed. Refresh before editing.')
    before = duty_json(value) if value else {}
    if not value:
        value = FieldDuty(employee_id=data.employee_id,work_date=data.work_date,updated_by=user.id)
        db.add(value)
    else:
        value.version+=1
    for key in ('period','location','purpose'):
        setattr(value,key,getattr(data,key))
    value.updated_by=user.id
    flush(db)
    audit(db,user,'field_duty.updated',value.id,data.reason,before,duty_json(value))
    commit(db)
    return duty_json(value)


@app.delete('/api/field-duty/{duty_id}')
def delete_duty(duty_id: str, data: ReasonInput, version: int=Query(ge=1), user=Depends(admin), db=Depends(get_db)):
    write_lock(db)
    value=db.get(FieldDuty,duty_id)
    if not value:
        raise HTTPException(404,'Field-duty record not found')
    require_open_month(db,value.work_date)
    if value.version!=version:
        raise HTTPException(409,'Record changed. Refresh before editing.')
    audit(db,user,'field_duty.removed',value.id,data.reason,before=duty_json(value))
    db.delete(value)
    commit(db)
    return {'ok':True}


@app.get('/api/months/{month}')
def month_status(month: str, user=Depends(admin), db=Depends(get_db)):
    start,end=parse_month(month)
    value=db.get(MonthLock,month)
    return {'month':month,'finalized':bool(value and value.finalized)}


@app.post('/api/months/{month}/{action}')
def lock_month(month: str, action: str, data: ReasonInput, user=Depends(admin), db=Depends(get_db)):
    start,end=parse_month(month)
    if action not in ('finalize','reopen'):
        raise HTTPException(404,'Unknown month action')
    if action=='finalize' and end>=now().astimezone(MANILA).date():
        raise HTTPException(409,'Only completed months can be finalized')
    write_lock(db)
    value=db.get(MonthLock,month)
    if not value:
        value=MonthLock(month=month,updated_by=user.id)
        db.add(value)
    value.finalized=action=='finalize'
    value.updated_by=user.id
    audit(db,user,'month.'+action,month,data.reason,after={'finalized':value.finalized})
    commit(db)
    return {'finalized':value.finalized}


@app.get('/api/reports/{employee_id}/{month}.pdf')
def report(employee_id: str, month: str, user=Depends(admin), db=Depends(get_db)):
    start,end=parse_month(month)
    value=employee(db,employee_id)
    records=list(db.scalars(select(Attendance).where(Attendance.employee_id==value.id,Attendance.work_date>=start,Attendance.work_date<=end,Attendance.voided==False)))
    duties=list(db.scalars(select(FieldDuty).where(FieldDuty.employee_id==value.id,FieldDuty.work_date>=start,FieldDuty.work_date<=end)))
    pdf=form48(value,start.year,start.month,records,duties,db.get(OfficeSettings,1))
    number=re.sub(r'[^A-Za-z0-9_-]','',value.employee_no) or value.id[:8]
    return Response(pdf,media_type='application/pdf',headers={'Content-Disposition':f'inline; filename="dtr-{number}-{month}.pdf"'})


@app.get('/api/settings')
def office_settings(user=Depends(current_user), db=Depends(get_db)):
    value=db.get(OfficeSettings,1)
    return {key:getattr(value,key) for key in OfficeInput.model_fields} | {'timezone':'Asia/Manila'}


@app.put('/api/settings')
def update_settings(data: OfficeInput,user=Depends(admin),db=Depends(get_db)):
    write_lock(db)
    value=db.get(OfficeSettings,1)
    before={key:getattr(value,key) for key in OfficeInput.model_fields}
    for key,val in data.model_dump().items():
        setattr(value,key,val)
    audit(db,user,'settings.updated','office','Office settings updated',before,data.model_dump())
    commit(db)
    return {'ok':True}


@app.get('/api/audit')
def audit_history(limit: int=Query(default=100,ge=1,le=500),subject: str|None=None,user=Depends(admin),db=Depends(get_db)):
    query=select(Audit,User.name).join(User,Audit.actor_id==User.id).order_by(Audit.id.desc()).limit(limit)
    if subject:
        query=query.where(Audit.subject==subject)
    return [{'id':a.id,'at':local(a.at).isoformat(),'actor':name,'kind':a.kind,'subject':a.subject,
             'reason':a.reason,'before':json.loads(a.before),'after':json.loads(a.after)} for a,name in db.execute(query)]


app.mount('/assets', StaticFiles(directory=STATIC), name='assets')


@app.get('/', include_in_schema=False)
def index():
    return FileResponse(STATIC/'index.html')
