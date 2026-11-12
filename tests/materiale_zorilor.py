"""Materiale de probă: brandul FICTIV „Cafeneaua Zorilor” (prăjitorie de cafea de specialitate, Brașov). Nicio persoană,
adresă sau număr real: telefonul și emailul sunt inventate. Folosit de testele colectorului (site-ul fals), ale
căutării hibride (întrebări cu pasajul așteptat) și ale registrului de fapte.

Fiecare pagină: cale -> (titlu, paragrafe). Un paragraf este un pasaj logic; întrebările din `INTREBARI` indică
un cuvânt-cheie care apare doar în pasajul așteptat (verificat de test)."""

import html

PAGINI: dict[str, tuple[str, list[str]]] = {
    "/despre": (
        "Despre Cafeneaua Zorilor",
        [
            "Cafeneaua Zorilor este o prăjitorie de cafea de specialitate din Brașov, înființată în 2014 de doi prieteni "
            "care voiau o cafea mai bună decât cea din supermarket. Prăjim în loturi mici, de maximum 12 kilograme, "
            "pentru ca fiecare pachet să ajungă la client în cel mult zece zile de la prăjire.",
            "Boabele vin direct de la cooperative și ferme mici din Etiopia, Columbia și Guatemala. Plătim fermierilor "
            "un preț cu 20% mai mare decât cel de pe bursă și publicăm pe site fișa fiecărui lot: altitudinea, "
            "procesarea și data recoltei.",
            "Echipa are opt oameni: doi prăjitori certificați, un barista campion național la filtru în 2021, doi "
            "colegi la livrări și trei la cafenea. Credem că o cafea bună se explică ușor, fără termeni complicați, "
            "și de aceea organizăm degustări gratuite în prima sâmbătă a fiecărei luni.",
            "Nu folosim arome artificiale și nu amestecăm boabele vechi cu cele proaspete. Dacă o cafea nu ți-a plăcut, "
            "ne scrii și o schimbăm, fără formalități.",
        ],
    ),
    "/produse": (
        "Cafea de specialitate",
        [
            "Etiopia Guji, natural, 250 g: 49 lei. Note de afine, miere și iasomie. Potrivită pentru filtru și "
            "V60, nu o recomandăm la espresso cu lapte. Lotul de toamnă a fost recoltat în octombrie.",
            "Columbia Huila, spălată, 250 g: 42 lei. Note de caramel, nuci și ciocolată cu lapte. Este cafeaua "
            "noastră cea mai vândută pentru espresso și pentru aparate automate de cafea.",
            "Guatemala Antigua, spălată, 1 kg: 138 lei. Note de cacao, portocală coaptă și tutun dulce. Se vinde și "
            "în pachete de 250 g la 41 lei, iar prețul pe kilogram scade cu 12% la pachetul mare.",
            "Amestecul Zorilor, 1 kg, 119 lei: 60% Columbia, 30% Guatemala, 10% Etiopia. Este amestecul casei, "
            "gândit pentru cafenele și birouri, cu o extracție stabilă la espresso.",
            "Cafeaua decofeinizată Sugarcane, 250 g, 47 lei: decofeinizată cu acetat de etil din trestie de zahăr, "
            "fără solvenți chimici. Are note de vanilie și biscuiți.",
        ],
    ),
    "/abonamente": (
        "Abonamente de cafea",
        [
            "Abonamentul Lunar costă 89 lei pe lună și include două pachete de 250 g alese de noi, în funcție de "
            "preferințele tale. Livrarea este inclusă în preț, iar abonamentul se poate opri oricând, cu un mesaj "
            "trimis cu cel puțin trei zile înainte de următoarea prăjire.",
            "Abonamentul Birou costă 310 lei pe lună și include 3 kilograme de amestec Zorilor, un set de filtre "
            "curate și o vizită trimestrială a unui barista care reglează râșnița. Se facturează lunar, cu factură "
            "fiscală pe firmă.",
            "Primul abonament vine cu o reducere de 15% la prima comandă, valabilă până la 31 decembrie 2026. "
            "Reducerea nu se cumulează cu alte promoții și nu se aplică abonamentului Birou.",
        ],
    ),
    "/livrare": (
        "Livrare și retur",
        [
            "Livrăm în toată România prin curier, în 24 până la 48 de ore de la prăjire. Costul livrării este de "
            "15 lei pentru comenzile sub 150 lei și gratuit peste această sumă. În Brașov livrăm cu bicicleta, "
            "în aceeași zi, pentru comenzile primite până la ora 12:00.",
            "Cafeaua se prăjește marți și vineri. Comenzile plasate după ora 14:00 în aceste zile pleacă la următoarea "
            "prăjire. Nu expediem în weekend, ca pachetele să nu stea în depozitul curierului.",
            "Poți returna un pachet nedeschis în 14 zile de la primire, conform legii. Pentru pachetele deschise nu "
            "putem accepta retur din motive de siguranță alimentară, dar îl schimbăm dacă gustul nu ți s-a potrivit.",
            "Plata se face cu cardul, online, sau ramburs la curier, cu un comision de 6 lei. Acceptăm și plata prin "
            "transfer bancar pentru comenzile firmelor, cu factură proformă.",
        ],
    ),
    "/contact": (
        "Contact și program",
        [
            "Cafenea și prăjitorie: strada Lungă nr. 14, Brașov. Program: luni–vineri 07:30–19:00, sâmbătă "
            "09:00–17:00, duminică închis. În zilele de sărbătoare legală cafeneaua este închisă.",
            "Telefon comenzi: 0700 000 000, de luni până vineri între 09:00 și 17:00. Email: "
            "comenzi@cafeneaua-zorilor.example. Răspundem la mesaje în maximum o zi lucrătoare.",
            "Parcare: în fața cafenelei există patru locuri cu plată. Cel mai apropiat acces cu transport public "
            "este stația Livada, la două minute pe jos.",
        ],
    ),
    "/workshopuri": (
        "Degustări și workshopuri",
        [
            "Degustarea gratuită din prima sâmbătă a lunii începe la ora 11:00 și durează aproximativ 45 de minute. "
            "Se fac înscrieri la cafenea sau prin email; avem 12 locuri pe sesiune, deci rezervarea este recomandată.",
            "Workshopul de preparare acasă costă 120 lei de persoană și durează trei ore. Înveți să folosești V60, "
            "AeroPress și moka, pleci cu 250 g de cafea la alegere și primești o fișă cu rețetele pe care le-am "
            "exersat împreună. Grupul are cel mult opt persoane.",
            "Workshopul pentru firme este personalizat și costă de la 900 lei pentru un grup de până la 15 persoane, "
            "în funcție de locație și de durată. Putem veni la sediul dumneavoastră cu tot echipamentul necesar.",
        ],
    ),
    "/blog/cum-alegi-cafeaua": (
        "Cum alegi cafeaua potrivită",
        [
            "Prima întrebare nu este ce cafea e mai bună, ci cum o prepari. Pentru espresso cauți un profil de "
            "prăjire mai închis, cu note de ciocolată și caramel. Pentru filtru, un profil mai deschis scoate în "
            "față aciditatea fructată și florală.",
            "Data prăjirii contează mai mult decât data expirării. Cafeaua are cel mai bun gust între șapte zile "
            "și șase săptămâni după prăjire; după aceea pierde aromele volatile, chiar dacă rămâne sigură la consum.",
            "Păstrează boabele într-un recipient opac, închis, departe de căldură și lumină. Nu le ține în frigider, "
            "pentru că absorb mirosurile și umiditatea. Macină cafeaua chiar înainte de preparare.",
        ],
    ),
    "/blog/metode-de-preparare": (
        "Metode de preparare acasă",
        [
            "La V60 folosim 15 grame de cafea la 250 ml de apă la 94 de grade, cu o infuzie totală de aproximativ "
            "doua minute și jumătate. Macinarea este medie-fină, ca sarea de masă.",
            "AeroPress este metoda cea mai iertătoare pentru începători: 17 grame de cafea, 220 ml de apă la 85 de "
            "grade și un minut și jumătate de infuzie. Rezultatul este curat și ușor de repetat.",
            "Moka produce o cafea intensă, apropiată de espresso. Umple rezervorul cu apă fierbinte, nu rece, și "
            "scoate ibricul de pe foc imediat ce începe să sâsâie, ca să eviți gustul ars.",
        ],
    ),
    "/intrebari-frecvente": (
        "Întrebări frecvente",
        [
            "Cafeaua este proaspătă? Da, prăjim de două ori pe săptămână, marți și vineri, iar pe fiecare pachet "
            "este tipărită data prăjirii. Nu vindem cafea prăjită de mai mult de trei săptămâni.",
            "Aveți cafea fără cofeină? Da, avem cafeaua decofeinizată Sugarcane, procesată fără solvenți chimici. "
            "Gustul este apropiat de cel al cafelelor obișnuite.",
            "Pot plăti în rate? Pentru comenzi de peste 500 lei, firmele pot plăti în două tranșe, cu acordul "
            "prealabil al contabilității noastre. Pentru persoane fizice plata se face integral la comandă.",
        ],
    ),
}

