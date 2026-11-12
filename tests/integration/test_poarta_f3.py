"""Poarta F3: „testul comparativ este rulat, iar pierderea oricărui furnizor nu oprește platforma”.

Partea verificabilă aici, cu furnizori falși (SIMULAT), pe Postgres real și motorul durabil în proces:
1. testul comparativ pe română rulează pe fiecare model de text din configurarea de probă (evaluare prin gateway, scor pe fiecare
   profil în registru);
2. pentru fiecare furnizor din configurare, oprit pe rând (erori de server permanente), un flux de probă pe FIECARE profil se
   termină curat: profilurile care permit degradarea dau un rezultat (marcat `degradat` / `provizoriu`, cu verificare în plus
   unde cere profilul), cele care nu degradează trec pe alt furnizor din lanț sau se amână curat (job reprogramat, fără eroare,
   fără model mai slab), iar modelul local se apelează doar de pe coada `greu`.
NEVERIFICAT: testul comparativ pe modele reale și evaluarea umană (rămân deschise până la migrare); comportamentul furnizorilor reali
la cădere. Nu validează decizia proprietarului la poartă."""

import uuid
from collections.abc import Callable, Iterator

import pytest
from sqlalchemy import Engine, text

from app.db import sesiune_agentie
from app.gateway import evaluare, registru
from app.gateway.profiluri import PROFILURI
from app.operare import motor
from app.operare.motor import Coada
from tests.furnizor_fals import FurnizorFals
from tests.gateway_utile import CeasControlat, FabricaModele, gazda
from tests.integration import fluxuri_poarta_f3 as pf3
from tests.integration.test_gateway_evaluare import furnizor_de_calitate

pytestmark = pytest.mark.db
Pornire = Callable[..., None]
TEXT_FLUX = '{"eticheta": "pozitiv", "dovezi": ["ok"], "incredere": 0.9}'
FURNIZORI = ("P1", "P2", "P3", "CL", "LOC")
PROFILURI_NUME = sorted(p.nume for p in PROFILURI)


class Configurare:
    """Cinci furnizori și cele șase profiluri din 8.2, cu lanțuri în spiritul semințelor: clasificarea și rescrierea degradează la
    modelul local, creația și judecata au câte două furnizori, strategia unul singur (nu degradează niciodată), consiliul are doar
    T4 și poate coborî la T3 „provizoriu”."""

    def __init__(self, f: FabricaModele) -> None:
        loc_cod = f"loc{uuid.uuid4().hex[:8]}"
        self.modele = {
            "P1": f.model(f.furnizor(), identificator="p1", nivel="T2"),
            "P2": f.model(f.furnizor(), identificator="p2", nivel="T2"),
            "P3": f.model(f.furnizor(), identificator="p3", nivel="T3"),
            "CL": f.model(f.furnizor(), identificator="cl", nivel="T4"),
            "LOC": f.model(
                f.furnizor(tip_api="local", cod=loc_cod, url_baza=f"http://{loc_cod}:8080/v1"),
                identificator="loc", nivel="local", capabilitati=["iesire_structurata"],
            ),
        }  # fmt: skip
        m = {k: v.cod for k, v in self.modele.items()}
        self.profil = {
            "clasificare": f.profil([m["P1"]], nivel_min="T1", la_epuizare="degradeaza", lant_degradare=[m["LOC"]]),
            "rescriere": f.profil([m["P2"]], la_epuizare="degradeaza", lant_degradare=[m["LOC"]], verificare_in_plus=True),
            "creatie": f.profil([m["P1"], m["P3"]]),
            "judecata": f.profil([m["P2"], m["P3"]]),
            "strategie": f.profil([m["P3"]], nivel_min="T3"),
            "consiliu": f.profil([m["CL"]], nivel_min="T4", la_epuizare="amana_sau_provizoriu", lant_degradare=["nivel:T3"]),
        }  # fmt: skip
        self.prompt = {p: f.prompt(nume) for p, nume in self.profil.items()}

    def gazda(self, furnizor: str) -> str:
        c = self.modele[furnizor]
        return c.furnizor if furnizor == "LOC" else gazda(c)


@pytest.fixture
def conf(fabrica_modele: FabricaModele) -> Configurare:
    return Configurare(fabrica_modele)


@pytest.fixture(autouse=True)
def _mediu(cheie_proba: str, ceas_controlat: CeasControlat, fals: FurnizorFals) -> Iterator[None]:
    fals.text = TEXT_FLUX
    pf3.reseteaza()
    yield
    pf3.reseteaza()


