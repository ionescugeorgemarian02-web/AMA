## 2. Ipoteze, constrângeri și ce am verificat

Proiectarea pornește de la un VPS dedicat platformei, cu cel puțin 24 GB RAM și fără GPU, de la modele gratuite și de la un cost de rulare cât mai aproape de zero. Am verificat 26 de fapte externe la 10 noiembrie 2026, iar mai multe dintre ele schimbă planul inițial.

### 2.1 Ce am luat ca dat

- **Infrastructură:** un VPS dedicat platformei, cu cel puțin 24 GB RAM, fără GPU. Pe el nu rulează nimic altceva. Numărul de nuclee și discul nu îmi sunt cunoscute. Calculele pornesc de la 8 nuclee și 100 GB \[I\] și se refac în pasul F0.4. CariereAI și BigBrain rămân pe VPS-ul lor actual.
- **Drepturi:** presupun că pe VPS-ul dedicat ai acces de administrator pentru instalarea inițială (Docker, firewall, utilizator dedicat). După aceea platforma rulează fără sudo, ca utilizator obișnuit. Se confirmă în pasul F0.4.
- **Buget:** zero cost de rulare, în afara VPS-ului dedicat. Modelele gratuite sunt cele deja configurate la fabrica de software. Nu am lista exactă a cheilor, deci arhitectura le tratează ca registru configurabil.
- **Mod de lucru:** de pe telefon, fără programare manuală. Codul îl scrie un agent de cod (Opus 5.5 sau un model GPT), într-un repo nou, un pas pe sesiune.
- **Firma:** SRL activ în România. Clienți externi, B2B și B2C. Conținut în română la început.
- **Conturi sociale:** se creează și se conectează ulterior. Asta afectează calendarul aprobărilor API (secțiunea 15).

### 2.2 Fapte verificate la 10 noiembrie 2026

