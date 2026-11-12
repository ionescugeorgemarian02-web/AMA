"""F3.8 — bugetele pe client, ca interceptor al gateway-ului: P2/P3 amânate la depășire, P1 după plafonul lui, P0 neatins;
consum din contoare proprii (corect la concurență); avertizare o singură dată pe fereastră; editare cu audit."""

import datetime as dt
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import Engine, text

from app import gateway
from app.db import sesiune_agentie, sesiune_tenant
from app.gateway import bugete
from app.gateway.bugete import BugetClient
from app.gateway.reguli_buget import Fereastra
from app.operare.motor import Prioritate
from tests.furnizor_fals import FurnizorFals
from tests.gateway_utile import FabricaModele, gazda
from tests.integration.test_gateway_apeluri import apeleaza
from tests.integration.utile_productie import AnunturiFalse

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def _mediu(cheie_proba: str, ceas_controlat: object, fals: FurnizorFals) -> None:
    fals.text = '{"eticheta": "pozitiv", "dovezi": ["a"], "incredere": 0.8}'
    fals.tokeni = (100, 50)


class Mediu:
    def __init__(self, f: FabricaModele) -> None:
        self.fa = f.furnizor()
        self.a = f.model(self.fa, identificator="ma", pret_umbra_intrare=10.0, pret_umbra_iesire=20.0)
        self.profil = f.profil([self.a.cod])
        self.prompt = f.prompt(self.profil)


@pytest.fixture
def mediu(fabrica_modele: FabricaModele) -> Mediu:
    return Mediu(fabrica_modele)


def buget(admin: Engine, tenant: uuid.UUID, **valori: Any) -> None:
    """Suprascrie bugetul clientului direct în bază (pregătire de test)."""
    with admin.begin() as c:
        c.execute(
            text("INSERT INTO gateway_bugete_client (tenant_id) VALUES (:t) ON CONFLICT DO NOTHING"),
            {"t": tenant},
        )
        for k, v in valori.items():
            c.execute(
                text(f"UPDATE gateway_bugete_client SET {k} = :v WHERE tenant_id = :t"), {"v": v, "t": tenant}
            )


def consum(tenant: uuid.UUID) -> tuple[int, int, Decimal]:
    with sesiune_tenant(tenant) as db:
        c = bugete.consum_curent(db, tenant)[Fereastra.ZI]
    return c.apeluri, c.tokeni, c.pret_umbra


def test_clientul_care_isi_depaseste_bugetul_are_p2_amanat_si_p0_neatins(
    tenant: uuid.UUID, mediu: Mediu, admin_engine: Engine, fals: FurnizorFals
) -> None:
    buget(admin_engine, tenant, apeluri_zi=2)
    apeleaza(tenant, mediu.prompt, prioritate=Prioritate.P2)
    apeleaza(tenant, mediu.prompt, prioritate=Prioritate.P2)
    with pytest.raises(gateway.Amanat) as amanat:
        apeleaza(tenant, mediu.prompt, prioritate=Prioritate.P2)
    # momentul resetării: începutul zilei următoare (cu marja de o secundă)
    assert amanat.value.pana_la == dt.datetime(2026, 11, 13, 0, 0, 1, tzinfo=dt.UTC)
    assert "bugetul clientului" in amanat.value.motiv and "apeluri pe zi" in amanat.value.motiv
    with pytest.raises(gateway.Amanat):
        apeleaza(tenant, mediu.prompt, prioritate=Prioritate.P3)
    # P0 nu e atins: trece și peste buget, iar consumul lui se numără
    r = apeleaza(tenant, mediu.prompt, prioritate=Prioritate.P0)
    assert r.iesire.eticheta == "pozitiv"  # type: ignore[attr-defined]
    assert consum(tenant)[0] == 3
    # apelurile amânate nu au ajuns la furnizor: doar cele trei reușite
    assert len(fals.cereri_la(gazda(mediu.a))) == 3


