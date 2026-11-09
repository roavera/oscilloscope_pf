# CONTROL_HORIZONTAL_COMPLETO_V1
"""Construcción del panel lateral y conexiones de señales de la interfaz."""

from PySide6.QtCore import QSettings, QTimer, Qt
from PySide6.QtWidgets import QHBoxLayout, QSplitter, QLayout, QSizePolicy, QVBoxLayout, QWidget


class InterfaceMixin:
    """Colabora sobre el estado único inicializado por OscilloscopeWidget."""

    def create_interface(self):
        """Display completo y panel lateral de altura adaptable."""
        self._layout_settings = QSettings("OsciloscopioPF", "Osciloscopio")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(5)

        self.plot.setMinimumWidth(320)
        self.splitter.addWidget(self.plot)

        # QWidget común: todos los controles de la página quedan en pantalla.
        # Se conserva el nombre del atributo por compatibilidad.
        self.controls_scroll = QWidget(self.splitter)
        # PANEL_HERRAMIENTAS_COMPLETO_V1
        # Una página de dos columnas no cabe en los ~400 px que podían quedar
        # guardados en QSettings: se recortaban Horizontal y CH2 a la derecha.
        # El mínimo se calcula a partir de las cuatro secciones, sin usar
        # tamaños rígidos de píxeles para widgets individuales.
        groups = (
            self.controls.trigger_controls,
            self.controls.horizontal_controls,
            self.controls.ch1_controls,
            self.controls.ch2_controls,
        )
        min_column = max(group.minimumSizeHint().width() for group in groups)
        # 40 px cubren separación de columnas, márgenes y scrollbar vertical.
        self._sidebar_min_width = max(540, 2 * min_column + 40)
        self.controls_scroll.setMinimumWidth(self._sidebar_min_width)
        self.controls_scroll.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        right_layout = QVBoxLayout(self.controls_scroll)
        right_layout.setContentsMargins(2, 2, 2, 2)
        right_layout.setSpacing(0)
        right_layout.setSizeConstraint(QLayout.SizeConstraint.SetDefaultConstraint)
        right_layout.addWidget(self.controls)
        self.splitter.addWidget(self.controls_scroll)

        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        layout.addWidget(self.splitter)
        # CONTROL_PAGES_SCROLL_V1: permitir reducir altura sin esconder eje X ni Time/div.
        layout.setSizeConstraint(QLayout.SizeConstraint.SetDefaultConstraint)

        self._restoring_splitter = True
        self.splitter.splitterMoved.connect(self._save_splitter_width)
        QTimer.singleShot(0, self._restore_splitter_width)


    def _restore_splitter_width(self):
        """Recupera el ancho lateral sin reducir demasiado el gráfico."""
        width = self._layout_settings.value(
            "layout/sidebar_width_v2", 560, type=int
        )
        # Respetar el mínimo aun si el usuario tenía guardados 400 px.
        min_width = self.controls_scroll.minimumWidth()
        width = max(min_width, min(700, width))
        available = max(0, self.splitter.width() - self.splitter.handleWidth())
        plot_min = self.plot.minimumWidth()
        if available >= min_width + plot_min:
            width = min(width, available - plot_min)
        self.splitter.setSizes([max(plot_min, available - width), width])
        self._restoring_splitter = False


    def _save_splitter_width(self, position, index):
        """Guarda el ancho elegido arrastrando el separador."""
        if not self._restoring_splitter:
            self._layout_settings.setValue(
                "layout/sidebar_width_v2", self.splitter.sizes()[1]
            )


    def connect_signals(self):
        resets = self.controls.reset_buttons
        resets["acquisition"].clicked.connect(self.reset_accumulation)
        resets["trigger"].clicked.connect(self.reset_trigger_controls)
        resets["horizontal"].clicked.connect(self.reset_horizontal_controls)
        resets["ch1"].clicked.connect(lambda _checked=False: self.reset_vertical_controls(1))
        resets["ch2"].clicked.connect(lambda _checked=False: self.reset_vertical_controls(2))
        resets["math"].clicked.connect(self.reset_math_controls)
        math_controls = self.controls.math_controls
        math_controls.configuration_changed.connect(self.set_math_configuration)
        math_controls.visibility_changed.connect(self.set_math_visible)
        math_controls.scale_changed.connect(lambda value: self.plot.set_math_settings(scale=value))
        math_controls.position_changed.connect(lambda value: self.plot.set_math_settings(position=value))
        self.controls.simulator_settings_changed.connect(
            self._on_simulator_settings_changed
        )

        self.cursor_controls.settings_changed.connect(self.plot.set_cursor_mode)
        self.cursor_controls.channel_changed.connect(self.plot.set_cursor_channel)
        self.cursor_controls.labels_visible_changed.connect(self.plot.set_cursor_labels_visible)
        self.plot.cursor_readout_changed.connect(self.cursor_controls.set_readout)
        self.controls.ch2_controls.volts_per_division_changed.connect(self.set_ch2_volts_per_division)
        self.controls.ch2_controls.position_changed.connect(self.set_ch2_position)
        self.plot.ch2_position_changed.connect(self.set_ch2_position)
        for ch, panel in ((1, self.controls.ch1_controls), (2, self.controls.ch2_controls)):
            panel.visibility_changed.connect(lambda visible, c=ch: self.plot.set_channel_settings(c, visible=visible))
        self.controls.trigger_controls.source_changed.connect(self.set_trigger_channel)
        self.controls.trigger_controls.type_changed.connect(self.set_trigger_type)
        self.controls.trigger_controls.pulse_width_changed.connect(self.set_pulse_width_settings)
        self.controls.trigger_controls.timeout_changed.connect(self.set_timeout_settings)
        self.controls.trigger_controls.runt_changed.connect(self.set_runt_settings)
        self.controls.trigger_controls.logic_changed.connect(self.set_logic_settings)
        self.controls.trigger_controls.auto_level_clicked.connect(self.auto_trigger_level)
        self.controls.simulator_controls_ch2.settings_changed.connect(self._on_simulator_ch2_settings_changed)
        # Control horizontal.
        nav = self.controls.horizontal_controls
        nav.reference_changed.connect(self.set_horizontal_reference)
        nav.delay_changed.connect(self.set_horizontal_delay)
        nav.zoom_changed.connect(self.set_horizontal_zoom)
        # Actualiza el indicador si se enciende/apaga Fino sin cambiar escala.
        nav.vernier_checkbox.toggled.connect(self.plot.set_timebase_vernier_enabled)
        self.controls.time_per_division_changed.connect(
            self.set_time_per_division
        )

        self.controls.horizontal_position_changed.connect(
            self.set_horizontal_position
        )

        self.plot.horizontal_position_changed.connect(
            lambda divisions: (
                self.set_horizontal_reference("Custom"),
                self.set_horizontal_position(divisions),
            )
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
        self.controls.trigger_controls.holdoff_changed.connect(
            self.set_trigger_holdoff
        )

        # Trigger desde el gráfico.
        self.plot.trigger_level_changed.connect(
            self.set_trigger_level
        )

        # Adquisición.
        self.controls.run_clicked.connect(self.run)
        self.controls.stop_clicked.connect(self.stop)

        self.controls.single_clicked.connect(
            self.single
        )
        
        # Selector de modos de adquisición
        self.controls.acquisition_mode_changed.connect(
            self.set_acquisition_mode
        )
        # Transformación exclusivamente visual, incluso con STOP.
        self.controls.interpolation_changed.connect(
            self.plot.set_interpolation_mode
        )
        self.controls.acquisition_controls.peak_bucket_size_changed.connect(self.set_peak_bucket_size)
        self.controls.acquisition_controls.high_resolution_factor_changed.connect(
            self.set_high_resolution_factor
        )
        self.controls.acquisition_controls.average_count_changed.connect(
            self.set_average_count
        )
        self.controls.acquisition_controls.envelope_count_changed.connect(
            self.set_envelope_count
        )
