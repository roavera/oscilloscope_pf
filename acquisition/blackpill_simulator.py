"""Generador de señales para simular el ADC de la Blackpill.

La salida del callback es un ndarray float32 de forma (N, C).
Los valores son normalizados, no voltios calibrados.
"""
import threading
import time
import numpy as np


class BlackpillSimulator:
    SAMPLE_RATE = 97656.25
    WAVEFORMS = ("sine", "square", "triangle")

    def __init__(
        self, sample_rate=SAMPLE_RATE, channels=1, blocksize=256,
        waveform="sine", frequency=1000.0, amplitude=0.5,
        offset=0.0, noise=0.0, seed=None,
    ):
        if sample_rate <= 0 or not np.isfinite(sample_rate):
            raise ValueError("sample_rate debe ser positivo y finito")
        if channels not in (1, 2):
            raise ValueError("channels debe ser 1 o 2")
        if blocksize <= 0:
            raise ValueError("blocksize debe ser positivo")

        self.sample_rate = float(sample_rate)
        self.channels = int(channels)
        self.blocksize = int(blocksize)
        self._lock = threading.RLock()
        self._rng = np.random.default_rng(seed)
        self._sample_index = 0
        self._stop_event = threading.Event()
        self._thread = None
        self._callback = None
        self._settings = [
            self._validate(waveform, frequency, amplitude, offset, noise)
            for _ in range(self.channels)
        ]

    def _validate(self, waveform, frequency, amplitude, offset, noise):
        if waveform not in self.WAVEFORMS:
            raise ValueError(f"Forma de onda inválida: {waveform}")
        values = (frequency, amplitude, offset, noise)
        if not all(np.isfinite(v) for v in values):
            raise ValueError("Los parámetros deben ser finitos")
        if not 0 <= frequency < self.sample_rate / 2:
            raise ValueError("La frecuencia debe ser menor que Nyquist")
        if amplitude < 0 or noise < 0:
            raise ValueError("Amplitud y ruido deben ser no negativos")
        return dict(waveform=waveform, frequency=float(frequency),
                    amplitude=float(amplitude), offset=float(offset),
                    noise=float(noise))

    def configure(self, channel=0, **kwargs):
        """Actualiza parámetros sin reiniciar; channel=0 (CH1) o 1 (CH2)."""
        if not 0 <= channel < self.channels:
            raise ValueError("Canal inexistente")
        with self._lock:
            settings = {**self._settings[channel], **kwargs}
            self._settings[channel] = self._validate(**settings)

    def generate_block(self, frames=None):
        """Genera muestras consecutivas, preservando fase entre bloques."""
        n = self.blocksize if frames is None else int(frames)
        if n <= 0:
            raise ValueError("frames debe ser positivo")

        with self._lock:
            indices = self._sample_index + np.arange(n, dtype=np.float64)
            result = np.empty((n, self.channels), dtype=np.float32)
            for ch, cfg in enumerate(self._settings):
                phase = np.remainder(indices * cfg["frequency"] /
                                     self.sample_rate, 1.0)
                waveform = cfg["waveform"]
                if waveform == "sine":
                    wave = np.sin(2 * np.pi * phase)
                elif waveform == "square":
                    wave = np.where(phase < 0.5, 1.0, -1.0)
                else:
                    wave = 1.0 - 4.0 * np.abs(phase - 0.5)

                signal = cfg["amplitude"] * wave + cfg["offset"]
                if cfg["noise"]:
                    signal += self._rng.normal(0, cfg["noise"], size=n)

                # Cuantización PCM signed de 24 bits, escala normalizada.
                pcm = np.clip(np.rint(signal * (2**23)), -(2**23), 2**23 - 1)
                result[:, ch] = (pcm / (2**23)).astype(np.float32)

            self._sample_index += n
            return result

    def start_stream(self, callback):
        """Entrega bloques (N, C) en un hilo, aproximadamente en tiempo real."""
        if not callable(callback):
            raise TypeError("callback debe ser una función")
        if self._thread is not None and self._thread.is_alive():
            return
        self._callback = callback
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="BlackpillSimulator", daemon=True
        )
        self._thread.start()

    def _run(self):
        period = self.blocksize / self.sample_rate
        deadline = time.perf_counter()
        while not self._stop_event.is_set():
            block = self.generate_block()
            try:
                self._callback(block)
            except Exception:
                self._stop_event.set()
                raise
            deadline += period
            wait = deadline - time.perf_counter()
            if wait > 0:
                self._stop_event.wait(wait)
            elif wait < -period:
                deadline = time.perf_counter()

    def stop_stream(self):
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        self._thread = None
        self._callback = None
