"""F8.5 — lista de decizii de montaj și Regizorul. „Gata când”: un script produce o listă validă, cu durate care se
potrivesc cu vocea. Cascada de voce și transcriere SIMULATĂ, modelul FALS (# SIMULAT)."""

# ruff: noqa: F811
import os
import shutil
import uuid
from pathlib import Path

import pytest

from app.db import sesiune_tenant
from app.media import lista, regizor, transcriere
from app.media.modele import Activ
from tests.integration.utile_productie import fabrica_clienti, tenant  # noqa: F401
from tests.media_utile import fraze, materiale, model_regizor, naratiune
from tests.onboarding_utile import ModelFals, model_fals, modele  # noqa: F401

pytestmark = pytest.mark.db


def test_scriptul_produce_o_lista_valida_cu_durate_potrivite_cu_vocea(
    tenant: uuid.UUID, modele: ModelFals
) -> None:
    rf = model_regizor(modele)
    with sesiune_tenant(tenant) as db:
        mat = materiale(db, tenant, "video", 3)
        nv = naratiune(db, tenant)
        fr = fraze()
        lm = regizor.regizeaza(db, tenant, fraze=fr, naratiune=nv, materiale=mat, format="A")
        assert rf.cereri == 1
        ids = {s.activ_id for s in lm.scene} | {lm.voce.activ_id}
        assert lista.probleme(lm, regizor.info_active(db, ids)) == []
        # durata = vocea reală + coada; scenele acoperă tot, tăieturile cad pe începutul fiecărei bătăi
        assert lm.durata == pytest.approx(nv.naratiune.durata + regizor.COADA, abs=0.002)
        assert lm.voce.durata == pytest.approx(regizor.info_activ(nv.naratiune.activ).durata or 0, abs=0.002)
        assert (
            len(lm.scene) == len(fr) == 5 and lm.scene[0].inceput == 0 and lm.scene[-1].sfarsit == lm.durata
        )
        k = 0
        for i, f in enumerate(fr):
            if i:
                assert lm.scene[i].inceput == pytest.approx(nv.aliniere.cuvinte[k].inceput, abs=0.001)
            k += len(transcriere.jetoane(f))
        assert len(lm.texte) == k and all(t.sfarsit <= lm.durata for t in lm.texte)
        # datele se pot compara și re-randa identic
        assert lista.ListaMontaj.model_validate_json(lm.model_dump_json()) == lm


def test_alegerile_invalide_se_repara_iar_o_lista_stricata_e_respinsa(
    tenant: uuid.UUID, modele: ModelFals
) -> None:
    model_regizor(modele, strica=True)
    with sesiune_tenant(tenant) as db:
        mat = materiale(db, tenant, "video", 2)
        nv = naratiune(db, tenant)
        lm = regizor.regizeaza(db, tenant, fraze=fraze(), naratiune=nv, materiale=mat, format="A")
        assert [s.activ_id for s in lm.scene][:2] == [mat[0].id, mat[1].id]  # rotație deterministă
        ids = {s.activ_id for s in lm.scene} | {lm.voce.activ_id}
        info = regizor.info_active(db, ids)
        gaura = lm.model_copy(
            update={"scene": [lm.scene[0].model_copy(update={"sfarsit": 0.6}), *lm.scene[1:]]}
        )
        assert any("gol sau suprapunere" in p for p in lista.probleme(gaura, info))
        scurta = lm.model_copy(update={"durata": lm.durata + 3})
        assert any("nu se potrivește cu vocea" in p for p in lista.probleme(scurta, info))
        foto = lm.model_copy(update={"format": "B"})
        assert any("nu folosește video" in p for p in lista.probleme(foto, info))
        fara_lic = {**info, mat[0].id: lista.InfoActiv("video", False, 6.0)}
        assert any("licență" in p for p in lista.probleme(lm, fara_lic))


def test_reutilizarea_subtitrarile_sus_si_durata_dupa_voce(tenant: uuid.UUID) -> None:
    """F-editorial, decizia 6: aceeași sursă cu altă mișcare e reutilizare, raportată pe activ; subtitrările
    urcă sus când subiectul stă jos; durata urmează vocea (fără prelungire spre 30 s)."""
    from app.media import biblioteca, licente, montaj, subtitrari
    from tests.media_utile import fotografie_procedurala

    scurt = {"hook": "Lanțul scârțâie?", "batai": [{"voce": "Îl curățăm și îl ungem.", "vizual": "lanț uns"},
             {"voce": "Pinionul rămâne curat.", "vizual": "pinion curat"}], "cta": "Programează-te azi."}  # fmt: skip
    with sesiune_tenant(tenant) as db:
        jos, sus = (
            biblioteca.incarca(
                db,
                tenant,
                fotografie_procedurala(subiect=(0.5, y), samanta=k),
                nume_original=f"f{k}.jpg",
                sursa="portal",
                utilizator_id=None,
                rol_vizual="fotografie",
                subiect="lanț pe pinion",
                licenta={
                    "tip": "productie_proprie",
                    "statut": licente.STATUT_OK,
                    "componente": [{"descriere": "fotografie de test"}],
                },
                generare={"zona_subiect": [0.3, y - 0.15, 0.7, y + 0.15]},
            )
            for k, y in ((1, 0.75), (2, 0.3))
        )
        nv, fr = naratiune(db, tenant, scurt), fraze(scurt)
        miscari = ["zoom_in", "zoom_out", "panoramare_stanga", "zoom_in"]
        alegeri = [regizor.AlegereScena(bataie=i, material=(1 if i == 1 else 0), miscare=m)  # type: ignore[arg-type]
                   for i, m in enumerate(miscari)]  # fmt: skip
        lm = regizor.construieste(format="B", canal="tiktok", fraze=fr, naratiune=nv, materiale=[jos, sus],
                                  alegeri=alegeri)  # fmt: skip
        lm = lm.model_copy(update={"stil": regizor.stil_subtitrari(lm, [jos, sus])})
        assert regizor.reutilizari(lm) == {jos.id: 2}  # alt zoom, aceeași sursă: tot reutilizare
        assert lm.stil.pozitie == "sus"  # subiectul stă jos cea mai mare parte a clipului
        zona_sus, zona_jos = (0.3, 0.15, 0.7, 0.45), (0.3, 0.6, 0.7, 0.9)
        assert regizor.pozitie_subtitrari([(zona_sus, 3.0), (zona_jos, 1.0)]) == "jos"
        assert regizor.pozitie_subtitrari([(None, 2.0)], pret_jos=True) == "sus"
        ecrane = subtitrari.grupeaza(lm)
        z = subtitrari.zona("tiktok")
        assert ecrane and all(
            e.cutie[1] == z.sus and subtitrari.in_zona(e, "tiktok", 1080, 1920) for e in ecrane
        )
        assert "Sub,DejaVu Sans" in subtitrari.ass(lm, ecrane) and ",8,60,150,160,1" in subtitrari.ass(
            lm, ecrane
        )
        assert lm.durata == pytest.approx(nv.naratiune.durata + regizor.COADA, abs=0.002) and lm.durata < 30
        r = montaj.pregateste(db, tenant, lm)
        assert r.masuratori["reutilizari"] == {str(jos.id): 2}
        r = montaj.executa(db, r)  # randarea reală: G6 trece cu subtitrările sus
        assert r.stare == "gata", r.control
        if dosar := os.environ.get("AMA_MOSTRE_MACHETE"):
            shutil.copyfile(regizor.cale(db.get(Activ, r.activ_id)), Path(dosar) / "clip_subtitrari_sus.mp4")
