"""Entrada de audio seleccionable y captura loopback."""
from __future__ import annotations

import threading


class AudioInput:
    def __init__(self, sample_rate=48000, channels=1, blocksize=2048,
                 device=None, on_error=None):
        self.sample_rate = float(sample_rate)
        self.channels = int(channels)
        self.blocksize = int(blocksize)
        self.device = device
        self.on_error = on_error
        self.stream = None
        self.callback_function = None
        self._thread = None
        self._stop_event = threading.Event()
        self._ready = threading.Event()
        self._startup_error = None

    @property
    def is_loopback(self):
        return (isinstance(self.device, (tuple, list)) and len(self.device) == 2
                and self.device[0] == "loopback")

    def _audio_callback(self, indata, frames, time, status):
        if status:
            print("STATUS ->", status)
        sample = (indata[:, 0].copy() if self.channels == 1
                  else indata[:, :2].copy())
        if self.callback_function is not None:
            self.callback_function(sample)

    def start_stream(self, callback_function):
        """Inicia captura; los bloques llegan al callback desde el backend."""
        self.callback_function = callback_function
        if self.is_loopback:
            self._start_loopback()
            return

        import sounddevice as sd
        device_id = (self.device[1]
                     if isinstance(self.device, (tuple, list))
                     and len(self.device) == 2 and self.device[0] == "input"
                     else self.device)
        self.stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            blocksize=self.blocksize,
            device=device_id,
            dtype="float32",
            callback=self._audio_callback,
        )
        self.stream.start()

    def _start_loopback(self):
        self._stop_event.clear()
        self._ready.clear()
        self._startup_error = None
        self._thread = threading.Thread(
            target=self._record_loopback, name="AudioLoopback", daemon=True
        )
        self._thread.start()
        if not self._ready.wait(timeout=8.0):
            self._stop_event.set()
            raise RuntimeError("Tiempo agotado al abrir la fuente loopback")
        if self._startup_error is not None:
            raise RuntimeError(f"No se pudo abrir loopback: {self._startup_error}") from self._startup_error

    def _record_loopback(self):
        try:
            import numpy as np
            import soundcard as sc
            microphone = sc.get_microphone(self.device[1], include_loopback=True)
            channel_info = getattr(microphone, "channels", 2)
            available = (int(channel_info) if isinstance(channel_info, int)
                         else len(channel_info))
            # WASAPI puede entregar datos corruptos al pedir un solo canal.
            capture_channels = 2 if available >= 2 else 1
            if self.channels > capture_channels:
                raise ValueError(
                    f"La fuente loopback ofrece {capture_channels} canal(es), "
                    f"pero se seleccionaron {self.channels}"
                )
            with microphone.recorder(
                samplerate=int(self.sample_rate),
                channels=capture_channels,
                blocksize=self.blocksize,
            ) as recorder:
                self._ready.set()
                while not self._stop_event.is_set():
                    data = np.asarray(
                        recorder.record(numframes=self.blocksize), dtype=np.float32
                    )
                    if data.ndim == 1:
                        data = data[:, None]
                    data = data[:, :self.channels].copy()
                    callback = self.callback_function
                    if callback is not None and data.size:
                        callback(data[:, 0] if self.channels == 1 else data)
        except Exception as exc:
            if not self._ready.is_set():
                self._startup_error = exc
            elif self.on_error is not None and not self._stop_event.is_set():
                self.on_error(exc)
        finally:
            self._ready.set()

    def stop_stream(self):
        if self.is_loopback:
            self._stop_event.set()
            thread = self._thread
            if thread is not None and thread is not threading.current_thread():
                thread.join(timeout=5.0)
                if thread.is_alive():
                    raise RuntimeError("El stream loopback no se detuvo")
            self._thread = None
            self.callback_function = None
            return
        if self.stream is not None:
            try:
                self.stream.stop()
            finally:
                self.stream.close()
                self.stream = None
        self.callback_function = None
