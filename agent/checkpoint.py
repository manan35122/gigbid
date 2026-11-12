"""Postgres checkpointer (C6): threads survive a process crash and resume later."""
import asyncio
import os
import sys
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

load_dotenv()
if sys.platform == "win32":  # psycopg async cannot run on the default Proactor loop
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def db_uri() -> str:
    return os.getenv("DATABASE_URL", "postgresql://gigbid:gigbid@localhost:5432/gigbid").replace("+psycopg", "")


@asynccontextmanager
async def saver():
    async with AsyncPostgresSaver.from_conn_string(db_uri()) as cp:
        await cp.setup()
        yield cp