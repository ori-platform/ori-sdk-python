# Copyright 2026 Ori Nexus Systems LTD
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import json
import socket
from pathlib import Path

import pytest

from ori_sdk.health import HealthClientError, RuntimeHealthClient

FIXTURES = Path(__file__).parent / "fixtures"


class _FakeSocket:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)

    def settimeout(self, _timeout: float) -> None:
        return None

    def connect(self, _path: str) -> None:
        return None

    def sendall(self, _payload: bytes) -> None:
        return None

    def shutdown(self, _how: int) -> None:
        return None

    def recv(self, _n: int) -> bytes:
        if self._chunks:
            return self._chunks.pop(0)
        return b""

    def __enter__(self) -> _FakeSocket:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_get_health_parses_success_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.loads((FIXTURES / "runtime_health_success.json").read_text())
    raw = json.dumps(payload).encode("utf-8")
    monkeypatch.setattr(
        socket,
        "socket",
        lambda *args, **kwargs: _FakeSocket([raw]),  # type: ignore[return-value]
    )

    response = RuntimeHealthClient("/tmp/ori-health.sock").get_health()

    assert response.ok is True
    assert response.health is not None
    assert response.health.device_id == "site-a"
    assert response.health.sensors[0].id == "mains-current"


def test_get_health_parses_error_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.loads((FIXTURES / "runtime_health_error.json").read_text())
    raw = json.dumps(payload).encode("utf-8")
    monkeypatch.setattr(
        socket,
        "socket",
        lambda *args, **kwargs: _FakeSocket([raw]),  # type: ignore[return-value]
    )

    response = RuntimeHealthClient("/tmp/ori-health.sock").get_health()

    assert response.ok is False
    assert response.error is not None
    assert response.error.code == "unsupported_request"


def test_get_health_handles_connection_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _RefusingSocket(_FakeSocket):
        def __init__(self) -> None:
            super().__init__([])

        def connect(self, _path: str) -> None:
            raise ConnectionRefusedError("refused")

    monkeypatch.setattr(
        socket,
        "socket",
        lambda *args, **kwargs: _RefusingSocket(),  # type: ignore[return-value]
    )

    client = RuntimeHealthClient("/tmp/ori-health.sock")
    with pytest.raises(HealthClientError, match="refused connection"):
        client.get_health()


class _FakeAsyncReader:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)

    async def read(self, _n: int) -> bytes:
        if self._chunks:
            return self._chunks.pop(0)
        return b""


class _FakeAsyncWriter:
    def __init__(self) -> None:
        self.closed = False

    def write(self, _data: bytes) -> None:
        return None

    async def drain(self) -> None:
        return None

    def write_eof(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None


def test_aget_health_parses_success_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.loads((FIXTURES / "runtime_health_success.json").read_text())
    raw = json.dumps(payload).encode("utf-8")

    async def _open_unix_connection(_path: str):
        return _FakeAsyncReader([raw]), _FakeAsyncWriter()

    monkeypatch.setattr(asyncio, "open_unix_connection", _open_unix_connection)

    response = asyncio.run(RuntimeHealthClient("/tmp/ori-health.sock").aget_health())
    assert response.ok is True
    assert response.health is not None
    assert response.health.device_id == "site-a"


def test_aget_health_handles_connection_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _open_unix_connection(_path: str):
        raise ConnectionRefusedError("refused")

    monkeypatch.setattr(asyncio, "open_unix_connection", _open_unix_connection)

    with pytest.raises(HealthClientError, match="refused connection"):
        asyncio.run(RuntimeHealthClient("/tmp/ori-health.sock").aget_health())
