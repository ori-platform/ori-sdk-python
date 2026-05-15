# Copyright 2026 Ori Nexus Systems LTD
# SPDX-License-Identifier: Apache-2.0

"""Runtime health Unix-socket client."""

from __future__ import annotations

import asyncio
import json
import socket

from ori_sdk.errors import (
    ORI_SDK_CONNECTION_REFUSED,
    ORI_SDK_EMPTY_RESPONSE,
    ORI_SDK_INVALID_JSON,
    ORI_SDK_RESPONSE_TOO_LARGE,
    ORI_SDK_SCHEMA_MISMATCH,
    ORI_SDK_SOCKET_NOT_FOUND,
    ORI_SDK_TIMEOUT,
    HealthClientError,
)
from ori_sdk.models import HealthResponse

DEFAULT_HEALTH_SOCKET_PATH = "/run/ori/health.sock"
DEFAULT_TIMEOUT_S = 2.0
MAX_RESPONSE_BYTES = 1_048_576


class RuntimeHealthClient:
    """Client for the read-only Ori runtime health AF_UNIX endpoint."""

    def __init__(
        self,
        path: str = DEFAULT_HEALTH_SOCKET_PATH,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        if not path.strip():
            raise ValueError("path must not be empty")
        if timeout_s <= 0:
            raise ValueError("timeout_s must be > 0")
        self._path = path
        self._timeout_s = timeout_s

    @property
    def path(self) -> str:
        return self._path

    def get_health(self) -> HealthResponse:
        payload = self._request("GET_HEALTH")
        return self._decode_response(payload)

    async def aget_health(self) -> HealthResponse:
        payload = await self._arequest("GET_HEALTH")
        return self._decode_response(payload)

    def _decode_response(self, payload: bytes) -> HealthResponse:
        try:
            decoded = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HealthClientError(
                f"invalid health response payload: {exc}", code=ORI_SDK_INVALID_JSON
            ) from exc
        if not isinstance(decoded, dict):
            raise HealthClientError(
                "invalid health response: expected JSON object",
                code=ORI_SDK_INVALID_JSON,
            )
        try:
            return HealthResponse.from_dict(decoded)
        except ValueError as exc:
            raise HealthClientError(
                f"invalid health schema: {exc}", code=ORI_SDK_SCHEMA_MISMATCH
            ) from exc

    def _request(self, message: str) -> bytes:
        request_bytes = message.encode("utf-8")
        buf = bytearray()
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(self._timeout_s)
                sock.connect(self._path)
                sock.sendall(request_bytes)
                sock.shutdown(socket.SHUT_WR)
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    buf.extend(chunk)
                    if len(buf) > MAX_RESPONSE_BYTES:
                        raise HealthClientError(
                            f"health response exceeded {MAX_RESPONSE_BYTES} bytes",
                            code=ORI_SDK_RESPONSE_TOO_LARGE,
                        )
        except TimeoutError as exc:
            raise HealthClientError(
                f"health socket request timed out after {self._timeout_s}s",
                code=ORI_SDK_TIMEOUT,
            ) from exc
        except FileNotFoundError as exc:
            raise HealthClientError(
                f"health socket not found at {self._path}",
                code=ORI_SDK_SOCKET_NOT_FOUND,
            ) from exc
        except ConnectionRefusedError as exc:
            raise HealthClientError(
                f"health socket refused connection at {self._path}",
                code=ORI_SDK_CONNECTION_REFUSED,
            ) from exc
        except OSError as exc:
            raise HealthClientError(
                f"health socket request failed: {exc}", code=ORI_SDK_CONNECTION_REFUSED
            ) from exc

        if not buf:
            raise HealthClientError(
                "empty health response payload", code=ORI_SDK_EMPTY_RESPONSE
            )
        return bytes(buf)

    async def _arequest(self, message: str) -> bytes:
        request_bytes = message.encode("utf-8")
        buf = bytearray()
        try:
            async with asyncio.timeout(self._timeout_s):
                reader, writer = await asyncio.open_unix_connection(self._path)
                try:
                    writer.write(request_bytes)
                    await writer.drain()
                    writer.write_eof()
                    while True:
                        chunk = await reader.read(4096)
                        if not chunk:
                            break
                        buf.extend(chunk)
                        if len(buf) > MAX_RESPONSE_BYTES:
                            raise HealthClientError(
                                f"health response exceeded {MAX_RESPONSE_BYTES} bytes",
                                code=ORI_SDK_RESPONSE_TOO_LARGE,
                            )
                finally:
                    writer.close()
                    await writer.wait_closed()
        except TimeoutError as exc:
            raise HealthClientError(
                f"health socket request timed out after {self._timeout_s}s",
                code=ORI_SDK_TIMEOUT,
            ) from exc
        except FileNotFoundError as exc:
            raise HealthClientError(
                f"health socket not found at {self._path}",
                code=ORI_SDK_SOCKET_NOT_FOUND,
            ) from exc
        except ConnectionRefusedError as exc:
            raise HealthClientError(
                f"health socket refused connection at {self._path}",
                code=ORI_SDK_CONNECTION_REFUSED,
            ) from exc
        except OSError as exc:
            raise HealthClientError(
                f"health socket request failed: {exc}", code=ORI_SDK_CONNECTION_REFUSED
            ) from exc

        if not buf:
            raise HealthClientError(
                "empty health response payload", code=ORI_SDK_EMPTY_RESPONSE
            )
        return bytes(buf)


__all__ = [
    "DEFAULT_HEALTH_SOCKET_PATH",
    "DEFAULT_TIMEOUT_S",
    "MAX_RESPONSE_BYTES",
    "HealthClientError",
    "RuntimeHealthClient",
]
