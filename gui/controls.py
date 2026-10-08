from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,)


class OscilloscopeControls(QWidget):

    # ================================================================
    # SEÑALES
    # ================================================================

    time_per_division_changed = Signal(float)
    volts_per_division_changed = Signal(float)
    trigger_level_changed = Signal(float)
    trigger_slope_changed = Signal(str)
    trigger_mode_changed = Signal(str)

    run_stop_clicked = Signal()
    single_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.create_interface()
        self.connect_signals()

    # ==================================================================
    # INTERFAZ
    # ==================================================================

    def create_interface(self):

        main_layout = QVBoxLayout()
        self.setLayout(
            main_layout
        )

        # ============================================================
        # CONTROLES
        # ============================================================
        controls_layout = QHBoxLayout()

        # ============================================================
        # TIME/DIV
        # ============================================================
        time_label = QLabel(
            "Tiempo/div:"
        )
        self.time_div_combo = QComboBox()
        self.time_opciones = {
            "10 ms/div": 0.010,
            "5 ms/div": 0.005,
            "2 ms/div": 0.002,
            "1 ms/div": 0.001,
            "500 µs/div": 0.0005,
            "200 µs/div": 0.0002,
            "100 µs/div": 0.0001,
            "50 µs/div": 0.00005,
            "20 µs/div": 0.00002,
            "10 µs/div": 0.00001
        }
        self.time_div_combo.addItems(
            self.time_opciones.keys()
        )
        self.time_div_combo.setCurrentText(
            "1 ms/div"
        )

        # ============================================================
        # VOLT/DIV
        # ============================================================
        voltage_label = QLabel(
            "Volt/div:"
        )
        self.voltage_div_combo = QComboBox()
        self.voltage_opciones = {
            "5 V/div": 5.0,
            "2 V/div": 2.0,
            "1 V/div": 1.0,
            "500 mV/div": 0.5,
            "200 mV/div": 0.2,
            "100 mV/div": 0.1,
            "50 mV/div": 0.05,
            "20 mV/div": 0.02,
            "10 mV/div": 0.01,
            "5 mV/div": 0.005,
            "2 mV/div": 0.002,
            "1 mV/div": 0.001
        }
        self.voltage_div_combo.addItems(
            self.voltage_opciones.keys()
        )
        self.voltage_div_combo.setCurrentText(
            "20 mV/div"
        )

        # ============================================================
        # TRIGGER LEVEL
        # ============================================================
        trigger_label = QLabel(
            "Trigger:"
        )

        self.trigger_combo = QComboBox()

        self.trigger_opciones = [
            "-2.0 V",
            "-1.0 V",
            "-0.5 V",
            "-0.2 V",
            "-0.1 V",
            "-0.05 V",
            "-0.02 V",
            "0 V",
            "0.02 V",
            "0.05 V",
            "0.1 V",
            "0.2 V",
            "0.5 V",
            "1.0 V",
            "2.0 V"
        ]
        self.trigger_combo.addItems(
            self.trigger_opciones
        )
        self.trigger_combo.setCurrentText(
            "0 V"
        )

        # ============================================================
        # FLANCO
        # ============================================================
        slope_label = QLabel(
            "Flanco:"
        )

        self.slope_combo = QComboBox()
        self.slope_combo.addItems([
            "Ascendente",
            "Descendente"
        ])
        self.slope_combo.setCurrentText(
            "Ascendente"
        )

        # ============================================================
        # MODO
        # ============================================================
        mode_label = QLabel(
            "Modo:"
        )

        self.mode_combo = QComboBox()

        self.mode_combo.addItems([
            "Auto",
            "Normal"
        ])

        self.mode_combo.setCurrentText(
            "Auto"
        )

        # ============================================================
        # RUN / STOP
        # ============================================================
        self.run_button = QPushButton(
            "STOP"
        )

        # ============================================================
        # SINGLE
        # ============================================================
        self.single_button = QPushButton(
            "SINGLE"
        )

        # ============================================================
        # AGREGAR CONTROLES
        # ============================================================
        controls_layout.addWidget(time_label)
        controls_layout.addWidget(self.time_div_combo)
        controls_layout.addSpacing(10)
        controls_layout.addWidget(voltage_label)
        controls_layout.addWidget(self.voltage_div_combo)
        controls_layout.addSpacing(10)
        controls_layout.addWidget(trigger_label)
        controls_layout.addWidget(self.trigger_combo)
        controls_layout.addSpacing(10)
        controls_layout.addWidget(slope_label)
        controls_layout.addWidget(self.slope_combo)
        controls_layout.addSpacing(10)
        controls_layout.addWidget(mode_label)
        controls_layout.addWidget(self.mode_combo)
        controls_layout.addSpacing(15)
        controls_layout.addWidget(self.run_button)
        controls_layout.addWidget(self.single_button)
        controls_layout.addStretch()

        main_layout.addLayout(
            controls_layout
        )

    # ==================================================================
    # CONEXIÓN DE SEÑALES
    # ==================================================================

    def connect_signals(self):

        self.time_div_combo.currentTextChanged.connect(self.update_time_per_division)
        self.voltage_div_combo.currentTextChanged.connect(self.update_volts_per_division)
        self.trigger_combo.currentTextChanged.connect(self.update_trigger_level)
        self.slope_combo.currentTextChanged.connect(self.update_trigger_slope)
        self.mode_combo.currentTextChanged.connect(self.update_trigger_mode)
        self.run_button.clicked.connect(self.toggle_run)
        self.single_button.clicked.connect(self.single_acquisition)

    # ==================================================================
    # TIME/DIV
    # ==================================================================
    def update_time_per_division(self, text):
        value = self.time_opciones[text]
        self.time_per_division_changed.emit(
            value
        )

    # ==================================================================
    # VOLT/DIV
    # ==================================================================
    def update_volts_per_division(self, text):
        value = self.voltage_opciones[text]
        self.volts_per_division_changed.emit(
            value
        )

    # ==================================================================
    # TRIGGER LEVEL
    # ==================================================================
    def update_trigger_level(self, text):
        value = float(
            text.replace(" V", "")
        )
        self.trigger_level_changed.emit(
            value
        )

    # ==================================================================
    # TRIGGER SLOPE
    # ==================================================================
    def update_trigger_slope(self, text):
        if text == "Ascendente":
            slope = "Rising"
        elif text == "Descendente":
            slope = "Falling"
        else:
            return
        self.trigger_slope_changed.emit(
            slope
        )

    # ==================================================================
    # TRIGGER MODE
    # ==================================================================
    def update_trigger_mode(self, text):
        self.trigger_mode_changed.emit(
            text
        )

    # ==================================================================
    # RUN / STOP
    # ==================================================================
    def toggle_run(self):

        self.run_stop_clicked.emit()

    # ==================================================================
    # SINGLE
    # ==================================================================
    def single_acquisition(self):

        self.single_clicked.emit()

    # ==================================================================
    # ACTUALIZAR CONTROLES DESDE EL PROGRAMA
    # ==================================================================
    def set_time_per_division(self, value):

        for text, option_value in self.time_opciones.items():
            if option_value == value:
                self.time_div_combo.setCurrentText(
                    text
                )
                return

    def set_volts_per_division(self, value):

        for text, option_value in self.voltage_opciones.items():
            if option_value == value:
                self.voltage_div_combo.setCurrentText(
                    text
                )
                return

    def set_trigger_level(self, value):
        text = f"{value:g} V"
        index = self.trigger_combo.findText(
            text
        )
        if index >= 0:
            self.trigger_combo.setCurrentIndex(
                index
            )

    def set_trigger_slope(self, value):
        if value == "Rising":
            text = "Ascendente"
        elif value == "Falling":
            text = "Descendente"
        else:
            return
        self.slope_combo.setCurrentText(
            text
        )

    def set_trigger_mode(self, value):
        self.mode_combo.setCurrentText(value)