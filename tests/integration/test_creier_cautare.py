"""F4.3 — vectori și căutare hibridă pe Postgres real (pgvector, tsvector, pg_trgm), cu serverul de vectori FALS.

„Gata când”: o întrebare de probă găsește pasajul corect din materialele clientului. Aici: materialele brandului fictiv
„Cafeneaua Zorilor”, 27 de întrebări în română, fiecare cu pasajul așteptat; vectorii vin de la un vectorizator fals
(sac de cuvinte cu hashing, `# SIMULAT`), deci calitatea măsurată e a MECANISMULUI (fuziunea, filtrele, diacriticele),
nu a modelului real de vectori (rămâne „de verificat la migrare”)."""

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text

from app import cercetare, gateway
from app.cercetare import html_text
from app.creier import cautare as cauta_mod
from app.creier import indexare
from app.db import sesiune_tenant
from app.operare import motor
from tests import materiale_zorilor as mz
from tests.furnizor_fals import FurnizorFals
from tests.gateway_utile import CeasControlat, FabricaModele
from tests.integration.utile_productie import tenant as tenant
from tests.vectorizator_fals import vector_bow

pytestmark = pytest.mark.db
LOCAL = "http://{cod}:8080/v1"
PARAMETRI_MICI = indexare.Parametri(
    tinta=420, maxim=700, suprapunere=60
)  # ~un paragraf pe pasaj, ca evaluarea să conteze


@pytest.fixture(autouse=True)
def _mediu(cheie_proba: str, ceas_controlat: object, fals: FurnizorFals) -> Iterator[None]:
    fals.dim_vectori = 384
    fals.vectorizator = vector_bow
    yield


class Model:
    def __init__(self, f: FabricaModele, admin: Engine, ident: str = "e5-mic") -> None:
        self.cod_furnizor = f"loc{uuid.uuid4().hex[:8]}"
        self.fid = f.furnizor(
            tip_api="local", cod=self.cod_furnizor, url_baza=LOCAL.format(cod=self.cod_furnizor)
        )
        m = f.model(self.fid, identificator=ident, nivel="local", capabilitati=["embeddings"])
        self.cod = m.cod
        self.model_id = m.model_id
        self.admin = admin
        with admin.begin() as c:
            c.execute(
                text("UPDATE gateway_modele SET dimensiune_vector = 384 WHERE id = :i"), {"i": m.model_id}
            )

    def opreste(self) -> None:
        with self.admin.begin() as c:
            c.execute(text("UPDATE gateway_furnizori SET stare = 'inactiv' WHERE id = :i"), {"i": self.fid})


@pytest.fixture
def model(fabrica_modele: FabricaModele, admin_engine: Engine) -> Model:
    return Model(fabrica_modele, admin_engine)


def sursa_manuala(tenant: uuid.UUID, pagini: dict[str, tuple[str, list[str]]] | None = None) -> uuid.UUID:
    """O sursă manuală cu paginile brandului fictiv, textul extras ca de colector din HTML."""
    with sesiune_tenant(tenant) as db:
        sid = cercetare.creeaza_sursa(
            db, tenant_id=tenant, tip="manual", statut_cod="material_client", nume="Zorilor"
        ).id
        for cale in pagini or mz.PAGINI:
            pag = html_text.extrage(mz.html_pagina(cale))
            cercetare.adauga_text(db, tenant_id=tenant, sursa_id=sid, titlu=pag.titlu, text=pag.text)
    return sid


def indexeaza(tenant: uuid.UUID, sid: uuid.UUID, parametri: indexare.Parametri = PARAMETRI_MICI) -> int:
    with sesiune_tenant(tenant) as db:
        n = indexare.pregateste_sursa(db, sid, parametri=parametri)
    while indexare.vectorizeaza_lot(tenant, sid):
        pass
    return n


def raspunde(tenant: uuid.UUID, intrebare: str, **kw: object):  # type: ignore[no-untyped-def]
    with sesiune_tenant(tenant) as db:
        return cauta_mod.cauta(db, tenant_id=tenant, intrebare=intrebare, **kw)  # type: ignore[arg-type]


# --- „Gata când”


