"""F4.4 — asistentul de onboarding. „Gata când”: un interviu de probă produce un brief complet, fără câmpuri goale;
un brief cu câmpuri goale nu poate fi trimis spre aprobare. Modelul este FALS (# SIMULAT, scriptat)."""

# ruff: noqa: F811
import uuid

import pytest
from sqlalchemy import text

from app import cercetare, creier, onboarding
from app.creier.compartimente import Compartiment, SursaTip
from app.creier.versiuni import Sursa
from app.db import sesiune_tenant
from app.onboarding import brief, clarificare, completare, interviu, sesiuni
from app.operare import motor
from tests import materiale_zorilor as mz
from tests.furnizor_fals import FurnizorFals
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401
from tests.onboarding_utile import RASPUNSURI, ModelFals, model_fals, modele  # noqa: F401

pytestmark = pytest.mark.db


def interviu_complet(
    tenant: uuid.UUID, om: uuid.UUID, *, suprascrie: dict[str, str] | None = None
) -> uuid.UUID:
    """Deschide sesiunea și răspunde la toate întrebările (inclusiv la clarificările generate)."""
    raspunsuri = {**RASPUNSURI, **(suprascrie or {})}
    with sesiune_tenant(tenant, om) as db:
        s = sesiuni.deschide(db, tenant_id=tenant, utilizator_id=om)
        while (q := sesiuni.urmatoarea(db, s.id)) is not None:
            r = sesiuni.raspunde(db, s.id, q.id, raspunsuri.get(q.cod, RASPUNSURI[q.cod]), utilizator_id=om)
            assert r.intrebare_id == q.id
        return s.id


def _gazde_modele() -> list[tuple[str]]:
    from app.db import sesiune_agentie

    with sesiune_agentie() as db:
        return [
            (r[0],)
            for r in db.execute(
                text(
                    "SELECT split_part(split_part(url_baza, '://', 2), '/', 1) FROM gateway_furnizori WHERE cod LIKE 'p%'"
                )
            )
        ]


def materiale(tenant: uuid.UUID) -> None:
    with sesiune_tenant(tenant) as db:
        sid = cercetare.creeaza_sursa(
            db, tenant_id=tenant, tip="manual", statut_cod="material_client", nume="Site"
        ).id
        for titlu, paragrafe in (mz.PAGINI["/produse"], mz.PAGINI["/despre"]):
            cercetare.adauga_text(
                db, tenant_id=tenant, sursa_id=sid, titlu=titlu, text="\n\n".join(paragrafe)
            )
        creier.pregateste_sursa(db, sid)


def compune(tenant: uuid.UUID, om: uuid.UUID, sid: uuid.UUID) -> str:
    job = onboarding.fluxuri.trimite_compunerea(tenant, sid, om, cheie=f"brief:{sid}")
    return motor.asteapta_flux(job, timeout_sec=60).stare.value


def test_interviul_se_reia_de_unde_a_ramas_si_exista_o_singura_sesiune_deschisa(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals
) -> None:
    with sesiune_tenant(tenant, om) as db:
        s = sesiuni.deschide(db, tenant_id=tenant, utilizator_id=om)
        q1 = sesiuni.urmatoarea(db, s.id)
        assert q1 is not None and q1.cod == "nume" and sesiuni.progres(db, s.id).procent == 0
        sesiuni.raspunde(db, s.id, q1.id, RASPUNSURI["nume"], utilizator_id=om)
        sid = s.id
    with sesiune_tenant(tenant, om) as db:  # „a doua zi”: aceeași sesiune, aceeași poziție
        s2 = sesiuni.deschide(db, tenant_id=tenant, utilizator_id=om)
        assert s2.id == sid
        q = sesiuni.urmatoarea(db, sid)
        p = sesiuni.progres(db, sid)
        assert q is not None and q.cod == "ce_vinde" and p.raspunse == 1 and p.total == 11 and not p.terminat
        n = db.execute(
            text("SELECT count(*) FROM onboarding_sesiuni WHERE tenant_id = :t"), {"t": tenant}
        ).scalar_one()
        assert n == 1
        # răspuns gol sau la o întrebare străină: refuzat
        with pytest.raises(onboarding.EroareOnboarding):
            sesiuni.raspunde(db, sid, q.id, "   ", utilizator_id=om)
        with pytest.raises(onboarding.EroareOnboarding):
            sesiuni.raspunde(db, sid, uuid.uuid4(), "ceva", utilizator_id=om)


