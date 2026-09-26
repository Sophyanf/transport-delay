import json
from datetime import UTC, datetime
from typing import Any

from transport_contracts import TelemetryEvent

from transport_gateway.decoder.base import ExtractedPackets


class JsonLinesPacketDecoder:
    # Извлекает полные JSON-строки из TCP-буфера.
    def extract_packets(self, buffer: bytes) -> ExtractedPackets:
        parts = buffer.split(b"\n")
        packets = tuple(part.rstrip(b"\r") for part in parts[:-1] if part.rstrip(b"\r"))
        return ExtractedPackets(
            packets=packets,
            remainder=parts[-1],
        )

    # Декодирует одну JSON-строку в событие телеметрии.
    def decode(self, packet: bytes) -> TelemetryEvent:
        payload = self._decode_payload(packet)
        normalized = self._decode_normalize(payload)
        return TelemetryEvent.model_validate(normalized)

    # Разбирает JSON и проверяет тип корневого значения.
    def _decode_payload(self, packet: bytes) -> dict[str, Any]:
        try:
            payload = json.loads(packet.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("Invalid JSON telemetry packet") from error
        if not isinstance(payload, dict):
            raise ValueError("Telemetry packet must be a JSON object")
        return payload

    # Нормализует поля пакета во внутренний контракт.
    def _decode_normalize(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        event_time = self._decode_datetime(payload.get("event_time", payload.get("timestamp")))
        unit_id = self._decode_optional_text(payload.get("unit_id", payload.get("peerAddress")))
        packet_id = self._decode_optional_text(payload.get("packet_id", payload.get("packetId")))
        return self._decode_normalized_payload(
            payload,
            event_time,
            unit_id,
            packet_id,
        )

    # Собирает нормализованный словарь события.
    def _decode_normalized_payload(
        self,
        payload: dict[str, Any],
        event_time: datetime,
        unit_id: str | None,
        packet_id: str | None,
    ) -> dict[str, Any]:
        tr_id = str(payload.get("tr_id") or unit_id or "")
        return {
            "event_id": self._decode_event_id(
                payload,
                unit_id,
                packet_id,
                event_time,
            ),
            "tr_id": tr_id,
            "unit_id": unit_id,
            "event_time": event_time,
            "received_at": datetime.now(UTC),
            "longitude": self._decode_coordinate(
                payload,
                "lon",
                "longitude",
            ),
            "latitude": self._decode_coordinate(
                payload,
                "lat",
                "latitude",
            ),
            "altitude_m": payload.get("alt", payload.get("altitude")),
            "speed_kmh": payload.get("speed", payload.get("speedAvg")),
            "heading_deg": payload.get("heading", payload.get("course")),
            "location_valid": self._decode_location_valid(payload),
            "packet_id": packet_id,
            "device_event_id": self._decode_optional_text(payload.get("device_event_id")),
            "is_historical": bool(payload.get("is_hist_data", False)),
            "source": "json-lines",
        }

    # Создаёт устойчивый идентификатор события.
    def _decode_event_id(
        self,
        payload: dict[str, Any],
        unit_id: str | None,
        packet_id: str | None,
        event_time: datetime,
    ) -> str:
        explicit = payload.get("event_id")
        if explicit:
            return str(explicit)
        return f"{unit_id or 'unknown'}:{packet_id or 'unknown'}:{event_time.timestamp()}"

    # Преобразует Unix timestamp или ISO-строку в UTC datetime.
    def _decode_datetime(self, value: object) -> datetime:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=UTC)
        if isinstance(value, str):
            normalized = value.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        raise ValueError("Packet has no valid event timestamp")

    # Извлекает и масштабирует координату.
    def _decode_coordinate(
        self,
        payload: dict[str, Any],
        short_name: str,
        long_name: str,
    ) -> float | None:
        value = payload.get(short_name, payload.get(long_name))
        if value is None:
            return None
        coordinate = float(value)
        if abs(coordinate) > 1_000:
            coordinate /= 10_000_000
        return coordinate

    # Извлекает флаг достоверности геопозиции.
    def _decode_location_valid(
        self,
        payload: dict[str, Any],
    ) -> bool:
        value = payload.get(
            "location_valid",
            payload.get("extraDopBit7", False),
        )
        if isinstance(value, str):
            return value.strip().lower() in {"true", "1", "yes"}
        return bool(value)

    # Преобразует необязательное значение в строку.
    def _decode_optional_text(self, value: object) -> str | None:
        if value is None or value == "":
            return None
        return str(value)
