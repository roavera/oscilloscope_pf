import sounddevice as sd

class AudioInput:
    def __init__(self, sample_rate=48000, channels=1, blocksize=2048, device=None):
        self.sample_rate = sample_rate
        self.channels = channels
        self.blocksize = blocksize
        self.device = device
        self.stream = None
        self.callback_function = None
        
    def _audio_callback(self, indata, frames, time, status):
        if status:
            print("STATUS ->", status)     
        
        sample = indata[:, 0].copy()  # Tomar solo el primer canal si hay múltiples canales
                
        if self.callback_function is not None: 
            self.callback_function(sample)

    def start_stream(self, callback_function):
        """Inicia la captura de audio y llama al callback con los datos."""
        self.callback_function = callback_function
        self.stream = sd.InputStream(samplerate=self.sample_rate, channels=self.channels, blocksize=self.blocksize, device=self.device, dtype='float32', callback=self._audio_callback)
        self.stream.start() 
                
    def stop_stream(self):
        """Detiene la captura de audio."""
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
            self.stream = None