def repara_furnizorii(admin: Engine, conf: Configurare) -> None:
    """Între scenarii furnizorii revin: întrerupătorul se închide, contoarele de eroare se golesc."""
    with admin.begin() as c:
        c.execute(
            text(
                "UPDATE gateway_furnizori SET erori_consecutive = 0, intrerupt_pana_la = NULL, stare = 'activ' WHERE id = ANY(:i)"
            ),
            {"i": [m.furnizor_id for m in conf.modele.values()]},
        )
        c.execute(text("DELETE FROM gateway_blocaje"))


def ruleaza_scenariul(
    tenant: uuid.UUID, conf: Configurare, scenariu: str, accepta: bool = False
) -> dict[str, str]:
    joburi = [
        motor.trimite(
            pf3.flux, str(tenant), conf.prompt[p], p, scenariu, accepta, False, coada=Coada.IO,
            cheie=f"pf3:{scenariu}:{p}:io",
        )
        for p in PROFILURI_NUME
    ]  # fmt: skip
    for j in joburi:
        stare = motor.asteapta_flux(j, timeout_sec=60)
        assert stare.stare is motor.StareJob.TERMINAT, (scenariu, stare)  # niciun flux nu eșuează
    # fluxurile mutate pe `greu` sunt joburi noi: așteptăm să se termine și ele
    import time

    t0 = time.monotonic()
    while len([r for r in pf3.REZULTATE if r[0] == scenariu]) < len(PROFILURI_NUME):
        assert time.monotonic() - t0 < 60, (scenariu, pf3.REZULTATE)
        time.sleep(0.05)
    return {profil: rez for sc, profil, rez in pf3.REZULTATE if sc == scenariu}


def test_testul_comparativ_este_rulat_pe_fiecare_model_de_text_din_configurare(
    tenant: uuid.UUID, conf: Configurare, fals: FurnizorFals
) -> None:
    calitati = {
        gazda(conf.modele[k]): c for k, c in (("P1", "mediu"), ("P2", "mediu"), ("P3", "bun"), ("CL", "bun"))
    }
    fals.text = furnizor_de_calitate(calitati)
    for k in ("P1", "P2", "P3", "CL"):  # modelul local se evaluează pe coada `greu` (vezi F3.5/F3.6)
        r = evaluare.ruleaza(conf.modele[k].cod)
        assert r.stare == "terminata" and r.facute == 72, k
    with sesiune_agentie() as db:
        scoruri = {
            c.cod: c.scor for c in registru.candidati(db) if c.cod in {m.cod for m in conf.modele.values()}
        }
    for k in ("P1", "P2", "P3", "CL"):
        assert (
            sorted(scoruri[conf.modele[k].cod]) == PROFILURI_NUME
        )  # fiecare model are scor pe fiecare profil
    assert scoruri[conf.modele["P3"].cod]["creatie"] > scoruri[conf.modele["P1"].cod]["creatie"]


