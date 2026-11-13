"""F4.6 — registrul de fapte și catalogul de oferte pe Postgres real. „Gata când”: fiecare fapt are sursă (constrângere în
bază), iar niciun fapt neaprobat nu intră în context: singura funcție de citire pentru context (`pentru_context`) întoarce
doar faptele aprobate și valabile la data cerută."""

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from app import cercetare, creier
from app.creier import fapte, oferte
from app.creier.compartimente import SursaTip
from app.creier.fapte import CitatNegasit, StareFapt
from app.creier.versiuni import RegulaCreier, Sursa
from app.db import sesiune_agentie, sesiune_tenant
from tests import materiale_zorilor as mz

pytestmark = pytest.mark.db
T0 = dt.datetime(2026, 11, 12, 10, 0, tzinfo=dt.UTC)
PRODUSE = mz.PAGINI["/produse"][1]


def ore(n: float) -> dt.datetime:
    return T0 + dt.timedelta(hours=n)


def continut(afirmatie: str, tip: str = "caracteristica", **valoare: object) -> dict[str, object]:
    c: dict[str, object] = {"tip": tip, "subiect": "Cafea", "afirmatie": afirmatie}
    if valoare:
        c["valoare"] = valoare
    return c


def declaratie(om: uuid.UUID) -> Sursa:
    return Sursa(SursaTip.DECLARATIE_CLIENT)


@pytest.fixture
def pasaj(tenant: uuid.UUID) -> tuple[uuid.UUID, str]:
    """Un pasaj real (din materialele brandului fictiv), pentru fapte cu sursă verificabilă."""
    with sesiune_tenant(tenant) as db:
        sid = cercetare.creeaza_sursa(
            db, tenant_id=tenant, tip="manual", statut_cod="material_client", nume="M"
        ).id
        cercetare.adauga_text(db, tenant_id=tenant, sursa_id=sid, titlu="Produse", text="\n\n".join(PRODUSE))
        creier.pregateste_sursa(db, sid)
        p = db.execute(
            text("SELECT id, text FROM pasaje WHERE sursa_id = :s ORDER BY pozitie LIMIT 1"), {"s": sid}
        ).one()
    return p[0], p[1]


# --- sursă obligatorie


def test_un_fapt_nu_exista_fara_sursa_nici_in_serviciu_nici_in_baza(
    tenant: uuid.UUID, om: uuid.UUID, admin_engine: Engine, pasaj: tuple[uuid.UUID, str]
) -> None:
    pid, _ = pasaj
    c = continut("Cafeaua se prăjește marți")
    with sesiune_tenant(tenant, om) as db:
        for sursa in (Sursa(SursaTip.OM), Sursa(SursaTip.SISTEM), Sursa(SursaTip.AGREGAT)):
            with pytest.raises(RegulaCreier):  # sursele permise: pasaj, document, URL, declarația clientului
                fapte.propune_fapt(db, tenant_id=tenant, continut=c, sursa=sursa, utilizator_id=om)
        with pytest.raises(CitatNegasit, match="citat_absent"):  # material fără citat
            fapte.propune_fapt(db, tenant_id=tenant, continut=c, sursa=Sursa(SursaTip.PASAJ, ref=str(pid)))
        with pytest.raises(CitatNegasit, match="sursa_inexistenta"):
            fapte.propune_fapt(
                db,
                tenant_id=tenant,
                continut=c,
                sursa=Sursa(SursaTip.PASAJ, ref=str(uuid.uuid4()), citat="Etiopia Guji"),
            )
        with pytest.raises(RegulaCreier):  # declarația clientului cere autorul
            fapte.propune_fapt(db, tenant_id=tenant, continut=c, sursa=Sursa(SursaTip.DECLARATIE_CLIENT))
    # în bază: nicio versiune fără tip de sursă; material fără referință nu intră
    with sesiune_tenant(tenant, om) as db:
        i, _, _ = fapte.propune_fapt(
            db, tenant_id=tenant, continut=continut("Program L-V"), sursa=declaratie(om), utilizator_id=om
        )
    inserare = (
        "INSERT INTO creier_versiuni (id, intrare_id, tenant_id, nr, continut, stare, sursa_tip, sursa_ref, propus_la) "
        "VALUES (gen_random_uuid(), :i, :t, 9, '{}', 'propus', :s, :r, now())"
    )
    for sursa_tip, ref in ((None, None), ("pasaj", None), ("document", None), ("url", None), ("magie", "x")):
        with pytest.raises(DBAPIError), admin_engine.begin() as cn:
            cn.execute(text(inserare), {"i": i.id, "t": tenant, "s": sursa_tip, "r": ref})


