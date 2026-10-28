"""Selecciona y administra la fuente de adquisición activa."""

import math

from acquisition.audio_input import AudioInput
from acquisition.blackpill_simulator import BlackpillSimulator

class AcquisitionManager:
    AUDIO = "audio"
    SIMULATOR = "simulator"
    BLACKPILL_USB = "blackpill_usb"

    SAMPLE_RATES = {
        AUDIO: 48000.0,
        SIMULATOR: 97656.25,
        BLACKPILL_USB: 97656.25,
    }

    def __init__(
        self,
        source=AUDIO,
        sample_rate=None,
        channels=1,
        blocksize=2048,
        device=None,
    ):
        self.source = self._validate_source(source)

        self.sample_rate = float(
            sample_rate
            if sample_rate is not None
            else self.SAMPLE_RATES[source]
        )

        self._validate_rate(self.sample_rate)

        if channels not in (1, 2):
            raise ValueError("channels debe ser 1 o 2")

        self.channels = channels
        self.blocksize = blocksize
        self.device = device

        self._backend = None
        self._running = False

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
        return self._running

    def change_source(self, source, sample_rate=None):
        """Detiene la fuente anterior y configura la nueva."""
        self._validate_source(source)
        new_rate = float(
            sample_rate
            if sample_rate is not None
            else self.SAMPLE_RATES[source]
        )
        self._validate_rate(new_rate)

        self.stop()

        self.source = source
        self.sample_rate = new_rate

        return self.sample_rate

    def start(self, callback):
        """Inicia la fuente configurada."""

        if self._running:
            return

        if self.source == self.AUDIO:
            backend = AudioInput(
                sample_rate=self.sample_rate,
                channels=self.channels,
                blocksize=self.blocksize,
                device=self.device,
            )

        elif self.source == self.SIMULATOR:
            backend = BlackpillSimulator(
                sample_rate=self.sample_rate,
                channels=self.channels,
                blocksize=self.blocksize,
            )

        else:
            raise NotImplementedError(
                "La adquisición por USB COM todavía no está implementada."
            )

        try:
            backend.start_stream(callback)

        except Exception:
            backend.stop_stream()
            raise

        self._backend = backend
        self._running = True

    def configure_simulator(self, channel=0, **kwargs):
        """Modifica los parámetros del simulador activo."""

        if (
            self.source != self.SIMULATOR
            or self._backend is None
        ):
            raise RuntimeError(
                "El simulador debe estar iniciado"
            )

        self._backend.configure(
            channel=channel,
            **kwargs,
        )

    def stop(self):
        """Detiene la adquisición activa."""

        backend = self._backend

        if backend is not None:
            backend.stop_stream()

        self._backend = None
        self._running = False