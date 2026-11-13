"""Probleme găsite de un validator determinist și transformarea lor într-un verdict (9.2). Nucleu pur.

Validatorii deterministe găsesc `Problema`-e (fragmentul, regula, instrucțiunea); `verdict_din_probleme` le
adună într-un
singur verdict al validatorului: fără probleme `trece`; cu cel puțin una blocantă `esec` (`majora`, sau
`critica` dacă una
e critică); doar neblocante `avertisment`. Instrucțiunile identice se spun o singură dată.
"""

from dataclasses import dataclass

from app.validare.verdict import Cost, Dovada, Severitate, Treapta, Verdict, avertisment, esec, trece


@dataclass(frozen=True)
class Problema:
    regula: str  # identificatorul regulii încălcate (ex. „G1.camp_lipsa”, „G3.fb.sanatate-1”)
    fragment: str  # fragmentul EXACT din text (gol pentru ce lipsește)
    instructiune: str  # ce are de făcut autorul
    blocant: bool = True
    severitate: Severitate = (
        Severitate.MAJORA
    )  # contează la `blocant`: majora / critica; la avertisment: minora / majora
    detalii: str = ""

    def dovada(self) -> Dovada:
        return Dovada(self.fragment, self.regula, self.detalii)


def verdict_din_probleme(
    validator: str,
    versiune: str,
    treapta: Treapta,
    probleme: list[Problema],
    *,
    cost: Cost | None = None,
    detalii: dict[str, object] | None = None,
) -> Verdict:
    extra = {"detalii": dict(detalii)} if detalii else {}
    cost_ = {"cost": cost} if cost else {}
    if not probleme:
        return trece(validator, versiune, treapta, **extra, **cost_)
    instructiuni = list(dict.fromkeys(p.instructiune for p in probleme))
    mesaj = " ".join(instructiuni)
    dovezi = [p.dovada() for p in probleme]
    blocante = [p for p in probleme if p.blocant]
    n_total, n_bloc = len(probleme), len(blocante)
    if blocante:
        critic = any(p.severitate is Severitate.CRITICA for p in blocante)
        return esec(
            validator,
            versiune,
            treapta,
            dovezi=dovezi,
            instructiune=mesaj,
            severitate=Severitate.CRITICA if critic else Severitate.MAJORA,
            scor=round(max(0.0, 1.0 - n_bloc / max(n_total, 1) - 0.2), 2),
            **extra,
            **cost_,
        )
    major = any(p.severitate is Severitate.MAJORA for p in probleme)
    return avertisment(
        validator,
        versiune,
        treapta,
        dovezi=dovezi,
        instructiune=mesaj,
        severitate=Severitate.MAJORA if major else Severitate.MINORA,
        scor=0.7 if major else 0.85,
        **extra,
        **cost_,
    )
