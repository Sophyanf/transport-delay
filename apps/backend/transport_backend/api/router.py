from typing import Any, Literal

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    UploadFile,
    WebSocket,
)
from starlette.websockets import WebSocketDisconnect

from transport_backend.repositories import (
    IncidentRepository,
    ScheduleContextRepository,
    VehicleRepository,
)
from transport_backend.score import ScoreService
from transport_backend.submission import SubmissionService
from transport_backend.websocket import WebSocketHub


def create_backend_router(
    incidents: IncidentRepository,
    vehicles: VehicleRepository,
    schedules: ScheduleContextRepository,
    scores: ScoreService,
    submissions: SubmissionService,
    websocket_hub: WebSocketHub,
) -> APIRouter:
    """Создаёт и конфигурирует маршруты Backend API."""
    router = APIRouter()
    _add_incident_routes(router, incidents, vehicles, schedules)
    _add_vehicle_routes(router, incidents, vehicles)
    _add_score_routes(router, scores, submissions)
    _add_system_routes(router, incidents, websocket_hub)
    return router


def _add_incident_routes(
    router: APIRouter,
    incidents: IncidentRepository,
    vehicles: VehicleRepository,
    schedules: ScheduleContextRepository,
) -> None:
    @router.get("/incidents")
    async def list_incidents(
        limit: int = Query(default=200, ge=1, le=1_000),
        risk_level: Literal["red", "yellow", "green"] | None = None,
    ) -> list[dict[str, Any]]:
        items = await incidents.list_recent(limit, risk_level)
        return [await vehicles.enrich_incident(item) for item in items]

    @router.get("/incident/{tr_id}")
    async def incident_card(tr_id: str) -> dict[str, Any]:
        item = await _latest_vehicle_incident(incidents, tr_id)
        result = await vehicles.enrich_incident(item)
        context = schedules.context(
            tr_id,
            str(item.get("target_stop_id", "")),
            _optional_text(item.get("target_time_begin")),
        )
        result.update(context)
        return result

    _add_incident_action_routes(router, incidents)


def _add_incident_action_routes(
    router: APIRouter,
    incidents: IncidentRepository,
) -> None:
    @router.post("/incidents/{incident_id}/ack")
    async def acknowledge(incident_id: str) -> dict[str, Any]:
        incident = await incidents.acknowledge(incident_id)
        return _required_incident(incident)

    @router.post("/incidents/{incident_id}/close")
    async def close(incident_id: str) -> dict[str, Any]:
        incident = await incidents.close(incident_id)
        return _required_incident(incident)


def _add_vehicle_routes(
    router: APIRouter,
    incidents: IncidentRepository,
    vehicles: VehicleRepository,
) -> None:
    @router.get("/vehicles/positions")
    async def positions() -> list[dict[str, Any]]:
        result = await vehicles.list_positions()
        risks = await _vehicle_risks(incidents)
        for position in result:
            tr_id = str(position.get("tr_id", ""))
            position["risk_level"] = risks.get(tr_id, "green")
        return result


def _add_score_routes(
    router: APIRouter,
    scores: ScoreService,
    submissions: SubmissionService,
) -> None:
    @router.post("/score/upload")
    async def upload_score(file: UploadFile) -> dict[str, Any]:
        """Upload a CSV file with scores for metric calculation."""
        return await scores.upload(file)

    @router.get("/score/history")
    async def score_history() -> list[dict[str, Any]]:
        return await scores.history()

    @router.get("/submission/download")
    async def submission_download() -> Any:
        return submissions.download()


def _add_system_routes(
    router: APIRouter,
    incidents: IncidentRepository,
    hub: WebSocketHub,
) -> None:
    @router.get("/statistics")
    async def statistics() -> dict[str, float | int]:
        return await incidents.statistics()

    @router.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "backend",
            "websocket_connections": hub.connection_count(),
        }

    @router.websocket("/stream")
    async def stream(websocket: WebSocket) -> None:
        await _serve_websocket(websocket, hub)


async def _serve_websocket(
    websocket: WebSocket,
    hub: WebSocketHub,
) -> None:
    await hub.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        hub.disconnect(websocket)


async def _latest_vehicle_incident(
    repository: IncidentRepository,
    tr_id: str,
) -> dict[str, Any]:
    items = await repository.list_recent(1_000)
    for item in items:
        if str(item.get("tr_id", "")) == tr_id:
            return item
    raise HTTPException(
        status_code=404,
        detail="Инцидент для ТС не найден",
    )


async def _vehicle_risks(
    repository: IncidentRepository,
) -> dict[str, str]:
    items = await repository.list_recent(1_000)
    result: dict[str, str] = {}
    for item in items:
        tr_id = str(item.get("tr_id", ""))
        if tr_id:
            result.setdefault(tr_id, str(item.get("risk_level", "green")))
    return result


def _required_incident(
    incident: dict[str, Any] | None,
) -> dict[str, Any]:
    if incident is None:
        raise HTTPException(
            status_code=404,
            detail="Инцидент не найден",
        )
    return incident


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
