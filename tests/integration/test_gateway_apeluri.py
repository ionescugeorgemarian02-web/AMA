"""F3.7 — `gateway.apeleaza` cap-coadă: prompt versionat → rutare → jurnal (și pentru eșecuri) → buget pe livrabil.
Conținutul stă într-un tabel cu RLS și retenție, nu în tabelele motorului, nu în jurnalele aplicației."""

import datetime as dt
import logging
import uuid
from typing import Any

import pytest
from sqlalchemy import Engine, text

from app import gateway, productie
from app.db import sesiune_tenant
from app.gateway import fluxuri, jurnal
from app.gateway.apel import ContextApel
from app.gateway.modele import Apel
from app.operare import motor
from app.operare.motor import Prioritate
from tests.furnizor_fals import FurnizorFals
from tests.gateway_utile import CHEIE_PROBA, Clasificare, FabricaModele, gazda
from tests.integration.utile_productie import livrabil

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def _mediu(cheie_proba: str, ceas_controlat: object, fals: FurnizorFals) -> None:
    fals.text = '{"eticheta": "pozitiv", "dovezi": ["a mulțumit"], "incredere": 0.8}'


class Mediu:
    def __init__(self, f: FabricaModele) -> None:
        self.fa, self.fb = f.furnizor(), f.furnizor()
        self.a = f.model(self.fa, identificator="ma", pret_umbra_intrare=0.6, pret_umbra_iesire=0.8)
        self.b = f.model(self.fb, identificator="mb")
        self.profil = f.profil([self.a.cod, self.b.cod])
        self.prompt = f.prompt(self.profil)


@pytest.fixture
def mediu(fabrica_modele: FabricaModele) -> Mediu:
    return Mediu(fabrica_modele)


def apeleaza(tenant: uuid.UUID, prompt: str, **kw: Any) -> gateway.Rezultat:
    """Apelantul prinde erorile gateway-ului ÎN tranzacția lui (altfel o excepție care iese din `with` anulează tot,
    inclusiv consumul din bugetul livrabilului) și le ridică după ce a închis tranzacția."""
    valori: dict[str, Any] = {
        "variabile": {"text": "Livrarea a fost rapidă!"}, "schema": Clasificare, "componenta": "h4.moderator",
        "prioritate": Prioritate.P2,
    }  # fmt: skip
    valori.update(kw)
    eroare: gateway.EroareGateway | None = None
    with sesiune_tenant(tenant) as db:
        try:
            return gateway.apeleaza(db, prompt=prompt, tenant_id=tenant, **valori)
        except gateway.EroareGateway as exc:
            eroare = exc
    raise eroare


def jurnal_pentru(admin: Engine, prompt: str) -> list[dict[str, Any]]:
    with admin.connect() as c:
        return [
            dict(r._mapping)
            for r in c.execute(
                text("SELECT * FROM gateway_apeluri WHERE prompt_nume = :p ORDER BY creat_la, id"),
                {"p": prompt},
            )
        ]


def continut(admin: Engine, apel_id: uuid.UUID) -> dict[str, Any] | None:
    with admin.connect() as c:
        r = c.execute(
            text("SELECT * FROM gateway_apeluri_continut WHERE apel_id = :i"), {"i": apel_id}
        ).first()
    return dict(r._mapping) if r else None


def test_un_apel_reusit_se_vede_in_jurnal_cu_prompt_model_tokeni_durata_si_pret_umbra(
    tenant: uuid.UUID, mediu: Mediu, fals: FurnizorFals, admin_engine: Engine
) -> None:
    fals.tokeni = (2000, 500)
    r = apeleaza(tenant, mediu.prompt, livrabil_id=None)
    assert r.iesire.eticheta == "pozitiv" and r.model == mediu.a.cod and r.apel_id is not None  # type: ignore[attr-defined]
    assert (r.prompt_nume, r.prompt_versiune) == (mediu.prompt, 1)
    # promptul ajunge la furnizor completat, cu mesaj de sistem
    trimis = fals.cereri_la(gazda(mediu.a))[0].corp["messages"]
    assert trimis[0]["role"] == "system" and trimis[0]["content"].startswith("Ești un clasificator atent.")
    assert "JSON" in trimis[0]["content"]  # modelul fără schemă nativă primește schema în instrucțiuni
    assert trimis[1] == {"role": "user", "content": "Clasifică textul: Livrarea a fost rapidă!"}
    [rand] = jurnal_pentru(admin_engine, mediu.prompt)
    assert rand["id"] == r.apel_id and rand["tenant_id"] == tenant and rand["livrabil_id"] is None
    assert (rand["rezultat"], rand["cod_eroare"], rand["componenta"], rand["prioritate"]) == (
        "ok",
        "",
        "h4.moderator",
        "P2",
    )
    assert (rand["profil"], rand["prompt_versiune"], rand["furnizor"], rand["model"]) == (
        mediu.profil,
        1,
        mediu.a.furnizor,
        mediu.a.cod,
    )
    assert (rand["tokeni_intrare"], rand["tokeni_iesire"], rand["reparatii"]) == (2000, 500, 0)
    assert rand["durata_ms"] >= 0 and str(rand["pret_umbra"]) == "0.001600"  # 2000×0,6 + 500×0,8 la 1 mil.
    assert rand["motiv_alegere"] == "primul model eligibil din lanț" and rand["corelare_id"]
    assert [i["rezultat"] for i in rand["incercari"]] == ["ok"] and rand["incercari"][0][
        "model"
    ] == mediu.a.cod
    c = continut(admin_engine, r.apel_id)
    assert c is not None and c["raspuns"]["eticheta"] == "pozitiv"
    assert [m["rol"] for m in c["mesaje"]] == ["system", "user"] and "Livrarea a fost rapidă!" in c["mesaje"][
        1
    ]["continut"]
    assert c["expira_la"] > rand["creat_la"] + dt.timedelta(days=29)  # 30 de zile