# Întrebare -> (calea paginii, cuvânt-cheie care apare numai în pasajul așteptat). Peste 20, în română, formulate
# natural (fără a copia cuvintele din pasaj mai mult decât e firesc într-o întrebare).
INTREBARI: list[tuple[str, str, str]] = [
    ("Cât costă cafeaua din Etiopia Guji?", "/produse", "Etiopia Guji"),
    ("Ce note de gust are cafeaua din Columbia?", "/produse", "caramel, nuci"),
    ("Cât costă un kilogram de cafea Guatemala?", "/produse", "138 lei"),
    ("Din ce este făcut amestecul casei?", "/produse", "60% Columbia"),
    ("Aveți cafea decofeinizată și cum este procesată?", "/produse", "acetat de etil"),
    ("Cât costă abonamentul lunar de cafea?", "/abonamente", "89 lei pe lună"),
    ("Ce include abonamentul pentru birou?", "/abonamente", "3 kilograme"),
    ("Până când este valabilă reducerea de 15% la prima comandă?", "/abonamente", "31 decembrie 2026"),
    ("Cât plătesc pentru livrare dacă comanda e sub 150 lei?", "/livrare", "15 lei pentru comenzile sub 150"),
    ("În ce zile se prăjește cafeaua și până când pot comanda?", "/livrare", "marți și vineri. Comenzile"),
    ("Pot returna un pachet deschis?", "/livrare", "pachetele deschise"),
    ("Puteți plăti ramburs la curier?", "/livrare", "ramburs la curier"),
    ("Care este programul cafenelei sâmbăta?", "/contact", "duminică închis"),
    ("La ce telefon pot da o comandă?", "/contact", "0700 000 000"),
    ("Unde pot parca lângă cafenea?", "/contact", "patru locuri"),
    ("Când este degustarea gratuită și cât durează?", "/workshopuri", "prima sâmbătă a lunii începe"),
    ("Cât costă workshopul de preparare acasă?", "/workshopuri", "120 lei de persoană"),
    ("Faceți workshopuri pentru firme?", "/workshopuri", "pentru firme"),
    ("Cum aleg o cafea pentru espresso?", "/blog/cum-alegi-cafeaua", "profil de prăjire mai închis"),
    ("Cât timp rămâne cafeaua bună după prăjire?", "/blog/cum-alegi-cafeaua", "șase săptămâni"),
    ("Cum păstrez boabele de cafea?", "/blog/cum-alegi-cafeaua", "recipient opac"),
    ("Câtă cafea și apă folosiți la V60?", "/blog/metode-de-preparare", "94 de grade"),
    ("Cum prepar cafeaua la AeroPress?", "/blog/metode-de-preparare", "17 grame"),
    ("Cumpărați boabele direct de la ferme sau cooperative?", "/despre", "cooperative și ferme mici"),
    ("Cu cât mai mult le plătiți fermierilor?", "/despre", "20% mai mare"),
    ("Câți oameni are echipa?", "/despre", "opt oameni"),
    ("Pot plăti în rate?", "/intrebari-frecvente", "în două tranșe"),
]


