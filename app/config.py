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

    # Motorul de execuție (F2.1–F2.2, 7.5). Biblioteca de workflow-uri stă în aceeași bază, schema `dbos`.
    # `worker_id` trebuie să fie stabil între reporniri: workerul reluat își recuperează joburile după el.
    worker_id: str = Field(default="worker-1", pattern=r"^[a-z0-9][a-z0-9_.-]{0,62}$")
    motor_schema: str = Field(default="dbos", pattern=r"^[a-z][a-z0-9_]{0,40}$")
    motor_versiune: str = Field(
        default="f2", pattern=r"^[A-Za-z0-9_.-]{1,60}$"
    )  # versiunea joburilor (vezi F2.1)
    motor_polling_sec: float = Field(default=1.0, gt=0.0, le=60.0)  # cât de des caută o coadă joburi noi
    motor_pool: int = Field(default=6, ge=2, le=20)  # conexiuni ale bibliotecii (worker)
    worker_oprire_sec: int = Field(default=20, ge=0, le=600)  # cât așteaptă joburile în curs la SIGTERM
    culoare_greu: int = Field(
        default=2, ge=1, le=16
    )  # culoare pentru joburile grele (7.5): câte un job pe culoar
    io_paralel: int = Field(default=24, ge=1, le=200)  # coada de intrări și ieșiri
    invatare_paralel: int = Field(default=1, ge=1, le=8)
    job_timp_maxim_sec: int = Field(default=1800, ge=1)  # fără niciun pas încheiat: job blocat (watchdog)
    # Watchdog (22.3): bătăi de inimă, scanarea joburilor, pragurile de alertă.
    watchdog_bataie_sec: float = Field(default=15.0, gt=0.0)
    watchdog_scanare_sec: float = Field(default=30.0, gt=0.0)
    worker_timeout_sec: float = Field(default=90.0, gt=0.0)  # fără bătaie atâta timp = fără semn de viață
    watchdog_prag_reporniri: int = Field(default=3, ge=1)  # a treia repornire într-o oră anunță
    watchdog_fereastra_min: int = Field(default=60, ge=1)
    erori_prag_crestere: int = Field(default=5, ge=2)  # câte joburi deschise cu aceeași cauză urcă alerta
    programare_polling_sec: float = Field(default=5.0, gt=0.0, le=60.0)  # cât de des caută programări noi
    # Producția livrabilelor (F2.3–F2.4, 7.3): limitele anti-buclă (valori de pornire).
    productie_runde_reparatie: int = Field(default=2, ge=0)  # a treia rundă merge la om
    productie_predari_max: int = Field(default=12, ge=1)  # intrări în stări de lucru ale componentelor
    productie_buget_apeluri_llm: int = Field(default=40, ge=1)  # per livrabil
    productie_buget_timp_sec: int = Field(default=3600, ge=1)  # timp de lucru acumulat, per livrabil
    intrerupator_prag_esec: float = Field(
        default=0.30, gt=0.0, le=1.0
    )  # rata de eșec peste care producția se oprește
    intrerupator_fereastra_min: int = Field(default=60, ge=1)
    intrerupator_volum_min: int = Field(
        default=10, ge=1
    )  # sub atâtea rezultate în fereastră nu se judecă rata
    # Cererile de aprobare (F2.8, 19.4): termen de 48 h, reamintire cu 24 h înainte de termen.
    aprobare_termen_ore: int = Field(default=48, ge=1)
    aprobare_reamintire_ore: int = Field(default=24, ge=1)
    # Autonomia (F2.10, 7.4): ponderea livrabilelor care merg totuși la om la L2 (10–20%) și la L3+ (5–10%).
    autonomie_esantion_l2: float = Field(default=0.15, ge=0.0, le=1.0)
    autonomie_esantion_l3: float = Field(default=0.075, ge=0.0, le=1.0)
    # Canale cu consimțământ per postare: rămân la cel mult L1 (TikTok, 7.4). Separate prin virgulă.
    canale_consimtamant: str = "tiktok"
    # Executorul de efecte externe (F2.5, 7.5): reîncercări cu pauză crescătoare, plasa de siguranță a
    # „tic”-ului.
    efecte_reincercari: int = Field(default=3, ge=0, le=10)
    efecte_pauza_sec: float = Field(default=2.0, gt=0.0, le=600.0)
    efecte_redistribuire_sec: int = Field(
        default=600, ge=1
    )  # un efect în așteptare fără job viu se repune în coadă
    # Gateway-ul de modele (F3.4, 7.5): reîncercări la erori de server, întrerupătorul pe furnizor
    # (valori de pornire).
    gateway_reincercari: int = Field(default=3, ge=0, le=10)  # reîncercări pe același model, apoi alt model
    gateway_pauza_sec: float = Field(default=1.0, gt=0.0, le=60.0)  # prima pauză; apoi × factorul
    gateway_factor_pauza: float = Field(default=2.0, ge=1.0, le=10.0)
    gateway_intrerupator_prag: int = Field(default=3, ge=1)  # eșecuri consecutive care scot furnizorul
    gateway_intrerupator_pauza_sec: float = Field(default=120.0, gt=0.0)  # cât stă scos, până la prima probă
    gateway_continut_zile: int = Field(
        default=30, ge=1, le=365
    )  # cât se păstrează conținutul apelurilor (20.4)
    # Bugetele pe client (F3.8, 8.5): ora UTC la care începe „ziua” bugetului (și luna, în prima zi a lunii).
    gateway_buget_reset_ora: int = Field(default=0, ge=0, le=23)
    # Planificatorul de capacitate (F3.11, A4): valori de pornire, nemăsurate.
    planificare_termen_apropiat_ore: int = Field(
        default=48, ge=24, le=720
    )  # sub acest termen un livrabil nu se amână
    planificare_orizont_zile: int = Field(
        default=14, ge=1, le=365
    )  # livrabilele cu termen mai îndepărtat nu intră în plan
    planificare_cpu_factor: float = Field(
        default=0.6, gt=0.0, le=1.0
    )  # cât din timpul culoarelor grele se poate planifica
    # Media pe disc (ADR-15) și colectorul de surse (F4.2, 12.3). User-Agent-ul identifică onest platforma;
    # adresa de contact reală se pune în configurarea serverului (NEVERIFICAT: domeniul agenției, F0.1).
    media_dir: str = "/var/lib/ama/media"
    colector_user_agent: str = Field(
        default=(
            "AMA-Colector/1.0 (robot de citit pagini pentru clientii agentiei de marketing; "
            "contact: setati AMA_COLECTOR_USER_AGENT)"
        ),
        pattern=r"^[\x20-\x7e]{10,300}$",  # antet HTTP: ASCII vizibil
    )
    # Doar în mediul `test`: module cu fluxuri de probă, încărcate de worker (separate prin virgulă).
    worker_module_test: str = ""

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