def test_apelul_cu_reparatie_si_cu_model_de_rezerva_isi_pastreaza_traseul(
    tenant: uuid.UUID, mediu: Mediu, fals: FurnizorFals, admin_engine: Engine
) -> None:
    fals.scenariu(gazda(mediu.a), "schema_gresita", "schema_gresita")
    r = apeleaza(tenant, mediu.prompt)
    [rand] = jurnal_pentru(admin_engine, mediu.prompt)
    assert r.model == mediu.b.cod and rand["model"] == mediu.b.cod
    assert [(i["model"], i["rezultat"]) for i in rand["incercari"]] == [
        (mediu.a.cod, "iesire_invalida"),
        (mediu.b.cod, "ok"),
    ]
    assert rand["motiv_alegere"].startswith("modelele dinaintea lui au eșuat")
    assert rand["tokeni_intrare"] > 0 and rand["pret_umbra"] > 0  # și încercarea eșuată s-a plătit


def test_si_apelurile_care_nu_reusesc_lasa_urma(
    tenant: uuid.UUID, mediu: Mediu, fals: FurnizorFals, admin_engine: Engine, fabrica_modele: FabricaModele
) -> None:
    # refuzat: variabile greșite
    with pytest.raises(gateway.ApelRefuzat):
        apeleaza(tenant, mediu.prompt, variabile={"altceva": "x"})
    # refuzat: prompt inexistent
    with pytest.raises(gateway.ApelRefuzat) as nec:
        apeleaza(tenant, "nu.exista")
    assert nec.value.cod == "prompt_necunoscut"
    # amânat: ambii furnizori căzuți
    fals.scenariu(gazda(mediu.a), permanent="5xx")
    fals.scenariu(gazda(mediu.b), permanent="5xx")
    with pytest.raises(gateway.Amanat):
        apeleaza(tenant, mediu.prompt)
    # eșuat: ieșire invalidă pe toate modelele
    fals.scenariu(gazda(mediu.a), permanent="schema_gresita")
    fals.scenariu(gazda(mediu.b), permanent="schema_gresita")
    c = fabrica_modele.model(
        fabrica_modele.furnizor(), identificator="mc"
    )  # alt furnizor: întrerupătorul lui b e deschis
    fals.scenariu(gazda(c), permanent="schema_gresita")
    prompt2 = fabrica_modele.prompt(fabrica_modele.profil([c.cod]))
    with pytest.raises(gateway.IesireInvalida):
        apeleaza(tenant, prompt2)
    pe_cod = {r["cod_eroare"]: r for r in jurnal_pentru(admin_engine, mediu.prompt)}
    assert pe_cod["variabile_lipsa"]["rezultat"] == "refuzat" and pe_cod["amanat"]["rezultat"] == "amanat"
    assert pe_cod["amanat"]["model"] != "" and len(pe_cod["amanat"]["incercari"]) == 2  # ce s-a încercat
    [esec] = jurnal_pentru(admin_engine, prompt2)
    assert (esec["rezultat"], esec["cod_eroare"], esec["model"]) == ("esec", "iesire_invalida", c.cod)
    assert esec["tokeni_intrare"] > 0
    [nec_rand] = jurnal_pentru(admin_engine, "nu.exista")
    assert nec_rand["rezultat"] == "refuzat" and nec_rand["prompt_versiune"] is None


