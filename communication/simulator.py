
"""
===============================================================================
SIMULADOR DE BLACKPILL - OSCILLOSCOPE_PF
===============================================================================

Simula la comunicación USB CDC con la Blackpill sin utilizar hardware físico.

Protocolo:
    AA 55 | tipo u8 | secuencia u8 | cantidad u16 LE | payload

Tipos de trama:
    0x01 -> Audio estéreo L/R
    0x02 -> Texto
    0x03 -> Audio mono L (CH1)
    0x04 -> Audio mono R (CH2)

Comandos:
    STREAM:1 -> transmitir ambos canales
    STREAM:L -> transmitir CH1
    STREAM:R -> transmitir CH2
    STREAM:0 -> detener transmisión
    PING     -> responder PONG

Características:
    - Frecuencia de muestreo nominal: 97656.25 Hz.
    - Audio PCM24 little-endian.
    - Bloques de 256 muestras por canal.
    - Generación de señales senoidales, cuadradas, triangulares y chirp.
    - Configuración de frecuencia y amplitud.
    - Simulación de ruido y loopback.
    - Secuencia de tramas módulo 256.
    - Buffer de transmisión y pérdidas por saturación.
    - Fragmentación de datos USB.
    - Transporte compatible con DeviceSession.

===============================================================================
"""

from __future__ import annotations

import math
import re
import time

import numpy as np

from .commands import Waveform
from .errors import LinkLost
from .protocol import (
    FIRMWARE_FS,
    FrameType,
    HEADER_SIZE,
    BYTES_PER_SAMPLE,
    pack_frame,
    encode_audio,
)
from .transport import RX_BUFFER_BYTES, Transport


# =============================================================================
# CONSTANTES
# =============================================================================

DEFAULT_FS = FIRMWARE_FS

FRAMES_PER_BLOCK = 256

RING_SIZE = 65536

USB_RX_BUFFER = 128

_FLOAT_PREFIX = re.compile(
    r"\s*[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?"
)


# =============================================================================
# FUNCIONES AUXILIARES
# =============================================================================

def _atof(text):
    """
    Conversión similar a atof() de C.

    Extrae el número inicial del texto.
    Devuelve 0.0 si no encuentra uno.
    """

    match = _FLOAT_PREFIX.match(text)

    if match is None:
        return 0.0

    return float(match.group(0))


# =============================================================================
# BLACKPILL SIMULADA
# =============================================================================

