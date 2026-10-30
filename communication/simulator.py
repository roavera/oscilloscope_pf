"""
Black Pill SIMULADA: habla el mismo protocolo que el firmware real, pero sin hardware. Sirve para desarrollar y
probar el programa sin la placa (y para las pruebas automáticas).

  FakeBlackPill       el "firmware": recibe comandos como CDC_Receive_FS + parse_command, genera el audio
                      a la cadencia del DMA (una trama de 256 frames cada 2,62 ms), lo guarda en un ring de
                      16 kB y descarta tramas enteras cuando el ring se llena (stream.c: begin_frame).
  SimulatedTransport  lo enchufa como un Transport (lo que usa DeviceSession en lugar del puerto serie).

Qué imita y qué no: imita el FORMATO de las tramas, el seq (que sube también en las descartadas), el buffer de
128 bytes de los comandos, que un comando desconocido se ignora en silencio y que PING contesta una trama de
texto "PONG". NO imita los tiempos del lazo principal ni el comportamiento analógico del códec: la salida del
DAC vuelve al ADC por un "cable" ideal (parámetro `loopback`), más un piso de ruido.

Valores de arranque (los mismos que la simulación del viaje de datos): 1000 Hz, 50 %, salidas encendidas,
stream apagado hasta recibir STREAM:1.
"""
from __future__ import annotations

import math
import re
import time

import numpy as np

from .commands import Waveform
from .errors import LinkLost
from .protocol import FIRMWARE_FS, FrameType, HEADER_SIZE, BYTES_PER_FRAME, pack_frame, encode_audio
from .transport import RX_BUFFER_BYTES, Transport

DEFAULT_FS = FIRMWARE_FS      # fs del I2S del firmware [Hz]
FRAMES_PER_BLOCK = 256        # frames que entrega cada callback del DMA
RING_SIZE = 16384             # ring de stream.c [bytes]
USB_RX_BUFFER = 128           # usb_rx_buffer del firmware

_FLOAT_PREFIX = re.compile(r"\s*[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?")


def _atof(text):
    """Como atof() de C: toma el número del principio del texto y, si no hay, devuelve 0."""
    m = _FLOAT_PREFIX.match(text)
    return float(m.group(0)) if m else 0.0


