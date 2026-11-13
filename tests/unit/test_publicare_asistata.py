"""F6.6 — nucleele publicării asistate: linkul lipit și pachetul; butonul de partajare din scriptul aplicației."""

import datetime as dt
import uuid
from pathlib import Path
from types import SimpleNamespace

from app import validare
from app.publicare import asistata


def test_linkul_trebuie_sa_fie_https_pe_domeniul_canalului_si_sa_duca_la_postare() -> None:
    assert asistata.link_valid("facebook", "https://www.facebook.com/zorilor/posts/123") is None
    assert asistata.link_valid("facebook", "https://fb.watch/abc") is None
    assert asistata.link_valid("instagram", "https://www.instagram.com/p/Cx1/") is None
    assert "https://" in (asistata.link_valid("facebook", "http://facebook.com/x/1") or "")
    assert "nu este pe facebook" in (asistata.link_valid("facebook", "https://facebook.com.rau.test/x") or "")
    assert "nu este pe linkedin" in (asistata.link_valid("linkedin", "https://www.facebook.com/x/1") or "")
    assert "prima pagină" in (asistata.link_valid("tiktok", "https://www.tiktok.com/") or "")
    assert asistata.link_valid("facebook", "nu e link") is not None


def test_pachetul_are_textul_final_ora_eticheta_ai_si_pasii() -> None:
    lv = SimpleNamespace(
        canal="facebook",
        tip="postare",
        termen_la=dt.datetime(2026, 12, 1, 16, tzinfo=dt.UTC),
        id=uuid.uuid4(),
    )
    c = validare.Continut(versiune=2, text="Știi ce înseamnă?\n\nComandă acum.", campuri={"hashtaguri": ["cafea", "#Brasov"]},
                          model_autor="furnizor/model")  # fmt: skip
    p = asistata.pachet_din(c, lv)  # type: ignore[arg-type]
    assert p["text"].endswith("\n\n#cafea #Brasov") and p["ora_recomandata"] == "2026-12-01T16:00:00+00:00"
    assert p["dezvaluire_ai"] is True and any("AI" in x for x in p["pasi_obligatorii"])
    assert asistata.pachet_din(validare.Continut(versiune=1, text="Om."), lv)["dezvaluire_ai"] is False  # type: ignore[arg-type]


def test_scriptul_aplicatiei_partajeaza_cu_web_share_si_copiaza_altfel() -> None:
    js = (Path(__file__).resolve().parents[2] / "app/web/static/js/app.js").read_text(encoding="utf-8")
    assert "[data-partajeaza]" in js and "navigator.share(" in js and "navigator.clipboard.writeText" in js