def test_p1_continua_peste_buget_pana_la_plafonul_lui(
    tenant: uuid.UUID, mediu: Mediu, admin_engine: Engine
) -> None:
    buget(admin_engine, tenant, apeluri_zi=2)  # plafon P1 implicit: 1,5 × 2 = 3
    for _ in range(3):
        apeleaza(tenant, mediu.prompt, prioritate=Prioritate.P1)
    with pytest.raises(gateway.Amanat):
        apeleaza(tenant, mediu.prompt, prioritate=Prioritate.P1)
    apeleaza(tenant, mediu.prompt, prioritate=Prioritate.P0)  # P0 tot trece


def test_bugetul_lunar_amana_pana_la_prima_zi_a_lunii_urmatoare(
    tenant: uuid.UUID, mediu: Mediu, admin_engine: Engine
) -> None:
    buget(admin_engine, tenant, apeluri_luna=1)
    apeleaza(tenant, mediu.prompt, prioritate=Prioritate.P2)
    with pytest.raises(gateway.Amanat) as amanat:
        apeleaza(tenant, mediu.prompt, prioritate=Prioritate.P2)
    assert amanat.value.pana_la == dt.datetime(2026, 12, 1, 0, 0, 1, tzinfo=dt.UTC)
    assert "apeluri pe lună" in amanat.value.motiv
    # nicio rezervare parțială: ziua nu a numărat apelul refuzat
    assert consum(tenant)[0] == 1


def test_tokenii_si_pretul_umbra_se_numara_dupa_apel_si_opresc_urmatorul(
    tenant: uuid.UUID, mediu: Mediu, admin_engine: Engine
) -> None:
    buget(admin_engine, tenant, tokeni_zi=200)  # un apel = 150 de tokeni
    apeleaza(tenant, mediu.prompt, prioritate=Prioritate.P2)
    assert consum(tenant) == (1, 150, Decimal("0.002000"))  # 100×10 + 50×20 la 1 mil.
    apeleaza(tenant, mediu.prompt, prioritate=Prioritate.P2)  # 150 < 200: încă încape
    with pytest.raises(gateway.Amanat) as amanat:
        apeleaza(tenant, mediu.prompt, prioritate=Prioritate.P2)  # 300 ≥ 200
    assert "tokeni pe zi" in amanat.value.motiv
    buget(admin_engine, tenant, tokeni_zi=None, pret_umbra_zi=Decimal("0.004"))
    with pytest.raises(gateway.Amanat) as amanat2:
        apeleaza(tenant, mediu.prompt, prioritate=Prioritate.P3)  # 0,004 ≥ 0,004
    assert "preț-umbră pe zi" in amanat2.value.motiv


def test_un_apel_amanat_de_cota_furnizorului_nu_consuma_din_bugetul_clientului(
    tenant: uuid.UUID, fabrica_modele: FabricaModele, admin_engine: Engine
) -> None:
    f = fabrica_modele.furnizor(cereri_minut=1)
    m = fabrica_modele.model(f, identificator="strans")
    prompt = fabrica_modele.prompt(fabrica_modele.profil([m.cod]))
    apeleaza(tenant, prompt, prioritate=Prioritate.P2)
    assert consum(tenant)[0] == 1
    with pytest.raises(gateway.Amanat):  # cota pe minut a furnizorului
        apeleaza(tenant, prompt, prioritate=Prioritate.P2)
    assert consum(tenant)[0] == 1  # rezervarea a fost eliberată: nu ajunsese la furnizor


def test_rezervarea_este_corecta_la_concurenta(tenant: uuid.UUID, admin_engine: Engine) -> None:
    buget(admin_engine, tenant, apeluri_zi=10)
    pornire = threading.Barrier(24)

    def incearca(_: int) -> bool:
        ctx = SimpleNamespace(tenant_id=tenant, prioritate=Prioritate.P2, extra={})
        pornire.wait()
        try:
            BugetClient().inainte(ctx)
        except gateway.Amanat:
            return False
        return True

    with ThreadPoolExecutor(24) as ex:
        rezultate = list(ex.map(incearca, range(24)))
    assert rezultate.count(True) == 10 and consum(tenant)[0] == 10