class FakeBlackPill:
    def __init__(self, fs=DEFAULT_FS, frames_per_block=FRAMES_PER_BLOCK, ring_size=RING_SIZE,
                 loopback=1.0, noise_dbfs=-110.0, seed=1):
        self.fs = float(fs)
        self.block = int(frames_per_block)
        self.ring_size = int(ring_size)
        self.loopback = float(loopback)                  # ganancia del "cable" salida -> entrada (0 = entrada al aire)
        self.noise = 10.0 ** (noise_dbfs / 20.0)         # ruido blanco en la entrada [RMS, fracción del fondo de escala]
        self._rng = np.random.default_rng(seed)

        # Lo que cambian los comandos
        self.freq = [1000.0, 1000.0]
        self.amp = [50, 50]
        self.on = [True, True]
        self.wave = [Waveform.SINE, Waveform.SINE]
        self.chirp = [(200.0, 2000.0, 1.0), (200.0, 2000.0, 1.0)]
        self.adc_on = True
        self.dac_on = True
        self.differential = True
        self.stream_on = False

        # Lo que pasó (para las pruebas)
        self.commands_seen = []                          # líneas completas recibidas
        self.ignored = []                                # las que no coincidieron con ningún comando
        self.rx_overflows = 0                            # veces que una línea desbordó el buffer de 128 bytes
        self.stream_dropped = 0                          # tramas descartadas por ring lleno (stream_dropped del firmware)

        # USB
        self._rx = bytearray()                           # usb_rx_buffer
        self._tx = bytearray()                           # ring de transmisión
        self._seq = 0

        # Reloj del DMA y estado de los generadores
        self._period = self.block / self.fs              # 2,62 ms
        self._t0 = None
        self._frames_done = 0
        self._phase = [0.0, 0.0]                         # fase de cada generador [rad]
        self._chirp_t = [0.0, 0.0]                       # segundos dentro del barrido de cada canal

    # ==================================================================================
    #  Reloj
    # ==================================================================================
    def start(self, now):
        self._t0 = float(now)
        self._frames_done = 0

    def _due(self, now):
        if self._t0 is None:
            self.start(now)
        return int((now - self._t0) / self._period + 1e-9)       # la tolerancia evita perder una trama por redondeo

    def block_times(self, now):
        """Los instantes, hasta `now`, en que vence cada callback del DMA que todavía no se atendió."""
        return [self._t0 + k * self._period for k in range(self._frames_done + 1, self._due(now) + 1)]

    def tick(self, now):
        """Atiende los callbacks del DMA que vencieron hasta `now` (las tramas nuevas quedan en el ring)."""
        due = self._due(now)
        todo = due - self._frames_done
        if todo <= 0:
            return
        self._frames_done = due
        if not self.stream_on:
            self._advance(todo)                          # el generador sigue andando aunque nadie lo escuche
            return
        size = HEADER_SIZE + self.block * BYTES_PER_FRAME
        for k in range(todo):
            if self.ring_size - len(self._tx) < size:
                rest = todo - k                          # ring lleno: se descartan enteras y el seq avanza igual
                self.stream_dropped += rest
                self._seq = (self._seq + rest) & 0xFF
                self._advance(rest)
                return
            payload = encode_audio(self._render_block())
            self._tx += pack_frame(FrameType.AUDIO, self._seq, payload, n=self.block)
            self._seq = (self._seq + 1) & 0xFF

    # ==================================================================================
    #  USB hacia la PC (ring de transmisión)
    # ==================================================================================
    @property
    def tx_available(self):
        return len(self._tx)

    def take(self, max_bytes):
        """Lo que el USB se lleva del ring (hasta max_bytes)."""
        data = bytes(self._tx[:max_bytes])
        del self._tx[:max_bytes]
        return data

    def clear_tx(self):
        self._tx.clear()

    def _push_text(self, text):
        payload = text.encode("ascii")
        if self.ring_size - len(self._tx) >= HEADER_SIZE + len(payload):
            self._tx += pack_frame(FrameType.TEXT, self._seq, payload)
        else:
            self.stream_dropped += 1
        self._seq = (self._seq + 1) & 0xFF               # el seq sube aunque la trama se descarte

    # ==================================================================================
    #  USB desde la PC (comandos): CDC_Receive_FS + parse_command
    # ==================================================================================
    def receive(self, data):
        for c in data:
            if c == 0x0A:                                # '\n': la línea está completa
                line = self._rx.decode("latin-1")
                self._rx.clear()
                self.commands_seen.append(line)
                self._parse_command(line)
            elif len(self._rx) < USB_RX_BUFFER - 1:
                self._rx.append(c)
            else:                                        # buffer lleno: se descarta lo acumulado (y este carácter)
                self.rx_overflows += 1
                self._rx.clear()

    def _parse_command(self, cmd):
        ch = {"L": 0, "R": 1}.get(cmd[:1])
        if ch is not None and cmd[1:6] == "FREQ:":
            self.freq[ch] = _atof(cmd[6:])
        elif ch is not None and cmd[1:5] == "AMP:":
            self.amp[ch] = int(_atof(cmd[5:]))
        elif ch is not None and cmd[1:] == "ON":
            self.on[ch] = True
        elif ch is not None and cmd[1:] == "OFF":
            self.on[ch] = False
        elif ch is not None and cmd[1:6] == "WAVE:":
            try:
                self.wave[ch] = Waveform(int(_atof(cmd[6:])))
            except ValueError:
                self.ignored.append(cmd)
        elif ch is not None and cmd[1:7] == "CHIRP:":
            parts = [_atof(p) for p in cmd[7:].split(",")]
            if len(parts) == 3 and all(p > 0 for p in parts):
                self.chirp[ch] = tuple(parts)
                self._chirp_t[ch] = 0.0
            else:
                self.ignored.append(cmd)
        elif cmd == "DIFF":
            self.differential = True
        elif cmd == "SE":
            self.differential = False
        elif cmd.startswith("ADC:"):
            self.adc_on = _atof(cmd[4:]) != 0
        elif cmd.startswith("DAC:"):
            self.dac_on = _atof(cmd[4:]) != 0
        elif cmd == "STREAM:1":
            self.stream_on = True
        elif cmd == "STREAM:0":
            self.stream_on = False
        elif cmd == "PING":
            self._push_text("PONG")
        else:
            self.ignored.append(cmd)                     # el firmware real también los ignora, sin avisar

    # ==================================================================================
    #  Generador y entrada
    # ==================================================================================
    def _generator(self, ch, n):
        """n muestras del generador del canal (avanza su fase). Forma de onda de -1 a 1."""
        if self.wave[ch] == Waveform.CHIRP:
            f0, f1, dur = self.chirp[ch]
            t = (self._chirp_t[ch] + np.arange(n) / self.fs) % dur
            self._chirp_t[ch] = (self._chirp_t[ch] + n / self.fs) % dur
            return np.sin(2.0 * math.pi * (f0 * t + 0.5 * (f1 - f0) / dur * t * t))
        dphi = 2.0 * math.pi * self.freq[ch] / self.fs
        ph = self._phase[ch] + dphi * np.arange(n)
        self._phase[ch] = (self._phase[ch] + dphi * n) % (2.0 * math.pi)
        s = np.sin(ph)
        if self.wave[ch] == Waveform.SQUARE:
            return np.where(s >= 0.0, 1.0, -1.0)
        if self.wave[ch] == Waveform.TRIANGLE:
            return (2.0 / math.pi) * np.arcsin(s)
        return s

    def _advance(self, frames):
        """Avanza los generadores `frames` callbacks sin calcular la señal (para saltear tramas descartadas)."""
        n = frames * self.block
        for ch in (0, 1):
            self._phase[ch] = (self._phase[ch] + 2.0 * math.pi * self.freq[ch] / self.fs * n) % (2.0 * math.pi)
            dur = self.chirp[ch][2]
            self._chirp_t[ch] = (self._chirp_t[ch] + n / self.fs) % dur

    def _render_block(self):
        """(block, 2): lo que ve el ADC en un callback."""
        out = np.zeros((self.block, 2))
        for ch in (0, 1):
            y = self._generator(ch, self.block)
            if self.on[ch] and self.dac_on and self.adc_on:
                out[:, ch] = self.loopback * (self.amp[ch] / 100.0) * y
            if self.adc_on:
                out[:, ch] += self.noise * self._rng.standard_normal(self.block)
        return out


