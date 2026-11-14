"""F8.9 — testul de capacitate. „Gata când”: timpul per video și consumul de memorie sunt măsurate, iar bugetele sunt
confirmate. Zece video pe culoarele grele (două, ca pe VPS), prin motorul durabil, cu producția de text în mers
(validarea deterministă a textelor, pe firul testului). Mașina locală nu e VPS-ul: cifrele de pe VPS, la migrare."""

# ruff: noqa: F811
import threading
import time
import uuid
from collections.abc import Callable

import pytest

from app.db import sesiune_tenant
from app.media import capacitate, ffmpeg, fluxuri, montaj
from app.media.modele import Randare
from app.operare import motor
from app.validare import independent
from tests.integration.utile_productie import fabrica_clienti, tenant  # noqa: F401
from tests.media_utile import SCRIPT, lista_simpla

pytestmark = [pytest.mark.db, pytest.mark.skipif(not ffmpeg.disponibil(), reason="ffmpeg lipsește")]
TEXT = "Cafeneaua Zorilor prăjește cafea în fiecare marți, la Brașov, în loturi mici. Comandă de pe site."


def test_zece_video_pe_culoarele_grele_cu_textul_in_mers(
    tenant: uuid.UUID, porneste_executor: Callable[..., None]
) -> None:
    porneste_executor(culoare_greu=2)
    ids = []
    with sesiune_tenant(tenant) as db:
        for i in range(10):
            script = {**SCRIPT, "hook": f"Varianta {i + 1}: știi de ce cafeaua ta e amară?"}
            ids.append(montaj.pregateste(db, tenant, lista_simpla(db, tenant, "AB"[i % 2], script=script)).id)
    joburi = [fluxuri.trimite(tenant, r) for r in ids]
    texte: list[float] = []
    gata = threading.Event()

    def productie_text() -> None:
        while not gata.is_set():
            t0 = time.monotonic()
            with sesiune_tenant(tenant) as db:
                independent.evalueaza_text(db, tenant, tip="postare", canal="facebook", text=TEXT,
                                           coduri=["G1", "G10"])  # fmt: skip
            texte.append(time.monotonic() - t0)
            time.sleep(0.05)  # un flux de texte, nu o buclă care ține procesorul

    fir = threading.Thread(target=productie_text)
    fir.start()
    try:
        for j in joburi:
            assert motor.asteapta_flux(j, timeout_sec=110).stare == motor.StareJob.TERMINAT
    finally:
        gata.set()
        fir.join()
    with sesiune_tenant(tenant) as db:
        randari = [db.get(Randare, i) for i in ids]
        assert all(r is not None and r.stare == "gata" for r in randari)
        rap = capacitate.raport([r for r in randari if r is not None])
    print("\n[F8.9] " + rap.text() + f"; text: {len(texte)} evaluări, max {max(texte):.2f} s")
    assert rap.videouri == 10 and rap.paralel_max <= 2  # câte un job pe culoar
    assert rap.in_buget, rap.text()
    assert texte and max(texte) < 5.0  # textul nu se oprește cât randează culoarele grele
