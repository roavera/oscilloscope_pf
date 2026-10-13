"""Integra adquisición, procesamiento, gráfico y controles."""

from threading import Lock

import numpy as np

from PySide6.QtCore import QTimer, Slot, Qt, QSignalBlocker

from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QScrollArea,
    QSlider,
    QLabel,
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
        # CONFIGURACIÓN DE ADQUISICIÓN
        # ============================================================

        self.sample_rate = 48000
        self.blocksize = 2048
        self.channels = 1

        # ============================================================
        # CONFIGURACIÓN DE PANTALLA
        # ============================================================

        self.horizontal_divisions = 12
        self.vertical_divisions = 8

        self.time_per_division = 0.001
        self.volts_per_division = 0.02

        self.horizontal_position = 0.0

        # Posición elegida por el usuario, expresada en divisiones.
        self.vertical_position_divisions = 0.0

        # Desplazamiento de los límites del eje Y, en unidades
        # de la señal, utilizado por OscilloscopePlot.
        self.vertical_offset = 0.0
        self.vertical_position_divisions = 0.0

        self.display_samples = int(
            self.sample_rate
            * self.time_per_division
            * self.horizontal_divisions
        )

        # ============================================================
        # CONFIGURACIÓN DEL TRIGGER
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

        self.last_acquisition = None
        self.trigger_found = False

        self._closed = False
        self._audio_error = None

        self._buffer_lock = Lock()
        self._new_data = False

        # ============================================================
        # BUFFER
        # ============================================================

        self.buffer = AcquisitionBuffer(self.sample_rate)

        # ============================================================
        # ENTRADA DE AUDIO
        # ============================================================

        self.audio = AudioInput(
            sample_rate=self.sample_rate,
            channels=self.channels,
            blocksize=self.blocksize,
        )

        # ============================================================
        # TRIGGER
        # ============================================================

        self.trigger = Edge_Trigger(
            level=self.trigger_level,
            slope=self.trigger_slope,
            position=self.trigger_position,
        )

        # ============================================================
        # CONTROLES Y GRÁFICO
        # ============================================================

        self.controls = OscilloscopeControls()

        self.plot = OscilloscopePlot(
            horizontal_divisions=self.horizontal_divisions,
            vertical_divisions=self.vertical_divisions,
            time_per_division=self.time_per_division,
            volts_per_division=self.volts_per_division,
            horizontal_position=self.horizontal_position,
            vertical_offset=self.vertical_offset,
            trigger_level=self.trigger_level,
            trigger_position=self.trigger_position,
        )

        # ============================================================
        # BARRA LATERAL DE POSICIÓN
        # ============================================================

        position_panel = QWidget()
        position_panel.setFixedWidth(48)

        position_layout = QVBoxLayout(position_panel)
        position_layout.setContentsMargins(4, 8, 4, 8)
        position_layout.setSpacing(6)

        channel_label = QLabel("CH1")
        channel_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self.position_slider = QSlider(
            Qt.Orientation.Vertical
        )

        self.position_slider.setRange(-400, 400)
        self.position_slider.setValue(0)
        self.position_slider.setSingleStep(10)
        self.position_slider.setPageStep(100)
        self.position_slider.setInvertedAppearance(False)

        self.position_slider.setToolTip(
            "Posición vertical de CH1: 0.00 div"
        )

        self.position_slider.setStyleSheet("""
            QSlider::groove:vertical {
                background: #454545;
                width: 6px;
                border-radius: 3px;
            }

            QSlider::handle:vertical {
                background: #e3c84b;
                border: 1px solid #8c7927;
                height: 18px;
                margin: 0 -8px;
                border-radius: 4px;
            }
        """)

        position_layout.addWidget(channel_label)

        position_layout.addWidget(
            self.position_slider,
            1,
            Qt.AlignmentFlag.AlignHCenter,
        )

        # ============================================================
        # PANEL DERECHO
        # ============================================================

        self.controls_scroll = QScrollArea()
        self.controls_scroll.setWidgetResizable(True)
        self.controls_scroll.setWidget(self.controls)
        self.controls_scroll.setFixedWidth(490)

        # ============================================================
        # DISTRIBUCIÓN GENERAL
        # ============================================================

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        layout.addWidget(position_panel)
        layout.addWidget(self.plot, 1)
        layout.addWidget(self.controls_scroll, 0)

        # ============================================================
        # CONEXIONES DE CONTROLES
        # ============================================================

        self.controls.time_per_division_changed.connect(
            self.set_time_per_division
        )

        self.controls.volts_per_division_changed.connect(
            self.set_volts_per_division
        )

        self.controls.vertical_position_changed.connect(
            self.set_vertical_position
        )

        self.position_slider.valueChanged.connect(
            lambda value: self.set_vertical_position(
                value / 100.0
            )
        )

        self.controls.trigger_level_changed.connect(
            self.set_trigger_level
        )

        self.controls.trigger_slope_changed.connect(
            self.set_trigger_slope
        )

        self.controls.trigger_mode_changed.connect(
            self.set_trigger_mode
        )

        self.controls.run_stop_clicked.connect(
            self.toggle_run_stop
        )

        self.controls.single_clicked.connect(
            self.single
        )

        # ============================================================
        # TEMPORIZADOR DE VISUALIZACIÓN
        # ============================================================

        self.display_timer = QTimer(self)
        self.display_timer.setInterval(40)
        self.display_timer.timeout.connect(
            self.process_oscilloscope
        )

        # ============================================================
        # SINCRONIZACIÓN INICIAL
        # ============================================================

        self.controls.sync_settings(self)

        self.set_vertical_position(
            self.vertical_position_divisions
        )

        self.update_controls_state()

        # Cerrar el audio al salir de la aplicación.
        app = QApplication.instance()

        if app is not None:
            app.aboutToQuit.connect(self.shutdown)

        # ============================================================
        # INICIAR ADQUISICIÓN
        # ============================================================

        try:
            self.audio.start_stream(self.audio_callback)

        except Exception as error:
            self.running = False
            self._audio_error = str(error)

            self.controls.run_button.setEnabled(False)
            self.controls.single_button.setEnabled(False)

            self.update_controls_state()

        else:
            self.display_timer.start()

    # ================================================================
    # CALLBACK DE AUDIO
    # ================================================================

    def audio_callback(self, data):
        """Guarda muestras sin emitir señales ni llamar a Qt."""

        data_array = np.asarray(data, dtype=np.float32)

        if data_array.size == 0:
            return

        with self._buffer_lock:
            if self._closed:
                return

            self.buffer.add_samples(data_array)
            self._new_data = True

    # ================================================================
    # PROCESAMIENTO
    # ================================================================

    @Slot()
    def process_oscilloscope(self):
        if self._closed or not self.running:
            return

        with self._buffer_lock:
            if not self._new_data:
                return

            data = self.buffer.get_data()
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

        # ------------------------------------------------------------
        # NORMAL / SINGLE
        # ------------------------------------------------------------

        if self.trigger_mode in ("Normal", "Single"):
            if acquisition is None:
                self.trigger_found = False
                self.update_controls_state()
                return

            self.last_acquisition = acquisition
            self.trigger_found = True

            self.plot.set_signal(
                acquisition,
                self.sample_rate,
            )

            if self.trigger_mode == "Single":
                self.running = False

            self.update_controls_state()
            return

        # ------------------------------------------------------------
        # AUTO
        # ------------------------------------------------------------

        if acquisition is not None:
            self.trigger_found = True

        else:
            self.trigger_found = False
            acquisition = data[-self.display_samples:].copy()

        self.last_acquisition = acquisition

        self.plot.set_signal(
            acquisition,
            self.sample_rate,
        )

        self.update_controls_state()

    # ================================================================
    # ESTADO DEL PANEL
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

        elif self.trigger_mode == "Normal" and not self.trigger_found:
            status = "RUN: esperando disparo"

        else:
            status = "RUN"

        self.controls.show_state(
            self.running,
            status,
        )

    # ================================================================
    # CONTROL HORIZONTAL
    # ================================================================

    def set_time_per_division(self, value):
        self.time_per_division = float(value)

        self.display_samples = max(
            2,
            int(
                self.sample_rate
                * self.time_per_division
                * self.horizontal_divisions
            ),
        )

        self.plot.set_time_per_division(
            self.time_per_division
        )

        self.controls.set_time_per_division(
            self.time_per_division
        )

    # ================================================================
    # CONTROL VERTICAL
    # ================================================================

    def set_volts_per_division(self, value):
        self.volts_per_division = float(value)

        self.plot.set_volts_per_division(
            self.volts_per_division
        )

        self.controls.set_volts_per_division(
            self.volts_per_division
        )

        # Conservar la posición en divisiones al cambiar la escala.
        self.set_vertical_position(
            self.vertical_position_divisions
        )

    def set_vertical_position(self, divisions):
        """Desplaza la vista y sincroniza perilla y barra lateral."""

        units = max(
            -400,
            min(400, round(float(divisions) * 100)),
        )

        self.vertical_position_divisions = units / 100.0

        # OscilloscopePlot suma vertical_offset a los límites Y.
        # Bajar esos límites hace que la traza suba en pantalla.
        self.vertical_offset = (
            -self.vertical_position_divisions
            * self.volts_per_division
        )

        self.plot.set_vertical_offset(
            self.vertical_offset
        )

        self.controls.set_vertical_position(
            self.vertical_position_divisions
        )

        blocker = QSignalBlocker(self.position_slider)

        try:
            self.position_slider.setValue(units)
        finally:
            del blocker

        self.position_slider.setToolTip(
            "Posición vertical de CH1: "
            f"{self.vertical_position_divisions:+.2f} div"
        )

    # ================================================================
    # CONFIGURACIÓN DEL TRIGGER
    # ================================================================

    def set_trigger_level(self, value):
        self.trigger_level = float(value)

        self.trigger.set_level(self.trigger_level)
        self.plot.set_trigger_level(self.trigger_level)
        self.controls.set_trigger_level(self.trigger_level)

        self.trigger_found = False
        self.update_controls_state()

    def set_trigger_slope(self, value):
        self.trigger_slope = value

        self.trigger.set_slope(value)
        self.controls.set_trigger_slope(value)

        self.trigger_found = False
        self.update_controls_state()

    def set_trigger_mode(self, value):
        if value == "Single":
            self.single()
            return

        self.trigger_mode = value
        self.single_mode = False
        self.trigger_found = False

        self.controls.set_trigger_mode(value)
        self.update_controls_state()

    # ================================================================
    # RUN / STOP
    # ================================================================

    def toggle_run_stop(self):
        if self._closed or self._audio_error is not None:
            return

        if self.running:
            self.running = False

        elif self.trigger_mode == "Single":
            self.single()
            return

        else:
            self.trigger_found = False
            self.running = True

        self.update_controls_state()

    # ================================================================
    # CAPTURA INDIVIDUAL
    # ================================================================

    def single(self):
        if self._closed or self._audio_error is not None:
            return

        self.trigger_mode = "Single"
        self.single_mode = True
        self.trigger_found = False
        self.last_acquisition = None

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

        # Detener fuera del bloqueo para permitir que termine
        # cualquier callback que todavía esté ejecutándose.
        self.audio.stop_stream()

    def closeEvent(self, event):
        self.shutdown()
        event.accept()