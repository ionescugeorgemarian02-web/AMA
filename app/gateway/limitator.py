"""Limitatoarele de cotă (8.4): contoare persistente în Postgres, rezervare atomică înainte de apel,
regularizare
după apel, corectare din antetele furnizorului, blocaje după 429.

Reguli:
- un contor pe (resursă, fereastră): resursa este un model (`model:<id>`) sau contul furnizorului
  (`furnizor:<id>`, limite comune tuturor modelelor lui, ca la OpenRouter); fereastra este minutul sau ziua;
- rezervarea este O SINGURĂ instrucțiune SQL pe contor (`INSERT … ON CONFLICT DO UPDATE … WHERE` sub
plafon): corectă
  la concurență, între fire și între workeri, fără blocări lungi; dacă un contor refuză, toate rezervările
  făcute
  în aceeași tranzacție se anulează;
- tranzacțiile sunt ale limitatorului (sesiune de agenție, commit imediat): rezervarea rămâne chiar dacă
apelantul
  face rollback, fiindcă apelul la furnizor s-a făcut oricum;
- timpul vine din `ceas.acum()` (înlocuibil în teste), nu din `now()` al bazei.
"""

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import BigInteger, CursorResult, Integer, bindparam, text
from sqlalchemy.orm import Session

from app.db import sesiune_agentie
from app.gateway import ceas, cote
from app.gateway.candidat import Candidat
from app.gateway.cote import Fereastra, LimiteCota
from app.gateway.tipuri import AntetLimita
from app.operare.motor import Prioritate

PASTRARE_CONTOARE_ZILE = 3

REZERVA = text(
    """
    INSERT INTO gateway_contoare AS c (cheie, fereastra, inceput, cereri, tokeni, actualizat_la)
    SELECT :cheie, :fereastra, :inceput, 1, :tokeni, :acum
    WHERE (CAST(:plafon_cereri AS integer) IS NULL OR 1 <= CAST(:plafon_cereri AS integer))
      AND (CAST(:plafon_tokeni AS bigint) IS NULL OR :tokeni <= CAST(:plafon_tokeni AS bigint))
    ON CONFLICT (cheie, fereastra, inceput) DO UPDATE
       SET cereri = c.cereri + 1, tokeni = c.tokeni + :tokeni, actualizat_la = :acum
     WHERE (CAST(:plafon_cereri AS integer) IS NULL OR c.cereri + 1 <= CAST(:plafon_cereri AS integer))
       AND (CAST(:plafon_tokeni AS bigint) IS NULL OR c.tokeni + :tokeni <= CAST(:plafon_tokeni AS bigint))
    RETURNING cereri, tokeni
    """
).bindparams(bindparam("plafon_cereri", type_=Integer), bindparam("plafon_tokeni", type_=BigInteger))


@dataclass(frozen=True)
class Resursa:
    """Un contor de urmărit pentru un apel: cheia, limitele ei și ora de resetare zilnică."""

    cheie: str
    limite: LimiteCota
    reset_zi_ora: int = 0


@dataclass(frozen=True)
class Rezervare:
    ferestre: tuple[tuple[str, Fereastra, dt.datetime], ...]  # (cheie, fereastră, începutul ferestrei)
    tokeni_estimati: int
    cheie_model: str
    cheie_furnizor: str


@dataclass(frozen=True)
class Refuz:
    """Rezervarea nu s-a făcut. `pana_la` este momentul de la care merită reîncercat; `imposibil`: cererea nu
    încape niciodată în limită (prea mulți tokeni pentru fereastră), deci modelul nu e bun pentru ea."""

    pana_la: dt.datetime
    motiv: str
    imposibil: bool = False


def resurse_pentru(c: Candidat) -> list[Resursa]:
    """Contoarele unui model: al lui și, dacă furnizorul are limite comune, al contului."""
    resurse = [Resursa(cote.cheie_model(c.model_id), c.limite_model, c.reset_zi_ora)]
    if not c.limite_furnizor.goala:
        resurse.append(Resursa(cote.cheie_furnizor(c.furnizor_id), c.limite_furnizor, c.reset_zi_ora))
    return resurse


def _blocaj_activ(db: Session, chei: Sequence[str], acum: dt.datetime) -> tuple[dt.datetime, str] | None:
    rand = db.execute(
        text(
            "SELECT max(pana_la), (array_agg(motiv ORDER BY pana_la DESC))[1] FROM gateway_blocaje "
            "WHERE cheie = ANY(:chei) AND pana_la > :acum"
        ),
        {"chei": list(chei), "acum": acum},
    ).one()
    return (rand[0], rand[1]) if rand[0] is not None else None


