from __future__ import annotations

import base64
import hashlib
import hmac


class RoomTokenSigner:
    def __init__(self, secret: str) -> None:
        if len(secret) < 16:
            raise ValueError("room token secret must be at least 16 characters")
        self._secret = secret.encode("utf-8")

    def issue(self, application_id: str) -> str:
        digest = hmac.new(self._secret, application_id.encode("utf-8"), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    def verify(self, application_id: str, token: str) -> bool:
        if not token:
            return False
        return hmac.compare_digest(self.issue(application_id), token)
