"""Decodificador incremental de paquetes USB CDC de la Blackpill.

AA 55 | tipo (u8) | secuencia (u8) | cantidad (u16 LE) | payload
Tipos: 1 estéreo, 2 texto, 3 CH1 mono, 4 CH2 mono.
Las muestras PCM son enteros con signo de 24 bits, little-endian.
"""
from dataclasses import dataclass
import numpy as np

MAGIC = b"\xAA\x55"
MAX_COUNT = 4096


@dataclass
class Frame:
    kind: str
    sequence: int
    samples: np.ndarray | None = None  # (N, C), float32
    channel: int | None = None         # 0=CH1, 1=CH2; None=estéreo/texto
    text: str | None = None


def decode_pcm24(payload: bytes, channels: int) -> np.ndarray:
    """Decodifica PCM24 LE intercalado y normaliza a [-1, 1)."""
    raw = np.frombuffer(payload, dtype=np.uint8)
    if raw.size % (3 * channels):
        raise ValueError("Payload PCM24 incompleto")
    triples = raw.reshape(-1, 3)
    values = (triples[:, 0].astype(np.int32)
              | (triples[:, 1].astype(np.int32) << 8)
              | (triples[:, 2].astype(np.int32) << 16))
    values = (values ^ 0x800000) - 0x800000
    return (values.astype(np.float32) / 8388608.0).reshape(-1, channels)


class FrameDecoder:
    def __init__(self):
        self._buffer = bytearray()
        self.last_sequence = None
        self.lost_packets = 0

    def reset(self):
        self._buffer.clear()
        self.last_sequence = None
        self.lost_packets = 0

    def feed(self, chunk: bytes) -> list[Frame]:
        """Recibe cualquier fragmento de bytes y devuelve tramas completas."""
        self._buffer.extend(chunk)
        frames = []
        while True:
            start = self._buffer.find(MAGIC)
            if start < 0:
                # Retener AA si podría ser el primer byte de la cabecera.
                self._buffer[:] = b"\xAA" if self._buffer.endswith(b"\xAA") else b""
                break
            if start:
                del self._buffer[:start]
            if len(self._buffer) < 6:
                break
            kind, sequence = self._buffer[2], self._buffer[3]
            count = int.from_bytes(self._buffer[4:6], "little")
            size_per_sample = {1: 6, 2: 1, 3: 3, 4: 3}.get(kind)
            if size_per_sample is None or count > MAX_COUNT:
                del self._buffer[0]
                continue
            packet_size = 6 + count * size_per_sample
            if len(self._buffer) < packet_size:
                break
            payload = bytes(self._buffer[6:packet_size])
            del self._buffer[:packet_size]
            if self.last_sequence is not None:
                missing = (sequence - self.last_sequence - 1) % 256
                self.lost_packets += missing
            self.last_sequence = sequence
            if kind == 2:
                frames.append(Frame("text", sequence, text=payload.decode("utf-8", errors="replace")))
            else:
                channels = 2 if kind == 1 else 1
                frames.append(Frame("samples", sequence,
                                    samples=decode_pcm24(payload, channels),
                                    channel=None if kind == 1 else (0 if kind == 3 else 1)))
        return frames