def test_un_raspuns_vag_primeste_cel_mult_doua_clarificari_generate_de_model(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals
) -> None:
    vag = "Diverse produse și multe lucruri bune."
    with sesiune_tenant(tenant, om) as db:
        s = sesiuni.deschide(db, tenant_id=tenant, utilizator_id=om)
        sesiuni.raspunde(db, s.id, sesiuni.urmatoarea(db, s.id).id, RASPUNSURI["nume"], utilizator_id=om)  # type: ignore[union-attr]
        q = sesiuni.urmatoarea(db, s.id)
        assert q is not None and q.cod == "ce_vinde"
        r1 = sesiuni.raspunde(db, s.id, q.id, vag, utilizator_id=om)
        assert r1.clarificare is not None and r1.clarificare.tip == "clarificare"
        assert (
            r1.clarificare.generata_de == "model" and "produse care se vând" in r1.clarificare.text_intrebare
        )
        assert sesiuni.urmatoarea(db, s.id).id == r1.clarificare.id  # type: ignore[union-attr]
        r2 = sesiuni.raspunde(
            db, s.id, r1.clarificare.id, "Tot felul de cafele, multe lucruri.", utilizator_id=om
        )
        assert r2.clarificare is not None and r2.clarificare.parinte_id == q.id
        r3 = sesiuni.raspunde(db, s.id, r2.clarificare.id, "Diverse, multe lucruri.", utilizator_id=om)
        assert r3.clarificare is None and "limita" in r3.motiv  # limita de două clarificări pe întrebare
        p = sesiuni.progres(db, s.id)
        assert p.clarificari_puse == 2 and p.raspunse == 2
        assert sesiuni.urmatoarea(db, s.id).cod == "preturi"  # type: ignore[union-attr]
    assert modele.apeluri.count("Întrebarea pusă clientului") == 3


def test_limita_de_clarificari_pe_sesiune(tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals) -> None:
    with sesiune_tenant(tenant, om) as db:
        s = sesiuni.deschide(db, tenant_id=tenant, utilizator_id=om)
        while (q := sesiuni.urmatoarea(db, s.id)) is not None:
            sesiuni.raspunde(
                db, s.id, q.id, "Diverse, multe lucruri bune și tot felul de alte lucruri.", utilizator_id=om
            )
        p = sesiuni.progres(db, s.id)
        assert p.clarificari_puse == clarificare.MAX_PE_SESIUNE and p.terminat


def test_fara_gateway_un_raspuns_prea_scurt_primeste_intrebarea_din_interviu(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, fals: FurnizorFals
) -> None:
    """Furnizorul cade: interviul nu se blochează; răspunsul scurt primește întrebarea-șablon, cel lung se acceptă."""
    for gazda in {c.gazda for c in fals.cereri} | {g for (g,) in _gazde_modele()}:
        fals.scenariu(gazda, permanent="5xx")
    with sesiune_tenant(tenant, om) as db:
        scurt = clarificare.evalueaza(
            db, tenant_id=tenant, intrebare=interviu.camp_intrebare("ce_vinde"), raspuns="Cafea"
        )
        lung = clarificare.evalueaza(
            db,
            tenant_id=tenant,
            intrebare=interviu.camp_intrebare("ce_vinde"),
            raspuns=RASPUNSURI["ce_vinde"],
        )
    assert scurt.suficient is False and scurt.generata_de == "sablon"
    assert scurt.intrebare == interviu.camp_intrebare("ce_vinde").clarificare_sablon
    assert lung.suficient is True


