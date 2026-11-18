"""Nucleul modelelor predictive (N6, F14.3 și F14.5): gradient boosting mic, scris în proiect (D-020), și
evaluarea pe date trecute față de o referință, cu marja măsurată.

- **Modelul:** boosting cu cioturi de decizie (un prag pe o trăsătură), pierdere logistică, pas Newton în
  frunze. Trăsăturile sunt numerice; categoriile devin indicatori 0/1 (`codifica`).
- **Evaluarea** (`evalueaza`): împărțire în timp (primele 70% antrenare, ultimele 30% test: modelul nu vede
  viitorul), AUC pe test pentru model și pentru referință (alegerea la întâmplare sau regula simplă), plus
  intervalul bootstrap pereche al diferenței. Modelul „bate” referința doar dacă marginea de jos a
  intervalului trece de `MARJA`.
- **Pragul de date:** sub prag nu se antrenează nimic; rândul din `modele_predictive` spune doar câte exemple
  sunt și cât lipsește.
"""

import datetime as dt
import math
import random
import uuid
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.invatare.modele import ModelPredictiv
from app.operare import urme

NUME = "invatare.predictiv"
MARJA = 0.05  # cu cât trebuie să depășească AUC-ul modelului pe cel al referinței (marginea de jos) [I]
FRACTIE_TEST = 0.30
RUNDE, RATA, MIN_FRUNZA = 60, 0.2, 10
N_BOOTSTRAP = 300


@dataclass(frozen=True)
class Exemplu:
    """Un caz trecut: trăsăturile, eticheta (1 = succes / câștigat / a plecat), momentul și scorul regulii
    simple."""

    trasaturi: dict[str, float]
    eticheta: int
    moment: dt.datetime
    scor_regula: float | None = None


@dataclass(frozen=True)
class Ciot:
    trasatura: int
    prag: float
    stanga: float
    dreapta: float


@dataclass
class Model:
    trasaturi: list[str]
    baza: float
    rata: float
    cioturi: list[Ciot] = field(default_factory=list)

    def scor(self, x: Sequence[float]) -> float:
        f = self.baza + sum(
            self.rata * (c.stanga if x[c.trasatura] <= c.prag else c.dreapta) for c in self.cioturi
        )
        return _sigmoid(f)

    def ca_dict(self) -> dict[str, Any]:
        return {"trasaturi": self.trasaturi, "baza": self.baza, "rata": self.rata,
                "cioturi": [asdict(c) for c in self.cioturi]}  # fmt: skip

    @classmethod
    def din_dict(cls, d: dict[str, Any]) -> "Model":
        return cls(
            list(d["trasaturi"]), float(d["baza"]), float(d["rata"]), [Ciot(**c) for c in d["cioturi"]]
        )


def codifica(exemple: Sequence[dict[str, Any]]) -> tuple[list[str], list[list[float]]]:
    """Trăsăturile ca matrice: numerele rămân, textele devin indicatori `camp=valoare` (sortați, stabili)."""
    nume: set[str] = set()
    for e in exemple:
        for k, v in e.items():
            nume.add(f"{k}={v}" if isinstance(v, str) else k)
    coloane = sorted(nume)
    poz = {c: i for i, c in enumerate(coloane)}
    X = []
    for e in exemple:
        rand = [0.0] * len(coloane)
        for k, v in e.items():
            if isinstance(v, str):
                rand[poz[f"{k}={v}"]] = 1.0
            else:
                rand[poz[k]] = float(v)
        X.append(rand)
    return coloane, X


def _sigmoid(f: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, f))))


def _ordine(X: list[list[float]], j: int) -> list[int]:
    return sorted(range(len(X)), key=lambda i: X[i][j])


