#!/usr/bin/env python3
"""Generează o pereche de chei VAPID (P-256) pentru Web Push. Rulează o dată; cheia privată este secret.

    uv run python scripts/genereaza_vapid.py

Scrie pe ecran variabilele de mediu de pus în fișierul de mediu al producției (nu în repo):
AMA_VAPID_PUBLIC_KEY (se dă și paginii) și AMA_VAPID_PRIVATE_KEY (rămâne pe server).
"""

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def b64url(octeti: bytes) -> str:
    return base64.urlsafe_b64encode(octeti).rstrip(b"=").decode()


def main() -> None:
    cheie = ec.generate_private_key(ec.SECP256R1())
    privata = cheie.private_numbers().private_value.to_bytes(32, "big")
    publica = cheie.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    print(f"AMA_VAPID_PUBLIC_KEY={b64url(publica)}")
    print(f"AMA_VAPID_PRIVATE_KEY={b64url(privata)}")
    print("AMA_VAPID_SUBJECT=mailto:adresa-ta@exemplu.ro")


if __name__ == "__main__":
    main()
