# ruff: noqa: F811
"""F12.8 — răspunsuri și escaladare. „Gata când”: o critică de test ajunge la om, iar un mesaj în afara ferestrei
nu se trimite. Canalele sunt SIMULATE."""

import datetime as dt
import uuid
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, text

from app.connectors import inbox as conector
from app.conturi import Rol
from app.crm import CrmRefuzat, inbox, raspunsuri, registru
from app.crm.modele import MesajInbox, RaspunsInbox
from app.db import sesiune_agentie
from app.operare.efecte import sistem
from tests.integration.conftest import Cont
from tests.integration.utile_crm import curata_crm
from tests.integration.utile_panou import autentifica, csrf
from tests.integration.utile_productie import om  # noqa: F401
from tests.integration.utile_site import asteapta

pytestmark = pytest.mark.db
ACUM = dt.datetime.now(dt.UTC).replace(microsecond=0)


@pytest.fixture(autouse=True)
def _curat(admin_engine: Engine) -> Iterator[None]:
    curata_crm(admin_engine)
    conector.INBOX.primite.clear()
    conector.INBOX.trimise.clear()
    conector.INBOX.ascunse.clear()
    yield
    conector.INBOX.primite.clear()
    curata_crm(admin_engine)


def vine(canal: str, cheie: str, text_: str, *, ore: float, tip: str = "mesaj") -> None:
    conector.INBOX.primite.append(
        conector.MesajPrimit(
            canal, cheie, tip, f"fir-{cheie}", f"pers_{cheie}", text_, ACUM - dt.timedelta(hours=ore)
        )
    )


def mesaj(cheie: str) -> MesajInbox:
    with sesiune_agentie() as db:
        m = db.scalars(select(MesajInbox).where(MesajInbox.id_extern == cheie)).one()
        db.expunge(m)
        return m


def trimise_catre(cheie: str) -> list[dict[str, str]]:
    return [t for t in conector.INBOX.trimise if t.get("catre") == f"pers_{cheie}"]


