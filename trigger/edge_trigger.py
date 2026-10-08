"""
===============================================================================
MÓDULO DE SINCRONISMO Y DISPARO (TRIGGER ENGINE) PARA OSCILOSCOPIO DIGITAL
===============================================================================
Proyecto:       Osciloscopio y Analizador de Audio por Software (DSO)
Institución:    Facultad de Ingeniería
Descripción:
    Implementación del detector de disparo por nivel y pendiente (Edge Trigger)
    con procesamiento vectorial mediante NumPy. 
    
    Características principales:
      - Detección de flanco (Rising / Falling) vectorizada O(N).
      - Manejo dinámico de ventana temporal (Pre-trigger / Post-trigger).
      - Estimación de fase sub-muestra mediante interpolación lineal continua
        para la compensación y anulación de jitter temporal en renderizado.
      - Extracción desacoplada de memoria para desacoplar adquisición y GUI.

Entrada:        Buffer de muestras normalizadas (NumPy array 1D).
Salida:         Índice de disparo, fracción sub-muestra y ventana recortada.
===============================================================================
"""
import numpy as np

class Edge_Trigger:
    def __init__(self, level=0.0, slope="Rising", position=0.5):
        self.level = float(level)
        self.slope = slope
        self.position = float(position)
        self.fractional_offset = 0.0


    def set_level(self, level):
        self.level = float(level)

    def set_slope(self, slope):
        if slope not in ("Rising", "Falling"):
            raise ValueError("Slope must be 'Rising' or 'Falling'")
        self.slope = slope

    def set_position(self, position):
        self.position = float(np.clip(position, 0.0, 1.0))

    def find(self, data, display_samples):
        
        n_samples = len(data)
        if n_samples < display_samples or display_samples < 2:
            return None

        samples_before = int(display_samples * self.position)
        samples_after = display_samples - samples_before
        v_th = self.level

        # 1. Detección de flancos vectorizada
        if self.slope == "Rising":
            condition = (data[:-1] < v_th) & (data[1:] >= v_th)
        else:
            condition = (data[:-1] > v_th) & (data[1:] <= v_th)

        crossings = np.flatnonzero(condition)
        if crossings.size == 0:
            return None

        # 2. Filtrado vectorial de límites de buffer
        min_idx = samples_before
        max_idx = n_samples - samples_after

        valid = crossings[(crossings >= min_idx) & (crossings <= max_idx)]
        if valid.size == 0:
            return None

        # 3. Selección del cruce más reciente
        trigger_idx = int(valid[-1])

        # 4. Cálculo de fase sub-muestra
        y0 = data[trigger_idx]
        y1 = data[trigger_idx + 1]
        dy = y1 - y0
        if dy != 0.0:
            mu = (v_th - y0) / dy
            self.fractional_offset = float(np.clip(mu, 0.0, 1.0))
        else:
            self.fractional_offset = 0.0

        return trigger_idx

    def capture(self, data, trigger_index, display_samples):
        """
        Extrae y retorna el segmento de datos centrado según position.
        """
        if trigger_index is None:
            return None

        samples_before = int(display_samples * self.position)
        start = trigger_index - samples_before
        end = start + display_samples

        if start < 0 or end > len(data):
            return None

        return data[start:end].copy()