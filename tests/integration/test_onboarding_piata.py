"""F4.10 — harta pieței și brieful de insight (C7, C8). „Gata când” (brand de probă, concurenți inventați): fiecare afirmație
a brieful este legată de o sursă, iar verificarea prin sondaj trece (și pică pe un citat falsificat). Modelul este FALS."""

# ruff: noqa: F811
import re
import uuid
from typing import Any

import pytest
from sqlalchemy import text

from app import cercetare, creier
from app.creier.compartimente import Compartiment, SursaTip
from app.db import sesiune_tenant
from app.onboarding import fluxuri, piata
from app.operare import motor
from tests import materiale_zorilor as mz
from tests.furnizor_fals import CerereInregistrata
from tests.integration.test_cercetare_colectare import mediu  # noqa: F401
from tests.integration.test_onboarding_ghid import brief_aprobat
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401
from tests.onboarding_utile import ModelFals, blocuri, model_fals, modele, raspuns_json  # noqa: F401
from tests.site_fals import SiteFals

pytestmark = pytest.mark.db


def model_piata(
    modele: ModelFals, *, inventat: bool = False, fara_trimitere: bool = False, trimitere_falsa: bool = False
) -> None:
    def afirmatii(c: CerereInregistrata) -> str:
        pasaj = blocuri(c)[0][1]
        lista = []
        for rand in pasaj.splitlines():
            rand = rand.strip()
            if len(rand) < 25:
                continue
            m = re.search(r"(\d+) lei", rand)
            citat = rand.split(". ")[0].rstrip(".") if ". " in rand else rand
            lista.append({"tip": "pret" if m else "mesaj", "afirmatie": f"Concurentul afirmă: {citat[:120]}", "citat": citat,
                          "valoare_numar": m.group(1) if m else None, "moneda": "RON" if m else None})  # fmt: skip
        if inventat:
            lista.append({"tip": "mesaj", "afirmatie": "Concurentul oferă cafea gratis pe viață", "citat": "Cafea gratis pe viață pentru toți clienții",
                          "valoare_numar": None, "moneda": None})  # fmt: skip
        return raspuns_json(afirmatii=lista)

    def brief(c: CerereInregistrata) -> str:
        ids = re.findall(r"\[(afirmatie:[0-9a-f-]{36})\] ([^:]+) \((\w+)\): (.*)", blocuri(c)[1][1])
        assert len(ids) >= 9

        def e(k: int, prefix: str) -> dict[str, Any]:
            t, nume, _, afirm = ids[k % len(ids)]
            return {"text": f"{prefix} {nume}: {afirm[:140]}", "surse": [t]}

        brief_ = {
            "titlu": "Piața cafelei de specialitate din Brașov",
            "rezumat": e(0, "Pe scurt,"),
            "harta": [e(k, "Se spune că") for k in range(1, 7)],
            "spatii_libere": [e(7, "Spațiu liber: nimeni nu pune accent pe")],
            "recomandari": [e(8, "Recomandare, plecând de la")],
        }
        if fara_trimitere:
            brief_["harta"][2]["surse"] = []
        if trimitere_falsa:
            brief_["harta"][3]["surse"] = [f"afirmatie:{uuid.uuid4()}"]  # neoferită modelului: se scoate
        return raspuns_json(brief=brief_)

    modele.handlere["Extrage ce afirmă concurentul"] = afirmatii
    modele.handlere["Scrie brieful de insight"] = brief


def concurenti_manuali(tenant: uuid.UUID, om: uuid.UUID) -> list[uuid.UUID]:
    ids = []
    with sesiune_tenant(tenant, om) as db:
        for nume, paragrafe in mz.CONCURENTI.items():
            s = piata.adauga_concurent(db, tenant_id=tenant, nume=nume, utilizator_id=om)
            cercetare.adauga_text(
                db, tenant_id=tenant, sursa_id=s.id, titlu=f"Pagina {nume}", text="\n\n".join(paragrafe)
            )
            creier.pregateste_sursa(db, s.id)
            ids.append(s.id)
    return ids


def extrage(tenant: uuid.UUID, ids: list[uuid.UUID], cheie: str) -> None:
    for sid in ids:
        job = fluxuri.trimite_extragerea(tenant, sid, "afirmatii", cheie=f"{cheie}:{sid}")
        assert motor.asteapta_flux(job, timeout_sec=60).stare.value == "terminat"


def propune(tenant: uuid.UUID, om: uuid.UUID, cheie: str) -> None:
    job = fluxuri.trimite_brief_insight(tenant, om, cheie=cheie)
    assert motor.asteapta_flux(job, timeout_sec=60).stare.value == "terminat"


def brief_db(tenant: uuid.UUID) -> tuple[uuid.UUID, Any]:
    with sesiune_tenant(tenant) as db:
        i = creier.gaseste_intrare(
            db, tenant_id=tenant, compartiment=Compartiment.INSIGHT_PIATA, cheie=piata.CHEIE_BRIEF
        )
        assert i is not None
        return i.id, creier.istoric(db, i.id)[-1]


