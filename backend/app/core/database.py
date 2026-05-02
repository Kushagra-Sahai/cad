from __future__ import annotations

import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING

from app.core.config import Settings

logger = logging.getLogger(__name__)


class MongoState:
    client: AsyncIOMotorClient | None = None
    db: AsyncIOMotorDatabase | None = None


mongo_state = MongoState()


async def connect_to_mongo(settings: Settings) -> None:
    mongo_state.client = AsyncIOMotorClient(settings.mongo_uri)
    mongo_state.db = mongo_state.client[settings.mongo_db_name]
    await mongo_state.db.command("ping")
    await ensure_indexes(mongo_state.db)
    logger.info("Connected to MongoDB database '%s'", settings.mongo_db_name)


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    await db.queries.create_index([("created_at", DESCENDING)])
    await db.queries.create_index([("query", ASCENDING)])
    await db.medicine_cache.create_index([("normalized_name", ASCENDING)], unique=True)
    await db.medicine_cache.create_index([("updated_at", DESCENDING)])
    await db.logs.create_index([("created_at", DESCENDING)])
    await db.logs.create_index([("level", ASCENDING)])


async def close_mongo() -> None:
    if mongo_state.client is not None:
        mongo_state.client.close()
    mongo_state.client = None
    mongo_state.db = None


def get_database() -> AsyncIOMotorDatabase:
    if mongo_state.db is None:
        raise RuntimeError("MongoDB is not connected")
    return mongo_state.db
