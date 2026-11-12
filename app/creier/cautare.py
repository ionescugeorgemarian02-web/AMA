"""Căutarea hibridă în pasajele unui client (F4.3, docs/10 §10.3 și §10.5): vectori + text, combinate prin
fuziune de
ranguri (RRF). Filtrarea pe client este obligatorie și dublă: RLS (sesiunea poartă clientul) și `tenant_id` în
orice
interogare; opțional se filtrează pe sursă și pe compartiment.

Trei canale, fiecare cu clasamentul lui: (1) vectorial (distanța cosinus, doar vectorii modelului activ); (2)
text
integral (`tsvector` `simple` peste textul fără diacritice, OR între cuvintele semnificative, cu prefixe pe
tulpini
ușoare pentru forme flexionate); (3) trigrame (`word_similarity`, tolerant la greșeli și forme neprevăzute).
Fără diacritice
în comparație: „ș / ş / s” și „ț / ţ / t” sunt același lucru. Dacă vectorul întrebării nu se poate calcula
(niciun model,
server căzut), căutarea continuă doar pe canalele de text și spune că e `degradat`.
"""

import uuid
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.orm import Session

from app import gateway
from app.config import get_settings
from app.creier import pasaje as nucleu
from app.creier.indexare import vector_literal
from app.db.motor import CTX_KEY
from app.operare.motor import Prioritate

CANDIDATI = 50  # câți candidați scoate fiecare canal înainte de fuziune
PRAG_TRIGRAME = 0.3
CANALE = ("vector", "text", "trigrame")


class CautareRefuzata(ValueError):
    pass


@dataclass(frozen=True)
class Rezultat:
    pasaj_id: uuid.UUID
    document_id: uuid.UUID
    sursa_id: uuid.UUID
    url: str | None
    titlu: str
    pozitie: int
    car_inceput: int
    car_sfarsit: int
    text: str
    scor: float
    ranguri: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class Raspuns:
    rezultate: list[Rezultat]
    degradat: bool = False  # fără canalul vectorial
    motiv: str = ""
    model_vectori: str | None = None


def stem_usor(j: str) -> str:
    """Tulpină grosieră: fără ultimele două litere ale unui cuvânt de 6+ litere (cafeaua -> cafea)."""
    return j[: len(j) - 2] if len(j) >= 6 else j


def interogare_text(jetoane: list[str]) -> str:
    """`to_tsquery` cu OR între cuvinte; cuvintele lungi devin prefixe. Doar litere / cifre ajung aici."""
    return " | ".join(f"{stem_usor(j)}:*" if len(j) >= 6 else j for j in jetoane)


