import base64
import hashlib
import os
import struct
from types import SimpleNamespace

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from httpx import ASGITransport, AsyncClient

from main import app
from services.wecom_crypto import decrypt_message


def _encrypt_message(*, aes_key: str, plaintext: str, receive_id: str = "proofdesk") -> str:
    key = base64.b64decode(f"{aes_key}=")
    random_prefix = os.urandom(16)
    payload = random_prefix + struct.pack(">I", len(plaintext.encode("utf-8"))) + plaintext.encode("utf-8") + receive_id.encode(
        "utf-8"
    )

    block_size = 32
    pad_len = block_size - (len(payload) % block_size)
    padded = payload + bytes([pad_len]) * pad_len

    cipher = Cipher(algorithms.AES(key), modes.CBC(key[:16]))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(ciphertext).decode("utf-8")


def _signature(*, token: str, timestamp: str, nonce: str, encrypted: str) -> str:
    joined = "".join(sorted([token, timestamp, nonce, encrypted]))
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()


async def test_wecom_callback_get_returns_decrypted_echo(monkeypatch):
    token = "drizJYNAB2MUvAg"
    aes_key = "SDyAgekIfeqWB1tdrFtNH3C1cxhdkbvUslMIguQ31pn"
    timestamp = "1712300000"
    nonce = "nonce-123"
    expected_echo = "proofdesk-wecom-ok"
    encrypted_echo = _encrypt_message(aes_key=aes_key, plaintext=expected_echo)
    signature = _signature(token=token, timestamp=timestamp, nonce=nonce, encrypted=encrypted_echo)

    monkeypatch.setattr("config.settings.wecom_kf_token", token)
    monkeypatch.setattr("config.settings.wecom_kf_encoding_aes_key", aes_key)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/api/wecom/kf/callback",
            params={
                "msg_signature": signature,
                "timestamp": timestamp,
                "nonce": nonce,
                "echostr": encrypted_echo,
            },
        )

    assert response.status_code == 200
    assert response.text == expected_echo


async def test_wecom_callback_get_rejects_invalid_signature(monkeypatch):
    monkeypatch.setattr("config.settings.wecom_kf_token", "drizJYNAB2MUvAg")
    monkeypatch.setattr(
        "config.settings.wecom_kf_encoding_aes_key",
        "SDyAgekIfeqWB1tdrFtNH3C1cxhdkbvUslMIguQ31pn",
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/api/wecom/kf/callback",
            params={
                "msg_signature": "bad-signature",
                "timestamp": "1712300000",
                "nonce": "nonce-123",
                "echostr": "bad-echostr",
            },
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid WeCom signature"


def test_wecom_crypto_round_trip_decrypts_event_xml():
    aes_key = "SDyAgekIfeqWB1tdrFtNH3C1cxhdkbvUslMIguQ31pn"
    plaintext = "<xml><MsgType><![CDATA[text]]></MsgType><Content><![CDATA[hello proofdesk]]></Content></xml>"
    encrypted = _encrypt_message(aes_key=aes_key, plaintext=plaintext)

    assert decrypt_message(aes_key, encrypted) == plaintext


async def test_wecom_callback_post_decrypts_event_and_returns_success(monkeypatch):
    token = "drizJYNAB2MUvAg"
    aes_key = "SDyAgekIfeqWB1tdrFtNH3C1cxhdkbvUslMIguQ31pn"
    timestamp = "1712300000"
    nonce = "nonce-123"
    plaintext = (
        "<xml>"
        "<ToUserName><![CDATA[wwcorp]]></ToUserName>"
        "<FromUserName><![CDATA[external-user]]></FromUserName>"
        "<CreateTime>1712300000</CreateTime>"
        "<MsgType><![CDATA[text]]></MsgType>"
        "<Content><![CDATA[hello proofdesk]]></Content>"
        "<MsgId>1234567890</MsgId>"
        "<OpenKfId><![CDATA[kfid_test]]></OpenKfId>"
        "</xml>"
    )
    encrypted = _encrypt_message(aes_key=aes_key, plaintext=plaintext)
    signature = _signature(token=token, timestamp=timestamp, nonce=nonce, encrypted=encrypted)

    monkeypatch.setattr("config.settings.wecom_kf_token", token)
    monkeypatch.setattr("config.settings.wecom_kf_encoding_aes_key", aes_key)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/wecom/kf/callback",
            params={
                "msg_signature": signature,
                "timestamp": timestamp,
                "nonce": nonce,
            },
            content=f"<xml><Encrypt><![CDATA[{encrypted}]]></Encrypt></xml>",
            headers={"Content-Type": "application/xml"},
        )

    assert response.status_code == 200
    assert response.text == "success"


async def test_wecom_callback_post_syncs_text_and_replies_with_same_content(monkeypatch):
    token = "drizJYNAB2MUvAg"
    aes_key = "SDyAgekIfeqWB1tdrFtNH3C1cxhdkbvUslMIguQ31pn"
    timestamp = "1712300000"
    nonce = "nonce-123"
    plaintext = (
        "<xml>"
        "<ToUserName><![CDATA[wwcorp]]></ToUserName>"
        "<CreateTime>1712300000</CreateTime>"
        "<MsgType><![CDATA[event]]></MsgType>"
        "<Event><![CDATA[kf_msg_or_event]]></Event>"
        "<Token><![CDATA[sync-token-1]]></Token>"
        "<OpenKfId><![CDATA[kfid_test]]></OpenKfId>"
        "</xml>"
    )
    encrypted = _encrypt_message(aes_key=aes_key, plaintext=plaintext)
    signature = _signature(token=token, timestamp=timestamp, nonce=nonce, encrypted=encrypted)

    monkeypatch.setattr("config.settings.wecom_kf_token", token)
    monkeypatch.setattr("config.settings.wecom_kf_encoding_aes_key", aes_key)
    monkeypatch.setattr("config.settings.wecom_corp_id", "wwcorp")
    monkeypatch.setattr("config.settings.wecom_kf_secret", "kf-secret")

    calls: list[tuple[str, ...]] = []

    class FakeWeComClient:
        async def sync_messages(self, *, sync_token: str, open_kfid: str, cursor: str | None = None):
            calls.append(("sync", sync_token, open_kfid, cursor or ""))
            return {
                "next_cursor": "cursor-2",
                "has_more": 0,
                "msg_list": [
                    {
                        "msgid": "msg-1",
                        "msgtype": "text",
                        "origin": 3,
                        "external_userid": "external-user-1",
                        "text": {"content": "1"},
                    }
                ],
            }

        async def send_text_message(self, *, touser: str, open_kfid: str, content: str):
            calls.append(("send", touser, open_kfid, content))
            return {"errcode": 0, "errmsg": "ok"}

    monkeypatch.setattr("api.wecom.get_wecom_client", lambda: FakeWeComClient())
    monkeypatch.setattr("api.wecom.wecom_runtime", SimpleNamespace(cursors={}, processed_message_ids=set()))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/wecom/kf/callback",
            params={
                "msg_signature": signature,
                "timestamp": timestamp,
                "nonce": nonce,
            },
            content=f"<xml><Encrypt><![CDATA[{encrypted}]]></Encrypt></xml>",
            headers={"Content-Type": "application/xml"},
        )

    assert response.status_code == 200
    assert response.text == "success"
    assert calls == [
        ("sync", "sync-token-1", "kfid_test", ""),
        ("send", "external-user-1", "kfid_test", "1"),
    ]