def html_pagina(cale: str, linkuri: list[str] | None = None) -> str:
    titlu, paragrafe = PAGINI[cale]
    corp = "".join(f"<p>{html.escape(p)}</p>" for p in paragrafe)
    nav = '<nav><a href="/">Acasă</a> <a href="/despre">Despre</a> <a href="/produse">Produse</a></nav>'
    extra = "".join(f'<a href="{html.escape(h)}">{html.escape(h)}</a> ' for h in (linkuri or []))
    return (
        f'<!doctype html><html lang="ro"><head><meta charset="utf-8"><title>{html.escape(titlu)} · Cafeneaua Zorilor</title>'
        f"</head><body>{nav}<main><h1>{html.escape(titlu)}</h1>{corp}{extra}</main>"
        f"<footer>© Cafeneaua Zorilor</footer></body></html>"
    )


# --- F4.9: recenzii, comentarii și întrebări INVENTATE (nicio persoană reală), pentru vocea clientului.
# 24 de texte curate + două cu date personale inventate (un email și un telefon) pe care garda trebuie să le respingă.
# Fiecare apare în material cu o semnătură de autor („— Ioana M.”), care NU trebuie să ajungă în citate.
RECENZII: list[str] = [
    "Cafeaua Etiopia Guji miroase a flori și are gust de afine, exact cum scrie în descriere.",
    "Pachetul a ajuns în două zile și pe el scria data prăjirii. Așa ceva nu am mai văzut la supermarket.",
    "Mi s-a părut puțin mai scumpă decât cafeaua din magazin, dar diferența de gust se simte din prima ceașcă.",
    "Abonamentul lunar a fost cea mai bună decizie: nu mai rămân niciodată fără cafea și nu mai caut prin magazine.",
    "Am vrut să renunț la abonament și mi-au spus că pot opri oricând, fără explicații. Asta m-a convins să rămân.",
    "La workshop am învățat în sfârșit să folosesc V60 fără să-mi iasă o cafea amară.",
    "Columbia Huila merge perfect la aparatul automat din birou; colegii au întrebat de unde e cafeaua.",
    "Nu știam ce cafea să aleg pentru espresso și m-au ajutat pe mesaj, fără să mă împingă spre cea mai scumpă.",
    "Livrarea gratuită peste 150 de lei m-a făcut să comand două pachete deodată.",
    "Mi-a plăcut că au schimbat pachetul când nu mi-a plăcut gustul, fără formalități.",
    "Prețul pare mare la început, dar o cafea proaspătă se macină mai puțin și ține mai mult.",
    "Degustarea de sâmbătă a fost relaxată; nimeni nu m-a făcut să mă simt prost că nu știu termenii.",
    "Cafeaua decofeinizată are gust adevărat de cafea, nu de carton, ceea ce nu mă așteptam.",
    "Am comandat pentru birou abonamentul cu vizită de barista și râșnița merge acum mult mai bine.",
    "Ambalajul este simplu și rezistent, iar supapa păstrează aroma până la ultima boabă.",
    "Aș vrea mai multe variante pentru cei care beau cafea cu lapte; Columbia e bună, dar caut ceva mai dulce.",
    "Cât de repede ajunge cafeaua după prăjire? Pe pachetul meu era data de marți și a ajuns vineri.",
    "Cum aleg cafeaua potrivită pentru un filtru de casă? Nu știu dacă să iau Etiopia sau Guatemala.",
    "Se poate opri abonamentul dacă plec în vacanță? Mi-e teamă să nu plătesc pentru ceva ce nu folosesc.",
    "Pot comanda cafea măcinată? Nu am râșniță acasă și nu vreau să cumpăr una doar pentru asta.",
    "Mi-a plăcut cum explică pe site notele de gust, fără cuvinte pretențioase.",
    "Am cumpărat cadou un pachet pentru socrul meu și a cerut încă unul după o săptămână.",
    "Singurul lucru care m-a deranjat a fost comisionul de 6 lei la plata ramburs; plata cu cardul a fost mai simplă.",
    "Prăjesc și eu acasă, dar cafeaua lor mi-a arătat cât de mult contează proaspătul.",
]
RECENZII_CU_DATE_PERSONALE: list[str] = [
    "Dacă aveți nelămuriri, scrieți-mi la ana.test@exemplu.test și vă povestesc cum merge abonamentul.",
    "Sunați-mă la 0700 111 222 dacă vreți o părere sinceră despre Guatemala Antigua.",
]
AUTORI = ["Ioana M.", "Radu P.", "Elena D.", "Mihai T.", "Alina S.", "Costin B."]


def recenzii_ca_material() -> dict[str, list[str]]:
    """Trei documente (recenzii, comentarii, întrebări): fiecare paragraf = o recenzie + semnătura autorului."""
    toate = [*RECENZII, *RECENZII_CU_DATE_PERSONALE]
    linii = [f"{t} — {AUTORI[k % len(AUTORI)]}" for k, t in enumerate(toate)]
    return {
        "Recenzii pe pagina de socializare": linii[:9],
        "Comentarii la postări": linii[9:18],
        "Întrebări primite de la clienți": linii[18:],
    }
