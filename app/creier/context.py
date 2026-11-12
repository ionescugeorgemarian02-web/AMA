"""Constructorul de context (F4.7, docs/10 §10.3): pachetul pe care îl primește o sarcină din Creierul
clientului.

Pentru o sarcină (client, tip, canal, întrebare / brief, livrabil) pachetul conține, în ordinea priorității
la tăiere:
1. reguli și interdicții (constrângerile aprobate ale clientului și ale platformei; obligatorii: nu se
   taie);
2. fapte aprobate și valabile, relevante pentru sarcină (`fapte.pentru_context`: doar ce a aprobat un om);
3. oferte valabile cu faptele lor valabile (`oferte.pentru_context`);
4. ghidul de brand aprobat (profilul; F4.5 îl produce; până atunci lipsa se spune explicit în `lipsuri`);
5. pasaje din materialele clientului găsite prin căutarea hibridă (F4.3), fără sursele care nu se pot
   reutiliza (statutul concurenței, 21.11), marcate ca extern când intră în prompt (`ca_text`).

Bugetul de tokeni se aplică determinist (`buget.alege`); fiecare element poartă identificatorul și versiunea
sursei. Pachetul se salvează (referințe + instantaneu compact) și se leagă de livrabil. Determinist:
aceleași intrări (inclusiv `la`) → aceeași amprentă. Faptele nu se citesc altfel decât prin `pentru_context`
(garda `tests/unit/test_creier_garda_context.py`).
"""

import dataclasses
import datetime as dt
import uuid

from sqlalchemy.orm import Session

from app import cercetare, gateway
from app.creier import buget, citire, fapte, oferte, pachete
from app.creier import cautare as cautare_hibrida
from app.creier import pasaje as nucleu
from app.creier.compartimente import Compartiment
from app.creier.pachete import Element, PachetContext

BUGET_IMPLICIT = 3000
MAX_FAPTE, MAX_OFERTE, MAX_PASAJE = 20, 8, 6
PRIORITATI = ["reguli", "fapte", "oferte", "ghid", "pasaje"]
OBLIGATORII = frozenset({"reguli"})
ORDINE_IN_TEXT = ["ghid", "reguli", "fapte", "oferte", "pasaje"]
TITLURI = {
    "ghid": "Ghid de brand (aprobat)", "reguli": "Reguli și interdicții", "fapte": "Fapte aprobate",
    "oferte": "Oferte valabile", "pasaje": "Pasaje din materialele clientului",
}  # fmt: skip
SEMNALE_MEREU = frozenset({"mentiune_legala"})  # mențiunile legale intră mereu printre faptele relevante
CARACTERE_PASAJ_IN_PROMPT = 1200


def _tulpini(text: str) -> set[str]:
    """Cuvintele semnificative, pe tulpină ușoară (aceeași ca la căutarea de text: „cafeaua” = „cafea”)."""
    return {cautare_hibrida.stem_usor(j) for j in nucleu.jetoane(text)}


def _scor(tulpini_sarcina: set[str], text: str) -> int:
    return len(tulpini_sarcina & _tulpini(text))


def _text_fapt(f: fapte.FaptPropus) -> str:
    v = f.valoare or {}
    valoare = ""
    if v.get("numar") is not None:
        moneda = f" {v['moneda']}" if v.get("moneda") else ""
        unitate = f"/{v['unitate']}" if v.get("unitate") else ""
        valoare = f" [{v['numar']}{moneda}{unitate}]"
    return f"{f.subiect}: {f.afirmatie}{valoare}"


def _text_oferta(o: oferte.OfertaContext) -> str:
    p = o.pret
    unitate = f"/{p['unitate']}" if p.get("unitate") else ""
    bucati = [f"{o.nume} ({o.tip}): {p.get('numar')} {p.get('moneda', 'RON')}{unitate}"]
    if o.pret_referinta:
        bucati.append(
            f"preț de referință {o.pret_referinta.get('numar')} {o.pret_referinta.get('moneda', 'RON')}"
        )
    bucati += [x for x in (o.descriere, o.conditii, o.garantie) if x]
    return "; ".join(bucati)


