"""Ajutor de test: parcurge lanțul Creierului (brief → ghid → public → insight) cu brandul FICTIV, ca fiecare pas să
poată porni de la un Creier aprobat. Totul prin serviciile reale; doar modelul este FALS (# SIMULAT)."""

import datetime as dt
import uuid
from dataclasses import dataclass

from app import creier
from app.creier import fapte
from app.creier.compartimente import Compartiment, SursaTip
from app.db import sesiune_tenant
from app.onboarding import fluxuri, ghid, public
from app.operare import motor
from tests.integration import test_onboarding_ghid as t_ghid
from tests.integration import test_onboarding_piata as t_piata
from tests.integration import test_onboarding_public as t_public
from tests.onboarding_utile import ModelFals


@dataclass
class Lant:
    ghid_id: uuid.UUID | None = None
    profil_public_id: uuid.UUID | None = None
    insight_id: uuid.UUID | None = None


def fapte_aprobate(tenant: uuid.UUID, om: uuid.UUID) -> None:
    """Câteva fapte și o ofertă, aprobate de un om (declarația clientului), ca pachetul să le conțină."""
    with sesiune_tenant(tenant, om) as db:
        for afirmatie, extra in (
            (
                "Etiopia Guji, 250 g, costă 49 lei",
                {"valoare": {"numar": "49", "moneda": "RON", "unitate": "250 g"}},
            ),
            ("Livrarea este gratuită peste 150 lei", {}),
        ):
            i, v, _ = fapte.propune_fapt(
                db, tenant_id=tenant,
                continut={"tip": "pret" if extra else "termen", "subiect": "Cafea Etiopia Guji" if extra else "Livrare",
                          "afirmatie": afirmatie, **extra},
                sursa=creier.Sursa(SursaTip.DECLARATIE_CLIENT), utilizator_id=om,
            )  # fmt: skip
            fapte.aproba_fapt(db, i.id, v.nr, utilizator_id=om)


def pana_la_insight(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, *, cu_fapte: bool = True, cu_materiale: bool = True
) -> Lant:
    """Brief aprobat, ghid aprobat, profil de public aprobat și brief de insight aprobat. Cere `executor`."""
    lant = Lant()
    t_ghid.inregistreaza(modele, t_ghid.tre_variante())
    if cu_materiale:
        t_ghid.materiale(tenant)
    t_ghid.brief_aprobat(tenant, om)
    assert t_ghid.propune(tenant, om, f"lant:ton:{tenant}") == "terminat"
    with sesiune_tenant(tenant, om) as db:
        lant.ghid_id, nr = ghid.alege(db, tenant, utilizator_id=om, varianta=2)
        creier.aproba(db, lant.ghid_id, nr, utilizator_id=om)
    t_public.model_citate(modele)
    t_public.model_profil(modele)
    sid = t_public.sursa_recenzii(tenant)
    assert t_public.extrage(tenant, sid, f"lant:citate:{tenant}") == "terminat"
    job = fluxuri.trimite_profilul_de_public(tenant, om, cheie=f"lant:public:{tenant}")
    assert motor.asteapta_flux(job, timeout_sec=60).stare.value == "terminat"
    with sesiune_tenant(tenant, om) as db:
        i = creier.gaseste_intrare(
            db, tenant_id=tenant, compartiment=Compartiment.INSIGHT_PUBLIC, cheie=public.CHEIE_PROFIL
        )
        assert i is not None
        lant.profil_public_id = i.id
        creier.aproba(db, i.id, 1, utilizator_id=om)
    t_piata.model_piata(modele)
    ids = t_piata.concurenti_manuali(tenant, om)
    t_piata.extrage(tenant, ids, f"lant:af:{tenant}")
    t_piata.propune(tenant, om, f"lant:insight:{tenant}")
    lant.insight_id, v = t_piata.brief_db(tenant)
    with sesiune_tenant(tenant, om) as db:
        creier.aproba(db, lant.insight_id, v.nr, utilizator_id=om)
    if cu_fapte:
        fapte_aprobate(tenant, om)
    return lant


def acum_plus() -> dt.datetime:
    return dt.datetime.now(dt.UTC) + dt.timedelta(seconds=5)
