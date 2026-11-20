"""Regizorul (F8.5, docs/14 §14.5 pasul 4): de la scriptul pe bătăi și vocea verificată la lista de montaj.

Modelul (profilul `creatie`, prin gateway) alege doar cadrul și mișcarea pe fiecare bătaie, dintr-o listă
numerotată de active CU licență. Momentele le pune programul, din vocea reală: bătaia i ține de la primul
cuvânt
al frazei i până la primul cuvânt al frazei următoare (tăietura cade pe bătaie); prima începe la 0, ultima se
termină cu vocea plus o coadă scurtă. O alegere invalidă (bătaie lipsă, material inexistent) se înlocuiește
determinist, prin rotație, și se notează.
"""

import math
import uuid
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app import continut, gateway
from app.config import get_settings
from app.logging import get_logger
from app.media import audio, biblioteca, compozitor, ffmpeg, licente, lista, selectie, transcriere
from app.media.modele import Activ
from app.operare.motor import Prioritate

log = get_logger("app.media")
COADA = 0.6  # [I] secunde după ultimul cuvânt
SUBIECT_JOS = 2 / 3  # [I] un subiect care coboară în treimea de jos ar fi acoperit de subtitrările de jos
SUBIECT_SUS = 0.2  # [I] un subiect care urcă peste 20% din înălțime ar fi acoperit de subtitrările de sus


