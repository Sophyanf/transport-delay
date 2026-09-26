import json
from typing import Any

from fastapi import WebSocket


class WebSocketHub:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.discard(websocket)

    def connection_count(self) -> int:
        return len(self._connections)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        message = json.dumps(payload, ensure_ascii=False)
        failed: list[WebSocket] = []
        for connection in tuple(self._connections):
            if not await self._broadcast_connection(connection, message):
                failed.append(connection)
        for connection in failed:
            self.disconnect(connection)

    async def _broadcast_connection(self, connection: WebSocket, message: str) -> bool:
        try:
            await connection.send_text(message)
        except RuntimeError:
            return False
        return True
