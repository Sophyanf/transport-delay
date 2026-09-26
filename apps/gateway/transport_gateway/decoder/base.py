from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from transport_contracts import TelemetryEvent


@dataclass(frozen=True)
class ExtractedPackets:
    packets: tuple[bytes, ...]
    remainder: bytes


@runtime_checkable
class PacketDecoder(Protocol):
    # Извлекает полные пакеты из накопленного TCP-буфера.
    def extract_packets(self, buffer: bytes) -> ExtractedPackets: ...

    # Декодирует один полный пакет телеметрии.
    def decode(self, packet: bytes) -> TelemetryEvent: ...
