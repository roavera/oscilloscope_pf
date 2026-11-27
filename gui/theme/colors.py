"""Paletas visuales de OSCILOSCOPIO."""

DARK = {
    "background": "#0B1320",
    "surface": "#142033",
    "surface_alt": "#1A2A41",
    "panel": "#101C2D",
    "panel_alt": "#18283E",
    "text": "#EAF5FF",
    "muted": "#A7BED6",
    "border": "#2E4A67",
    "accent": "#21D4F5",
    "accent_hover": "#3BE4FF",
    "violet": "#8D63F8",
    "magenta": "#FF3BCB",
    "success": "#1FAE7A",
    "warning": "#B37A2D",
    "danger": "#A44B57",
}

LIGHT = {
    "background": "#F2F7FC",
    "surface": "#FFFFFF",
    "surface_alt": "#ECF3FB",
    "panel": "#FAFCFF",
    "panel_alt": "#F0F6FD",
    "text": "#183149",
    "muted": "#55718D",
    "border": "#B9CCE0",
    "accent": "#168DCB",
    "accent_hover": "#0F7AB4",
    "violet": "#6E58D9",
    "magenta": "#D53AA8",
    "success": "#178A63",
    "warning": "#A66C24",
    "danger": "#A14D58",
}

THEMES = {
    "dark": DARK,
    "light": LIGHT,
}

# Colores del display. Se conservan independientes del tema general.
PLOT_COLORS = {
    "dark": {
        "background": "#001228",
        "grid": "#0D4468",
        "ch1": "#FFE45C",
        "ch2": "#21D4F5",
        "trigger": "#E278E8",
    },
    "light": {
        "background": "#FFFFFF",
        "grid": "#D6DFE9",
        "ch1": "#A67C00",
        "ch2": "#0B8EB7",
        "trigger": "#AD39B8",
    },
}