def rezerva(
    candidat: Candidat, tokeni: int, prioritate: Prioritate, *, acum: dt.datetime | None = None
) -> Rezervare | Refuz:
    """Rezervă o cerere și `tokeni` pe toate contoarele modelului. Atomic: ori toate, ori niciunul."""
    acum = acum or ceas.acum()
    resurse = resurse_pentru(candidat)
    with sesiune_agentie() as db:
        chei_blocaj = {r.cheie for r in resurse} | {cote.cheie_furnizor(candidat.furnizor_id)}
        blocaj = _blocaj_activ(db, sorted(chei_blocaj), acum)
        if blocaj is not None:
            return Refuz(cote.reluare_dupa(blocaj[0]), blocaj[1] or "blocat după o limitare a furnizorului")
        luate: list[tuple[str, Fereastra, dt.datetime]] = []
        refuzuri: list[Refuz] = []
        for r in resurse:
            for fereastra in Fereastra:
                lim_cereri, lim_tokeni = r.limite.pe(fereastra)
                if lim_cereri is None and lim_tokeni is None:
                    continue
                pc = cote.plafon(lim_cereri, fereastra, prioritate)
                pt = cote.plafon(lim_tokeni, fereastra, prioritate)
                inceput = cote.inceput_fereastra(acum, fereastra, r.reset_zi_ora)
                sfarsit = cote.reluare_dupa(cote.sfarsit_fereastra(acum, fereastra, r.reset_zi_ora))
                if pt is not None and tokeni > pt:
                    refuzuri.append(
                        Refuz(sfarsit, f"cererea nu încape în limita de tokeni pe {fereastra}", True)
                    )
                    continue
                rand = db.execute(
                    REZERVA,
                    {
                        "cheie": r.cheie,
                        "fereastra": fereastra.value,
                        "inceput": inceput,
                        "tokeni": tokeni,
                        "plafon_cereri": pc,
                        "plafon_tokeni": pt,
                        "acum": acum,
                    },
                ).first()
                if rand is None:
                    refuzuri.append(Refuz(sfarsit, f"cota pe {fereastra} este epuizată"))
                else:
                    luate.append((r.cheie, fereastra, inceput))
        if refuzuri:
            db.rollback()  # niciun contor nu păstrează o rezervare dintr-o cerere refuzată
            if all(x.imposibil for x in refuzuri):
                return Refuz(max(x.pana_la for x in refuzuri), refuzuri[0].motiv, True)
            return Refuz(max(x.pana_la for x in refuzuri if not x.imposibil), refuzuri[0].motiv)
        return Rezervare(
            tuple(luate),
            tokeni,
            cote.cheie_model(candidat.model_id),
            cote.cheie_furnizor(candidat.furnizor_id),
        )


def regularizeaza(rezervare: Rezervare, tokeni_reali: int | None, *, acum: dt.datetime | None = None) -> None:
    """Înlocuiește tokenii estimați cu cei raportați de furnizor. `None` = rezultat necunoscut (ex. timeout):
    rezervarea rămâne ca estimare. Cererea rămâne numărată, indiferent de rezultat."""
    if tokeni_reali is None or not rezervare.ferestre:
        return
    diferenta = tokeni_reali - rezervare.tokeni_estimati
    if diferenta == 0:
        return
    acum = acum or ceas.acum()
    with sesiune_agentie() as db:
        for cheie, fereastra, inceput in rezervare.ferestre:
            db.execute(
                text(
                    "UPDATE gateway_contoare SET tokeni = GREATEST(0, tokeni + :d), actualizat_la = :acum "
                    "WHERE cheie = :cheie AND fereastra = :fereastra AND inceput = :inceput"
                ),
                {
                    "d": diferenta,
                    "acum": acum,
                    "cheie": cheie,
                    "fereastra": fereastra.value,
                    "inceput": inceput,
                },
            )


def _ridica_contor(
    db: Session,
    cheie: str,
    fereastra: Fereastra,
    inceput: dt.datetime,
    *,
    cereri: int | None,
    tokeni: int | None,
    acum: dt.datetime,
) -> None:
    """Contorul nu coboară niciodată din cauza antetelor (numărătoarea noastră poate include cereri în
    zbor)."""
    db.execute(
        text(
            "INSERT INTO gateway_contoare AS c (cheie, fereastra, inceput, cereri, tokeni, actualizat_la) "
            "VALUES (:cheie, :fereastra, :inceput, COALESCE(:cereri, 0), COALESCE(:tokeni, 0), :acum) "
            "ON CONFLICT (cheie, fereastra, inceput) DO UPDATE SET "
            "cereri = GREATEST(c.cereri, COALESCE(:cereri, 0)), "
            "tokeni = GREATEST(c.tokeni, COALESCE(:tokeni, 0)), "
            "actualizat_la = :acum"
        ).bindparams(bindparam("cereri", type_=Integer), bindparam("tokeni", type_=BigInteger)),
        {
            "cheie": cheie,
            "fereastra": fereastra.value,
            "inceput": inceput,
            "cereri": cereri,
            "tokeni": tokeni,
            "acum": acum,
        },
    )


