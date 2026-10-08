from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    database_url: str
    jwt_secret: str
    cookie_secure: bool = True
    session_hours: int = 8

    @field_validator('jwt_secret')
    @classmethod
    def strong_secret(cls, value: str) -> str:
        if len(value) < 32 or value.upper().startswith(('REPLACE', 'CHANGE_ME')):
            raise ValueError('JWT_SECRET must be a real generated secret containing at least 32 characters; template placeholders are not allowed')
        return value


@lru_cache
def settings() -> Settings:
    return Settings()