def test_intrebarile_de_proba_gasesc_pasajul_corect(tenant: uuid.UUID, model: Model) -> None:
    sid = sursa_manuala(tenant)
    n = indexeaza(tenant, sid)
    assert n >= len(mz.PAGINI) * 2
    gresite: list[str] = []
    ranguri = {"hibrid": 0, "vector": 0, "text": 0, "trigrame": 0}
    for intrebare, cale, cuvant in mz.INTREBARI:
        r = raspunde(tenant, intrebare, limita=3)
        corect = [
            i
            for i, x in enumerate(r.rezultate)
            if cuvant in x.text and x.titlu.startswith(mz.PAGINI[cale][0])
        ]
        if not corect:
            gresite.append(intrebare)
            continue
        ranguri["hibrid"] += corect[0] == 0
        for canal in ("vector", "text", "trigrame"):
            ranguri[canal] += r.rezultate[corect[0]].ranguri.get(canal, 99) == 1 and corect[0] == 0
    assert not gresite, gresite  # fiecare întrebare: pasajul corect e printre primele 3
    assert len(mz.INTREBARI) >= 20
    assert ranguri["hibrid"] >= 0.75 * len(mz.INTREBARI), (
        ranguri
    )  # și pe primul loc, în cel puțin 75% din cazuri


def test_fuziunea_nu_e_mai_slaba_decat_cel_mai_bun_canal_luat_singur(tenant: uuid.UUID, model: Model) -> None:
    sid = sursa_manuala(tenant)
    indexeaza(tenant, sid)
    scor = {"hibrid": 0, "doar_text": 0}
    for intrebare, _cale, cuvant in mz.INTREBARI:
        for nume, kw in (("hibrid", {}), ("doar_text", {"doar_text": True})):
            r = raspunde(tenant, intrebare, limita=1, **kw)
            scor[nume] += bool(r.rezultate) and cuvant in r.rezultate[0].text
    assert scor["hibrid"] >= scor["doar_text"], scor


def test_pasajul_pastreaza_legatura_cu_documentul_sursa_url_si_pozitia(
    tenant: uuid.UUID, model: Model
) -> None:
    sid = sursa_manuala(tenant)
    indexeaza(tenant, sid)
    [r, *_] = raspunde(tenant, "Cât costă un kilogram de cafea Guatemala?", limita=1).rezultate
    with sesiune_tenant(tenant) as db:
        d = cercetare.document(db, r.document_id)
        assert r.sursa_id == sid and r.titlu == d.titlu and r.url is None  # material manual: fără URL
        assert d.text[r.car_inceput : r.car_sfarsit] == r.text  # feliat exact din document
        assert "138 lei" in r.text and r.pozitie >= 0 and r.scor > 0 and r.ranguri


def test_diacriticele_nu_conteaza_la_cautarea_de_text(tenant: uuid.UUID, model: Model) -> None:
    sid = sursa_manuala(tenant)
    indexeaza(tenant, sid)
    variante = (
        "Care este programul sâmbăta?",
        "Care este programul sambata?",
        "Care ESTE programul şambăta?",
    )
    primele = [raspunde(tenant, v, limita=1, doar_text=True).rezultate[0].pasaj_id for v in variante]
    assert len(set(primele)) == 1
    asemanatoare = ("Cat costa transportul pentru comanda mica", "Cât costă transportul pentru comandă mică")
    assert {
        raspunde(tenant, v, limita=1, doar_text=True).rezultate[0].pasaj_id for v in asemanatoare
    } != set()
    [a, b] = [raspunde(tenant, v, limita=1, doar_text=True).rezultate[0].pasaj_id for v in asemanatoare]
    assert a == b
    # forma cu sedilă (ş, ţ) din materialele unui client se găsește cu forma corectă (ș, ț) și invers
    with sesiune_tenant(tenant) as db:
        s2 = cercetare.creeaza_sursa(
            db, tenant_id=tenant, tip="manual", statut_cod="material_client", nume="S"
        ).id
        cercetare.adauga_text(
            db,
            tenant_id=tenant,
            sursa_id=s2,
            titlu="Ofertă",
            text="Oferim reducere pentru ţinuta de seară şi pentru încălţăminte.",
        )
    indexeaza(tenant, s2)
    r = raspunde(tenant, "reducere ținută seară încălțăminte", sursa_id=s2, limita=1, doar_text=True)
    assert r.rezultate and "ţinuta" in r.rezultate[0].text