def test_jurnalul_ramane_chiar_daca_apelantul_face_rollback(
    tenant: uuid.UUID, mediu: Mediu, admin_engine: Engine
) -> None:
    class Anulat(Exception):
        pass

    with pytest.raises(Anulat), sesiune_tenant(tenant) as db:
        gateway.apeleaza(
            db, prompt=mediu.prompt, variabile={"text": "x"}, schema=Clasificare, tenant_id=tenant,
            componenta="test", prioritate=Prioritate.P2,
        )  # fmt: skip
        raise Anulat
    assert len(jurnal_pentru(admin_engine, mediu.prompt)) == 1


def test_apelul_se_contorizeaza_in_bugetul_livrabilului_si_cu_bugetul_epuizat_se_refuza(
    tenant: uuid.UUID, mediu: Mediu, fals: FurnizorFals, admin_engine: Engine
) -> None:
    lid = livrabil(tenant)
    with admin_engine.begin() as c:
        c.execute(text("UPDATE livrabile SET buget_apeluri_llm = 2 WHERE id = :i"), {"i": lid})

    def consum() -> tuple[int, float]:
        with sesiune_tenant(tenant) as db:
            lv = productie.citeste(db, lid)
            assert lv is not None
            return lv.apeluri_llm, lv.timp_sec

    apeleaza(tenant, mediu.prompt, livrabil_id=lid)
    assert consum()[0] == 1
    fals.scenariu(gazda(mediu.a), permanent="5xx")
    fals.scenariu(gazda(mediu.b), permanent="5xx")
    with pytest.raises(gateway.Amanat):
        apeleaza(tenant, mediu.prompt, livrabil_id=lid)
    assert consum()[0] == 2  # și încercarea eșuată a ajuns la furnizori, deci se numără
    fals.scenariu(gazda(mediu.a))
    with pytest.raises(gateway.ApelRefuzat) as exc:
        apeleaza(tenant, mediu.prompt, livrabil_id=lid)
    assert exc.value.cod == "buget_livrabil" and consum()[0] == 2  # refuzat înainte de apel: nu se mai numără


def test_la_limita_bugetului_livrabilul_ramane_unde_e_iar_apelul_urmator_se_refuza(
    tenant: uuid.UUID, mediu: Mediu, admin_engine: Engine
) -> None:
    from app.productie.stari import Stare

    lid = livrabil(tenant)
    with admin_engine.begin() as c:
        c.execute(text("UPDATE livrabile SET buget_apeluri_llm = 1 WHERE id = :i"), {"i": lid})
    from tests.integration.utile_productie import muta, stare

    muta(tenant, lid, Stare.PLANIFICAT, Stare.BRIEFAT)
    muta(tenant, lid, Stare.BRIEFAT, Stare.IN_SCRIERE)
    apeleaza(tenant, mediu.prompt, livrabil_id=lid)  # 1 din 1: la limită, nu peste
    assert stare(tenant, lid) is Stare.IN_SCRIERE
    with pytest.raises(gateway.ApelRefuzat):
        apeleaza(tenant, mediu.prompt, livrabil_id=lid)  # peste buget nu se mai apelează


def test_livrabilul_altui_client_si_sesiunea_altui_client_se_refuza(
    tenant: uuid.UUID, fabrica_clienti: Any, mediu: Mediu, fals: FurnizorFals
) -> None:
    alt = fabrica_clienti()
    lid_alt = livrabil(alt)
    with pytest.raises(gateway.ApelRefuzat) as exc:
        apeleaza(tenant, mediu.prompt, livrabil_id=lid_alt)
    assert exc.value.cod == "livrabil_necunoscut"
    with pytest.raises(gateway.ApelRefuzat) as exc2, sesiune_tenant(alt) as db:
        gateway.apeleaza(
            db, prompt=mediu.prompt, variabile={"text": "x"}, schema=Clasificare, tenant_id=tenant,
            componenta="t", prioritate=Prioritate.P2,
        )  # fmt: skip
    assert exc2.value.cod == "tenant_diferit" and not fals.cereri


def test_schema_diferita_de_a_promptului_si_secretele_in_prompt_se_refuza(
    tenant: uuid.UUID, mediu: Mediu, fals: FurnizorFals, admin_engine: Engine
) -> None:
    class AltaSchema(gateway.Iesire):
        x: int

    with pytest.raises(gateway.ApelRefuzat) as exc:
        apeleaza(tenant, mediu.prompt, schema=AltaSchema)
    assert exc.value.cod == "schema_diferita"
    with pytest.raises(gateway.ApelRefuzat) as exc2:
        apeleaza(tenant, mediu.prompt, variabile={"text": f"parola mea e {CHEIE_PROBA}"})
    assert exc2.value.cod == "secret_in_prompt" and not fals.cereri
    for rand in jurnal_pentru(admin_engine, mediu.prompt):
        c = continut(admin_engine, rand["id"])
        assert c is None or CHEIE_PROBA not in str(c)
        assert CHEIE_PROBA not in str(rand)


