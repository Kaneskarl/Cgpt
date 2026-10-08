import secrets
from datetime import datetime, timedelta, timezone
import jwt
from fastapi import Depends, HTTPException, Request
from pwdlib import PasswordHash
from sqlalchemy import select
from .config import settings
from .db import get_db
from .models import User

passwords = PasswordHash.recommended()
# Equal-cost verification for unknown accounts.
dummy_hash = passwords.hash(secrets.token_urlsafe(32))


def token_for(user):
    csrf = secrets.token_urlsafe(24)
    token = jwt.encode({'sub': user.id, 'ver': user.auth_version, 'csrf': csrf,
                        'exp': datetime.now(timezone.utc) + timedelta(hours=settings().session_hours),
                        'iat': datetime.now(timezone.utc), 'aud': 'attendance', 'iss': 'office-attendance'},
                       settings().jwt_secret, algorithm='HS256')
    return token, csrf


def current_user(request: Request, db=Depends(get_db)):
    authorization = request.headers.get('authorization', '')
    bearer = authorization.startswith('Bearer ')
    token = authorization[7:] if bearer else request.cookies.get('attendance_session')
    if not token:
        raise HTTPException(401, 'Please log in')
    try:
        claims = jwt.decode(token, settings().jwt_secret, algorithms=['HS256'], audience='attendance', issuer='office-attendance')
    except jwt.PyJWTError:
        raise HTTPException(401, 'Session expired; please log in again')
    user = db.get(User, claims['sub'])
    if not user or not user.active or claims.get('ver') != user.auth_version:
        raise HTTPException(401, 'Account access has changed; please log in again')
    if not bearer and request.method not in ('GET', 'HEAD', 'OPTIONS'):
        if not secrets.compare_digest(request.headers.get('x-csrf-token', ''), claims.get('csrf', '')):
            raise HTTPException(403, 'Invalid request verification token')
    request.state.csrf = claims['csrf']
    return user


def admin(user=Depends(current_user)):
    if user.role != 'admin':
        raise HTTPException(403, 'Administrator access required')
    return user


def operator(user=Depends(current_user)):
    if user.role != 'operator':
        raise HTTPException(403, 'Operator access required')
    return user