def test_citatul_trebuie_sa_apara_literal_in_pasaj(
    tenant: uuid.UUID, om: uuid.UUID, pasaj: tuple[uuid.UUID, str]
) -> None:
    pid, text_pasaj = pasaj
    citat = text_pasaj.split(".")[0] + "."  # prima propoziție: „Etiopia Guji, natural, 250 g: 49 lei.”
    ok = Sursa(SursaTip.PASAJ, ref=str(pid), citat=citat, detalii={"pozitie": 0})
    c = continut("Etiopia Guji 250 g costă 49 lei", "pret", numar="49", moneda="RON", unitate="250 g")
    with sesiune_tenant(tenant) as db:
        for rau, cod in (
            (citat.replace("49", "39"), "citat_negasit"),
            ("Etiopia Guji este cea mai bună cafea din lume", "citat_negasit"),
            ("scurt", "citat_scurt"),
        ):
            with pytest.raises(CitatNegasit) as exc:
                fapte.propune_fapt(
                    db, tenant_id=tenant, continut=c, sursa=Sursa(SursaTip.PASAJ, ref=str(pid), citat=rau)
                )
            assert exc.value.cod == cod
        with pytest.raises(CitatNegasit) as exc:  # cifra afirmată lipsește din citat
            fapte.propune_fapt(db, tenant_id=tenant, continut={**c, "valoare": {"numar": "59"}}, sursa=ok)
        assert exc.value.cod == "valoare_absenta_din_citat"
        _, ver, creat = fapte.propune_fapt(db, tenant_id=tenant, continut=c, sursa=ok)
        assert creat and ver.stare == "propus" and ver.sursa_tip == "pasaj" and ver.sursa_citat == citat
        assert ver.continut["valoare"]["numar"] == "49"  # număr exact, nu float


def test_aceeasi_afirmatie_nu_se_propune_de_doua_ori(tenant: uuid.UUID, om: uuid.UUID) -> None:
    with sesiune_tenant(tenant, om) as db:
        a, _, nou1 = fapte.propune_fapt(
            db,
            tenant_id=tenant,
            continut=continut("Livrăm marți și vineri"),
            sursa=declaratie(om),
            utilizator_id=om,
        )
        b, _, nou2 = fapte.propune_fapt(
            db,
            tenant_id=tenant,
            continut=continut("livram MARTI si vineri"),
            sursa=declaratie(om),
            utilizator_id=om,
        )
    assert (nou1, nou2) == (True, False) and a.id == b.id


# --- stări și citirea pentru context


def propus(tenant: uuid.UUID, om: uuid.UUID, afirmatie: str, **kw: object):  # type: ignore[no-untyped-def]
    with sesiune_tenant(tenant, om) as db:
        i, v, _ = fapte.propune_fapt(
            db,
            tenant_id=tenant,
            continut=continut(afirmatie),
            sursa=declaratie(om),
            utilizator_id=om,
            acum=ore(0),
            **kw,  # type: ignore[arg-type]
        )
        return i.id, v.nr


def aprobat(tenant: uuid.UUID, om: uuid.UUID, afirmatie: str, la: float = 1, **kw: object) -> uuid.UUID:
    iid, nr = propus(tenant, om, afirmatie, **kw)
    with sesiune_tenant(tenant, om) as db:
        fapte.aproba_fapt(db, iid, nr, utilizator_id=om, acum=ore(la))
    return iid


def in_context(tenant: uuid.UUID, la: dt.datetime) -> set[str]:
    with sesiune_tenant(tenant) as db:
        return {f.afirmatie for f in fapte.pentru_context(db, tenant, la)}


