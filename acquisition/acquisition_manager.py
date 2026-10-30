"""Selecciona y administra fuentes de adquisición del osciloscopio.

El callback recibe float32 (N,) para un canal y (N,2) para dos.
Los datos de Blackpill están normalizados, NO calibrados en voltios.
"""
from __future__ import annotations

import math
import threading
import numpy as np

from acquisition.acquisition_buffer import AcquisitionBuffer
from acquisition.audio_input import AudioInput
from acquisition.blackpill_simulator import BlackpillSimulator


class _USBBackend:
    """Adaptador del lector Blackpill a la API start_stream/stop_stream."""

    def __init__(self, *, channel="L", port=None, simulated=False,
                 transport=None, on_discontinuity=None):
        from communication.worker import BlackPillReader
        self.reader = BlackPillReader(
            channel=channel, port=port, simulated=simulated,
            transport=transport,
        )
        self.on_discontinuity = on_discontinuity
        self._stop_event = threading.Event()
        self._thread = None
        self._callback = None
        self.last_error = None

    def start_stream(self, callback):
        if self._thread is not None and self._thread.is_alive():
            return
        self._callback = callback
        self.last_error = None
        self._stop_event.clear()
        # La apertura espera el primer bloque; ocurre en este hilo para
        # comunicar errores de conexión directamente a start().
        opened = self.reader.open(should_stop=self._stop_event.is_set)
        if not opened:
            raise RuntimeError("Se canceló la apertura de la Blackpill")
        self._thread = threading.Thread(
            target=self._run, name="BlackPillAcquisition", daemon=True
        )
        self._thread.start()

    def _run(self):
        try:
            while not self._stop_event.is_set():
                samples, discontinuity, offset = self.reader.read_chunk()
                if len(samples) == 0:
                    continue
                # Ante un corte, solo el sufijo posterior al último
                # corte pertenece al nuevo segmento temporal continuo.
                if discontinuity:
                    if self.on_discontinuity is not None:
                        self.on_discontinuity()
                    samples = samples[offset:]
                if len(samples):
                    self._callback(samples)
        except Exception as exc:
            self.last_error = exc
            self._stop_event.set()
            print(f"Error de adquisición Blackpill: {exc}", flush=True)
        finally:
            self.reader.close()

    def stop_stream(self):
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=5.0)
            if thread.is_alive():
                raise RuntimeError("El hilo de adquisición USB no se detuvo")
        if thread is None:
            self.reader.close()
        self._thread = None
        self._callback = None