def cauta(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    intrebare: str,
    limita: int = 8,
    sursa_id: uuid.UUID | None = None,
    compartiment: str | None = None,
    vector_intrebare: list[float] | None = None,
    model_vector: str | None = None,
    doar_text: bool = False,
    ponderi: dict[str, float] | None = None,
) -> Raspuns:
    """Pasajele clientului cele mai potrivite întrebării, de la cel mai bun. `vector_intrebare` (și
    `model_vector`)
    se pot da de-a gata; altfel se calculează prin gateway."""
    ctx = db.info.get(CTX_KEY)
    if ctx is not None and ctx.tenant_id is not None and ctx.tenant_id != tenant_id:
        raise CautareRefuzata("sesiunea aparține altui client")
    if not 1 <= limita <= 50:
        raise CautareRefuzata("limita: între 1 și 50")
    jet = nucleu.jetoane(intrebare)
    filtre = ""
    parametri: dict[str, object] = {"t": tenant_id, "k": CANDIDATI}
    if sursa_id is not None:
        filtre += " AND p.sursa_id = :sursa"
        parametri["sursa"] = sursa_id
    if compartiment is not None:
        filtre += " AND p.compartiment = :comp"
        parametri["comp"] = compartiment
    clasamente: dict[str, list[str]] = {}
    degradat, motiv, model_folosit = doar_text, "doar text cerut" if doar_text else "", None
    if not doar_text:
        try:
            if vector_intrebare is None:
                vectori, model_vector = gateway.vectorizeaza_cu_model(
                    [get_settings().vectori_prefix_intrebare + intrebare],
                    tenant_id=tenant_id,
                    componenta="creier.cautare",
                    prioritate=Prioritate.P1,
                )
                vector_intrebare = vectori[0]
            if model_vector is None:
                m = gateway.model_vectori(tenant_id)
                model_vector = m.cod if m else None
            model_folosit = model_vector
        except (gateway.Amanat, gateway.EroareGateway) as exc:
            degradat, motiv = True, f"fără vectori: {type(exc).__name__}"
            vector_intrebare = None
    if vector_intrebare is not None and model_vector is not None:
        clasamente["vector"] = [
            str(r[0])
            for r in db.execute(
                text(
                    "SELECT p.id FROM pasaje p WHERE p.tenant_id = :t AND p.embedding IS NOT NULL "  # noqa: S608
                    f"AND p.model_vectori = :m{filtre} "
                    "ORDER BY p.embedding <=> CAST(:q AS vector), p.id LIMIT :k"
                ),
                {**parametri, "m": model_vector, "q": vector_literal(vector_intrebare)},
            )
        ]
        if not clasamente["vector"]:
            nevectorizate = db.execute(
                text(
                    "SELECT count(*) FROM pasaje p WHERE p.tenant_id = :t "  # noqa: S608
                    f"AND p.model_vectori IS DISTINCT FROM :m{filtre}"
                ),
                {**parametri, "m": model_vector},
            ).scalar_one()
            if nevectorizate:
                degradat, motiv = True, "pasajele nu au încă vectorii modelului activ (reindexare în curs)"
    elif not doar_text:
        degradat = True
    if jet:
        clasamente["text"] = [
            str(r[0])
            for r in db.execute(
                text(
                    "SELECT p.id FROM pasaje p, to_tsquery('simple', :tsq) q WHERE p.tenant_id = :t "  # noqa: S608
                    f"AND p.fts @@ q{filtre} ORDER BY ts_rank_cd(p.fts, q) DESC, p.id LIMIT :k"
                ),
                {**parametri, "tsq": interogare_text(jet)},
            )
        ]
        db.execute(text(f"SELECT set_config('pg_trgm.word_similarity_threshold', '{PRAG_TRIGRAME}', true)"))
        qn = " ".join(jet)
        clasamente["trigrame"] = [
            str(r[0])
            for r in db.execute(
                text(
                    "SELECT p.id FROM pasaje p WHERE p.tenant_id = :t AND :qn <% p.text_normalizat"  # noqa: S608
                    f"{filtre} ORDER BY word_similarity(:qn, p.text_normalizat) DESC, p.id LIMIT :k"
                ),
                {**parametri, "qn": qn},
            )
        ]
    fuzionat = nucleu.fuzioneaza(clasamente, ponderi=ponderi)[:limita]
    if not fuzionat:
        return Raspuns([], degradat, motiv, model_folosit)
    detalii = {
        str(r.id): r
        for r in db.execute(
            text(
                "SELECT p.id, p.document_id, p.sursa_id, d.url, d.titlu, p.pozitie, p.car_inceput, "
                "p.car_sfarsit, p.text "
                "FROM pasaje p JOIN documente_colectate d ON d.id = p.document_id "
                "WHERE p.tenant_id = :t AND p.id = ANY(CAST(:ids AS uuid[]))"
            ),
            {"t": tenant_id, "ids": [e for e, _, _ in fuzionat]},
        )
    }
    rezultate: list[Rezultat] = []
    for e, scor, ranguri in fuzionat:
        d = detalii.get(e)
        if d is None:
            continue
        rezultate.append(
            Rezultat(
                pasaj_id=d.id,
                document_id=d.document_id,
                sursa_id=d.sursa_id,
                url=d.url,
                titlu=d.titlu,
                pozitie=d.pozitie,
                car_inceput=d.car_inceput,
                car_sfarsit=d.car_sfarsit,
                text=d.text,
                scor=scor,
                ranguri=ranguri,
            )
        )
    return Raspuns(rezultate, degradat, motiv, model_folosit)
