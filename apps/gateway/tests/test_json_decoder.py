import json

import pytest
from transport_gateway.decoder import JsonLinesPacketDecoder


# Создаёт тестовый JSON-пакет эмулятора.
def create_json_decoder_packet() -> bytes:
    return json.dumps(
        {
            "peerAddress": 42,
            "packetId": 1001,
            "timestamp": 1_735_728_000,
            "longitude": 376_173_000,
            "latitude": 557_558_000,
            "speedAvg": 21.5,
            "course": 180,
            "location_valid": True,
        }
    ).encode("utf-8")


# Проверяет нормализацию JSON-пакета.
def test_json_decoder_normalizes_packet() -> None:
    event = JsonLinesPacketDecoder().decode(create_json_decoder_packet())
    assert event.unit_id == "42"
    assert event.tr_id == "42"
    assert event.longitude == pytest.approx(37.6173)
    assert event.latitude == pytest.approx(55.7558)
    assert event.speed_kmh == 21.5
    assert event.heading_deg == 180.0


# Проверяет извлечение нескольких JSON-строк.
def test_json_decoder_extracts_complete_lines() -> None:
    decoder = JsonLinesPacketDecoder()
    result = decoder.extract_packets(b'{"a":1}\n{"b":2}\n{"c":')
    assert result.packets == (b'{"a":1}', b'{"b":2}')
    assert result.remainder == b'{"c":'


# Проверяет отклонение некорректного JSON.
def test_json_decoder_rejects_invalid_json() -> None:
    with pytest.raises(ValueError):
        JsonLinesPacketDecoder().decode(b"{invalid}")
