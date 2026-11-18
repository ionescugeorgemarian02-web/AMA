"""F16.5 — generatorul video extern. „Gata când”: oprit fără buget; pornit, un insert de 3–6 s se generează cu
costul rezervat înainte de apel și cu licența `generat` + eticheta AI; peste plafonul lunar cererea e refuzată fără
apel; un apel eșuat nu consumă bugetul; furnizorul fără drept comercial e refuzat. Furnizorul e SIMULAT (D-026)."""

# ruff: noqa: F811
import uuid
from collections.abc import Iterator

import pytest

from app.config import get_settings
from app.db import sesiune_tenant
from app.media import ffmpeg, furnizori, provenienta, regizor, video_extern
from tests.integration.utile_productie import fabrica_clienti, tenant  # noqa: F401

pytestmark = [pytest.mark.db, pytest.mark.skipif(not ffmpeg.disponibil(), reason="ffmpeg lipsește")]
PROMPT = "aburi care se ridică dintr-o ceașcă de cafea, lumină caldă de dimineață"


class Numarator(video_extern.GeneratorVideoSimulat):
    def __init__(self, esueaza: bool = False) -> None:
        self.apeluri, self.esueaza = 0, esueaza

    def genereaza(self, prompt: str, **kw: object) -> bytes:  # type: ignore[override]
        self.apeluri += 1
        if self.esueaza:
            raise TimeoutError("furnizorul nu a răspuns")
        return super().genereaza(prompt, **kw)  # type: ignore[arg-type]


@pytest.fixture
def setari(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("AMA_VIDEO_EXTERN_ACTIV", "true")
    monkeypatch.setenv("AMA_VIDEO_EXTERN_PLAFON_LUNAR_BANI", "500")  # 10 secunde la 50 de bani
    get_settings.cache_clear()
    yield
    video_extern.seteaza(None)
    get_settings.cache_clear()


def test_oprit_fara_buget(tenant: uuid.UUID) -> None:
    with sesiune_tenant(tenant) as db, pytest.raises(video_extern.GeneratorOprit):
        video_extern.genereaza_insert(db, tenant, PROMPT)


def test_insert_cu_buget_si_plafon(tenant: uuid.UUID, setari: None) -> None:
    g = Numarator()
    video_extern.seteaza(g)
    with sesiune_tenant(tenant) as db:
        with pytest.raises(video_extern.GenerareRefuzata):
            video_extern.genereaza_insert(db, tenant, PROMPT, durata=8)
        with pytest.raises(furnizori.PromptRefuzat):
            video_extern.genereaza_insert(db, tenant, "un logo Nike cu text mare")
        r, a = video_extern.genereaza_insert(db, tenant, PROMPT, durata=6)
        assert r.stare == "gata" and r.cost_bani == 300 and a is not None and a.categorie == "video"
        assert a.licenta is not None and a.licenta["tip"] == "generat" and a.licenta["eticheta_ai"] is True
        assert 5.5 <= ffmpeg.durata(regizor.cale(a)) <= 6.5
        assert provenienta.ai_din([{"licenta": a.licenta}])["imagine_generata"]
        r2, a2 = video_extern.genereaza_insert(db, tenant, PROMPT + " de iarnă", durata=5)
        assert (r2.stare, a2, g.apeluri) == ("refuzat", None, 1), "300 + 250 > 500: refuz fără apel"
        r3, _ = video_extern.genereaza_insert(db, tenant, PROMPT + " de iarnă", durata=4)
        assert r3.stare == "gata" and video_extern.cheltuit_luna(db, tenant, r3.la) == 500


def test_apelul_esuat_nu_consuma_bugetul(tenant: uuid.UUID, setari: None) -> None:
    video_extern.seteaza(Numarator(esueaza=True))
    with sesiune_tenant(tenant) as db:
        r, a = video_extern.genereaza_insert(db, tenant, PROMPT, durata=6)
        assert (r.stare, a) == ("esuat", None) and "TimeoutError" in r.motiv
        assert video_extern.cheltuit_luna(db, tenant, r.la) == 0


def test_furnizorul_fara_drept_comercial_e_refuzat(tenant: uuid.UUID, setari: None) -> None:
    class CuFiligran(video_extern.GeneratorVideoSimulat):
        conditii = video_extern.ConditiiFurnizor(True, True, "nivel gratuit, cu filigran")

    video_extern.seteaza(CuFiligran())
    with sesiune_tenant(tenant) as db, pytest.raises(video_extern.GenerareRefuzata):
        video_extern.genereaza_insert(db, tenant, PROMPT)
