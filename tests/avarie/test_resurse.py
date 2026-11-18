"""F15.1, docs/25 §25.3: discul la 85%, memoria la limită, workerul oprit în timpul unei randări.

Măsurarea discului și a memoriei e SIMULATĂ (`resurse.seteaza_masurare`); randările sunt reale (ffmpeg), pe
executorul din procesul testului.
"""

import datetime as dt
import os
import time
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from app.config import get_settings
from app.db import sesiune_tenant
from app.media import ffmpeg, fluxuri, montaj
from app.media.modele import Randare
from app.operare import alerte, motor, resurse
from app.operare.motor import Coada
from tests.integration import fluxuri_cozi as cozi
from tests.media_utile import lista_simpla

pytestmark = pytest.mark.db
cu_ffmpeg = pytest.mark.skipif(not ffmpeg.disponibil(), reason="ffmpeg lipsește")


@pytest.fixture(autouse=True)
def _masurare_reala_la_final() -> Iterator[None]:
    yield
    resurse.seteaza_masurare(None)


@pytest.fixture
def alerte_trimise(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    lista: list[tuple[str, str]] = []
    monkeypatch.setattr(alerte, "trimite", lambda nivel, titlu, text: lista.append((nivel, titlu)) or True)
    return lista


def _simuleaza(disc: float, memorie: float = 40.0) -> None:
    resurse.seteaza_masurare(lambda: resurse.Masurare(disc_pct=disc, memorie_pct=memorie))


def _vechi(p: Path) -> Path:
    t = time.time() - 2 * 3600
    os.utime(p, (t, t))
    return p


def test_discul_la_85_curata_partialele_si_alerteaza_o_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, alerte_trimise: list[tuple[str, str]]
) -> None:
    monkeypatch.setenv("AMA_MEDIA_DIR", str(tmp_path))
    get_settings.cache_clear()
    lucru = tmp_path / resurse.DIR_LUCRU / "randare-veche"
    lucru.mkdir(parents=True)
    (lucru / "bucata.mp4").write_bytes(b"x")
    _vechi(lucru)
    (tmp_path / "client" / "active").mkdir(parents=True)
    tmp_vechi = tmp_path / "client" / "active" / ".a.mp4.1.ab.tmp"
    tmp_vechi.write_bytes(b"x")
    _vechi(tmp_vechi)
    tmp_nou = tmp_path / "client" / "active" / ".b.mp4.1.cd.tmp"
    tmp_nou.write_bytes(b"x")  # o scriere în curs: rămâne
    final = tmp_path / "client" / "active" / "c.mp4"
    final.write_bytes(b"x")

    _simuleaza(84.0)
    assert resurse.verifica()["sterse"] == 0 and alerte_trimise == []
    _simuleaza(85.0)
    assert resurse.verifica()["sterse"] == 2
    assert not lucru.exists() and not tmp_vechi.exists() and tmp_nou.exists() and final.exists()
    assert resurse.permite_greu() == (False, "disc")
    resurse.verifica()
    assert [n for n, _ in alerte_trimise] == ["critic"], "o singură alertă pe trecerea peste prag"
    _simuleaza(60.0)
    resurse.verifica()
    assert resurse.permite_greu() == (True, "")
    _simuleaza(91.0)
    resurse.verifica()
    assert [n for n, _ in alerte_trimise] == ["critic", "critic"]
    get_settings.cache_clear()


def _randare(tenant: uuid.UUID) -> uuid.UUID:
    with sesiune_tenant(tenant) as db:
        return montaj.pregateste(db, tenant, lista_simpla(db, tenant, "A")).id


def _stare(tenant: uuid.UUID, rid: uuid.UUID) -> str:
    with sesiune_tenant(tenant) as db:
        r = db.get(Randare, rid)
        assert r is not None
        return r.stare


def _asteapta_stare(tenant: uuid.UUID, rid: uuid.UUID, *stari: str, timeout: float = 120) -> str:
    limita = time.monotonic() + timeout
    while time.monotonic() < limita:
        if (s := _stare(tenant, rid)) in stari:
            return s
        time.sleep(0.2)
    raise AssertionError(f"randarea a rămas {_stare(tenant, rid)}")


@cu_ffmpeg
def test_cu_discul_plin_randarea_noua_se_amana_si_porneste_dupa_eliberare(
    tenant: uuid.UUID, porneste_executor: Callable[..., None], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(resurse, "AMANARE_GREU", dt.timedelta(seconds=1))
    porneste_executor()
    rid = _randare(tenant)
    _simuleaza(90.0)
    job = fluxuri.trimite(tenant, rid)
    assert motor.asteapta_flux(job, timeout_sec=30).stare is motor.StareJob.TERMINAT
    assert _stare(tenant, rid) == "in_lucru", "randarea nu a pornit"
    _simuleaza(50.0)  # discul eliberat: jobul reprogramat pornește singur
    assert _asteapta_stare(tenant, rid, "gata", "respins") == "gata"


@cu_ffmpeg
def test_memoria_la_limita_amana_doar_joburile_grele(
    tenant: uuid.UUID, porneste_executor: Callable[..., None], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(resurse, "AMANARE_GREU", dt.timedelta(minutes=30))
    porneste_executor()
    cozi.reseteaza()
    _simuleaza(40.0, memorie=95.0)
    assert resurse.permite_greu() == (False, "memorie")
    rid = _randare(tenant)
    job = fluxuri.trimite(tenant, rid)
    assert motor.asteapta_flux(job, timeout_sec=30).stare is motor.StareJob.TERMINAT
    # serviciile permanente (cozile io și urgent) lucrează în continuare
    for c in (Coada.IO, Coada.URGENT):
        j = motor.trimite(cozi.job, f"permanent-{c.value}", coada=c, cheie=f"avarie-mem-{c.value}")
        assert motor.asteapta_flux(j, timeout_sec=20).stare is motor.StareJob.TERMINAT
    assert _stare(tenant, rid) == "in_lucru"
    cozi.reseteaza()


@cu_ffmpeg
def test_randarea_reluata_sterge_fisierele_partiale_si_termina_o_data(
    tenant: uuid.UUID, porneste_executor: Callable[..., None]
) -> None:
    porneste_executor()
    rid = _randare(tenant)
    # starea lăsată de un worker omorât în mijlocul randării: directorul de lucru cu bucăți parțiale
    ramas = Path(get_settings().media_dir) / resurse.DIR_LUCRU / f"randare-{rid}"
    ramas.mkdir(parents=True, exist_ok=True)
    (ramas / "bucata-partiala.mp4").write_bytes(b"\x00" * 1024)
    job = fluxuri.trimite(tenant, rid)
    assert motor.asteapta_flux(job, timeout_sec=120).stare is motor.StareJob.TERMINAT
    assert _stare(tenant, rid) == "gata"
    assert not ramas.exists(), "fișierele parțiale se curăță"
    # a doua livrare a aceluiași job (reluarea după cădere) nu randează din nou
    assert fluxuri._randeaza(str(tenant), str(rid)) == "gata"
