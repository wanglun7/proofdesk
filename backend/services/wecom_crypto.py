import base64
import hashlib
import struct
from xml.etree import ElementTree

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from fastapi import HTTPException


def verify_signature(token: str, timestamp: str, nonce: str, encrypted: str, signature: str) -> bool:
    payload = "".join(sorted([token, timestamp, nonce, encrypted]))
    expected = hashlib.sha1(payload.encode("utf-8")).hexdigest()
    return expected == signature


def decrypt_message(aes_key: str, encrypted: str) -> str:
    key = base64.b64decode(f"{aes_key}=")
    ciphertext = base64.b64decode(encrypted)
    cipher = Cipher(algorithms.AES(key), modes.CBC(key[:16]))
    decryptor = cipher.decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    payload = _unpad_wecom_payload(padded)

    msg_len = struct.unpack(">I", payload[16:20])[0]
    message = payload[20 : 20 + msg_len]
    return message.decode("utf-8")


def _unpad_wecom_payload(padded: bytes) -> bytes:
    # WeCom/WeChat callback crypto uses PKCS#7 with a 32-byte block size.
    # Some test fixtures may still use a 16-byte block size, so accept both.
    if not padded:
        raise ValueError("Empty decrypted payload")

    pad_len = padded[-1]
    if pad_len < 1 or pad_len > 32:
        raise ValueError("Invalid padding bytes")

    suffix = padded[-pad_len:]
    if suffix != bytes([pad_len]) * pad_len:
        raise ValueError("Invalid padding bytes")
    return padded[:-pad_len]


def extract_encrypted_message(xml_body: bytes) -> str:
    try:
        root = ElementTree.fromstring(xml_body)
    except ElementTree.ParseError as exc:
        raise HTTPException(400, "Invalid WeCom XML payload") from exc

    encrypted = root.findtext("Encrypt")
    if not encrypted:
        raise HTTPException(400, "Missing Encrypt field")
    return encrypted
