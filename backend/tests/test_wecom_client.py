import json

import httpx

from services.wecom_client import WeComClient


async def test_wecom_client_get_access_token_uses_corpid_and_secret():
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"errcode": 0, "errmsg": "ok", "access_token": "token-123", "expires_in": 7200})

    client = WeComClient(
        corp_id="wwcorp",
        secret="kf-secret",
        base_url="https://example.test/cgi-bin",
        transport=httpx.MockTransport(handler),
    )

    token = await client.get_access_token()

    assert token == "token-123"
    assert len(requests) == 1
    assert requests[0].url.path == "/cgi-bin/gettoken"
    assert requests[0].url.params["corpid"] == "wwcorp"
    assert requests[0].url.params["corpsecret"] == "kf-secret"


async def test_wecom_client_sync_and_send_use_expected_payloads():
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/kf/sync_msg"):
            return httpx.Response(
                200,
                json={
                    "errcode": 0,
                    "errmsg": "ok",
                    "next_cursor": "cursor-2",
                    "has_more": 0,
                    "msg_list": [],
                },
            )
        return httpx.Response(200, json={"errcode": 0, "errmsg": "ok"})

    client = WeComClient(
        corp_id="wwcorp",
        secret="kf-secret",
        base_url="https://example.test/cgi-bin",
        transport=httpx.MockTransport(handler),
    )
    client._access_token = "token-123"
    client._access_token_expires_at = 9999999999

    sync_response = await client.sync_messages(sync_token="sync-token-1", open_kfid="kfid-1", cursor="cursor-1")
    send_response = await client.send_text_message(touser="external-1", open_kfid="kfid-1", content="1")

    assert sync_response["next_cursor"] == "cursor-2"
    assert send_response["errcode"] == 0

    assert len(requests) == 2
    assert requests[0].url.path == "/cgi-bin/kf/sync_msg"
    assert requests[0].url.params["access_token"] == "token-123"
    assert json.loads(requests[0].read().decode("utf-8")) == {
        "cursor": "cursor-1",
        "token": "sync-token-1",
        "limit": 1000,
        "voice_format": 0,
        "open_kfid": "kfid-1",
    }

    assert requests[1].url.path == "/cgi-bin/kf/send_msg"
    assert requests[1].url.params["access_token"] == "token-123"
    assert json.loads(requests[1].read().decode("utf-8")) == {
        "touser": "external-1",
        "open_kfid": "kfid-1",
        "msgtype": "text",
        "text": {"content": "1"},
    }