def antreneaza(
    trasaturi: list[str], X: list[list[float]], y: list[int], *, runde: int = RUNDE, rata: float = RATA,
    min_frunza: int = MIN_FRUNZA,
) -> Model:  # fmt: skip
    n = len(y)
    p0 = min(max(sum(y) / n, 1e-3), 1 - 1e-3)
    m = Model(trasaturi, math.log(p0 / (1 - p0)), rata)
    F = [m.baza] * n
    ordini = [_ordine(X, j) for j in range(len(trasaturi))]
    for _ in range(runde):
        p = [_sigmoid(f) for f in F]
        r = [y[i] - p[i] for i in range(n)]
        h = [p[i] * (1 - p[i]) for i in range(n)]
        total_r, total_h = sum(r), sum(h)
        cel_mai_bun: tuple[float, int, float] | None = None
        for j, ordine in enumerate(ordini):
            sr = sh = 0.0
            for k in range(n - 1):
                i = ordine[k]
                sr, sh = sr + r[i], sh + h[i]
                v, urm = X[i][j], X[ordine[k + 1]][j]
                if v == urm or k + 1 < min_frunza or n - k - 1 < min_frunza:
                    continue
                castig = sr * sr / (sh + 1e-9) + (total_r - sr) ** 2 / (total_h - sh + 1e-9)
                if cel_mai_bun is None or castig > cel_mai_bun[0]:
                    cel_mai_bun = (castig, j, (v + urm) / 2)
        if cel_mai_bun is None:
            break
        _, j, prag = cel_mai_bun
        st = [i for i in range(n) if X[i][j] <= prag]
        dr = [i for i in range(n) if X[i][j] > prag]
        val_st = sum(r[i] for i in st) / (sum(h[i] for i in st) + 1e-9)
        val_dr = sum(r[i] for i in dr) / (sum(h[i] for i in dr) + 1e-9)
        c = Ciot(j, prag, max(-4.0, min(4.0, val_st)), max(-4.0, min(4.0, val_dr)))
        m.cioturi.append(c)
        for i in range(n):
            F[i] += rata * (c.stanga if X[i][j] <= prag else c.dreapta)
    return m


def auc(scoruri: Sequence[float], y: Sequence[int]) -> float:
    """Aria de sub curba ROC (Mann-Whitney, cu egalitățile la jumătate). 0,5 dacă lipsește o clasă."""
    poz = [s for s, e in zip(scoruri, y, strict=True) if e == 1]
    neg = [s for s, e in zip(scoruri, y, strict=True) if e == 0]
    if not poz or not neg:
        return 0.5
    perechi = sorted([(s, 1) for s in poz] + [(s, 0) for s in neg])
    suma_rang, i = 0.0, 0
    while i < len(perechi):
        j = i
        while j < len(perechi) and perechi[j][0] == perechi[i][0]:
            j += 1
        rang = (i + j + 1) / 2
        suma_rang += rang * sum(1 for k in range(i, j) if perechi[k][1] == 1)
        i = j
    return (suma_rang - len(poz) * (len(poz) + 1) / 2) / (len(poz) * len(neg))


def compara(
    model: Sequence[float],
    referinta: Sequence[float],
    y: Sequence[int],
    *,
    marja: float = MARJA,
    seed: int = 0,
) -> dict[str, Any]:
    """AUC-ul modelului față de al referinței pe același test, cu intervalul bootstrap pereche (95%)."""
    rng = random.Random(seed)  # noqa: S311  (bootstrap reproductibil, nu criptografie)
    n = len(y)
    dif = []
    for _ in range(N_BOOTSTRAP):
        idx = [rng.randrange(n) for _ in range(n)]
        yy = [y[i] for i in idx]
        dif.append(auc([model[i] for i in idx], yy) - auc([referinta[i] for i in idx], yy))
    dif.sort()
    jos, sus = dif[int(0.025 * N_BOOTSTRAP)], dif[int(0.975 * N_BOOTSTRAP) - 1]
    a_m, a_r = auc(model, y), auc(referinta, y)
    return {"auc_model": round(a_m, 4), "auc_referinta": round(a_r, 4), "diferenta": round(a_m - a_r, 4),
            "interval": [round(jos, 4), round(sus, 4)], "marja": marja, "n_test": n,
            "bate": jos > marja}  # fmt: skip


