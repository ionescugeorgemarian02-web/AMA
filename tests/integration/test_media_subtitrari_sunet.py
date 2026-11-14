"""F8.7 — subtitrări și sunet. „Gata când”: subtitrările sunt sincronizate și nivelul sonor este în țintă. FFmpeg
și libass reale; vocea, muzica și stock-ul SIMULATE (D-007)."""

# ruff: noqa: F811
import tempfile
import uuid
from pathlib import Path

import pytest

from app.config import get_settings
from app.db import sesiune_tenant
from app.media import ffmpeg, furnizori, montaj, subtitrari, sunet
from app.media.modele import Activ
from tests.integration.utile_productie import fabrica_clienti, tenant  # noqa: F401
from tests.media_utile import lista_simpla

pytestmark = [pytest.mark.db, pytest.mark.skipif(not ffmpeg.disponibil(), reason="ffmpeg lipsește")]


def test_subtitrarile_sunt_sincronizate_si_nivelul_sonor_in_tinta(tenant: uuid.UUID) -> None:
    with sesiune_tenant(tenant) as db:
        muzica = furnizori.aduce_muzica(db, tenant, "calm", 12.0)
        lm = lista_simpla(db, tenant, "A", muzica=muzica)
        r = montaj.produ(db, tenant, lm)
        assert r.stare == "gata"
        v = db.get(Activ, r.activ_id)
        assert v is not None
        cale = Path(get_settings().media_dir) / v.cale
        # subtitrări: 2–4 cuvinte pe ecran, în ordine, fiecare cuvânt evidențiat exact la momentul lui
        ecrane = subtitrari.grupeaza(lm)
        assert all(1 <= len(e.cuvinte) <= subtitrari.MAX_CUVINTE for e in ecrane)
        assert sum(len(e.cuvinte) >= subtitrari.MIN_CUVINTE for e in ecrane) >= len(ecrane) - 1
        assert [c for e in ecrane for c in e.cuvinte] == lm.texte
        assert all(subtitrari.in_zona(e, lm.canal, lm.latime, lm.inaltime) for e in ecrane)
        text_ass = subtitrari.ass(lm, ecrane)
        dialoguri = [x for x in text_ass.splitlines() if x.startswith("Dialogue:")]
        assert len(dialoguri) == len(lm.texte)
        for d, t in zip(dialoguri[1:], lm.texte[1:], strict=True):
            start = d.split(",")[1]
            h, m, s = start.split(":")
            moment = int(h) * 3600 + int(m) * 60 + float(s)
            assert moment == pytest.approx(t.inceput, abs=0.011) or moment <= t.inceput  # începutul ecranului
        assert any("ș" in x or "ț" in x for x in dialoguri)  # diacriticele ajung în fișier
        assert r.masuratori["subtitrari_srt"].startswith("1\n")
        # subtitrările sunt arse: zona lor diferă de cadrul fără subtitrări
        with tempfile.TemporaryDirectory() as tmp:
            e = ecrane[1]
            t = (e.inceput + e.sfarsit) / 2
            cadru = Path(tmp) / "c.png"
            ffmpeg.ruleaza(["-ss", f"{t:.2f}", "-i", str(cale), "-frames:v", "1", str(cadru)])
            from PIL import Image

            img = Image.open(cadru).convert("L").crop(e.cutie)
            assert max(img.tobytes()) > 230  # textul alb apare în cutia calculată
        # nivelul sonor: −14 LUFS ± 1, vârf sub −1 dBTP; muzica e atenuată sub voce
        n = sunet.masoara(cale)
        assert n.in_tinta, n
        assert r.masuratori["lufs"] == pytest.approx(n.lufs, abs=0.6)
        sub_voce = sunet.masoara(cale, de_la=lm.texte[2].inceput, pana_la=lm.texte[6].sfarsit)
        coada = sunet.masoara(cale, de_la=lm.texte[-1].sfarsit + 0.15, pana_la=lm.durata)
        assert coada.lufs < sub_voce.lufs - 6  # în coadă se aude doar muzica, mult sub voce


def test_fara_muzica_este_o_varianta_valida(tenant: uuid.UUID) -> None:
    with sesiune_tenant(tenant) as db:
        r = montaj.produ(db, tenant, lista_simpla(db, tenant, "B"))
        v = db.get(Activ, r.activ_id)
        assert v is not None and sunet.masoara(Path(get_settings().media_dir) / v.cale).in_tinta