def test_cheia_nu_apare_in_jurnal_audit_continut_nici_in_jurnalele_aplicatiei(
    tenant: uuid.UUID,
    mediu: Mediu,
    fals: FurnizorFals,
    admin_engine: Engine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    fals.scenariu(gazda(mediu.a), "401")  # eroare de autentificare: pauză + audit + alertă
    apeleaza(tenant, mediu.prompt)
    fals.scenariu(gazda(mediu.b), "5xx", "429")
    with pytest.raises(gateway.EroareGateway):
        apeleaza(tenant, mediu.prompt)
    with admin_engine.connect() as c:
        tot = " ".join(
            str(r) for t in ("gateway_apeluri", "gateway_apeluri_continut", "jurnal_audit", "jurnal_evenimente")
            for r in c.execute(text(f"SELECT * FROM {t}"))
        )  # fmt: skip
        motor_tabele = " ".join(
            str(r) for r in c.execute(text("SELECT inputs, output, error FROM dbos.workflow_status"))
        )
    assert CHEIE_PROBA not in tot and CHEIE_PROBA not in motor_tabele
    assert CHEIE_PROBA not in "\n".join(f"{r.getMessage()} {r.args}" for r in caplog.records)
    assert "Livrarea a fost rapidă!" not in "\n".join(
        r.getMessage() for r in caplog.records
    )  # conținutul nu intră în jurnale
    assert "Livrarea a fost rapidă!" not in motor_tabele


def test_continutul_se_sterge_dupa_30_de_zile_iar_metadatele_raman(
    tenant: uuid.UUID, mediu: Mediu, admin_engine: Engine, ceas_controlat: Any
) -> None:
    r = apeleaza(tenant, mediu.prompt)
    assert r.apel_id is not None and continut(admin_engine, r.apel_id) is not None
    assert jurnal.curata_continut() == 0  # încă valabil
    ceas_controlat.avanseaza(31 * 24 * 3600)
    assert jurnal.curata_continut() >= 1
    assert continut(admin_engine, r.apel_id) is None
    [rand] = jurnal_pentru(admin_engine, mediu.prompt)
    assert rand["model"] == mediu.a.cod and rand["tokeni_intrare"] > 0  # metadatele rămân


def test_curatarea_zilnica_este_un_job_programat_al_motorului() -> None:
    fluxuri.declara_programari()
    ob = [p.nume for p in motor.programari_declarate()]
    assert fluxuri.NUME_CURATARE in ob
    assert "app.gateway.fluxuri" in __import__("app.worker", fromlist=["MODULE_FLUXURI"]).MODULE_FLUXURI


def test_interceptorul_de_mascare_schimba_ce_se_trimite_si_ce_se_pastreaza(
    tenant: uuid.UUID, mediu: Mediu, fals: FurnizorFals, admin_engine: Engine
) -> None:
    class Masca:
        nume = "masca"

        def inainte(self, ctx: ContextApel) -> None:
            ctx.mesaje = tuple(
                type(m)(m.rol, m.continut.replace("cod-intern-77", "[ASCUNS]")) for m in ctx.mesaje
            )

        def dupa(self, ctx: ContextApel, rezultat: object, eroare: BaseException | None) -> None:
            pass

    gateway.adauga_interceptor(Masca())
    try:
        r = apeleaza(tenant, mediu.prompt, variabile={"text": "referința este cod-intern-77"})
    finally:
        gateway.elimina_interceptor("masca")
    assert "cod-intern-77" not in fals.cereri_la(gazda(mediu.a))[0].text_prompt
    assert r.apel_id is not None
    c = continut(admin_engine, r.apel_id)
    assert c is not None and "cod-intern-77" not in str(c["mesaje"]) and "[ASCUNS]" in str(c["mesaje"])


def test_interogarile_ocolesc_alt_client(tenant: uuid.UUID, fabrica_clienti: Any, mediu: Mediu) -> None:
    apeleaza(tenant, mediu.prompt)
    alt = fabrica_clienti()
    with sesiune_tenant(alt) as db:
        assert jurnal.lista(db, jurnal.Filtre(model=mediu.a.cod)) == []
        assert jurnal.totaluri(db, jurnal.Filtre()).apeluri == 0
    with sesiune_tenant(tenant) as db:
        assert len(jurnal.lista(db, jurnal.Filtre(model=mediu.a.cod))) == 1
        assert db.query(Apel).count() >= 1
