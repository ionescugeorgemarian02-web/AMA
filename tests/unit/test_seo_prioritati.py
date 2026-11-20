from io import StringIO

import pytest

from app import seo


def test_exportul_pastreaza_pagina_si_produsul_si_prioritizeaza_dupa_date() -> None:
    export = StringIO(
        "Query,Product,Page,Impressions,Position\n"
        "Cafea boabe,Guji,/guji,10,3\n"
        "Etiopia boabe,Guji,/guji,20,6\n"
        "Etiopia boabe,Guji,/guji,30,8\n"
        "Cafea boabe,Guji,/cadou,60,4\n"
        "Cafea boabe,Huila,/cadou,30,2\n"
    )
    grupuri = seo.cuvinte.din_csv(export)
    assert [(g.produs, g.pagina, g.impresii) for g in grupuri] == [
        ("Guji", "/cadou", 60),
        ("Guji", "/guji", 60),
        ("Huila", "/cadou", 30),
    ]
    b = seo.articole.brief(grupuri[1], [])
    assert (b["produs"], b["pagina"], b["principal"], b["secundare"]) == (
        "Guji",
        "/guji",
        "Etiopia boabe",
        ["Cafea boabe"],
    )
    assert b["impresii"] == 60 and b["pozitie"] == pytest.approx(6.5)


def test_export_gsc_filtrat_pe_pagina_si_date_lipsa() -> None:
    csv = "\ufeffInterogări populare;Afișări;Poziție\nCafea;90;7,2\n"
    with pytest.raises(ValueError, match="pagina"):
        seo.cuvinte.din_csv(StringIO(csv), produs="Guji")
    g = seo.cuvinte.din_csv(StringIO(csv), produs="Guji", pagina="/guji")[0]
    assert (g.impresii, g.pozitie, g.pagina) == (90, 7.2, "/guji")

    [manual] = seo.cuvinte.din_csv(StringIO("query,product,page\nCafea,Guji,/guji\n"))
    assert manual.impresii is None and manual.pozitie is None


@pytest.mark.parametrize("valoare", ["-1,2", "2,nan", "a,2", "8,", ","])
def test_respinge_metrici_invalide(valoare: str) -> None:
    with pytest.raises(ValueError, match="rândul 2"):
        seo.cuvinte.din_csv(StringIO(f"query,product,page,impressions,position\ncafea,G,/g,{valoare}\n"))