def test_filtrare_pe_sursa_si_pe_compartiment(tenant: uuid.UUID, model: Model) -> None:
    s1 = sursa_manuala(tenant, {"/produse": mz.PAGINI["/produse"]})
    s2 = sursa_manuala(tenant, {"/livrare": mz.PAGINI["/livrare"]})
    indexeaza(tenant, s1)
    indexeaza(tenant, s2)
    q = "Cât costă livrarea și cafeaua?"
    assert {x.sursa_id for x in raspunde(tenant, q, limita=20).rezultate} == {s1, s2}
    assert {x.sursa_id for x in raspunde(tenant, q, limita=20, sursa_id=s2).rezultate} == {s2}
    assert raspunde(tenant, q, compartiment="playbook").rezultate == []  # niciun pasaj cu acest compartiment
    with sesiune_tenant(tenant) as db:
        db.execute(text("UPDATE pasaje SET compartiment = 'playbook' WHERE sursa_id = :s"), {"s": s1})
    assert {x.sursa_id for x in raspunde(tenant, q, limita=20, compartiment="playbook").rezultate} == {s1}


def test_reindexare_la_schimbarea_modelului_de_vectori(
    tenant: uuid.UUID, model: Model, fabrica_modele: FabricaModele, admin_engine: Engine
) -> None:
    sid = sursa_manuala(tenant, {p: mz.PAGINI[p] for p in ("/produse", "/livrare", "/contact")})
    indexeaza(tenant, sid)
    with sesiune_tenant(tenant) as db:
        s = indexare.stare(db, tenant, sid)
        assert s.de_vectorizat == 0 and s.vectorizate == s.pasaje > 0 and s.model_activ == model.cod
        assert indexare.numara_de_vectorizat(db, tenant) == 0
    # modelul se schimbă (același număr de dimensiuni, alt model): vechiul se oprește, apare altul
    model.opreste()
    nou = Model(fabrica_modele, admin_engine, ident="e5-mare")
    with sesiune_tenant(tenant) as db:
        s = indexare.stare(db, tenant, sid)
        assert s.model_activ == nou.cod and s.vectorizate == 0 and s.de_vectorizat == s.pasaje
        assert s.modele_in_pasaje == {model.cod: s.pasaje}
        assert indexare.surse_de_vectorizat(db, tenant) == [sid]
    # până la reindexare căutarea merge pe text (vectorii vechi nu se amestecă cu cei ai modelului nou)
    r = raspunde(tenant, "Cât costă cafeaua Guatemala?", limita=2)
    assert r.rezultate and "vector" not in r.rezultate[0].ranguri and r.degradat
    while indexare.vectorizeaza_lot(tenant, sid):
        pass
    with sesiune_tenant(tenant) as db:
        s = indexare.stare(db, tenant, sid)
        assert s.de_vectorizat == 0 and s.modele_in_pasaje == {nou.cod: s.pasaje}
    r = raspunde(tenant, "Cât costă cafeaua Guatemala?", limita=2)
    assert "vector" in r.rezultate[0].ranguri and not r.degradat and r.model_vectori == nou.cod


def test_fara_model_de_vectori_cautarea_continua_pe_text_si_spune_ca_e_degradata(
    tenant: uuid.UUID, model: Model
) -> None:
    sid = sursa_manuala(tenant, {"/contact": mz.PAGINI["/contact"]})
    indexeaza(tenant, sid)
    model.opreste()
    r = raspunde(tenant, "La ce telefon pot da o comandă?", limita=1)
    assert (
        r.degradat
        and r.rezultate
        and "0268 555 0100" in r.rezultate[0].text
        and r.motiv.startswith("fără vectori")
    )


def test_un_document_schimbat_isi_inlocuieste_pasajele_si_cele_nemodificate_raman(
    tenant: uuid.UUID, model: Model
) -> None:
    sid = sursa_manuala(tenant, {"/produse": mz.PAGINI["/produse"], "/contact": mz.PAGINI["/contact"]})
    indexeaza(tenant, sid)
    with sesiune_tenant(tenant) as db:
        ids_inainte = {
            r[0] for r in db.execute(text("SELECT id FROM pasaje WHERE sursa_id = :s"), {"s": sid})
        }
        docs = cercetare.documente(db, sid)
        produse = next(d for d in docs if d.titlu.startswith("Cafea"))
        produse.text = "Etiopia Guji costă acum 52 lei. " + produse.text
        produse.hash_text = "b" * 64  # ca și cum re-colectarea ar fi adus alt conținut
        db.flush()
    assert indexeaza(tenant, sid) > 0
    with sesiune_tenant(tenant) as db:
        ids_dupa = {r[0] for r in db.execute(text("SELECT id FROM pasaje WHERE sursa_id = :s"), {"s": sid})}
        contact = next(d for d in cercetare.documente(db, sid) if d.titlu.startswith("Contact"))
        pasaje_contact = {
            r[0] for r in db.execute(text("SELECT id FROM pasaje WHERE document_id = :d"), {"d": contact.id})
        }
    assert (
        pasaje_contact <= ids_inainte and pasaje_contact <= ids_dupa
    )  # documentul nemodificat nu a fost atins
    assert len(ids_dupa - ids_inainte) > 0 and not (
        ids_inainte - ids_dupa
    ) - {  # pasajele vechi ale celui schimbat au dispărut
        i for i in ids_inainte if i not in pasaje_contact
    }
    r = raspunde(tenant, "Cât costă acum Etiopia Guji?", limita=1)
    assert "52 lei" in r.rezultate[0].text


