"""F13.3 — verificarea planului media: structură, plafoane, criterii de oprire, măsurare."""

from app.reclame.plan import CampaniePlan, CriteriiOprire, Masurare, PlanMedia, link_cu_utm, slug, verifica


def plan(**kw: object) -> PlanMedia:
    baza: dict[str, object] = {
        "obiectiv": "lead", "pagina_destinatie": "https://agentie.example/audit", "buget_lunar_bani": 240_000,
        "campanii": [
            CampaniePlan(nume="A · scalare", rol="scalare", buget_zilnic_bani=6_400, public="IMM-uri"),
            CampaniePlan(nume="A · test", rol="test", buget_zilnic_bani=1_600, public="IMM-uri", variabila="hook",
                         variante=["preț", "timp", "dovadă"]),
        ],
        "plafon_zilnic_bani": 10_000, "plafon_lunar_bani": 300_000, "plafon_campanie_bani": 8_000,
        "criterii_oprire": CriteriiOprire(cost_tinta_bani=4_000), "masurare": Masurare(utm_source="meta", utm_campaign="audit"),
    }  # fmt: skip
    return PlanMedia.model_validate(baza | kw)


def test_planul_bun_trece_si_cel_peste_plafoane_nu() -> None:
    assert verifica(plan()) == []
    p = verifica(plan(plafon_campanie_bani=5_000, plafon_zilnic_bani=7_000, pagina_destinatie="http://x.ro"))
    assert any("plafonul pe campanie" in x for x in p) and any("plafonul zilnic" in x for x in p)
    assert any("https" in x for x in p)
    assert any("plafonul lunar" in x for x in verifica(plan(buget_lunar_bani=100_000)))


def test_structura_si_criteriile() -> None:
    fara_scalare = plan(campanii=[CampaniePlan(nume="Test", rol="test", buget_zilnic_bani=100, public="IMM",
                                                variabila="hook", variante=["a"])])  # fmt: skip
    p = verifica(fara_scalare)
    assert any("scalare" in x for x in p) and any("o singură variabilă" in x for x in p)
    p = verifica(plan(criterii_oprire=CriteriiOprire(cost_tinta_bani=100_000)))
    assert any("oprirea n-ar veni niciodată" in x for x in p)


def test_utm_si_slug() -> None:
    assert slug("Audit gratuit – Iași!") == "audit-gratuit-iasi"
    assert link_cu_utm(plan(), "Preț corect") == (
        "https://agentie.example/audit?utm_source=meta&utm_medium=cpc&utm_campaign=audit&utm_content=pret-corect"
    )
