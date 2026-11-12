"""Modelul de vectori (F3.5, 10.5, 6.3): `gateway.vectorizeaza(texte, *, tenant_id) -> list[list[float]]`.

Un model multilingv mic, SEPARAT de modelul de text, pe propriul server compatibil OpenAI (`/embeddings`),
în rețeaua internă. Nu consumă cotă externă și NU ocupă un culoar greu: apelul vine dintr-un job `io` /
worker-light (sau din procesul web) și nu trece prin coada `greu`, deci un vector se calculează chiar când
toate culoarele grele sunt ocupate. Modelul se alege din registru (capabilitatea `embeddings`, furnizor
activ, `antrenare_pe_date` fals); DIMENSIUNEA vectorului este o dată în registru (`dimensiune_vector`) și
se verifică la fiecare răspuns, ca baza de date (pgvector, F4) să primească mereu aceeași mărime.

Textele nu se mascează (merg doar la serverul propriu, nu la un furnizor extern) și nu se salvează:
jurnalul păstrează doar metadate (model, număr de texte, tokeni, durată). Eșecurile (server căzut) devin
`Amanat`, nu o pierdere: apelantul reprogramează.
"""

import datetime as dt
import time
import uuid
from collections.abc import Sequence

from app.config import get_settings
from app.db import sesiune_tenant
from app.gateway import ceas, client, jurnal, registru, sanatate
from app.gateway.candidat import Candidat
from app.gateway.erori import Amanat, EroareFurnizor, FurnizoriIndisponibili
from app.gateway.intrerupator import deschis
from app.ids import new_id
from app.logging import correlation_id
from app.operare.motor import Prioritate

MAX_TEXTE = 64  # texte într-o cerere
MAX_CARACTERE_TEXT = 20_000  # peste asta, apelantul împarte textul în pasaje (F4.3)
PAUZA_FARA_MODEL_SEC = 300.0


class VectoriInvalizi(ValueError):
    """Cerere de vectori nepermisă (listă goală, prea multe texte, text gol sau prea lung)."""


def modele_de_vectori(candidati: Sequence[Candidat]) -> list[Candidat]:
    """Modelele de vectori utilizabile acum, în ordine stabilă."""
    ok = [
        c
        for c in candidati
        if "embeddings" in c.capabilitati
        and c.stare_furnizor == "activ"
        and c.model_activ
        and c.dimensiune_vector
        and c.antrenare_pe_date is False  # textele clientului merg doar la un server care nu antrenează
    ]
    return sorted(ok, key=lambda c: c.cod)


def dimensiune(tenant_id: uuid.UUID) -> int | None:
    """Dimensiunea vectorilor modelului activ (pentru coloana pgvector), sau `None` dacă nu există model."""
    with sesiune_tenant(tenant_id) as db:
        m = modele_de_vectori(registru.candidati(db))
    return m[0].dimensiune_vector if m else None


def vectorizeaza(
    texte: Sequence[str],
    *,
    tenant_id: uuid.UUID,
    componenta: str = "vectori",
    prioritate: Prioritate = Prioritate.P2,
) -> list[list[float]]:
    """Vectorii textelor, în aceeași ordine. Ridică `Amanat` (niciun model activ, server căzut) sau
    `FurnizoriIndisponibili` (serverul a refuzat cererea)."""
    if not texte or len(texte) > MAX_TEXTE:
        raise VectoriInvalizi(f"între 1 și {MAX_TEXTE} de texte")
    if any(not t.strip() or len(t) > MAX_CARACTERE_TEXT for t in texte):
        raise VectoriInvalizi(f"fiecare text: între 1 și {MAX_CARACTERE_TEXT} de caractere")
    lista = list(texte)
    acum = ceas.acum()
    with sesiune_tenant(tenant_id) as db:
        modele = modele_de_vectori(registru.candidati(db))
    if not modele:
        raise Amanat(acum + dt.timedelta(seconds=PAUZA_FARA_MODEL_SEC), "niciun model de vectori activ")
    c = modele[0]
    stare = sanatate.citeste_starea(c.furnizor_id, acum)
    if deschis(stare, acum) and stare.intrerupt_pana_la is not None:
        raise Amanat(stare.intrerupt_pana_la, "serverul de vectori este scos temporar")
    start = time.monotonic()
    try:
        vectori, tokeni = _cu_reincercari(c, lista)
    except Amanat as amanat:
        _jurnal(tenant_id, componenta, prioritate, c, len(lista), 0, start, "amanat", "amanat")
        raise amanat from None
    except FurnizoriIndisponibili:
        _jurnal(tenant_id, componenta, prioritate, c, len(lista), 0, start, "esec", "cerere_respinsa")
        raise
    _jurnal(tenant_id, componenta, prioritate, c, len(lista), tokeni, start, "ok", "")
    return vectori


def _cu_reincercari(c: Candidat, texte: list[str]) -> tuple[list[list[float]], int]:
    s = get_settings()
    for incercare in range(s.gateway_reincercari + 1):
        try:
            vectori, tokeni = client.trimite_vectori(c.destinatie, texte)
        except EroareFurnizor as exc:
            if exc.fel not in ("server", "retea"):
                raise FurnizoriIndisponibili("serverul de vectori a refuzat cererea") from None
            stare = sanatate.inregistreaza_esec(c.furnizor_id)
            if incercare >= s.gateway_reincercari:
                pana = stare.intrerupt_pana_la or ceas.acum() + dt.timedelta(
                    seconds=s.gateway_intrerupator_pauza_sec
                )
                raise Amanat(pana, "serverul de vectori nu răspunde") from None
            ceas.dormi(s.gateway_pauza_sec * s.gateway_factor_pauza**incercare)
            continue
        if any(len(v) != c.dimensiune_vector for v in vectori):
            # Un model schimbat fără actualizarea registrului ar strica indexul: refuz, nu vectori de
            # altă mărime.
            raise FurnizoriIndisponibili("dimensiunea vectorilor nu corespunde cu registrul")
        if c.erori_consecutive or c.intrerupt_pana_la is not None:
            sanatate.inregistreaza_succes(c.furnizor_id)
        return vectori, tokeni
    raise AssertionError("neajuns")  # pragma: no cover


def _jurnal(
    tenant_id: uuid.UUID, componenta: str, prioritate: Prioritate, c: Candidat, n: int, tokeni: int,
    start: float, rezultat: str, cod: str,
) -> None:  # fmt: skip
    jurnal.scrie(
        jurnal.IntrareJurnal(
            id=new_id(), tenant_id=tenant_id, componenta=componenta, prioritate=prioritate.name,
            profil="vectori", rezultat=rezultat, cod_eroare=cod, furnizor=c.furnizor, model=c.cod,
            nivel=c.nivel, motiv_alegere=f"{n} texte", tokeni_intrare=tokeni,
            durata_ms=int((time.monotonic() - start) * 1000),
            corelare_id=correlation_id.get() or "",
        )
    )  # fmt: skip
