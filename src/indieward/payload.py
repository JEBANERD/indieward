"""IW-Mark v1 payload: 40-bit record ID + 24-bit MAC = 64 bits.

The record ID is random and points to an asset record in the creator's vault
(and in their signed certificate). The MAC is HMAC-SHA256 under the creator's
private MAC key, truncated to 24 bits. Anyone can read the ID from a mark;
only the key holder can confirm it's genuine. A forger guessing a valid
ID+MAC pair succeeds about 1 time in 16.7 million per try.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

ID_BITS = 40
MAC_BITS = 24


def new_record_id() -> int:
    return secrets.randbits(ID_BITS)


def mac24(mac_key: bytes, record_id: int) -> int:
    msg = b"IW-Mark v1|" + record_id.to_bytes(5, "big")
    return int.from_bytes(hmac.new(mac_key, msg, hashlib.sha256).digest()[:3], "big")


def make(mac_key: bytes, record_id: int) -> int:
    return (record_id << MAC_BITS) | mac24(mac_key, record_id)


def split(payload: int) -> tuple[int, int]:
    return payload >> MAC_BITS, payload & ((1 << MAC_BITS) - 1)


def is_genuine(mac_key: bytes, payload: int) -> bool:
    rid, tag = split(payload)
    return hmac.compare_digest(mac24(mac_key, rid).to_bytes(3, "big"), tag.to_bytes(3, "big"))


def fmt(record_id: int) -> str:
    h = f"{record_id:010x}"
    return f"IW1-{h[:5]}-{h[5:]}"
