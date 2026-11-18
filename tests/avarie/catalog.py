"""Catalogul testelor de avarie (F15.1): fiecare scenariu din docs/25 §25.3 -> testele care îl dovedesc.

Testele noi stau în `tests/avarie/`; unde un pas anterior a construit deja dovada (gateway, motor, efecte,
reclame, backup), catalogul o referă, ca să nu dubleze rularea în `make check`. `scripts/avarie.sh` rulează
exact nodurile de aici (local sau pe staging) și scrie rezultatul pe scenarii.
"""

from dataclasses import dataclass

IN = "tests/integration/"
C = "tests/chaos/"
A = "tests/avarie/"


@dataclass(frozen=True)
class Scenariu:
    cod: str
    titlu: str  # exact ca în tabelul din docs/25 §25.3
    teste: tuple[str, ...]


SCENARII: tuple[Scenariu, ...] = (
    Scenariu(
        "A01",
        "Furnizorul principal de modele nu răspunde",
        (
            IN + "test_gateway_rutare.py::test_cu_un_furnizor_oprit_munca_trece_pe_urmatorul",
            IN
            + "test_gateway_rutare.py::test_eroare_de_server_trei_reincercari_cu_pauza_crescatoare_apoi_alt_furnizor",
            IN + "test_gateway_rutare.py::test_strategia_se_amana_nu_se_degradeaza",
            IN + "test_gateway_rutare.py::test_autentificare_pune_furnizorul_pe_pauza_cu_alerta_si_audit",
        ),
    ),
    Scenariu(
        "A02",
        "Toate cotele găzduite sunt epuizate",
        (
            IN + "test_gateway_rutare.py::test_strategia_se_amana_si_cand_cota_e_epuizata_la_toti",
            IN + "test_gateway_rutare.py::test_clasificarea_degradeaza_la_modelul_local_cu_marcaj",
            IN + "test_gateway_cote.py::test_zece_la_suta_din_limita_zilnica_ramane_pentru_p0",
        ),
    ),
    Scenariu(
        "A03",
        "Baza de date repornește în mijlocul unui workflow",
        (
            A + "test_baza_repornita.py::test_baza_repornita_la_mijloc_fluxul_reia_fara_pasi_dubli",
            C + "test_efecte.py::test_sigkill_dupa_ce_platforma_a_inregistrat_trimiterea_nu_se_retrimite",
        ),
    ),
    Scenariu(
        "A04",
        "Workerul este oprit forțat în timpul unei randări",
        (
            A + "test_resurse.py::test_randarea_reluata_sterge_fisierele_partiale_si_termina_o_data",
            C + "test_recuperare.py::test_flux_oprit_la_mijloc_reia_de_la_ultimul_pas",
            C + "test_watchdog.py::test_worker_oprit_fortat_este_repornit_si_jobul_se_termina_exact_o_data",
        ),
    ),
    Scenariu(
        "A05",
        "Discul ajunge la 85%",
        (
            A + "test_resurse.py::test_discul_la_85_curata_partialele_si_alerteaza_o_data",
            A + "test_resurse.py::test_cu_discul_plin_randarea_noua_se_amana_si_porneste_dupa_eliberare",
        ),
    ),
    Scenariu(
        "A06",
        "Memoria se apropie de limită",
        (A + "test_resurse.py::test_memoria_la_limita_amana_doar_joburile_grele",),
    ),
    Scenariu(
        "A07",
        "Toate culoarele grele sunt ocupate și sosește un job P0",
        (
            IN + "test_motor_cozi.py::test_prioritatile_si_termenele_hotarasc_ordinea_pornirii",
            A + "test_culoare.py::test_p0_trece_in_fata_cozii_cand_culoarele_grele_sunt_ocupate",
        ),
    ),
    Scenariu(
        "A08",
        "Un token de platformă expiră",
        (
            IN + "test_publicare_api_interfata.py::test_token_respins_pune_pauza_iar_reautorizarea_o_ridica",
            IN + "test_efecte.py::test_eroare_de_autentificare_pune_canalul_pe_pauza_si_nu_pierde_efectul",
            IN + "test_publicare_sanatate.py::test_tokenul_aproape_expirat_cere_reautorizare_o_singura_data",
        ),
    ),
    Scenariu(
        "A09",
        "Un webhook sosește de două ori",
        (
            A + "test_webhook_dublu.py::test_webhookul_de_plata_repetat_se_aplica_o_singura_data",
            IN + "test_telegram.py::test_actualizare_repetata_se_executa_o_singura_data",
        ),
    ),
    Scenariu(
        "A10",
        "Platforma răspunde cu eroare după ce a publicat",
        (
            IN
            + "test_efecte.py::test_conectorul_executa_apoi_raspunde_cu_eroare_executorul_verifica_si_nu_retrimite",
            IN
            + "test_publicare_api_interfata.py::test_executorul_publica_o_singura_data_si_dupa_raspuns_pierdut",
        ),
    ),
    Scenariu(
        "A11",
        "Un document colectat conține instrucțiuni ostile",
        (
            IN + "test_creier_context.py::test_un_pasaj_ostil_ramane_text_extern_neutralizat",
            IN + "test_gateway_garzi.py::test_text_ostil_nemarcat_da_semnal_dar_nu_blocheaza",
            IN + "test_gateway_garzi.py::test_atacul_ajunge_la_model_doar_in_zona_de_date_marcata",
        ),
    ),
    Scenariu(
        "A12",
        "Cheltuială anormală simulată la reclame",
        (
            IN + "test_reclame_urgenta.py::test_propunerea_peste_plafon_e_refuzata_si_anomalia_opreste_tot",
            IN + "test_reclame_urgenta.py::test_celelalte_semnale_opresc_si_ele",
        ),
    ),
    Scenariu(
        "A13",
        "VPS-ul repornește complet",
        (
            A + "test_repornire_vps.py::test_toate_serviciile_au_politica_de_repornire",
            C + "test_watchdog.py::test_worker_oprit_fortat_este_repornit_si_jobul_se_termina_exact_o_data",
            C + "test_programare.py::test_dupa_sigkill_nu_raman_goluri_si_nu_exista_dubluri",
        ),
    ),
    Scenariu(
        "A14",
        "Restaurare pe un mediu curat",
        (IN + "test_backup_restore.py::test_circuit_complet_backup_si_restaurare",),
    ),
)


def noduri() -> list[str]:
    """Toate nodurile, fără dubluri, în ordinea catalogului."""
    return list(dict.fromkeys(t for s in SCENARII for t in s.teste))


if __name__ == "__main__":
    print("\n".join(noduri()))
