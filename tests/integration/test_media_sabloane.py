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


def test_machetele_editoriale_aleg_dupa_brief_si_active_si_nu_reintra_in_scene(
    fabrica_clienti: Callable[[], uuid.UUID],
) -> None:
    """F-editorial, decizia 5: fără fotografie, macheta tipografică cu notă; cu fotografie, foto_dominanta
    sau detaliu_explicat; caruselul are N cadre. Toate ies cu `rol_vizual='coperta'`."""
    from app.media import biblioteca, licente, regizor
    from tests.media_utile import fotografie_procedurala

    t = fabrica_clienti()
    brief = {"ce_vede_publicul": "mecanicul cu bicicleta în atelier", "natura": "prezentare"}
    with sesiune_tenant(t) as db:
        fara = compozitor.exporta(db, t, "Atelierul Spița", brief, {"titlu": "Revizie de primăvară"})
        assert fara.macheta == "anunt" and "Nu avem o fotografie" in fara.nota
        assert fara.active[0].rol_vizual == "coperta" and fara.active[0].generare["nota"] == fara.nota
        foto = biblioteca.incarca(
            db, t, fotografie_procedurala(), nume_original="atelier.jpg", sursa="portal", utilizator_id=None,
            rol_vizual="fotografie", subiect="mecanicul cu bicicleta în atelier",
            licenta={"tip": "productie_proprie", "statut": licente.STATUT_OK,
                     "componente": [{"descriere": "fotografie de test, procedurală"}]},
            generare={"zona_subiect": [0.4, 0.45, 0.7, 0.8], "punct_piesa": [0.55, 0.62]},
        )  # fmt: skip
        dom = compozitor.exporta(db, t, "Atelierul Spița", brief, {"titlu": "Revizie de primăvară"})
        assert dom.macheta == "foto_dominanta" and len(dom.active) == 1
        a = dom.active[0]
        assert (
            a.rol_vizual == "coperta" and a.generare["zona_subiect"] and a.generare["pozitie_titlu"] == "sus"
        )
        assert {c["activ_id"] for c in a.licenta["componente"]} >= {str(foto.id)}
        det = compozitor.exporta(db, t, "Atelierul Spița", {**brief, "ce_vede_publicul": "pinionul în prim-plan"},
                                 {"titlu": "Pinionul uzat"})  # fmt: skip
        assert det.macheta == "detaliu_explicat" and det.active[0].generare["pozitie_titlu"] != "banda"
        car = compozitor.exporta(db, t, "Atelierul Spița", {**brief, "format": "carusel"},
                                 {"intrebare": "De ce scârțâie frâna?", "idei": ["Plăcuțe uzate", "Disc murdar"],
                                  "pas": "Programează revizia"})  # fmt: skip
        assert car.macheta == "carusel" and len(car.imagini) == 4
        assert all(x.rol_vizual == "coperta" for x in car.active)
        # exporturile nu reintră în scene (decizia 2)
        cand = {c.id for c in regizor.candidati(biblioteca.ale_clientului(db, t))}
        from app.media import selectie

        eligibili = {c.id for c in selectie.eligibili(regizor.candidati(biblioteca.ale_clientului(db, t)))}
        assert cand and eligibili == {foto.id}
