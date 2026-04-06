import base64
import hashlib
import struct
from xml.etree import ElementTree

from cryptography.hazmat.primitives import padding
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

    unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
    payload = unpadder.update(padded) + unpadder.finalize()

    msg_len = struct.unpack(">I", payload[16:20])[0]
    message = payload[20 : 20 + msg_len]
    return message.decode("utf-8")


def extract_encrypted_message(xml_body: bytes) -> str:
    try:
        root = ElementTree.fromstring(xml_body)
    except ElementTree.ParseError as exc:
        raise HTTPException(400, "Invalid WeCom XML payload") from exc

    encrypted = root.findtext("Encrypt")
    if not encrypted:
        raise HTTPException(400, "Missing Encrypt field")
    return encrypted
