# Poarta F8 — „zece video consecutive trec controlul media fără intervenție”

- **Test:** `tests/integration/test_poarta_f8.py`.
- **Drumul, fără niciun om:** scriptul pe bătăi (E2) -> normalizare -> vocea verificată prin transcriere inversă ->
  Regizorul (prin gateway) -> lista validată -> montajul ca job durabil pe două culoare grele (subtitrări, muzică
  atenuată, nivel) -> G6 pe fișierul final -> coperta din șablon (G5) -> pașaport și etichetă (G11). Zece
  hook-uri, formate A și B alternate, trei canale, cu și fără muzică.
- **Reale:** FFmpeg, libass, Postgres (RLS), motorul durabil, validatorii G5 / G6 / G11, licențele cerute de bază.
- **SIMULATE (D-007):** vocea (Piper), transcriptorul (whisper.cpp), stock-ul, generarea de imagini, muzica,
  modelul Regizorului.
- **La migrare:** poarta repetată pe VPS cu Piper, whisper.cpp, furnizorii reali și modelul real; ascultarea și
  vizionarea de către un om a primelor zece video.