def test_concurentii_sunt_surse_3_pana_la_5_iar_textul_lor_nu_se_reutilizeaza(
    tenant: uuid.UUID, om: uuid.UUID
) -> None:
    concurenti_manuali(tenant, om)
    with sesiune_tenant(tenant, om) as db:
        assert {s.nume for s in piata.concurenti(db, tenant)} == set(mz.CONCURENTI)
        assert all(not cercetare.STATUTE[s.statut].reutilizare_text for s in piata.concurenti(db, tenant))
        piata.adauga_concurent(db, tenant_id=tenant, nume="Al patrulea", utilizator_id=om)
        piata.adauga_concurent(db, tenant_id=tenant, nume="Al cincilea", utilizator_id=om)
        with pytest.raises(piata.RegulaPiata, match="cel mult 5"):
            piata.adauga_concurent(db, tenant_id=tenant, nume="Al șaselea", utilizator_id=om)


def test_afirmatiile_au_sursa_citat_literal_iar_cele_inventate_sau_cu_cifra_gresita_sunt_respinse(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, executor: None
) -> None:
    model_piata(modele, inventat=True)
    ids = concurenti_manuali(tenant, om)
    extrage(tenant, ids, "af1")
    with sesiune_tenant(tenant) as db:
        toate = piata.afirmatii(db, tenant)
        assert len(toate) == 9 and {a.concurent for a in toate} == set(mz.CONCURENTI)
        for a in toate:
            p = db.execute(text("SELECT text FROM pasaje WHERE id = :i"), {"i": a.pasaj_id}).scalar_one()
            assert creier.citat_in_text(a.citat, p)  # citat literal în pasajul-sursă
        preturi = {a.valoare["numar"] for a in toate if a.concurent == "Cafeneaua Brumei" and a.valoare}  # type: ignore[index]
        assert preturi == {"45", "95"}
        rez = piata.extractie.rezumat(db, tenant, ids[0], piata.REFERINTA_AFIRMATII)
        assert rez["respinse"] >= 1 and rez["propuse"] == 3  # citatul inventat, la fiecare pasaj
        assert "Cafea gratis pe viață" not in " ".join(a.afirmatie for a in toate)


def test_brieful_de_insight_leaga_fiecare_afirmatie_de_o_sursa_iar_sondajul_trece(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, executor: None
) -> None:
    model_piata(modele)
    brief_aprobat(tenant, om)
    ids = concurenti_manuali(tenant, om)
    extrage(tenant, ids, "af2")
    propune(tenant, om, f"insight:{tenant}:1")
    iid, v = brief_db(tenant)
    assert v.stare == "propus"
    c = v.continut
    enunturi = piata.enunturi(c)
    assert len(enunturi) == 9 and piata.fara_trimitere(c) == []
    assert all(e["surse"] for e in enunturi)  # fiecare afirmație → o sursă
    with sesiune_tenant(tenant, om) as db:
        raport = piata.verifica_prin_sondaj(db, tenant, c)
        assert raport.trece and len(raport.verificate) >= 5  # eșantion de cel puțin 5
        # trimiterile duc la afirmații aprobate cu pasaj și URL/poziție
        a0 = enunturi[0]["surse"][0].split(":")[1]
        sursa = creier.citeste(db, uuid.UUID(a0), 1)
        assert (
            sursa.sursa_tip == SursaTip.PASAJ.value and sursa.sursa_citat and "pozitie" in sursa.sursa_detalii
        )
        with pytest.raises(
            creier.RegulaCreier, match="doar de un om"
        ):  # afirmațiile se aprobă de sistem, brieful nu
            creier.aproba(db, iid, v.nr, utilizator_id=None, prin_sistem=True)
        creier.aproba(db, iid, v.nr, utilizator_id=om)  # un om îl aprobă
        assert creier.versiune_aprobata(db, iid) is not None


def test_o_afirmatie_fara_trimitere_blocheaza_trimiterea_si_aprobarea(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, executor: None
) -> None:
    model_piata(modele, fara_trimitere=True, trimitere_falsa=True)
    brief_aprobat(tenant, om)
    ids = concurenti_manuali(tenant, om)
    extrage(tenant, ids, "af3")
    propune(tenant, om, f"insight:{tenant}:2")
    iid, v = brief_db(tenant)
    assert (
        v.stare == "ciorna"
    )  # nu poate fi „propus”: două afirmații fără trimitere (una cu trimitere inventată, scoasă)
    assert len(piata.fara_trimitere(v.continut)) == 2
    with sesiune_tenant(tenant, om) as db:
        with pytest.raises(creier.PoartaInchisa) as exc:
            creier.trimite_spre_aprobare(db, iid, v.nr, utilizator_id=om)
        assert len(exc.value.probleme) == 2 and "fără trimitere" in exc.value.probleme[0]
        with pytest.raises(
            creier.PoartaInchisa
        ):  # nici o versiune nouă cu același conținut nu devine „propus”
            creier.propune_schimbare(
                db, iid, continut=v.continut, sursa=creier.Sursa(SursaTip.OM), utilizator_id=om
            )
        assert creier.versiune_aprobata(db, iid) is None


