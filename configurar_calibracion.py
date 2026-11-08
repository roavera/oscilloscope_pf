"""Configura coeficientes físicos sin cambiar la codificación USB.

Ejemplos desde la carpeta del proyecto:
    python configurar_calibracion.py --show
    python configurar_calibracion.py --channel 1 --gain 3.0 --offset 0.0
    python configurar_calibracion.py --channel 1 --gain 2.994 --offset 0.013 --verified

El flag --verified solo es adecuado si hubo medición frente a instrumento patrón.
Reiniciar el osciloscopio después de modificar los parámetros.
"""
import argparse
import json
from acquisition.voltage_calibration import VoltageCalibration


def main():
    p = argparse.ArgumentParser(description="Calibración vertical de Blackpill física")
    p.add_argument("--show", action="store_true", help="Mostrar valores actuales")
    p.add_argument("--channel", type=int, choices=(1, 2))
    p.add_argument("--gain", type=float, help="Voltios por unidad PCM24 normalizada")
    p.add_argument("--offset", type=float, default=0.0, help="Offset en voltios")
    p.add_argument("--verified", action="store_true", help="Coeficiente medido contra patrón")
    a = p.parse_args()
    cal = VoltageCalibration()
    if a.channel is not None or a.gain is not None:
        if a.channel is None or a.gain is None:
            p.error("--channel y --gain se deben indicar juntos")
        cal.set_physical(a.channel, a.gain, a.offset, verified=a.verified)
        print("Guardado. Reiniciá la aplicación para aplicar los coeficientes.")
    elif not a.show:
        p.error("Elegí --show o --channel N --gain V")
    print(json.dumps(cal.as_dict(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