def test_interviu_de_proba_produce_un_brief_complet_cu_sursa_pe_fiecare_camp(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, executor: None
) -> None:
    materiale(tenant)
    modele.stricate.add(
        "preturi"
    )  # modelul „strică” un citat: verificatorul îl respinge, câmpul cade pe răspuns
    sid = interviu_complet(tenant, om)
    assert compune(tenant, om, sid) == "terminat"
    with sesiune_tenant(tenant, om) as db:
        s = sesiuni.sesiune(db, sid)
        b = s.brief
        assert s.stare == "brief_gata" and b is not None
        assert brief.lipsuri(b) == [] and list(s.brief_probleme) == []  # fără câmpuri goale
        assert set(b) == set(brief.CAMPURI)
        for camp, c in b.items():
            assert c["valoare"].strip() and c["surse"], camp  # sursă pe fiecare câmp
        assert b["ce_vinde"]["surse"][0]["tip"] == "pasaj"  # completat din materialele colectate
        pasaj = db.execute(
            text("SELECT text FROM pasaje WHERE id = :i"), {"i": b["ce_vinde"]["surse"][0]["ref"]}
        ).scalar_one()
        assert creier.citat_in_text(b["ce_vinde"]["surse"][0]["citat"], pasaj)
        assert (
            b["preturi"]["surse"][0]["tip"] == "raspuns"
        )  # citatul falsificat a fost respins → răspunsul clientului
        assert "inventat" not in b["preturi"]["surse"][0]["citat"]
        # brieful devine intrare în Creier: compartimentul „brief”, versiune propusă
        iid, nr = completare.trimite_spre_aprobare(db, sid, utilizator_id=om)
        v = creier.citeste(db, iid, nr)
        assert nr == 1 and v.stare == "propus" and v.sursa_tip == SursaTip.DECLARATIE_CLIENT.value
        assert creier.intrare(db, iid).compartiment == Compartiment.BRIEF.value
        assert sesiuni.sesiune(db, sid).stare == "trimis"
        # poate începe o sesiune nouă (reînnoirea brieful) fără să atingă versiunea 1
        s2 = sesiuni.deschide(db, tenant_id=tenant, utilizator_id=om)
        assert s2.id != sid


def test_brief_cu_campuri_goale_nu_poate_fi_trimis_spre_aprobare(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, executor: None
) -> None:
    sid = interviu_complet(tenant, om, suprascrie={"obiectiv": "Nu știu", "ton": "-"})
    assert compune(tenant, om, sid) == "terminat"
    with sesiune_tenant(tenant, om) as db:
        s = sesiuni.sesiune(db, sid)
        assert any("Obiectiv pe 90 de zile" in p for p in s.brief_probleme) and any(
            "Ton dorit" in p for p in s.brief_probleme
        )
        with pytest.raises(creier.PoartaInchisa) as exc:
            completare.trimite_spre_aprobare(db, sid, utilizator_id=om)
        assert len(exc.value.probleme) == 2
        assert (
            db.execute(
                text("SELECT count(*) FROM creier_intrari WHERE tenant_id = :t AND compartiment = 'brief'"),
                {"t": tenant},
            ).scalar_one()
            == 0
        )
        # nici pe calea generică a Creierului (panou, alt serviciu) un brief incomplet nu devine „propus” / „aprobat”
        with pytest.raises(creier.PoartaInchisa):
            creier.creeaza_intrare(db, tenant_id=tenant, compartiment=Compartiment.BRIEF, cheie="brief",
                                   continut=s.brief or {}, sursa=Sursa(SursaTip.OM), utilizator_id=om)  # fmt: skip
        i, v = creier.creeaza_intrare(db, tenant_id=tenant, compartiment=Compartiment.BRIEF, cheie="manual",
                                      continut=s.brief or {}, sursa=Sursa(SursaTip.OM), utilizator_id=om, propune=False)  # fmt: skip
        with pytest.raises(creier.PoartaInchisa):
            creier.trimite_spre_aprobare(db, i.id, v.nr, utilizator_id=om)
        # operatorul completează câmpurile; abia atunci brieful poate trece
        completare.seteaza_camp(
            db, sid, "obiectiv_90_zile", "Să ajungem la 60 de abonamente noi în 90 de zile.", utilizator_id=om
        )
        with pytest.raises(creier.PoartaInchisa):
            completare.trimite_spre_aprobare(db, sid, utilizator_id=om)
        rest = completare.seteaza_camp(
            db, sid, "ton_dorit", "Prietenos și simplu, ca un barista care explică.", utilizator_id=om
        )
        assert rest == []
        iid, nr = completare.trimite_spre_aprobare(db, sid, utilizator_id=om)
        assert creier.citeste(db, iid, nr).stare == "propus"
        assert "operator" in {x["tip"] for x in sesiuni.sesiune(db, sid).brief["ton_dorit"]["surse"]}  # type: ignore[index]


def test_brieful_nu_se_compune_inainte_de_terminarea_interviului(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals
) -> None:
    with sesiune_tenant(tenant, om) as db:
        s = sesiuni.deschide(db, tenant_id=tenant, utilizator_id=om)
        with pytest.raises(onboarding.EroareOnboarding):
            completare.compune(db, s.id, utilizator_id=om)
        with pytest.raises(onboarding.EroareOnboarding):
            completare.trimite_spre_aprobare(db, s.id, utilizator_id=om)