def test_sondajul_pica_pe_un_citat_falsificat_si_blocheaza_aprobarea(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, executor: None
) -> None:
    model_piata(modele)
    brief_aprobat(tenant, om)
    ids = concurenti_manuali(tenant, om)
    extrage(tenant, ids, "af4")
    model_piata(modele)
    propune(tenant, om, f"insight:{tenant}:3")
    iid, v = brief_db(tenant)
    c = v.continut
    # abia acum se strecoară o afirmație cu citat FALSIFICAT, pe calea generică (care nu verifică citate); brieful
    # cinstit de mai sus nu o poate cita, iar sondajul trebuie să o prindă într-un brief care o citează
    with sesiune_tenant(tenant, om) as db:
        pasaj = db.execute(
            text("SELECT id FROM pasaje WHERE tenant_id = :t LIMIT 1"), {"t": tenant}
        ).scalar_one()
        i, ver = creier.creeaza_intrare(
            db, tenant_id=tenant, compartiment=Compartiment.INSIGHT_PIATA, cheie="afirm-falsa",
            continut={"tip": "afirmatie", "concurent": "Cafeneaua Brumei", "categorie": "mesaj", "afirmatie": "Cafea gratis pe viață"},
            sursa=creier.Sursa(SursaTip.PASAJ, ref=str(pasaj), citat="Cafea gratis pe viață pentru toți clienții"),
        )  # fmt: skip
        creier.aproba(db, i.id, ver.nr, utilizator_id=None, prin_sistem=True)
        falsa = f"afirmatie:{i.id}"
    # brieful cinstit trece; cel cu trimiterea la afirmația falsificată pică la sondaj (eșantionul acoperă toate trimiterile când sunt puține)
    reale = [e["surse"][0] for e in piata.enunturi(c)][:3]
    c2 = {
        **c,
        "rezumat": {"text": "Rezumat sprijinit pe afirmații reale.", "surse": [reale[0]]},
        "harta": [{"text": "Afirmație sprijinită pe un citat real.", "surse": [reale[1]]},
                  {"text": "O afirmație sprijinită doar pe citatul falsificat.", "surse": [falsa]},
                  {"text": "Altă afirmație, cu o sursă reală.", "surse": [reale[2]]}],
        "spatii_libere": [{"text": "Un spațiu liber, cu o sursă reală.", "surse": [reale[1]]}],
        "recomandari": [{"text": "O recomandare, cu o sursă reală.", "surse": [reale[0]]}],
    }  # fmt: skip
    with sesiune_tenant(tenant, om) as db:
        assert piata.verifica_prin_sondaj(db, tenant, c).trece
        raport = piata.verifica_prin_sondaj(
            db, tenant, c2
        )  # puține trimiteri: eșantionul le acoperă pe toate
        assert not raport.trece and [x["trimitere"] for x in raport.picate] == [falsa]
        with pytest.raises(creier.PoartaInchisa, match="nu se regăsește în sursă"):
            creier.propune_schimbare(db, iid, continut=c2, sursa=creier.Sursa(SursaTip.OM), utilizator_id=om)
        # trimitere către nimic: raportată separat
        c3 = {
            **c2,
            "harta": [
                {"text": "Afirmație cu trimitere către nimic.", "surse": [f"afirmatie:{uuid.uuid4()}"]}
            ],
        }
        assert piata.verifica_prin_sondaj(db, tenant, c3).inexistente


def test_brieful_cere_cel_putin_3_concurenti_cu_afirmatii(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, executor: None
) -> None:
    model_piata(modele)
    brief_aprobat(tenant, om)
    ids = concurenti_manuali(tenant, om)
    extrage(tenant, ids[:2], "af5")
    with sesiune_tenant(tenant, om) as db, pytest.raises(piata.RegulaPiata, match="cel puțin 3 concurenți"):
        piata.propune_brief(db, tenant_id=tenant, utilizator_id=om)


def test_un_concurent_cu_site_se_citeste_cu_colectorul_si_robots_txt_apoi_se_extrag_afirmatiile(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, executor: None, mediu: SiteFals
) -> None:
    from tests.integration.test_cercetare_colectare import ruleaza, sursa_site

    model_piata(modele)
    sid = sursa_site(tenant, mediu, "site_concurenta")  # același colector ca pentru site-ul clientului
    ruleaza(tenant, sid)
    cai = {c for c, _ in mediu.cereri}
    assert "/robots.txt" in cai and not any(c.startswith("/privat/") for c in cai)  # robots.txt respectat
    with sesiune_tenant(tenant) as db:
        assert creier.pregateste_sursa(db, sid) > 0
        assert [s.id for s in piata.concurenti(db, tenant)] == [sid]
    extrage(tenant, [sid], "af6")
    with sesiune_tenant(tenant) as db:
        toate = piata.afirmatii(db, tenant)
    assert toate and {a.concurent for a in toate} == {"Site Zorilor"}
    assert all(a.url and a.url.startswith(mediu.baza) for a in toate)  # fiecare afirmație → pasaj și URL
    assert any(a.categorie == "pret" and a.valoare and a.valoare["numar"] == "49" for a in toate)
