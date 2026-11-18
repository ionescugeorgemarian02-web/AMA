"""Generatorul de oferte (F12.6, docs/17 §17.7, J5): oferta pornește din audit și din pachete; tu o aprobi.

- **Din audit:** constatările și recomandările raportului de audit al lead-ului (site-ul, F7.2) devin „ce am
  găsit” și „ce facem în primele 30 de zile”. Fără raport gata, nu există ofertă.
- **Din pachete:** planul se alege din bugetul declarat la calificare (F12.4); prețul, livrabilele și ce nu
  include vin din `app.finante.planuri`, singura sursă a prețurilor (aceleași ca pe site și la facturare).
- **Verificări deterministe** înainte să ajungă la tine: prețul e cel din catalog, nicio promisiune de
  rezultat garantat, un singur apel la acțiune, constatări din audit prezente. O ofertă care pică e „blocată”.
- **Aprobarea e a omului:** oferta stă „de aprobat” (notificare + ecranul `/crm/oferte`). Aprobată, pleacă pe
  email (tranzacțional: lead-ul a cerut-o în apel) și lead-ul trece în „ofertă trimisă”. Respinsă, cu motiv.
  Componentă D (D-024): textul e compus din date, nu scris de un model.
"""

import datetime as dt
import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.crm import calificare, registru
from app.crm.modele import Contact, Firma, LeadCrm, Oferta
from app.crm.registru import CrmRefuzat
from app.finante import planuri
from app.ids import new_id
from app.operare import audit, notificari, urme
from app.operare.efecte import sistem

VALABILITATE_ZILE = 14  # [I]
PACHET_DUPA_BUGET = {"1000_3000": "start", "3000_10000": "crestere", "peste_10000": "pro"}
PACHET_IMPLICIT = "crestere"
PROMISIUNI = re.compile(r"\b(garant\w*|100\s?%|sigur\w* (?:vânzări|clienți)|dublăm|triplăm)\b", re.IGNORECASE)
APEL = "Răspundeți la acest email cu „Accept” și pornim onboardingul."
ETICHETE_STARE = {
    "de_aprobat": "de aprobat",
    "aprobata": "aprobată",
    "respinsa": "respinsă",
    "blocata": "blocată",
}


def alege_pachet(buget: str | None) -> str:
    return PACHET_DUPA_BUGET.get(buget or "", PACHET_IMPLICIT)


def compune(firma: str, raport: dict[str, Any], pachet: str) -> dict[str, Any]:
    """Conținutul ofertei, din audit și din plan (pur)."""
    p = planuri.PLANURI[pachet]
    livrabile = [
        f"{n} {planuri.ETICHETE_LIVRABILE.get(t, t)} pe lună" for t, n in p.livrabile.items() if n > 0
    ]
    return {
        "titlu": f"Oferta pentru {firma}: pachetul {p.nume}",
        "rezumat": str(raport.get("rezumat", "")),
        "constatari": [str(x) for x in raport.get("constatari", [])][:5],
        "primele_30_de_zile": [str(x) for x in raport.get("recomandari", [])][:5],
        "pachet": {
            "cod": p.cod,
            "nume": p.nume,
            "pentru": p.pentru,
            "livrabile": livrabile,
            "canale": p.canale,
            "nu_include": list(p.nu_include),
        },
        "pret_lunar": p.pret_lunar,
        "setup": planuri.SETUP,
        "valabilitate_zile": VALABILITATE_ZILE,
        "apel": APEL,
        "mentiune": "Prețuri în lei, fără TVA. Ofertă pregătită din auditul site-ului, verificată de un om.",
    }


def text_oferta(c: dict[str, Any]) -> str:
    linii = [c["titlu"], "", c["rezumat"], "", "Ce am găsit în audit:"]
    linii += [f"- {x}" for x in c["constatari"]]
    linii += ["", "Ce facem în primele 30 de zile:"] + [f"- {x}" for x in c["primele_30_de_zile"]]
    pk = c["pachet"]
    linii += ["", f"Pachetul {pk['nume']} ({pk['pentru']}):"] + [f"- {x}" for x in pk["livrabile"]]
    linii += [f"- {pk['canale']} canale", "Nu include: " + ", ".join(pk["nu_include"]), ""]
    linii += [
        f"Preț: {c['pret_lunar']} lei pe lună; configurarea inițială: {c['setup']} lei, o singură dată."
    ]
    linii += [f"Oferta e valabilă {c['valabilitate_zile']} zile.", "", c["apel"], "", c["mentiune"]]
    return "\n".join(linii)


def verifica(c: dict[str, Any]) -> dict[str, Any]:
    """Verificările deterministe ale ofertei. `trece` doar dacă toate trec."""
    p = planuri.PLANURI[c["pachet"]["cod"]]
    text = text_oferta(c)
    rez = {
        "pret_din_catalog": c["pret_lunar"] == p.pret_lunar and c["setup"] == planuri.SETUP,
        "fara_promisiuni_garantate": PROMISIUNI.search(text) is None,
        "un_singur_apel": text.count("Răspundeți la acest email") == 1,
        "constatari_din_audit": len(c["constatari"]) > 0,
    }
    return {**rez, "trece": all(rez.values())}


