# Fișa de pregătire și măsurare a VPS-ului dedicat (Ș3)

Șablon gol. Se completează de proprietar la migrarea pe VPS (F0.4, D-001). Închide punctul de decizie PD1.

- **Ce ai cumpărat:** furnizor ______ · plan ______ · locație ______ · nuclee ___ (dedicate / partajate) · memorie ___ GB · disc ___ GB (tip ______)
- **Drepturi:** acces de administrator: da / nu · instalarea inițială o face: ______
- **Instalarea inițială** (`docs/runbooks/instalare-vps.md`, bifată punct cu punct):
  - [ ] Docker și Docker Compose
  - [ ] Utilizator fără drepturi de administrator, sub care rulează platforma
  - [ ] Firewall: deschise doar 80, 443 și administrarea, pe cheie
  - [ ] Proxy cu certificate automate și subdomeniile create
  - [ ] Serviciile repornesc singure după repornirea serverului
  - [ ] Actualizări de securitate automate pentru sistem
- **Test de procesor:** sarcină de probă ______ · timp pe un nucleu ___ s · timp pe toate nucleele ___ s
- **Rezultat:** numărul de culoare grele ___ · tabelul din secțiunea 6.4 refăcut: da / nu · bugetul de disc pentru media ___ GB
- **Decizia PD1:** continui / ajustezi / schimbi VPS-ul. Motiv: ______
