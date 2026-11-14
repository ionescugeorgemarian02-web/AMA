"""Formatul E, om real (F8.12, docs/14 §14.1): clientul se filmează citind scriptul (prompterul din
portal), iar
platforma taie pauzele, pune subtitrări și aduce sunetul la nivel. Fără etichetă AI pentru imagine și voce.

Pașii: sunetul filmării -> segmentele de vorbire (energie; pauzele de peste 0,5 s [I] se taie, cu 0,15 s de
aer
la capete) -> tăierea și lipirea imaginii și a sunetului, la 1080×1920 / 30 fps -> transcrierea pe textul
scriptului (aliniere forțată, simulat; whisper.cpp la migrare) -> lista de montaj E (o scenă: clipul tăiat;
vocea:
sunetul lui) -> montajul obișnuit (subtitrări, nivel, G6, pașaport).
"""

import tempfile
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.media import audio, biblioteca, ffmpeg, licente, lista, montaj, regizor, transcriere
from app.media.modele import Activ, Randare

PAUZA_TAIATA = 0.5  # [I]
AER = 0.15  # [I]


def segmente_vorbire(w: audio.Wav) -> list[tuple[float, float]]:
    """Intervalele păstrate: vorbirea, cu aer la capete; pauzele mai scurte de `PAUZA_TAIATA` rămân."""
    seg = audio.segmente(w, prag=0.01, pauza_min=PAUZA_TAIATA, durata_min=0.2)
    out: list[tuple[float, float]] = []
    for a, b in seg:
        a, b = max(0.0, a - AER), min(w.durata, b + AER)
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], b)
        else:
            out.append((a, b))
    return [(round(a, 3), round(b, 3)) for a, b in out]


def _extrage_sunet(sursa: Path, d: Path) -> audio.Wav:
    iesire = d / "brut.wav"
    ffmpeg.ruleaza(["-i", str(sursa), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(iesire)])
    return audio.citeste(iesire.read_bytes())


def _taie(sursa: Path, segmente: list[tuple[float, float]], d: Path) -> tuple[Path, Path]:
    filtre, eti = [], ""
    for i, (a, b) in enumerate(segmente):
        filtre.append(
            f"[0:v]trim={a:.3f}:{b:.3f},setpts=PTS-STARTPTS,scale=1080:1920:"
            f"force_original_aspect_ratio=increase,crop=1080:1920,fps=30,setsar=1[v{i}]"
        )
        filtre.append(f"[0:a]atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS,aresample=16000[a{i}]")
        eti += f"[v{i}][a{i}]"
    filtre.append(f"{eti}concat=n={len(segmente)}:v=1:a=1[v][a]")
    video, sunet = d / "taiat.mp4", d / "taiat.wav"
    ffmpeg.ruleaza(
        [
            "-i",
            str(sursa),
            "-filter_complex",
            ";".join(filtre),
            "-map",
            "[v]",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(video),
            "-map",
            "[a]",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(sunet),
        ],
        fir=4,
    )
    return video, sunet


def proceseaza(
    db: Session, tenant_id: uuid.UUID, brut: Activ, fraze: list[str], *, canal: str = "tiktok"
) -> Randare:
    """Filmarea brută -> clip publicabil (randare `gata` sau `respinsa`, cu controlul G6 și pașaportul)."""
    licente.foloseste(db, brut.id, scop="format_e")
    lic = {
        "tip": "material_client",
        "statut": licente.STATUT_OK,
        "declarat_de": (brut.licenta or {}).get("declarat_de", "client"),
        "conditii": f"derivat din filmarea clientului {brut.id}",
    }
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        w = _extrage_sunet(regizor.cale(brut), d)
        seg = segmente_vorbire(w)
        if not seg:
            raise regizor.ListaInvalida(["filmarea nu are vorbire"])
        video, sunet = _taie(regizor.cale(brut), seg, d)
        clip = biblioteca.incarca(
            db,
            tenant_id,
            video.read_bytes(),
            nume_original="format-e-taiat.mp4",
            sursa="format_e",
            utilizator_id=None,
            descriere="filmarea, fără pauze",
            licenta=lic,
        )
        wav = audio.citeste(sunet.read_bytes())
    voce = biblioteca.incarca(
        db,
        tenant_id,
        audio.scrie(wav),
        nume_original="format-e-voce.wav",
        sursa="format_e",
        utilizator_id=None,
        descriere="vocea reală a clientului",
        licenta=lic,
    )
    al = transcriere.aliniaza(fraze, transcriere.transcriptor().transcrie(wav, asteptat=" ".join(fraze)))
    durata_clip = ffmpeg.durata(regizor.cale(clip))
    durata = round(min(durata_clip, wav.durata), 3)
    lm = lista.ListaMontaj(
        format="E",
        canal=canal,
        durata=durata,
        voce=lista.Pista(activ_id=voce.id, durata=round(wav.durata, 3)),
        scene=[lista.Scena(activ_id=clip.id, inceput=0, sfarsit=durata, bataie=0)],
        texte=regizor.texte(fraze, al),
    )
    r = montaj.produ(db, tenant_id, lm)
    r.masuratori = {
        **(r.masuratori or {}),
        "brut_sec": round(w.durata, 2),
        "taiat_sec": durata,
        "segmente": len(seg),
    }
    db.flush()
    return r
