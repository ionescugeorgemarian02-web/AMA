"""F8.12 — formatul E, om real. „Gata când”: o filmare brută de un minut devine clip publicabil. Prompterul din
portal (HTTP), încărcarea, jobul pe culoarul greu, tăierea pauzelor, subtitrările, nivelul și G6 reale; filmarea și
vocea clientului SIMULATE (D-007); transcrierea prin aliniere forțată (whisper.cpp la migrare)."""

import tempfile
import time
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import productie, validare
from app.config import get_settings
from app.conturi import Rol
from app.db import sesiune_tenant
from app.media import control, ffmpeg, provenienta, subtitrari
from app.media.modele import Activ, Randare
from tests.integration.conftest import Cont, csrf_din, login
from tests.media_utile import SCRIPT_E, filmare_bruta

pytestmark = [pytest.mark.db, pytest.mark.skipif(not ffmpeg.disponibil(), reason="ffmpeg lipsește")]


def test_filmarea_bruta_de_un_minut_devine_clip_publicabil(
    client: TestClient, fabrica_conturi: Callable[..., Cont], executor: None
) -> None:
    cont = fabrica_conturi(Rol.CLIENT_TITULAR)
    t = cont.tenant_id
    assert t is not None
    with sesiune_tenant(t) as db:
        lid = productie.creeaza(db, tenant_id=t, tip="script_video_scurt", canal="instagram").id
        voci = [SCRIPT_E["hook"], *(b["voce"] for b in SCRIPT_E["batai"]), SCRIPT_E["cta"]]
        validare.continut.scrie(
            db, lid, text=" ".join(voci), campuri=SCRIPT_E, autor="E2", model_autor="fals"
        )
    assert login(client, cont.email, cont.parola).status_code == 303
    h = client.get(f"/portal/prompter/{lid}")
    assert h.status_code == 200 and SCRIPT_E["hook"] in h.text and "prompter-normal" in h.text
    assert "prompter-lent" in client.get(f"/portal/prompter/{lid}?viteza=lent").text
    with tempfile.TemporaryDirectory() as tmp:
        corp, durata_bruta = filmare_bruta(tmp, voci)
    assert durata_bruta >= 58
    r = client.post(f"/portal/prompter/{lid}", data={"csrf_token": csrf_din(h.text)},
                    files={"fisier": ("filmare.mp4", corp, "video/mp4")}, follow_redirects=False)  # fmt: skip
    assert r.status_code == 303 and r.headers["location"].endswith("mesaj=trimis")
    limita = time.monotonic() + 100
    while True:  # jobul pe culoarul greu: așteptăm randarea (gata sau respinsă)
        with sesiune_tenant(t) as db:
            stari = list(db.execute(select(Randare.stare).where(Randare.tenant_id == t)).scalars())
        if stari and stari[0] != "in_lucru":
            break
        assert time.monotonic() < limita, "formatul E nu s-a terminat"
        time.sleep(0.5)
    with sesiune_tenant(t) as db:
        [rd] = list(db.execute(select(Randare).where(Randare.tenant_id == t)).scalars())
        assert rd.stare == "gata", rd.control
        v = db.get(Activ, rd.activ_id)
        assert v is not None
        cale = Path(get_settings().media_dir) / v.cale
        # pauzele tăiate: clipul e mult mai scurt decât filmarea, vocea rămâne întreagă
        assert (
            rd.masuratori["brut_sec"] >= 58 and rd.masuratori["taiat_sec"] < rd.masuratori["brut_sec"] * 0.75
        )
        assert rd.masuratori["segmente"] >= len(voci)
        # publicabil: G6 trece (format, fără tăceri lungi, nivel, subtitrări în zona sigură)
        from app.media import lista

        lm = lista.ListaMontaj.model_validate(rd.lista)
        assert lm.format == "E" and len(lm.texte) == sum(len(x.split()) for x in voci)
        vd, _ = control.verdict(
            cale, control.Asteptari(canal=lm.canal, ecrane=tuple(subtitrari.grupeaza(lm)))
        )
        assert vd.rezultat == validare.Rezultat.TRECE, vd.dovezi
        # om real: pașaport fără etichetă AI
        p = provenienta.al_activului(db, v.id)
        assert p is not None and p.continut["ai"]["om_real"] is True
        assert all(not e["eticheta_ai"] for e in p.continut["etichete"].values())
