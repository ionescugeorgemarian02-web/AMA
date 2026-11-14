"""F8.10 — șabloane grafice și Compozitorul. „Gata când”: fiecare brand propriu are șase șabloane și textul apare cu
diacritice corecte. Randatorul de referință (Pillow) e real; HTML/Chromium: la migrare."""

# ruff: noqa: F811
import io
import uuid
from collections.abc import Callable

import pytest
from PIL import Image

from app import creier, validare
from app.db import sesiune_tenant
from app.media import compozitor, furnizori, sabloane, vizual
from tests.integration.utile_productie import fabrica_clienti  # noqa: F401

pytestmark = pytest.mark.db
BRANDURI_PROPRII = ("AMA Agenția Autonomă", "CariereAI", "BigBrain")  # brandurile proprii (D-007, F6.8)
TEXTE = {
    "citat": {"titlu": "Şi cea mai bună cafea începe cu o întrebare simplă", "semnatura": "Echipa, Brașov"},
    "oferta": {"titlu": "Abonamentul lunar, livrat acasă", "pret": "89 lei pe lună", "corp": "Oprești oricând."},
    "sfat": {"eticheta": "Sfat", "titlu": "Păstrează boabele departe de lumină", "corp": "Într-un borcan opac, la "
             "temperatura camerei, nu în frigider: așa își țin aroma două săptămâni."},
    "rezultat": {"cifra": "12 kg", "titlu": "pe lot, prăjite în fiecare marți", "corp": "Loturi mici, gust stabil."},
    "anunt": {"eticheta": "Noutate", "titlu": "Degustări gratuite în prima sâmbătă", "corp": "Înscrie-te pe site."},
    "coperta_video": {"titlu": "Știi de ce cafeaua ta e amară?"},
}  # fmt: skip


def test_fiecare_brand_propriu_are_sase_sabloane_cu_diacritice_corecte(
    fabrica_clienti: Callable[[], uuid.UUID],
) -> None:
    assert all(sabloane.are_glif(c) for c in sabloane.DIACRITICE)
    assert not sabloane.are_glif("")  # verificarea chiar deosebește o glifă lipsă
    for nume in BRANDURI_PROPRII:
        t = fabrica_clienti()
        with sesiune_tenant(t) as db:
            sab = sabloane.asigura_sabloane(db, t, nume)
            assert sorted(s.tip for s in sab) == sorted(sabloane.TIPURI) and len(sab) == 6
            # identitatea lipsea: e propusă în Creier și așteaptă aprobarea clientului
            intr = creier.gaseste_intrare(db, tenant_id=t, compartiment=creier.Compartiment.IDENTITATE_VIZUALA,
                                          cheie=sabloane.CHEIE)  # fmt: skip
            assert intr is not None and creier.versiune_aprobata(db, intr.id) is None
            ident = sab[0].definitie["identitate"]
            assert (
                vizual.contrast(vizual.rgb(ident["culori"]["text"]), vizual.rgb(ident["culori"]["fundal"]))
                >= 7
            )
            assert sabloane.asigura_sabloane(db, t, nume)[0].id == sab[0].id  # a doua cerere nu dublează
            foto = furnizori.genereaza_imagine(db, t, "boabe de cafea pe lemn, lumină caldă", samanta=3)
            for s in sab:
                a, c = compozitor.creeaza(db, t, s, TEXTE[s.tip], foto=foto if s.tip in ("oferta", "coperta_video")
                                          else None)  # fmt: skip
                v = vizual.verdict(c.png, c.asteptari)
                assert v.rezultat == validare.Rezultat.TRECE, (
                    nume,
                    s.tip,
                    vizual.probleme(c.png, c.asteptari),
                )
                assert a.licenta is not None and a.licenta["tip"] == "productie_proprie"
                texte = a.generare["texte"] if a.generare else {}
                assert texte == TEXTE[s.tip]
                img = Image.open(io.BytesIO(c.png))
                assert img.size == (s.definitie["latime"], s.definitie["inaltime"])
        # sedila e scrisă cu virgulă în imagine: compoziția cu „Şi” e identică cu cea cu „Și”
        with sesiune_tenant(t) as db:
            [citat] = [s for s in sabloane.asigura_sabloane(db, t, nume) if s.tip == "citat"]
            cu_sedila = compozitor.compune(citat, {"titlu": "Şi ţara"}).png
            cu_virgula = compozitor.compune(citat, {"titlu": "Și țara"}).png
            assert cu_sedila == cu_virgula


def test_textul_prea_lung_nu_iese_din_cutie(fabrica_clienti: Callable[[], uuid.UUID]) -> None:
    t = fabrica_clienti()
    with sesiune_tenant(t) as db:
        [anunt] = [s for s in sabloane.asigura_sabloane(db, t, "Cafeneaua Zorilor") if s.tip == "anunt"]
        with pytest.raises(compozitor.TextPreaLung):
            compozitor.compune(anunt, {"titlu": "cuvânt " * 200})