# ======================================================================================
#  Como Transport
# ======================================================================================
class SimulatedTransport(Transport):
    """
    La FakeBlackPill vista como un puerto. Sin hilos: cada read() mira el reloj, hace que la placa produzca lo que
    venció y entrega lo disponible. `clock` y `sleep` se pueden reemplazar (las pruebas usan un reloj falso que
    avanza solo, así corren al instante). Si `max_chunk` > 0, las lecturas devuelven trozos de tamaño aleatorio
    para ejercitar el reensamblado de tramas partidas.

    `host_buffer` imita el buffer de recepción del sistema operativo (en Windows se le piden 1 MB, ver
    transport.RX_BUFFER_BYTES): el controlador USB va vaciando el ring de la placa trama a trama aunque el
    programa tarde en leer, y recién se pierden tramas si ese buffer también se llena (un corte de ~1,7 s).
    Con host_buffer=0 no hay buffer intermedio y la placa descarta apenas su ring de 16 kB (~28 ms) se llena:
    sirve para probar las pérdidas.
    """

    def __init__(self, device=None, read_timeout=0.05, max_chunk=0, clock=time.perf_counter, sleep=time.sleep,
                 seed=None, host_buffer=RX_BUFFER_BYTES):
        self.device = device if device is not None else FakeBlackPill()
        self.read_timeout = read_timeout
        self.max_chunk = max_chunk
        self.host_buffer = int(host_buffer)
        self.description = "Black Pill simulada"
        self._clock = clock
        self._sleep = sleep
        self._rng = np.random.default_rng(seed)
        self._host = bytearray()                         # lo que el sistema operativo ya recibió y el programa no leyó
        self._open = False

    @property
    def is_open(self):
        return self._open

    def open(self):
        self.device.start(self._clock())
        self._host.clear()
        self._open = True

    def close(self):
        self._open = False

    # --- la placa y el buffer del host ----------------------------------------------
    def _sync(self, now):
        """Hace avanzar la placa hasta `now`; con buffer del host, lo vacía hacia allí en cada trama."""
        dev = self.device
        if self.host_buffer > 0:
            for t in dev.block_times(now):
                dev.tick(t)
                self._to_host()
        dev.tick(now)
        self._to_host()

    def _to_host(self):
        room = self.host_buffer - len(self._host)
        if room > 0 and self.device.tx_available:
            self._host += self.device.take(room)

    def _available(self):
        return len(self._host) + self.device.tx_available

    def _take(self, n):
        out = bytes(self._host[:n])
        del self._host[:n]
        if len(out) < n:
            out += self.device.take(n - len(out))
        return out

    # --- Transport ------------------------------------------------------------------
    def read(self):
        if not self._open:
            raise LinkLost("El puerto simulado está cerrado.")
        deadline = self._clock() + self.read_timeout
        while True:
            now = self._clock()
            self._sync(now)
            if self._available():
                break
            if now >= deadline:
                return b""
            self._sleep(min(0.0005, max(deadline - now, 0.0)))
        n = self._available()
        if self.max_chunk > 0:
            n = min(n, int(self._rng.integers(1, self.max_chunk + 1)))
        return self._take(n)

    def write(self, data):
        if not self._open:
            raise LinkLost("El puerto simulado está cerrado.")
        self._sync(self._clock())                        # primero lo que ya venció, después el comando
        self.device.receive(bytes(data))
        self._to_host()                                  # (una respuesta inmediata, como el PONG)

    def reset_input(self):
        self._sync(self._clock())
        self._host.clear()
        self.device.clear_tx()
