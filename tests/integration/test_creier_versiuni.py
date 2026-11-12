"""F4.1 — versiunile Creierului pe Postgres real. „Gata când”: o schimbare creează o versiune nouă, iar cea
veche rămâne citibilă și nemodificabilă (impus în bază)."""

import datetime as dt
import uuid

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from app import creier
from app.creier import Compartiment, Nivel, Sursa, SursaTip
from app.db import sesiune_agentie, sesiune_tenant

pytestmark = pytest.mark.db
T0 = dt.datetime(2026, 11, 12, 10, 0, tzinfo=dt.UTC)
OM = Sursa(SursaTip.OM)


def minute(n: int) -> dt.datetime:
    return T0 + dt.timedelta(minutes=n)


def profil(tenant: uuid.UUID, om: uuid.UUID, **kw: object) -> tuple[uuid.UUID, int]:
    with sesiune_tenant(tenant, om) as db:
        i, v = creier.creeaza_intrare(
            db, tenant_id=tenant, compartiment=Compartiment.PROFIL_BRAND, cheie="profil",
            continut={"pozitionare": "Cafea de specialitate din Brașov", "ton": ["cald"]},
            sursa=OM, utilizator_id=om, acum=minute(0), **kw,
        )  # fmt: skip
        return i.id, v.nr


def test_o_schimbare_creeaza_o_versiune_noua_iar_cea_veche_ramane_citibila_si_nemodificabila(
    tenant: uuid.UUID, om: uuid.UUID, admin_engine: Engine
) -> None:
    iid, nr1 = profil(tenant, om)
    with sesiune_tenant(tenant, om) as db:
        creier.aproba(db, iid, nr1, utilizator_id=om, acum=minute(1))
    with sesiune_tenant(tenant, om) as db:
        v2 = creier.propune_schimbare(
            db, iid, continut={"pozitionare": "Cafea de specialitate din Brașov", "ton": ["cald", "direct"]},
            sursa=OM, utilizator_id=om, motiv="tonul „direct”", acum=minute(5),
        )  # fmt: skip
        assert v2.nr == 2 and v2.stare == "propus"
    with sesiune_tenant(tenant, om) as db:
        creier.aproba(db, iid, 2, utilizator_id=om, acum=minute(10))
    with sesiune_tenant(tenant, om) as db:
        v1 = creier.citeste(db, iid, 1)  # cea veche rămâne citibilă, cu conținutul ei
        assert v1.continut["ton"] == ["cald"] and v1.stare == "retras" and v1.retras_cauza == "inlocuita"
        assert v1.inlocuita_de == 2 and v1.aprobat_de == om and v1.aprobat_la == minute(1)
        v2 = creier.versiune_aprobata(db, iid)
        assert v2 is not None and v2.nr == 2 and v2.continut["ton"] == ["cald", "direct"]
        assert [v.nr for v in creier.istoric(db, iid)] == [1, 2]
        assert [(s.cale, s.fel.value) for s in creier.diferenta_versiuni(db, iid, 1, 2)] == [
            ("ton.1", "adaugat")
        ]
    # nemodificabilă, impus în bază: nici cu drepturile aplicației, nici ca proprietar
    for rol_admin in (False, True):
        for coloana, valoare in (
            ("continut", '{"x": 1}'),
            ("sursa_tip", "sistem"),
            ("valabil_pana_la", "2030-01-01"),
        ):
            with pytest.raises(DBAPIError) as exc:
                if rol_admin:
                    with admin_engine.begin() as c:
                        c.execute(
                            text(
                                f"UPDATE creier_versiuni SET {coloana} = CAST(:v AS {_tip(coloana)}) WHERE intrare_id = :i AND nr = 1"
                            ),
                            {"v": valoare, "i": iid},
                        )
                else:
                    with sesiune_tenant(tenant, om) as db:
                        db.execute(
                            text(
                                f"UPDATE creier_versiuni SET {coloana} = CAST(:v AS {_tip(coloana)}) WHERE intrare_id = :i AND nr = 1"
                            ),
                            {"v": valoare, "i": iid},
                        )
            assert "nu se modifică" in str(exc.value)


def _tip(coloana: str) -> str:
    return {"continut": "jsonb", "sursa_tip": "text", "valabil_pana_la": "timestamptz"}[coloana]


