# ruff: noqa: F811
"""F14.2 — Umbră, canar, promovare, revenire. „Gata când”: un candidat trece prin toate etapele și revenirea
funcționează. Livrabilele sunt SIMULATE: rutarea reală, scorul dat de test (în locul verdictului validării)."""

import datetime as dt
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text

from app import gateway
from app.db import sesiune_agentie
from app.invatare import constitutie, optimizator, promovare
from app.invatare.constitutie import ConstitutieIncalcata
from app.invatare.promovare import PromovareRefuzata
from tests.integration import utile_optimizare as u
from tests.integration.utile_productie import om  # noqa: F401

pytestmark = pytest.mark.db
ACUM = dt.datetime.now(dt.UTC)


@pytest.fixture(autouse=True)
def _dezghetat(admin_engine: Engine) -> Iterator[None]:
    yield
    with admin_engine.begin() as c:
        c.execute(text("UPDATE invatare_stare SET inghetat = false WHERE id = 1"))


def candidat() -> tuple[str, uuid.UUID]:
    nume = u.prompt_de_proba()
    with sesiune_agentie() as db:
        o = optimizator.optimizeaza(
            db, nume, executor=u.model_simulat, propunator=u.propunator_simulat, exemple=u.set_aur()
        )
        assert o.stare == "candidat"
        return nume, o.id


def livrabile(nume: str, n: int, scor: dict[str, float], *, start: int = 0) -> dict[str, int]:
    """n livrabile prin rutarea reală; fiecare primește scorul grupului lui (cu un mic zgomot determinist).
    În umbră se scorează și producția paralelă a candidatului."""
    numarate = {"campion": 0, "candidat": 0}
    for i in range(start, start + n):
        cheie = f"livrabil-{i}"
        with sesiune_agentie() as db:
            r = promovare.ruteaza(db, nume, cheie)
            assert r.promovare_id is not None and r.grup is not None
            zgomot = (i % 5) * 0.01
            promovare.observa(
                db, r.promovare_id, grup=r.grup, cheie=cheie, scor=scor[r.grup] + zgomot, conform=True
            )
            numarate[r.grup] += 1
            if r.umbra is not None:
                promovare.observa(
                    db, r.promovare_id, grup="candidat", cheie=cheie, scor=scor["candidat"] + zgomot,
                    conform=True, umbra=True,
                )  # fmt: skip
    return numarate


def pana_la_iesire(
    nume: str, pid: uuid.UUID, din: str, scor: dict[str, float], *, start: int, lot: int = 300
) -> tuple[dict[str, int], str]:
    """Livrabile în loturi până când promovarea iese din etapa `din`. Rutarea e după un hash al id-ului
    promovării (aleator la fiecare rulare), deci câte livrabile ajung la eșantionul cerut variază: 300 dau
    ~30 în grupul de 10%, dar uneori sub cele 20 cerute (~1,6% din rulări). Testul nu presupune un număr fix,
    ci verifică că etapa nu se schimbă până nu se strânge eșantionul. Întoarce numărătoarea și etapa nouă."""
    total = {"campion": 0, "candidat": 0}
    for k in range(5):  # 1500 de livrabile: probabilitatea să nu ajungă e neglijabilă
        n = livrabile(nume, lot, scor, start=start + k * lot)
        total = {g: total[g] + n[g] for g in total}
        if (e := etapa(pid)) != din:
            return total, e
    return total, din


def etapa(pid: uuid.UUID) -> str:
    with sesiune_agentie() as db:
        return promovare.avanseaza(db, pid, acum=ACUM).etapa


def activ(nume: str) -> gateway.prompturi.Reperat:
    with sesiune_agentie() as db:
        p = gateway.prompturi.rezolva(db, nume)
    assert p is not None
    return p


