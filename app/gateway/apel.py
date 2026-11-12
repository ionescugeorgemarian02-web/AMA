"""Apelul pe UN model, cu cotele: rezervare → cerere → regularizare. Piesa pe care se construiește rutarea
(F3.4).

`incearca_model` nu alege modelul și nu trece pe altul: face un singur lucru cu un model dat. Cota refuzată
este
semnalată prin `CotaEpuizata` (rutarea trece pe următorul candidat; apelul pe un model fixat primește
`Amanat`).
"""

import json

from app.gateway import ceas, client, cote, limitator
from app.gateway.candidat import Candidat
from app.gateway.cote import estimeaza_tokeni
from app.gateway.erori import Amanat, ApelRefuzat, EroareFurnizor
from app.gateway.iesire import Iesire, schema_json
from app.gateway.limitator import Refuz
from app.gateway.structurat import IesireStructurata, ruleaza_structurat
from app.gateway.tipuri import CerereModel, Mesaj, RaspunsModel
from app.operare.motor import Prioritate


class CotaEpuizata(Exception):
    """Cota modelului nu permite apelul acum. Intern gateway-ului."""

    def __init__(self, refuz: Refuz) -> None:
        super().__init__(refuz.motiv)
        self.refuz = refuz


def _caractere(cerere: CerereModel) -> int:
    n = sum(len(m.continut) for m in cerere.mesaje)
    return n + (len(json.dumps(cerere.schema_json)) if cerere.schema_json else 0)


def un_apel(
    candidat: Candidat, cheie: str | None, cerere: CerereModel, prioritate: Prioritate
) -> RaspunsModel:
    """O cerere HTTP cu cota ei: rezervă, trimite, regularizează cu tokenii reali, corectează din antete."""
    rezervare = limitator.rezerva(
        candidat, estimeaza_tokeni(_caractere(cerere), cerere.max_tokeni), prioritate
    )
    if isinstance(rezervare, Refuz):
        raise CotaEpuizata(rezervare)
    try:
        raspuns = client.trimite(candidat.destinatie, cheie, cerere)
    except EroareFurnizor as exc:
        if exc.fel == "limita":
            limitator.blocheaza_dupa_429(candidat, exc.retry_dupa)
        if exc.fel != "retea":  # la timeout nu știm ce a consumat furnizorul: rezervarea rămâne
            limitator.regularizeaza(rezervare, 0)
        raise
    limitator.regularizeaza(rezervare, raspuns.tokeni_intrare + raspuns.tokeni_iesire)
    limitator.corecteaza_din_antete(candidat, raspuns.antete)
    return raspuns


def incearca_model(
    candidat: Candidat,
    cheie: str | None,
    mesaje: tuple[Mesaj, ...],
    schema: type[Iesire],
    *,
    prioritate: Prioritate,
    max_tokeni: int = 1024,
    temperatura: float = 0.2,
) -> IesireStructurata:
    """Apel structurat (cu o reparație) pe `candidat`, fiecare cerere HTTP trecând prin limitator."""
    sj = schema_json(schema)
    nativ = "iesire_structurata" in candidat.capabilitati

    def trimite(m: tuple[Mesaj, ...]) -> RaspunsModel:
        cerere = CerereModel(
            mesaje=m,
            max_tokeni=max_tokeni,
            temperatura=temperatura,
            schema_json=sj if nativ else None,
            schema_nume=schema.__name__,
        )
        return un_apel(candidat, cheie, cerere, prioritate)

    return ruleaza_structurat(trimite, mesaje, schema, nativ=nativ)


def apeleaza_pe_model(
    candidat: Candidat,
    cheie: str | None,
    mesaje: tuple[Mesaj, ...],
    schema: type[Iesire],
    *,
    prioritate: Prioritate = Prioritate.P1,
    max_tokeni: int = 1024,
    temperatura: float = 0.2,
) -> IesireStructurata:
    """Un model fixat, fără rutare: cota epuizată devine `Amanat(pana_la)`. Pentru probe și diagnostic;
    aplicațiile apelează prin profiluri (`gateway.apeleaza`)."""
    try:
        return incearca_model(
            candidat,
            cheie,
            mesaje,
            schema,
            prioritate=prioritate,
            max_tokeni=max_tokeni,
            temperatura=temperatura,
        )
    except CotaEpuizata as exc:
        if exc.refuz.imposibil:
            raise ApelRefuzat("cerere_prea_mare", exc.refuz.motiv) from None
        raise Amanat(exc.refuz.pana_la, exc.refuz.motiv) from None
    except EroareFurnizor as exc:
        if exc.fel == "limita":  # limitatorul l-a blocat deja; apelantul primește momentul reluării
            pana_la = cote.reluare_dupa(cote.pana_la_dupa_429(exc.retry_dupa, ceas.acum()))
            raise Amanat(pana_la, "limită de rată la furnizor") from None
        raise
