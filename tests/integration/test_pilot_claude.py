# ruff: noqa: F811
"""Pilot manual pe bază temporară, cu informații fictive și model Anthropic real."""

import datetime as dt
import json
import os
import shutil
import uuid
from pathlib import Path

import pytest
from sqlalchemy import Engine, select, text

from app import cercetare, continut, creier, validare
from app.continut import pipeline
from app.db import sesiune_tenant
from app.media import cereri, compozitor, fluxuri, montaj, regizor, sabloane, voce
from app.onboarding import citate, completare, ghid, piata, public, strategie
from app.operare import motor
from tests.gateway_utile import FabricaModele
from tests.integration.test_onboarding_interviu import interviu_complet
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401
from tests.pilot_clienti import CAZURI
from tests.validare_utile import fapt_aprobat, oferta_aprobata

pytestmark = [pytest.mark.db, pytest.mark.skipif(os.getenv("AMA_PILOT_CLAUDE") != "1", reason="pilot manual")]


def test_campanie(
    tenant: uuid.UUID,
    om: uuid.UUID,
    fabrica_modele: FabricaModele,
    admin_engine: Engine,
    executor: None,
) -> None:
    caz = os.environ["AMA_PILOT_CAZ"]
    dosar = CAZURI[caz]
    iesire = Path(os.environ["AMA_PILOT_IESIRE"])
    iesire.mkdir(parents=True, exist_ok=True)

    def salveaza(nume: str, date: object) -> None:
        (iesire / nume).write_text(json.dumps(date, ensure_ascii=False, indent=2, default=str))

    raport = {
        "executate": [],
        "simulate": ["date client", "aprobările umane", "alinierea subtitrării pe textul cunoscut"],
        "omise": ["publicare externă", "judecător independent", "atribuire comercială live"],
        # F-editorial: o oprire legitimă (material lipsă) e un rezultat, nu o cădere a pilotului
        "blocate": [],
    }

    def etapa(nume: str) -> None:
        raport["executate"].append(nume)
        salveaza("raport.json", raport)

    salveaza("raport.json", raport)
    assert os.environ.get("AMA_CHEIE_PILOT"), "Configurează secretul ANTHROPIC_API_KEY."
    ident = os.environ["AMA_PILOT_MODEL"].strip()
    assert ident, "Configurează modelul Anthropic."
    f = fabrica_modele.furnizor(
        tip_api="anthropic", url_baza="https://api.anthropic.com", cheie_env="AMA_CHEIE_PILOT", platit=True
    )
    m = fabrica_modele.model(f, identificator=ident, nivel="T3", capabilitati=["iesire_structurata"])
    with admin_engine.begin() as conn:
        for profil in ("clasificare", "strategie", "creatie", "rescriere"):
            assert (
                conn.execute(
                    text(
                        "UPDATE gateway_profiluri SET lant=:lant, lant_degradare='{}', la_epuizare='amana' "
                        "WHERE nume=:profil RETURNING nume"
                    ),
                    {"lant": [m.cod], "profil": profil},
                ).scalar_one()
                == profil
            )
    sid = interviu_complet(tenant, om, suprascrie=dosar.raspunsuri)
    with sesiune_tenant(tenant, om) as db:
        completare.compune(db, sid, utilizator_id=om)
        iid, nr = completare.trimite_spre_aprobare(db, sid, utilizator_id=om)
        creier.aproba(db, iid, nr, utilizator_id=om)
        ghid.propune_variante(db, tenant_id=tenant, utilizator_id=om)
        iid, nr = ghid.alege(db, tenant, utilizator_id=om, varianta=1)
        creier.aproba(db, iid, nr, utilizator_id=om)
    etapa("interviu, brief, ton")
    for nume, paragrafe in [("Recenzii", dosar.recenzii), *dosar.concurenti.items()]:
        recenzii = nume == "Recenzii"
        with sesiune_tenant(tenant, om) as db:
            sursa = (
                cercetare.creeaza_sursa(
                    db, tenant_id=tenant, tip="manual", statut_cod="recenzii_client", nume=nume
                )
                if recenzii
                else piata.adauga_concurent(db, tenant_id=tenant, nume=nume, utilizator_id=om)
            )
            cercetare.adauga_text(
                db, tenant_id=tenant, sursa_id=sursa.id, titlu=nume, text="\n\n".join(paragrafe)
            )
            creier.pregateste_sursa(db, sursa.id)
            ids = list(db.scalars(select(creier.Pasaj.id).where(creier.Pasaj.sursa_id == sursa.id)))
        for pid in ids:
            (citate.extrage_din_pasaj if recenzii else piata.extrage_din_pasaj)(tenant, pid)
    fid = fapt_aprobat(
        tenant,
        om,
        "pret",
        dosar.produs,
        dosar.raspunsuri["preturi"],
        valoare={"numar": dosar.pret, "moneda": "RON", "unitate": dosar.unitate},
    )
    oferta_aprobata(
        tenant,
        om,
        dosar.produs,
        dosar.pret,
        destinatie="/produse/guji" if caz == "magazin" else "/programare",
        fapte=[str(fid)],
    )
    for functie in (public.propune_profil, piata.propune_brief, strategie.propune):
        with sesiune_tenant(tenant, om) as db:
            iid, nr = functie(db, tenant_id=tenant, utilizator_id=om)
            v = creier.aproba(db, iid, nr, utilizator_id=om)
            salveaza(f"{functie.__module__.split('.')[-1]}.json", v.continut)
        etapa(functie.__module__)
    with sesiune_tenant(tenant, om) as db:
        cal = continut.calendar.propune(db, tenant_id=tenant, utilizator_id=om, inceput=dt.date.today())
        salveaza("calendar.json", cal.propunere)
        continut.calendar.aproba(db, cal.id, utilizator_id=om)
        alese = {}
        for slot in continut.calendar.intrari(db, cal.id):
            alese.setdefault(slot.tip, slot.livrabil_id)
        assert alese
    etapa("calendar")
    for tip, lid in alese.items():
        assert lid
        stare = pipeline.produ(tenant, lid)
        assert stare == "asteapta_aprobare", stare
        with sesiune_tenant(tenant, om) as db:
            c = validare.continut.citeste(db, lid)
            (iesire / f"{tip}.txt").write_text(c.text)
            titlu = c.campuri.get("hook") or dosar.produs
            if tip == "script_video_scurt":
                cop = next(
                    s for s in sabloane.asigura_sabloane(db, tenant, dosar.marca) if s.tip == "coperta_video"
                )
                _, imagine = compozitor.creeaza(db, tenant, cop, {"titlu": titlu})
                (iesire / f"coperta-{tip}.png").write_bytes(imagine.png)
            # imaginile prin machetele editoriale: foto_dominanta dacă există fotografie, altfel cea tipografică
            b = continut.brief.al_livrabilului(db, lid)
            try:
                exp = compozitor.exporta(
                    db, tenant, dosar.marca, dict(b.continut or {}) if b else {}, {"titlu": titlu}
                )
            except compozitor.MachetaIlizibila as e:
                raport["blocate"].append(
                    {"etapa": f"imagine {tip}", "motiv": "macheta ilizibilă", "detalii": e.probleme}
                )
            else:
                for k, png in enumerate(exp.imagini):
                    (iesire / f"imagine-{tip}-{exp.macheta}-{k + 1}.png").write_bytes(png)
                raport.setdefault("machete", []).append(
                    {"tip": tip, "macheta": exp.macheta, "nota": exp.nota}
                )
            versiune = c.versiune
        if tip == "script_video_scurt":
            job = motor.trimite(
                fluxuri.produce_script,
                str(tenant),
                str(lid),
                str(versiune),
                coada=motor.Coada.GREU,
                cheie=f"pilot-video:{lid}",
            )
            assert motor.asteapta_flux(job, timeout_sec=1800).stare == motor.StareJob.TERMINAT
            with sesiune_tenant(tenant, om) as db:
                activ = montaj.video_verificat(db, tenant, lid, versiune)
                lipsa = cereri.deschise(db, tenant, lid)
                if activ is None and lipsa:  # oprire legitimă: storyboardul cere fotografii reale
                    raport["blocate"].append({
                        "etapa": "video",
                        "motiv": "material lipsă (prezentare fără fotografii reale)",
                        "cereri": [{"scena": x.scena, "subiect": x.subiect, "cerere": x.cerere} for x in lipsa],
                    })  # fmt: skip
                    raport["omise"].append("video: blocat pe material lipsă (vezi „blocate”)")
                else:
                    assert activ, "Exportul video nu a trecut G6."
                    shutil.copyfile(regizor.cale(activ), iesire / "video.mp4")
                # mostra audio, cu vocea folosită la randare
                _, wav = voce.mostra(
                    db,
                    tenant,
                    dosar.marca,
                    f"{dosar.pret} lei",
                    c.campuri.get("cta") or "",
                    voce.PROFIL_RANDARE,
                )
                (iesire / "mostra.wav").write_bytes(wav)
                raport["executate"].append("mostra audio")
        etapa(f"validare și export {tip}")
    if "script_video_scurt" not in alese:
        raport["omise"].append("video: calendarul nu conține acest format")
        salveaza("raport.json", raport)
