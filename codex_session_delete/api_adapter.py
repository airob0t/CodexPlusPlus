from __future__ import annotations

import json
from typing import Protocol
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from codex_session_delete.models import DeleteResult, DeleteStatus, SessionRef


class ApiAdapter(Protocol):
    def delete(self, session: SessionRef) -> DeleteResult | None: ...


class UnavailableApiAdapter:
    def delete(self, session: SessionRef) -> DeleteResult | None:
        return None


class ConfirmedHttpDeleteAdapter:
    def __init__(self, delete_url: str):
        self.delete_url = delete_url

    def delete(self, session: SessionRef) -> DeleteResult | None:
        request = Request(
            self.delete_url,
            data=json.dumps({"session_id": session.session_id, "title": session.title}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=5):
                pass
        except HTTPError as exc:
            if exc.code == 404:
                return None
            raise
        return DeleteResult(
            DeleteStatus.SERVER_DELETED,
            session.session_id,
            "已通过服务器接口删除",
        )
