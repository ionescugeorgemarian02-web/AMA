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

    # Sesiuni și autentificare (21.3). Valorile sunt presupuneri documentate în docs/specs/F1.5.md.
    session_idle_minutes: int = Field(default=30, ge=1)
    session_absolute_hours: int = Field(default=12, ge=1)
    session_pending_minutes: int = Field(default=10, ge=1)  # între parolă și al doilea factor
    login_max_failures_account: int = Field(default=5, ge=1)
    login_max_failures_ip: int = Field(default=20, ge=1)
    login_window_minutes: int = Field(default=15, ge=1)

    # Livrare (F1.8): jetonul comun cu deployer-ul. Sub 32 de caractere = rutele interne dezactivate (404).
    deploy_token: SecretStr = Field(default=SecretStr(""))
    # Starea backup-ului, scrisă de serviciul `backup` (F1.9). Nesetat = „necunoscut”.
    backup_status_dir: str = ""

    # Notificări push (F1.7). Fără chei, push este dezactivat. Cheia privată este secret.
    vapid_public_key: str = ""
    vapid_private_key: SecretStr = Field(default=SecretStr(""))
    vapid_subject: str = "mailto:admin@example.invalid"

    # Telegram (F1.10). Fără jeton, chat și secret de webhook, botul este dezactivat.
    telegram_bot_token: SecretStr = Field(default=SecretStr(""))
    telegram_chat_id: str = ""
    telegram_webhook_secret: SecretStr = Field(default=SecretStr(""))

    @property
    def push_activ(self) -> bool:
        return bool(self.vapid_public_key) and len(self.vapid_private_key.get_secret_value()) >= 32

    @property
    def livrare_activa(self) -> bool:
        return len(self.deploy_token.get_secret_value()) >= 32

    @property
    def telegram_activ(self) -> bool:
        return bool(
            self.telegram_bot_token.get_secret_value()
            and self.telegram_chat_id.lstrip("-").isdigit()
            and len(self.telegram_webhook_secret.get_secret_value()) >= 16
        )

    @property
    def cookie_secure(self) -> bool:
        """Cookie-urile sunt `Secure` (și cu prefix `__Host-`) peste tot în afară de dev/test."""
        return self.env not in ("dev", "test")

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
