"""F3.4 — rutarea și lanțurile de rezervă pe Postgres real, cu furnizorul fals: reacțiile din 7.5, întrerupătorul,
profilurile din 8.2. „Gata când”: cu un furnizor oprit, munca trece pe următorul, iar o sarcină de strategie se amână,
nu se degradează."""

import datetime as dt
import uuid
from typing import Any

import pytest
from sqlalchemy import Engine, text

from app import gateway
from app.db import sesiune_agentie, sesiune_tenant
from app.gateway import apel
from app.gateway.apel import ContextApel, Rezultat
from app.gateway.tipuri import Mesaj
from app.operare import opriri
from app.operare.motor import Prioritate
from tests.furnizor_fals import FurnizorFals
from tests.gateway_utile import CeasControlat, FabricaModele, gazda, sanatate
from tests.integration import fluxuri_gateway as proba
from tests.integration.utile_productie import AnunturiFalse

pytestmark = pytest.mark.db
T2 = "T2"


@pytest.fixture(autouse=True)
def _mediu(cheie_proba: str, ceas_controlat: CeasControlat, fals: FurnizorFals) -> None:
    fals.text = '{"eticheta": "ok", "dovezi": ["d"], "incredere": 0.7}'


def apeleaza(tenant: uuid.UUID, profil: str, **kw: Any) -> Rezultat:
    with sesiune_tenant(tenant) as db:
        ctx = ContextApel(
            db=db, tenant_id=tenant, profil=profil, mesaje=proba.MESAJE, schema=proba.Raspuns,
            componenta="test", **kw,
        )  # fmt: skip
        return apel.ruleaza(ctx)


class Doi:
    """Doi furnizori, câte un model T2 fiecare, într-un lanț `a` → `b`."""

    def __init__(self, f: FabricaModele, **model: Any) -> None:
        self.fa = f.furnizor()
        self.fb = f.furnizor()
        self.a = f.model(self.fa, identificator="ma", **model)
        self.b = f.model(self.fb, identificator="mb", **model)
        self.profil = f.profil([self.a.cod, self.b.cod])


@pytest.fixture
def doi(fabrica_modele: FabricaModele) -> Doi:
    return Doi(fabrica_modele)


def test_primul_model_din_lant_raspunde_cu_tokeni_durata_si_pret_umbra(
    tenant: uuid.UUID, doi: Doi, fals: FurnizorFals
) -> None:
    fals.tokeni = (1000, 500)
    r = apeleaza(tenant, doi.profil)
    assert r.model == doi.a.cod and r.furnizor == doi.a.furnizor and r.nivel == T2
    assert (r.tokeni_intrare, r.tokeni_iesire, r.reparatii) == (1000, 500, 0)
    assert str(r.pret_umbra) == "0.001250"  # 1000 × 0,5 + 500 × 1,5 USD la 1 mil.
    assert r.motiv_alegere == "primul model eligibil din lanț" and not r.degradat
    assert [(i.model, i.rezultat) for i in r.incercari] == [(doi.a.cod, "ok")]
    assert len(fals.cereri_la(gazda(doi.a))) == 1 and not fals.cereri_la(gazda(doi.b))


@pytest.mark.parametrize("stare", ["inactiv", "pauza"])
def test_cu_un_furnizor_oprit_munca_trece_pe_urmatorul(
    tenant: uuid.UUID, doi: Doi, fals: FurnizorFals, admin_engine: Engine, stare: str
) -> None:
    with admin_engine.begin() as c:
        c.execute(
            text("UPDATE gateway_furnizori SET stare = :s WHERE cod = :c"), {"s": stare, "c": doi.a.furnizor}
        )
    r = apeleaza(tenant, doi.profil)
    assert r.model == doi.b.cod and not fals.cereri_la(gazda(doi.a))
    assert (
        r.motiv_alegere == "primul model eligibil din lanț"
    )  # a doua nu e „rezervă”: prima nu era eligibilă


def test_eroare_de_server_trei_reincercari_cu_pauza_crescatoare_apoi_alt_furnizor(
    tenant: uuid.UUID, doi: Doi, fals: FurnizorFals, ceas_controlat: CeasControlat
) -> None:
    fals.scenariu(gazda(doi.a), permanent="5xx")
    r = apeleaza(tenant, doi.profil)
    assert r.model == doi.b.cod
    assert len(fals.cereri_la(gazda(doi.a))) == 4  # prima cerere + 3 reîncercări
    assert ceas_controlat.pauze == [1.0, 2.0, 4.0]  # pauză crescătoare
    assert [i.rezultat for i in r.incercari] == ["server", "ok"]
    assert "modelele dinaintea lui au eșuat" in r.motiv_alegere