class AcquisitionManager:
    AUDIO = "audio"
    SIMULATOR = "simulator"
    BLACKPILL_USB = "blackpill_usb"

    SAMPLE_RATES = {
        AUDIO: 48000.0,
        SIMULATOR: 97656.25,
        BLACKPILL_USB: 97656.25,
    }

    def __init__(self, source=AUDIO, sample_rate=None, channels=1,
                 blocksize=2048, device=None, *, usb_port=None,
                 usb_simulated=False, usb_transport=None,
                 buffer_size=1_048_576):
        self.source = self._validate_source(source)
        self.sample_rate = float(
            self.SAMPLE_RATES[self.source] if sample_rate is None else sample_rate
        )
        self._validate_rate(self.sample_rate)
        if channels not in (1, 2):
            raise ValueError("channels debe ser 1 o 2")
        if int(blocksize) <= 0:
            raise ValueError("blocksize debe ser positivo")
        self.channels = int(channels)
        self.blocksize = int(blocksize)
        self.device = device
        self.usb_port = usb_port
        self.usb_simulated = bool(usb_simulated)
        self.usb_transport = usb_transport
        self.buffer_ch1 = AcquisitionBuffer(buffer_size)
        self.buffer_ch2 = AcquisitionBuffer(buffer_size)
        self._lock = threading.RLock()
        self._backend = None
        self._running = False
        self.last_error = None

    @classmethod
    def _validate_source(cls, source):
        if source not in cls.SAMPLE_RATES:
            raise ValueError(f"Fuente desconocida: {source}")
        return source

    @staticmethod
    def _validate_rate(rate):
        if not math.isfinite(rate) or rate <= 0:
            raise ValueError("Frecuencia de muestreo inválida")

    @property
    def is_running(self):
        return self._running and not (
            isinstance(self._backend, _USBBackend)
            and self._backend._stop_event.is_set()
        )

    def clear_buffers(self):
        with self._lock:
            self.buffer_ch1.clear()
            self.buffer_ch2.clear()

    def get_data(self, channel=0, count=None):
        """Obtiene últimas muestras de CH1 (0) o CH2 (1)."""
        if channel not in (0, 1):
            raise ValueError("channel debe ser 0 (CH1) o 1 (CH2)")
        with self._lock:
            buf = self.buffer_ch1 if channel == 0 else self.buffer_ch2
            return buf.get_data(count)

    def change_source(self, source, sample_rate=None):
        self._validate_source(source)
        new_rate = float(
            self.SAMPLE_RATES[source] if sample_rate is None else sample_rate
        )
        self._validate_rate(new_rate)
        self.stop()
        self.source = source
        self.sample_rate = new_rate
        self.clear_buffers()
        return self.sample_rate

    def _ingest(self, samples, callback, *, channel="L"):
        x = np.asarray(samples, dtype=np.float32)
        if x.size == 0:
            return
        if x.ndim == 1:
            if channel not in ("L", "R"):
                raise ValueError("Un bloque mono necesita identidad L o R")
            with self._lock:
                target = self.buffer_ch1 if channel == "L" else self.buffer_ch2
                target.add_samples(x)
            callback(x)
            return
        if x.ndim != 2 or x.shape[1] not in (1, 2):
            raise ValueError(f"Forma de muestras inválida: {x.shape}")
        if x.shape[1] == 1:
            self._ingest(x[:, 0], callback, channel=channel)
            return
        with self._lock:
            self.buffer_ch1.add_samples(x[:, 0])
            self.buffer_ch2.add_samples(x[:, 1])
        callback(x)

    def start(self, callback):
        """Inicia adquisición. callback(x) se ejecuta desde hilo de captura."""
        if not callable(callback):
            raise TypeError("callback debe ser una función")
        if self.is_running:
            return
        if self._backend is not None:
            self.stop()
        self.clear_buffers()
        self.last_error = None

        if self.source == self.AUDIO:
            backend = AudioInput(
                sample_rate=self.sample_rate, channels=self.channels,
                blocksize=self.blocksize, device=self.device,
            )
            # AudioInput actual siempre entrega CH1 como vector mono.
            receive = lambda x: self._ingest(x, callback, channel="L")
        elif self.source == self.SIMULATOR:
            backend = BlackpillSimulator(
                sample_rate=self.sample_rate, channels=self.channels,
                blocksize=self.blocksize,
            )
            receive = lambda x: self._ingest(x, callback, channel="L")
        else:
            channel = "LR" if self.channels == 2 else "L"
            backend = _USBBackend(
                channel=channel, port=self.usb_port,
                simulated=self.usb_simulated, transport=self.usb_transport,
                on_discontinuity=self.clear_buffers,
            )
            receive = lambda x: self._ingest(x, callback, channel=channel)

        try:
            backend.start_stream(receive)
        except Exception:
            backend.stop_stream()
            raise
        self._backend = backend
        self._running = True

    def configure_simulator(self, channel=0, **kwargs):
        if self.source != self.SIMULATOR or self._backend is None:
            raise RuntimeError("El simulador debe estar iniciado")
        self._backend.configure(channel=channel, **kwargs)

    def stop(self):
        """Detiene la fuente activa; puede llamarse repetidamente."""
        backend = self._backend
        if backend is None:
            self._running = False
            return
        try:
            backend.stop_stream()
        finally:
            if isinstance(backend, _USBBackend):
                self.last_error = backend.last_error
            self._backend = None
            self._running = False
