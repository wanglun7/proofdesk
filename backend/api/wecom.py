import asyncio
import logging
import time
from xml.etree import ElementTree

from fastapi import APIRouter, HTTPException, Query, Request, Response

from config import settings
from services.wecom_client import WeComClient
from services.wecom_crypto import decrypt_message, extract_encrypted_message, verify_signature

router = APIRouter()
logger = logging.getLogger(__name__)
_CUSTOMER_ORIGIN = 3
_MIN_REPLY_INTERVAL_SECONDS = 3.0
_now = time.monotonic


class WeComRuntime:
    def __init__(self):
        self.cursors: dict[str, str] = {}
        self.processed_message_ids: set[str] = set()
        self.reply_locks: dict[str, asyncio.Lock] = {}
        self.last_reply_sent_at: dict[str, float] = {}
        self.active_tasks: set[asyncio.Task] = set()
        self.recent_send_attempts: dict[str, dict] = {}


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


def _content_preview(content: str | None, limit: int = 80) -> str | None:
    if content is None:
        return None
    cleaned = content.replace("\n", "\\n")
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit]}..."


def _message_debug_summary(message: dict) -> dict:
    text = message.get("text") or {}
    event = message.get("event") or {}
    summary = {
        "msgid": message.get("msgid"),
        "msgtype": message.get("msgtype"),
        "origin": message.get("origin"),
        "send_time": message.get("send_time"),
        "external_userid": message.get("external_userid"),
        "servicer_userid": message.get("servicer_userid"),
        "open_kfid": message.get("open_kfid"),
        "has_text": bool(isinstance(text.get("content"), str) and text.get("content").strip()),
        "text_preview": _content_preview(text.get("content")),
        "event_type": event.get("event_type"),
        "fail_type": event.get("fail_type"),
        "origin_msgid": event.get("origin_msgid"),
    }
    return {key: value for key, value in summary.items() if value not in (None, "", False)}


def _skip_reason(message: dict) -> str:
    msgtype = message.get("msgtype")
    if msgtype != "text":
        return f"unsupported_msgtype:{msgtype}"
    origin = message.get("origin")
    if origin != _CUSTOMER_ORIGIN:
        return f"non_customer_origin:{origin}"
    if not message.get("external_userid"):
        return "missing_external_userid"

    text = message.get("text") or {}
    content = text.get("content")
    if not isinstance(content, str) or not content.strip():
        return "empty_text_content"
    return "not_selected"


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


def _remember_send_attempt(send_msgid: str | None, details: dict) -> None:
    if not send_msgid:
        return
    wecom_runtime.recent_send_attempts[send_msgid] = details
    if len(wecom_runtime.recent_send_attempts) > 2000:
        wecom_runtime.recent_send_attempts.clear()


def _get_reply_lock(open_kfid: str) -> asyncio.Lock:
    lock = wecom_runtime.reply_locks.get(open_kfid)
    if lock is None:
        lock = asyncio.Lock()
        wecom_runtime.reply_locks[open_kfid] = lock
    return lock


def _schedule_customer_service_sync(*, sync_token: str, open_kfid: str) -> None:
    task = asyncio.create_task(_run_customer_service_sync(sync_token=sync_token, open_kfid=open_kfid))
    wecom_runtime.active_tasks.add(task)

    def _cleanup(done_task: asyncio.Task) -> None:
        wecom_runtime.active_tasks.discard(done_task)
        try:
            done_task.result()
        except Exception:
            logger.exception("WeCom background sync task failed: open_kfid=%s", open_kfid)

    task.add_done_callback(_cleanup)


async def _run_customer_service_sync(*, sync_token: str, open_kfid: str) -> None:
    lock = _get_reply_lock(open_kfid)
    async with lock:
        client = get_wecom_client()
        await _process_sync_batch(client=client, sync_token=sync_token, open_kfid=open_kfid)


