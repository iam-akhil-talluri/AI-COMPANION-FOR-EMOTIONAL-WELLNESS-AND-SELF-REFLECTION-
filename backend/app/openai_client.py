"""Shared AsyncOpenAI client for chat and embeddings.

The client's HTTP connection pool is tied to the event loop it was first used
on, so one client is kept per running loop. Under uvicorn there is a single
loop, so this is effectively one client; tests may run several loops.
"""

import asyncio
import weakref

from openai import AsyncOpenAI

from .config import get_settings

_clients: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, AsyncOpenAI]" = weakref.WeakKeyDictionary()


def get_client() -> AsyncOpenAI:
    loop = asyncio.get_running_loop()
    client = _clients.get(loop)
    if client is None:
        client = AsyncOpenAI(api_key=get_settings().openai_api_key)
        _clients[loop] = client
    return client
