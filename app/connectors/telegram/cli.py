"""Gestiunea webhook-ului. Nu rulează automat:

python -m app.connectors.telegram.cli seteaza-webhook --url https://app.exemplu.ro/telegram/webhook
python -m app.connectors.telegram.cli info
python -m app.connectors.telegram.cli sterge-webhook
"""

import argparse
import sys

from app.config import get_settings
from app.connectors.telegram.client import TelegramClient, TelegramEroare


def main(argv: list[str] | None = None, client: TelegramClient | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m app.connectors.telegram.cli", description=__doc__)
    sub = p.add_subparsers(dest="comanda", required=True)
    sub.add_parser("info", help="arată starea webhook-ului")
    sub.add_parser("sterge-webhook", help="oprește primirea prin webhook")
    sw = sub.add_parser("seteaza-webhook", help="înregistrează adresa webhook-ului la Telegram")
    sw.add_argument(
        "--url", required=True, help="adresa publică HTTPS, de ex. https://app.exemplu.ro/telegram/webhook"
    )
    args = p.parse_args(argv)

    s = get_settings()
    if client is None:
        if not s.telegram_bot_token.get_secret_value():
            print("AMA_TELEGRAM_BOT_TOKEN nu este setat.", file=sys.stderr)
            return 2
        client = TelegramClient(s.telegram_bot_token.get_secret_value())
    try:
        if args.comanda == "info":
            info = client.get_webhook_info()
            print(f"url: {info.get('url') or '(niciunul)'}")
            print(f"actualizări în așteptare: {info.get('pending_update_count', 0)}")
            if info.get("last_error_message"):
                print(f"ultima eroare: {info['last_error_message']}")
        elif args.comanda == "sterge-webhook":
            client.delete_webhook()
            print("Webhook șters.")
        else:
            secret = s.telegram_webhook_secret.get_secret_value()
            if not args.url.startswith("https://"):
                print("Adresa trebuie să înceapă cu https://", file=sys.stderr)
                return 2
            if len(secret) < 16:
                print("AMA_TELEGRAM_WEBHOOK_SECRET lipsește sau are sub 16 caractere.", file=sys.stderr)
                return 2
            client.set_webhook(args.url, secret)
            print("Webhook înregistrat.")
    except TelegramEroare as exc:
        print(f"Telegram a refuzat: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