def test_baza_refuza_stergerea_si_intoarcerea_starii(tenant: uuid.UUID, om: uuid.UUID) -> None:
    iid, nr = profil(tenant, om)
    with sesiune_tenant(tenant, om) as db:
        creier.aproba(db, iid, nr, utilizator_id=om)
    with pytest.raises(DBAPIError), sesiune_tenant(tenant, om) as db:
        db.execute(text("DELETE FROM creier_versiuni WHERE intrare_id = :i"), {"i": iid})
    with pytest.raises(DBAPIError), sesiune_tenant(tenant, om) as db:
        db.execute(text("DELETE FROM creier_intrari WHERE id = :i"), {"i": iid})
    with sesiune_tenant(tenant, om) as db:
        creier.retrage(db, iid, nr, utilizator_id=om, motiv="nu mai e valabil")
    with pytest.raises(DBAPIError) as exc, sesiune_tenant(tenant, om) as db:  # retras → aprobat: nu
        db.execute(text("UPDATE creier_versiuni SET stare = 'aprobat' WHERE intrare_id = :i"), {"i": iid})
    assert "tranziție nepermisă" in str(exc.value)


def test_aprobarea_ceruta_unui_om_nu_merge_fara_om_iar_sistemul_aproba_doar_compartimentele_automate(
    tenant: uuid.UUID, om: uuid.UUID
) -> None:
    iid, nr = profil(tenant, om)
    with sesiune_tenant(tenant, om) as db:
        with pytest.raises(creier.RegulaCreier):
            creier.aproba(db, iid, nr, utilizator_id=None)  # fără om
        with pytest.raises(creier.RegulaCreier):
            creier.aproba(db, iid, nr, utilizator_id=None, prin_sistem=True)  # profilul cere om
        i, v = creier.creeaza_intrare(
            db, tenant_id=tenant, compartiment=Compartiment.EXEMPLE_AUR, continut={"text": "postare bună"},
            sursa=Sursa(SursaTip.SISTEM),
        )  # fmt: skip
        a = creier.aproba(db, i.id, v.nr, utilizator_id=None, prin_sistem=True)
        assert a.aprobat_prin == "sistem" and a.aprobat_de is None and a.stare == "aprobat"


def test_sursa_este_obligatorie_in_serviciu_si_in_baza(
    tenant: uuid.UUID, om: uuid.UUID, admin_engine: Engine
) -> None:
    with sesiune_tenant(tenant, om) as db:
        with pytest.raises(creier.RegulaCreier):  # document fără referință
            creier.creeaza_intrare(
                db, tenant_id=tenant, compartiment=Compartiment.PLAYBOOK, continut={"lectie": "x"},
                sursa=Sursa(SursaTip.DOCUMENT), utilizator_id=om,
            )  # fmt: skip
        with pytest.raises(creier.RegulaCreier):  # declarația clientului fără autor
            creier.creeaza_intrare(
                db, tenant_id=tenant, compartiment=Compartiment.PLAYBOOK, continut={"lectie": "x"},
                sursa=Sursa(SursaTip.DECLARATIE_CLIENT),
            )  # fmt: skip
    iid, _ = profil(tenant, om)
    cu_sursa = "INSERT INTO creier_versiuni (id, intrare_id, tenant_id, nr, continut, stare, sursa_tip, sursa_ref{}) VALUES (gen_random_uuid(), :i, :t, 9, '{{}}', 'propus', :s, :r{})"
    with pytest.raises(DBAPIError) as exc, admin_engine.begin() as c:
        c.execute(
            text(cu_sursa.format(", propus_la", ", now()")), {"i": iid, "t": tenant, "s": "pasaj", "r": None}
        )
    assert "creier_versiuni_sursa_referinta" in str(exc.value)
    with pytest.raises(DBAPIError), admin_engine.begin() as c:  # nicio sursă (tipul lipsește)
        c.execute(
            text(
                "INSERT INTO creier_versiuni (id, intrare_id, tenant_id, nr, continut, stare, propus_la) VALUES (gen_random_uuid(), :i, :t, 10, '{}', 'propus', now())"
            ),
            {"i": iid, "t": tenant},
        )


def test_citirea_la_o_data_arata_ce_era_in_vigoare_atunci(tenant: uuid.UUID, om: uuid.UUID) -> None:
    iid, nr1 = profil(tenant, om)
    with sesiune_tenant(tenant, om) as db:
        creier.aproba(db, iid, nr1, utilizator_id=om, acum=minute(10))
    with sesiune_tenant(tenant, om) as db:
        creier.propune_schimbare(
            db, iid, continut={"pozitionare": "nouă"}, sursa=OM, utilizator_id=om, acum=minute(20)
        )
        creier.aproba(db, iid, 2, utilizator_id=om, acum=minute(30))
        assert creier.la_data(db, iid, minute(5)) is None  # încă neaprobată
        v = creier.la_data(db, iid, minute(15))
        assert v is not None and v.nr == 1
        v = creier.la_data(db, iid, minute(31))
        assert v is not None and v.nr == 2
        # valabilitatea face parte din versiune: după „valabil până la” nu mai e în vigoare
    with sesiune_tenant(tenant, om) as db:
        creier.propune_schimbare(
            db, iid, continut={"pozitionare": "de sezon"}, sursa=OM, utilizator_id=om,
            valabil_de_la=minute(40), valabil_pana_la=minute(50), acum=minute(35),
        )  # fmt: skip
        creier.aproba(db, iid, 3, utilizator_id=om, acum=minute(36))
        assert creier.la_data(db, iid, minute(45)).nr == 3  # type: ignore[union-attr]
        assert creier.la_data(db, iid, minute(55)) is None
        assert creier.la_data(db, iid, minute(38)) is None  # aprobată, dar încă nevalabilă


