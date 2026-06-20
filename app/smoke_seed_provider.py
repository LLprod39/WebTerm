from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SmokeSshTarget:
    host: str
    port: int
    username: str
    password: str


@dataclass(frozen=True)
class SmokeSeedItem:
    id: int
    name: str


class SmokeServerSeedProvider(Protocol):
    def upsert_server(self, *, user_id: int, index: int, target: SmokeSshTarget) -> SmokeSeedItem: ...

    def upsert_agent(self, *, user_id: int, index: int, username: str, server_id: int) -> SmokeSeedItem: ...


class SmokePipelineSeedProvider(Protocol):
    def upsert_pipeline(self, *, user_id: int, index: int, server_id: int) -> SmokeSeedItem: ...


_server_seed_provider: SmokeServerSeedProvider | None = None
_pipeline_seed_provider: SmokePipelineSeedProvider | None = None


def register_smoke_server_seed_provider(provider: SmokeServerSeedProvider | None) -> None:
    global _server_seed_provider
    _server_seed_provider = provider


def register_smoke_pipeline_seed_provider(provider: SmokePipelineSeedProvider | None) -> None:
    global _pipeline_seed_provider
    _pipeline_seed_provider = provider


def upsert_smoke_server(*, user_id: int, index: int, target: SmokeSshTarget) -> SmokeSeedItem:
    if _server_seed_provider is None:
        raise RuntimeError("Smoke server seed provider is not registered")
    return _server_seed_provider.upsert_server(user_id=user_id, index=index, target=target)


def upsert_smoke_agent(*, user_id: int, index: int, username: str, server_id: int) -> SmokeSeedItem:
    if _server_seed_provider is None:
        raise RuntimeError("Smoke server seed provider is not registered")
    return _server_seed_provider.upsert_agent(user_id=user_id, index=index, username=username, server_id=server_id)


def upsert_smoke_pipeline(*, user_id: int, index: int, server_id: int) -> SmokeSeedItem:
    if _pipeline_seed_provider is None:
        raise RuntimeError("Smoke pipeline seed provider is not registered")
    return _pipeline_seed_provider.upsert_pipeline(user_id=user_id, index=index, server_id=server_id)
