"""Gestor de fuentes de adquisición para el osciloscopio.
"""
from acquisition.audio_input import AudioInput

class AcquisitionManager:
    AUDIO = "audio"

    def __init__(self, source=AUDIO, sample_rate=48000, channels=1,
                 blocksize=2048, device=None):
        self.source = source
        self.sample_rate = float(sample_rate)
        self.channels = channels
        self.blocksize = blocksize
        self.device = device
        self._backend = None
        self._running = False

    @property
    def is_running(self):
        return self._running

    def start(self, callback):
        """Inicia la fuente y entrega cada bloque al callback."""
        if self._running:
            return

        if self.source != self.AUDIO:
            raise ValueError(
                f"Fuente de adquisición no implementada: {self.source}"
            )

        backend = AudioInput(
            sample_rate=self.sample_rate,
            channels=self.channels,
            blocksize=self.blocksize,
            device=self.device,
        )

        try:
            backend.start_stream(callback)
        except Exception:
            backend.stop_stream()
            raise

        self._backend = backend
        self._running = True

    def stop(self):
        """Detiene y libera la fuente activa."""
        backend = self._backend
        self._backend = None
        self._running = False

        if backend is not None:
            backend.stop_stream()