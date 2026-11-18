# G-pool Gateway „pool” de modele gratuite (portat din fabrica)

- **Pasul:** G-pool (în afara fazelor, cerut de proprietar pe 2026-11-18; ADR-04, `docs/08`, F3.1–F3.6). Sesiunea A,
  D-028. Sursa: `fabrica-autonoma/core/gateway` (`catalog`, `limits`, `quota_manager`, `capacity`, `model_health`,
  `diversity_guard`, `transport`, `service`) și `core/vault/store.py`, citite, nu copiate: AMA avea deja clientul,
  adaptoarele, cotele cu rezervare și decontare, întrerupătorul și rutarea pe profiluri (F3.1–F3.6).
- **Ce face:**
  - `app/gateway/catalog.py`: furnizorii (Gemini, NVIDIA NIM ×2 conturi, Groq, OpenRouter, SambaNova, Cloudflare,
    Mistral, Kilo, LLM7, Z.ai, Ollama Cloud, SEA-LION), familiile, `PROVIDER_SECRETS` (nume exacte),
    `OPENAI_COMPATIBLE`, 47 de modele cu limitele cunoscute, fusul resetării, rezervele pe rol;
  - `app/gateway/secrete.py`: cheile din mediu (nume exact), apoi din seif, apoi numele vechi `AMA_CHEIE_*`;
    un furnizor fără TOATE secretele e dezactivat automat (`fara_cheie`); `account_id` Cloudflare și adresa NIM
    vin din secrete;
  - `app/gateway/seif.py` + tabelul `gateway_seif` (migrarea `0109`): Fernet, cheie derivată (HKDF) din
    `AMA_MASTER_KEY`; doar nume din catalog; RLS forțat, doar agenția; CLI `python -m app.gateway.seif pune|lista|sterge`;
  - rutare (`rutare.py`): intrarea de lanț `rezerva:<profil>` (rezervele rolului, rapide înaintea celor lente,
    familiile alternate; nepotrivitele se sar în tăcere), `alta_familie=True` la `gateway.apeleaza` (judecătorul din
    altă familie decât autorul, paza diversității), verificarea prealabilă a contextului (`context_sau_tpm_prea_mic`;
    tokenii pe minut îi refuză deja limitatorul ca `imposibil`), modelele bolnave sărite;
  - `app/gateway/sanatate_model.py`: 404 → model scos o zi; 3 erori de server/rețea → 5 minute; succesul resetează;
    fiecare pauză lasă o urmă FT (`gateway` / `model_indisponibil`);
  - cote: resetul zilnic al Gemini la miezul nopții în `America/Los_Angeles` (ora UTC recalculată, cu ora de vară);
    restul pe limitatorul existent (rezervare, decontare, corectare din antete, blocare după 429);
  - migrarea `0109`: sămânța catalogului (furnizori noi `inactiv`, uz comercial neconfirmat, marcaj `I`; modelele noi
    și la furnizorii existenți) și `rezerva:<profil>` la coada profilurilor clasificare, rescriere, creație, judecată,
    strategie (consiliul rămâne pe T4);
  - `python -m app.gateway.verifica_furnizori [--furnizor X] [--toate-modelele] [--json]`: un apel mic (16 tokeni)
    la fiecare furnizor cu toate secretele, raport ok / eroare / dezactivat (cu numele secretelor lipsă), urmă FT;
    ieșire 0 / 1 / 2.
- **Hotărâri.**
  - Catalogul e cod (date), registrul din bază rămâne sursa rutării: proprietarul activează furnizorii după ce confirmă
    termenii (8.1), ca până acum. OpenRouter și restul furnizorilor F3.1 rămân neschimbați; numele vechi de chei merg.
  - FreeLLMAPI (agregator local, `http://`) nu intră: AMA cere `https` și nu are agregatorul în infrastructură.
  - Sănătatea pe model e în memoria procesului; cea comună (pe furnizor) rămâne întrerupătorul din bază.
  - `# NEVERIFICAT:` identificatorii modelelor și limitele (luate din fabrica, 10.2026), termenii de folosire ai
    furnizorilor noi, resetul real al cotelor.
- **Gata când:**
  - fiecare furnizor din catalog are secretele cu nume exacte în `infra/env/*.example` (goale) și în compose;
  - fără toate secretele, furnizorul nu primește apeluri; cu ele, primește (după activare);
  - rolurile AMA cad pe rezerve din alte familii când lanțul explicit e epuizat; judecătorul poate cere altă familie;
  - un model 404 nu mai e încercat; o cerere mai mare decât contextul nu e trimisă;
  - `verifica_furnizori` apelează doar furnizorii activi, nu afișează chei și raportează lipsurile.
- **Teste:** `tests/unit/test_gateway_pool.py` (catalog, secrete, rutare, sănătate, verificare pe transport HTTP
  simulat), `tests/integration/test_gateway_pool.py` (sămânța, seiful criptat, „altă familie”, 404 pe furnizor fals).
- **De verificat la primul test live:** `python -m app.gateway.verifica_furnizori --toate-modelele` cu cheile reale;
  modelele care răspund 404 se scot din catalog; termenii fiecărui furnizor nou se confirmă în inventar înainte de
  activare.
