from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class InverterProtocol:
    name: str
    aliases: tuple[str, ...]
    default_request_hex: str
    default_frame_length: int
    default_data_length: int
    default_crc_order: str
    parse_frame: Callable[
        [bytes, str, int, int, int, str, bool],
        dict,
    ]


def get_protocol_aliases() -> dict[str, str]:
    from solar_rs485_monitor.protocols.inoelectric_iepvs_g1_g2 import (
        PROTOCOL as INOELECTRIC_IEPVS_G1_G2,
    )

    protocols = {
        INOELECTRIC_IEPVS_G1_G2.name: INOELECTRIC_IEPVS_G1_G2,
    }
    aliases: dict[str, str] = {}

    for canonical_name, protocol in protocols.items():
        aliases[canonical_name] = canonical_name
        for alias in protocol.aliases:
            aliases[alias] = canonical_name

    return aliases


def list_protocol_names() -> list[str]:
    return sorted(set(get_protocol_aliases().values()))


def get_protocol(name: str) -> InverterProtocol:
    from solar_rs485_monitor.protocols.inoelectric_iepvs_g1_g2 import (
        PROTOCOL as INOELECTRIC_IEPVS_G1_G2,
    )

    protocols = {
        INOELECTRIC_IEPVS_G1_G2.name: INOELECTRIC_IEPVS_G1_G2,
    }
    normalized_name = name.strip().lower().replace("-", "_")
    canonical_name = get_protocol_aliases().get(normalized_name)

    if canonical_name is None:
        raise RuntimeError(f"Unknown INVERTER_PROTOCOL: {name}")

    return protocols[canonical_name]
