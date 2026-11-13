"""Poarta F6 (docs/23 §23.9, docs/25 §25.4 poarta de lansare 1): prima versiune utilizabilă intern. Lanțul complet, pe
brandul FICTIV „Cafeneaua Zorilor”, cu acțiunile omului prin rutele reale ale panoului: strategie aprobată → calendar pe 30
de zile aprobat din ecran → briefuri → hook-uri și postare (flux durabil) → validare → aprobare din birou → pachet pe telefon
→ link lipit → publicat; respingerea devine exemplu negativ în sarcina următoare; scriptul video în durata-țintă; adaptările
pe canale; apoi proba de 14 zile pe două branduri, fără incident critic. Modelele, materialele, omul și publicarea reală
sunt SIMULATE (# SIMULAT, D-007); proba reală și postarea reală: la migrare."""

# ruff: noqa: F811
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app import continut, creier, productie, publicare, validare
from app.continut import adaptor, pipeline, proba, scripturi
from app.conturi import Rol
from app.creier.compartimente import Compartiment
from app.db import sesiune_tenant
from app.operare import motor
from app.productie import Stare
from tests.continut_utile import model_adaptor, model_brief, model_calendar, model_postari, model_scripturi
from tests.integration.conftest import Cont
from tests.integration.lant_continut import INCEPUT, calendar_aprobat, fara_cereri_ramase, pana_la_strategie  # noqa: F401
from tests.integration.test_continut_proba import ZILNIC, decident
from tests.integration.utile_panou import autentifica, csrf
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401
from tests.onboarding_utile import ModelFals, model_fals, modele, prompt_complet  # noqa: F401

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("fara_cereri_ramase")]
LINK = "https://www.facebook.com/cafeneauazorilor/posts/2026120118"


