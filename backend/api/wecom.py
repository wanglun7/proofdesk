import logging
from xml.etree import ElementTree

from fastapi import APIRouter, HTTPException, Query, Request, Response

from config import settings
from services.wecom_crypto import decrypt_message, extract_encrypted_message, verify_signature

router = APIRouter()
logger = logging.getLogger(__name__)


def _require_wecom_callback_config() -> tuple[str, str]:
    if not settings.wecom_kf_token or not settings.wecom_kf_encoding_aes_key:
        raise HTTPException(503, "WeCom callback is not configured")
    return settings.wecom_kf_token, settings.wecom_kf_encoding_aes_key


def _verify_request_signature(*, token: str, timestamp: str, nonce: str, encrypted: str, signature: str) -> None:
    if not verify_signature(token, timestamp, nonce, encrypted, signature):
        raise HTTPException(403, "Invalid WeCom signature")


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
    return Response(content="success", media_type="text/plain")