def corecteaza_din_antete(
    candidat: Candidat, antete: AntetLimita, *, acum: dt.datetime | None = None
) -> None:
    """Antetele furnizorului sunt sursa de adevăr (8.4): ce spun că a rămas devine, dacă e mai puțin decât ce
    credeam noi, noul consum al ferestrei; ce a ajuns la zero blochează resursa până la resetare.

    Ce fereastră descriu antetele și ce resursă (modelul sau contul) este o DATĂ a furnizorului
    (`parametri.antete_cereri`, `antete_tokeni`: `minut` | `zi`; `antete_cheie`: `model` | `furnizor`)."""
    if antete.gol:
        return
    acum = acum or ceas.acum()
    p = candidat.parametri
    pe_cont = p.get("antete_cheie") == "furnizor"
    resursa = (
        Resursa(cote.cheie_furnizor(candidat.furnizor_id), candidat.limite_furnizor, candidat.reset_zi_ora)
        if pe_cont
        else Resursa(cote.cheie_model(candidat.model_id), candidat.limite_model, candidat.reset_zi_ora)
    )
    with sesiune_agentie() as db:
        for ramas, limita_antet, reset, axa, implicit in (
            (antete.ramas_cereri, antete.limita_cereri, antete.reset_cereri_la, "cereri", "minut"),
            (antete.ramas_tokeni, antete.limita_tokeni, antete.reset_tokeni_la, "tokeni", "minut"),
        ):
            if ramas is None:
                continue
            fereastra = Fereastra(p.get(f"antete_{axa}", implicit))
            lim_cereri, lim_tokeni = resursa.limite.pe(fereastra)
            limita = limita_antet or (lim_cereri if axa == "cereri" else lim_tokeni)
            inceput = cote.inceput_fereastra(acum, fereastra, resursa.reset_zi_ora)
            if limita is not None:
                folosit = max(0, limita - ramas)
                _ridica_contor(
                    db, resursa.cheie, fereastra, inceput,
                    cereri=folosit if axa == "cereri" else None,
                    tokeni=folosit if axa == "tokeni" else None,
                    acum=acum,
                )  # fmt: skip
            if ramas == 0:
                pana_la = reset or cote.sfarsit_fereastra(acum, fereastra, resursa.reset_zi_ora)
                _blocheaza(db, resursa.cheie, pana_la, f"antetele furnizorului: {axa} epuizate", acum)


def _blocheaza(db: Session, cheie: str, pana_la: dt.datetime, motiv: str, acum: dt.datetime) -> None:
    db.execute(
        text(
            "INSERT INTO gateway_blocaje AS b (cheie, pana_la, motiv, actualizat_la) "
            "VALUES (:cheie, :pana_la, :motiv, :acum) "
            "ON CONFLICT (cheie) DO UPDATE SET pana_la = GREATEST(b.pana_la, :pana_la), "
            "motiv = CASE WHEN :pana_la >= b.pana_la THEN :motiv ELSE b.motiv END, actualizat_la = :acum"
        ),
        {"cheie": cheie, "pana_la": pana_la, "motiv": motiv[:200], "acum": acum},
    )


def blocheaza_dupa_429(
    candidat: Candidat, retry_dupa_sec: float | None, *, acum: dt.datetime | None = None
) -> dt.datetime:
    """Furnizorul a răspuns 429: blocăm modelul (și contul, dacă limita lui e pe cont) până la resetare."""
    acum = acum or ceas.acum()
    pana_la = cote.pana_la_dupa_429(retry_dupa_sec, acum)  # momentul brut; blocajul se citește cu marjă
    chei = [cote.cheie_model(candidat.model_id)]
    if candidat.parametri.get("antete_cheie") == "furnizor":
        chei.append(cote.cheie_furnizor(candidat.furnizor_id))
    with sesiune_agentie() as db:
        for cheie in chei:
            _blocheaza(db, cheie, pana_la, "429 de la furnizor", acum)
    return cote.reluare_dupa(pana_la)


def curata(*, acum: dt.datetime | None = None) -> int:
    """Șterge contoarele și blocajele vechi (rulează o dată pe zi). Întoarce câte rânduri a șters."""
    acum = acum or ceas.acum()
    limita = acum - dt.timedelta(days=PASTRARE_CONTOARE_ZILE)
    with sesiune_agentie() as db:
        sterse = 0
        for tabel, coloana in (("gateway_contoare", "inceput"), ("gateway_blocaje", "pana_la")):
            r = db.execute(text(f"DELETE FROM {tabel} WHERE {coloana} < :l"), {"l": limita})  # noqa: S608
            sterse += r.rowcount if isinstance(r, CursorResult) else 0
    return sterse
