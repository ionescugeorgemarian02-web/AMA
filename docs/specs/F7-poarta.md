# Poarta F7: de la audit la plată și la prima aprobare

Testul `tests/integration/test_poarta_f7.py`, un singur drum cap-coadă, prin rutele reale: auditul cerut în site și
confirmat din email → raportul → „Alege pachetul” → înscrierea → pagina de plată a procesatorului (mediul de probă) →
webhook-uri semnate: abonament activ, lead `client` → emailul cu linkul de activare → contul → interviul din portal →
brieful aprobat de client în portal → (agenția: lanțul F4–F6 cu modelul FALS) → primul lot de 2 postări aprobat de
client dintr-o atingere → pachetele de publicare pregătite; bara de progres arată pașii făcuți.

**Trecută local pe SIMULARE (D-007).** Simulate: emailul, procesatorul de plăți, motorul de audit, modelele. **Rămân
la migrare:** procesatorul real și facturarea fiscală (e-Factura), furnizorul de email, motorul de audit din BigBrain,
domeniul și proxy-ul site-ului, telefonul real.
