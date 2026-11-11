"""Configurarea aplicației. Vine exclusiv din variabile de mediu (prefix AMA_)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AMA_", env_file=None, extra="ignore")

    env: Literal["dev", "test", "staging", "prod"] = "dev"
    log_level: str = "INFO"
    version: str = "dev"  # setată de CI la construirea imaginii

    # Baza de date. Aplicația se conectează cu un rol fără drept de a ocoli izolarea pe client;
    # migrările folosesc rolul proprietar.
    database_url: str = "postgresql+psycopg://ama_app@localhost:5432/ama"
    database_owner_url: str = "postgresql+psycopg://ama_owner@localhost:5432/ama"

    # Secrete. Fără valori implicite utilizabile în producție: validate la pornire.
    secret_key: SecretStr = Field(default=SecretStr(""))
    master_key: SecretStr = Field(default=SecretStr(""))  # criptează secretele ținute în bază

    base_url: str = "http://localhost:8000"

    def require_secrets(self) -> None:
        """Refuză pornirea în staging/producție fără secrete setate."""
        if self.env in ("staging", "prod"):
            missing = [
                name
                for name in ("secret_key", "master_key")
                if len(getattr(self, name).get_secret_value()) < 32
            ]
            if missing:
                raise RuntimeError(f"Secrete lipsă sau prea scurte: {', '.join(missing)}")


@lru_cache
def get_settings() -> Settings:
    return Settings()
