from transport_gateway.decoder.base import PacketDecoder
from transport_gateway.decoder.json_lines import JsonLinesPacketDecoder
from transport_gateway.decoder.ndtp import NdtpPacketDecoder


# Создаёт настроенный декодер телеметрии.
def create_packet_decoder(name: str) -> PacketDecoder:
    factories = {
        "json_lines": JsonLinesPacketDecoder,
        "ndtp": NdtpPacketDecoder,
    }
    factory = factories.get(name)
    if factory is None:
        raise ValueError(f"Unsupported packet decoder: {name}")
    decoder = factory()
    if not isinstance(decoder, PacketDecoder):
        raise TypeError("Decoder does not implement PacketDecoder")
    return decoder
