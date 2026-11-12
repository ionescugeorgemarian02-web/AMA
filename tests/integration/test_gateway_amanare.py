"""F3.3 „Gata când”: la atingerea unei limite simulate, apelurile se amână în loc să eșueze. Amânarea este o
reprogramare durabilă prin motor (nu `sleep` într-un fir); apelantul sincron primește `Amanat(pana_la)`.

SIMULAT: furnizorul fals și un ceas deplasat ca resetarea ferestrei de minut să cadă la câteva secunde de acum."""

import datetime as dt
import time
import uuid

import pytest

from app import gateway
from app.gateway import apel, ceas, cote
from app.gateway.candidat import Candidat
from app.gateway.erori import ApelRefuzat
from app.operare import motor
from app.operare.motor import StareJob
from tests.furnizor_fals import FurnizorFals
from tests.gateway_utile import CeasControlat, FabricaModele, gazda
from tests.integration import fluxuri_gateway as proba

pytestmark = pytest.mark.db
CHEIE = "cheie-de-proba"


def apeleaza(c: Candidat) -> object:
    return apel.apeleaza_pe_model(c, CHEIE, proba.MESAJE, proba.Raspuns)


@pytest.fixture
def raspuns_ok(fals: FurnizorFals) -> FurnizorFals:
    fals.text = '{"eticheta": "ok", "dovezi": [], "incredere": 0.5}'
    return fals


def test_apelantul_sincron_primeste_amanat_cu_momentul_resetarii(
    fabrica_modele: FabricaModele, raspuns_ok: FurnizorFals, ceas_controlat: CeasControlat
) -> None:
    m = fabrica_modele.model(fabrica_modele.furnizor(), cereri_minut=2)
    apeleaza(m)
    apeleaza(m)
    with pytest.raises(gateway.Amanat) as exc:
        apeleaza(m)
    assert exc.value.pana_la == dt.datetime(2026, 11, 12, 12, 1, 1, tzinfo=dt.UTC)
    assert "amânat până la 2026-11-12T12:01:01" in str(exc.value)
    assert len(raspuns_ok.cereri_la(gazda(m))) == 2  # a treia cerere nu a ajuns la furnizor
    ceas_controlat.avanseaza(51)  # fereastra următoare
    apeleaza(m)
    assert len(raspuns_ok.cereri_la(gazda(m))) == 3


def test_un_429_al_furnizorului_amana_apelurile_urmatoare_fara_sa_le_trimita(
    fabrica_modele: FabricaModele, raspuns_ok: FurnizorFals, ceas_controlat: CeasControlat
) -> None:
    m = fabrica_modele.model(
        fabrica_modele.furnizor()
    )  # fără limite în registru: furnizorul e cel care limitează
    raspuns_ok.scenariu(gazda(m), "429", "ok")
    with pytest.raises(gateway.Amanat) as exc:
        apeleaza(m)
    assert exc.value.pana_la == ceas_controlat.t + dt.timedelta(
        seconds=7 + cote.MARJA_RESET_SEC
    )  # retry-after: 7
    with pytest.raises(gateway.Amanat):
        apeleaza(m)
    assert len(raspuns_ok.cereri_la(gazda(m))) == 1  # al doilea apel nu a mai deranjat furnizorul
    ceas_controlat.t = exc.value.pana_la
    apeleaza(m)
    assert len(raspuns_ok.cereri_la(gazda(m))) == 2


def test_antetele_de_la_ultimul_raspuns_pot_opri_apelul_urmator(
    fabrica_modele: FabricaModele, raspuns_ok: FurnizorFals, ceas_controlat: CeasControlat
) -> None:
    m = fabrica_modele.model(fabrica_modele.furnizor(), cereri_minut=1000)  # noi credem că mai avem loc
    raspuns_ok.antete_ok = {
        "x-ratelimit-limit-requests": "1000",
        "x-ratelimit-remaining-requests": "0",
        "x-ratelimit-reset-requests": "20s",
    }
    apeleaza(m)
    with pytest.raises(gateway.Amanat) as exc:
        apeleaza(m)  # furnizorul a spus „0 rămase”: el are dreptate, nu numărătoarea noastră
    assert len(raspuns_ok.cereri_la(gazda(m))) == 1
    assert exc.value.pana_la >= ceas_controlat.t + dt.timedelta(seconds=20)


def test_cererea_care_nu_incape_niciodata_nu_se_amana(
    fabrica_modele: FabricaModele, raspuns_ok: FurnizorFals, ceas_controlat: CeasControlat
) -> None:
    m = fabrica_modele.model(fabrica_modele.furnizor(), tokeni_minut=50)
    with pytest.raises(ApelRefuzat) as exc:
        apeleaza(m)
    assert exc.value.cod == "cerere_prea_mare" and not raspuns_ok.cereri


def test_amanarea_este_o_reprogramare_durabila_prin_motor_nu_un_sleep(
    executor: None,
    fabrica_modele: FabricaModele,
    raspuns_ok: FurnizorFals,
    cheie_proba: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    m = fabrica_modele.model(fabrica_modele.furnizor(), cereri_minut=1)
    # Ceas deplasat: limita ferestrei de minut cade la ~3 s de acum, în timp real.
    real = dt.datetime.now(dt.UTC)
    limita = real.replace(second=0, microsecond=0) + dt.timedelta(hours=1)
    decalaj = (limita - dt.timedelta(seconds=2)) - real
    monkeypatch.setattr(ceas, "_ceas", lambda: dt.datetime.now(dt.UTC) + decalaj)
    mid = str(m.model_id)

    primul = motor.trimite(proba.flux_proba, mid, 1, cheie=f"gw1-{uuid.uuid4().hex}")
    assert motor.asteapta_flux(primul, timeout_sec=15).stare is StareJob.TERMINAT
    assert len(raspuns_ok.cereri_la(gazda(m))) == 1  # cota minutului e consumată

    start = time.monotonic()
    al_doilea_cheie = f"gw2-{uuid.uuid4().hex}"
    al_doilea = motor.trimite(proba.flux_proba, mid, 2, cheie=al_doilea_cheie)
    assert motor.asteapta_flux(al_doilea, timeout_sec=15).stare is StareJob.TERMINAT  # nu a eșuat
    assert len(raspuns_ok.cereri_la(gazda(m))) == 1  # nu a ajuns la furnizor: a fost amânat

    # Jobul reprogramat există deja în motor, pentru momentul resetării (~3 s), cu cheie derivată din amânare.
    reluat_id = f"proba_gw:{mid}:2:{int((limita + dt.timedelta(seconds=1)).timestamp())}"
    stare = motor.stare_flux(reluat_id)
    assert stare is not None and stare.stare in (
        StareJob.AMANAT,
        StareJob.IN_COADA,
        StareJob.IN_LUCRU,
        StareJob.TERMINAT,
    )
    final = motor.asteapta_flux(reluat_id, timeout_sec=20)
    assert final.stare is StareJob.TERMINAT
    assert time.monotonic() - start >= 2.5  # a așteptat resetarea, nu a rulat imediat
    assert len(raspuns_ok.cereri_la(gazda(m))) == 2  # și acum a trecut: un singur apel în plus
