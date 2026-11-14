"""F8.3 — nucleele pure: WER, alinierea cu cuvinte lipsă / în plus, alinierea forțată pe segmente."""

from app.media import audio, transcriere
from app.media.transcriere import CuvantTimp


def test_wer() -> None:
    assert transcriere.wer(["a", "b", "c"], ["a", "b", "c"]) == 0
    assert transcriere.wer(["a", "b", "c", "d"], ["a", "x", "c", "d"]) == 0.25


def test_alinierea_da_moment_si_cuvintelor_nerostite() -> None:
    auzite = [CuvantTimp("cafea", 0.0, 0.4), CuvantTimp("bună", 0.5, 0.9)]
    al = transcriere.aliniaza(["Cafea foarte bună."], auzite)
    assert [(c.cuvant, c.inceput) for c in al.cuvinte] == [("cafea", 0.0), ("foarte", 0.4), ("bună", 0.5)]
    assert al.semnalate == [0]


def test_alinierea_fortata_pe_semnal_fara_cuvinte() -> None:
    w = audio.Wav(16000, audio.ton(16000, 0.5, 150))
    w.esantioane.extend(audio.liniste(16000, 0.3))
    w.esantioane.extend(audio.ton(16000, 0.5, 150))
    cuv = transcriere.TranscriptorSimulat().transcrie(w, asteptat="unu doi")
    assert [c.cuvant for c in cuv] == ["unu", "doi"]
    assert cuv[0].inceput < 0.02 and abs(cuv[1].inceput - 0.8) < 0.02