def test_intrerupatorul_scoate_furnizorul_si_il_reincearca_dupa_o_pauza(
    tenant: uuid.UUID, doi: Doi, fals: FurnizorFals, ceas_controlat: CeasControlat, admin_engine: Engine
) -> None:
    fals.scenariu(gazda(doi.a), permanent="5xx")
    apeleaza(tenant, doi.profil)
    stare, erori, pana = sanatate(admin_engine, doi.fa)
    assert stare == "activ" and erori == 4 and pana == ceas_controlat.t + dt.timedelta(seconds=120)
    n = len(fals.cereri_la(gazda(doi.a)))
    assert apeleaza(tenant, doi.profil).model == doi.b.cod
    assert len(fals.cereri_la(gazda(doi.a))) == n  # scos: nicio cerere nouă către el
    # după pauză, prima cerere e o probă; furnizorul s-a vindecat: se închide și lanțul redevine cel normal
    ceas_controlat.avanseaza(121)
    fals.scenariu(gazda(doi.a))
    assert apeleaza(tenant, doi.profil).model == doi.a.cod
    assert sanatate(admin_engine, doi.fa)[1:] == (0, None)


def test_proba_esuata_dupa_pauza_redeschide_intrerupatorul(
    tenant: uuid.UUID, doi: Doi, fals: FurnizorFals, ceas_controlat: CeasControlat, admin_engine: Engine
) -> None:
    fals.scenariu(gazda(doi.a), permanent="5xx")
    apeleaza(tenant, doi.profil)
    ceas_controlat.avanseaza(121)
    assert apeleaza(tenant, doi.profil).model == doi.b.cod
    pana = sanatate(admin_engine, doi.fa)[2]
    assert pana == ceas_controlat.t + dt.timedelta(seconds=120)  # redeschis pentru o pauză întreagă


def test_429_trece_pe_alt_furnizor_si_modelul_ramane_blocat_pana_la_reset(
    tenant: uuid.UUID, doi: Doi, fals: FurnizorFals, ceas_controlat: CeasControlat
) -> None:
    fals.scenariu(gazda(doi.a), "429")
    r = apeleaza(tenant, doi.profil)
    assert r.model == doi.b.cod and [i.rezultat for i in r.incercari] == ["limita", "ok"]
    apeleaza(tenant, doi.profil)
    assert len(fals.cereri_la(gazda(doi.a))) == 1  # blocat: nu mai e deranjat
    ceas_controlat.avanseaza(9)  # retry-after: 7 s (+1 s marjă)
    assert apeleaza(tenant, doi.profil).model == doi.a.cod


def test_iesire_in_afara_schemei_o_reparatie_apoi_alt_model(
    tenant: uuid.UUID, doi: Doi, fals: FurnizorFals
) -> None:
    fals.scenariu(gazda(doi.a), "schema_gresita", "schema_gresita", "ok")
    fals.tokeni = (100, 10)
    r = apeleaza(tenant, doi.profil)
    assert len(fals.cereri_la(gazda(doi.a))) == 2  # cererea + exact o reparație
    assert r.model == doi.b.cod and r.reparatii == 0
    assert [i.rezultat for i in r.incercari] == ["iesire_invalida", "ok"]
    assert "eticheta" in r.incercari[0].detaliu  # ce câmp era greșit
    assert (r.tokeni_intrare, r.tokeni_iesire) == (300, 30)  # și încercarea eșuată s-a plătit


def test_reparatia_reusita_ramane_pe_acelasi_model(tenant: uuid.UUID, doi: Doi, fals: FurnizorFals) -> None:
    fals.scenariu(gazda(doi.a), "json_invalid", "ok")
    r = apeleaza(tenant, doi.profil)
    assert r.model == doi.a.cod and r.reparatii == 1 and [i.rezultat for i in r.incercari] == ["reparat"]
    assert not fals.cereri_la(gazda(doi.b))


