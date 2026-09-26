import asyncio
import logging

from transport_gateway.decoder import PacketDecoder
from transport_gateway.publisher import TelemetryPublisher

LOGGER = logging.getLogger(__name__)


class TelemetryTcpServer:
    # Создаёт асинхронный TCP-сервер телеметрии.
    def __init__(
        self,
        host: str,
        port: int,
        read_size: int,
        max_buffer_bytes: int,
        client_timeout_s: float,
        decoder: PacketDecoder,
        publisher: TelemetryPublisher,
    ) -> None:
        self._host = host
        self._port = port
        self._read_size = read_size
        self._max_buffer_bytes = max_buffer_bytes
        self._client_timeout_s = client_timeout_s
        self._decoder = decoder
        self._publisher = publisher
        self._server: asyncio.Server | None = None

    # Запускает прослушивание TCP-порта.
    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle_client,
            self._host,
            self._port,
        )
        addresses = [str(socket.getsockname()) for socket in self._server.sockets or ()]
        LOGGER.info("Gateway listens on %s", addresses)

    # Ожидает завершения TCP-сервера.
    async def serve_forever(self) -> None:
        if self._server is None:
            raise RuntimeError("TCP server is not started")
        async with self._server:
            await self._server.serve_forever()

    # Останавливает TCP-сервер.
    async def stop(self) -> None:
        if self._server is None:
            return
        self._server.close()
        await self._server.wait_closed()
        self._server = None

    # Обрабатывает одно клиентское соединение.
    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        peer = writer.get_extra_info("peername")
        LOGGER.info("Telemetry client connected: %s", peer)
        try:
            await self._handle_client_stream(reader)
        except (TimeoutError, ConnectionError) as error:
            LOGGER.info("Telemetry client closed: %s, %s", peer, error)
        finally:
            writer.close()
            await writer.wait_closed()

    # Читает TCP-данные и обрабатывает извлечённые пакеты.
    async def _handle_client_stream(
        self,
        reader: asyncio.StreamReader,
    ) -> None:
        buffer = b""
        while not reader.at_eof():
            chunk = await asyncio.wait_for(
                reader.read(self._read_size),
                timeout=self._client_timeout_s,
            )
            if not chunk:
                break
            buffer += chunk
            self._handle_client_validate_buffer(buffer)
            extracted = self._decoder.extract_packets(buffer)
            buffer = extracted.remainder
            await self._handle_client_packets(extracted.packets)
        await self._handle_client_remainder(buffer)

    # Проверяет ограничение размера TCP-буфера.
    def _handle_client_validate_buffer(self, buffer: bytes) -> None:
        if len(buffer) > self._max_buffer_bytes:
            raise ConnectionError("Telemetry buffer limit exceeded")

    # Обрабатывает последовательность полных пакетов.
    async def _handle_client_packets(
        self,
        packets: tuple[bytes, ...],
    ) -> None:
        for packet in packets:
            await self._handle_client_packet(packet)

    # Декодирует и публикует один пакет.
    async def _handle_client_packet(self, packet: bytes) -> None:
        try:
            telemetry = self._decoder.decode(packet)
            await self._publisher.publish(telemetry)
        except (TypeError, ValueError) as error:
            LOGGER.warning("Telemetry packet rejected: %s", error)
            await self._publisher.publish_rejected(packet, str(error))

    # Публикует незавершённый остаток соединения как ошибку.
    async def _handle_client_remainder(self, remainder: bytes) -> None:
        if not remainder.strip():
            return
        reason = "Connection closed with incomplete telemetry packet"
        await self._publisher.publish_rejected(remainder, reason)