def test_avertizarea_pleaca_o_singura_data_pe_fereastra(
    tenant: uuid.UUID, mediu: Mediu, admin_engine: Engine, anunturi: AnunturiFalse
) -> None:
    buget(admin_engine, tenant, apeluri_zi=5, apeluri_luna=None)  # pragul implicit: 80% = al 4-lea apel
    for _ in range(3):
        apeleaza(tenant, mediu.prompt, prioritate=Prioritate.P2)
    assert anunturi.titluri() == []
    apeleaza(tenant, mediu.prompt, prioritate=Prioritate.P2)
    assert anunturi.titluri() == ["Buget de modele aproape epuizat"]
    assert "apeluri pe zi" in anunturi.trimise[0][2] and "80%" in anunturi.trimise[0][2]
    apeleaza(tenant, mediu.prompt, prioritate=Prioritate.P2)  # al 5-lea: tot în aceeași fereastră
    assert len(anunturi.trimise) == 1
    # fereastra următoare, aceeași situație: o nouă avertizare
    from app.gateway import ceas as modul_ceas

    modul_ceas.seteaza_ceas(lambda: dt.datetime(2026, 11, 13, 9, 0, tzinfo=dt.UTC))
    for _ in range(4):
        apeleaza(tenant, mediu.prompt, prioritate=Prioritate.P2)
    assert len(anunturi.trimise) == 2


def test_valorile_implicite_se_aplica_si_suprascrierea_clientului_le_bate(
    tenant: uuid.UUID, admin_engine: Engine, om: uuid.UUID
) -> None:
    with sesiune_agentie() as db:
        implicit = bugete.implicit(db)
        assert implicit.zi.apeluri == 400 and implicit.prag_avertizare == pytest.approx(0.8)
        assert implicit.plafon_p1 == pytest.approx(1.5)
        assert bugete.efectiv(db, tenant) == implicit  # fără suprascriere
        bugete.seteaza_client(
            db, tenant, {"apeluri_zi": 7, "tokeni_luna": 99, "pret_umbra_luna": "12.50"}, utilizator_id=om
        )
        bugete.seteaza_implicite(
            db, {"tokeni_zi": 1_500_000}, prag_avertizare=0.8, plafon_p1=1.5, utilizator_id=om
        )
    with sesiune_tenant(tenant) as db:
        efectiv = bugete.efectiv(db, tenant)
    assert efectiv.zi.apeluri == 7 and efectiv.zi.tokeni == implicit.zi.tokeni  # restul rămâne implicit
    assert efectiv.luna.pret_umbra == Decimal("12.5000") and efectiv.luna.tokeni == 99
    with sesiune_agentie() as db:  # revenire la valoarea implicită
        bugete.seteaza_client(db, tenant, {"apeluri_zi": None}, utilizator_id=om)
        assert bugete.efectiv(db, tenant).zi.apeluri == 400
    with admin_engine.connect() as c:
        n = c.execute(
            text(
                "SELECT count(*) FROM jurnal_audit WHERE actiune = 'gateway.buget_client_setat' AND tenant_id = :t"
            ),
            {"t": tenant},
        ).scalar_one()
    assert n == 2


@pytest.mark.parametrize(
    "valori",
    [{"apeluri_zi": -1}, {"nu_exista": 1}, {"tokeni_luna": "abc"}],
)
def test_valorile_nepermise_se_refuza(tenant: uuid.UUID, valori: dict[str, Any], om: uuid.UUID) -> None:
    with sesiune_agentie() as db, pytest.raises(bugete.BugetInvalid):
        bugete.seteaza_client(db, tenant, valori, utilizator_id=om)


def test_situatia_arata_consumul_fiecarui_client_fata_de_buget(
    tenant: uuid.UUID, fabrica_clienti: Any, mediu: Mediu, admin_engine: Engine
) -> None:
    altul = fabrica_clienti()
    buget(admin_engine, tenant, apeluri_zi=50)
    apeleaza(tenant, mediu.prompt, prioritate=Prioritate.P2)
    with sesiune_agentie() as db:
        randuri = {r.tenant_id: r for r in bugete.situatie(db)}
    assert randuri[tenant].zi.apeluri == 1 and randuri[tenant].luna.apeluri == 1 and randuri[tenant].propriu
    assert randuri[tenant].buget.zi.apeluri == 50
    assert randuri[altul].zi.apeluri == 0 and not randuri[altul].propriu