| Subiect și sursă | Ce am găsit | Ce înseamnă pentru noi |
| --- | --- | --- |
| [Claude: Agent SDK și modul headless](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan) \[V\] | Când ești logat cu planul, consumă din limitele abonamentului. O schimbare anunțată pentru 15 iunie 2026 a fost suspendată. | Claude rulează pe cadență, nu în bucla fiecărui task. Politica se poate schimba din nou. |
| [Claude: credite API lunare](https://support.claude.com/en/articles/17154008-monthly-api-credits-for-max-ultra-and-team-plans) \[V\] | Max primește 100 USD, Ultra 200 USD pe lună, pentru Claude API și Agent SDK cu cheie din organizația Console legată. Pro nu primește. Nu se reportează. La epuizare, cererile se opresc. | Pe Max sau Ultra, Consiliul poate fi apelat programatic, cu buget fix. |
| [OpenRouter: limite](https://openrouter.ai/docs/limits) \[V\] | Modelele gratuite: 20 de cereri pe minut; 50 pe zi, sau 1.000 pe zi după 10 USD cumpărați o singură dată. Limita este pe cont. | 10 USD o singură dată este singura cheltuială cu randament mare. Conturile multiple nu ajută. |
| [Gemini API: termeni](https://ai.google.dev/gemini-api/terms) \[V\] | Din 23 martie 2026, aplicațiile oferite utilizatorilor din SEE pot folosi doar serviciile plătite. | Nivelul gratuit Gemini nu intră în calea de producție pentru clienți. |
| [Groq: limite](https://console.groq.com/docs/rate-limits) \[S\] | Exemple pe model: 30 de cereri pe minut, 1.000 pe zi, 200.000 de tokeni pe zi, la nivel de organizație. | Limita de tokeni contează: la apeluri de 2.500–3.000 de tokeni, ies 65–80 de apeluri pe model pe zi. |
| [Cloudflare Workers AI: preț](https://developers.cloudflare.com/workers-ai/platform/pricing/) \[S\] | 10.000 de „neuroni” gratuiți pe zi. O imagine FLUX schnell 512×512 în 4 pași costă circa 43. | Sursă gratuită de imagini AI. Cota este comună cu textul. |
| [Volatilitatea nivelurilor gratuite](https://github.com/pacocartones/free-llm-api-hub) \[S\] | În 2026 s-au închis sau restrâns mai multe: GitHub Models retras la 30 iulie, Cerebras devenit trial. | Niciun furnizor nu este fundație. Gateway cu rezervă locală. |
| [TikTok: reguli de postare prin API](https://developers.tiktok.com/doc/content-sharing-guidelines) \[V\] | Aplicație neauditată: postări doar private, maximum 5 utilizatori în 24 h. Se cer previzualizare și consimțământ expres înainte de fiecare încărcare. | Pe TikTok rămâne aprobare per postare. Aplicația se creează în F0.6. Auditul se cere când fluxul merge în modul de test (F9.6). |
| [YouTube: încărcare prin API](https://developers.google.com/youtube/v3/docs/videos/insert) \[V\] | Proiectele API neverificate au videoclipurile blocate pe „privat” până la auditul de conformitate. | Proiectul se creează în F0.6. Auditul se cere după F9.4. Costul unui upload se citește din consolă. |
| [Instagram: publicare](https://developers.facebook.com/docs/instagram-platform/content-publishing) \[V\] | Două etape (container, publicare), fișiere la URL public, app review, 100 de postări API în 24 h (unele pagini spun 50). | Citim limita reală din endpoint. Fișierele media se servesc prin HTTPS. |
| [LinkedIn: permisiuni](https://bundle.social/blog/linkedin-api-permissions) \[S\] | Postarea pe profilul propriu este self-serve. Paginile de companie cer Community Management API, cu review. | Pagina de companie a clientului depinde de o aprobare. |
| [Meta Ads: autorizare](https://developers.facebook.com/docs/marketing-api/get-started/authorization) \[V\] | Administrarea conturilor de reclame ale altora cere Advanced Access, App Review și Business Verification. | Verificarea firmei în Meta Business se face în F0. |
| [Google Ads API: acces](https://developers.google.com/google-ads/api/docs/first-call/dev-token) \[V\] | Tokenurile de developer au fost retrase la 9 septembrie 2026. Nivelurile țin de proiectul Google Cloud: Test, Explorer (2.880 de operații pe zi), Basic (15.000), Standard. | Explorer ajunge pentru început. |
| [Meta Ad Library API](https://adsuploader.com/blog/facebook-ad-library-api) \[S\] | Returnează reclamele livrate în UE din ultimul an. Cere confirmarea identității. Acoperirea este raportată ca incompletă. | Sursă legală pentru analiza concurenței. |
| [Legea 506/2004, art. 12](https://legislatie.just.ro/Public/DetaliiDocument/56973) \[V\] | Comunicările comerciale prin email cer consimțământ expres prealabil. Regula se aplică și abonaților persoane juridice. | Cold email automat către firme din România: nu. |
| [AI Act, art. 50](https://www.actuia.com/en/news/ai-act-obligations-in-force-and-delays-under-omnibus-2026-1744/) \[S\] | Obligațiile de transparență se aplică din 2 august 2026. Marcarea lizibilă de mașini pentru sistemele deja pe piață are termen 2 decembrie 2026. | Etichetăm și marcăm conținutul AI. Nu ștergem proveniența. |
| [Etichetare AI pe platforme](https://www.postora.org/blog/ai-generated-content-labels-social-media-2026) \[S\] | TikTok, Meta și YouTube cer etichetarea conținutului AI realist și citesc metadatele C2PA. Conținutul neetichetat poate fi restricționat sau eliminat. | La fel ca mai sus. |
| [Voce în română: Piper](https://huggingface.co/rhasspy/piper-voices/blob/952f41d04e72535c242ae181b2ee1ed13d357d12/ro/ro_RO/mihai/medium/MODEL_CARD) \[V\] | Există voce ro\_RO pe set de date CC0. [VoxCPM2](https://huggingface.co/openbmb/VoxCPM2) nu listează româna. Un [furnizor](https://tts.ai/text-to-speech/romanian/) marchează vocea românească drept necomercială. | Piper este baza. Licența vocii se verifică sau se înregistrează o voce proprie. |
| [Video programatic: HyperFrames](https://github.com/heygen-com/hyperframes) \[S\] | Licență Apache 2.0. Redă HTML în MP4 cu Chrome headless și FFmpeg. Remotion este gratuit doar până la 3 persoane în firmă. | FFmpeg ca bază, HyperFrames pentru animații de brand. |
| [GEPA](https://arxiv.org/pdf/2507.19457) și [ACE](https://arxiv.org/pdf/2510.04618) \[V\] | GEPA (ICLR 2026, disponibil în DSPy) evoluează prompturi prin reflecție. ACE ține un „playbook” actualizat incremental. | Ambele intră în sistemul de învățare (secțiunea 11). |
| [DBOS](https://docs.dbos.dev) \[V\] | Licență MIT. Rulează ca bibliotecă peste Postgres, cu workflow-uri durabile și cozi cu limită de rată. | Nu avem nevoie de un server de orchestrare separat. |
| [Incidentul LiteLLM](https://www.netspi.com/blog/executive-blog/ai-ml-pentesting/litellm-supply-chain-compromise/) \[S\] | Versiunile 1.82.7 și 1.82.8 de pe PyPI au fost compromise la 24 martie 2026 și furau credențiale. | Gateway propriu, subțire. Dependențe fixate cu hash. |
| [Reddit API](https://octolens.com/blog/reddit-api-pricing) \[S\] | Nivelul gratuit este doar pentru uz necomercial. | Reddit nu intră în colectarea automată. |
| [Google Trends API](https://scrapfly.io/blog/posts/google-trends-api-alternatives) \[S\] | Există oficial din iulie 2025, în alfa, cu acces pe bază de cerere. | Aplicăm. Până atunci, fluxul RSS de tendințe zilnice. |
| [Retenție video pe YouTube](https://academy.adriel.com/en/youtube-analytics) \[S\] | YouTube Analytics API dă curba de retenție în 100 de puncte per video. | „Secunda la care pleacă privitorii” există doar pe YouTube. |
| [Revolut: Subscriptions API](https://developer.revolut.com/docs/guides/merchant/billing-subscriptions/api/introduction) \[V\] | Merchant API are planuri, abonamente, încasare automată și webhook-uri. | Abonamentele clienților se pot automatiza cu procesatorul pe care îl folosești deja. |

Toate limitele de mai sus se schimbă des. Agentul de cod le reverifică în pasul în care construiește fiecare conector.

### 2.3 Ce nu știu încă și cum se află

| Necunoscută | Cum se verifică | Pas |
| --- | --- | --- |
| Lista exactă de modele și chei gratuite pe care le ai | Inventar în registrul de modele | F0.3 |
| Câte nuclee, cât disc și ce drepturi ai pe VPS-ul dedicat | Panoul furnizorului și măsurare pe VPS | F0.4 |
| Cât de repede generează modelul local pe procesorul VPS-ului | Test de viteză | F3.5 |
| Ce platforme cer demonstrația fluxului încă de la prima cerere | Se citește pe pagina fiecărei cereri | F0.6 |
| Dacă auditul TikTok acceptă aprobarea din portal drept consimțământ | Se află doar aplicând | F9.6 |
| Rolul platformei sub art. 50 (furnizor sau implementator) | Consultanță juridică | F0.7 |
| Calitatea în română a fiecărui model gratuit | Test comparativ pe set de aur | F3.6 |
| Dreptul de uz comercial al vocii românești Piper | Verificare juridică sau voce proprie | F8.1 |
| Viteza reală de randare video | Test de capacitate | F8.9 |
| Costul în unități al unui upload YouTube (sursele spun 100 sau 1.600) | Citit din consola Google Cloud | F9.4 |
| Dacă planul tău Claude permite conectori personalizați și sarcini programate | Setările din aplicația Claude | F13.7 |
