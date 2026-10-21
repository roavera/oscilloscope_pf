"""Integra adquisición, gráfico y controles del osciloscopio."""

from threading import Lock

import numpy as np

from PySide6.QtCore import QTimer, Slot
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QScrollArea,
    QWidget,
)

from acquisition.audio_input import AudioInput
from acquisition.acquisition_buffer import AcquisitionBuffer
from trigger.edge_trigger import Edge_Trigger

from gui.controls import OscilloscopeControls
from gui.oscilloscope_plot import OscilloscopePlot


class OscilloscopeWidget(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        # ============================================================
        # ADQUISICIÓN
        # ============================================================

        self.sample_rate = 48000
        self.blocksize = 2048
        self.channels = 1

        # ============================================================
        # PANTALLA Y ESCALAS
        # ============================================================

        self.horizontal_divisions = 12
        self.vertical_divisions = 8

        self.time_per_division = 0.001
        self.volts_per_division = 0.02

        # Origen del eje temporal, en segundos.
        self.horizontal_position = 0.0

        # Posición del disparo respecto del centro, en divisiones.
        self.horizontal_position_divisions = 0.0

        # Posición vertical de la traza, en divisiones.
        self.vertical_position_divisions = 0.0

        # Desplazamiento del rango visible del eje Y, en voltios.
        self.vertical_offset = 0.0

        self.display_samples = max(
            2,
            int(
                self.sample_rate
                * self.time_per_division
                * self.horizontal_divisions
            ),
        )

        # ============================================================
        # TRIGGER
        # ============================================================

        self.trigger_level = 0.0
        self.trigger_slope = "Rising"
        self.trigger_position = 0.5
        self.trigger_mode = "Auto"

        # ============================================================
        # ESTADO
        # ============================================================

        self.running = True
        self.single_mode = False
        self.trigger_found = False
        self.last_acquisition = None

        self._closed = False
        self._audio_error = None
        self._new_data = False

        self._buffer_lock = Lock()

        # Copia de la última adquisición para cambiar el recorte
        # horizontal incluso en STOP.
        self._last_display_buffer = None
        self._last_trigger_index = None
        self._last_fractional_offset = 0.0

        # ============================================================
        # COMPONENTES
        # ============================================================

        self.buffer = AcquisitionBuffer(self.sample_rate)

        self.audio = AudioInput(
            sample_rate=self.sample_rate,
            channels=self.channels,
            blocksize=self.blocksize,
        )

        self.trigger = Edge_Trigger(
            level=self.trigger_level,
            slope=self.trigger_slope,
            position=self.trigger_position,
        )

        self.controls = OscilloscopeControls()

        self.plot = OscilloscopePlot(
            horizontal_divisions=self.horizontal_divisions,
            vertical_divisions=self.vertical_divisions,
            time_per_division=self.time_per_division,
            volts_per_division=self.volts_per_division,
            trigger_level=self.trigger_level,
            trigger_position=self.trigger_position,
            horizontal_position=self.horizontal_position,
            vertical_offset=self.vertical_offset,
        )

        self.create_interface()
        self.connect_signals()

        # La interfaz se actualiza desde el hilo de Qt.
        self.display_timer = QTimer(self)
        self.display_timer.setInterval(40)
        self.display_timer.timeout.connect(self.process_data)

        self.controls.sync_settings(self)

        self.set_vertical_position(
            self.vertical_position_divisions
        )

        self.set_horizontal_position(
            self.horizontal_position_divisions
        )

        self.update_controls_state()

        app = QApplication.instance()

        if app is not None:
            app.aboutToQuit.connect(self.shutdown)

        self.start_audio()

    # ================================================================
    # INTERFAZ
    # ================================================================

    def create_interface(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Panel derecho de controles.
        self.controls_scroll = QScrollArea(self)
        self.controls_scroll.setWidgetResizable(True)
        self.controls_scroll.setWidget(self.controls)
        self.controls_scroll.setFixedWidth(490)

        layout.addWidget(self.plot, 1)
        layout.addWidget(self.controls_scroll)

    # ================================================================
    # CONEXIONES
    # ================================================================

    def connect_signals(self):
        # Control horizontal.
        self.controls.time_per_division_changed.connect(
            self.set_time_per_division
        )

        self.controls.horizontal_position_changed.connect(
            self.set_horizontal_position
        )

        self.plot.horizontal_position_changed.connect(
            self.set_horizontal_position
        )

        # Control vertical.
        self.controls.volts_per_division_changed.connect(
            self.set_volts_per_division
        )

        self.controls.vertical_position_changed.connect(
            self.set_vertical_position
        )

        self.plot.vertical_position_changed.connect(
            self.set_vertical_position
        )

        # Trigger desde el panel.
        self.controls.trigger_level_changed.connect(
            self.set_trigger_level
        )

        self.controls.trigger_slope_changed.connect(
            self.set_trigger_slope
        )

        self.controls.trigger_mode_changed.connect(
            self.set_trigger_mode
        )

        # Trigger desde el gráfico.
        self.plot.trigger_level_changed.connect(
            self.set_trigger_level
        )

        # Adquisición.
        self.controls.run_stop_clicked.connect(
            self.toggle_run_stop
        )

        self.controls.single_clicked.connect(
            self.single
        )

    # ================================================================
    # AUDIO
    # ================================================================

    def start_audio(self):
        try:
            self.audio.start_stream(self.audio_callback)

        except Exception as error:
            self._audio_error = str(error)
            self.running = False

            self.controls.set_acquisition_enabled(False)
            self.update_controls_state()

        else:
            self.display_timer.start()

    def audio_callback(self, data):
        """Guarda muestras sin acceder a los widgets."""

        samples = np.asarray(data, dtype=np.float32)

        if samples.size == 0:
            return

        with self._buffer_lock:
            if self._closed:
                return

            self.buffer.add_samples(samples)
            self._new_data = True

    # ================================================================
    # PROCESAMIENTO
    # ================================================================

    @Slot()
    def process_data(self):
        if self._closed or not self.running:
            return

        with self._buffer_lock:
            if not self._new_data:
                return

            # Copia independiente del buffer de adquisición.
            data = self.buffer.get_data().copy()
            self._new_data = False

        if len(data) < self.display_samples:
            return

        trigger_index = self.trigger.find(
            data,
            self.display_samples,
        )

        acquisition = None

        if trigger_index is not None:
            acquisition = self.trigger.capture(
                data,
                trigger_index,
                self.display_samples,
            )

        self.trigger_found = acquisition is not None

        if not self.trigger_found:
            # Normal y Single conservan la última traza
            # mientras esperan un disparo válido.
            if self.trigger_mode in ("Normal", "Single"):
                self.update_controls_state()
                return

            # Auto sin disparo.
            self._last_display_buffer = data
            self._last_trigger_index = None
            self._last_fractional_offset = 0.0

            acquisition = data[-self.display_samples:].copy()
            self._show_acquisition(acquisition)

        else:
            # Guarda el contexto del disparo para poder volver
            # a recortar esta adquisición sin buscar otro cruce.
            self._last_display_buffer = data
            self._last_trigger_index = trigger_index
            self._last_fractional_offset = (
                self.trigger.fractional_offset
            )

            samples_before = int(
                self.display_samples * self.trigger.position
            )

            trigger_sample = (
                samples_before + self._last_fractional_offset
            )

            self._show_acquisition(
                acquisition,
                trigger_sample=trigger_sample,
            )

            if self.trigger_mode == "Single":
                self.running = False

        self.update_controls_state()

    def _show_acquisition(self, acquisition, trigger_sample=None):
        self.last_acquisition = acquisition

        self.plot.set_signal(
            acquisition,
            self.sample_rate,
            trigger_sample=trigger_sample,
        )

    def _redraw_last_acquisition(self):
        """Redibuja usando únicamente el buffer guardado."""

        data = self._last_display_buffer

        if data is None:
            return

        if self._last_trigger_index is not None:
            acquisition = self.trigger.capture(
                data,
                self._last_trigger_index,
                self.display_samples,
            )

            if acquisition is None:
                self.last_acquisition = None
                self.plot.clear_signal()
                return

            samples_before = int(
                self.display_samples * self.trigger.position
            )

            trigger_sample = (
                samples_before + self._last_fractional_offset
            )

            self._show_acquisition(
                acquisition,
                trigger_sample=trigger_sample,
            )

        else:
            # Sin disparo no existe una referencia temporal
            # para desplazar el recorte alrededor de un cruce.
            if len(data) < self.display_samples:
                self.last_acquisition = None
                self.plot.clear_signal()
                return

            acquisition = data[-self.display_samples:].copy()
            self._show_acquisition(acquisition)

    # ================================================================
    # ESTADO
    # ================================================================

    def update_controls_state(self):
        if self._audio_error is not None:
            self.controls.show_state(
                False,
                "ERROR DE AUDIO",
                self._audio_error,
            )
            return

        if not self.running:
            status = "STOP"

        elif self.trigger_mode == "Single":
            status = "SINGLE: esperando disparo"

        elif (
            self.trigger_mode == "Normal"
            and not self.trigger_found
        ):
            status = "RUN: esperando disparo"

        else:
            status = "RUN"

        self.controls.show_state(self.running, status)

    # ================================================================
    # CONTROL HORIZONTAL
    # ================================================================

    def set_time_per_division(self, value):
        value = float(value)

        if not np.isfinite(value) or value <= 0:
            return

        self.time_per_division = value

        self.display_samples = max(
            2,
            int(
                self.sample_rate
                * self.time_per_division
                * self.horizontal_divisions
            ),
        )

        self.plot.set_time_per_division(value)
        self.controls.set_time_per_division(value)

        self._redraw_last_acquisition()

    def set_horizontal_position(self, divisions):
        divisions = float(divisions)

        if not np.isfinite(divisions):
            return

        half_screen = self.horizontal_divisions / 2.0

        # Misma resolución que la perilla: 0.01 div.
        divisions = round(divisions, 2)

        self.horizontal_position_divisions = float(
            np.clip(divisions, -half_screen, half_screen)
        )

        # Cero divisiones corresponde al centro de la pantalla.
        self.trigger_position = (
            0.5
            + self.horizontal_position_divisions
            / self.horizontal_divisions
        )

        self.trigger.set_position(self.trigger_position)
        self.plot.set_trigger_position(self.trigger_position)

        self.controls.set_horizontal_position(
            self.horizontal_position_divisions
        )

        self._redraw_last_acquisition()

    # ================================================================
    # CONTROL VERTICAL
    # ================================================================

    def set_volts_per_division(self, value):
        value = float(value)

        if not np.isfinite(value) or value <= 0:
            return

        self.volts_per_division = value

        self.plot.set_volts_per_division(value)
        self.controls.set_volts_per_division(value)

        self.set_vertical_position(
            self.vertical_position_divisions
        )

    def set_vertical_position(self, divisions):
        divisions = float(divisions)

        if not np.isfinite(divisions):
            return

        slider_value = max(
            -400,
            min(400, round(divisions * 100)),
        )

        self.vertical_position_divisions = slider_value / 100.0

        # Desplaza el rango visible, sin modificar las muestras.
        self.vertical_offset = (
            -self.vertical_position_divisions
            * self.volts_per_division
        )

        self.plot.set_vertical_offset(self.vertical_offset)

        self.controls.set_vertical_position(
            self.vertical_position_divisions
        )

        self.update_trigger_range()

    # ================================================================
    # TRIGGER
    # ================================================================

    def update_trigger_range(self):
        minimum, maximum = self.plot.vertical_range()

        self.controls.set_trigger_range(
            minimum,
            maximum,
        )

    def set_trigger_level(self, value):
        value = float(value)

        if not np.isfinite(value):
            return

        self.trigger_level = value

        self.trigger.set_level(value)
        self.plot.set_trigger_level(value)
        self.controls.set_trigger_level(value)

        self.trigger_found = False
        self.update_controls_state()

    def set_trigger_slope(self, value):
        if value not in ("Rising", "Falling"):
            return

        self.trigger_slope = value

        self.trigger.set_slope(value)
        self.controls.set_trigger_slope(value)

        self.trigger_found = False
        self.update_controls_state()

    def set_trigger_mode(self, value):
        if value not in ("Auto", "Normal", "Single"):
            return

        if value == "Single":
            self.single()
            return

        self.trigger_mode = value
        self.single_mode = False
        self.trigger_found = False

        self.controls.set_trigger_mode(value)
        self.update_controls_state()

    # ================================================================
    # RUN / STOP Y SINGLE
    # ================================================================

    def toggle_run_stop(self):
        if self._closed or self._audio_error is not None:
            return

        if self.running:
            # Se congela la adquisición mostrada.
            # El audio continúa alimentando el buffer.
            self.running = False

        elif self.trigger_mode == "Single":
            self.single()
            return

        else:
            self.trigger_found = False
            self.running = True

        self.update_controls_state()

    def single(self):
        if self._closed or self._audio_error is not None:
            return

        self.trigger_mode = "Single"
        self.single_mode = True
        self.trigger_found = False

        # La adquisición anterior permanece visible mientras
        # se espera el nuevo disparo.
        with self._buffer_lock:
            self.buffer.clear()
            self._new_data = False

        self.running = True

        self.controls.set_trigger_mode("Single")
        self.update_controls_state()

    # ================================================================
    # CIERRE
    # ================================================================

    @Slot()
    def shutdown(self):
        if self._closed:
            return

        self.display_timer.stop()
        self.running = False

        with self._buffer_lock:
            self._closed = True

        # Fuera del lock para no bloquear el callback al cerrar.
        self.audio.stop_stream()

    def closeEvent(self, event):
        self.shutdown()
        event.accept()