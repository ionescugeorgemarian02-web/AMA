"""F1.10 — botul Telegram: webhook păzit, chat permis, comenzi, oprire/pornire, replay, alerte."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.conturi import Rol
from app.db import sesiune_agentie
from app.operare import alerte, opriri
from app.operare.opriri import Oprire
from tests.integration.conftest import Cont
from tests.integration.utile_panou import CHAT, SECRET_WEBHOOK, BotFals, actualizare

pytestmark = pytest.mark.db

Fabrica = Callable[..., Cont]
ANTET = {"X-Telegram-Bot-Api-Secret-Token": SECRET_WEBHOOK}
_id = iter(range(5000, 10**6))


def randuri(admin: Engine, sql: str, **p: object) -> list[dict[str, Any]]:
    with admin.connect() as c:
        return [dict(r._mapping) for r in c.execute(text(sql), p)]


def trimite(
    client: TestClient,
    comanda: str,
    chat: str = CHAT,
    antet: dict[str, str] | None = None,
    uid: int | None = None,
):  # type: ignore[no-untyped-def]
    return client.post(
        "/telegram/webhook",
        json=actualizare(uid or next(_id), comanda, chat),
        headers=ANTET if antet is None else antet,
    )


def oprit(tip: Oprire, tenant_id: object = None) -> bool:
    with sesiune_agentie() as db:
        return opriri.este_oprit(db, tip, tenant_id=tenant_id)  # type: ignore[arg-type]


# ---- apărarea intrării -----------------------------------------------------------------------------------


def test_botul_nesetat_este_dezactivat_webhook_404(client: TestClient) -> None:
    r = trimite(client, "/stare")
    assert r.status_code == 404
    assert alerte.trimite("critic", "t", "x") is False  # nici alertele nu pleacă, fără excepție


@pytest.mark.parametrize(
    "antet",
    [
        {},
        {"X-Telegram-Bot-Api-Secret-Token": ""},
        {"X-Telegram-Bot-Api-Secret-Token": "w" * 31},
        {"X-Telegram-Bot-Api-Secret-Token": SECRET_WEBHOOK + "x"},
        {"X-Wrong": SECRET_WEBHOOK},
    ],
)
def test_antet_secret_gresit_sau_lipsa_este_respins_si_nu_executa_nimic(
    client: TestClient, bot_fals: BotFals, antet: dict[str, str], admin_engine: Engine
) -> None:
    r = trimite(client, "/opreste publicare", antet=antet)
    assert r.status_code == 401
    assert bot_fals.cereri == [] and randuri(admin_engine, "SELECT 1 FROM opriri") == []
    assert randuri(admin_engine, "SELECT 1 FROM telegram_actualizari") == []


def test_secretul_prea_scurt_inseamna_bot_dezactivat(client: TestClient, config: Callable[..., None]) -> None:
    from tests.integration.utile_panou import CHAT, TOKEN_BOT

    config(telegram_bot_token=TOKEN_BOT, telegram_chat_id=CHAT, telegram_webhook_secret="scurt")
    assert trimite(client, "/stare", antet={"X-Telegram-Bot-Api-Secret-Token": "scurt"}).status_code == 404


def test_chat_strain_este_ignorat_si_auditat_fara_sa_primeasca_raspuns(
    client: TestClient, bot_fals: BotFals, admin_engine: Engine
) -> None:
    r = trimite(client, "/opreste publicare", chat="999999")
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert bot_fals.cereri == []  # fără răspuns: nu confirmăm nimic unui necunoscut
    assert randuri(admin_engine, "SELECT * FROM opriri") == []
    a = randuri(
        admin_engine,
        "SELECT * FROM jurnal_audit WHERE actiune = 'telegram.chat_necunoscut' ORDER BY id DESC LIMIT 1",
    )[0]
    assert a["rezultat"] == "refuzat" and a["detalii"]["chat"] == 999999 and a["actor_tip"] == "anonim"
    # nici comanda de repornire nu merge dintr-un chat străin
    trimite(client, "/confirma 123456", chat="999999")
    assert bot_fals.cereri == []


def test_actualizare_repetata_se_executa_o_singura_data(
    client: TestClient, bot_fals: BotFals, admin_engine: Engine
) -> None:
    sql = "SELECT 1 FROM jurnal_audit WHERE actiune = 'oprire.oprit' AND obiect_id = 'reclame'"
    inainte = len(randuri(admin_engine, sql))  # jurnalul de audit nu se golește între teste
    for _ in range(3):
        assert trimite(client, "/opreste reclame", uid=777001).status_code == 200
    assert len(bot_fals.mesaje()) == 1
    assert len(randuri(admin_engine, sql)) == inainte + 1
    assert len(randuri(admin_engine, "SELECT 1 FROM telegram_actualizari WHERE update_id = 777001")) == 1


def test_actualizari_fara_forma_recunoscuta_sau_fara_text_nu_strica_nimic(
    client: TestClient, bot_fals: BotFals
) -> None:
    assert client.post("/telegram/webhook", json={"nimic": 1}, headers=ANTET).json() == {"ok": True}
    assert (
        client.post(
            "/telegram/webhook",
            json={"update_id": 888001, "edited_message": {"message_id": 1}},
            headers=ANTET,
        ).status_code
        == 200
    )
    r = client.post(
        "/telegram/webhook",
        json={
            "update_id": 888002,
            "message": {"message_id": 2, "chat": {"id": int(CHAT), "type": "private"}},
        },
        headers=ANTET,
    )
    assert (
        r.status_code == 200 and bot_fals.mesaje() and "Comenzi:" in bot_fals.mesaje()[0]
    )  # fără text: ajutor


# ---- comenzi ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("comanda", ["/ajutor", "/start", "salut", "/ceva_necunoscut", "/nimic"])
def test_comenzi_necunoscute_primesc_textul_de_ajutor(
    client: TestClient, bot_fals: BotFals, comanda: str
) -> None:
    trimite(client, comanda)
    (raspuns,) = bot_fals.mesaje()
    assert (
        raspuns.startswith("Comenzi:")
        and "/opreste" in raspuns
        and "/porneste" in raspuns
        and "/confirma" in raspuns
    )


def test_stare_arata_versiune_mediu_baza_opriri_si_backup(
    client: TestClient, bot_fals: BotFals, config: Callable[..., None], tmp_path: Any
) -> None:
    config(version="1.2.3-test", backup_status_dir=str(tmp_path))
    trimite(client, "/opreste invatare")
    trimite(client, "/stare")
    stare = bot_fals.mesaje()[-1]
    for fragment in (
        "AMA — stare",
        "Versiune: 1.2.3-test",
        "Mediu: test",
        "Baza de date: ok",
        "Opriri active: invatare",
        "Backup: backup nerulat",
        "test de restaurare nerulat",
        "Notă:",
    ):
        assert fragment in stare, fragment


def test_stare_nu_contine_secrete_si_comanda_cu_numele_botului_merge(
    client: TestClient, bot_fals: BotFals
) -> None:
    from tests.integration.utile_panou import SECRET_WEBHOOK, TOKEN_BOT

    trimite(client, "/stare@ama_bot")
    stare = bot_fals.mesaje()[-1]
    assert stare.startswith("AMA — stare") and TOKEN_BOT not in stare and SECRET_WEBHOOK not in stare


@pytest.mark.parametrize("tip", ["publicare", "reclame", "invatare", "apeluri_platite"])
def test_opreste_seteaza_steagul_si_scrie_auditul_cu_canalul(
    client: TestClient, bot_fals: BotFals, admin_engine: Engine, tip: str
) -> None:
    assert not oprit(Oprire(tip))
    trimite(client, f"/opreste {tip}")
    assert oprit(Oprire(tip))
    assert "Oprit:" in bot_fals.mesaje()[-1] and "apar în fazele următoare" in bot_fals.mesaje()[-1]
    a = randuri(
        admin_engine,
        "SELECT * FROM jurnal_audit WHERE actiune = 'oprire.oprit' AND obiect_id = :t ORDER BY id DESC LIMIT 1",
        t=tip,
    )[0]
    assert a["detalii"]["canal"] == "telegram" and a["actor_tip"] == "sistem" and a["creat_la"] is not None
    row = randuri(admin_engine, "SELECT * FROM opriri WHERE tip = :t", t=tip)[0]
    assert row["activ"] is True and row["canal"] == "telegram"
    trimite(client, f"/opreste {tip}")  # a doua oară: era deja oprit
    assert "Era deja oprit" in bot_fals.mesaje()[-1]


def test_opreste_cu_tip_necunoscut_nu_schimba_nimic(
    client: TestClient, bot_fals: BotFals, admin_engine: Engine
) -> None:
    trimite(client, "/opreste ceva")
    trimite(client, "/opreste")
    assert (
        all("Tip necunoscut" in m for m in bot_fals.mesaje())
        and randuri(admin_engine, "SELECT 1 FROM opriri") == []
    )


def test_opreste_client_dupa_nume_sau_id_si_apoi_efectul_asupra_tuturor_tipurilor(
    client: TestClient, bot_fals: BotFals, fabrica_conturi: Fabrica, admin_engine: Engine
) -> None:
    a = fabrica_conturi(Rol.CLIENT_TITULAR)
    b = fabrica_conturi(Rol.CLIENT_TITULAR)
    nume_a = randuri(admin_engine, "SELECT nume FROM clienti WHERE id = :i", i=a.tenant_id)[0]["nume"]
    trimite(client, f"/opreste_client {nume_a.lower()}")  # fără diferență între litere mari și mici
    assert oprit(Oprire.CLIENT, a.tenant_id) and not oprit(Oprire.CLIENT, b.tenant_id)
    assert oprit(Oprire.PUBLICARE, a.tenant_id) and not oprit(
        Oprire.PUBLICARE, b.tenant_id
    )  # oprirea pe client le oprește pe toate
    assert not oprit(Oprire.PUBLICARE)  # fără client: global rămâne neoprit
    trimite(client, f"/opreste_client {b.tenant_id}")
    assert oprit(Oprire.CLIENT, b.tenant_id)
    a_ = randuri(
        admin_engine,
        "SELECT * FROM jurnal_audit WHERE actiune = 'oprire.oprit' AND tenant_id = :t",
        t=a.tenant_id,
    )
    assert len(a_) == 1 and a_[0]["detalii"]["canal"] == "telegram"


@pytest.mark.parametrize("arg", ["", "nu exista nicio firma", "00000000-0000-4000-8000-000000000000"])
def test_opreste_client_necunoscut_nu_schimba_nimic(
    client: TestClient, bot_fals: BotFals, admin_engine: Engine, arg: str
) -> None:
    trimite(client, f"/opreste_client {arg}")
    assert randuri(admin_engine, "SELECT 1 FROM opriri") == []
    assert bot_fals.mesaje()


# ---- repornirea cere confirmare --------------------------------------------------------------------------


def cod_din(bot: BotFals) -> str:
    return bot.mesaje()[-1].split("/confirma ")[1].split()[0]


def test_repornirea_nu_porneste_fara_confirmare_si_cere_codul(client: TestClient, bot_fals: BotFals) -> None:
    trimite(client, "/opreste publicare")
    trimite(client, "/porneste publicare")
    assert oprit(Oprire.PUBLICARE), "cererea de repornire singură nu are voie să pornească"
    mesaj = bot_fals.mesaje()[-1]
    cod = cod_din(bot_fals)
    assert len(cod) == 6 and cod.isdigit() and "5 minute" in mesaj
    trimite(client, f"/confirma {cod}")
    assert not oprit(Oprire.PUBLICARE) and "Repornit" in bot_fals.mesaje()[-1]


def test_cod_gresit_anuleaza_cererea_iar_codul_bun_e_de_unica_folosinta(
    client: TestClient, bot_fals: BotFals, admin_engine: Engine
) -> None:
    trimite(client, "/opreste reclame")
    trimite(client, "/porneste reclame")
    cod = cod_din(bot_fals)
    gresit = "000000" if cod != "000000" else "111111"
    trimite(client, f"/confirma {gresit}")
    assert oprit(Oprire.RECLAME) and bot_fals.mesaje()[-1].startswith("Cod greșit.")
    assert randuri(admin_engine, "SELECT 1 FROM jurnal_audit WHERE actiune = 'telegram.confirmare_gresita'")
    trimite(client, f"/confirma {cod}")  # o singură încercare: după un cod greșit, nici cel bun nu mai merge
    assert oprit(Oprire.RECLAME) and "Nu există nicio repornire în așteptare" in bot_fals.mesaje()[-1]
    trimite(client, "/porneste reclame")
    cod = cod_din(bot_fals)
    trimite(client, f"/confirma {cod}")
    assert not oprit(Oprire.RECLAME)
    trimite(client, "/opreste reclame")
    trimite(client, f"/confirma {cod}")  # același cod a doua oară: de unică folosință
    assert oprit(Oprire.RECLAME) and "Nu există nicio repornire în așteptare" in bot_fals.mesaje()[-1]


def test_codul_expirat_nu_porneste(client: TestClient, bot_fals: BotFals, admin_engine: Engine) -> None:
    trimite(client, "/opreste publicare")
    trimite(client, "/porneste publicare")
    cod = cod_din(bot_fals)
    with admin_engine.begin() as c:
        c.execute(text("UPDATE telegram_confirmari SET expira_la = now() - interval '1 minute'"))
    trimite(client, f"/confirma {cod}")
    assert oprit(Oprire.PUBLICARE) and "expirat" in bot_fals.mesaje()[-1]


def test_codul_se_pastreaza_doar_ca_hash_si_o_noua_cerere_il_inlocuieste(
    client: TestClient, bot_fals: BotFals, admin_engine: Engine
) -> None:
    trimite(client, "/opreste publicare")
    trimite(client, "/porneste publicare")
    primul = cod_din(bot_fals)
    rand = randuri(admin_engine, "SELECT * FROM telegram_confirmari")[0]
    assert len(rand["cod_hash"]) == 32 and primul.encode() not in bytes(rand["cod_hash"])
    trimite(client, "/porneste publicare")
    al_doilea = cod_din(bot_fals)
    assert len(randuri(admin_engine, "SELECT 1 FROM telegram_confirmari")) == 1
    if al_doilea != primul:
        trimite(client, f"/confirma {primul}")
        assert oprit(Oprire.PUBLICARE)  # codul vechi nu mai e valabil
        # codul greșit a anulat și cererea a doua (o singură încercare)
        trimite(client, f"/confirma {al_doilea}")
        assert oprit(Oprire.PUBLICARE)
        trimite(client, "/porneste publicare")
        al_doilea = cod_din(bot_fals)
    trimite(client, f"/confirma {al_doilea}")
    assert not oprit(Oprire.PUBLICARE)


def test_repornirea_unui_client_cere_si_ea_confirmare(
    client: TestClient, bot_fals: BotFals, fabrica_conturi: Fabrica
) -> None:
    a = fabrica_conturi(Rol.CLIENT_TITULAR)
    trimite(client, f"/opreste_client {a.tenant_id}")
    trimite(client, f"/porneste_client {a.tenant_id}")
    assert oprit(Oprire.CLIENT, a.tenant_id)
    trimite(client, f"/confirma {cod_din(bot_fals)}")
    assert not oprit(Oprire.CLIENT, a.tenant_id)


def test_confirma_fara_cerere_sau_fara_cod(client: TestClient, bot_fals: BotFals) -> None:
    trimite(client, "/confirma")
    trimite(client, "/confirma 123456")
    assert all("Nu există nicio repornire în așteptare" in m for m in bot_fals.mesaje())


# ---- alerte de ieșire și robustețe -----------------------------------------------------------------------


def test_alerta_critica_ajunge_in_conversatia_proprietarului(bot_fals: BotFals) -> None:
    assert alerte.trimite("critic", "Cheltuială anormală", "Plafonul zilnic a fost depășit.") is True
    (req,) = bot_fals.cereri
    import json

    corp = json.loads(req.content)
    assert (
        corp["chat_id"] == int(CHAT)
        and corp["text"] == "[CRITIC] Cheltuială anormală\nPlafonul zilnic a fost depășit."
    )


def test_telegram_cazut_nu_strica_apelantul_nici_webhook_ul(
    client: TestClient, bot_fals: BotFals, admin_engine: Engine
) -> None:
    bot_fals.status, bot_fals.corp = 500, {"ok": False, "error_code": 500, "description": "Internal"}
    assert alerte.trimite("critic", "t", "x") is False
    r = trimite(client, "/opreste publicare")  # comanda se execută chiar dacă răspunsul nu poate pleca
    assert r.status_code == 200 and oprit(Oprire.PUBLICARE)


def test_alerta_cu_exceptie_neasteptata_nu_se_propaga(
    monkeypatch: pytest.MonkeyPatch, bot_fals: BotFals
) -> None:
    def explodeaza(self: object, chat_id: int, text_: str) -> int:
        raise RuntimeError("neașteptat")

    monkeypatch.setattr("app.connectors.telegram.TelegramClient.send_message", explodeaza)
    assert alerte.trimite("critic", "t", "x") is False


def test_stergerea_actualizarilor_vechi(client: TestClient, bot_fals: BotFals, admin_engine: Engine) -> None:
    with admin_engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO telegram_actualizari (update_id, primit_la) VALUES (1, now() - interval '10 days')"
            )
        )
    trimite(client, "/ajutor")
    assert randuri(admin_engine, "SELECT 1 FROM telegram_actualizari WHERE update_id = 1") == []
