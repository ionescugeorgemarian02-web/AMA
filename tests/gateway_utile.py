"""Ajutoare comune pentru testele gateway-ului (F3.3+): modele de probă în registru, ceas controlat, furnizorul fals."""

import datetime as dt
import json
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from sqlalchemy import Engine, text

from app.db import sesiune_agentie
from app.gateway import ceas, client, prompturi
from app.gateway.candidat import Candidat, din_randuri
from app.gateway.iesire import Iesire
from app.gateway.modele import Furnizor, ModelLlm
from app.ids import new_id
from tests.furnizor_fals import FurnizorFals

CHEIE_PROBA = "cheie-de-proba-" + "x" * 30  # construită la rulare: nu este o cheie reală
T0 = dt.datetime(2026, 11, 12, 12, 0, 10, tzinfo=dt.UTC)


class Clasificare(Iesire):
    """Schema ieșirii pentru prompturile de probă."""

    eticheta: str


class CeasControlat:
    def __init__(self, t: dt.datetime = T0) -> None:
        self.t = t
        self.pauze: list[float] = []

    def __call__(self) -> dt.datetime:
        return self.t

    def avanseaza(self, secunde: float) -> None:
        self.t += dt.timedelta(seconds=secunde)

    def dormi(self, secunde: float) -> None:
        self.pauze.append(secunde)  # nicio pauză reală în teste


@pytest.fixture
def ceas_controlat() -> Iterator[CeasControlat]:
    c = CeasControlat()
    ceas.seteaza_ceas(c)
    ceas.seteaza_dormi(c.dormi)
    yield c
    ceas.seteaza_ceas(None)
    ceas.seteaza_dormi(None)


@pytest.fixture
def fals() -> Iterator[FurnizorFals]:
    f = FurnizorFals()
    client.seteaza_transport(f.transport)
    yield f
    client.seteaza_transport(None)