def test_niciun_fapt_neaprobat_sau_nevalabil_nu_intra_in_context(tenant: uuid.UUID, om: uuid.UUID) -> None:
    propus(tenant, om, "Fapt propus, neaprobat")
    aprobat(tenant, om, "Fapt aprobat și valabil")
    aprobat(tenant, om, "Fapt valabil de mâine", valabil_de_la=ore(48))
    aprobat(tenant, om, "Fapt cu valabilitate depășită, încă neexpirat de job", valabil_pana_la=ore(5))
    aprobat(tenant, om, "Fapt valabil până peste o lună", valabil_pana_la=ore(24 * 30))
    resp, nr = propus(tenant, om, "Fapt respins")
    ret = aprobat(tenant, om, "Fapt retras după aprobare")
    with sesiune_tenant(tenant, om) as db:
        fapte.respinge_fapt(db, resp, nr, utilizator_id=om, motiv="nu e corect", acum=ore(2))
        fapte.retrage_fapt(db, ret, 1, utilizator_id=om, motiv="nu mai e valabil", acum=ore(2))
    ceruta = ore(10)
    assert in_context(tenant, ceruta) == {"Fapt aprobat și valabil", "Fapt valabil până peste o lună"}
    # aceeași interogare, la alte momente
    assert in_context(tenant, ore(0.5)) == set()  # nimic nu era aprobat încă
    assert in_context(tenant, ore(1.5)) == {
        "Fapt aprobat și valabil", "Fapt cu valabilitate depășită, încă neexpirat de job",
        "Fapt valabil până peste o lună", "Fapt retras după aprobare",
    }  # fmt: skip
    assert in_context(tenant, ore(24 * 3)) == {
        "Fapt aprobat și valabil",
        "Fapt valabil de mâine",
        "Fapt valabil până peste o lună",
    }
    with sesiune_tenant(tenant) as db, pytest.raises(RegulaCreier):
        fapte.pentru_context(db, tenant, dt.datetime(2026, 11, 12, 10, 0))  # data cere fus orar


def test_stari_fapt_propus_aprobat_respins_expirat_inlocuit_retras(tenant: uuid.UUID, om: uuid.UUID) -> None:
    a, _ = propus(tenant, om, "Stare: propus")
    ap = aprobat(tenant, om, "Stare: aprobat")
    r, rn = propus(tenant, om, "Stare: respins")
    ex = aprobat(tenant, om, "Stare: expirat", valabil_pana_la=ore(3))
    inl = aprobat(tenant, om, "Stare: înlocuit")
    ret = aprobat(tenant, om, "Stare: retras")
    with sesiune_tenant(tenant, om) as db:
        fapte.respinge_fapt(db, r, rn, utilizator_id=om, motiv="greșit")
        fapte.retrage_fapt(db, ret, 1, utilizator_id=om, motiv="vechi")
        fapte.expira(db, ore(4))
        v2 = fapte.modifica_fapt(
            db, inl, continut=continut("Stare: înlocuit, varianta nouă"), sursa=declaratie(om), utilizator_id=om,
            motiv="corectat",
        )  # fmt: skip
        fapte.aproba_fapt(db, inl, v2.nr, utilizator_id=om)
        stare = lambda i, nr=0: fapte.stare_fapt(creier.istoric(db, i)[nr])  # noqa: E731
        assert (
            stare(a) is StareFapt.PROPUS and stare(ap) is StareFapt.APROBAT and stare(r) is StareFapt.RESPINS
        )
        assert stare(ex) is StareFapt.EXPIRAT and stare(ret) is StareFapt.RETRAS
        assert stare(inl, 0) is StareFapt.INLOCUIT and stare(inl, 1) is StareFapt.APROBAT
        assert fapte.fapt(db, inl).afirmatie == "Stare: înlocuit, varianta nouă"  # ultima versiune
        assert fapte.fapt(db, r).motiv == "greșit"