def genereaza(
    db: Session, lead_id: uuid.UUID, *, raport: dict[str, Any] | None = None, acum: dt.datetime | None = None
) -> Oferta:
    """Scrie oferta unui lead și o trimite la aprobare. `raport` lipsă: se citește auditul din site."""
    acum = acum or dt.datetime.now(dt.UTC)
    lead = db.get(LeadCrm, lead_id)
    if lead is None or lead.etapa in registru.INCHISE:
        raise CrmRefuzat("lead inexistent sau închis")
    if raport is None and lead.lead_site_id is not None:
        from app.site import audit as site_audit  # import târziu: site-ul importă deja CRM-ul

        raport = site_audit.raport_pentru_lead(db, lead.lead_site_id)
    if not raport:
        raise CrmRefuzat("oferta pornește din audit: lead-ul nu are încă un raport de audit gata")
    firma = db.get(Firma, lead.firma_id)
    c_curenta = calificare.curenta(db, lead.id)
    pachet = alege_pachet(c_curenta.raspunsuri.get("buget") if c_curenta else None)
    continut = compune(firma.nume if firma else "firma dumneavoastră", raport, pachet)
    v = verifica(continut)
    o = Oferta(
        id=new_id(), lead_id=lead.id, pachet=pachet,
        pret_lunar=continut["pret_lunar"], setup=continut["setup"],
        continut=continut, verificari=v, stare="de_aprobat" if v["trece"] else "blocata", creat_la=acum,
    )  # fmt: skip
    try:
        with db.begin_nested():
            db.add(o)
            db.flush()
    except IntegrityError:
        raise CrmRefuzat("lead-ul are deja o ofertă care așteaptă aprobarea") from None
    registru.adauga_activitate(db, lead.id, "oferta", f"Ofertă {planuri.PLANURI[pachet].nume} pregătită.")
    audit.record(
        db, "crm.oferta_generata", obiect_tip="oferta", obiect_id=o.id, actor_tip="sistem",
        detalii={"pachet": pachet, "stare": o.stare},
    )  # fmt: skip
    urme.inregistreaza(
        db, "crm", "oferta_generata", rezultat="ok" if v["trece"] else "blocat", obiect_tip="oferta",
        obiect_id=str(o.id), intrari={"lead": str(lead.id), "din_audit": True},
        iesiri={"pachet": pachet, **v},
    )  # fmt: skip
    if v["trece"]:
        registru.dupa_commit(
            db,
            lambda: notificari.notifica(
                notificari.Nivel.IMPORTANT,
                "Ofertă de aprobat",
                "O ofertă nouă așteaptă decizia ta.",
                url="/crm/oferte",
            ),
        )
    return o


def _deschisa(db: Session, oferta_id: uuid.UUID) -> Oferta:
    o = db.execute(select(Oferta).where(Oferta.id == oferta_id).with_for_update()).scalar_one_or_none()
    if o is None or o.stare != "de_aprobat":
        raise CrmRefuzat("oferta nu există sau nu mai așteaptă aprobarea")
    return o


def aproba(db: Session, oferta_id: uuid.UUID, *, utilizator_id: uuid.UUID) -> Oferta:
    o = _deschisa(db, oferta_id)
    lead = db.get(LeadCrm, o.lead_id)
    contact = db.get(Contact, lead.contact_id) if lead else None
    if lead is None or contact is None:
        raise CrmRefuzat("lead inexistent")
    o.stare, o.decis_de, o.decis_la = "aprobata", utilizator_id, dt.datetime.now(dt.UTC)
    # Tranzacțional: lead-ul a cerut oferta în apel (F12.2: lista locurilor cu emailuri necomerciale)
    sistem.cere(
        db, "email", cheie=f"oferta:{o.id}",
        payload={"catre": contact.email, "subiect": o.continut["titlu"], "text": text_oferta(o.continut)},
    )  # fmt: skip
    if lead.etapa != "oferta_trimisa":
        registru.muta_etapa(db, lead.id, "oferta_trimisa", utilizator_id=utilizator_id)
    audit.record(db, "crm.oferta_aprobata", obiect_tip="oferta", obiect_id=o.id, utilizator_id=utilizator_id)
    urme.inregistreaza(
        db, "crm", "oferta_aprobata", obiect_tip="oferta", obiect_id=str(o.id), actor=str(utilizator_id)
    )
    return o


def respinge(db: Session, oferta_id: uuid.UUID, *, utilizator_id: uuid.UUID, motiv: str) -> Oferta:
    motiv = motiv.strip()
    if not 3 <= len(motiv) <= 500:
        raise CrmRefuzat("spune pe scurt de ce respingi oferta (3–500 de caractere)")
    o = _deschisa(db, oferta_id)
    o.stare, o.motiv, o.decis_de, o.decis_la = "respinsa", motiv, utilizator_id, dt.datetime.now(dt.UTC)
    registru.adauga_activitate(db, o.lead_id, "oferta", f"Ofertă respinsă: {motiv}", utilizator_id)
    audit.record(
        db, "crm.oferta_respinsa", obiect_tip="oferta", obiect_id=o.id, utilizator_id=utilizator_id,
        rezultat="refuzat", detalii={"motiv": motiv[:200]},
    )  # fmt: skip
    urme.inregistreaza(
        db, "crm", "oferta_respinsa", rezultat="respins", motiv=motiv[:200], obiect_tip="oferta",
        obiect_id=str(o.id), actor=str(utilizator_id),
    )  # fmt: skip
    return o


def de_aprobat(db: Session) -> list[tuple[Oferta, LeadCrm, Firma]]:
    return [
        (o, lead, f)
        for o, lead, f in db.execute(
            select(Oferta, LeadCrm, Firma)
            .join(LeadCrm, LeadCrm.id == Oferta.lead_id)
            .join(Firma, Firma.id == LeadCrm.firma_id)
            .where(Oferta.stare.in_(("de_aprobat", "blocata")))
            .order_by(Oferta.creat_la)
        ).tuples()
    ]
