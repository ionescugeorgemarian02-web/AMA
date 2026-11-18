# Juridic — ciorne (F15.4)

**Toate documentele din acest director sunt CIORNE și necesită revizuirea avocatului** (docs/21 §21.13). Nu sunt
consultanță juridică. Paginile publice din `/site/legal/...` se generează din aceste fișiere (`app/site/juridic.py`)
și poartă același marcaj până când avocatul le semnează (atunci se scoate rândul `stare:` din antet).

| Fișier | Pagina publică |
| --- | --- |
| `contract-servicii.md` | `/site/legal/contract` |
| `acord-prelucrare.md` | `/site/legal/acord-prelucrare` |
| `termeni.md` | `/site/legal/termeni` |
| `confidentialitate.md` | `/site/legal/confidentialitate` |
| `cookie-uri.md` | `/site/legal/cookie-uri` |

Formatul: prima linie `# Titlu`, apoi `descriere:` și `stare:` (`ciorna` = necesită revizuirea avocatului),
apoi secțiuni `## ...` cu paragrafe și liste `- ...`. Datele firmei (nume, CUI, adresă) sunt substituenți
`[FIRMA]`, `[CUI]`, `[ADRESA]` până la F0.1.
