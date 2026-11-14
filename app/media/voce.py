"""Vocea (F8.1, docs/14 §14.4, ADR-10): motorul de sinteză în spatele unui adaptor, profilurile de voce cu
licența lor și narațiunea sintetizată frază cu frază, salvată în biblioteca de active cu statutul licenței.

Hotărâri (D-007):
- Profilul se alege din `PROFILURI`; fiecare are motorul, modelul și licența (statut `verificata` /
  `de_verificat` / `refuzata`). Doar o voce `verificata` intră într-un fișier final (`permite_publicarea`).
- Vocea de pornire Piper (set de date CC0) rămâne `de_verificat` până se verifică lanțul de antrenare; vocea
  proprie (acord scris, ~2 ore, antrenare o singură dată) e recomandarea, tot `de_verificat` până există.
- Până la migrare, motorul implicit este cel SIMULAT: semnal sintetic determinist (tonuri pe silabe, liniște
  între cuvinte), fără date de antrenare, deci fără terți în lanțul de drepturi (`verificata`).
- Frazele se sintetizează pe rând, cu pauze de 200 ms (14.4: 150–300 ms); durata reală devine baza de timp.
"""

import re
import shutil
import subprocess
import tempfile
import uuid
import zlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.config import get_settings
from app.media import audio, biblioteca
from app.media.modele import Activ

PAUZA_FRAZE = 0.2  # [I] secunde între fraze (14.4: 150–300 ms)
RATA_SIMULAT = 16000

STATUTE = ("verificata", "de_verificat", "refuzata")


@dataclass(frozen=True)
class LicentaVoce:
    statut: str
    tip: str  # generat_intern / set_de_date / voce_proprie / furnizor
    detinator: str
    dovada: str
    nota: str = ""


@dataclass(frozen=True)
class ProfilVoce:
    cod: str
    motor: str  # simulat / piper
    model: str
    licenta: LicentaVoce
    limba: str = "ro-RO"


PROFILURI: dict[str, ProfilVoce] = {
    "ro-simulat": ProfilVoce(
        "ro-simulat",
        "simulat",
        "ama-simulat-1",
        LicentaVoce(
            "verificata",
            "generat_intern",
            "AMA",
            "semnal sintetic generat de cod, fără date de antrenare și fără terți",
            "SIMULAT: ține locul vocii reale până la migrare",
        ),
    ),
    "ro-piper-pornire": ProfilVoce(
        "ro-piper-pornire",
        "piper",
        "ro_RO-mihai-medium",
        LicentaVoce(
            "de_verificat",
            "set_de_date",
            "set de date public (CC0, declarat)",
            "",
            "dreptul de uz comercial pe tot lanțul de antrenare se verifică la migrare (ADR-10)",
        ),
    ),
    "ro-proprie": ProfilVoce(
        "ro-proprie",
        "piper",
        "ama-voce-proprie",
        LicentaVoce(
            "de_verificat",
            "voce_proprie",
            "AMA",
            "",
            "recomandat: acord scris al vorbitorului, ~2 ore înregistrate, antrenare o singură dată "
            "(GPU închiriat)",
        ),
    ),
}
PROFIL_IMPLICIT = "ro-simulat"


def profil(cod: str | None = None) -> ProfilVoce:
    c = cod or PROFIL_IMPLICIT
    if c not in PROFILURI:
        raise ValueError(f"profil de voce necunoscut: {c}")
    return PROFILURI[c]


def permite_publicarea(licenta: dict[str, Any] | None) -> bool:
    return bool(licenta) and (licenta or {}).get("statut") == "verificata"


class MotorVoce(Protocol):
    def sintetizeaza(
        self, text: str, profil: ProfilVoce, *, gresit: dict[str, str] | None = None
    ) -> audio.Wav:
        """O frază -> WAV mono. `gresit`: doar motorul simulat (cuvinte citite greșit, pentru probe)."""
        ...


VOCALE = re.compile(r"[aeiouăâîy]+", re.IGNORECASE)


def silabe(cuvant: str) -> int:
    return max(1, len(VOCALE.findall(cuvant)))


class MotorVoceSimulat:
    """# SIMULAT: fiecare cuvânt = tonuri pe silabe (0,16 s / silabă), 50 ms de liniște între cuvinte.
    Frecvența vine din cuvânt (crc32), deci același text dă același fișier. Cuvintele rostite se scriu în
    bucata `amaw` (citită doar de transcriptorul simulat). `gresit`: cuvânt -> ce „rostește” în loc."""

    SILABA = 0.16
    INTRE_CUVINTE = 0.05

    def sintetizeaza(
        self, text: str, profil: ProfilVoce, *, gresit: dict[str, str] | None = None
    ) -> audio.Wav:
        r = RATA_SIMULAT
        es = audio.liniste(r, 0.0)
        rostite: list[dict[str, Any]] = []
        cuvinte = text.split()
        for i, c in enumerate(cuvinte):
            spus = (gresit or {}).get(c.strip(".,;:!?"), c)
            inceput = len(es) / r
            for k in range(silabe(spus)):
                f = 110 + (zlib.crc32(f"{spus}:{k}".encode()) % 120)
                es.extend(audio.ton(r, self.SILABA, f))
            rostite.append({"w": spus.strip(".,;:!?"), "s": round(inceput, 3), "e": round(len(es) / r, 3)})
            if i < len(cuvinte) - 1:
                es.extend(audio.liniste(r, self.INTRE_CUVINTE))
        return audio.Wav(r, es, {"cuvinte": rostite})