def test_critica_ajunge_la_om_iar_mesajul_in_afara_ferestrei_nu_se_trimite(
    executor: None, om: uuid.UUID, admin_engine: Engine
) -> None:
    with sesiune_agentie() as db:
        inbox.aproba_canal(db, "instagram", utilizator_id=om, nivel="L2")
    vine("instagram", "critica", "Sunt foarte dezamăgit, postările întârzie de o săptămână.", ore=1)
    vine("instagram", "intrebare", "Ce program aveți?", ore=2)
    vine("instagram", "veche", "Mulțumesc mult, super!", ore=30)  # în afara ferestrei de 24 de ore
    vine("instagram", "spam", "Ai câștigat un premiu! Click aici: https://castig.example/x", ore=1)
    vine("instagram", "com", "Ce program aveți?", ore=48, tip="comentariu")  # comentariu: 7 zile, un răspuns
    vine("instagram", "pret", "Cât costă pachetul? Scrieți-mi la ana@cafenea.example", ore=1)
    rez = inbox.ruleaza()
    assert sum(rez.values()) == 6

    # critica: la om, cu o variantă de răspuns, nimic trimis; nu se ascunde
    c = mesaj("critica")
    assert (c.clasa, c.stare) == ("critica", "la_om")
    with sesiune_agentie() as db:
        [varianta] = raspunsuri.propuneri(db, c.id)
        assert (varianta.stare, varianta.autor) == ("propus", "sistem")
        with pytest.raises(CrmRefuzat, match="criticile rămân"):
            raspunsuri._ascunde(db, db.get(MesajInbox, c.id), 1)  # type: ignore[arg-type]
    # mesajul în afara ferestrei: blocat, fără niciun efect
    v = mesaj("veche")
    with sesiune_agentie() as db:
        [b] = raspunsuri.propuneri(db, v.id)
        assert (b.stare, b.motiv) == ("blocat", "în afara ferestrei de mesagerie")
    # întrebarea cu fapt, comentariul și cererea de preț: răspuns automat la L2, cu dezvăluirea AI
    asteapta(lambda: (trimise_catre("intrebare") and trimise_catre("com") and trimise_catre("pret")) or None)
    for cheie in ("intrebare", "com", "pret"):
        [t] = trimise_catre(cheie)
        assert (
            t["text"].startswith(raspunsuri.PREFIX_AI) and "scrie „om”" in t["text"] and t["eticheta"] == ""
        )
    assert "Start 1490 lei/lună" in trimise_catre("pret")[0]["text"]
    assert not trimise_catre("critica") and not trimise_catre("veche")
    asteapta(lambda: conector.INBOX.ascunse or None)
    assert conector.INBOX.ascunse == ["spam"] and mesaj("spam").stare == "ascuns"
    with sesiune_agentie() as db:
        [lead] = [r[0] for r in registru.lista(db)]
        assert lead.sursa == "inbox" and registru.scopuri_acordate(db, lead.contact_id) == []

    # omul răspunde: la mesajul vechi de 30 h, cu eticheta „agent uman”; la comentariu, al doilea răspuns: blocat
    with sesiune_agentie() as db:
        r = raspunsuri.raspunde_om(db, v.id, "Mulțumim, Ana!", utilizator_id=om)
        assert (r.stare, r.eticheta_agent_uman) == ("trimis", True)
        r2 = raspunsuri.raspunde_om(db, mesaj("com").id, "Și duminica, la cerere.", utilizator_id=om)
        assert r2.stare == "blocat", "un singur răspuns privat la un comentariu"
        r3 = raspunsuri.raspunde_om(db, c.id, "Îmi pare rău, vă sun azi.", utilizator_id=om)
        assert r3.stare == "trimis" and not r3.text.startswith(raspunsuri.PREFIX_AI)
    asteapta(lambda: [t for t in trimise_catre("veche") if t["eticheta"] == "HUMAN_AGENT"] or None)

    # executorul reverifică fereastra în clipa trimiterii
    with sesiune_agentie() as db:
        e = sistem.cere(
            db, "mesaj_social", cheie="test:expirat", porneste=False,
            payload={"actiune": "raspunde", "canal": "instagram", "fir": "f", "catre": "x", "text": "t",
                     "fereastra_pana_la": (ACUM - dt.timedelta(minutes=1)).isoformat()},
        ).id  # fmt: skip
    assert sistem.incearca(e) == "esuat"
    with admin_engine.begin() as conn:
        actiuni = {
            r[0] for r in conn.execute(text("SELECT DISTINCT actiune FROM urme WHERE componenta = 'inbox'"))
        }
    assert {"escaladare", "raspuns_blocat", "raspuns_trimis", "ascuns", "lead_din_cerere"} <= actiuni


def test_la_l1_se_propune_iar_propunerea_aprobata_nu_primeste_eticheta_de_agent_uman(
    client: TestClient, fabrica_conturi: Callable[..., Cont], ceas: dict[str, float], executor: None
) -> None:
    autentifica(client, fabrica_conturi(Rol.PROPRIETAR, cu_totp=True), ceas)
    jeton = csrf(client, "/crm/inbox")
    client.post("/crm/inbox/canal", data={"csrf_token": jeton, "canal": "facebook", "nivel": "L1"})
    vine("facebook", "nou", "Ce program aveți?", ore=1)
    vine("facebook", "batran", "Ce program aveți?", ore=26)
    inbox.ruleaza()
    assert mesaj("nou").stare == "propus" and not conector.INBOX.trimise, "la L1 nu pleacă nimic singur"
    h = client.get("/crm/inbox").text
    assert "Trimite propunerea" in h
    with sesiune_agentie() as db:
        [p_nou] = raspunsuri.propuneri(db, mesaj("nou").id)
        [p_vechi] = raspunsuri.propuneri(db, mesaj("batran").id)
    r = client.post(f"/crm/inbox/{p_nou.mesaj_id}/raspunde", data={"csrf_token": jeton, "propunere": str(p_nou.id)},
                    follow_redirects=False)  # fmt: skip
    assert r.headers["location"].endswith("mesaj=trimis")
    r = client.post(f"/crm/inbox/{p_vechi.mesaj_id}/raspunde", data={"csrf_token": jeton, "propunere": str(p_vechi.id)},
                    follow_redirects=False)  # fmt: skip
    assert r.headers["location"].endswith("mesaj=blocat"), "textul sistemului nu poate folosi eticheta"
    asteapta(lambda: trimise_catre("nou") or None)
    assert not trimise_catre("batran")
    with sesiune_agentie() as db:
        assert not db.scalars(select(RaspunsInbox).where(RaspunsInbox.eticheta_agent_uman.is_(True))).all()