def construieste(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    tip_sarcina: str,
    intrebare: str,
    canal: str | None = None,
    livrabil_id: uuid.UUID | None = None,
    la: dt.datetime | None = None,
    buget_tokeni: int = BUGET_IMPLICIT,
    utilizator_id: uuid.UUID | None = None,
    salveaza: bool = True,
) -> PachetContext:
    """Pachetul de context al unei sarcini. `intrebare` este brieful / întrebarea. `la`: data pentru care se
    citesc faptele (implicit acum, la secundă). Cu `salveaza=True` pachetul se scrie (și se leagă de
    `livrabil_id`)."""
    la = la or dt.datetime.now(dt.UTC).replace(microsecond=0)
    if buget_tokeni < 1:
        raise ValueError("bugetul de tokeni trebuie să fie pozitiv")
    tulpini = _tulpini(f"{intrebare} {tip_sarcina.replace('_', ' ')}")
    candidati: list[buget.Candidat] = []
    elemente: dict[str, Element] = {}
    lipsuri: list[str] = []

    def adauga(sectiune: str, tip: str, id_: str, versiune: int | None, text: str, **detalii: object) -> None:
        cheie = f"{sectiune}:{id_}"
        elemente[cheie] = Element(
            sectiune, tip, id_, versiune, text, buget.estimeaza_tokeni(text), dict(detalii)
        )
        candidati.append(buget.Candidat(sectiune, cheie, text))

    for r in citire.pentru_context(db, tenant_id, Compartiment.CONSTRANGERI, la, cu_platforma=True):
        adauga(
            "reguli",
            "constrangere",
            str(r.intrare_id),
            r.versiune,
            r.text,
            nivel=r.nivel,
            cheie_intrare=r.cheie,
        )
    oferte_rel = sorted(
        (
            (s, o)
            for o in oferte.pentru_context(db, tenant_id, la)
            if (s := _scor(tulpini, f"{o.nume} {o.descriere}")) > 0
        ),
        key=lambda p: (-p[0], str(p[1].intrare_id)),
    )[:MAX_OFERTE]
    legate = {x for _, o in oferte_rel for x in o.fapte}  # faptele ofertelor alese sunt relevante prin ele
    relevante = sorted(
        (
            (s, f)
            for f in fapte.pentru_context(db, tenant_id, la)
            if (s := _scor(tulpini, f"{f.subiect} {f.afirmatie}")) > 0
            or f.tip in SEMNALE_MEREU
            or f.intrare_id in legate
        ),
        key=lambda p: (-p[0], str(p[1].intrare_id)),
    )[:MAX_FAPTE]
    for s, f in relevante:
        adauga("fapte", "fapt", str(f.intrare_id), f.versiune, _text_fapt(f), tip_fapt=f.tip, scor=s,
               sursa_tip=f.sursa_tip, sursa_ref=f.sursa_ref, sursa_citat=f.sursa_citat)  # fmt: skip
    if not relevante:
        lipsuri.append(
            "fapte_relevante"
        )  # 9.3: lipsa unui fapt necesar oprește livrabilul cu o întrebare, nu o presupunere
    for s, o in oferte_rel:
        adauga("oferte", "oferta", str(o.intrare_id), o.versiune, _text_oferta(o), scor=s,
               fapte=sorted(str(x) for x in o.fapte))  # fmt: skip
    profil = citire.pentru_context(db, tenant_id, Compartiment.PROFIL_BRAND, la)
    if profil:
        for r in profil:
            adauga("ghid", "profil", str(r.intrare_id), r.versiune, r.text, cheie_intrare=r.cheie)
    else:
        lipsuri.append("ghid_brand")  # F4.5 îl produce; până atunci lipsa e explicită, nu o presupunere
    surse_ok = [s.id for s in cercetare.surse(db, tenant_id) if cercetare.STATUTE[s.statut].reutilizare_text]
    if surse_ok:
        raspuns = cautare_hibrida.cauta(
            db, tenant_id=tenant_id, intrebare=intrebare, limita=MAX_PASAJE, surse=surse_ok
        )
        for p in raspuns.rezultate:  # în ordinea relevanței; ce se trimite este ce se numără la buget
            text = p.text[:CARACTERE_PASAJ_IN_PROMPT]
            adauga(
                "pasaje", "pasaj", str(p.pasaj_id), p.versiune_document, text,
                document_id=str(p.document_id), sursa_id=str(p.sursa_id), url=p.url, titlu=p.titlu,
                pozitie=p.pozitie, car_inceput=p.car_inceput, car_sfarsit=p.car_sfarsit,
                scor=round(p.scor, 6), extern=True, trunchiat=len(p.text) > CARACTERE_PASAJ_IN_PROMPT,
            )  # fmt: skip
        if raspuns.degradat:
            lipsuri.append("vectori_indisponibili")
    else:
        lipsuri.append("pasaje_materiale")
    alegere = buget.alege(candidati, prioritati=PRIORITATI, obligatorii=OBLIGATORII, buget=buget_tokeni)
    finale = tuple(elemente[c.cheie] for c in alegere.pastrate)
    taiate = tuple(
        {"sectiune": c.sectiune, "id": elemente[c.cheie].id, "motiv": m} for c, m in alegere.taiate
    )
    pachet = PachetContext(
        id=None, tenant_id=tenant_id, livrabil_id=livrabil_id, tip_sarcina=tip_sarcina, canal=canal,
        intrebare=intrebare[:2000], la=la, buget_tokeni=buget_tokeni, tokeni_folositi=alegere.tokeni,
        depasit=alegere.depasit, elemente=finale, lipsuri=tuple(lipsuri), taiate=taiate, amprenta="",
    )  # fmt: skip
    pachet = dataclasses.replace(pachet, amprenta=pachete.amprenta(pachete.continut_canonic(pachet)))
    return pachete.salveaza(db, pachet, utilizator_id=utilizator_id) if salveaza else pachet


def ca_text(p: PachetContext) -> str:
    """Pachetul, gata de pus într-un prompt. Pasajele sunt text extern: intră doar prin `marcheaza_extern`
    (identificatorul blocului e aleatoriu, deci textul de prompt nu e identic de la o randare la alta;
    pachetul salvat, da)."""
    blocuri: list[str] = []
    for sectiune in ORDINE_IN_TEXT:
        elem = p.sectiune(sectiune)
        if not elem:
            continue
        linii = []
        for e in elem:
            if e.detalii.get("extern"):
                linii.append(
                    gateway.marcheaza_extern(e.text, sursa="pagina", max_caractere=CARACTERE_PASAJ_IN_PROMPT)
                )
            else:
                linii.append(f"- {e.text}")
        blocuri.append(f"## {TITLURI[sectiune]}\n" + "\n".join(linii))
    if p.lipsuri:
        blocuri.append("## Lipsuri\n" + "\n".join(f"- {x}" for x in p.lipsuri))
    return "\n\n".join(blocuri)


ale_livrabilului = pachete.ale_livrabilului
citeste_pachet = pachete.citeste_pachet
