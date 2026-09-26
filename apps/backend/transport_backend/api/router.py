from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, WebSocket
from starlette.websockets import WebSocketDisconnect

from transport_backend.repositories import IncidentRepository
from transport_backend.websocket import WebSocketHub


# Создаёт HTTP и WebSocket маршруты Backend.
def create_backend_router(
    repository: IncidentRepository,
    websocket_hub: WebSocketHub,
) -> APIRouter:
    router = APIRouter()
    create_backend_router_incidents(
        router,
        repository,
        websocket_hub,
    )
    create_backend_router_system(
        router,
        repository,
        websocket_hub,
    )
    return router


# Добавляет маршруты диспетчерских инцидентов.
def create_backend_router_incidents(
    router: APIRouter,
    repository: IncidentRepository,
    websocket_hub: WebSocketHub,
) -> None:
    @router.get("/incidents")
    async def list_incidents(
        limit: int = Query(default=200, ge=1, le=1_000),
        risk_level: Literal["red", "yellow", "green"] | None = None,
    ) -> list[dict[str, Any]]:
        return await repository.list_recent(limit, risk_level)

    @router.get("/incidents/{incident_id}")
    async def get_incident(incident_id: str) -> dict[str, Any]:
        return await create_backend_router_get(
            repository,
            incident_id,
        )

    @router.post("/incidents/{incident_id}/ack")
    async def acknowledge_incident(
        incident_id: str,
    ) -> dict[str, Any]:
        incident = await repository.acknowledge(incident_id)
        return await create_backend_router_changed(
            incident,
            websocket_hub,
            "incident.acknowledged",
        )

    @router.post("/incidents/{incident_id}/close")
    async def close_incident(
        incident_id: str,
    ) -> dict[str, Any]:
        incident = await repository.close(incident_id)
        return await create_backend_router_changed(
            incident,
            websocket_hub,
            "incident.closed",
        )


# Добавляет healthcheck, статистику и WebSocket.
def create_backend_router_system(
    router: APIRouter,
    repository: IncidentRepository,
    websocket_hub: WebSocketHub,
) -> None:
    @router.get("/statistics")
    async def statistics() -> dict[str, float | int]:
        return await repository.statistics()

    @router.get("/health")
    async def health() -> dict[str, str | int]:
        return {
            "status": "ok",
            "service": "backend",
            "websocket_connections": websocket_hub.connection_count(),
        }

    @router.websocket("/stream")
    async def stream(websocket: WebSocket) -> None:
        await websocket_hub.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            websocket_hub.disconnect(websocket)


# Возвращает инцидент или ошибку 404.
async def create_backend_router_get(
    repository: IncidentRepository,
    incident_id: str,
) -> dict[str, Any]:
    incident = await repository.get(incident_id)
    if incident is None:
        raise HTTPException(
            status_code=404,
            detail="Incident not found",
        )
    return incident


# Рассылает изменение инцидента или возвращает 404.
async def create_backend_router_changed(
    incident: dict[str, Any] | None,
    websocket_hub: WebSocketHub,
    event_type: str,
) -> dict[str, Any]:
    if incident is None:
        raise HTTPException(
            status_code=404,
            detail="Incident not found",
        )
    await websocket_hub.broadcast(
        {
            "type": event_type,
            "payload": incident,
        }
    )
    return incident
