"""Identificatori unici, ordonați în timp, generați de aplicație (UUIDv7, RFC 9562)."""

import os
import time
import uuid


def new_id() -> uuid.UUID:
    ms = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10), "big")
    value = (ms & 0xFFFFFFFFFFFF) << 80
    value |= 0x7 << 76  # versiunea 7
    value |= ((rand >> 68) & 0xFFF) << 64  # rand_a, 12 biți
    value |= 0b10 << 62  # varianta RFC
    value |= rand & 0x3FFFFFFFFFFFFFFF  # rand_b, 62 de biți
    return uuid.UUID(int=value)