class MotorPiper:
    """# NEVERIFICAT: Piper local pe CPU (`AMA_PIPER_BIN`, modelele în `AMA_PIPER_MODELE`). Nu rulează în
    CI."""

    def sintetizeaza(
        self, text: str, profil: ProfilVoce, *, gresit: dict[str, str] | None = None
    ) -> audio.Wav:
        s = get_settings()
        binar = s.piper_bin or shutil.which("piper")
        if not binar:
            raise RuntimeError("Piper nu este instalat (AMA_PIPER_BIN)")
        model = Path(s.piper_modele) / f"{profil.model}.onnx"
        with tempfile.TemporaryDirectory() as d:
            iesire = Path(d) / "f.wav"
            subprocess.run(
                [binar, "--model", str(model), "--output_file", str(iesire)],
                input=text.encode(),
                check=True,
                capture_output=True,
                timeout=120,
            )
            return audio.citeste(iesire.read_bytes())


_motor_fortat: MotorVoce | None = None


def seteaza_motor(m: MotorVoce | None) -> None:
    """Pentru teste: un motor anume, indiferent de profil."""
    global _motor_fortat
    _motor_fortat = m


def motor_pentru(p: ProfilVoce) -> MotorVoce:
    if _motor_fortat is not None:
        return _motor_fortat
    return MotorPiper() if p.motor == "piper" else MotorVoceSimulat()


@dataclass
class Fraza:
    text: str
    inceput: float
    sfarsit: float


@dataclass
class Naratiune:
    activ: Activ
    fraze: list[Fraza]
    durata: float
    wav: audio.Wav = field(repr=False)


def compune(fraze_wav: list[audio.Wav], texte: list[str]) -> tuple[audio.Wav, list[Fraza]]:
    """Lipește frazele cu `PAUZA_FRAZE` între ele; cuvintele simulate primesc momentele în pista întreagă."""
    if not fraze_wav:
        raise ValueError("narațiune fără fraze")
    rata = fraze_wav[0].rata
    total = audio.liniste(rata, 0.0)
    cuvinte: list[dict[str, Any]] = []
    out: list[Fraza] = []
    for i, (w, t) in enumerate(zip(fraze_wav, texte, strict=True)):
        if w.rata != rata:
            raise ValueError("frazele au rate diferite")
        start = len(total) / rata
        total.extend(w.esantioane)
        for c in w.extra.get("cuvinte", []):
            cuvinte.append({**c, "s": round(c["s"] + start, 3), "e": round(c["e"] + start, 3), "f": i})
        out.append(Fraza(t, round(start, 3), round(len(total) / rata, 3)))
        if i < len(fraze_wav) - 1:
            total.extend(audio.liniste(rata, PAUZA_FRAZE))
    extra = {"cuvinte": cuvinte} if cuvinte else {}
    return audio.Wav(rata, total, extra), out


def licenta_activ(p: ProfilVoce) -> dict[str, Any]:
    d = asdict(p.licenta)
    d["baza_drepturi"] = d.pop("tip")
    return {**d, "tip": "voce_sintetizata", "profil": p.cod, "motor": p.motor, "model": p.model}


def sintetizeaza(
    db: Session,
    tenant_id: uuid.UUID,
    fraze: list[str],
    *,
    profil_cod: str | None = None,
    gresit: dict[str, str] | None = None,
    descriere: str = "narațiune",
) -> Naratiune:
    """Sintetizează frazele (deja normalizate) și salvează narațiunea în biblioteca de active, cu licența
    vocii."""
    p = profil(profil_cod)
    m = motor_pentru(p)
    texte = [f.strip() for f in fraze if f.strip()]
    bucati = [m.sintetizeaza(t, p, gresit=gresit) for t in texte]
    wav, fr = compune(bucati, texte)
    a = biblioteca.incarca(
        db,
        tenant_id,
        audio.scrie(wav),
        nume_original="naratiune.wav",
        sursa="voce_sintetizata",
        utilizator_id=None,
        descriere=descriere,
        licenta=licenta_activ(p),
        generare={"motor": p.motor, "model": p.model, "fraze": len(texte)},
    )
    return Naratiune(a, fr, round(wav.durata, 3), wav)


def durata_estimata(text: str) -> float:
    """Pentru planificare (motorul simulat): secundele unei fraze."""
    c = text.split()
    s = sum(silabe(x) for x in c)
    return round(s * MotorVoceSimulat.SILABA + max(0, len(c) - 1) * MotorVoceSimulat.INTRE_CUVINTE, 3)