def test_pierderea_oricarui_furnizor_nu_opreste_platforma(
    tenant: uuid.UUID, conf: Configurare, fals: FurnizorFals, porneste_executor: Pornire, admin_engine: Engine
) -> None:
    porneste_executor(culoare_greu=2)
    rezultate: dict[str, dict[str, str]] = {}
    for furnizor in ("niciunul", *FURNIZORI):
        repara_furnizorii(admin_engine, conf)
        for f in FURNIZORI:
            fals.scenariu(conf.gazda(f))  # toți revin
        if furnizor != "niciunul":
            fals.scenariu(conf.gazda(furnizor), permanent="5xx")  # furnizorul a căzut definitiv
        rezultate[furnizor] = ruleaza_scenariul(tenant, conf, furnizor)

    def model(f: str) -> str:
        return conf.modele[f].cod

    def ok(r: str, cod: str, **marcaje: int) -> bool:
        parti = r.split(":")
        return (
            parti[0] == "ok"
            and ":".join(parti[1:]).startswith(cod)
            and all(f"{k}={v}" in parti for k, v in marcaje.items())
        )

    # Fără nicio cădere: fiecare profil pe furnizorul lui din lanț, nimic degradat.
    baza = rezultate["niciunul"]
    for profil, f in (("clasificare", "P1"), ("rescriere", "P2"), ("creatie", "P1"), ("judecata", "P2"),
                      ("strategie", "P3"), ("consiliu", "CL")):  # fmt: skip
        assert ok(baza[profil], model(f), degradat=0), (profil, baza[profil])

    # P1 cade: clasificarea degradează la modelul local (mutat pe coada `greu`), creația trece pe P3.
    r = rezultate["P1"]
    assert ok(r["clasificare"], model("LOC"), degradat=1) and ok(r["creatie"], model("P3"), degradat=0)
    assert (
        ok(r["judecata"], model("P2")) and ok(r["strategie"], model("P3")) and ok(r["consiliu"], model("CL"))
    )
    # P2 cade: rescrierea degradează la local CU verificare în plus, judecata trece pe P3.
    r = rezultate["P2"]
    assert ok(r["rescriere"], model("LOC"), degradat=1, verificare=1) and ok(r["judecata"], model("P3"))
    assert ok(r["clasificare"], model("P1")) and ok(r["creatie"], model("P1"))
    # P3 cade: creația și judecata trec pe celălalt furnizor, STRATEGIA SE AMÂNĂ CURAT (nu coboară la un model mai slab).
    r = rezultate["P3"]
    assert ok(r["creatie"], model("P1"), degradat=0) and ok(r["judecata"], model("P2"), degradat=0)
    assert r["strategie"] == "amanat" and ok(r["consiliu"], model("CL"))
    # Claude cade: consiliul (T4) se amână curat; fără acordul apelantului nu coboară la T3.
    r = rezultate["CL"]
    assert r["consiliu"] == "amanat"
    assert all(
        ok(r[p], m)
        for p, m in (("clasificare", model("P1")), ("rescriere", model("P2")), ("strategie", model("P3")))
    )
    # Modelul local cade: nimic nu se schimbă pentru profilurile care nu au nevoie de el.
    assert all(ok(rezultate["LOC"][p], model(f), degradat=0) for p, f in
               (("clasificare", "P1"), ("rescriere", "P2"), ("creatie", "P1"), ("judecata", "P2"), ("strategie", "P3"))
               ), rezultate["LOC"]  # fmt: skip
    # Pretutindeni: niciun refuz sau eroare; doar „ok” sau „amanat”; modelul local doar după mutarea pe coada `greu`.
    for scenariu, pe_profil in rezultate.items():
        for profil, rez in pe_profil.items():
            assert rez == "amanat" or rez.startswith("ok:"), (scenariu, profil, rez)
    mutate = {(sc, p) for sc, p, e in pf3.ETAPE if e == "mutat_pe_greu"}
    assert mutate == {("P1", "clasificare"), ("P2", "rescriere")}
    amanate = {(sc, p) for sc, p, e in pf3.ETAPE if e == "reprogramat"}
    assert amanate == {("P3", "strategie"), ("CL", "consiliu")}
    # Amânările sunt joburi durabile reprogramate (vor rula la momentul cerut), nu eșecuri.
    with admin_engine.connect() as c:
        in_asteptare = c.execute(
            text(
                "SELECT count(*) FROM dbos.workflow_status WHERE name = 'poarta_f3.flux' AND status = 'DELAYED'"
            )
        ).scalar_one()
        esuate = c.execute(
            text(
                "SELECT count(*) FROM dbos.workflow_status WHERE name = 'poarta_f3.flux' AND status IN ('ERROR', 'MAX_RECOVERY_ATTEMPTS_EXCEEDED')"
            )
        ).scalar_one()
    assert esuate == 0 and in_asteptare >= 2
    # Jurnalul: niciun apel al probei nu s-a încheiat cu eșec; doar ok / amânat / refuz de coadă (mutarea pe `greu`).
    with admin_engine.connect() as c:
        stari = {
            r[0]: r[1]
            for r in c.execute(
                text(
                    "SELECT rezultat, count(*) FROM gateway_apeluri WHERE componenta = 'poarta.f3' AND tenant_id = :t GROUP BY 1"
                ),
                {"t": tenant},
            )
        }
    assert (
        "esec" not in stari
        and stari.get("ok", 0) == 34
        and stari.get("amanat", 0) == 2
        and stari.get("refuzat", 0) == 2
    )
    # Modelul local a primit cereri doar după mutarea pe `greu`: 2 clasificări / rescrieri degradate (câte una pe scenariu).
    cereri_locale = fals.cereri_la(conf.gazda("LOC"))
    assert len(cereri_locale) >= 2 and all(
        "authorization" not in {k.lower() for k in c.antete} for c in cereri_locale
    )