def test_autentificare_pune_furnizorul_pe_pauza_cu_alerta_si_audit(
    tenant: uuid.UUID,
    doi: Doi,
    fals: FurnizorFals,
    anunturi: AnunturiFalse,
    admin_engine: Engine,
) -> None:
    fals.scenariu(gazda(doi.a), permanent="401")
    r = apeleaza(tenant, doi.profil)
    assert r.model == doi.b.cod and len(fals.cereri_la(gazda(doi.a))) == 1  # fără reîncercări pe 401
    assert sanatate(admin_engine, doi.fa)[0] == "pauza"
    assert (
        len(anunturi.trimise) == 1
        and "pauză" in anunturi.trimise[0][1]
        and doi.a.furnizor in anunturi.trimise[0][2]
    )
    apeleaza(tenant, doi.profil)
    assert (
        len(fals.cereri_la(gazda(doi.a))) == 1 and len(anunturi.trimise) == 1
    )  # nici cerere nouă, nici alertă nouă
    with admin_engine.connect() as c:
        n = c.execute(
            text(
                "SELECT count(*) FROM jurnal_audit WHERE actiune = 'gateway.furnizor_pauza' AND obiect_id = :c"
            ),
            {"c": doi.a.furnizor},
        ).scalar_one()
        assert n == 1
    # un om îl reactivează (cheia e configurată, termenii permit): revine în lanț
    fals.scenariu(gazda(doi.a))
    with sesiune_agentie() as db:
        gateway.activeaza(db, doi.fa, utilizator_id=None)
    assert apeleaza(tenant, doi.profil).model == doi.a.cod


def test_strategia_se_amana_nu_se_degradeaza(
    tenant: uuid.UUID, fabrica_modele: FabricaModele, fals: FurnizorFals, ceas_controlat: CeasControlat
) -> None:
    f1, f2, f3 = fabrica_modele.furnizor(), fabrica_modele.furnizor(), fabrica_modele.furnizor()
    s1 = fabrica_modele.model(f1, identificator="s1", nivel="T3")
    s2 = fabrica_modele.model(f2, identificator="s2", nivel="T3")
    mic = fabrica_modele.model(f3, identificator="mic", nivel="T1")  # activ, disponibil, dar mai slab
    profil = fabrica_modele.profil([s1.cod, s2.cod, mic.cod], nivel_min="T3", la_epuizare="amana")
    fals.scenariu(gazda(s1), permanent="5xx")
    fals.scenariu(gazda(s2), permanent="5xx")
    with pytest.raises(gateway.Amanat) as exc:
        apeleaza(tenant, profil)
    assert exc.value.pana_la == ceas_controlat.t + dt.timedelta(
        seconds=120
    )  # până se redeschide întrerupătorul
    assert not fals.cereri_la(gazda(mic))  # niciodată un model mai slab
    # cu furnizorii sănătoși din nou, aceeași sarcină se face pe modelul bun
    ceas_controlat.avanseaza(121)
    fals.scenariu(gazda(s1))
    assert apeleaza(tenant, profil).model == s1.cod


def test_strategia_se_amana_si_cand_cota_e_epuizata_la_toti(
    tenant: uuid.UUID, fabrica_modele: FabricaModele, fals: FurnizorFals, ceas_controlat: CeasControlat
) -> None:
    s1 = fabrica_modele.model(fabrica_modele.furnizor(), identificator="s1", nivel="T3", cereri_minut=1)
    s2 = fabrica_modele.model(fabrica_modele.furnizor(), identificator="s2", nivel="T3", cereri_zi=1000)
    profil = fabrica_modele.profil([s1.cod, s2.cod], nivel_min="T3")
    assert apeleaza(tenant, profil).model == s1.cod
    assert apeleaza(tenant, profil).model == s2.cod  # prima fără cotă: urmează a doua
    fals.scenariu(gazda(s2), "429")
    with pytest.raises(gateway.Amanat) as exc:
        apeleaza(tenant, profil)
    # cel mai apropiat moment: s2 după retry-after (7 s + 1 s), nu s1 la minutul nou
    assert exc.value.pana_la == ceas_controlat.t + dt.timedelta(seconds=8)


def test_fara_niciun_furnizor_activ_apelul_se_amana(
    tenant: uuid.UUID, doi: Doi, admin_engine: Engine, ceas_controlat: CeasControlat
) -> None:
    with admin_engine.begin() as c:
        c.execute(
            text("UPDATE gateway_furnizori SET stare = 'inactiv' WHERE cod = ANY(:c)"),
            {"c": [doi.a.furnizor, doi.b.furnizor]},
        )
    with pytest.raises(gateway.Amanat) as exc:
        apeleaza(tenant, doi.profil)
    assert exc.value.pana_la == ceas_controlat.t + dt.timedelta(seconds=300)


