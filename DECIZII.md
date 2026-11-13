# Fișierul de decizii

Hotărârile luate pe parcurs, în ordine cronologică. Deciziile de arhitectură au fișier propriu în `docs/adr/`.

## De hotărât de proprietar (F0.1)

| Decizie | Stare | Valoare |
| --- | --- | --- |
| Nișa-pilot | **deschisă** | – |
| Pachetul-pilot | **deschisă** | – |
| Numele agenției | **deschisă** | – (în cod se folosește provizoriu „AMA”) |

## Decizii luate

### D-001 (2026-11-11) — Construim întâi pe git, VPS-ul vine la final

- **Context:** planul (secțiunea 23) cere VPS măsurat (F0.4) și staging înainte de F1.
- **Hotărâre (proprietar):** platforma se construiește și se validează în repo, capitol cu capitol; migrarea pe VPS se face o singură dată, la final.
- **Consecințe:** criteriile „Gata când” care cer staging, telefon sau servicii externe se verifică prin teste automate în CI și local. Ce rămâne de verificat pe VPS se adună în `docs/specs/STARE.md`, la „De verificat la migrare”. Pașii F0.3–F0.8 (inventar, VPS, cereri de aprobare, juridic, conturi) rămân ai proprietarului și curg în fundal.

### D-002 (2026-11-11) — O cerere de integrare pe fază

- **Context:** planul spune „un pas = o ramură = o cerere de integrare”.
- **Hotărâre:** până la migrare, o fază (capitol) = o cerere de integrare, cu un commit pe pas. Validarea proprietarului se face la poarta fazei.
- **Consecințe:** revizuirea „doi ochi diferiți” (24.4) se face pe fază: un model scrie, alt model revizuiește diferența față de specificație.

### D-003 (2026-11-11) — Unelte de lucru

- Manager de pachete: `uv`, cu `uv.lock` (versiuni exacte și hash-uri). Python 3.13 în imagini și CI (cerința este ≥ 3.12).
- Acces sincron la bază (SQLAlchemy 2 + psycopg 3): mai simplu de izolat pe client și compatibil cu biblioteca de workflow-uri.
- Scanarea repo-ului după chei scăpate: `detect-secrets`; vulnerabilități: `pip-audit`. Ambele rulează în CI, fixate în `uv.lock`.

### D-004 (2026-11-12) — Bugetele de modele pe client: consum din contoare proprii, P1 cu plafon

- **Context:** 8.5 cere bugete pe client și spune „P0 și P1 au cotă garantată; P2 și P3 se amână la epuizare; P0 continuă”, dar nu spune ce se întâmplă cu P1 peste buget.
- **Hotărâre (adoptată, D-007):** consumul se ține în contoare proprii (nu se citește din jurnal: jurnalul se scrie după apel, deci nu este corect la concurență). P0 nu este atins niciodată; P1 continuă până la 1,5 × bugetul (configurabil), apoi se amână; P2 și P3 se amână la atingerea bugetului. Valorile implicite de buget sunt de pornire, nemăsurate.
- **Consecințe:** `gateway.Amanat(pana_la)` cu momentul resetării (miezul nopții UTC, ora este setare). Se revizuiește după primele luni de consum real.

### D-005 (2026-11-12) — Trei compartimente adăugate Creierului în F4: `brief`, `insight_piata`, `strategie`

- **Context:** `docs/10` §10.1 are zece compartimente. Brieful de onboarding (F4.4), harta pieței și brieful de insight (F4.10) și strategia pe 90 de zile
  (F4.11) cer același regim ca restul Creierului: versiuni, sursă obligatorie, aprobare de om, citire „la o dată”, diferență între versiuni.
- **Hotărâre (adoptată, D-007):** se adaugă trei compartimente ca date (`app/creier/compartimente.py`), fără a le schimba pe cele zece. Nu se creează tabele paralele.
- **Consecințe:** ecranul „Creierul de brand” (F4.8) le arată împreună cu celelalte; `tests/unit/test_creier_compartimente.py` numără 13 și păstrează verificarea
  celor zece din 10.1. Documentul 10.1 se actualizează odată cu poarta F4 (propunere).


### D-006 (2026-11-13) — Faza F5: severitatea hotărăște unde merge un eșec; conținutul livrabilului provizoriu; reguli în TOML

- **Context:** `docs/09` spune „un eșec critic blochează” (9.2) și „un livrabil blocat critic intră în carantină” (9.8), iar 7.3 cere cel mult 2 reparații. Nu spune
  ce eșec merge la reparație și ce eșec la carantină. Nu există încă tabel de conținut (F6) și nici bibliotecă YAML în dependențele de rulare.
- **Hotărâre (adoptată, D-007):** (1) orice `esec` blochează și oprește cascada; severitatea `majora` = reparabil (autorul primește
  instrucțiunea, cel mult 2 runde, apoi om), `critica` = nu se repară prin rescriere (nișă refuzată, injecție) → carantină; avertismentele se numără în puncte (minoră 1,
  majoră 2), peste `AMA_VALIDARE_PRAG_AVERTISMENTE` (4, de pornire) livrabilul cere aprobarea unui om. (2) Până la F6, `livrabile_continut` ține versiunile de conținut ale
  livrabilului (text + câmpuri pe canal + active); F6 îl refolosește. (3) Pachetele de reguli (F5.4) sunt fișiere TOML (`tomllib`, bibliotecă standard), nu YAML:
  nicio dependență nouă.
- **Consecințe:** F5.10 construiește ieșirea din carantină; un eșec `critica` nu intră în bucla de reparație. O eventuală schimbare (eșecurile critice reparate
  întâi) se face într-un singur loc, `app/validare/agregare.py`, cu decizie nouă în acest fișier.

### D-007 (2026-11-13) — Agentul de cod decide; nimic nu rămâne „de confirmat de proprietar”

- **Context:** pașii lăsau hotărâri „de confirmat de proprietar” sau „rămâne la proprietar”, iar unii pași păreau să aștepte o aprobare
  care nu ține de cod.
- **Hotărâre (proprietar):** toate deciziile le ia agentul de cod: alege cea mai bună soluție, o aplică, o documentează aici sau în
  specificația pasului și continuă. Nu lasă nimic „de confirmat de proprietar” și nu sare peste pași. Singurele excepții sunt cele care
  cer tehnic resurse externe (chei de API, conturi de platformă, VPS): acestea stau la „De verificat la migrare” (`docs/specs/STARE.md`),
  iar tot ce depinde de ele se construiește și se testează cu simulări. Mecanismele pentru oamenii agenției (etichetare umană, promovarea
  exemplelor în setul de aur, aprobări) sunt funcții ale produsului: se construiesc complet, dar nu sunt condiții pentru a închide pașii.
- **Consecințe:** D-004, D-005 și D-006 sunt adoptate (nu mai sunt propuneri). În `docs/specs/STARE.md` starea fiecărui pas spune ce este
  verificat local și ce depinde de resurse externe, nu ce „așteaptă proprietarul”.