class FakeBlackPill:
    """
    Simula el comportamiento del firmware de la Blackpill.

    Genera muestras para ambos canales internamente, pero transmite
    solamente los canales seleccionados por el comando STREAM.

    Modos:
        L  -> CH1
        R  -> CH2
        LR -> CH1 + CH2
    """

    def __init__(
        self,
        fs=DEFAULT_FS,
        frames_per_block=FRAMES_PER_BLOCK,
        ring_size=RING_SIZE,
        loopback=1.0,
        noise_dbfs=-110.0,
        seed=1,
    ):

        # ---------------------------------------------------------------------
        # Configuración de adquisición
        # ---------------------------------------------------------------------

        self.fs = float(fs)

        self.block = int(frames_per_block)

        self.ring_size = int(ring_size)

        self.loopback = float(loopback)

        self.noise = 10.0 ** (
            noise_dbfs / 20.0
        )

        self.offset = [0.0, 0.0]
        self.noise_channels = [self.noise, self.noise]
        self._rng = np.random.default_rng(seed)

        # ---------------------------------------------------------------------
        # Generadores de señales
        # ---------------------------------------------------------------------

        self.freq = [
            1000.0,
            1000.0,
        ]

        self.amp = [
            50,
            50,
        ]

        self.on = [
            True,
            True,
        ]

        self.wave = [
            Waveform.SINE,
            Waveform.SINE,
        ]

        self.chirp = [
            (200.0, 2000.0, 1.0),
            (200.0, 2000.0, 1.0),
        ]

        # ---------------------------------------------------------------------
        # Estado del códec
        # ---------------------------------------------------------------------

        self.adc_on = True

        self.dac_on = True

        self.differential = True

        # ---------------------------------------------------------------------
        # Estado de transmisión
        # ---------------------------------------------------------------------

        self.stream_on = False

        # LR = estéreo por defecto
        self.stream_channel = "LR"

        # ---------------------------------------------------------------------
        # Estadísticas
        # ---------------------------------------------------------------------

        self.commands_seen = []

        self.ignored = []

        self.rx_overflows = 0

        self.stream_dropped = 0

        # ---------------------------------------------------------------------
        # Buffers USB
        # ---------------------------------------------------------------------

        self._rx = bytearray()

        self._tx = bytearray()

        self._seq = 0

        # ---------------------------------------------------------------------
        # Reloj DMA
        # ---------------------------------------------------------------------

        self._period = (
            self.block / self.fs
        )

        self._t0 = None

        self._frames_done = 0

        # ---------------------------------------------------------------------
        # Estado de fase
        # ---------------------------------------------------------------------

        self._phase = [
            0.0,
            0.0,
        ]

        self._chirp_t = [
            0.0,
            0.0,
        ]

    # =========================================================================
    # RELOJ DE ADQUISICIÓN
    # =========================================================================

    def start(self, now):
        """Inicializa el reloj de adquisición."""

        self._t0 = float(now)

        self._frames_done = 0

    def _due(self, now):
        """Calcula los callbacks DMA que deberían haberse ejecutado."""

        if self._t0 is None:
            self.start(now)

        return int(
            (now - self._t0) / self._period
            + 1e-9
        )

    def block_times(self, now):
        """Devuelve los instantes pendientes de callbacks DMA."""

        return [
            self._t0 + k * self._period
            for k in range(
                self._frames_done + 1,
                self._due(now) + 1,
            )
        ]

    # =========================================================================
    # SELECCIÓN DEL TIPO DE TRAMA
    # =========================================================================

    def _audio_frame_type(self):
        """
        Devuelve el tipo de trama según el canal seleccionado.
        """

        return {
            "LR": FrameType.AUDIO_STEREO,
            "L": FrameType.AUDIO_L,
            "R": FrameType.AUDIO_R,
        }[self.stream_channel]

    def _channel_count(self):
        """Cantidad de canales transmitidos."""

        return (
            2
            if self.stream_channel == "LR"
            else 1
        )

    # =========================================================================
    # GENERACIÓN DE TRAMAS
    # =========================================================================

    def tick(self, now):
        """
        Atiende los callbacks DMA pendientes.

        Genera tramas PCM24 según el modo seleccionado:
            LR -> estéreo
            L  -> mono CH1
            R  -> mono CH2

        Si el buffer está lleno, descarta tramas completas
        y mantiene el avance del contador de secuencia.
        """

        due = self._due(now)

        todo = due - self._frames_done

        if todo <= 0:
            return

        self._frames_done = due

        # ---------------------------------------------------------------------
        # Si no hay transmisión, avanzar los generadores
        # ---------------------------------------------------------------------

        if not self.stream_on:

            self._advance(todo)

            return

        # ---------------------------------------------------------------------
        # Tipo de trama y tamaño
        # ---------------------------------------------------------------------

        frame_type = self._audio_frame_type()

        channels = self._channel_count()

        bytes_per_frame = (
            channels * BYTES_PER_SAMPLE
        )

        frame_size = (
            HEADER_SIZE
            + self.block * bytes_per_frame
        )

        # ---------------------------------------------------------------------
        # Generar bloques pendientes
        # ---------------------------------------------------------------------

        for k in range(todo):

            # -----------------------------------------------------------------
            # Verificar espacio en buffer
            # -----------------------------------------------------------------

            available = (
                self.ring_size
                - len(self._tx)
            )

            if available < frame_size:

                remaining = todo - k

                self.stream_dropped += remaining

                self._seq = (
                    self._seq + remaining
                ) & 0xFF

                self._advance(remaining)

                return

            # -----------------------------------------------------------------
            # Generar ambos canales internamente
            # -----------------------------------------------------------------

            samples = self._render_block()

            # -----------------------------------------------------------------
            # Seleccionar canales transmitidos
            # -----------------------------------------------------------------

            if self.stream_channel == "L":

                selected = samples[:, 0:1]

            elif self.stream_channel == "R":

                selected = samples[:, 1:2]

            else:

                selected = samples

            # -----------------------------------------------------------------
            # Codificar PCM24
            # -----------------------------------------------------------------

            payload = encode_audio(
                selected,
                frame_type=frame_type,
            )

            # -----------------------------------------------------------------
            # Construir trama binaria
            # -----------------------------------------------------------------

            frame = pack_frame(
                frame_type,
                self._seq,
                payload,
                n=self.block,
            )

            # -----------------------------------------------------------------
            # Guardar en buffer
            # -----------------------------------------------------------------

            self._tx += frame

            # -----------------------------------------------------------------
            # Avanzar secuencia
            # -----------------------------------------------------------------

            self._seq = (
                self._seq + 1
            ) & 0xFF

    # =========================================================================
    # BUFFER DE TRANSMISIÓN USB
    # =========================================================================

    @property
    def tx_available(self):
        """Cantidad de bytes pendientes de transmisión."""

        return len(self._tx)

    def take(self, max_bytes):
        """Extrae hasta max_bytes del buffer USB."""

        data = bytes(
            self._tx[:max_bytes]
        )

        del self._tx[:max_bytes]

        return data

    def clear_tx(self):
        """Limpia el buffer de transmisión."""

        self._tx.clear()

    def _push_text(self, text):
        """Genera una trama de texto."""

        payload = text.encode("ascii")

        frame_size = (
            HEADER_SIZE + len(payload)
        )

        available = (
            self.ring_size - len(self._tx)
        )

        if available >= frame_size:

            self._tx += pack_frame(
                FrameType.TEXT,
                self._seq,
                payload,
            )

        else:

            self.stream_dropped += 1

        self._seq = (
            self._seq + 1
        ) & 0xFF

    # =========================================================================
    # RECEPCIÓN DE COMANDOS USB
    # =========================================================================

    def receive(self, data):
        """
        Recibe comandos ASCII terminados en '\\n'.

        Simula el buffer de recepción del firmware.
        """

        for byte in data:

            if byte == 0x0A:

                line = self._rx.decode(
                    "latin-1"
                )

                self._rx.clear()

                self.commands_seen.append(line)

                self._parse_command(line)

            elif len(self._rx) < USB_RX_BUFFER - 1:

                self._rx.append(byte)

            else:

                self.rx_overflows += 1

                self._rx.clear()

    # =========================================================================
    # INTERPRETACIÓN DE COMANDOS
    # =========================================================================

    def _parse_command(self, cmd):
        """
        Interpreta los comandos recibidos.

        Los comandos desconocidos se ignoran,
        igual que en el firmware original.
        """

        ch = {
            "L": 0,
            "R": 1,
        }.get(cmd[:1])

        # ---------------------------------------------------------------------
        # Frecuencia
        # ---------------------------------------------------------------------

        if ch is not None and cmd[1:6] == "FREQ:":

            self.freq[ch] = _atof(
                cmd[6:]
            )

        # ---------------------------------------------------------------------
        # Amplitud
        # ---------------------------------------------------------------------

        elif ch is not None and cmd[1:5] == "AMP:":

            self.amp[ch] = int(
                _atof(cmd[5:])
            )

        # ---------------------------------------------------------------------
        # Encendido de salida
        # ---------------------------------------------------------------------

        elif ch is not None and cmd[1:] == "ON":

            self.on[ch] = True

        elif ch is not None and cmd[1:] == "OFF":

            self.on[ch] = False

        # ---------------------------------------------------------------------
        # Forma de onda
        # ---------------------------------------------------------------------

        elif ch is not None and cmd[1:6] == "WAVE:":

            try:

                self.wave[ch] = Waveform(
                    int(_atof(cmd[6:]))
                )

            except ValueError:

                self.ignored.append(cmd)

        # ---------------------------------------------------------------------
        # Chirp
        # ---------------------------------------------------------------------

        elif ch is not None and cmd[1:7] == "CHIRP:":

            parts = [
                _atof(part)
                for part in cmd[7:].split(",")
            ]

            if (
                len(parts) == 3
                and all(part > 0 for part in parts)
            ):

                self.chirp[ch] = tuple(parts)

                self._chirp_t[ch] = 0.0

            else:

                self.ignored.append(cmd)

        # ---------------------------------------------------------------------
        # Configuración del códec
        # ---------------------------------------------------------------------

        elif cmd == "DIFF":

            self.differential = True

        elif cmd == "SE":

            self.differential = False

        elif cmd.startswith("ADC:"):

            self.adc_on = (
                _atof(cmd[4:]) != 0
            )

        elif cmd.startswith("DAC:"):

            self.dac_on = (
                _atof(cmd[4:]) != 0
            )

        # ---------------------------------------------------------------------
        # TRANSMISIÓN - PROTOCOLO ACTUALIZADO
        # ---------------------------------------------------------------------

        elif cmd in (
            "STREAM:1",
            "STREAM:L",
            "STREAM:R",
        ):

            self.stream_on = True

            self.stream_channel = {
                "STREAM:1": "LR",
                "STREAM:L": "L",
                "STREAM:R": "R",
            }[cmd]

        elif cmd == "STREAM:0":

            self.stream_on = False

        # ---------------------------------------------------------------------
        # PING / PONG
        # ---------------------------------------------------------------------

        elif cmd == "PING":

            self._push_text("PONG")

        # ---------------------------------------------------------------------
        # Comando desconocido
        # ---------------------------------------------------------------------

        else:

            self.ignored.append(cmd)

    # =========================================================================
    # GENERADORES DE SEÑALES
    # =========================================================================

    def _generator(self, ch, n):
        """
        Genera n muestras para un canal.

        Formas de onda:
            SINE
            SQUARE
            TRIANGLE
            CHIRP
        """

        if self.wave[ch] == Waveform.CHIRP:

            f0, f1, duration = self.chirp[ch]

            t = (
                self._chirp_t[ch]
                + np.arange(n) / self.fs
            ) % duration

            self._chirp_t[ch] = (
                self._chirp_t[ch]
                + n / self.fs
            ) % duration

            return np.sin(
                2.0 * math.pi
                * (
                    f0 * t
                    + 0.5
                    * (f1 - f0)
                    / duration
                    * t * t
                )
            )

        # ---------------------------------------------------------------------
        # Fase
        # ---------------------------------------------------------------------

        dphi = (
            2.0
            * math.pi
            * self.freq[ch]
            / self.fs
        )

        phase = (
            self._phase[ch]
            + dphi * np.arange(n)
        )

        self._phase[ch] = (
            self._phase[ch]
            + dphi * n
        ) % (2.0 * math.pi)

        sine = np.sin(phase)

        # ---------------------------------------------------------------------
        # Cuadrada
        # ---------------------------------------------------------------------

        if self.wave[ch] == Waveform.SQUARE:

            return np.where(
                sine >= 0.0,
                1.0,
                -1.0,
            )

        # ---------------------------------------------------------------------
        # Triangular
        # ---------------------------------------------------------------------

        if self.wave[ch] == Waveform.TRIANGLE:

            return (
                2.0 / math.pi
            ) * np.arcsin(sine)

        # ---------------------------------------------------------------------
        # Senoidal
        # ---------------------------------------------------------------------

        return sine

    # =========================================================================
    # AVANCE TEMPORAL SIN GENERAR MUESTRAS
    # =========================================================================

    def _advance(self, frames):
        """
        Avanza las fases cuando no se generan muestras
        o cuando se descartan tramas.
        """

        n = frames * self.block

        for ch in (0, 1):

            self._phase[ch] = (
                self._phase[ch]
                + 2.0
                * math.pi
                * self.freq[ch]
                / self.fs
                * n
            ) % (2.0 * math.pi)

            duration = self.chirp[ch][2]

            self._chirp_t[ch] = (
                self._chirp_t[ch]
                + n / self.fs
            ) % duration

    # =========================================================================
    # SIMULACIÓN DEL ADC
    # =========================================================================

    def _render_block(self):
        """
        Genera un bloque estéreo (N, 2).

        El simulador produce ambos canales internamente.
        Luego tick() selecciona cuáles transmitir.
        """

        output = np.zeros(
            (self.block, 2),
            dtype=np.float64,
        )

        for ch in (0, 1):

            signal = self._generator(
                ch,
                self.block,
            )

            if (
                self.on[ch]
                and self.dac_on
                and self.adc_on
            ):

                output[:, ch] = (
                    self.loopback
                    * (self.amp[ch] / 100.0)
                    * signal
                )

            if self.adc_on:

                output[:, ch] += (
                    self.noise_channels[ch]
                    * self._rng.standard_normal(
                        self.block
                    )
                )

            if self.adc_on:
                output[:, ch] += self.offset[ch]

        return output


