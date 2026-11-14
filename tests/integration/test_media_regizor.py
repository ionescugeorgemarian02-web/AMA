"""F8.5 — lista de decizii de montaj și Regizorul. „Gata când”: un script produce o listă validă, cu durate care se
potrivesc cu vocea. Cascada de voce și transcriere SIMULATĂ, modelul FALS (# SIMULAT)."""

# ruff: noqa: F811
import uuid

import pytest

from app.db import sesiune_tenant
from app.media import lista, regizor, transcriere
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
