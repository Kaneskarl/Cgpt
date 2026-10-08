from datetime import date, time
from typing import Literal
from pydantic import BaseModel, Field, model_validator, field_validator

Action = Literal['am_in', 'am_out', 'pm_in', 'pm_out']


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)
    client: Literal['web', 'scanner'] = 'web'


class EmployeeInput(BaseModel):
    employee_no: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    position: str = Field(default='', max_length=120)
    active: bool = True

    @field_validator('employee_no', 'name', 'position')
    @classmethod
    def strip_text(cls, value):
        return value.strip()

    @model_validator(mode='after')
    def nonblank(self):
        if not self.name or not self.employee_no:
            raise ValueError('Name and employee number cannot be blank')
        return self


class AccountInput(BaseModel):
    username: str = Field(pattern=r'^[a-zA-Z0-9_.-]{3,80}$')
    name: str = Field(min_length=1, max_length=120)
    role: Literal['admin', 'operator']
    password: str = Field(min_length=12, max_length=256)


class AccountUpdate(BaseModel):
    active: bool
    password: str | None = Field(default=None, min_length=12, max_length=256)
    reason: str = Field(default='Account access updated', min_length=5, max_length=500)


class EnrollInput(BaseModel):
    code: str = Field(min_length=10, max_length=200)
    name: str = Field(min_length=1, max_length=100)
    public_key: str = Field(min_length=100, max_length=2000)


class ScanInput(BaseModel):
    request_id: str = Field(pattern=r'^[0-9a-fA-F-]{36}$')
    timestamp_ms: int
    qr_code: str = Field(min_length=10, max_length=100)
    action: Action
    device_id: str = Field(max_length=36)
    signature: str = Field(max_length=1000)


class CorrectionInput(BaseModel):
    employee_id: str
    work_date: date
    action: Action
    local_time: time
    reason: str = Field(min_length=5, max_length=500)
    expected_version: int = Field(ge=0)


class DutyInput(BaseModel):
    employee_id: str
    work_date: date
    period: Literal['full_day', 'morning', 'afternoon']
    location: str = Field(min_length=1, max_length=200)
    purpose: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=5, max_length=500)
    expected_version: int = Field(ge=0)


class ReasonInput(BaseModel):
    reason: str = Field(min_length=5, max_length=500)


class VersionReasonInput(ReasonInput):
    expected_version: int = Field(ge=1)


class OfficeInput(BaseModel):
    office_name: str = Field(min_length=1, max_length=120)
    signatory: str = Field(max_length=120)
    signatory_title: str = Field(max_length=120)
    am_in: str = Field(pattern=r'^\d{2}:\d{2}$')
    am_out: str = Field(pattern=r'^\d{2}:\d{2}$')
    pm_in: str = Field(pattern=r'^\d{2}:\d{2}$')
    pm_out: str = Field(pattern=r'^\d{2}:\d{2}$')

    @model_validator(mode='after')
    def schedule(self):
        values = [time.fromisoformat(getattr(self, k)) for k in ['am_in', 'am_out', 'pm_in', 'pm_out']]
        if not all(a < b for a, b in zip(values, values[1:])):
            raise ValueError('Schedule must be in chronological order')
        return self
