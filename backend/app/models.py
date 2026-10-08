import uuid
from datetime import date, datetime, timezone
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


def uid():
    return str(uuid.uuid4())


def now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    auth_version: Mapped[int] = mapped_column(Integer, default=1)


class Employee(Base):
    __tablename__ = 'employees'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    employee_no: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    position: Mapped[str] = mapped_column(String(120), default='')
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    qr_code: Mapped[str] = mapped_column(String(100), unique=True)
    photo: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)


class Device(Base):
    __tablename__ = 'devices'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(100))
    public_key: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    enrolled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    enrolled_by: Mapped[str] = mapped_column(ForeignKey('users.id'))


class Enrollment(Base):
    __tablename__ = 'enrollments'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(ForeignKey('users.id'))


class Attendance(Base):
    __tablename__ = 'attendance'
    __table_args__ = (UniqueConstraint('employee_id', 'work_date', 'action', name='uq_attendance_slot'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    employee_id: Mapped[str] = mapped_column(ForeignKey('employees.id'))
    work_date: Mapped[date] = mapped_column(Date, index=True)
    action: Mapped[str] = mapped_column(String(10))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    original_recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(10))
    operator_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    device_id: Mapped[str | None] = mapped_column(ForeignKey('devices.id'), nullable=True)
    corrected: Mapped[bool] = mapped_column(Boolean, default=False)
    voided: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)


class ScanReceipt(Base):
    __tablename__ = 'scan_receipts'
    request_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey('devices.id'))
    operator_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    payload_hash: Mapped[str] = mapped_column(String(64))
    attendance_id: Mapped[str] = mapped_column(ForeignKey('attendance.id'))
    attendance_version: Mapped[int] = mapped_column(Integer)


class FieldDuty(Base):
    __tablename__ = 'field_duties'
    __table_args__ = (UniqueConstraint('employee_id', 'work_date', name='uq_field_duty'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    employee_id: Mapped[str] = mapped_column(ForeignKey('employees.id'))
    work_date: Mapped[date] = mapped_column(Date, index=True)
    period: Mapped[str] = mapped_column(String(10))
    location: Mapped[str] = mapped_column(String(200))
    purpose: Mapped[str] = mapped_column(String(500))
    updated_by: Mapped[str] = mapped_column(ForeignKey('users.id'))
    version: Mapped[int] = mapped_column(Integer, default=1)


class MonthLock(Base):
    __tablename__ = 'month_locks'
    month: Mapped[str] = mapped_column(String(7), primary_key=True)
    finalized: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_by: Mapped[str] = mapped_column(ForeignKey('users.id'))


class Audit(Base):
    __tablename__ = 'audit'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    actor_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    kind: Mapped[str] = mapped_column(String(50))
    subject: Mapped[str] = mapped_column(String(100))
    reason: Mapped[str] = mapped_column(String(500))
    before: Mapped[str] = mapped_column(Text, default='{}')
    after: Mapped[str] = mapped_column(Text, default='{}')


class OfficeSettings(Base):
    __tablename__ = 'office_settings'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    office_name: Mapped[str] = mapped_column(String(120), default='Office Attendance')
    signatory: Mapped[str] = mapped_column(String(120), default='')
    signatory_title: Mapped[str] = mapped_column(String(120), default='In Charge')
    am_in: Mapped[str] = mapped_column(String(5), default='08:00')
    am_out: Mapped[str] = mapped_column(String(5), default='12:00')
    pm_in: Mapped[str] = mapped_column(String(5), default='13:30')
    pm_out: Mapped[str] = mapped_column(String(5), default='17:00')
