import numpy as np

from acquisition.acquisition_processor import AcquisitionProcessor

processor = AcquisitionProcessor()

samples = np.array(
    [0.0, 0.5, 1.0, 0.5, 0.0, -0.5, -1.0],
    dtype=np.float32,
)

resultado = processor.process(samples, channel=1)

print("Modo:", processor.get_mode())
print("Original:", samples)
print("Resultado:", resultado)

assert np.array_equal(samples, resultado)

print("Sampling funciona correctamente.")