class AlegereScena(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bataie: int = Field(ge=0)
    material: int = Field(ge=0)
    miscare: Literal["static", "zoom_in", "zoom_out", "panoramare_stanga", "panoramare_dreapta"] = "static"


class PlanRegizor(gateway.Iesire):
    scene: list[AlegereScena] = Field(min_length=1, max_length=10)
    coperta: str = Field(default="", max_length=60)


def fraze_din_script(campuri: dict[str, Any]) -> list[str]:
    """Bătăile rostite, în ordine: hook, vocea bătăilor, apelul la acțiune (conținutul E2, F6.4)."""
    out = [str(campuri.get("hook", "")).strip()]
    out += [str(b.get("voce", "")).strip() for b in campuri.get("batai", [])]
    out.append(str(campuri.get("cta", "")).strip())
    return [f for f in out if f]


def cale(a: Activ) -> Path:
    return Path(get_settings().media_dir) / a.cale


def info_activ(a: Activ) -> lista.InfoActiv:
    durata: float | None = None
    if a.categorie == "audio":
        durata = audio.citeste(cale(a).read_bytes()).durata
    elif a.categorie == "video":
        durata = ffmpeg.durata(cale(a))
    return lista.InfoActiv(a.categorie, not licente.probleme(a.licenta), durata)


def info_active(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, lista.InfoActiv]:
    out = {}
    for i in ids:
        a = db.get(Activ, i)
        if a is not None:
            out[i] = info_activ(a)
    return out


def texte(fraze: list[str], al: transcriere.Aliniere) -> list[lista.Text]:
    """Cuvintele afișate (cu majusculele și punctuația lor), cu momentele din aliniere."""
    out: list[lista.Text] = []
    k = 0
    for fi, f in enumerate(fraze):
        for tok in f.split():
            n = len(transcriere.jetoane(tok))
            if not n:
                continue
            c0, c1 = al.cuvinte[k], al.cuvinte[k + n - 1]
            k += n
            sfarsit = max(c1.sfarsit, c0.inceput + 0.05)
            out.append(lista.Text(cuvant=tok[:40], inceput=c0.inceput, sfarsit=sfarsit, fraza=fi))
    return out


def momente_batai(fraze: list[str], al: transcriere.Aliniere, durata: float) -> list[tuple[float, float]]:
    inceputuri: list[float] = []
    k = 0
    for f in fraze:
        inceputuri.append(al.cuvinte[k].inceput if k < len(al.cuvinte) else durata)
        k += len(transcriere.jetoane(f))
    inceputuri[0] = 0.0
    return [(round(a, 3), round(b, 3)) for a, b in zip(inceputuri, [*inceputuri[1:], durata], strict=True)]


def _repara(plan: PlanRegizor, n_batai: int, n_mat: int) -> tuple[list[AlegereScena], list[str]]:
    note: list[str] = []
    pe_bataie = {s.bataie: s for s in plan.scene if s.bataie < n_batai}
    out: list[AlegereScena] = []
    for b in range(n_batai):
        s = pe_bataie.get(b)
        if s is None or s.material >= n_mat:
            note.append(f"bătaia {b}: alegere invalidă, înlocuită prin rotație")
            s = AlegereScena(bataie=b, material=b % n_mat, miscare="zoom_in")
        out.append(s)
    return out, note


def construieste(
    *,
    format: str,
    canal: str,
    fraze: list[str],
    naratiune: transcriere.NaratiuneVerificata,
    materiale: list[Activ],
    alegeri: list[AlegereScena],
    coperta: str = "",
    muzica: Activ | None = None,
    durate: dict[uuid.UUID, float] | None = None,
    stil: lista.StilSubtitrari | None = None,
) -> lista.ListaMontaj:
    """Nucleul determinist: alegerile + momentele vocii -> lista de montaj. `durate` (video): o bătaie
    mai lungă decât clipul ales se împarte în bucăți egale, pe clipurile următoare care o acoperă.
    Tăietura cade pe începutul replicii care cere cadrul (`momente_batai`); durata urmează vocea (+ coada),
    fără prelungire spre o durată-țintă."""
    durata = round(naratiune.naratiune.durata + COADA, 3)
    intervale = momente_batai(fraze, naratiune.aliniere, durata)
    scene = []
    for (a, b), s in zip(intervale, alegeri, strict=True):
        m = materiale[s.material]
        # formatul B e „imagini în mișcare”: o fotografie nu stă niciodată pe loc (altfel G6 o vede înghețată)
        miscare = (s.miscare if s.miscare != "static" else "zoom_in") if m.categorie == "foto" else "static"
        for activ, x, y in _bucati(m, a, b, materiale, durate or {}):
            scene.append(
                lista.Scena(activ_id=activ.id, inceput=x, sfarsit=y, miscare=miscare, bataie=s.bataie)
            )
    return lista.ListaMontaj(
        format=format,
        canal=canal,
        durata=durata,
        voce=lista.Pista(activ_id=naratiune.naratiune.activ.id, durata=naratiune.naratiune.durata),
        muzica=lista.Muzica(activ_id=muzica.id) if muzica is not None else None,
        scene=scene,
        texte=texte(fraze, naratiune.aliniere),
        stil=stil or lista.StilSubtitrari(),
        coperta=lista.Coperta(text=(coperta or fraze[0])[:60]),
    )


def reutilizari(lm: lista.ListaMontaj) -> dict[uuid.UUID, int]:
    """Câte bătăi în plus refolosesc aceeași sursă, pe `activ_id`. Alt zoom sau altă mișcare pe aceeași
    sursă rămâne reutilizare; bucățile aceleiași bătăi (un clip împărțit) nu contează."""
    batai: dict[uuid.UUID, set[int]] = {}
    for s in lm.scene:
        batai.setdefault(s.activ_id, set()).add(s.bataie)
    return {a: len(b) - 1 for a, b in batai.items() if len(b) > 1}


def _bucati(
    m: Activ, a: float, b: float, materiale: list[Activ], durate: dict[uuid.UUID, float]
) -> list[tuple[Activ, float, float]]:
    """Scena [a, b] pe clipul `m`; dacă clipul e mai scurt, n bucăți egale, fiecare pe un clip destul de lung
    (întâi `m`, apoi celelalte video, prin rotație)."""
    d = durate.get(m.id)
    if m.categorie != "video" or d is None or b - a <= d + lista.CADRU:
        return [(m, a, b)]
    n = math.ceil((b - a) / d)
    pas = (b - a) / n
    start = materiale.index(m)
    rotatie = [materiale[(start + k) % len(materiale)] for k in range(len(materiale))]
    potrivite = [x for x in rotatie if x.categorie == "video" and durate.get(x.id, 0.0) + lista.CADRU >= pas]
    if not potrivite:
        return [(m, a, b)]  # validarea listei o va respinge, cu motivul exact
    out = []
    for k in range(n):
        x = a + k * pas
        y = b if k == n - 1 else round(a + (k + 1) * pas, 3)
        out.append((potrivite[k % len(potrivite)], round(x, 3), y))
    return out


Zona = tuple[float, float, float, float]


def pozitie_subtitrari(
    zone: list[tuple[Zona | None, float]], *, pret_jos: bool = False
) -> Literal["jos", "sus"]:
    """Subtitrările urcă sus când prețul stă jos sau când subiectul (zona relativă) coboară în treimea de jos
    mai mult timp decât urcă în banda de sus. `zone`: (zona scenei, durata scenei). Nucleu pur."""
    if pret_jos:
        return "sus"
    jos = sum(d for z, d in zone if z is not None and z[3] > SUBIECT_JOS)
    sus = sum(d for z, d in zone if z is not None and z[1] < SUBIECT_SUS)
    return "sus" if jos > sus else "jos"


def stil_subtitrari(
    lm: lista.ListaMontaj, materiale: list[Activ], *, pret_jos: bool = False
) -> lista.StilSubtitrari:
    """Stilul listei, cu poziția aleasă din zonele subiectului pe durata scenelor."""
    zone = {m.id: compozitor.zona_relativa(m) for m in materiale}
    pe_scene = [(zone.get(s.activ_id), s.sfarsit - s.inceput) for s in lm.scene]
    return lm.stil.model_copy(update={"pozitie": pozitie_subtitrari(pe_scene, pret_jos=pret_jos)})


# --- storyboardul (F-editorial, decizia 3): din inventarul real, ÎNAINTE de voce și montaj ---

Natura = Literal["educativ", "prezentare"]


class ScenaStoryboard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scena: int = Field(ge=0)
    replica: str
    subiect: str
    activ_id: uuid.UUID | None = None
    scor: float = 0.0
    motiv: str
    sursa: Literal["activ", "ilustratie", "lipsa"]
    obligatorie: bool = True
    nota: str = ""


class Storyboard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    natura: Natura
    scene: list[ScenaStoryboard]
    # sigla clientului: DOAR semnătură finală opțională, niciodată scenă
    semnatura: uuid.UUID | None = None

    @property
    def blocat(self) -> bool:
        return any(s.sursa == "lipsa" for s in self.scene)

    def cereri(self) -> list[tuple[int, str, str]]:
        """(scena, subiect, cererea precisă) pentru scenele lipsă; întâi bătăile cu indicație proprie."""
        lipsa = [s for s in self.scene if s.sursa == "lipsa"]
        alese = [s for s in lipsa if s.obligatorie] or lipsa
        return [(s.scena, s.subiect, cerere_material(s.subiect)) for s in alese]


def cerere_material(subiect: str) -> str:
    return f"Încarcă o fotografie verticală cu {subiect}"


def scene_script(script: dict[str, Any]) -> list[selectie.CerereScena]:
    """Scenele, în ordinea frazelor (`fraze_din_script`): hook și apel fără indicație proprie, bătăile cu
    indicația lor vizuală (obligatorie dacă există). Cu `cadre` (conceptul ales, F-idee), bătaia j primește
    cadrul j (subiect + acțiune + context și interogările de stock) ca indicații în plus."""
    out = []
    if str(script.get("hook", "")).strip():
        out.append(selectie.CerereScena(str(script["hook"]).strip(), "", obligatorie=False))
    cadre = [c for c in script.get("cadre", []) if isinstance(c, dict) and c.get("tip") != "text"]
    for j, b in enumerate(x for x in script.get("batai", []) if str(x.get("voce", "")).strip()):
        voce, vizual = str(b.get("voce", "")).strip(), str(b.get("vizual", "")).strip()
        cadru = cadre[j] if j < len(cadre) else None
        alternative: tuple[str, ...] = ()
        if cadru is not None:
            descriere = " ".join(str(cadru.get(k, "")) for k in ("subiect", "actiune", "context")).strip()
            alternative = tuple(x for x in (descriere, *map(str, cadru.get("interogari", []))) if x.strip())
        out.append(
            selectie.CerereScena(
                voce,
                vizual,
                obligatorie=bool(vizual or alternative),
                alternative=alternative,
                video=bool(cadru and cadru.get("tip") == "video"),
            )
        )
    if str(script.get("cta", "")).strip():
        out.append(selectie.CerereScena(str(script["cta"]).strip(), "", obligatorie=False))
    return out


def candidati(active: list[Activ]) -> list[selectie.Candidat]:
    """Inventarul real al clientului. Clipurile animate generate automat nu sunt material al afacerii."""
    return [
        selectie.Candidat(
            id=a.id,
            rol=a.rol_vizual,
            categorie=a.categorie,
            subiect=a.subiect or "",
            descriere=a.descriere or "",
            licenta_ok=not licente.probleme(a.licenta),
        )
        for a in active
        if a.sursa != "animatie"
    ]


def compune_storyboard(
    script: dict[str, Any], active: list[Activ], *, natura: Natura = "prezentare"
) -> Storyboard:
    """Nucleul determinist al storyboardului (fără bază)."""
    cereri = scene_script(script)
    alegeri = selectie.alege(cereri, candidati(active))
    scene = []
    for c, a in zip(cereri, alegeri, strict=True):
        if a.activ_id is not None:
            sursa, nota = "activ", ""
        elif natura == "educativ":
            sursa = "ilustratie"
            nota = f"Nu avem material cu „{a.subiect}”: scena e o ilustrație animată, nu o imagine reală."
        else:
            sursa, nota = "lipsa", cerere_material(a.subiect)
        scene.append(
            ScenaStoryboard(scena=a.scena, replica=a.replica, subiect=a.subiect, activ_id=a.activ_id,
                            scor=a.scor, motiv=a.motiv, sursa=sursa, obligatorie=c.obligatorie, nota=nota)
        )  # fmt: skip
    sigla = next((a.id for a in active if a.rol_vizual == "logo" and not licente.probleme(a.licenta)), None)
    return Storyboard(natura=natura, scene=scene, semnatura=sigla)


def storyboard(db: Session, tenant_id: uuid.UUID, script: dict[str, Any], *, natura: Natura) -> Storyboard:
    """Storyboardul livrabilului din inventarul real al clientului (`biblioteca.ale_clientului`)."""
    return compune_storyboard(script, biblioteca.ale_clientului(db, tenant_id), natura=natura)


class ListaInvalida(ValueError):
    def __init__(self, probleme: list[str]) -> None:
        super().__init__("; ".join(probleme))
        self.probleme = probleme


def regizeaza(
    db: Session,
    tenant_id: uuid.UUID,
    *,
    fraze: list[str],
    naratiune: transcriere.NaratiuneVerificata,
    materiale: list[Activ],
    format: str = "A",
    canal: str = "tiktok",
    muzica: Activ | None = None,
    livrabil_id: uuid.UUID | None = None,
    script: dict[str, Any] | None = None,
    materiale_fixe: list[int] | None = None,
    pret_jos: bool = False,
) -> lista.ListaMontaj:
    """Cere alegerile modelului, construiește lista și o validează (`ListaInvalida` dacă nu trece).
    `materiale_fixe` (din storyboard): materialul fiecărei bătăi e deja ales; modelul dă doar mișcarea.
    `pret_jos`: prețul apare jos în cadru, deci subtitrările urcă sus."""
    folosibile = [m for m in materiale if not licente.probleme(m.licenta)]
    if not folosibile:
        raise ListaInvalida(["niciun material cu licență"])
    durate = {
        m.id: d for m in folosibile if (d := info_activ(m).durata) is not None and m.categorie == "video"
    }
    indicatii = [""] * len(fraze)
    if script:
        indicatii = (
            ([""] if script.get("hook") else [])
            + [str(b.get("vizual", "")) for b in script.get("batai", []) if str(b.get("voce", "")).strip()]
            + ([""] if script.get("cta") else [])
        )
        if len(indicatii) != len(fraze):
            raise ListaInvalida(["scenariul și narațiunea au număr diferit de bătăi"])
    continut.prompturi.asigura()
    r = gateway.apeleaza(
        db,
        prompt="media.regizor@1",
        schema=PlanRegizor,
        tenant_id=tenant_id,
        componenta="media.regizor",
        livrabil_id=livrabil_id,
        prioritate=Prioritate.P2,
        max_tokeni=800,
        variabile={
            "format": format,
            "batai": "\n".join(f"{i}. {f} {indicatii[i]}".strip() for i, f in enumerate(fraze)),
            "materiale": "\n".join(
                f"{i}: {m.descriere or m.nume_original}"
                + (f" ({durate[m.id]:.1f} s)" if m.id in durate else "")
                for i, m in enumerate(folosibile)
            ),
        },
    )
    if not isinstance(r.iesire, PlanRegizor):
        raise TypeError("ieșirea nu respectă schema promptului")
    alegeri, note = _repara(r.iesire, len(fraze), len(folosibile))
    if materiale_fixe is not None:
        if len(materiale_fixe) != len(fraze) or any(not 0 <= m < len(folosibile) for m in materiale_fixe):
            raise ListaInvalida(["storyboardul nu se potrivește cu bătăile sau cu materialele"])
        alegeri = [a.model_copy(update={"material": materiale_fixe[a.bataie]}) for a in alegeri]
    if note:
        log.warning("regizorul a primit alegeri invalide", extra={"note": note[:5]})
    lm = construieste(format=format, canal=canal, fraze=fraze, naratiune=naratiune, materiale=folosibile,
                      alegeri=alegeri, coperta=r.iesire.coperta, muzica=muzica, durate=durate)  # fmt: skip
    lm = lm.model_copy(update={"stil": stil_subtitrari(lm, folosibile, pret_jos=pret_jos)})
    ids = {s.activ_id for s in lm.scene} | {lm.voce.activ_id} | ({lm.muzica.activ_id} if lm.muzica else set())
    p = lista.probleme(lm, info_active(db, ids))
    if p:
        raise ListaInvalida(p)
    return lm
