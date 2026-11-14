"""Contorul de unități al platformelor cu cotă pe proiect (F9.4: YouTube). Adunare atomică în Postgres
(`INSERT … ON CONFLICT DO UPDATE`), corectă la concurență; ziua o dă conectorul (ziua Pacific la YouTube)."""

import datetime as dt

from sqlalchemy import text

from app.db import sesiune_agentie


def consumat(platforma: str, zi: dt.date) -> int:
    with sesiune_agentie() as db:
        v = db.execute(
            text("SELECT unitati FROM publicare_cote WHERE platforma = :p AND zi = :z"),
            {"p": platforma, "z": zi},
        ).scalar_one_or_none()
    return int(v or 0)


def adauga(platforma: str, zi: dt.date, unitati: int) -> int:
    with sesiune_agentie() as db:
        return int(
            db.execute(
                text(
                    "INSERT INTO publicare_cote (platforma, zi, unitati) VALUES (:p, :z, :u) "
                    "ON CONFLICT (platforma, zi) DO UPDATE SET unitati = publicare_cote.unitati + :u, "
                    "actualizat_la = now() RETURNING unitati"
                ),
                {"p": platforma, "z": zi, "u": unitati},
            ).scalar_one()
        )
