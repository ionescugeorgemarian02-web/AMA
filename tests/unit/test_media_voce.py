"""F8.1 — nucleele pure ale vocii: WAV, compunerea frazelor cu pauze, determinismul motorului simulat, profilurile."""

from app.media import audio, voce


def test_wav_dus_intors_cu_bucata_de_cuvinte() -> None:
    w = audio.Wav(16000, audio.ton(16000, 0.2, 150), {"cuvinte": [{"w": "ăîșț", "s": 0, "e": 0.2}]})
    w2 = audio.citeste(audio.scrie(w))
    assert w2.rata == 16000 and list(w2.esantioane) == list(w.esantioane) and w2.extra == w.extra


def test_motorul_simulat_este_determinist_si_frazele_au_pauze() -> None:
    p = voce.profil()
    m = voce.MotorVoceSimulat()
    a, b = m.sintetizeaza("Cafea proaspătă azi.", p), m.sintetizeaza("Cafea proaspătă azi.", p)
    assert audio.scrie(a) == audio.scrie(b)
    total, fraze = voce.compune([a, b], ["x", "y"])
    assert round(fraze[1].inceput - fraze[0].sfarsit, 3) == voce.PAUZA_FRAZE
    assert 0.15 <= voce.PAUZA_FRAZE <= 0.3
    assert total.durata == fraze[1].sfarsit
    assert voce.durata_estimata("Cafea proaspătă azi.") == round(a.durata, 3)


def test_profilurile_au_licenta_cu_statut_cunoscut() -> None:
    for p in voce.PROFILURI.values():
        assert p.licenta.statut in voce.STATUTE and p.limba == "ro-RO"
    assert voce.PROFILURI["ro-piper-pornire"].licenta.statut == "de_verificat"
    assert not voce.permite_publicarea(None) and not voce.permite_publicarea({"statut": "de_verificat"})
