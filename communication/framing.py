"""
FrameParser: convierte el chorro de bytes del puerto (llega en trozos de cualquier tamaño) en tramas completas.

Es la misma lógica que `Receptor._procesar` de visor_adc.py: buscar AA 55, validar tipo y n, esperar la trama
entera y contar saltos de seq. Lo que agrega es que NO tira bytes en silencio: los cuenta (LinkStats), así se
puede saber qué tan sano está el enlace. Sin hilos, sin puertos: se le dan bytes con feed() y devuelve tramas.

Reconoce audio estéreo, mono L y mono R con el protocol.py actualizado.
Mientras busca sincronismo, espera la marca de la siguiente trama para
confirmar una trama de audio. Una trama de audio aislada puede quedar
pendiente; este parser está pensado para streaming continuo.
No hay CRC propio: la resincronización es una comprobación heurística.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np

from .protocol import (SYNC, HEADER_SIZE, FrameType, MAX_AUDIO_FRAMES, MAX_TEXT_LEN, EXPECTED_AUDIO_FRAMES,
                       payload_size, lost_frames, decode_audio, is_printable_text,
                       is_audio_frame, audio_channels)


# ======================================================================================
#  Lo que sale del parser
# ======================================================================================
@dataclass
class AudioFrame:
    seq: int
    samples: np.ndarray        # (n, C) float32, normalizadas a [-1, 1); NO voltios
    lost_before: int = 0       # salto de secuencia antes de esta trama (audio O texto)
    frame_type: FrameType = FrameType.AUDIO  # al final: conserva los 3 argumentos originales

    @property
    def channels(self) -> tuple[str, ...]:
        """Identidad de las columnas: ('L', 'R'), ('L',) o ('R',)."""
        return audio_channels(self.frame_type)


@dataclass
class TextFrame:
    seq: int
    text: str                  # tal cual llegó (la placa no manda terminador)
    lost_before: int = 0


@dataclass
class LinkStats:
    """Contadores acumulados desde que se creó el parser (o desde el último reset(clear_stats=True))."""
    bytes_in: int = 0          # bytes leídos del puerto
    audio_frames: int = 0      # tramas de audio completas
    text_frames: int = 0       # tramas de texto completas
    audio_samples: int = 0     # suma de n por trama: instantes recibidos, no suma de columnas
    lost_frames: int = 0       # tramas que el seq dice que faltan (descartadas por la placa o perdidas en la PC)
    loss_events: int = 0       # cuántos saltos de seq hubo (un salto puede abarcar varias tramas)
    junk_bytes: int = 0        # bytes descartados por estar fuera de una trama
    false_syncs: int = 0       # AA 55 con un encabezado imposible (tipo o n inválidos)
    resyncs: int = 0           # veces que se perdió el sincronismo con la corriente en marcha y hubo que buscarlo
    last_seq: int | None = None

    def as_dict(self):
        return asdict(self)


# ======================================================================================
#  El parser
# ======================================================================================
class FrameParser:
    def __init__(self, max_audio_frames=MAX_AUDIO_FRAMES, max_text_len=MAX_TEXT_LEN,
                 expected_audio_frames=EXPECTED_AUDIO_FRAMES):
        self.max_audio_frames = max_audio_frames
        self.max_text_len = max_text_len
        self.expected_audio_frames = expected_audio_frames
        self.stats = LinkStats()
        self._buf = bytearray()
        self._in_sync = False          # True mientras las tramas se suceden una tras otra sin bytes de por medio

    # --- control ------------------------------------------------------------------
    def reset(self, clear_stats=False):
        """Descarta lo acumulado y la referencia de seq (por ejemplo, al reiniciar el stream)."""
        self._buf.clear()
        self._in_sync = False
        self.stats.last_seq = None
        if clear_stats:
            self.stats = LinkStats()

    def forget_sequence(self):
        """La próxima trama no se compara con la anterior (el stream se detuvo y vuelve a arrancar)."""
        self.stats.last_seq = None

    @property
    def pending_bytes(self):
        """Bytes recibidos que todavía no forman una trama completa."""
        return len(self._buf)

    # --- entrada ------------------------------------------------------------------
    def feed(self, data):
        """Devuelve AudioFrame/TextFrame en orden y conserva fragmentos pendientes.

        lost_before también se informa en TextFrame: el consumidor debe
        procesarlo en AMBOS tipos para no ocultar un corte anterior al texto.
        No llamar desde varios hilos a la vez sobre la misma instancia.
        """
        buf = self._buf
        buf.extend(data)
        st = self.stats
        st.bytes_in += len(data)
        out = []
        pos = 0                                        # lo anterior a `pos` ya se consumió; se borra una sola vez al final
        end = len(buf)
        while True:
            i = buf.find(SYNC, pos)
            if i < 0:
                # No hay marca. Se conserva el último byte por si es el 0xAA de un encabezado partido entre dos lecturas.
                keep = 1 if end > pos and buf[end - 1] == SYNC[0] else 0
                self._discard(end - pos - keep)
                pos = end - keep
                break
            if i > pos:
                self._discard(i - pos)                 # basura antes de la marca
                pos = i
            if end - pos < HEADER_SIZE:
                break                                  # hay marca pero falta el resto del encabezado
            tipo = buf[pos + 2]
            seq = buf[pos + 3]
            n = buf[pos + 4] | (buf[pos + 5] << 8)
            size = payload_size(tipo, n, self.max_audio_frames, self.max_text_len, self.expected_audio_frames)
            if size is None:                           # falso sincronismo: AA 55 casual dentro de los datos
                st.false_syncs += 1
                self._discard(1)
                pos += 1
                continue
            total = HEADER_SIZE + size
            if end - pos < total:
                break                                  # falta llegar el resto de la trama
            if is_audio_frame(tipo) and not self._in_sync:
                # Buscando sincronismo: una trama de audio se acepta recién cuando la SIGUIENTE también empieza
                # con AA 55 (el audio llega sin pausas: la próxima trama está a 2,6 ms). Un encabezado casual que
                # pasó todas las validaciones no tiene una marca exactamente donde terminaría.
                if end - pos < total + len(SYNC):
                    break
                if buf[pos + total:pos + total + len(SYNC)] != SYNC:
                    st.false_syncs += 1
                    self._discard(1)
                    pos += 1
                    continue
            payload = bytes(buf[pos + HEADER_SIZE:pos + total])
            if tipo == FrameType.TEXT and not is_printable_text(payload):
                st.false_syncs += 1                    # "texto" con bytes binarios: era un AA 55 casual
                self._discard(1)
                pos += 1
                continue
            pos += total
            self._in_sync = True
            lost = self._track_seq(seq)
            if is_audio_frame(tipo):
                st.audio_frames += 1
                st.audio_samples += n
                out.append(AudioFrame(
                    seq=seq, samples=decode_audio(payload, tipo),
                    lost_before=lost, frame_type=FrameType(tipo),
                ))
            else:
                st.text_frames += 1
                out.append(TextFrame(seq, payload.decode("ascii", errors="replace"), lost))
        del buf[:pos]
        return out

    # --- internos -----------------------------------------------------------------
    def _discard(self, count):
        if count <= 0:
            return
        self.stats.junk_bytes += count
        if self._in_sync:                              # se rompió una corriente que venía bien: un solo resync por episodio
            self.stats.resyncs += 1
            self._in_sync = False

    def _track_seq(self, seq):
        # Es un salto módulo 256, no una medida exacta de muestras perdidas.
        # Reinicios/duplicados requieren tratamiento en la sesión.
        st = self.stats
        lost = 0 if st.last_seq is None else lost_frames(st.last_seq, seq)
        if lost:
            st.lost_frames += lost
            st.loss_events += 1
        st.last_seq = seq
        return lost