def test_un_candidat_trece_prin_toate_etapele_si_revenirea_functioneaza(
    om: uuid.UUID, admin_engine: Engine
) -> None:
    nume, oid = candidat()
    with sesiune_agentie() as db:
        pid = promovare.porneste(db, oid, acum=ACUM).id
        with pytest.raises(PromovareRefuzata, match="a mai fost pornit"):
            promovare.porneste(db, oid, acum=ACUM)
    # umbra: campionul produce, candidatul doar în paralel; cu date puține nu se trece mai departe
    with sesiune_agentie() as db:
        r = promovare.ruteaza(db, nume, "x")
        assert (r.folosit, r.umbra) == (f"{nume}@1", f"{nume}@3")
    livrabile(nume, 10, {"campion": 0.80, "candidat": 0.90})
    assert etapa(pid) == "umbra"
    livrabile(nume, 10, {"campion": 0.80, "candidat": 0.90}, start=10)
    assert etapa(pid) == "canar"
    # canarul: ~10% pe candidat; campionul rămâne activ până se strâng cele 20 de livrabile ale candidatului
    n = livrabile(nume, 100, {"campion": 0.80, "candidat": 0.90}, start=100)
    assert n["candidat"] <= 25
    assert activ(nume).versiune == 1  # campionul e încă activ
    n, e = pana_la_iesire(nume, pid, "canar", {"campion": 0.80, "candidat": 0.90}, start=200)
    assert e == "productie"
    assert 0.05 <= n["candidat"] / sum(n.values()) <= 0.2
    # producția: candidatul e activ, ~10% rămân pe campionul vechi (control)
    assert activ(nume).versiune == 3
    n, e = pana_la_iesire(nume, pid, "productie", {"campion": 0.80, "candidat": 0.90}, start=10_000)
    assert 0.05 <= n["campion"] / sum(n.values()) <= 0.2
    assert e == "promovat"
    with sesiune_agentie() as db:
        p = promovare.istoric(db, nume)[0]
        assert p.castig["concluzie"] == "castiga_b" and p.castig["medie_b"] > p.castig["medie_a"]
        assert p.castig["test_ab"] == str(p.test_ab_id) and p.castig["p"] < 0.05  # testul formal (F14.4)
        assert [x["in"] for x in p.istoric] == ["umbra", "canar", "productie", "promovat"]
        assert promovare.ruteaza(db, nume, "y").folosit == nume  # promovarea s-a încheiat: versiunea activă
    # revenirea dintr-o atingere, după promovare: o versiune nouă cu textul campionului vechi
    with sesiune_agentie() as db:
        p = promovare.revino(db, pid, utilizator_id=om, motiv="vreau varianta veche")
        assert p.etapa == "revenit" and p.revenire_versiune == 4
    assert activ(nume).versiune == 4 and activ(nume).sistem == u.SISTEM_CAMPION
    with admin_engine.connect() as c:
        actiuni = c.execute(
            text("SELECT actiune FROM urme WHERE componenta = 'invatare.promovari' AND obiect_id = :p ORDER BY la"),
            {"p": str(pid)},
        ).scalars().all()  # fmt: skip
    assert actiuni == ["etapa_umbra", "etapa_canar", "etapa_productie", "etapa_promovat", "etapa_revenit"]


def test_umbra_slaba_respinge_iar_controlul_mai_bun_revine_automat() -> None:
    nume, oid = candidat()
    with sesiune_agentie() as db:
        pid = promovare.porneste(db, oid, acum=ACUM).id
    livrabile(nume, 20, {"campion": 0.90, "candidat": 0.70})
    assert etapa(pid) == "respins"
    with sesiune_agentie() as db:
        assert {p.versiune: p.stare for p in gateway.prompturi.lista(db, nume=nume)}[3] == "retras"
    # alt candidat, care trece de umbră și de canar, dar pierde față de control în producție
    with sesiune_agentie() as db:
        o = optimizator.optimizeaza(
            db, nume, executor=u.model_simulat, propunator=u.propunator_simulat, exemple=u.set_aur()
        )
        pid = promovare.porneste(db, o.id, acum=ACUM).id
    livrabile(nume, 20, {"campion": 0.80, "candidat": 0.80})
    assert etapa(pid) == "canar"
    _, e = pana_la_iesire(nume, pid, "canar", {"campion": 0.80, "candidat": 0.80}, start=100)
    assert e == "productie"
    _, e = pana_la_iesire(nume, pid, "productie", {"campion": 0.95, "candidat": 0.78}, start=10_000)
    assert e == "revenit"
    assert activ(nume).sistem == u.SISTEM_CAMPION  # versiune nouă, cu textul campionului


def test_constitutia_inghetarea_si_o_promovare_pe_saptamana(om: uuid.UUID) -> None:
    nume, oid = candidat()
    with sesiune_agentie() as db:
        constitutie.ingheata(db, activ=True, utilizator_id=om, motiv="probă")
    with sesiune_agentie() as db, pytest.raises(ConstitutieIncalcata, match="înghețată"):
        promovare.porneste(db, oid, acum=ACUM)
    with sesiune_agentie() as db:
        constitutie.ingheata(db, activ=False, utilizator_id=om)
        pid = promovare.porneste(db, oid, acum=ACUM).id
        with pytest.raises(PromovareRefuzata, match="de ce revii"):
            promovare.revino(db, pid, utilizator_id=om, motiv="")
        assert promovare.revino(db, pid, utilizator_id=om, motiv="nu acum").etapa == "revenit"  # din umbră
        assert {p.versiune: p.stare for p in gateway.prompturi.lista(db, nume=nume)} == {
            1: "activ", 2: "retras", 3: "retras",
        }  # fmt: skip
    with sesiune_agentie() as db:  # o promovare încheiată acum 2 zile blochează următoarea
        db.execute(
            text("UPDATE promovari SET promovat_la = :t WHERE id = :p"),
            {"t": ACUM - dt.timedelta(days=2), "p": pid},
        )
        o = optimizator.optimizeaza(
            db, nume, executor=u.model_simulat, propunator=u.propunator_simulat, exemple=u.set_aur()
        )
        with pytest.raises(ConstitutieIncalcata, match="ultimele 7 zile"):
            promovare.porneste(db, o.id, acum=ACUM)
        assert promovare.porneste(db, o.id, acum=ACUM + dt.timedelta(days=6)).etapa == "umbra"
    assert promovare.ruleaza(acum=ACUM) >= 0


def test_rutarea_e_determinista() -> None:
    pid = uuid.uuid4()
    assert promovare.galeata(pid, "a") == promovare.galeata(pid, "a")
    assert promovare.garda([(0.8, True)], [(0.8, False)]) is not None
    assert promovare.garda([(0.8, True)], [(0.77, True)]) is None
    assert "scorul" in (promovare.garda([(0.9, True)], [(0.7, True)]) or "")
