"""Protocolo Blackpill / PCM3060 (Firmware_PCB).

PC -> placa: comandos ASCII terminados en LF (b'\n').
Placa -> PC: AA 55 | tipo u8 | secuencia u8 | cantidad u16 LE | payload.

Tipos: 01 = estéreo L/R, 02 = texto, 03 = mono L, 04 = mono R.
Cantidad cuenta muestras POR CANAL; en texto cuenta bytes.
PCM24 con signo, little-endian; salida float32 normalizada, NO voltios.

Este módulo define formatos y conversiones. No abre puertos ni junta
fragmentos: esas tareas corresponden a transport.py y framing.py.
"""
import operator
import struct
from enum import IntEnum

import numpy as np

SYNC = b"\xAA\x55"
_HEADER = struct.Struct("<2sBBH")
HEADER_SIZE = _HEADER.size
FIRMWARE_FS = 97656.25  # Valor nominal: no viene incluido en las tramas.

# Se conservan por compatibilidad: estas dos constantes describen ESTÉREO.
CHANNELS = 2
BYTES_PER_SAMPLE = 3
BYTES_PER_FRAME = CHANNELS * BYTES_PER_SAMPLE
FULL_SCALE = float(1 << 23)
MAX_AUDIO_FRAMES = 4096
EXPECTED_AUDIO_FRAMES = 256  # None al validar permite otros tamaños.
MAX_TEXT_LEN = 64  # Límite del receptor conservado del paquete original.
SEQ_MODULO = 256
COMMAND_TERMINATOR = b"\n"
MAX_COMMAND_LEN = 127


class FrameType(IntEnum):
    AUDIO = 0x01  # Nombre original conservado para el código existente.
    AUDIO_STEREO = 0x01
    TEXT = 0x02
    AUDIO_L = 0x03
    AUDIO_R = 0x04


AUDIO_TYPES = (FrameType.AUDIO, FrameType.AUDIO_L, FrameType.AUDIO_R)


def is_audio_frame(frame_type):
    """Indica si el tipo transporta muestras (estéreo o mono)."""
    return frame_type in AUDIO_TYPES


def audio_channels(frame_type):
    """Identidad de las columnas: ('L', 'R'), ('L',) o ('R',)."""
    if frame_type == FrameType.AUDIO:
        return ("L", "R")
    if frame_type == FrameType.AUDIO_L:
        return ("L",)
    if frame_type == FrameType.AUDIO_R:
        return ("R",)
    raise ValueError(f"El tipo {frame_type!r} no es de audio")


def bytes_per_audio_frame(frame_type):
    """Bytes por instante de muestreo: 6 en estéreo, 3 en mono."""
    return len(audio_channels(frame_type)) * BYTES_PER_SAMPLE


def pack_frame(frame_type, seq, payload, n=None):
    """Construye una trama; deduce n y comprueba que coincida con el payload.

Permite tamaños distintos de 256 para simulaciones. Los límites de recepción
se aplican por separado mediante payload_size().
    """
    frame_type = FrameType(frame_type)
    payload = bytes(payload)
    stride = 1 if frame_type == FrameType.TEXT else bytes_per_audio_frame(frame_type)
    if len(payload) % stride:
        raise ValueError("Payload incompleto para el tipo de trama")
    inferred_n = len(payload) // stride
    n = inferred_n if n is None else operator.index(n)
    if not 0 <= n <= 65535 or n != inferred_n:
        raise ValueError("Cantidad fuera de rango o incompatible con el payload")
    if is_audio_frame(frame_type) and n == 0:
        raise ValueError("Una trama de audio debe contener muestras")
    return _HEADER.pack(SYNC, int(frame_type), operator.index(seq) & 0xFF, n) + payload


def unpack_header(data):
    """Devuelve (tipo, seq, n), o None si falta la cabecera o su marca."""
    if len(data) < HEADER_SIZE:
        return None
    sync, tipo, seq, n = _HEADER.unpack_from(data, 0)
    return (tipo, seq, n) if sync == SYNC else None


def payload_size(frame_type, n, max_audio_frames=MAX_AUDIO_FRAMES,
                 max_text_len=MAX_TEXT_LEN, expected_audio_frames=EXPECTED_AUDIO_FRAMES):
    """Longitud esperada del payload, o None para un encabezado inválido.

El filtro de 256 muestras se aplica a los tres tipos de audio.
    """
    try:
        n = operator.index(n)
    except TypeError:
        return None
    if not 0 <= n <= 65535:
        return None
    if is_audio_frame(frame_type) and 0 < n <= max_audio_frames:
        if expected_audio_frames is not None and n != expected_audio_frames:
            return None
        return n * bytes_per_audio_frame(frame_type)
    if frame_type == FrameType.TEXT and n <= max_text_len:
        return n
    return None


def is_printable_text(payload):
    """Valida texto ASCII imprimible, sin terminador dentro del payload."""
    return all(32 <= b <= 126 for b in payload)


def lost_frames(last_seq, seq):
    """Salto módulo 256; cuenta tramas, no muestras ni solo audio.

No permite distinguir reinicios, duplicados ni pérdidas de vueltas completas.
La sesión debe restablecer la referencia cuando corresponda.
    """
    return (seq - last_seq - 1) & 0xFF


def decode_audio(payload, frame_type=FrameType.AUDIO):
    """PCM24 LE -> float32 (N, C). Por defecto conserva el modo estéreo.

Para mono usar AUDIO_L o AUDIO_R. La identidad se obtiene con
audio_channels(frame_type), no con el índice de la columna.
    """
    channels = len(audio_channels(frame_type))
    raw = np.frombuffer(payload, dtype=np.uint8)
    if raw.size % (BYTES_PER_SAMPLE * channels):
        raise ValueError("Payload PCM24 incompleto")
    triples = raw.reshape(-1, 3).astype(np.int32)
    values = triples[:, 0] | (triples[:, 1] << 8) | (triples[:, 2] << 16)
    # Extensión de signo de 24 bits a 32 bits.
    values = (values ^ 0x800000) - 0x800000
    return (values.astype(np.float32) / FULL_SCALE).reshape(-1, channels)


def encode_audio(samples, frame_type=FrameType.AUDIO):
    """Muestras normalizadas -> PCM24 LE, para simulación y pruebas.

Acepta (N, C) o un vector 1D intercalado. El tipo define C: 1 o 2.
Recorta al rango representable y rechaza NaN e infinito.
    """
    channels = len(audio_channels(frame_type))
    x = np.asarray(samples, dtype=np.float64)
    if x.ndim == 1:
        if x.size % channels:
            raise ValueError("Cantidad de muestras incompatible con los canales")
        x = x.reshape(-1, channels)
    elif x.ndim != 2 or x.shape[1] != channels:
        raise ValueError(f"Se esperaba un array (N, {channels}) o un vector intercalado")
    if not np.all(np.isfinite(x)):
        raise ValueError("Las muestras deben ser finitas")
    x = np.clip(x, -1.0, 1.0 - 1.0 / FULL_SCALE)
    q = np.rint(x * FULL_SCALE).astype(np.int32).reshape(-1)
    out = np.empty((q.size, 3), dtype=np.uint8)
    out[:, 0] = q & 0xFF
    out[:, 1] = (q >> 8) & 0xFF
    out[:, 2] = (q >> 16) & 0xFF
    return out.tobytes()