def test_o_propunere_veche_se_retrage_cand_una_mai_noua_e_aprobata_si_ciorna_se_trimite(
    tenant: uuid.UUID, om: uuid.UUID
) -> None:
    iid, _ = profil(tenant, om, propune=False)  # prima versiune e ciornă
    with sesiune_tenant(tenant, om) as db:
        assert creier.citeste(db, iid, 1).stare == "ciorna"
        with pytest.raises(creier.TranzitieNepermisa):
            creier.aproba(db, iid, 1, utilizator_id=om)  # o ciornă nu se aprobă direct
        creier.trimite_spre_aprobare(db, iid, 1, utilizator_id=om)
        creier.propune_schimbare(db, iid, continut={"pozitionare": "b"}, sursa=OM, utilizator_id=om)
        creier.propune_schimbare(db, iid, continut={"pozitionare": "c"}, sursa=OM, utilizator_id=om)
        creier.aproba(db, iid, 3, utilizator_id=om)
        stari = {v.nr: (v.stare, v.retras_cauza) for v in creier.istoric(db, iid)}
        assert stari == {1: ("retras", "inlocuita"), 2: ("retras", "inlocuita"), 3: ("aprobat", None)}


def test_respingerea_si_retragerea_lasa_urma_si_audit(
    tenant: uuid.UUID, om: uuid.UUID, admin_engine: Engine
) -> None:
    iid, nr = profil(tenant, om)
    with sesiune_tenant(tenant, om) as db:
        v = creier.retrage(
            db, iid, nr, utilizator_id=om, motiv="nu e corect", cauza=creier.CauzaRetragere.RESPINS
        )
        assert v.retras_cauza == "respins" and v.retras_de == om and v.retras_motiv == "nu e corect"
        with pytest.raises(creier.TranzitieNepermisa):
            creier.retrage(db, iid, nr, utilizator_id=om)
    with admin_engine.connect() as c:
        actiuni = [
            r[0]
            for r in c.execute(
                text(
                    "SELECT actiune FROM jurnal_audit WHERE tenant_id = :t AND obiect_tip = 'creier_versiune' ORDER BY id"
                ),
                {"t": tenant},
            )
        ]
    assert actiuni == ["creier.intrare_creata", "creier.versiune_retrasa"]


def test_nivelurile_din_10_2(tenant: uuid.UUID, om: uuid.UUID) -> None:
    with sesiune_tenant(tenant, om) as db:
        with pytest.raises(creier.RegulaCreier):  # profilul nu are nivel de nișă
            creier.creeaza_intrare(
                db, tenant_id=None, nivel=Nivel.NISA, compartiment=Compartiment.PROFIL_BRAND, continut={"a": 1},
                sursa=Sursa(SursaTip.AGREGAT),
            )  # fmt: skip
        with pytest.raises(creier.RegulaCreier):  # nivelul client cere un client
            creier.creeaza_intrare(
                db,
                tenant_id=None,
                compartiment=Compartiment.PLAYBOOK,
                continut={"a": 1},
                sursa=Sursa(SursaTip.SISTEM),
            )
        with pytest.raises(creier.RegulaCreier):  # nișa primește doar tipare agregate
            creier.creeaza_intrare(
                db, tenant_id=None, nivel=Nivel.NISA, compartiment=Compartiment.PLAYBOOK, continut={"a": 1},
                sursa=Sursa(SursaTip.OM), utilizator_id=om,
            )  # fmt: skip
    with sesiune_agentie(om) as db:
        i, v = creier.creeaza_intrare(
            db, tenant_id=None, nivel=Nivel.NISA, compartiment=Compartiment.PLAYBOOK,
            continut={"lectie": "hook-urile cu întrebare țin mai bine privitorul"}, sursa=Sursa(SursaTip.AGREGAT),
        )  # fmt: skip
        assert i.tenant_id is None and v.tenant_id is None
