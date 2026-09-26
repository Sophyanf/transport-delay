import asyncio
import logging

from redis.asyncio import Redis

from transport_gateway.decoder import create_packet_decoder
from transport_gateway.publisher import TelemetryPublisher
from transport_gateway.server import TelemetryTcpServer
from transport_gateway.settings import GatewaySettings


# Создаёт компоненты Gateway из настроек.
def create_gateway(
    settings: GatewaySettings,
) -> tuple[TelemetryTcpServer, Redis]:
    redis = Redis.from_url(
        settings.redis_url,
        decode_responses=False,
    )
    decoder = create_packet_decoder(settings.gateway_decoder)
    publisher = TelemetryPublisher(
        redis=redis,
        stream=settings.telemetry_stream,
        dead_letter_stream=settings.telemetry_dead_letter_stream,
        max_length=settings.telemetry_stream_maxlen,
    )
    server = TelemetryTcpServer(
        host=settings.gateway_host,
        port=settings.gateway_port,
        read_size=settings.gateway_read_size,
        max_buffer_bytes=settings.gateway_max_buffer_bytes,
        client_timeout_s=settings.gateway_client_timeout_s,
        decoder=decoder,
        publisher=publisher,
    )
    return server, redis


# Запускает Gateway и освобождает ресурсы.
async def run_gateway() -> None:
    settings = GatewaySettings()
    server, redis = create_gateway(settings)
    try:
        await redis.ping()
        await server.start()
        await server.serve_forever()
    finally:
        await server.stop()
        await redis.aclose()


# Настраивает журналирование и запускает Gateway.
def main() -> None:
    settings = GatewaySettings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(run_gateway())


if __name__ == "__main__":
    main()
