# FS.4 Atribuirea vânzărilor

- **Context:** FS.3, raport lunar F10.5. ADR-05: calcul determinist, nu model.
- **Construiește:** raport lunar UTC, grupare campanie/canal/monedă, UTM prioritar față de cod reducere mapat explicit; necunoscut separat; anulări și rambursări scăzute.
- **Nu:** atribuire probabilistică, cross-device, modificarea modulului analizei (zona altei sesiuni).
- **Date:** comanda normalizată are creata_la UTC; raport API public pentru consumatorul raportului lunar. Coduri → (campanie, canal), mapare injectată per tenant.
- **Acceptare:** UTM câștigă; cod fără UTM atribuit; necunoscut păstrat; monede separate; limita lunii respectată; anulare/rambursare scăzute.
- **Riscuri:** UTM declarat de browser, cod partajat; atribuire orientativă, fără a afirma cauzalitate.
- **Module:** app/comert și teste/spec proprii. Fără migrare.
- **Depinde:** FS.3. **Deblochează:** FS.5/6. **Revizuire:** calcul financiar, sesiunea A.
- **Întrebări:** niciuna. Conectarea efectivă în raportul F10 este cerere pentru proprietarul modulului.

Maparea codurilor este persistentă în comert_magazine.coduri_reducere:
cod → [campanie, canal], izolată prin RLS; ecranul o trimite raportului lunar.
Configurarea se face de consumatorul contractului local; nu există încă interfață de editare.
