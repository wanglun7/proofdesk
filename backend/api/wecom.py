import logging
from xml.etree import ElementTree

from fastapi import APIRouter, HTTPException, Query, Request, Response

from config import settings
from services.wecom_client import WeComClient
from services.wecom_crypto import decrypt_message, extract_encrypted_message, verify_signature

router = APIRouter()
logger = logging.getLogger(__name__)
_CUSTOMER_ORIGIN = 3


class WeComRuntime:
    def __init__(self):
        self.cursors: dict[str, str] = {}
        self.processed_message_ids: set[str] = set()


wecom_runtime = WeComRuntime()
_wecom_client: WeComClient | None = None


def _require_wecom_callback_config() -> tuple[str, str]:
    if not settings.wecom_kf_token or not settings.wecom_kf_encoding_aes_key:
        raise HTTPException(503, "WeCom callback is not configured")
    return settings.wecom_kf_token, settings.wecom_kf_encoding_aes_key


def _require_wecom_api_config() -> tuple[str, str]:
    if not settings.wecom_corp_id or not settings.wecom_kf_secret:
        raise HTTPException(503, "WeCom customer-service API is not configured")
    return settings.wecom_corp_id, settings.wecom_kf_secret


def get_wecom_client() -> WeComClient:
    global _wecom_client
    corp_id, secret = _require_wecom_api_config()
    if _wecom_client is None or _wecom_client.corp_id != corp_id or _wecom_client.secret != secret:
        _wecom_client = WeComClient(corp_id=corp_id, secret=secret)
    return _wecom_client


def _verify_request_signature(*, token: str, timestamp: str, nonce: str, encrypted: str, signature: str) -> None:
    if not verify_signature(token, timestamp, nonce, encrypted, signature):
        raise HTTPException(403, "Invalid WeCom signature")


def _event_text(event: ElementTree.Element, tag: str) -> str | None:
    value = event.findtext(tag)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _should_echo_message(message: dict) -> bool:
    if message.get("msgtype") != "text":
        return False
    if message.get("origin") != _CUSTOMER_ORIGIN:
        return False
    if not message.get("external_userid"):
        return False

    text = message.get("text") or {}
    content = text.get("content")
    return isinstance(content, str) and bool(content.strip())


def _remember_processed_message(msgid: str) -> None:
    wecom_runtime.processed_message_ids.add(msgid)
    if len(wecom_runtime.processed_message_ids) > 5000:
        wecom_runtime.processed_message_ids.clear()


async def _process_sync_batch(*, client: WeComClient, sync_token: str, open_kfid: str) -> None:
    cursor_key = open_kfid
    cursor = wecom_runtime.cursors.get(cursor_key)

    while True:
        payload = await client.sync_messages(sync_token=sync_token, open_kfid=open_kfid, cursor=cursor)
        next_cursor = payload.get("next_cursor") or cursor or ""

        for message in payload.get("msg_list", []):
            msgid = str(message.get("msgid") or "")
            if msgid and msgid in wecom_runtime.processed_message_ids:
                continue

            if _should_echo_message(message):
                content = message["text"]["content"].strip()
                await client.send_text_message(
                    touser=message["external_userid"],
                    open_kfid=open_kfid,
                    content=content,
                )
                logger.info("WeCom echo reply sent: open_kfid=%s msgid=%s content=%r", open_kfid, msgid, content)

            if msgid:
                _remember_processed_message(msgid)

        wecom_runtime.cursors[cursor_key] = next_cursor
        cursor = next_cursor
        if payload.get("has_more") not in (1, True, "1"):
            break


async def _handle_customer_service_event(event: ElementTree.Element) -> None:
    if _event_text(event, "MsgType") != "event":
        return
    if _event_text(event, "Event") != "kf_msg_or_event":
        return

    sync_token = _event_text(event, "Token")
    open_kfid = _event_text(event, "OpenKfId")
    if not sync_token or not open_kfid:
        logger.warning("WeCom callback missing Token/OpenKfId")
        return

    client = get_wecom_client()
    await _process_sync_batch(client=client, sync_token=sync_token, open_kfid=open_kfid)


@router.get("/kf/callback")
async def verify_wecom_callback(
    msg_signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
    echostr: str = Query(...),
):
    token, aes_key = _require_wecom_callback_config()
    _verify_request_signature(
        token=token,
        timestamp=timestamp,
        nonce=nonce,
        encrypted=echostr,
        signature=msg_signature,
    )
    return Response(content=decrypt_message(aes_key, echostr), media_type="text/plain")


@router.post("/kf/callback")
async def receive_wecom_callback(
    request: Request,
    msg_signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
):
    token, aes_key = _require_wecom_callback_config()
    raw_body = await request.body()
    encrypted = extract_encrypted_message(raw_body)
    _verify_request_signature(
        token=token,
        timestamp=timestamp,
        nonce=nonce,
        encrypted=encrypted,
        signature=msg_signature,
    )

    try:
        event_xml = decrypt_message(aes_key, encrypted)
    except Exception:
        logger.exception(
            "Failed to decrypt WeCom callback: body=%s encrypted_len=%s encrypted_prefix=%s",
            raw_body.decode("utf-8", errors="replace"),
            len(encrypted),
            encrypted[:48],
        )
        raise
    try:
        event = ElementTree.fromstring(event_xml)
    except ElementTree.ParseError as exc:
        raise HTTPException(400, "Invalid WeCom decrypted payload") from exc

    logger.info(
        "Received WeCom customer-service callback: msg_type=%s open_kfid=%s from_user=%s",
        event.findtext("MsgType"),
        event.findtext("OpenKfId"),
        event.findtext("FromUserName"),
    )
    try:
        await _handle_customer_service_event(event)
    except Exception:
        logger.exception("Failed to process WeCom customer-service callback")
    return Response(content="success", media_type="text/plain")