def test_poarta_f6_lantul_complet_si_proba_de_14_zile(
    client: TestClient, fabrica_conturi: Callable[..., Cont], ceas: dict[str, float],
    fabrica_clienti: Callable[[], uuid.UUID], tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, executor: None,
) -> None:  # fmt: skip
    # 1. strategia aprobată, apoi calendarul pe 30 de zile cerut și aprobat de proprietar din ecran (F6.1)
    pana_la_strategie(tenant, om, modele)
    model_calendar(modele)
    job = continut.fluxuri.trimite_calendarul(tenant, om, inceput=INCEPUT, cheie=f"poarta:cal:{tenant}")
    assert motor.asteapta_flux(job, timeout_sec=60).stare.value == "terminat"
    cont = fabrica_conturi(Rol.PROPRIETAR, cu_totp=True)
    autentifica(client, cont, ceas)
    with sesiune_tenant(tenant) as db:
        [cal] = continut.calendar.calendare(db, tenant)
    r = client.post(f"/calendar/{tenant}/{cal.id}/aproba", data={"csrf_token": csrf(client, f"/calendar/{tenant}")},
                    follow_redirects=False)  # fmt: skip
    assert r.status_code == 303
    # 2. briefuri cu fapte permise pentru fiecare slot (F6.2)
    model_brief(modele)
    job = continut.fluxuri.trimite_briefurile(tenant, cal.id, cheie=f"poarta:briefuri:{tenant}")
    assert motor.asteapta_flux(job, timeout_sec=120).stare.value == "terminat"
    with sesiune_tenant(tenant) as db:
        sloturi = continut.calendar.intrari(db, cal.id)
        assert len(sloturi) == 21
        assert all(
            (b := continut.brief.al_livrabilului(db, s.livrabil_id)) and b.continut["fapte_permise"]
            for s in sloturi
        )  # type: ignore[arg-type]
    postari = [s.livrabil_id for s in sloturi if s.tip == "postare"]
    scripturi_ = [s.livrabil_id for s in sloturi if s.tip == "script_video_scurt"]
    # 3. hook-uri și postare prin fluxul durabil, validare reală, aprobare cerută (F6.3)
    model_postari(modele, stricate={1})
    model_scripturi(modele)
    a, b2, c3 = postari[:3]
    job = continut.fluxuri.trimite_productia(tenant, a, cheie=f"poarta:produ:{a}")  # type: ignore[arg-type]
    assert motor.asteapta_flux(job, timeout_sec=120).stare.value == "terminat"
    assert pipeline.stare(tenant, a) is Stare.ASTEAPTA_APROBARE  # type: ignore[arg-type]
    # 4. scriptul video în durata-țintă (F6.4)
    assert pipeline.produ(tenant, scripturi_[0]) == Stare.ASTEAPTA_APROBARE.value  # type: ignore[arg-type]
    with sesiune_tenant(tenant) as db:
        c = validare.continut.citeste(db, scripturi_[0])  # type: ignore[arg-type]
        assert scripturi.se_incadreaza(c.campuri["durata_estimata_sec"], c.campuri["durata_tinta_sec"])
    # 5. aceeași idee pe celelalte canale, în limite (F6.5)
    model_adaptor(modele)
    with sesiune_tenant(tenant) as db:
        rez = adaptor.adapteaza(db, a)  # type: ignore[arg-type]
    assert set(rez.livrabile) == {"instagram", "linkedin", "tiktok"}
    for lid in rez.livrabile.values():
        assert pipeline.produ(tenant, lid) == Stare.ASTEAPTA_APROBARE.value
    # 6. aprobare din birou → pachet pe telefon → link lipit → publicat (F6.6)
    with sesiune_tenant(tenant) as db:
        ap = productie.aprobari.cerere_activa(db, a)  # type: ignore[arg-type]
        assert ap is not None
    r = client.post(f"/aprobari/{ap.id}/aproba", data={"csrf_token": csrf(client, "/aprobari"), "versiune": ap.versiune},
                    follow_redirects=False)  # fmt: skip
    assert r.status_code == 303
    with sesiune_tenant(tenant) as db:
        [p] = publicare.asistata.ale_livrabilului(db, a)  # type: ignore[arg-type]
    html = client.get("/publicare").text
    assert f'data-partajeaza="t-{p.id}"' in html
    r = client.post(f"/publicare/{p.id}/link", data={"csrf_token": csrf(client, "/publicare"), "link": LINK},
                    follow_redirects=False)  # fmt: skip
    assert r.status_code == 303
    with sesiune_tenant(tenant) as db:
        lv = productie.citeste(db, a)  # type: ignore[arg-type]
        assert (
            lv is not None and lv.stare == Stare.PUBLICAT.value and proba.verifica_publicarea(db, lv.id) == []
        )
    assert LINK in client.get("/publicare").text
    # 7. respingerea din birou devine exemplu negativ în contextul sarcinii următoare (F6.7)
    assert pipeline.produ(tenant, b2) == Stare.ASTEAPTA_APROBARE.value  # type: ignore[arg-type]
    with sesiune_tenant(tenant) as db:
        ap = productie.aprobari.cerere_activa(db, b2)  # type: ignore[arg-type]
        assert ap is not None
    r = client.post(f"/aprobari/{ap.id}/respinge", data={"csrf_token": csrf(client, "/aprobari"), "versiune": ap.versiune,
                    "motiv_standard": "ton_nepotrivit", "motiv": "Prea solemn pentru o cafenea"}, follow_redirects=False)  # fmt: skip
    assert r.status_code == 303
    with sesiune_tenant(tenant) as db:
        assert creier.lista(db, tenant_id=tenant, compartiment=Compartiment.EXEMPLE_NEGATIVE)
    vazut: list[str] = []
    h = modele.handlere["Scrie postarea pentru"]
    modele.handlere["Scrie postarea pentru"] = lambda cer: (vazut.append(prompt_complet(cer)), h(cer))[1]
    assert pipeline.produ(tenant, c3) == Stare.ASTEAPTA_APROBARE.value  # type: ignore[arg-type]
    assert len(vazut) == 1 and "Exemple respinse" in vazut[0] and "Prea solemn pentru o cafenea" in vazut[0]
    # 8. proba de 14 zile pe două branduri proprii, la L1, fără incident critic (F6.8, accelerată)
    branduri = []
    for t in (fabrica_clienti(), fabrica_clienti()):
        cal_id, _ = calendar_aprobat(t, om, modele, calendar=ZILNIC)
        branduri.append((t, cal_id))
    model_brief(modele)
    model_postari(modele)
    model_scripturi(modele)
    raport = proba.ruleaza(
        branduri, om=om, inceput=INCEPUT, decident=decident,
        publicator=lambda _p, n: f"https://www.facebook.com/zorilor/posts/{n}",
    )  # fmt: skip
    assert raport.zile == 14 and all(z["produse"] >= 2 for z in raport.pe_zi)
    assert raport.incidente_critice == [] and raport.rata_aprobare_din_prima is not None