def test_o_schimbare_de_pret_creeaza_versiune_noua_iar_contextul_vede_pretul_potrivit_momentului(
    tenant: uuid.UUID, om: uuid.UUID
) -> None:
    pret = lambda n: continut(f"Etiopia Guji 250 g costă {n} lei", "pret", numar=str(n), moneda="RON")  # noqa: E731
    with sesiune_tenant(tenant, om) as db:
        i, _, _ = fapte.propune_fapt(
            db, tenant_id=tenant, continut=pret(49), sursa=declaratie(om), utilizator_id=om, acum=ore(0)
        )
        fapte.aproba_fapt(db, i.id, 1, utilizator_id=om, acum=ore(1))
        v2 = fapte.modifica_fapt(
            db, i.id, continut=pret(52), sursa=declaratie(om), utilizator_id=om, motiv="scumpire", acum=ore(5)
        )
        assert v2.nr == 2 and [s.cale for s in creier.diferenta_versiuni(db, i.id, 1, 2)] == [
            "afirmatie",
            "valoare.numar",
        ]
        fapte.aproba_fapt(db, i.id, 2, utilizator_id=om, acum=ore(6))

    def pretul(la: float) -> list[str]:
        with sesiune_tenant(tenant) as db:
            return [str((f.valoare or {}).get("numar")) for f in fapte.pentru_context(db, tenant, ore(la))]

    assert pretul(3) == ["49"] and pretul(10) == ["52"] and pretul(0.5) == []


def test_expirarea_retrage_ce_a_trecut_si_lasa_o_intrebare_pentru_client(
    tenant: uuid.UUID, om: uuid.UUID
) -> None:
    f = aprobat(tenant, om, "Reducere de toamnă 15%", valabil_pana_la=ore(2))
    aprobat(tenant, om, "Fapt fără expirare")
    with sesiune_agentie(om) as db:
        expirate = fapte.expira(db, ore(3))
        assert [e.intrare_id for e in expirate if e.tenant_id == tenant] == [f]
        assert fapte.expira(db, ore(3)) == []  # idempotent
    with sesiune_tenant(tenant) as db:
        assert [x.afirmatie for x in fapte.expirate_de_clarificat(db, tenant)] == ["Reducere de toamnă 15%"]
    assert in_context(tenant, ore(4)) == {"Fapt fără expirare"}
    with sesiune_tenant(
        tenant, om
    ) as db:  # clientul răspunde: o versiune nouă, aprobată → întrebarea dispare
        v2 = fapte.modifica_fapt(
            db,
            f,
            continut=continut("Reducere de iarnă 10%"),
            sursa=declaratie(om),
            utilizator_id=om,
            valabil_pana_la=ore(24 * 60),
        )
        fapte.aproba_fapt(db, f, v2.nr, utilizator_id=om)
        assert fapte.expirate_de_clarificat(db, tenant) == []


# --- catalogul de oferte


def pret_oferta(numar: str, **kw: object) -> dict[str, object]:
    return {
        "tip": "produs",
        "nume": "Etiopia Guji 250 g",
        "pret": {"numar": numar, "moneda": "RON", "unitate": "250 g"},
        **kw,
    }


def test_ofertele_se_leaga_de_fapte_si_intra_in_context_doar_cu_faptele_lor_valabile(
    tenant: uuid.UUID, om: uuid.UUID
) -> None:
    fapt_pret = aprobat(tenant, om, "Etiopia Guji 250 g costă 49 lei", valabil_pana_la=ore(10))
    with sesiune_tenant(tenant, om) as db:
        with pytest.raises(RegulaCreier):  # fapt inexistent
            oferte.propune_oferta(
                db,
                tenant_id=tenant,
                continut=pret_oferta("49", fapte=[str(uuid.uuid4())]),
                sursa=declaratie(om),
                utilizator_id=om,
            )
        with pytest.raises(RegulaCreier):  # nu e un UUID
            oferte.propune_oferta(
                db,
                tenant_id=tenant,
                continut=pret_oferta("49", fapte=["abc"]),
                sursa=declaratie(om),
                utilizator_id=om,
            )
        i, v, creata = oferte.propune_oferta(
            db, tenant_id=tenant, continut=pret_oferta("49", fapte=[str(fapt_pret)], garantie="schimb dacă nu ți-a plăcut"),
            sursa=declaratie(om), utilizator_id=om, acum=ore(0),
        )  # fmt: skip
        assert creata and v.stare == "propus" and v.continut["pret"]["numar"] == "49"
        assert (
            oferte.propune_oferta(
                db, tenant_id=tenant, continut=pret_oferta("49"), sursa=declaratie(om), utilizator_id=om
            )[2]
            is False
        )
        assert oferte.pentru_context(db, tenant, ore(2)) == []  # propusă: nu intră
        oferte.aproba_oferta(db, i.id, 1, utilizator_id=om, acum=ore(1))
        [o] = oferte.pentru_context(db, tenant, ore(2))
        assert o.nume == "Etiopia Guji 250 g" and o.pret["numar"] == "49" and o.fapte == (fapt_pret,)
        assert oferte.pentru_context(db, tenant, ore(12)) == []  # faptul legat nu mai e valabil → nici oferta


