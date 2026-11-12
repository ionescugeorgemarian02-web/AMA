"""F4.5 — profilul de brand. „Gata când” (în teste, cu brandul fictiv): propunere (3 variante) → alegere → aprobare, iar
ghidul aprobat este citit de constructorul de context în secțiunea ghidului. Modelul este FALS (# SIMULAT, scriptat).
Aprobarea reală a profilului CariereAI / BigBrain rămâne a proprietarului."""

# ruff: noqa: F811
import copy
import datetime as dt
import uuid
from typing import Any

import pytest

from app import creier
from app.creier import context
from app.creier.compartimente import Compartiment, SursaTip
from app.creier.versiuni import Sursa
from app.db import sesiune_tenant
from app.onboarding import fluxuri, ghid
from app.operare import motor
from tests.furnizor_fals import CerereInregistrata
from tests.integration.test_onboarding_interviu import compune, interviu_complet, materiale
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401
from tests.onboarding_utile import ModelFals, model_fals, modele, raspuns_json  # noqa: F401

pytestmark = pytest.mark.db


def varianta(nume: str, ton: str, interzis: list[str], **suprascrie: Any) -> dict[str, Any]:
    v: dict[str, Any] = {
        "nume": nume,
        "descriere": f"Brandul sună {ton}, ca un barista care explică pe îndelete și nu se grăbește.",
        "reguli_da": [f"Spune pe nume ce e în pachet ({ton})", "Dă data prăjirii"],
        "reguli_nu": ["Nu promite efecte medicale", "Nu compara cu numele altor firme"],
        "vocabular_preferat": ["proaspăt", "prăjit în loturi mici", "degustare"],
        "vocabular_interzis": interzis,
        "exemple": [
            {"canal": "facebook", "text": f"Sâmbătă la 11:00 facem degustare gratuită la cafenea ({ton})."},
            {
                "canal": "email",
                "text": f"Salut! Pachetul tău de cafea pleacă marți, proaspăt prăjit ({ton}).",
            },
            {
                "canal": "site",
                "text": f"Prăjim în loturi mici, ca fiecare pachet să ajungă la tine proaspăt ({ton}).",
            },
        ],
    }
    v.update(suprascrie)
    return v


def tre_variante(**strica: Any) -> list[dict[str, Any]]:
    v = [
        varianta("Barista prietenos", "cald", ["ieftin", "miraculos"]),
        varianta("Expertul calm", "calm", ["ieftin", "revoluționar"]),
        varianta("Vecinul vesel", "vesel", ["ieftin", "garantat"]),
    ]
    if strica:
        v[strica.pop("index", 1)].update(strica)
    return v


def inregistreaza(modele: ModelFals, variante: list[dict[str, Any]]) -> None:
    def handler(_c: CerereInregistrata) -> str:
        return raspuns_json(variante=variante)

    modele.handlere["Propune trei variante de ton"] = handler


def brief_aprobat(tenant: uuid.UUID, om: uuid.UUID) -> None:
    from app.onboarding import completare

    sid = interviu_complet(tenant, om)
    assert compune(tenant, om, sid) == "terminat"
    with sesiune_tenant(tenant, om) as db:
        iid, nr = completare.trimite_spre_aprobare(db, sid, utilizator_id=om)
        creier.aproba(db, iid, nr, utilizator_id=om)


def propune(tenant: uuid.UUID, om: uuid.UUID, cheie: str) -> str:
    job = fluxuri.trimite_propunerea_de_ton(tenant, om, cheie=cheie)
    return motor.asteapta_flux(job, timeout_sec=60).stare.value


def ghid_in_pachet(tenant: uuid.UUID) -> tuple[Any, str]:
    with sesiune_tenant(tenant) as db:
        p = context.construieste(
            db,
            tenant_id=tenant,
            tip_sarcina="postare_facebook",
            intrebare="Postare despre cafea",
            salveaza=False,
            la=dt.datetime.now(dt.UTC) + dt.timedelta(seconds=5),
        )
    return p, context.ca_text(p)


