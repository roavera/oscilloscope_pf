"""Panel frontal del osciloscopio, inspirado en LeCroy."""

from PySide6.QtCore import Signal, QSettings
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QSizePolicy, QPushButton,
    QButtonGroup, QStackedWidget, QLabel, QFrame, QScrollArea,
)
from PySide6.QtCore import Qt

from gui.panels.vertical_controls import VerticalControls
from gui.panels.math_controls import MathControls
from gui.panels.filter_controls import FilterControls
from gui.panels.measurement_controls import MeasurementControls
from gui.panels.horizontal_controls import HorizontalControls
from gui.panels.trigger_controls import TriggerControls
from gui.panels.acquisition_controls import AcquisitionControls
from gui.panels.simulator_controls import SimulatorControls
from gui.widgets.cursor_controls import CursorControls
from gui.widgets.section_reset_button import SectionResetButton


class OscilloscopeControls(QWidget):
    """Contenedor de los paneles de control del osciloscopio."""

    # ============================================================
    # SEÑALES HORIZONTALES
    # ============================================================

    time_per_division_changed = Signal(float)
    horizontal_position_changed = Signal(float)

    # ============================================================
    # SEÑALES VERTICALES
    # ============================================================

    volts_per_division_changed = Signal(float)
    vertical_position_changed = Signal(float)

    # ============================================================
    # SEÑALES DE TRIGGER
    # ============================================================

    trigger_level_changed = Signal(float)
    trigger_slope_changed = Signal(str)
    trigger_mode_changed = Signal(str)
    single_clicked = Signal()

    # ============================================================
    # SEÑALES DE ADQUISICIÓN
    # ============================================================

    run_clicked = Signal()
    stop_clicked = Signal()
    factory_reset_requested = Signal()
    autostore_toggled = Signal(bool)
    erase_requested = Signal()

    acquisition_mode_changed = Signal(str)
    interpolation_changed = Signal(str)

    # ============================================================
    # SEÑALES DEL SIMULADOR
    # ============================================================

    simulator_settings_changed = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.settings = QSettings(
            "OsciloscopioAudio",
            "OsciloscopioPF",
        )

        self.sections = {}

        self.create_interface()
        self.connect_signals()

    # ============================================================
    # INTERFAZ TIPO OSCILOSCOPIO FÍSICO
    # ============================================================

    def create_interface(self):
        """Adquisición fija y controles organizados en dos columnas."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(4)

        self.acquisition_controls = AcquisitionControls()
        self.ch1_controls = VerticalControls(channel="CH1")
        self.ch2_controls = VerticalControls(channel="CH2")
        self.horizontal_controls = HorizontalControls()
        self.trigger_controls = TriggerControls()

        # SINGLE_PERMANENTE_V1
        # Reutilizar el botón original: conserva señales, estilo y habilitación.
        def _layout_of_button(layout, button):
            for index in range(layout.count()):
                item = layout.itemAt(index)
                if item.widget() is button:
                    return layout
                if item.layout() is not None:
                    found = _layout_of_button(item.layout(), button)
                    if found is not None:
                        return found
            return None

        single = self.trigger_controls.single_button
        source_row = _layout_of_button(self.trigger_controls.layout(), single)
        acq = self.acquisition_controls
        target_row = _layout_of_button(acq.layout(), acq.stop_button)
        if source_row is None or target_row is None:
            raise RuntimeError("No se encontraron las filas de SINGLE y STOP")
        if not hasattr(target_row, "insertWidget"):
            raise RuntimeError("La fila de adquisición no es un QBoxLayout")
        source_row.removeWidget(single)
        single.setParent(acq)
        single.setMinimumHeight(acq.run_button.minimumHeight())
        target_row.insertWidget(target_row.indexOf(acq.stop_button) + 1, single, 1)
        # El botón sigue siendo propiedad lógica de TriggerControls.
        # No llamar show(): Qt lo hará al mostrar la barra de adquisición.
        self.math_controls = MathControls()
        self.filter_controls = FilterControls()
        self.cursor_controls = CursorControls()
        self.cursor_controls.setToolTip("Elegí CH1 o CH2 como referencia de los cursores de tensión y Track.")
        self.simulator_controls = SimulatorControls()
        self.simulator_controls_ch2 = SimulatorControls(channel="CH2")
        self.simulator_controls_ch2.set_waveform("square")
        self.simulator_controls_ch2.frequency.setValue(500.0)

        for panel in (
            self.acquisition_controls,
            self.ch1_controls,
            self.ch2_controls,
            self.horizontal_controls,
            self.trigger_controls,
            self.cursor_controls,
            self.simulator_controls,
            self.simulator_controls_ch2,
        ):
            panel.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Preferred,
            )

        # Compactar espacios sin alterar rangos, señales ni valores.
        for panel in (
            self.acquisition_controls, self.trigger_controls,
            self.horizontal_controls, self.ch1_controls, self.ch2_controls,
        ):
            self._compact_layout(panel.layout())

        # Cabeceras compactas con botones de reset integrados en el recuadro.
        self.reset_buttons = {}
        for key, section, description in (
            ("acquisition", self.acquisition_controls,
             "Reiniciar acumulación: conserva modo, cantidad y última captura. En STOP espera RUN o SINGLE."),
            ("trigger", self.trigger_controls,
             "Restablecer Trigger: CH1, 0 V, flanco ascendente y modo Auto."),
            ("horizontal", self.horizontal_controls,
             "Restablecer Horizontal: 1 ms/div y posición 0 div."),
            ("ch1", self.ch1_controls,
             "Restablecer CH1: 20 mV/div, posición 0 div y mostrar canal."),
            ("ch2", self.ch2_controls,
             "Restablecer CH2: 20 mV/div, posición 0 div y mostrar canal."),
            ("math", self.math_controls,
             "Restablecer MATH: CH1 + CH2, 0.02 u.a./div, posición 0 div y ocultar."),
        ):
            button = SectionResetButton(section, description)
            section.reset_button = button
            self.reset_buttons[key] = button

        # Barra de navegación, siempre por encima de Adquisición.
        nav = QHBoxLayout()
        nav.setContentsMargins(0, 0, 0, 0)
        nav.setSpacing(4)
        self.navigation_layout = nav
        self.navigation_group = QButtonGroup(self)
        self.navigation_group.setExclusive(True)
        self.navigation_buttons = {}

        for key, title in (
            ("controls", "CONTROLES"),
            ("measurements", "MEDICIONES"),
            ("cursors", "CURSORES"),
            ("math", "MATH / XY"),
            ("filters", "FILTROS"),
            ("simulator", "Generador de funciones"),
        ):
            button = QPushButton(title, self)
            button.setCheckable(True)
            button.setMinimumHeight(24)
            button.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            button.setObjectName("navButton")
            self.navigation_group.addButton(button)
            self.navigation_buttons[key] = button
            nav.addWidget(button, 2 if key == "simulator" else 1)

        layout.addLayout(nav)

        # RUN/STOP y el acceso a configuración siempre visibles.
        layout.addWidget(self.acquisition_controls)

        self.pages = QStackedWidget(self)
        self.pages.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )

        # Página 0: controles físicos existentes.
        controls_page = QWidget()
        controls_layout = QGridLayout(controls_page)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setHorizontalSpacing(4)
        controls_layout.setVerticalSpacing(4)
        controls_layout.setColumnStretch(0, 1)
        controls_layout.setColumnStretch(1, 1)
        controls_layout.addWidget(self.trigger_controls, 0, 0)
        controls_layout.addWidget(self.horizontal_controls, 0, 1)
        controls_layout.addWidget(self.ch1_controls, 1, 0, Qt.AlignmentFlag.AlignTop)
        controls_layout.addWidget(self.ch2_controls, 1, 1, Qt.AlignmentFlag.AlignTop)
        # Mismos anchos mínimos para las dos columnas. La primera fila
        # se rellena completa para igualar la altura de ambos recuadros.
        column_minimum = max(
            panel.minimumSizeHint().width() for panel in (
                self.trigger_controls, self.horizontal_controls,
                self.ch1_controls, self.ch2_controls,
            )
        )
        controls_layout.setColumnMinimumWidth(0, column_minimum)
        controls_layout.setColumnMinimumWidth(1, column_minimum)
        controls_layout.setRowStretch(2, 1)
        self.pages.addWidget(controls_page)

        # Página 1: mediciones de la captura de CH1 o CH2.
        self.measurement_controls = MeasurementControls()
        self.pages.addWidget(self.measurement_controls)

        # Página 2: reutiliza el panel de cursores original.
        cursors_page = QWidget()
        cursors_layout = QVBoxLayout(cursors_page)
        cursors_layout.setContentsMargins(0, 0, 0, 0)
        self.cursor_section = self.cursor_controls
        cursors_layout.addWidget(self.cursor_section)
        cursors_layout.addStretch(1)
        self.pages.addWidget(cursors_page)

        # Página 3: se habilita solo al seleccionar la fuente simulador.
        simulator_page = QWidget()
        simulator_layout = QVBoxLayout(simulator_page)
        simulator_layout.setContentsMargins(0, 0, 0, 0)
        self.simulator_section = self.simulator_controls
        simulator_layout.addWidget(self.simulator_section)
        simulator_layout.addWidget(self.simulator_controls_ch2)
        simulator_layout.addStretch(1)
        self.pages.addWidget(simulator_page)

        math_page = QWidget()
        math_layout = QVBoxLayout(math_page)
        math_layout.setContentsMargins(0, 0, 0, 0)
        math_layout.addWidget(self.math_controls)
        math_layout.addStretch(1)
        self.pages.addWidget(math_page)

        filter_page = QWidget()
        filter_layout = QVBoxLayout(filter_page)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.addWidget(self.filter_controls)
        filter_layout.addStretch(1)
        self.pages.addWidget(filter_page)

        for key, index in {"controls": 0, "measurements": 1, "cursors": 2,
                           "simulator": 3, "math": 4, "filters": 5}.items():
            self.navigation_buttons[key].clicked.connect(
                lambda _checked=False, i=index: self.pages.setCurrentIndex(i)
            )

        self.navigation_buttons["controls"].setChecked(True)
        self.navigation_buttons["simulator"].setVisible(False)
        self.pages.setCurrentIndex(0)
        # CONTROL_PAGES_SCROLL_V1: solo la página de controles es desplazable.
        # Navegación y RUN/STOP permanecen fijos; el display no queda recortado
        # cuando se expande Inspección temporal en un monitor de poca altura.
        self.pages_scroll = QScrollArea(self)
        self.pages_scroll.setObjectName("control_pages_scroll")
        self.pages_scroll.setWidgetResizable(True)
        self.pages_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.pages_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.pages_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.pages_scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.pages_scroll.setMinimumHeight(120)
        self.pages_scroll.setWidget(self.pages)
        layout.addWidget(self.pages_scroll, 1)
        self.pages.currentChanged.connect(self._update_page_size)
        self._update_page_size(self.pages.currentIndex())

    @staticmethod
    def _compact_layout(layout):
        """Reduce espacios de layouts existentes, respetando sus widgets."""
        if layout is None:
            return
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        for index in range(layout.count()):
            nested = layout.itemAt(index).layout()
            if nested is not None:
                OscilloscopeControls._compact_layout(nested)

    def _update_page_size(self, current):
        """Solo la pestaña visible determina el tamaño mínimo del panel."""
        for index in range(self.pages.count()):
            page = self.pages.widget(index)
            policy = (QSizePolicy.Policy.Preferred if index == current
                      else QSizePolicy.Policy.Ignored)
            page.setSizePolicy(policy, policy)
            page.updateGeometry()
        self.pages.layout().invalidate()
        self.pages.updateGeometry()
        self.updateGeometry()

    # ============================================================
    # VISIBILIDAD DEL SIMULADOR
    # ============================================================

    def set_simulator_visible(self, visible):
        """Habilita la pestaña del simulador sin destruir sus controles."""
        visible = bool(visible)
        self.navigation_buttons["simulator"].setVisible(visible)
        if not visible and self.pages.currentIndex() == 3:
            self.navigation_buttons["controls"].setChecked(True)
            self.pages.setCurrentIndex(0)

    # ============================================================
    # CONEXIONES DE SEÑALES
    # ============================================================

    def connect_signals(self):

        # --------------------------------------------------------
        # SIMULADOR
        # --------------------------------------------------------

        self.simulator_controls.settings_changed.connect(
            self.simulator_settings_changed.emit
        )
        self.acquisition_controls.default_clicked.connect(
            self.factory_reset_requested.emit
        )
        self.acquisition_controls.autostore_toggled.connect(
            self.autostore_toggled.emit
        )
        self.acquisition_controls.erase_clicked.connect(
            self.erase_requested.emit
        )

        # --------------------------------------------------------
        # CONTROL VERTICAL
        # --------------------------------------------------------

        self.ch1_controls.volts_per_division_changed.connect(
            self.volts_per_division_changed.emit
        )

        self.ch1_controls.position_changed.connect(
            self.vertical_position_changed.emit
        )

        # --------------------------------------------------------
        # CONTROL HORIZONTAL
        # --------------------------------------------------------

        self.horizontal_controls.time_per_division_changed.connect(
            self.time_per_division_changed.emit
        )

        self.horizontal_controls.position_changed.connect(
            self.horizontal_position_changed.emit
        )

        # --------------------------------------------------------
        # TRIGGER
        # --------------------------------------------------------

        self.trigger_controls.level_changed.connect(
            self.trigger_level_changed.emit
        )

        self.trigger_controls.slope_changed.connect(
            self.trigger_slope_changed.emit
        )

        self.trigger_controls.mode_changed.connect(
            self.trigger_mode_changed.emit
        )

        # SINGLE ahora pertenece al panel Trigger.
        self.trigger_controls.single_clicked.connect(
            self.single_clicked.emit
        )

        # --------------------------------------------------------
        # RUN / STOP
        # --------------------------------------------------------

        self.acquisition_controls.run_clicked.connect(
            self.run_clicked.emit
        )

        self.acquisition_controls.stop_clicked.connect(
            self.stop_clicked.emit
        )

        # --------------------------------------------------------
        # MODOS DE ADQUISICIÓN
        # --------------------------------------------------------

        self.acquisition_controls.mode_changed.connect(
            self.acquisition_mode_changed.emit
        )

        # --------------------------------------------------------
        # INTERPOLACIÓN
        # --------------------------------------------------------

        self.acquisition_controls.interpolation_changed.connect(
            self.interpolation_changed.emit
        )

    # ============================================================
    # CONFIGURACIÓN HORIZONTAL
    # ============================================================

    def set_time_per_division(self, value):
        self.horizontal_controls.set_time_per_division(
            value
        )

    def set_horizontal_position(self, divisions):
        self.horizontal_controls.set_position(
            divisions
        )

    # ============================================================
    # CONFIGURACIÓN VERTICAL
    # ============================================================

    def set_volts_per_division(self, value):
        self.ch1_controls.set_volts_per_division(
            value
        )

    def set_vertical_position(self, divisions):
        self.ch1_controls.set_position(
            divisions
        )

    # ============================================================
    # CONFIGURACIÓN TRIGGER
    # ============================================================

    def set_trigger_level(self, value):
        self.trigger_controls.set_level(
            value
        )

    def set_trigger_slope(self, value):
        self.trigger_controls.set_slope(
            value
        )

    def set_trigger_mode(self, value):
        self.trigger_controls.set_mode(
            value
        )

    def set_trigger_range(self, minimum, maximum):
        self.trigger_controls.set_level_range(
            minimum,
            maximum,
        )

    # ============================================================
    # CONFIGURACIÓN ADQUISICIÓN
    # ============================================================

    def set_acquisition_mode(self, mode):
        self.acquisition_controls.set_mode(
            mode
        )

    def set_interpolation(self, interpolation):
        self.acquisition_controls.set_interpolation(
            interpolation
        )

    def enable_acquisition_mode(self, mode, enabled=True):
        self.acquisition_controls.enable_mode(
            mode,
            enabled,
        )

    def enable_interpolation(self, interpolation, enabled=True):
        self.acquisition_controls.enable_interpolation(
            interpolation,
            enabled,
        )

    # ============================================================
    # SINCRONIZACIÓN DE CONFIGURACIÓN
    # ============================================================

    def sync_settings(self, settings):
        """Sincroniza los controles con el estado del osciloscopio."""

        self.set_time_per_division(
            settings.time_per_division
        )

        self.set_horizontal_position(
            settings.horizontal_position_divisions
        )

        self.set_volts_per_division(
            settings.volts_per_division
        )

        self.set_vertical_position(
            settings.vertical_position_divisions
        )

        self.set_trigger_level(
            settings.trigger_level
        )

        self.set_trigger_slope(
            settings.trigger_slope
        )

        self.set_trigger_mode(
            settings.trigger_mode
        )

    # ============================================================
    # ESTADO DE ADQUISICIÓN
    # ============================================================

    def show_state(self, running, status, error=None):
        """Actualiza el estado y los botones RUN/STOP."""

        self.acquisition_controls.show_state(
            running,
            status,
            error,
        )

    def set_acquisition_enabled(self, enabled):
        """Habilita o deshabilita RUN/STOP."""

        self.acquisition_controls.set_actions_enabled(
            enabled
        )

        # SINGLE requiere una fuente conectada.
        # El controlador decide cuándo está disponible.
        self.trigger_controls.single_button.setEnabled(
            bool(enabled)
        )

    # ============================================================
    # ACCESO A BOTONES
    # ============================================================

    @property
    def run_button(self):
        return self.acquisition_controls.run_button

    @property
    def stop_button(self):
        return self.acquisition_controls.stop_button

    @property
    def single_button(self):
        return self.trigger_controls.single_button

