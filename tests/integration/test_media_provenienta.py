"""F8.11 — proveniență și dezvăluire AI (G11). „Gata când”: fiecare fișier final are pașaport și etichetă stabilită.
FFmpeg real; vocea, stock-ul și generarea SIMULATE (D-007). Standardul de marcare (C2PA etc.): la migrare (F0.7)."""

# ruff: noqa: F811
import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from app import validare
from app.config import get_settings
from app.db import sesiune_tenant
from app.media import compozitor, ffmpeg, furnizori, montaj, provenienta, regizor, sabloane
from app.media.modele import Activ
from tests.integration.utile_productie import fabrica_clienti, tenant  # noqa: F401
from tests.media_utile import fraze, lista_simpla, naratiune

pytestmark = [pytest.mark.db, pytest.mark.skipif(not ffmpeg.disponibil(), reason="ffmpeg lipsește")]


def test_fiecare_fisier_final_are_pasaport_si_eticheta(tenant: uuid.UUID) -> None:
    with sesiune_tenant(tenant) as db:
        finale: list[Activ] = []
        # video din stock + voce sintetică
        r1 = montaj.produ(db, tenant, lista_simpla(db, tenant, "A"))
        # video din imagini GENERATE + voce sintetică
        gen = [
            furnizori.genereaza_imagine(db, tenant, f"boabe de cafea, variantă {i}", samanta=i)
            for i in range(3)
        ]
        nv = naratiune(db, tenant)
        alegeri = [
            regizor.AlegereScena(bataie=i, material=i % 3, miscare="zoom_in") for i in range(len(fraze()))
        ]
        lm = regizor.construieste(format="B", canal="instagram", fraze=fraze(), naratiune=nv, materiale=gen,
                                  alegeri=alegeri)  # fmt: skip
        r2 = montaj.produ(db, tenant, lm)
        # o copertă din șablon
        [cop] = [
            s for s in sabloane.asigura_sabloane(db, tenant, "Cafeneaua Zorilor") if s.tip == "coperta_video"
        ]
        a3, _ = compozitor.creeaza(db, tenant, cop, {"titlu": "Știi de ce cafeaua ta e amară?"})
        for r in (r1, r2):
            assert r.stare == "gata" and r.activ_id
            a = db.get(Activ, r.activ_id)
            assert a is not None
            finale.append(a)
        finale.append(a3)
        for a in finale:
            p = provenienta.al_activului(db, a.id)
            assert p is not None, a.sursa
            assert p.continut["sha256"] == a.sha256
            assert set(p.continut["etichete"]) == set(provenienta.CANALE)
            assert provenienta.verdict(db, a).rezultat == validare.Rezultat.TRECE
            lateral = Path(get_settings().media_dir) / str(tenant) / "pasapoarte" / f"{a.sha256}.json"
            assert json.loads(lateral.read_text())["activ_id"] == str(a.id)
        e1 = provenienta.al_activului(db, finale[0].id).continut  # type: ignore[union-attr]
        e2 = provenienta.al_activului(db, finale[1].id).continut  # type: ignore[union-attr]
        e3 = provenienta.al_activului(db, finale[2].id).continut  # type: ignore[union-attr]
        assert e1["ai"] == {"imagine_generata": False, "voce_sintetica": True, "om_real": False}
        assert (
            e1["etichete"]["tiktok"]["eticheta_ai"]
            and "Voce generată" in e1["etichete"]["tiktok"]["mentiune"]
        )
        assert e2["ai"]["imagine_generata"] and "Imagini generate" in e2["etichete"]["instagram"]["mentiune"]
        assert any(c.get("generare", {}).get("samanta") == 0 for c in e2["componente"])  # sămânța păstrată
        assert e3["etichete"]["facebook"]["eticheta_ai"] is False  # grafică din șablon, fără conținut generat
        assert e1["validari"]["G6"]["rezultat"] == "trece"
        # marcajul din fișier (lizibil de mașini)
        tags = ffmpeg.probe(Path(get_settings().media_dir) / finale[0].cale)["format"].get("tags", {})
        assert json.loads(tags["comment"])["ai"] == ["voce_sintetica"]
        # G11 respinge un fișier final fără pașaport
        fara = furnizori.genereaza_imagine(db, tenant, "fundal simplu", samanta=99)
        v = provenienta.verdict(db, fara)
        assert v.rezultat == validare.Rezultat.ESEC and "fără pașaport" in v.dovezi[0].detalii
        n = len(list(db.execute(select(Activ).where(Activ.sursa.in_(("montaj", "compozitor")))).scalars()))
        assert n == len(finale)


def test_eticheta_pe_canal_nucleu() -> None:
    real = provenienta.etichete({"imagine_generata": False, "voce_sintetica": False, "om_real": True})
    assert all(not e["eticheta_ai"] and e["motiv"].startswith("om real") for e in real.values())
    gen = provenienta.etichete({"imagine_generata": True, "voce_sintetica": False, "om_real": False})
    assert all(e["eticheta_ai"] and e["platforma"] for e in gen.values())