def test_propunere_alegere_aprobare_si_ghidul_ajunge_in_pachetul_de_context(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, executor: None
) -> None:
    materiale(tenant)
    inregistreaza(modele, tre_variante())
    brief_aprobat(tenant, om)
    p0, _ = ghid_in_pachet(tenant)
    assert "ghid_brand" in p0.lipsuri and not p0.sectiune("ghid")  # înainte: lipsa spusă explicit
    assert propune(tenant, om, f"ton:{tenant}:1") == "terminat"
    with sesiune_tenant(tenant) as db:
        v = ghid.variante(db, tenant)
        assert [x.nr for x in v] == [1, 2, 3] and len({x.grup_id for x in v}) == 1
        assert all(
            len(x.continut["exemple"]) >= 3 and len({e["canal"] for e in x.continut["exemple"]}) >= 3
            for x in v
        )
        assert all(
            x.continut["reguli_da"] and x.continut["reguli_nu"] and x.continut["vocabular_interzis"]
            for x in v
        )
        assert v[0].brief_versiune == 1
    with sesiune_tenant(
        tenant, om
    ) as db:  # omul alege varianta 2: devine propunere, nu intră încă în context
        iid, nr = ghid.alege(db, tenant, utilizator_id=om, varianta=2)
        assert creier.citeste(db, iid, nr).stare == "propus"
    p1, _ = ghid_in_pachet(tenant)
    assert "ghid_brand" in p1.lipsuri  # un ghid doar propus nu intră în context
    with sesiune_tenant(tenant, om) as db:
        creier.aproba(db, iid, nr, utilizator_id=om)
        assert [x.nr for x in ghid.variante(db, tenant) if x.ales] == [2]
    p2, text = ghid_in_pachet(tenant)
    assert "ghid_brand" not in p2.lipsuri
    [e] = p2.sectiune("ghid")
    assert e.id == str(iid) and e.versiune == 1
    assert (
        "Expertul calm" in text
        and "Nu promite efecte medicale" in text
        and "Vocabular interzis: ieftin, revoluționar" in text
    )
    assert "## Ghid de brand (aprobat)" in text and "[email]" in text


def test_combinarea_si_editarea_creeaza_versiuni_noi_si_versiunea_aprobata_ramane_pana_la_noua_aprobare(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, executor: None
) -> None:
    inregistreaza(modele, tre_variante())
    brief_aprobat(tenant, om)
    assert propune(tenant, om, f"ton:{tenant}:2") == "terminat"
    with sesiune_tenant(tenant, om) as db:
        iid, n1 = ghid.alege(db, tenant, utilizator_id=om, varianta=1)
        creier.aproba(db, iid, n1, utilizator_id=om)
        _, n2 = ghid.alege(
            db, tenant, utilizator_id=om,
            combina={"descriere": 3, "reguli": 1, "vocabular": 2, "exemple": 2},
            editari={"nume": "Barista vesel"},
        )  # fmt: skip
        v2 = creier.citeste(db, iid, n2)
        assert n2 == n1 + 1 and v2.stare == "propus" and v2.continut["origine"] == "editat"
        assert v2.continut["din_variante"] == [1, 2, 3] or sorted(v2.continut["din_variante"]) == [1, 2, 3]
        assert v2.continut["vocabular_interzis"] == ["ieftin", "revoluționar"]  # vocabularul variantei 2
        assert creier.versiune_aprobata(db, iid).nr == n1  # type: ignore[union-attr]
    _, text = ghid_in_pachet(tenant)
    assert "Barista prietenos" in text and "Barista vesel" not in text  # încă versiunea aprobată
    with sesiune_tenant(tenant, om) as db:
        creier.aproba(db, iid, n2, utilizator_id=om)
    assert "Barista vesel" in ghid_in_pachet(tenant)[1]


