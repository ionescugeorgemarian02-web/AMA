## 1. Verdictul pe scurt

Platforma se poate construi pe un VPS dedicat, cu modele gratuite și cu un cost de rulare mic și fix, dar nu „100% autonomă din prima zi” și nu cu toate cele 33 de piese exact cum le-ai descris. Mai jos este varianta care poate funcționa legal, stabil și profitabil.

**Cum am citit cererea.** „Nu scrie cod, doar pașii de construcție” înseamnă: fără cod, cu arhitectură și pași detaliați. Documentul nu conține cod.

### Ce este fezabil cu resursele actuale

- Cercetare, strategie, texte, scripturi și validare în cascadă, pe modele gratuite plus un model local ținut încărcat permanent, de rezervă.
- Voce în română și video „faceless” (stock, imagini, subtitrări cuvânt cu cuvânt, muzică), montat automat pe CPU.
- Panou de control complet de pe telefon, portal pentru clienți, abonamente cu plată recurentă.
- Învățare autonomă reală, în trepte: memorie de lecții, optimizare de prompturi, alegere adaptivă a variantelor, apoi modele predictive când există date.
- Publicare și reclame prin API-urile oficiale, cu plafoane de buget și butoane de oprire.

### Ce nu este fezabil sau nu trebuie construit

- **Avatare cu lip-sync și video generativ la calitate comercială.** Cer GPU sau API plătit. Versiunea 1 folosește formate fără avatar.
- **Publicare publică automată din prima săptămână.** TikTok, YouTube, Instagram și LinkedIn cer audit sau aprobare, cu durată de săptămâni. Până atunci folosim „publicare asistată”.
- **Trei piese din lista ta.** Ștergerea urmelor AI (#24), anti-detect cu proxy-uri (#26) și cold email automat pe liste extrase (#28 și parțial #9) încalcă regulile platformelor sau legea din România. Le înlocuiesc în secțiunea 3.
- **Claude ca motor al fiecărui agent.** Limitele abonamentului nu permit asta. Claude devine Consiliu și Strateg, pe cadență.
- **„Exclusiv gratuit” ca strategie de creștere.** Este potrivit pentru lansare. După primii clienți, o parte mică din venit trebuie pusă în inferență plătită pe pașii critici.

### Cele opt decizii care definesc arhitectura

1. Monolit modular în Python, un singur Postgres, fără microservicii și fără Redis la început.
2. 87 de componente, fiecare cu tip declarat: serviciu determinist, apel LLM cu schemă, agent cu unelte, model ML sau om. Aproximativ jumătate nu folosesc deloc LLM.
3. Toate apelurile la modele trec printr-un gateway intern care cunoaște cotele și rutează după capacitatea rămasă.
4. Validare în cascadă, de la reguli ieftine la judecători LLM și la om. Faptele vin dintr-un registru aprobat de client; autorii nu au voie să inventeze.
5. Niveluri de autonomie L0–L4 pe client și pe tip de acțiune. Banii și conturile clienților pornesc cu aprobare umană.
6. Doar API-uri oficiale. Fiecare canal are o stare de aprobare și un mod asistat de rezervă.
7. Învățare cu promovare controlată: nimic nu ajunge în producție fără să bată varianta curentă pe setul de test și fără să treacă toate verificările de conformitate.
8. Claude în afara căii critice: platforma continuă să funcționeze dacă abonamentul lipsește o zi.

### Ordine de mărime (ipoteze de validat)

| Indicator | Estimare | Unde e calculul |
| --- | --- | --- |
| Clienți suportați pe cote gratuite | circa 10 pe pachetul mediu | secțiunea 4.7 |
| Timpul tău per client, la început | 1,5–2 ore pe lună | secțiunea 4.6 |
| Memorie alocată platformei, pe VPS dedicat | circa 21 GB din 24, cu toate serviciile pornite permanent | secțiunea 6.4 |
| Joburi grele în paralel | 2 la 8 nuclee; câte unul la fiecare 4 nuclee \[I\] | secțiunea 6.4 |
| Până la prima versiune utilizabilă intern | 3–5 săptămâni de sesiuni cu agentul de cod | secțiunea 23 |
| Aprobări externe pentru publicare și ads | 2–8 săptămâni de la cererea completă, în afara controlului nostru | secțiunea 15.3 |

### Cum citești documentul

- Secțiunile 2–4: decizii pentru tine.
- Secțiunile 5–22: specificația pe care o primește agentul de cod.
- Secțiunile 23–25: pașii de construcție, repo, testare și lansare.
- Secțiunea 26: registrul de riscuri și punctele de decizie.
- Secțiunea 27: anexele. Convenții și glosar, șabloane, fișa fiecărui pas, legătura dintre componente și pași, surse.

Marcaje folosite: **\[V\]** verificat la 10 noiembrie 2026 dintr-o sursă oficială, **\[S\]** sursă secundară, **\[I\]** ipoteză sau estimare de validat.
