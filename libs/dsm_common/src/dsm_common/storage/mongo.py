from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from dsm_common.schemas import ClusterSnapshotDocument, StudentProfileDocument

if TYPE_CHECKING:
    from pymongo import AsyncMongoClient


class ProfileRepository(ABC):
    @abstractmethod
    async def upsert_profile(self, profile: StudentProfileDocument) -> None: ...

    @abstractmethod
    async def upsert_snapshot(self, snapshot: ClusterSnapshotDocument) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...


class MongoProfileRepository(ProfileRepository):
    def __init__(self, mongo_uri: str, database_name: str = "dsm_lms") -> None:
        self._mongo_uri = mongo_uri
        self._database_name = database_name
        self._client: AsyncMongoClient | None = None
        self._client_lock = asyncio.Lock()

    async def _get_client(self) -> AsyncMongoClient:
        if self._client is None:
            async with self._client_lock:
                if self._client is None:
                    from pymongo import AsyncMongoClient

                    self._client = AsyncMongoClient(self._mongo_uri, tz_aware=True)
        return self._client

    async def upsert_profile(self, profile: StudentProfileDocument) -> None:
        client = await self._get_client()
        collection = client[self._database_name]["student_profiles"]
        doc = profile.to_mongo_doc()
        await collection.replace_one({"_id": doc["_id"]}, doc, upsert=True)

    async def upsert_snapshot(self, snapshot: ClusterSnapshotDocument) -> None:
        client = await self._get_client()
        collection = client[self._database_name]["cluster_snapshots"]
        doc = snapshot.to_mongo_doc()
        await collection.replace_one({"_id": doc["_id"]}, doc, upsert=True)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None


class InMemoryProfileRepository(ProfileRepository):
    def __init__(self) -> None:
        self.profiles: dict[str, StudentProfileDocument] = {}
        self.snapshots: dict[str, ClusterSnapshotDocument] = {}

    async def upsert_profile(self, profile: StudentProfileDocument) -> None:
        self.profiles[profile.id] = profile

    async def upsert_snapshot(self, snapshot: ClusterSnapshotDocument) -> None:
        self.snapshots[snapshot.id] = snapshot

    async def close(self) -> None:
        return None
