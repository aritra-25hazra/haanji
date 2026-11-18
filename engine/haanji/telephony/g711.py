"""G.711 μ-law <-> 16-bit linear PCM, in pure Python (audioop is gone from
Python 3.13). Twilio speaks μ-law; Exotel speaks 16-bit little-endian PCM;
the recogniser and the synthesiser stay on μ-law, so a provider that speaks
PCM is converted at the edge."""
from __future__ import annotations
import struct

_BIAS = 0x84


def _decode(u: int) -> int:
    u = ~u & 0xFF
    sign, exponent, mantissa = u & 0x80, (u >> 4) & 0x07, u & 0x0F
    sample = (((mantissa << 3) + _BIAS) << exponent) - _BIAS
    return -sample if sign else sample


_SEG_END = (0x3F, 0x7F, 0xFF, 0x1FF, 0x3FF, 0x7FF, 0xFFF, 0x1FFF)


def _encode(sample: int) -> int:
    """The classic Sun/CCITT encoder (what audioop.lin2ulaw did): the sample
    scaled to 14 bits, biased, and placed in one of eight segments."""
    v = sample >> 2
    mask = 0x7F if v < 0 else 0xFF
    v = min(abs(v), 8159) + (_BIAS >> 2)
    seg = next((i for i, end in enumerate(_SEG_END) if v <= end), 8)
    if seg >= 8:
        return 0x7F ^ mask
    return ((seg << 4) | ((v >> (seg + 1)) & 0x0F)) ^ mask


_ULAW_TO_LIN = [_decode(u) for u in range(256)]
_LIN_TO_ULAW = bytes(_encode(s) for s in range(-32768, 32768))


def ulaw_to_pcm16(data: bytes) -> bytes:
    """μ-law bytes -> little-endian 16-bit PCM (twice as long)."""
    return struct.pack(f"<{len(data)}h", *(_ULAW_TO_LIN[b] for b in data))


def pcm16_to_ulaw(data: bytes) -> bytes:
    """Little-endian 16-bit PCM -> μ-law (half as long); a trailing odd byte is dropped."""
    n = len(data) // 2
    return bytes(_LIN_TO_ULAW[s + 32768] for s in struct.unpack(f"<{n}h", data[: n * 2]))
