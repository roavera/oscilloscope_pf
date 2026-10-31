"""Selecciona y administra fuentes de adquisición del osciloscopio.

El callback recibe float32 (N,) para un canal y (N,2) para dos.
Los datos de Blackpill están normalizados, NO calibrados en voltios.

Conserva start(callback), stop(), change_source(), get_data(), clear_buffers()
y configure_simulator(). USB start() ahora es ASÍNCRONO: is_connecting=True
hasta recibir audio; is_running=True solo cuando se confirma la recepción.

Notificaciones opcionales del constructor, también asignables como atributos:
  on_state_changed(state): connecting / connected / stopped / error.
  on_error(exception): fallo de apertura, lectura, callback de datos o cierre USB.
  on_discontinuity(): corte del historial ANTES del siguiente bloque de datos.

Los callbacks USB se ejecutan en el hilo lector. No tocar widgets desde ellos.
Para estado/error emitir señales Qt. Para discontinuidad limpiar el buffer del
consumidor bajo su lock aquí, o encolar corte y datos juntos y en orden.
Los callbacks deben ser rápidos y no llamar start/stop/change_source.
Usar un único hilo de control para esas operaciones (normalmente Qt).

La GUI anterior debe adaptarse: no rechazar USB porque is_running sea False
inmediatamente después de start(). No incluye reconexión automática.
CH1 usa channels=1; estéreo usa channels=2. Fs nominal: 97656.25 Hz.
Para probar la ruta USB sin placa: usb_simulated=True.

Ejemplo:
    manager = AcquisitionManager(
        source=AcquisitionManager.BLACKPILL_USB, usb_port="COM5", channels=1,
        on_state_changed=print, on_error=print,
    )
    manager.start(procesar_muestras)
    # Al cerrar, desde el hilo de control: manager.stop()

"""
from __future__ import annotations

import math
import threading
import logging
import numpy as np

from acquisition.acquisition_buffer import AcquisitionBuffer
from acquisition.blackpill_simulator import BlackpillSimulator


class _USBBackend:
    """Adaptador del lector Blackpill a la API start_stream/stop_stream."""

    def __init__(self, *, channel="L", port=None, simulated=False,
                 transport=None, on_discontinuity=None, on_state=None, on_error=None):
        from communication.worker import BlackPillReader
        self.reader = BlackPillReader(
            channel=channel, port=port, simulated=simulated,
            transport=transport,
        )
        self.on_state = on_state
        self.on_error = on_error
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
        self._thread = threading.Thread(
            target=self._run, name="BlackPillAcquisition", daemon=True
        )
        self._thread.start()

    def _run(self):
        try:
            if not self.reader.open(should_stop=self._stop_event.is_set):
                return
            if self._stop_event.is_set():
                return
            self.on_state("connected")
            while not self._stop_event.is_set():
                samples, discontinuity, offset = self.reader.read_chunk()
                if len(samples) == 0:
                    continue
                # Ante un corte, solo el sufijo posterior al último
                # corte pertenece al nuevo segmento temporal continuo.
                restart = self.reader.take_restart()
                if discontinuity or restart is not None:
                    if self.on_discontinuity is not None:
                        self.on_discontinuity()
                    cut = max(offset if discontinuity else 0, restart or 0)
                    samples = samples[cut:]
                if len(samples):
                    self._callback(samples)
        except Exception as exc:
            self.last_error = exc
            self._stop_event.set()
            self.on_error(exc)
        finally:
            try:
                self.reader.close()
            except Exception as exc:
                self.last_error = exc
                self.on_error(exc)
            finally:
                self._stop_event.set()
                if self.last_error is None:
                    self.on_state("stopped")

    def stop_stream(self):
        self._stop_event.set()
        thread = self._thread
        if thread is threading.current_thread():
            raise RuntimeError("Llamar stop() desde el hilo de control, no desde callbacks")
        if thread is not None:
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

    STOPPED = "stopped"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"

    SAMPLE_RATES = {
        AUDIO: 48000.0,
        SIMULATOR: 97656.25,
        BLACKPILL_USB: 97656.25,
    }

    def __init__(self, source=AUDIO, sample_rate=None, channels=1,
                 blocksize=2048, device=None, *, usb_port=None,
                 usb_simulated=False, usb_transport=None,
                 buffer_size=1_048_576, on_state_changed=None,
                 on_error=None, on_discontinuity=None):
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
        self._state = self.STOPPED
        self.on_state_changed = on_state_changed
        self.on_error = on_error
        self.on_discontinuity = on_discontinuity
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
    def state(self):
        with self._lock:
            return self._state

    @property
    def is_running(self):
        """True solo cuando la fuente ya está conectada."""
        return self.state == self.CONNECTED

    @property
    def is_connecting(self):
        return self.state == self.CONNECTING

    @staticmethod
    def _notify(callback, *args):
        if callback is not None:
            try:
                callback(*args)
            except Exception:
                logging.getLogger(__name__).exception("Error en notificación")

    def _set_state(self, state):
        with self._lock:
            changed = self._state != state
            self._state = state
            self._running = state == self.CONNECTED
        if changed:
            self._notify(self.on_state_changed, state)

    def _report_error(self, error):
        with self._lock:
            self.last_error = error
        self._set_state(self.ERROR)
        self._notify(self.on_error, error)

    def _discontinuity(self):
        self.clear_buffers()
        # Antes del siguiente bloque: limpiar también el buffer del consumidor.
        # Si falla, detener la captura para no mezclar segmentos discontinuos.
        if self.on_discontinuity is not None:
            self.on_discontinuity()

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
        if self.is_running or self.is_connecting:
            return
        if self._backend is not None:
            self.stop()
        self.clear_buffers()
        self.last_error = None

        if self.source == self.AUDIO:
            from acquisition.audio_input import AudioInput
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
                on_discontinuity=self._discontinuity,
                on_state=self._set_state, on_error=self._report_error,
            )
            receive = lambda x: self._ingest(x, callback, channel=channel)

        # Publicar antes de arrancar: el hilo puede fallar inmediatamente.
        self._backend = backend
        self._set_state(self.CONNECTING)
        try:
            backend.start_stream(receive)
        except Exception as exc:
            try:
                backend.stop_stream()
            finally:
                self._report_error(exc)
            raise
        if not isinstance(backend, _USBBackend):
            self._set_state(self.CONNECTED)

    def configure_simulator(self, channel=0, **kwargs):
        if self.source != self.SIMULATOR or self._backend is None:
            raise RuntimeError("El simulador debe estar iniciado")
        self._backend.configure(channel=channel, **kwargs)

    def stop(self):
        """Detiene y espera al lector desde el hilo de control.

        Conserva el backend si el cierre falla para evitar un segundo lector.
        Los transportes deben usar timeouts finitos.
        """
        backend = self._backend
        if backend is not None:
            try:
                backend.stop_stream()
            except Exception as exc:
                self._report_error(exc)
                raise
            self._backend = None
        self._set_state(self.STOPPED)