def test_clasificarea_degradeaza_la_modelul_local_cu_marcaj(
    tenant: uuid.UUID, fabrica_modele: FabricaModele, fals: FurnizorFals
) -> None:
    mic = fabrica_modele.model(fabrica_modele.furnizor(), identificator="mic", nivel="T1")
    local = fabrica_modele.model(fabrica_modele.furnizor(), identificator="local", nivel="local")
    p_cu = fabrica_modele.profil(
        [mic.cod],
        nivel_min="T1",
        la_epuizare="degradeaza",
        lant_degradare=["nivel:local"],
        verificare_in_plus=True,
    )
    p_fara = fabrica_modele.profil(
        [mic.cod], nivel_min="T1", la_epuizare="degradeaza", lant_degradare=["nivel:local"]
    )
    fals.scenariu(gazda(mic), permanent="5xx")
    r = apeleaza(tenant, p_cu)
    assert r.model == local.cod and r.degradat and r.verificare_suplimentara and not r.provizoriu
    assert "degradare" in r.motiv_alegere
    assert not apeleaza(tenant, p_fara).verificare_suplimentara  # clasificarea nu cere verificare în plus


def test_consiliul_nu_ruleaza_pe_calea_critica_si_amana_sau_vine_provizoriu(
    tenant: uuid.UUID, fabrica_modele: FabricaModele, fals: FurnizorFals, ceas_controlat: CeasControlat
) -> None:
    f = fabrica_modele.furnizor(platit=True)
    opus = fabrica_modele.model(f, identificator="opus", nivel="T4")
    sonet = fabrica_modele.model(fabrica_modele.furnizor(), identificator="sonet", nivel="T3")
    profil = fabrica_modele.profil(
        [opus.cod], nivel_min="T4", la_epuizare="amana_sau_provizoriu", lant_degradare=["nivel:T3"]
    )
    for pr in (Prioritate.P0, Prioritate.P1):
        with pytest.raises(gateway.ApelRefuzat) as exc:
            apeleaza(tenant, profil, prioritate=pr)
        assert exc.value.cod == "t4_in_afara_caii_critice"
    assert not fals.cereri  # Claude nu a fost nici măcar încercat
    assert apeleaza(tenant, profil, prioritate=Prioritate.P2).model == opus.cod
    fals.scenariu(gazda(opus), permanent="5xx")
    with pytest.raises(gateway.Amanat):
        apeleaza(tenant, profil, prioritate=Prioritate.P2)
    r = apeleaza(tenant, profil, prioritate=Prioritate.P2, accepta_provizoriu=True)
    assert r.model == sonet.cod and r.provizoriu and r.degradat


def test_cu_apelurile_platite_oprite_modelele_platite_nu_se_ating(
    tenant: uuid.UUID, fabrica_modele: FabricaModele, fals: FurnizorFals
) -> None:
    gratis = fabrica_modele.model(fabrica_modele.furnizor(), identificator="g")
    platit = fabrica_modele.model(fabrica_modele.furnizor(platit=True), identificator="p")
    cu_gratis = fabrica_modele.profil([platit.cod, gratis.cod])
    doar_platit = fabrica_modele.profil([platit.cod])
    with sesiune_agentie() as db:
        opriri.seteaza(db, opriri.Oprire.APELURI_PLATITE, True, canal="panou", motiv="test")
    assert apeleaza(tenant, cu_gratis).model == gratis.cod and not fals.cereri_la(gazda(platit))
    with pytest.raises(gateway.ApelRefuzat) as exc:
        apeleaza(tenant, doar_platit)
    assert exc.value.cod == "apeluri_platite_oprite"  # o oprire hotărâtă de om nu se amână la nesfârșit
    with sesiune_agentie() as db:
        opriri.seteaza(db, opriri.Oprire.APELURI_PLATITE, False, canal="panou")
    assert apeleaza(tenant, doar_platit).model == platit.cod


def test_un_client_oprit_nu_primeste_apeluri(tenant: uuid.UUID, doi: Doi, fals: FurnizorFals) -> None:
    with sesiune_agentie() as db:
        opriri.seteaza(db, opriri.Oprire.CLIENT, True, canal="panou", tenant_id=tenant)
    with pytest.raises(gateway.ApelRefuzat) as exc:
        apeleaza(tenant, doi.profil)
    assert exc.value.cod == "client_oprit" and not fals.cereri