# =============================================================================
# TRANSPORTE SIMULADO
# =============================================================================

class SimulatedTransport(Transport):
    """
    Implementa la interfaz Transport utilizando FakeBlackPill.

    Permite probar DeviceSession y el parser sin hardware.

    Parámetros:
        device:
            Instancia de FakeBlackPill.

        read_timeout:
            Tiempo máximo de espera por datos.

        max_chunk:
            Tamaño máximo de fragmentos recibidos.
            0 significa sin fragmentación artificial.

        clock:
            Función de reloj.

        sleep:
            Función de espera.

        seed:
            Semilla para fragmentación aleatoria.

        host_buffer:
            Capacidad del buffer del sistema operativo.
    """

    def __init__(
        self,
        device=None,
        read_timeout=0.05,
        max_chunk=0,
        clock=time.perf_counter,
        sleep=time.sleep,
        seed=None,
        host_buffer=RX_BUFFER_BYTES,
    ):

        self.device = (
            device
            if device is not None
            else FakeBlackPill()
        )

        self.read_timeout = read_timeout

        self.max_chunk = max_chunk

        self.host_buffer = int(host_buffer)

        self.description = "Black Pill simulada"

        self._clock = clock

        self._sleep = sleep

        self._rng = np.random.default_rng(seed)

        self._host = bytearray()

        self._open = False

    # =========================================================================
    # ESTADO
    # =========================================================================

    @property
    def is_open(self):
        return self._open

    def open(self):
        """Abre el transporte simulado."""

        self.device.start(
            self._clock()
        )

        self._host.clear()

        self._open = True

    def close(self):
        """Cierra el transporte simulado."""

        self._open = False

    # =========================================================================
    # SINCRONIZACIÓN
    # =========================================================================

    def _sync(self, now):
        """
        Avanza el simulador hasta el instante indicado.

        Con buffer de host, transfiere datos después
        de cada callback DMA.
        """

        device = self.device

        if self.host_buffer > 0:

            for timestamp in device.block_times(now):

                device.tick(timestamp)

                self._to_host()

        device.tick(now)

        self._to_host()

    # =========================================================================
    # TRANSFERENCIA AL BUFFER DEL HOST
    # =========================================================================

    def _to_host(self):
        """Transfiere bytes pendientes al buffer del host."""

        room = (
            self.host_buffer
            - len(self._host)
        )

        if (
            room > 0
            and self.device.tx_available
        ):

            self._host += self.device.take(
                room
            )

    def _available(self):
        """Bytes disponibles para lectura."""

        return (
            len(self._host)
            + self.device.tx_available
        )

    def _take(self, n):
        """Extrae hasta n bytes disponibles."""

        output = bytes(
            self._host[:n]
        )

        del self._host[:n]

        if len(output) < n:

            output += self.device.take(
                n - len(output)
            )

            if self.adc_on:
                output[:, ch] += self.offset[ch]

        return output

    # =========================================================================
    # LECTURA
    # =========================================================================

    def read(self):
        """
        Lee datos del transporte simulado.

        Puede devolver fragmentos de tamaño variable
        para comprobar el reensamblado del parser.
        """

        if not self._open:

            raise LinkLost(
                "El puerto simulado está cerrado."
            )

        deadline = (
            self._clock()
            + self.read_timeout
        )

        while True:

            now = self._clock()

            self._sync(now)

            if self._available():
                break

            if now >= deadline:
                return b""

            self._sleep(
                min(
                    0.0005,
                    max(
                        deadline - now,
                        0.0,
                    ),
                )
            )

        n = self._available()

        if self.max_chunk > 0:

            n = min(
                n,
                int(
                    self._rng.integers(
                        1,
                        self.max_chunk + 1,
                    )
                ),
            )

        return self._take(n)

    # =========================================================================
    # ESCRITURA
    # =========================================================================

    def write(self, data):
        """
        Envía comandos a la Blackpill simulada.
        """

        if not self._open:

            raise LinkLost(
                "El puerto simulado está cerrado."
            )

        # Generar lo pendiente antes del comando
        self._sync(
            self._clock()
        )

        self.device.receive(
            bytes(data)
        )

        # Transferir respuestas inmediatas
        self._to_host()

    # =========================================================================
    # LIMPIEZA DE ENTRADA
    # =========================================================================

    def reset_input(self):
        """Descarta datos pendientes de recepción."""

        self._sync(
            self._clock()
        )

        self._host.clear()

        self.device.clear_tx()
