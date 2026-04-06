import time
from typing import Any

import httpx


class WeComClient:
    def __init__(
        self,
        *,
        corp_id: str,
        secret: str,
        base_url: str = "https://qyapi.weixin.qq.com/cgi-bin",
        timeout: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.corp_id = corp_id
        self.secret = secret
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.transport = transport
        self._access_token: str | None = None
        self._access_token_expires_at = 0.0

    async def get_access_token(self) -> str:
        if self._access_token and time.time() < self._access_token_expires_at - 60:
            return self._access_token

        async with self._http_client() as client:
            response = await client.get(
                "/gettoken",
                params={"corpid": self.corp_id, "corpsecret": self.secret},
            )
        data = self._parse_response(response)
        access_token = data["access_token"]
        expires_in = int(data.get("expires_in", 7200))
        self._access_token = access_token
        self._access_token_expires_at = time.time() + expires_in
        return access_token

    async def sync_messages(self, *, sync_token: str, open_kfid: str, cursor: str | None = None) -> dict[str, Any]:
        access_token = await self.get_access_token()
        payload = {
            "cursor": cursor or "",
            "token": sync_token,
            "limit": 1000,
            "voice_format": 0,
            "open_kfid": open_kfid,
        }
        async with self._http_client() as client:
            response = await client.post(
                "/kf/sync_msg",
                params={"access_token": access_token},
                json=payload,
            )
        return self._parse_response(response)

    async def send_text_message(self, *, touser: str, open_kfid: str, content: str) -> dict[str, Any]:
        access_token = await self.get_access_token()
        payload = {
            "touser": touser,
            "open_kfid": open_kfid,
            "msgtype": "text",
            "text": {"content": content},
        }
        async with self._http_client() as client:
            response = await client.post(
                "/kf/send_msg",
                params={"access_token": access_token},
                json=payload,
            )
        return self._parse_response(response)

    def _http_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            transport=self.transport,
        )

    @staticmethod
    def _parse_response(response: httpx.Response) -> dict[str, Any]:
        response.raise_for_status()
        data = response.json()
        errcode = int(data.get("errcode", 0))
        if errcode != 0:
            raise RuntimeError(f"WeCom API error {errcode}: {data.get('errmsg', 'unknown error')}")
        return data