async def _process_sync_batch(*, client: WeComClient, sync_token: str, open_kfid: str) -> None:
    cursor_key = open_kfid
    cursor = wecom_runtime.cursors.get(cursor_key)
    latest_candidate: dict | None = None
    total_messages = 0

    while True:
        payload = await client.sync_messages(sync_token=sync_token, open_kfid=open_kfid, cursor=cursor)
        messages = payload.get("msg_list", [])
        total_messages += len(messages)
        next_cursor = payload.get("next_cursor") or cursor or ""
        logger.info(
            "WeCom sync batch: open_kfid=%s cursor_in=%s cursor_out=%s message_count=%s has_more=%s",
            open_kfid,
            cursor or "",
            next_cursor,
            len(messages),
            payload.get("has_more"),
        )

        for message in messages:
            msgid = str(message.get("msgid") or "")
            logger.info("WeCom sync item: open_kfid=%s details=%s", open_kfid, _message_debug_summary(message))
            event = message.get("event") or {}
            if event.get("event_type") == "msg_send_fail":
                related = wecom_runtime.recent_send_attempts.get(str(event.get("origin_msgid") or ""))
                logger.warning(
                    "WeCom send fail event: open_kfid=%s msgid=%s fail_type=%s origin_msgid=%s related_attempt=%s",
                    open_kfid,
                    msgid,
                    event.get("fail_type"),
                    event.get("origin_msgid"),
                    related,
                )
            if msgid and msgid in wecom_runtime.processed_message_ids:
                logger.info("WeCom sync item skipped duplicate: open_kfid=%s msgid=%s", open_kfid, msgid)
                continue

            if _should_echo_message(message):
                latest_candidate = message
                logger.info(
                    "WeCom sync item selected candidate: open_kfid=%s msgid=%s content=%r",
                    open_kfid,
                    msgid,
                    message["text"]["content"].strip(),
                )
            else:
                logger.info(
                    "WeCom sync item skipped: open_kfid=%s msgid=%s skip_reason=%s",
                    open_kfid,
                    msgid,
                    _skip_reason(message),
                )

            if msgid:
                _remember_processed_message(msgid)

        wecom_runtime.cursors[cursor_key] = next_cursor
        cursor = next_cursor
        if payload.get("has_more") not in (1, True, "1"):
            break

    if latest_candidate is None:
        logger.info("WeCom sync finished: open_kfid=%s total_messages=%s latest_reply=none", open_kfid, total_messages)
        return

    content = latest_candidate["text"]["content"].strip()
    msgid = str(latest_candidate.get("msgid") or "")
    last_sent_at = wecom_runtime.last_reply_sent_at.get(open_kfid)
    now = _now()
    if last_sent_at is not None and now - last_sent_at < _MIN_REPLY_INTERVAL_SECONDS:
        logger.warning(
            "WeCom reply throttled: open_kfid=%s msgid=%s content=%r last_sent_delta=%.3f",
            open_kfid,
            msgid,
            content,
            now - last_sent_at,
        )
        return

    logger.info(
        "WeCom sync finished: open_kfid=%s total_messages=%s latest_reply_msgid=%s content=%r",
        open_kfid,
        total_messages,
        msgid,
        content,
    )
    logger.info(
        "WeCom send request: open_kfid=%s reply_to_msgid=%s touser=%s content=%r",
        open_kfid,
        msgid,
        latest_candidate["external_userid"],
        content,
    )
    send_response = await client.send_text_message(
        touser=latest_candidate["external_userid"],
        open_kfid=open_kfid,
        content=content,
    )
    send_msgid = str(send_response.get("msgid") or "")
    logger.info("WeCom send response: open_kfid=%s reply_to_msgid=%s response=%s", open_kfid, msgid, send_response)
    _remember_send_attempt(
        send_msgid or None,
        {
            "open_kfid": open_kfid,
            "reply_to_msgid": msgid,
            "touser": latest_candidate["external_userid"],
            "content": content,
            "response_msgid": send_msgid or None,
        },
    )
    wecom_runtime.last_reply_sent_at[open_kfid] = now
    logger.info("WeCom echo reply sent: open_kfid=%s msgid=%s content=%r", open_kfid, msgid, content)


def _handle_customer_service_event(event: ElementTree.Element) -> None:
    if _event_text(event, "MsgType") != "event":
        return
    if _event_text(event, "Event") != "kf_msg_or_event":
        return

    sync_token = _event_text(event, "Token")
    open_kfid = _event_text(event, "OpenKfId")
    if not sync_token or not open_kfid:
        logger.warning("WeCom callback missing Token/OpenKfId")
        return

    logger.info("WeCom callback accepted: open_kfid=%s sync_token=%s", open_kfid, sync_token[:8])
    _schedule_customer_service_sync(sync_token=sync_token, open_kfid=open_kfid)


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
    _handle_customer_service_event(event)
    return Response(content="success", media_type="text/plain")
