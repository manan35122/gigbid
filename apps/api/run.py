import asyncio

import uvicorn

if __name__ == "__main__":
    server = uvicorn.Server(uvicorn.Config("apps.api.main:app", port=8000))
    asyncio.run(server.serve(), loop_factory=asyncio.SelectorEventLoop)