"""F8.6 — montajul pentru formatele A și B. „Gata când”: un video vertical complet iese dintr-o listă, fără
intervenție. FFmpeg real; vocea, stock-ul și fotografiile SIMULATE (D-007)."""

# ruff: noqa: F811
import uuid
from pathlib import Path

import pytest

from app.config import get_settings
from app.db import sesiune_tenant
from app.media import ffmpeg, licente, montaj
from app.media.modele import Activ
from tests.integration.utile_productie import fabrica_clienti, tenant  # noqa: F401
from tests.media_utile import lista_simpla

pytestmark = [pytest.mark.db, pytest.mark.skipif(not ffmpeg.disponibil(), reason="ffmpeg lipsește")]


@pytest.mark.parametrize("fmt", ["A", "B"])
def test_un_video_vertical_complet_iese_din_lista(tenant: uuid.UUID, fmt: str) -> None:
    with sesiune_tenant(tenant) as db:
        lm = lista_simpla(db, tenant, fmt)
        r = montaj.produ(db, tenant, lm)
        assert r.stare == "gata" and r.activ_id is not None
        v = db.get(Activ, r.activ_id)
        assert v is not None and (v.categorie, v.sursa, v.mime) == ("video", "montaj", "video/mp4")
        cale = Path(get_settings().media_dir) / v.cale
        info = ffmpeg.probe(cale)
        [vid] = [s for s in info["streams"] if s["codec_type"] == "video"]
        [aud] = [s for s in info["streams"] if s["codec_type"] == "audio"]
        assert (vid["codec_name"], vid["width"], vid["height"], vid["avg_frame_rate"], vid["pix_fmt"]) == (
            "h264", 1080, 1920, "30/1", "yuv420p")  # fmt: skip
        assert aud["codec_name"] == "aac"
        assert float(info["format"]["duration"]) == pytest.approx(lm.durata, abs=0.1)
        # licența videoului: producție proprie, cu fiecare componentă și licența ei; folosirile consemnate
        assert v.licenta is not None and v.licenta["tip"] == "productie_proprie"
        comp = {c["activ_id"]: c for c in v.licenta["componente"]}
        assert str(lm.voce.activ_id) in comp and all(str(s.activ_id) in comp for s in lm.scene)
        assert all(len(licente.folosiri(db, s.activ_id)) >= 1 for s in lm.scene)
        assert r.masuratori["secunde"] > 0 and r.masuratori["memorie_mb"] > 0