def test_judecata_foloseste_alt_model_decat_autorul(tenant: uuid.UUID, doi: Doi, fals: FurnizorFals) -> None:
    assert apeleaza(tenant, doi.profil, alt_model_decat=doi.a.cod).model == doi.b.cod
    assert not fals.cereri_la(gazda(doi.a))


def test_profil_necunoscut_si_date_confidentiale(
    tenant: uuid.UUID, fabrica_modele: FabricaModele, doi: Doi
) -> None:
    with pytest.raises(gateway.ApelRefuzat) as exc:
        apeleaza(tenant, "nu_exista")
    assert exc.value.cod == "profil_necunoscut"
    antrenat = fabrica_modele.model(fabrica_modele.furnizor(antrenare_pe_date=True), identificator="antrenat")
    profil = fabrica_modele.profil([antrenat.cod, doi.a.cod])
    assert apeleaza(tenant, profil).model == antrenat.cod
    assert (
        apeleaza(tenant, profil, date_confidentiale=True).model == doi.a.cod
    )  # 8.9: nu la furnizori care antrenează


def test_cererea_cu_cheie_lipsa_nu_ajunge_la_furnizor(
    tenant: uuid.UUID,
    doi: Doi,
    fals: FurnizorFals,
    monkeypatch: pytest.MonkeyPatch,
    ceas_controlat: CeasControlat,
) -> None:
    monkeypatch.delenv("AMA_CHEIE_PROBA")
    with pytest.raises(gateway.Amanat):
        apeleaza(tenant, doi.profil)
    assert not fals.cereri


class Spion:
    nume = "spion"

    def __init__(self) -> None:
        self.evenimente: list[str] = []
        self.mesaje_vazute: list[tuple[Mesaj, ...]] = []

    def inainte(self, ctx: ContextApel) -> None:
        self.evenimente.append("inainte")
        ctx.mesaje = (*ctx.mesaje, Mesaj("user", "adaos de interceptor"))

    def dupa(self, ctx: ContextApel, rezultat: Rezultat | None, eroare: BaseException | None) -> None:
        self.evenimente.append("dupa:" + (rezultat.model if rezultat else type(eroare).__name__))
        self.mesaje_vazute.append(ctx.mesaje)


@pytest.fixture
def spion() -> Spion:
    s = Spion()
    gateway.adauga_interceptor(s)
    yield s  # type: ignore[misc]
    gateway.elimina_interceptor("spion")


def test_interceptorii_ruleaza_o_data_inainte_de_rutare_si_dupa_apel(
    tenant: uuid.UUID, doi: Doi, fals: FurnizorFals, spion: Spion
) -> None:
    fals.scenariu(
        gazda(doi.a), permanent="5xx"
    )  # două încercări de model, un singur „înainte” și un singur „după”
    r = apeleaza(tenant, doi.profil)
    assert spion.evenimente == ["inainte", f"dupa:{doi.b.cod}"] and r.model == doi.b.cod
    trimis = fals.cereri_la(gazda(doi.b))[0].text_prompt
    assert "adaos de interceptor" in trimis  # ce a schimbat interceptorul ajunge la furnizor
    assert "adaos de interceptor" in fals.cereri_la(gazda(doi.a))[0].text_prompt


def test_un_interceptor_poate_opri_apelul_si_dupa_vede_eroarea(
    tenant: uuid.UUID, doi: Doi, fals: FurnizorFals
) -> None:
    class Buget:
        nume = "buget"

        def __init__(self) -> None:
            self.erori: list[BaseException | None] = []

        def inainte(self, ctx: ContextApel) -> None:
            raise gateway.ApelRefuzat("buget_client", "bugetul zilnic e epuizat")

        def dupa(self, ctx: ContextApel, rezultat: Rezultat | None, eroare: BaseException | None) -> None:
            self.erori.append(eroare)
            raise RuntimeError("o eroare în „după” nu schimbă rezultatul")

    b = Buget()
    gateway.adauga_interceptor(b, ordine=1)
    try:
        with pytest.raises(gateway.ApelRefuzat) as exc:
            apeleaza(tenant, doi.profil)
    finally:
        gateway.elimina_interceptor("buget")
    assert exc.value.cod == "buget_client" and not fals.cereri
    assert isinstance(b.erori[0], gateway.ApelRefuzat)
