from pathlib import Path

from transport_contracts import TelemetryEvent

from transport_gateway.decoder.base import ExtractedPackets


class NdtpPacketDecoder:
    # Создаёт декодер, требующий официальную бинарную спецификацию.
    def __init__(
        self,
        specification_path: Path | None = None,
    ) -> None:
        self._specification_path = specification_path

    # Извлекает NDTP-пакеты после реализации официального framing.
    def extract_packets(self, buffer: bytes) -> ExtractedPackets:
        raise NotImplementedError(self._unsupported_message())

    # Декодирует G6CellNav00 после реализации официальной раскладки.
    def decode(self, packet: bytes) -> TelemetryEvent:
        raise NotImplementedError(self._unsupported_message())

    # Формирует сообщение о недостающей спецификации.
    def _unsupported_message(self) -> str:
        path = (
            str(self._specification_path)
            if self._specification_path is not None
            else "docs/Emulator-and-Telematic-Packets-Specification.md"
        )
        return (
            "Binary NDTP decoder requires exact framing, byte order, "
            f"field offsets and checksum rules from {path}"
        )