@pytest.fixture
def cheie_proba(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("AMA_CHEIE_PROBA", CHEIE_PROBA)
    return CHEIE_PROBA


class FabricaModele:
    """Furnizori și modele de probă în registru (SIMULAT: gazde `*.exemplu.test`, fără rețea). La final se șterg."""

    def __init__(self, admin: Engine) -> None:
        self.admin = admin
        self.furnizori: list[str] = []
        self.profiluri: list[str] = []
        self.prompturi: list[str] = []

    def furnizor(self, *, tip_api: str = "openai_compat", stare: str = "activ", **campuri: Any) -> uuid.UUID:
        cod = f"p{uuid.uuid4().hex[:8]}"
        valori: dict[str, Any] = {
            "id": new_id(), "cod": cod, "nume": f"Furnizor de probă {cod}", "tip_api": tip_api,
            "url_baza": f"https://{cod}.exemplu.test/v1", "cheie_env": "AMA_CHEIE_PROBA", "stare": stare,
            "uz_comercial": True, "antrenare_pe_date": False, "marcaj": "I", "platit": False,
            "cereri_minut": None, "cereri_zi": None, "tokeni_minut": None, "tokeni_zi": None,
            "reset_zi_ora": 0, "parametri": json.dumps({}),
        }  # fmt: skip
        valori.update(campuri)
        if isinstance(valori["parametri"], dict):
            valori["parametri"] = json.dumps(valori["parametri"])
        with self.admin.begin() as c:
            c.execute(
                text(
                    "INSERT INTO gateway_furnizori (id, cod, nume, tip_api, url_baza, cheie_env, stare, uz_comercial, "
                    "antrenare_pe_date, marcaj, platit, cereri_minut, cereri_zi, tokeni_minut, tokeni_zi, reset_zi_ora, "
                    "parametri) VALUES (:id, :cod, :nume, :tip_api, :url_baza, :cheie_env, :stare, :uz_comercial, "
                    ":antrenare_pe_date, :marcaj, :platit, :cereri_minut, :cereri_zi, :tokeni_minut, :tokeni_zi, "
                    ":reset_zi_ora, CAST(:parametri AS jsonb))"
                ),
                valori,
            )
        self.furnizori.append(cod)
        return valori["id"]  # type: ignore[no-any-return]

    def model(
        self, furnizor_id: uuid.UUID, *, identificator: str = "model-proba", **campuri: Any
    ) -> Candidat:
        valori: dict[str, Any] = {
            "id": new_id(), "f": furnizor_id, "ident": identificator, "nivel": "T2", "ctx": 32000,
            "capabilitati": [], "activ": True, "cereri_minut": None, "cereri_zi": None, "tokeni_minut": None,
            "tokeni_zi": None, "scor": json.dumps({}), "pi": 0.5, "pe": 1.5,
        }  # fmt: skip
        valori.update(campuri)
        valori["pi"] = campuri.get("pret_umbra_intrare", valori["pi"])
        valori["pe"] = campuri.get("pret_umbra_iesire", valori["pe"])
        if isinstance(valori["scor"], dict):
            valori["scor"] = json.dumps(valori["scor"])
        with self.admin.begin() as c:
            c.execute(
                text(
                    "INSERT INTO gateway_modele (id, furnizor_id, identificator, nume_afisat, nivel, context_tokeni, "
                    "capabilitati, activ, cereri_minut, cereri_zi, tokeni_minut, tokeni_zi, scor, pret_umbra_intrare, "
                    "pret_umbra_iesire, marcaj) VALUES (:id, :f, :ident, :ident, :nivel, :ctx, :capabilitati, :activ, "
                    ":cereri_minut, :cereri_zi, :tokeni_minut, :tokeni_zi, CAST(:scor AS jsonb), :pi, :pe, 'I')"
                ),
                valori,
            )
        return self.candidat(valori["id"])

    def profil(
        self,
        lant: list[str],
        *,
        nivel_min: str = "T2",
        la_epuizare: str = "amana",
        lant_degradare: list[str] | None = None,
        verificare_in_plus: bool = False,
        capabilitati: list[str] | None = None,
    ) -> str:
        """Un profil de probă (nume unic). Lanțurile conțin coduri `furnizor/identificator` sau `nivel:X`."""
        nume = f"pr_{uuid.uuid4().hex[:8]}"
        with self.admin.begin() as c:
            c.execute(
                text(
                    "INSERT INTO gateway_profiluri (nume, eticheta, nivel_min, capabilitati, lant, la_epuizare, "
                    "lant_degradare, verificare_in_plus) VALUES (:n, :n, :nm, :cap, :l, :le, :ld, :v)"
                ),
                {"n": nume, "nm": nivel_min, "cap": capabilitati or [], "l": lant, "le": la_epuizare,
                 "ld": lant_degradare or [], "v": verificare_in_plus},
            )  # fmt: skip
        self.profiluri.append(nume)
        return nume

    def prompt(
        self,
        profil: str,
        *,
        sablon: str = "Clasifică textul: {{text}}",
        sistem: str = "Ești un clasificator atent.",
        activ: bool = True,
    ) -> str:
        """Un prompt de probă, cu nume unic (versiunea 1), activ. Schema: `Clasificare`."""
        nume = f"t{uuid.uuid4().hex[:8]}.clasifica"
        with sesiune_agentie() as db:
            prompturi.creeaza(db, nume, profil=profil, sablon=sablon, sistem=sistem, schema=Clasificare)
            if activ:
                prompturi.activeaza(db, nume, 1)
        self.prompturi.append(nume)
        return nume

    def candidat(self, model_id: uuid.UUID) -> Candidat:
        with sesiune_agentie() as db:
            m = db.get(ModelLlm, model_id)
            assert m is not None
            f = db.get(Furnizor, m.furnizor_id)
            assert f is not None
            return din_randuri(f, m)

    def curata(self) -> None:
        if self.prompturi:
            with self.admin.begin() as c:
                c.execute(text("DELETE FROM gateway_prompturi WHERE nume = ANY(:n)"), {"n": self.prompturi})
            self.prompturi.clear()
        if self.profiluri:
            with self.admin.begin() as c:
                c.execute(text("DELETE FROM gateway_profiluri WHERE nume = ANY(:n)"), {"n": self.profiluri})
            self.profiluri.clear()
        if not self.furnizori:
            return
        with self.admin.begin() as c:
            c.execute(
                text(
                    "DELETE FROM gateway_contoare WHERE substring(cheie from 4) IN (SELECT id::text FROM gateway_modele "
                    "WHERE furnizor_id IN (SELECT id FROM gateway_furnizori WHERE cod = ANY(:c))) "
                    "OR substring(cheie from 10) IN (SELECT id::text FROM gateway_furnizori WHERE cod = ANY(:c))"
                ),
                {"c": self.furnizori},
            )
            c.execute(
                text(
                    "DELETE FROM gateway_blocaje WHERE substring(cheie from 7) IN (SELECT id::text FROM gateway_modele "
                    "WHERE furnizor_id IN (SELECT id FROM gateway_furnizori WHERE cod = ANY(:c))) "
                    "OR substring(cheie from 10) IN (SELECT id::text FROM gateway_furnizori WHERE cod = ANY(:c))"
                ),
                {"c": self.furnizori},
            )
            c.execute(
                text(
                    "DELETE FROM gateway_modele WHERE furnizor_id IN (SELECT id FROM gateway_furnizori WHERE cod = ANY(:c))"
                ),
                {"c": self.furnizori},
            )
            c.execute(text("DELETE FROM gateway_furnizori WHERE cod = ANY(:c)"), {"c": self.furnizori})
        self.furnizori.clear()


@pytest.fixture
def fabrica_modele(admin_engine: Engine) -> Iterator[FabricaModele]:
    f = FabricaModele(admin_engine)
    yield f
    f.curata()


def gazda(c: Candidat) -> str:
    return f"{c.furnizor}.exemplu.test"


def contor(admin: Engine, cheie: str, fereastra: str) -> tuple[int, int]:
    with admin.connect() as c:
        r = c.execute(
            text(
                "SELECT COALESCE(sum(cereri), 0), COALESCE(sum(tokeni), 0) FROM gateway_contoare WHERE cheie = :c AND fereastra = :f"
            ),
            {"c": cheie, "f": fereastra},
        ).one()
    return int(r[0]), int(r[1])


Fabrica = Callable[..., Candidat]


def sanatate(admin: Engine, furnizor_id: uuid.UUID) -> tuple[str, int, dt.datetime | None]:
    with admin.connect() as c:
        r = c.execute(
            text("SELECT stare, erori_consecutive, intrerupt_pana_la FROM gateway_furnizori WHERE id = :i"),
            {"i": furnizor_id},
        ).one()
    return r[0], int(r[1]), r[2]
