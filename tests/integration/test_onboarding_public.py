"""F4.9 — vocea clientului și profilul de public (C4, C5). „Gata când” (în teste, cu brandul fictiv și materiale de probă
inventate): ≥ 20 de citate cu sursă și poziție, verificate literal, fără date personale și fără numele autorilor, apoi
profilul de public aprobat de un om. Modelul este FALS (# SIMULAT). Pentru brandurile reale rămâne la proprietar."""

# ruff: noqa: F811
import re
import uuid
from typing import Any

import pytest
from sqlalchemy import text

from app import cercetare, creier
from app.creier.compartimente import Compartiment
from app.db import sesiune_tenant
from app.onboarding import citate, fluxuri, public
from app.operare import motor
from tests import materiale_zorilor as mz
from tests.furnizor_fals import CerereInregistrata
from tests.integration.test_onboarding_ghid import brief_aprobat
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401
from tests.onboarding_utile import ModelFals, blocuri, model_fals, modele, raspuns_json  # noqa: F401

pytestmark = pytest.mark.db
SEMNATURA = re.compile(r"\s+—\s+[A-ZĂÂÎȘȚ][a-zăâîșț]+ [A-Z]\.$")


def model_citate(modele: ModelFals, **strica: bool) -> None:
    """Modelul scoate din fiecare linie citatul fără semnătură; cu `semnatura=True` o lasă, cu `inventat=True` adaugă un citat inexistent."""

    def handler(c: CerereInregistrata) -> str:
        pasaj = blocuri(c)[0][1]
        citate_ = []
        for linie in pasaj.splitlines():
            linie = linie.strip()
            if len(linie) < 25:
                continue
            t = linie if strica.get("semnatura") else SEMNATURA.sub("", linie)
            citate_.append({"text": t, "tip": "intrebare" if t.endswith("?") else "recenzie", "tema": "cafea",
                            "sentiment": "neutru" if t.endswith("?") else "pozitiv"})  # fmt: skip
        if strica.get("inventat"):
            citate_.append({"text": "Cea mai bună cafea din lume, garantat pe viață, fără nicio îndoială.", "tip": "recenzie",
                            "tema": "inventat", "sentiment": "pozitiv"})  # fmt: skip
        return raspuns_json(citate=citate_)

    modele.handlere["Extrage citate reale din textul"] = handler


def model_profil(modele: ModelFals) -> None:
    def handler(c: CerereInregistrata) -> str:
        ids = re.findall(r"\[([0-9a-f-]{36})\]", blocuri(c)[1][1])
        return raspuns_json(
            profil={
                "segmente": [{"nume": "Iubitori de cafea", "descriere": "Oameni de 25–45 de ani care vor gust bun acasă."},
                             {"nume": "Birouri mici", "descriere": "Echipe care vor cafea bună la sediu, fără bătăi de cap."}],
                "nevoi": ["Cafea proaspătă", "Explicații simple despre gust"],
                "obiectii": ["Prețul mai mare decât la supermarket", "Nu știu ce cafea să aleg"],
                "declansatori": ["Un cadou pentru cineva", "Aparat nou de cafea"],
                "canale": ["facebook", "instagram"],
                "limbaj": ["proaspăt", "gust adevărat", "fără formalități"],
                "dovezi": ids[:4],
            }
        )  # fmt: skip

    modele.handlere["Construiește profilul clientului ideal"] = handler


def sursa_recenzii(tenant: uuid.UUID) -> uuid.UUID:
    with sesiune_tenant(tenant) as db:
        sid = cercetare.creeaza_sursa(
            db, tenant_id=tenant, tip="manual", statut_cod="recenzii_client", nume="Recenzii"
        ).id
        for titlu, linii in mz.recenzii_ca_material().items():
            cercetare.adauga_text(db, tenant_id=tenant, sursa_id=sid, titlu=titlu, text="\n\n".join(linii))
        creier.pregateste_sursa(db, sid)
    return sid


def extrage(tenant: uuid.UUID, sid: uuid.UUID, cheie: str) -> str:
    job = fluxuri.trimite_extragerea_citatelor(tenant, sid, cheie=cheie)
    return motor.asteapta_flux(job, timeout_sec=60).stare.value


def citate_db(tenant: uuid.UUID) -> list[Any]:
    with sesiune_tenant(tenant) as db:
        return [
            (i, v)
            for i, v in creier.lista(db, tenant_id=tenant, compartiment=Compartiment.INSIGHT_PUBLIC)
            if v and v.continut.get("tip") == "citat"
        ]


