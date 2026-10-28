"""Gestiona la fuente activa de adquisición."""

from acquisition.audio_input import AudioInput

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
                 blocksize=2048, device=None):
        self.source = self._validate_source(source)
        self.sample_rate = float(sample_rate if sample_rate is not None
                                 else self.SAMPLE_RATES[source])
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

    @property
    def is_running(self):
        return self._running

    def change_source(self, source, sample_rate=None):
        """Detiene la fuente anterior y configura la nueva, sin iniciarla."""
        self._validate_source(source)
        new_rate = float(sample_rate if sample_rate is not None
                         else self.SAMPLE_RATES[source])
        if not 0 < new_rate < float('inf'):
            raise ValueError("Frecuencia de muestreo inválida")
        self.stop()
        self.source = source
        self.sample_rate = new_rate
        return self.sample_rate

    def start(self, callback):
        """Inicia la fuente configurada y entrega bloques al callback."""
        if self._running:
            return
        if self.source != self.AUDIO:
            raise NotImplementedError(
                f"Fuente aún no implementada: {self.source}"
            )
        backend = AudioInput(sample_rate=self.sample_rate,
                             channels=self.channels,
                             blocksize=self.blocksize, device=self.device)
        try:
            backend.start_stream(callback)
        except Exception:
            backend.stop_stream()
            raise
        self._backend = backend
        self._running = True

    def stop(self):
        """Detiene el backend; se puede llamar más de una vez."""
        backend = self._backend
        if backend is not None:
            backend.stop_stream()
        self._backend = None
        self._running = False