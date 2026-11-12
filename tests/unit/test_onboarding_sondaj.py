"""F4.10 — nucleele pure: eșantionul determinist al sondajului și trimiterile brieful de insight."""

import uuid

from app.onboarding import piata, sondaj


def trimiteri(n: int) -> list[str]:
    return [f"afirmatie:{uuid.UUID(int=k + 1)}" for k in range(n)]


def test_esantionul_este_determinist_nu_depinde_de_ordine_si_are_marimea_ceruta() -> None:
    t = trimiteri(40)
    a = sondaj.esantion(t, samanta="s1")
    assert (
        a == sondaj.esantion(list(reversed(t)), samanta="s1") == sondaj.esantion(t + t[:5], samanta="s1")
    )  # aceeași intrare
    assert len(a) == 12 and set(a) <= set(t)  # ⌈30% din 40⌉
    assert sondaj.esantion(t, samanta="s2") != a  # altă sămânță, alt eșantion
    assert len(sondaj.esantion(trimiteri(10), samanta="s")) == 5  # minim 5
    assert sondaj.esantion(trimiteri(3), samanta="s") == sorted(trimiteri(3))  # puține trimiteri: toate
    assert sondaj.esantion([], samanta="s") == []
    assert len(sondaj.esantion(t, samanta="s", fractie=1.0)) == 40


def test_toate_trimiterile_apar_in_esantion_cand_fractia_este_1() -> None:
    t = trimiteri(17)
    assert sondaj.esantion(t, samanta="x", fractie=1.0, minim=1) == sorted(t)


def brief(surse: list[list[str]]) -> dict[str, object]:
    def e(s: list[str]) -> dict[str, object]:
        return {"text": "O afirmație oarecare despre piață.", "surse": s}

    return {"tip": "brief_insight", "rezumat": e(surse[0]), "harta": [e(s) for s in surse[1:-2]],
            "spatii_libere": [e(surse[-2])], "recomandari": [e(surse[-1])]}  # fmt: skip


def test_afirmatiile_fara_trimitere_sau_cu_trimitere_malformata_sunt_gasite() -> None:
    bun = f"afirmatie:{uuid.uuid4()}"
    assert piata.fara_trimitere(brief([[bun]] * 6)) == []
    probleme = piata.fara_trimitere(
        brief([[bun], [], [bun], ["pasaj:nu-e-uuid"], [bun], ["altceva:" + str(uuid.uuid4())], [bun]])
    )
    assert len(probleme) == 3 and "fără trimitere" in probleme[0] and "formă nepermisă" in probleme[1]
    assert piata.toate_trimiterile(brief([[bun]] * 6)) == [bun]
    assert len(piata.enunturi(brief([[bun]] * 6))) == 6
    assert (
        piata.trimitere_valida(f"pasaj:{uuid.uuid4()}")
        and not piata.trimitere_valida("pasaj:")
        and not piata.trimitere_valida("x")
    )