def test_promotia_cere_pret_de_referinta_mai_mare_si_prețul_nu_poate_fi_negativ(
    tenant: uuid.UUID, om: uuid.UUID
) -> None:
    from pydantic import ValidationError

    with sesiune_tenant(tenant, om) as db:
        for rau in (
            {"tip": "promotie", "nume": "Toamnă", "pret": {"numar": "40"}},
            {"tip": "promotie", "nume": "Toamnă", "pret": {"numar": "40"}, "pret_referinta": {"numar": "40"}},
            {"tip": "produs", "nume": "X", "pret": {"numar": "-1"}},
            {"tip": "produs", "nume": "X", "pret": {"numar": "1", "moneda": "lei"}},
        ):
            with pytest.raises((ValidationError, ValueError)):
                oferte.propune_oferta(
                    db, tenant_id=tenant, continut=rau, sursa=declaratie(om), utilizator_id=om
                )
        _, v, _ = oferte.propune_oferta(
            db, tenant_id=tenant, continut={"tip": "promotie", "nume": "Toamnă", "pret": {"numar": "40"}, "pret_referinta": {"numar": "49"}},
            sursa=declaratie(om), utilizator_id=om,
        )  # fmt: skip
        assert Decimal(v.continut["pret_referinta"]["numar"]) == 49


def test_oferta_dintr_un_pasaj_isi_verifica_citatul_si_pretul(
    tenant: uuid.UUID, om: uuid.UUID, pasaj: tuple[uuid.UUID, str]
) -> None:
    pid, text_pasaj = pasaj
    citat = text_pasaj.split(".")[0] + "."
    with sesiune_tenant(tenant, om) as db:
        with pytest.raises(CitatNegasit):  # prețul din ofertă (59) nu apare în citat
            oferte.propune_oferta(
                db,
                tenant_id=tenant,
                continut=pret_oferta("59"),
                sursa=Sursa(SursaTip.PASAJ, ref=str(pid), citat=citat),
            )
        _, v, _ = oferte.propune_oferta(
            db,
            tenant_id=tenant,
            continut=pret_oferta("49"),
            sursa=Sursa(SursaTip.PASAJ, ref=str(pid), citat=citat),
        )
        assert v.sursa_tip == "pasaj"


def test_programarea_zilnica_a_expirarii_si_anuntul_catre_agentie(
    tenant: uuid.UUID, om: uuid.UUID, executor: None, anunturi: object
) -> None:
    from app.creier import fluxuri
    from app.operare import motor
    from tests.integration.utile_productie import AnunturiFalse

    assert isinstance(anunturi, AnunturiFalse)
    fluxuri.declara_programari()
    [p] = [p for p in motor.programari_declarate() if p.nume == fluxuri.NUME_EXPIRARE]
    assert p.cron.endswith("10 5 * * *") and p.coada == "io"
    aprobat(tenant, om, "Promoție de weekend -20%", valabil_pana_la=ore(-24 * 365 * 30))  # expirat de mult
    job = motor.trimite(
        fluxuri.expira_valabilitati, dt.datetime.now(dt.UTC), None, cheie=f"expirare:{uuid.uuid4()}"
    )
    assert motor.asteapta_flux(job, timeout_sec=30).stare is motor.StareJob.TERMINAT
    [titlu] = [t for t in anunturi.titluri() if t.startswith("Valabilitate expirată")]
    assert "Valabilitate expirată: " in titlu
    assert "Întreabă clientul" in next(x[2] for x in anunturi.trimise if x[1] == titlu)
    assert in_context(tenant, dt.datetime.now(dt.UTC)) == set()