def test_coloana_de_vectori_are_dimensiunea_din_registru(tenant: uuid.UUID, model: Model) -> None:
    with sesiune_tenant(tenant) as db:
        assert indexare.dimensiune_coloana(db) == 384 == gateway.dimensiune_vectori(tenant)
    m = gateway.model_vectori(tenant)
    assert m is not None and m.cod == model.cod and m.dimensiune == 384


# --- ca flux durabil


def test_fluxul_de_indexare_vectorizeaza_in_loturi_si_se_reprogrameaza_la_amanat(
    tenant: uuid.UUID,
    model: Model,
    fals: FurnizorFals,
    executor: None,
    motor_curat: None,
    admin_engine: Engine,
    ceas_controlat: CeasControlat,
) -> None:
    from app.creier import fluxuri

    sid = sursa_manuala(tenant)
    # 1. serverul de vectori cade: fluxul NU eșuează, se reprogramează
    fals.scenariu(model.cod_furnizor, permanent="5xx")
    job = fluxuri.trimite(tenant, sid, cheie=f"indexare:test:{sid}")
    stare = motor.asteapta_flux(job, timeout_sec=30)
    assert stare.stare is motor.StareJob.TERMINAT and motor.stare_flux(job) is not None
    with sesiune_tenant(tenant) as db:
        s = indexare.stare(db, tenant, sid)
        assert s.pasaje > 0 and s.vectorizate == 0  # pasajele sunt tăiate, vectorii lipsesc
    with (
        admin_engine.connect() as c
    ):  # reprogramarea: un job nou, cu cheia derivată din momentul amânării, în viitor
        reluari = c.execute(
            text("SELECT workflow_uuid, status FROM dbos.workflow_status WHERE workflow_uuid LIKE :k"),
            {"k": f"indexare:{sid}:reluare:%"},
        ).all()
    assert len(reluari) == 1 and reluari[0][1] in ("DELAYED", "ENQUEUED")
    # 2. serverul revine: o nouă indexare termină munca, fără să refacă pasajele
    fals.scenariu(model.cod_furnizor)
    ceas_controlat.avanseaza(3600)  # întrerupătorul furnizorului se închide
    with sesiune_tenant(tenant) as db:
        ids = {r[0] for r in db.execute(text("SELECT id FROM pasaje WHERE sursa_id = :s"), {"s": sid})}
    job2 = fluxuri.trimite(tenant, sid, cheie=f"indexare:test2:{sid}")
    assert motor.asteapta_flux(job2, timeout_sec=30).stare is motor.StareJob.TERMINAT
    with sesiune_tenant(tenant) as db:
        s = indexare.stare(db, tenant, sid)
        assert s.de_vectorizat == 0 and s.vectorizate == s.pasaje
        assert {
            r[0] for r in db.execute(text("SELECT id FROM pasaje WHERE sursa_id = :s"), {"s": sid})
        } == ids
    cereri = [c for c in fals.cereri_la(f"{model.cod_furnizor}") if c.cale.endswith("/embeddings")]
    assert all(len(c.corp["input"]) <= indexare.LOT_VECTORI for c in cereri)  # în loturi


def test_dupa_o_colectare_terminata_porneste_indexarea_sursei(
    tenant: uuid.UUID, model: Model, executor: None, motor_curat: None
) -> None:
    from app.creier import fluxuri

    sid = sursa_manuala(tenant, {"/contact": mz.PAGINI["/contact"]})
    fluxuri.activeaza_indexarea_dupa_colectare()
    try:
        from app.cercetare import colectare as c

        cid = uuid.uuid4()
        for cb in list(c._dupa_colectare):
            cb(tenant, sid, cid)
        stare = motor.asteapta_flux(f"indexare:{cid}", timeout_sec=30)
        assert stare.stare is motor.StareJob.TERMINAT
        with sesiune_tenant(tenant) as db:
            assert indexare.stare(db, tenant, sid).de_vectorizat == 0
    finally:
        from app.cercetare import colectare as c

        c._dupa_colectare.remove(fluxuri._dupa_colectare)