def test_alegerea_cere_variante_si_o_combinatie_valida(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals
) -> None:
    with sesiune_tenant(tenant, om) as db:
        with pytest.raises(creier.RegulaCreier, match="nu există variante"):
            ghid.alege(db, tenant, utilizator_id=om, varianta=1)
        with pytest.raises(creier.RegulaCreier, match="brieful nu este aprobat"):
            ghid.propune_variante(db, tenant_id=tenant, utilizator_id=om)


def test_variantele_care_incalca_verificarile_sunt_refuzate_si_nu_se_salveaza(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, executor: None
) -> None:
    brief_aprobat(tenant, om)
    exemple = copy.deepcopy(tre_variante()[1]["exemple"])
    exemple[0]["text"] = (
        "Cafea ieftin și bună, doar azi la cafenea."  # folosește vocabular interzis („ieftin”)
    )
    inregistreaza(modele, tre_variante(exemple=exemple))
    assert (
        propune(tenant, om, f"ton:{tenant}:3") == "terminat"
    )  # fluxul se încheie curat, fără variante salvate
    with sesiune_tenant(tenant) as db:
        assert ghid.variante(db, tenant) == []
    with (
        sesiune_tenant(tenant, om) as db,
        pytest.raises(ghid.VariantaInvalida, match="vocabular interzis: ieftin"),
    ):
        ghid.propune_variante(db, tenant_id=tenant, utilizator_id=om)
    scurt = list(tre_variante()[1]["exemple"])
    for e in scurt:
        e["canal"] = "facebook"  # toate pe același canal
    inregistreaza(modele, tre_variante(exemple=scurt))
    assert propune(tenant, om, f"ton:{tenant}:4") == "terminat"
    with sesiune_tenant(tenant) as db:
        assert ghid.variante(db, tenant) == []
    with sesiune_tenant(tenant, om) as db, pytest.raises(ghid.VariantaInvalida, match="cel puțin 3 canale"):
        ghid.propune_variante(db, tenant_id=tenant, utilizator_id=om)


def test_ghidul_trebuie_sa_respecte_schema_si_verificarile_la_alegere(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, executor: None
) -> None:
    inregistreaza(modele, tre_variante())
    brief_aprobat(tenant, om)
    assert propune(tenant, om, f"ton:{tenant}:5") == "terminat"
    with sesiune_tenant(tenant, om) as db:
        with pytest.raises(ghid.VariantaInvalida):  # o editare care scoate exemplele sub minim
            ghid.alege(
                db,
                tenant,
                utilizator_id=om,
                varianta=1,
                editari={"exemple": [{"canal": "email", "text": "Un singur exemplu scris"}]},
            )
        with pytest.raises(
            ghid.VariantaInvalida
        ):  # o editare care introduce un cuvânt interzis într-un exemplu
            ghid.alege(
                db,
                tenant,
                utilizator_id=om,
                varianta=1,
                editari={"vocabular_interzis": ["degustare", "ieftin"]},
            )
        assert (
            creier.gaseste_intrare(db, tenant_id=tenant, compartiment=Compartiment.PROFIL_BRAND, cheie="ghid")
            is None
        )


def test_un_profil_de_alt_fel_se_randeaza_ca_inainte(tenant: uuid.UUID, om: uuid.UUID) -> None:
    with sesiune_tenant(tenant, om) as db:
        i, v = creier.creeaza_intrare(
            db, tenant_id=tenant, compartiment=Compartiment.PROFIL_BRAND, cheie="vechi",
            continut={"ton": "cald și simplu"}, sursa=Sursa(SursaTip.OM), utilizator_id=om,
        )  # fmt: skip
        creier.aproba(db, i.id, v.nr, utilizator_id=om)
    _, text = ghid_in_pachet(tenant)
    assert "cald și simplu" in text