def evalueaza(exemple: list[Exemplu], *, referinta: str, seed: int = 0) -> tuple[Model, dict[str, Any]]:
    """Antrenează pe trecutul timpuriu și compară pe cel recent. `referinta`: `intamplare` sau `reguli`."""
    ordonate = sorted(exemple, key=lambda e: e.moment)
    taie = int(len(ordonate) * (1 - FRACTIE_TEST))
    nume, X = codifica([e.trasaturi for e in ordonate])
    y = [e.eticheta for e in ordonate]
    m = antreneaza(nume, X[:taie], y[:taie])
    scoruri = [m.scor(x) for x in X[taie:]]
    if referinta == "reguli":
        ref = [float(e.scor_regula or 0.0) for e in ordonate[taie:]]
    else:  # alegerea la întâmplare: același scor pentru toți, AUC = 0,5 (valoarea ei așteptată), fără zgomot
        ref = [0.5] * len(scoruri)
    metrici = compara(scoruri, ref, y[taie:], seed=seed)
    metrici |= {"n_antrenare": taie, "rata_de_baza": round(sum(y[taie:]) / max(1, len(y) - taie), 4)}
    return m, metrici


def ruleaza(
    db: Session, *, tip: str, exemple: list[Exemplu], prag: int, referinta: str, tenant_id: uuid.UUID |
    None = None,
    canal: str = "", acum: dt.datetime | None = None,
) -> ModelPredictiv:  # fmt: skip
    """Verifică pragul, antrenează doar peste el și scrie încercarea (cu urmă)."""
    with urme.span(NUME, f"antreneaza_{tip}", db=db, obiect_tip="model_predictiv", obiect_id=canal or tip,
                   intrari={"n": len(exemple), "prag": prag, "referinta": referinta}) as s:  # fmt: skip
        r = ModelPredictiv(tenant_id=tenant_id, tip=tip, canal=canal, n_exemple=len(exemple), prag=prag,
                           referinta=referinta, antrenat_la=acum or dt.datetime.now(dt.UTC))  # fmt: skip
        if len(exemple) < prag:
            r.stare, r.metrici = "sub_prag", {"lipsesc": prag - len(exemple)}
            s.rezultat, s.motiv = "info", f"sub pragul de date: {len(exemple)} din {prag}"
        else:
            m, metrici = evalueaza(exemple, referinta=referinta)
            r.stare, r.metrici, r.model = ("valid" if metrici["bate"] else "nu_bate"), metrici, m.ca_dict()
            s.rezultat = "ok" if r.stare == "valid" else "info"
        db.add(r)
        db.flush()
        s.iesiri = {
            "stare": r.stare,
            **{k: r.metrici.get(k) for k in ("auc_model", "auc_referinta", "interval")},
        }
        return r


def ultimul(
    db: Session, tip: str, *, tenant_id: uuid.UUID | None = None, canal: str = ""
) -> ModelPredictiv | None:
    q = select(ModelPredictiv).where(ModelPredictiv.tip == tip, ModelPredictiv.canal == canal)
    q = q.where(ModelPredictiv.tenant_id == tenant_id if tenant_id else ModelPredictiv.tenant_id.is_(None))
    return db.execute(q.order_by(ModelPredictiv.antrenat_la.desc()).limit(1)).scalar_one_or_none()


def prezice(r: ModelPredictiv, trasaturi: dict[str, Any]) -> float | None:
    """Probabilitatea dată de un model `valid`; None altfel (sub prag sau nu bate referința)."""
    if r.stare != "valid":
        return None
    m = Model.din_dict(r.model)
    poz = {c: i for i, c in enumerate(m.trasaturi)}
    x = [0.0] * len(m.trasaturi)
    for k, v in trasaturi.items():
        cheie = f"{k}={v}" if isinstance(v, str) else k
        if cheie in poz:
            x[poz[cheie]] = 1.0 if isinstance(v, str) else float(v)
    return m.scor(x)
