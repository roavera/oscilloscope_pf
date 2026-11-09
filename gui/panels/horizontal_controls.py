# CONTROL_HORIZONTAL_UI_INLINE_V2
# CONTROL_HORIZONTAL_COMPLETO_V1
"""Panel horizontal compacto para el diseño de osciloscopio estilo LeCroy."""

from math import isfinite

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QCheckBox, QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from gui.widgets.drag_knob import DragKnob
from gui.widgets.position_knob import PositionKnob


class HorizontalControls(QGroupBox):
    time_per_division_changed = Signal(float)
    position_changed = Signal(float)
    reference_changed = Signal(str)
    delay_changed = Signal(float)    # Segundos
    zoom_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__("Horizontal", parent)
        self._time_per_division = 0.001
        self._position_divisions = 0.0
        self._fine_item_index = None
        self.time_options = {
            "10 s/div": 10.0,
            "5 s/div": 5.0,
            "2 s/div": 2.0,
            "1 s/div": 1.0,
            "500 ms/div": 0.5,
            "200 ms/div": 0.2,
            "100 ms/div": 0.1,
            "50 ms/div": 0.05,
            "20 ms/div": 0.02,
            "10 ms/div": 0.010,
            "5 ms/div": 0.005,
            "2 ms/div": 0.002,
            "1 ms/div": 0.001,
            "500 µs/div": 0.0005,
            "200 µs/div": 0.0002,
            "100 µs/div": 0.0001,
            "50 µs/div": 0.00005,
            "20 µs/div": 0.00002,
            "10 µs/div": 0.00001,
        }
        self.create_interface()
        self.connect_signals()
        self.set_time_per_division(self._time_per_division)
        self.set_position(0.0)

    def create_interface(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(5)

        knobs_row = QHBoxLayout()
        knobs_row.setSpacing(8)

        time_column = QVBoxLayout()
        time_column.setSpacing(3)
        time_column.setAlignment(Qt.AlignmentFlag.AlignTop)
        time_title = QLabel("Time/div")
        time_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.time_knob = DragKnob(
            minimum=0,
            maximum=len(self.time_options) - 1,
            step=1,
            initial=list(self.time_options).index("1 ms/div"),
            reset_value=list(self.time_options).index("1 ms/div"),
            pixels_per_step=12.0,
            size=64,
        )
        self.time_knob.setToolTip(
            "Arrastrá hacia arriba para reducir Tiempo/div.\n"
            "Doble clic para volver a 1 ms/div."
        )
        self.time_combo = QComboBox()
        for label, value in self.time_options.items():
            self.time_combo.addItem(label, value)
        self.time_combo.setMinimumWidth(0)
        self.time_combo.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed
        )
        time_column.addWidget(time_title)
        time_column.addWidget(self.time_knob, 0, Qt.AlignmentFlag.AlignHCenter)
        time_column.addWidget(self.time_combo)

        position_column = QVBoxLayout()
        position_column.setSpacing(3)
        position_column.setAlignment(Qt.AlignmentFlag.AlignTop)
        position_title = QLabel("Posición")
        position_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.position_knob = PositionKnob(
            minimum=-6.0, maximum=6.0, initial=0.0,
            accent_color="#B0BDCC", size=64,
        )
        self.position_label = QLabel()
        self.position_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.position_label.setToolTip("Desplazamiento horizontal en divisiones y tiempo")
        self.position_input = QDoubleSpinBox(self)
        self.position_input.hide()
        self.position_input.setRange(-6.0, 6.0)
        self.position_input.setDecimals(2)
        self.position_input.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.position_input.setSingleStep(0.01)
        self.position_input.setSuffix(" div")
        self.position_input.setKeyboardTracking(False)
        self.position_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.position_input.setMinimumWidth(0)
        self.position_input.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.position_input.setToolTip("Posición exacta en divisiones; Enter para confirmar")
        self.position_input.setAccessibleName("Posición en divisiones")
        self.center_button = QPushButton("0", self)
        self.center_button.hide()
        self.center_button.setToolTip("Centrar posición horizontal")
        self.center_button.setFixedWidth(30)
        self.center_button.setFixedHeight(24)
        position_column.addWidget(position_title)
        position_column.addWidget(self.position_knob, 0, Qt.AlignmentFlag.AlignHCenter)
        
        self.position_time_label = QLabel(self)
        self.position_time_label.hide()
        self.position_time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        

        knobs_row.addLayout(time_column, 1)
        knobs_row.addLayout(position_column, 1)
        layout.addLayout(knobs_row)
        # Referencia y Vernier siempre disponibles, sin diálogo emergente.
        navigation_row = QHBoxLayout()
        navigation_row.setSpacing(5)
        reference_title = QLabel("Ref.", self)
        reference_title.setToolTip("Ubicación del disparo cuando Delay = 0")
        self.reference_combo = QComboBox(self)
        self.reference_combo.setAccessibleName("Referencia temporal")
        self.reference_combo.setToolTip(
            "Dónde ubicar el disparo: izquierda, centro, derecha o posición libre"
        )
        for key, title in (("Left", "Izq."), ("Center", "Centro"),
                           ("Right", "Der."), ("Custom", "Libre")):
            self.reference_combo.addItem(title, key)
        self.reference_combo.setCurrentIndex(1)
        self.reference_combo.setMinimumWidth(0)
        self.reference_combo.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed
        )
        self.vernier_checkbox = QCheckBox("Fino", self)
        self.vernier_checkbox.setAccessibleName("Habilitar Vernier")
        self.vernier_checkbox.setToolTip(
            "Ajustar Time/div entre los valores estándar de la perilla"
        )
        navigation_row.addWidget(reference_title)
        navigation_row.addWidget(self.reference_combo, 1)
        navigation_row.addWidget(self.vernier_checkbox)
        layout.addLayout(navigation_row)

        # Se abre solamente al activar 'Fino' para no saturar el panel.
        self.fine_row = QWidget(self)
        fine_layout = QHBoxLayout(self.fine_row)
        fine_layout.setContentsMargins(0, 0, 0, 0)
        fine_layout.setSpacing(5)
        fine_title = QLabel("Time/div fino", self.fine_row)
        self.fine_time_spin = QDoubleSpinBox(self.fine_row)
        self.fine_time_spin.setAccessibleName("Time por división fino")
        self.fine_time_spin.setDecimals(2)
        self.fine_time_spin.setRange(10.0, 10_000_000.0)
        self.fine_time_spin.setSingleStep(1.0)
        self.fine_time_spin.setValue(1000.0)
        self.fine_time_spin.setSuffix(" µs/div")
        self.fine_time_spin.setKeyboardTracking(False)
        self.fine_time_spin.setMinimumWidth(0)
        self.fine_time_spin.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed
        )
        self.fine_time_spin.setToolTip(
            "Escala fina de adquisición; afecta Time/div, no el zoom de STOP"
        )
        fine_layout.addWidget(fine_title)
        fine_layout.addWidget(self.fine_time_spin, 1)
        layout.addWidget(self.fine_row)
        self.fine_row.hide()

        # Herramientas de inspección en un desplegable integrado al panel.
        self.navigation_button = QPushButton("▸  Inspección temporal (STOP)", self)
        self.navigation_button.setCheckable(True)
        self.navigation_button.setAccessibleName("Mostrar u ocultar inspección temporal")
        self.navigation_button.setToolTip(
            "Desplazar y ampliar una captura congelada, sin generar nuevas muestras"
        )
        layout.addWidget(self.navigation_button)

        self.inspection_area = QWidget(self)
        inspection_layout = QGridLayout(self.inspection_area)
        inspection_layout.setContentsMargins(3, 2, 3, 2)
        inspection_layout.setHorizontalSpacing(6)
        inspection_layout.setVerticalSpacing(5)
        self.delay_spin = QDoubleSpinBox(self.inspection_area)
        self.delay_spin.setAccessibleName("Delay temporal en milisegundos")
        self.delay_spin.setRange(-500.0, 500.0)
        self.delay_spin.setDecimals(3)
        self.delay_spin.setSingleStep(0.1)
        self.delay_spin.setSuffix(" ms")
        self.delay_spin.setKeyboardTracking(False)
        self.delay_spin.setToolTip(
            "STOP: + desplaza hacia muestras posteriores; − hacia anteriores"
        )
        self.zoom_spin = QDoubleSpinBox(self.inspection_area)
        self.zoom_spin.setAccessibleName("Factor de zoom temporal")
        self.zoom_spin.setRange(1.0, 20.0)
        self.zoom_spin.setDecimals(2)
        self.zoom_spin.setSingleStep(0.5)
        self.zoom_spin.setValue(1.0)
        self.zoom_spin.setSuffix(" ×")
        self.zoom_spin.setKeyboardTracking(False)
        self.zoom_spin.setToolTip(
            "STOP: amplía la captura guardada sin cambiar Time/div de adquisición"
        )
        inspection_layout.addWidget(QLabel("Delay", self.inspection_area), 0, 0)
        inspection_layout.addWidget(self.delay_spin, 0, 1)
        inspection_layout.addWidget(QLabel("Zoom", self.inspection_area), 1, 0)
        inspection_layout.addWidget(self.zoom_spin, 1, 1)
        self.reset_inspection_button = QPushButton(
            "Restablecer inspección", self.inspection_area
        )
        self.reset_inspection_button.setToolTip("Zoom ×1 y Delay 0; conserva Time/div y referencia")
        inspection_layout.addWidget(self.reset_inspection_button, 2, 0, 1, 2)
        layout.addWidget(self.inspection_area)
        self.inspection_area.hide()
        layout.addStretch(1)

    def _on_inspection_toggled(self, visible):
        """Expansión integrada; no abre ventanas flotantes."""
        self.inspection_area.setVisible(bool(visible))
        self.navigation_button.setText(
            "▾  Inspección temporal (STOP)" if visible
            else "▸  Inspección temporal (STOP)"
        )

    def _reset_navigation_view(self):
        """Restablece solo la inspección; no cambia la base de tiempo."""
        self.delay_spin.setValue(0.0)
        self.zoom_spin.setValue(1.0)

    def set_navigation_enabled(self, enabled):
        """RUN/ROLL/FASTACT: inspección visible, pero no editable."""
        enabled = bool(enabled)
        self.delay_spin.setEnabled(enabled)
        self.zoom_spin.setEnabled(enabled)
        self.reset_inspection_button.setEnabled(enabled)
        self.navigation_button.setToolTip(
            "Inspección de capturas congeladas" if enabled
            else "Presioná STOP para inspeccionar la última captura"
        )

    def set_reference(self, reference):
        index = self.reference_combo.findData(reference)
        if index < 0:
            return
        blocker = QSignalBlocker(self.reference_combo)
        self.reference_combo.setCurrentIndex(index)
        del blocker

    def set_delay_seconds(self, seconds):
        blocker = QSignalBlocker(self.delay_spin)
        self.delay_spin.setValue(float(seconds) * 1000.0)
        del blocker

    def set_zoom_factor(self, factor):
        blocker = QSignalBlocker(self.zoom_spin)
        self.zoom_spin.setValue(float(factor))
        del blocker

    def _on_reference_changed(self, index):
        mode = self.reference_combo.itemData(index)
        if mode not in ("Left", "Center", "Right", "Custom"):
            return
        self.reference_changed.emit(mode)
        presets = {"Left": -6.0, "Center": 0.0, "Right": 6.0}
        if mode in presets:
            self.set_position(presets[mode])
            self.position_changed.emit(presets[mode])

    def _disable_vernier_from_coarse(self):
        if self.vernier_checkbox.isChecked():
            blocker = QSignalBlocker(self.vernier_checkbox)
            self.vernier_checkbox.setChecked(False)
            del blocker
            self.fine_row.hide()

    def _on_vernier_toggled(self, enabled):
        self.fine_row.setVisible(bool(enabled))
        if enabled:
            self._on_fine_time_changed(self.fine_time_spin.value())

    def _on_fine_time_changed(self, microseconds):
        if not self.vernier_checkbox.isChecked():
            return
        seconds = float(microseconds) * 1e-6
        self.set_time_per_division(seconds)
        self.time_per_division_changed.emit(seconds)

    def connect_signals(self):
        self.navigation_button.toggled.connect(self._on_inspection_toggled)
        self.reset_inspection_button.clicked.connect(self._reset_navigation_view)
        self.reference_combo.currentIndexChanged.connect(self._on_reference_changed)
        self.delay_spin.valueChanged.connect(lambda ms: self.delay_changed.emit(ms * 1e-3))
        self.zoom_spin.valueChanged.connect(self.zoom_changed.emit)
        self.vernier_checkbox.toggled.connect(self._on_vernier_toggled)
        self.fine_time_spin.valueChanged.connect(self._on_fine_time_changed)
        self.time_combo.currentIndexChanged.connect(self._on_time_combo_changed)
        self.time_knob.value_changed.connect(self._on_time_knob_changed)
        self.position_knob.value_changed.connect(self._on_position_changed)
        self.center_button.clicked.connect(self._center_position)
        self.position_input.valueChanged.connect(self._on_position_changed)

    def _on_time_combo_changed(self, index):
        if index < 0:
            return
        value = self.time_combo.itemData(index)
        if value is None:
            return
        self._disable_vernier_from_coarse()
        self.set_time_per_division(value)
        self.time_per_division_changed.emit(float(value))

    def _on_time_knob_changed(self, value):
        index = int(round(value))
        if not 0 <= index < self.time_combo.count():
            return
        time_per_division = float(self.time_combo.itemData(index))
        self._disable_vernier_from_coarse()
        self.set_time_per_division(time_per_division)
        self.time_per_division_changed.emit(time_per_division)

    def _on_position_changed(self, divisions):
        self.set_reference("Custom")
        self.reference_changed.emit("Custom")
        self.set_position(divisions)
        self.position_changed.emit(self._position_divisions)

    def _center_position(self, _checked=False):
        self.set_position(0.0)
        self.position_changed.emit(0.0)

    def set_time_per_division(self, value):
        """Sincroniza los controles sin emitir una orden al controlador."""
        value = float(value)
        if not isfinite(value) or value <= 0:
            raise ValueError("Tiempo/div debe ser positivo y finito.")

        blocker = QSignalBlocker(self.time_combo)
        try:
            index = self.time_combo.findData(value)
            if index < 0:
                if self._fine_item_index is None:
                    self.time_combo.addItem(f"{self._format_time(value)}/div", value)
                    self._fine_item_index = self.time_combo.count() - 1
                else:
                    self.time_combo.setItemText(self._fine_item_index,
                                                f"{self._format_time(value)}/div")
                    self.time_combo.setItemData(self._fine_item_index, value)
                index = self._fine_item_index
            self.time_combo.setCurrentIndex(index)
            self.time_knob.configure_range(
                minimum=0,
                maximum=self.time_combo.count() - 1,
                step=1,
                value=index,
            )
        finally:
            del blocker
        self._time_per_division = value
        blocker_fine = QSignalBlocker(self.fine_time_spin)
        self.fine_time_spin.setValue(value * 1_000_000)
        del blocker_fine
        self._update_position_label()

    def set_position(self, divisions):
        """Actualiza la posición sin emitir position_changed."""
        divisions = float(divisions)
        if not isfinite(divisions):
            raise ValueError("La posición debe ser finita.")
        self.position_knob.set_value(divisions)
        blocker = QSignalBlocker(self.position_input)
        self.position_input.setValue(self.position_knob.numeric_value())
        del blocker
        self._position_divisions = self.position_knob.numeric_value()
        self._update_position_label()

    def _update_position_label(self):
        displacement = self._position_divisions * self._time_per_division
        self.position_time_label.setText(self._format_time(displacement, signed=True))
        self.position_label.setText(
            f"{self._position_divisions:+.2f} div\n"
            f"{self._format_time(displacement, signed=True)}"
        )

    @staticmethod
    def _format_time(seconds, signed=False):
        magnitude = abs(seconds)
        if magnitude == 0:
            value, unit = 0.0, "s"
        elif magnitude < 0.001:
            value, unit = seconds * 1_000_000, "µs"
        elif magnitude < 1.0:
            value, unit = seconds * 1_000, "ms"
        else:
            value, unit = seconds, "s"
        text = f"{value:+.4g}" if signed else f"{value:.4g}"
        return f"{text} {unit}"