def test_citatele_au_sursa_si_pozitie_sunt_verificate_literal_fara_date_personale_si_fara_autori(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, executor: None
) -> None:
    model_citate(modele, inventat=True)
    sid = sursa_recenzii(tenant)
    assert extrage(tenant, sid, f"citate:{sid}:1") == "terminat"
    gasite = citate_db(tenant)
    assert len(gasite) >= citate.MINIM_CITATE == 20  # materialul are 24 de recenzii curate
    with sesiune_tenant(tenant) as db:
        for _i, v in gasite:
            assert v.stare == "aprobat" and v.aprobat_prin == "sistem" and v.sursa_tip == "pasaj"
            pasaj = db.execute(text("SELECT text FROM pasaje WHERE id = :i"), {"i": v.sursa_ref}).scalar_one()
            assert (
                creier.citat_in_text(v.continut["text"], pasaj) and v.sursa_citat == v.continut["text"]
            )  # literal
            assert {"document_id", "url", "pozitie", "car_inceput", "car_sfarsit"} <= set(v.sursa_detalii)
            assert not SEMNATURA.search(v.continut["text"])
        rez = citate.extractie.rezumat(db, tenant, sid, citate.REFERINTA_PROMPT)
        assert rez["propuse"] == len(gasite) and rez["respinse"] >= 3  # citatul inventat + email + telefon
        motive = [
            r["motiv"]
            for r in db.execute(
                text("SELECT jsonb_array_elements(respinse) AS r FROM creier_extrageri")
            ).scalars()
        ]
        assert "citat_negasit" in str(motive) and "date_personale" in str(motive)
    toate = " ".join(v.continut["text"] + (v.sursa_citat or "") for _, v in gasite)
    for nume in mz.AUTORI:  # numele autorilor nu se păstrează nicăieri
        assert nume not in toate and nume.split()[0] not in toate
    assert "exemplu.test" not in toate and "0700" not in toate
    # a doua rulare nu cheamă modelul din nou și nu dublează citatele
    apeluri = len(modele.apeluri)
    assert extrage(tenant, sid, f"citate:{sid}:2") == "terminat"
    assert len(modele.apeluri) == apeluri and len(citate_db(tenant)) == len(gasite)


def test_citatele_cu_semnatura_autorului_sunt_respinse(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, executor: None
) -> None:
    model_citate(modele, semnatura=True)
    sid = sursa_recenzii(tenant)
    assert extrage(tenant, sid, f"citate:{sid}:3") == "terminat"
    assert citate_db(tenant) == []  # fiecare linie venea cu „— Nume I.”: toate respinse
    with sesiune_tenant(tenant) as db:
        rez = citate.extractie.rezumat(db, tenant, sid, citate.REFERINTA_PROMPT)
        assert rez["respinse"] >= 24


def test_profilul_de_public_cere_20_de_citate_se_sprijina_pe_ele_si_il_aproba_un_om(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, executor: None
) -> None:
    brief_aprobat(tenant, om)
    model_profil(modele)
    with (
        sesiune_tenant(tenant, om) as db,
        pytest.raises(public.ProfilInvalid, match="cel puțin 20"),
    ):  # fără citate
        public.propune_profil(db, tenant_id=tenant, utilizator_id=om)
    model_citate(modele)
    sid = sursa_recenzii(tenant)
    assert extrage(tenant, sid, f"citate:{sid}:4") == "terminat"
    job = fluxuri.trimite_profilul_de_public(tenant, om, cheie=f"public:{tenant}:1")
    assert motor.asteapta_flux(job, timeout_sec=60).stare.value == "terminat"
    with sesiune_tenant(tenant, om) as db:
        i = creier.gaseste_intrare(
            db, tenant_id=tenant, compartiment=Compartiment.INSIGHT_PUBLIC, cheie=public.CHEIE_PROFIL
        )
        assert i is not None
        v = creier.citeste(db, i.id, 1)
        assert v.stare == "propus" and v.continut["tip"] == "profil_public"
        assert {"segmente", "nevoi", "obiectii", "declansatori", "canale", "limbaj"} <= set(v.continut)
        aprobate = {str(x) for x, _ in citate.citate_aprobate(db, tenant)}
        assert (
            len(v.continut["dovezi"]) >= 3 and set(v.continut["dovezi"]) <= aprobate
        )  # se sprijină pe citate reale
        with pytest.raises(creier.RegulaCreier, match="se aprobă doar de un om"):
            creier.aproba(
                db, i.id, 1, utilizator_id=None, prin_sistem=True
            )  # profilul îl aprobă un om, nu sistemul
        creier.aproba(db, i.id, 1, utilizator_id=om)
        assert creier.versiune_aprobata(db, i.id).continut["limbaj"] == [
            "proaspăt",
            "gust adevărat",
            "fără formalități",
        ]  # type: ignore[union-attr]
        assert len(citate.citate_aprobate(db, tenant)) >= 20


def test_poarta_profilului_refuza_dovezi_straine_si_elemente_lipsa(tenant: uuid.UUID, om: uuid.UUID) -> None:
    ok = {"tip": "profil_public", "segmente": [{"nume": "Segment", "descriere": "Descriere suficient de lungă"}],
          "nevoi": ["a1", "a2"], "obiectii": ["b1", "b2"], "declansatori": ["c1", "c2"], "canale": ["email"],
          "limbaj": ["x", "y", "z"], "dovezi": [str(uuid.uuid4()) for _ in range(3)]}  # fmt: skip
    assert public.probleme_profil(None, None, ok) == []  # schema singură (fără bază)
    for camp in ("segmente", "nevoi", "obiectii", "declansatori", "canale", "limbaj", "dovezi"):
        lipsa = {k: v for k, v in ok.items() if k != camp}
        assert public.probleme_profil(None, None, lipsa), camp
    with sesiune_tenant(tenant, om) as db:
        probleme = public.probleme_profil(db, tenant, ok)
        assert any("0 citate aprobate" in p for p in probleme) and any(
            "dovezi care nu sunt citate" in p for p in probleme
        )
