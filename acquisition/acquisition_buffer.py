
"""
===============================================================================
BUFFER CIRCULAR DE ADQUISICIÓN
===============================================================================

Proyecto: Osciloscopio Digital - oscilloscope_pf
Archivo: acquisition/acquisition_buffer.py

Descripción:
    Buffer circular para almacenar muestras adquiridas continuamente.

Características:
    - Almacenamiento en formato float32.
    - Capacidad fija e independiente de Time/div.
    - Escritura circular sin desplazar el historial.
    - Conserva las muestras más recientes.
    - Compatible con datos mono de Blackpill.
    - Lectura cronológica mediante get_data().
    - Permite obtener las últimas N muestras.
    - Preparado para utilizar un buffer independiente por canal.

Importante:
    Esta clase almacena un único canal.

    Para adquirir CH1 y CH2 simultáneamente, AcquisitionManager
    debe crear dos instancias independientes de AcquisitionBuffer.

===============================================================================
"""

import numpy as np


class AcquisitionBuffer:
    """
    Buffer circular de adquisición para un único canal.

    Parámetros
    ----------
    size : int
        Capacidad máxima del buffer, expresada en muestras.

    Atributos
    ---------
    size : int
        Capacidad total.

    buffer : np.ndarray
        Memoria circular de muestras float32.

    valid_samples : int
        Cantidad de muestras válidas almacenadas.

    write_index : int
        Posición donde se escribirá la siguiente muestra.
    """

    DEFAULT_SIZE = 1_048_576

    # ========================================================================
    # INICIALIZACIÓN
    # ========================================================================

    def __init__(self, size=DEFAULT_SIZE):

        self.size = int(size)

        if self.size <= 0:
            raise ValueError(
                "El tamaño del buffer debe ser positivo."
            )

        # Reservar memoria una sola vez
        self.buffer = np.zeros(
            self.size,
            dtype=np.float32
        )

        # Cantidad de muestras válidas
        self.valid_samples = 0

        # Próxima posición de escritura
        self.write_index = 0

    # ========================================================================
    # LIMPIEZA
    # ========================================================================

    def clear(self):
        """
        Reinicia el buffer circular.

        Elimina el historial válido y reinicia
        el índice de escritura.
        """

        self.buffer.fill(0)

        self.valid_samples = 0

        self.write_index = 0

    # ========================================================================
    # ESCRITURA DE MUESTRAS
    # ========================================================================

    def add_samples(self, samples):
        """
        Agrega muestras al buffer circular.

        Parámetros
        ----------
        samples : array-like
            Vector de muestras mono con forma (N,).

        Funcionamiento
        --------------
        - Si hay espacio hasta el final, escribe directamente.
        - Si llega al final, continúa desde el comienzo.
        - Si el bloque supera la capacidad, conserva
          únicamente las últimas muestras.

        No admite arrays estéreo (N, 2).
        """

        # Convertir a NumPy float32
        samples = np.asarray(
            samples,
            dtype=np.float32
        )

        # --------------------------------------------------------
        # Validar que sea un único canal
        # --------------------------------------------------------

        if samples.ndim != 1:
            raise ValueError(
                "AcquisitionBuffer solo admite muestras "
                "mono con forma (N,). "
                f"Forma recibida: {samples.shape}"
            )

        n = samples.size

        # --------------------------------------------------------
        # No hay muestras nuevas
        # --------------------------------------------------------

        if n == 0:
            return

        # --------------------------------------------------------
        # Bloque igual o mayor a la capacidad
        # --------------------------------------------------------

        if n >= self.size:

            # Conservar únicamente las últimas muestras
            self.buffer[:] = samples[-self.size:]

            self.valid_samples = self.size

            # El historial quedó ordenado desde índice 0
            self.write_index = 0

            return

        # --------------------------------------------------------
        # Escritura circular
        # --------------------------------------------------------

        # Muestras que caben antes del final
        first = min(
            n,
            self.size - self.write_index
        )

        self.buffer[
            self.write_index:self.write_index + first
        ] = samples[:first]

        # --------------------------------------------------------
        # Si el bloque cruza el final
        # --------------------------------------------------------

        remaining = n - first

        if remaining > 0:

            self.buffer[:remaining] = samples[first:]

        # --------------------------------------------------------
        # Actualizar índice de escritura
        # --------------------------------------------------------

        self.write_index = (
            self.write_index + n
        ) % self.size

        # --------------------------------------------------------
        # Actualizar cantidad válida
        # --------------------------------------------------------

        self.valid_samples = min(
            self.size,
            self.valid_samples + n
        )

    # ========================================================================
    # LECTURA DE MUESTRAS
    # ========================================================================

    def get_data(self, count=None):
        """
        Devuelve las muestras en orden cronológico.

        Parámetros
        ----------
        count : int o None
            None:
                Devuelve todo el historial válido.

            N:
                Devuelve las últimas N muestras disponibles.

        Retorna
        -------
        np.ndarray
            Vector float32 independiente del buffer interno.

        El orden es:
            muestra más antigua -> muestra más reciente.
        """

        # Cantidad total válida
        n = self.valid_samples

        # --------------------------------------------------------
        # Limitar cantidad solicitada
        # --------------------------------------------------------

        if count is not None:

            n = min(
                n,
                max(0, int(count))
            )

        # --------------------------------------------------------
        # Buffer vacío
        # --------------------------------------------------------

        if n == 0:

            return np.empty(
                0,
                dtype=np.float32
            )

        # --------------------------------------------------------
        # Determinar inicio del historial solicitado
        # --------------------------------------------------------

        start = (
            self.write_index - n
        ) % self.size

        end = start + n

        # --------------------------------------------------------
        # Lectura sin cruzar el final
        # --------------------------------------------------------

        if end <= self.size:

            return self.buffer[
                start:end
            ].copy()

        # --------------------------------------------------------
        # Lectura cruzando el final
        # --------------------------------------------------------

        first = self.buffer[start:]

        second = self.buffer[
            :end - self.size
        ]

        return np.concatenate(
            (first, second)
        )

    # ========================================================================
    # ESTADO DEL BUFFER
    # ========================================================================

    def is_full(self):
        """
        Indica si el buffer alcanzó su capacidad.
        """

        return (
            self.valid_samples == self.size
        )
