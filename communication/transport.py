"""
Transportes: por dónde se mueven los bytes. Todos cumplen la misma interfaz mínima (`Transport`), así el resto
de `communications/` no sabe si habla con el puerto USB real, con la placa simulada (simulator.py) o con lo que
se agregue más adelante (un archivo grabado, un socket...).

Acá también está la búsqueda del puerto: el COM de la Black Pill cambia de número entre PCs, así que se la
reconoce por el VID:PID del USB (0483:5740 es el «STM32 Virtual ComPort» que genera CubeMX por defecto).
"""
from __future__ import annotations

from dataclasses import dataclass

try:
    import serial
    from serial.tools import list_ports
except ImportError:                      # sin pyserial funciona todo menos el puerto real
    serial = None
    list_ports = None

from .errors import CommunicationError, PortNotFound, LinkLost

DEFAULT_USB_IDS = ((0x0483, 0x5740),)    # (VID, PID) del STM32 Virtual ComPort
RX_BUFFER_BYTES = 1 << 20                # buffer de recepción que se le pide a Windows (por defecto 4 kB = 7 ms de audio)


# ======================================================================================
#  Interfaz
# ======================================================================================
class Transport:
    """Lo mínimo que necesita DeviceSession de un enlace de bytes."""
    description = "transporte"

    def open(self):
        raise NotImplementedError

    def close(self):
        raise NotImplementedError

    @property
    def is_open(self):
        raise NotImplementedError

    def read(self):
        """Espera hasta `read_timeout` por el primer byte y devuelve todo lo que haya (b'' si no llegó nada)."""
        raise NotImplementedError

    def write(self, data):
        raise NotImplementedError

    def reset_input(self):
        """Descarta lo que ya llegó y todavía no se leyó."""
        raise NotImplementedError

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()


# ======================================================================================
#  Puerto serie real (USB CDC)
# ======================================================================================
def _open_error_message(port, exc):
    text = str(exc)
    low = text.lower()
    msg = f"No se pudo abrir {port}: {text}"
    if "permission" in low or "denied" in low or "denegado" in low or "access" in low or "busy" in low:
        msg += ("\n  Un puerto COM lo puede usar un solo programa a la vez: ¿está abierto en comandos.py, "
                "en un monitor serie o en otra copia del analizador?")
    elif "no such file" in low or "could not find" in low or "cannot find" in low or "no se puede encontrar" in low:
        msg += "\n  El puerto no existe: ¿está enchufada la placa? ¿cambió el número de COM?"
    return msg


class SerialTransport(Transport):
    """
    Puerto serie por pyserial. En USB CDC el baudrate, la paridad y los bits de parada no significan nada
    (el firmware los ignora): los datos viajan a la velocidad del USB (12 Mbit/s) sea cual sea el valor.
    `port` es un nombre de puerto ('COM5') o una URL de pyserial (por ejemplo 'loop://' para pruebas).
    """

    def __init__(self, port, baudrate=115200, read_timeout=0.05, write_timeout=1.0, rx_buffer=RX_BUFFER_BYTES):
        self.port = port
        self.baudrate = baudrate
        self.read_timeout = read_timeout
        self.write_timeout = write_timeout
        self.rx_buffer = rx_buffer
        self.description = f"puerto {port}"
        self._ser = None

    @property
    def is_open(self):
        return self._ser is not None and self._ser.is_open

    def open(self):
        if serial is None:
            raise CommunicationError("Falta la librería pyserial. Instalala con:  pip install pyserial")
        try:
            # serial_for_url abre igual un nombre común ('COM5', '/dev/ttyACM0') y además URLs de pyserial:
            # 'loop://' (para pruebas), 'socket://host:puerto' o 'rfc2217://...' (placa conectada por red).
            ser = serial.serial_for_url(self.port, baudrate=self.baudrate, timeout=self.read_timeout,
                                        write_timeout=self.write_timeout)
        except (serial.SerialException, OSError, ValueError) as e:
            raise CommunicationError(_open_error_message(self.port, e)) from e
        try:
            ser.set_buffer_size(rx_size=self.rx_buffer)       # solo existe en Windows; en otros sistemas se ignora
        except (AttributeError, serial.SerialException, OSError, ValueError):
            pass
        self._ser = ser

    def close(self):
        ser, self._ser = self._ser, None
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass

    def read(self):
        ser = self._ser
        if ser is None:
            raise LinkLost("El puerto está cerrado.")
        try:
            return ser.read(ser.in_waiting or 1)              # lo que haya; si no hay nada, espera 1 byte hasta el timeout
        except (serial.SerialException, OSError) as e:
            raise LinkLost(f"Se perdió la conexión con {self.port} (¿cable USB? ¿se reinició la placa?): {e}") from e

    def write(self, data):
        ser = self._ser
        if ser is None:
            raise LinkLost("El puerto está cerrado.")
        try:
            ser.write(data)
        except serial.SerialTimeoutException as e:
            raise LinkLost(f"La placa no aceptó los datos en {self.write_timeout:g} s ({self.port}).") from e
        except (serial.SerialException, OSError) as e:
            raise LinkLost(f"No se pudo escribir en {self.port}: {e}") from e

    def reset_input(self):
        if self._ser is not None:
            try:
                self._ser.reset_input_buffer()
            except (serial.SerialException, OSError):
                pass                                          # si el puerto murió, el próximo read() lo informa


# ======================================================================================
#  Búsqueda del puerto
# ======================================================================================
@dataclass(frozen=True)
class PortInfo:
    device: str                  # 'COM5', '/dev/ttyACM0'
    description: str
    vid: int | None
    pid: int | None
    manufacturer: str
    exact: bool                  # coincide con el VID:PID de la Black Pill
    likely: bool                 # coincide por VID:PID o por el nombre (STM32 / STMicroelectronics)

    def __str__(self):
        ids = f"{self.vid:04X}:{self.pid:04X}" if self.vid is not None and self.pid is not None else "----:----"
        return f"{self.device}  [{ids}]  {self.description}"


def list_serial_ports(usb_ids=DEFAULT_USB_IDS):
    """Los puertos serie del sistema, ordenados por número, marcando cuáles parecen la Black Pill."""
    if list_ports is None:
        raise CommunicationError("Falta la librería pyserial. Instalala con:  pip install pyserial")
    ids = {(int(v), int(p)) for v, p in usb_ids}
    out = []
    for p in list_ports.comports():
        exact = p.vid is not None and p.pid is not None and (p.vid, p.pid) in ids
        text = f"{p.description or ''} {p.manufacturer or ''} {getattr(p, 'product', None) or ''}".lower()
        likely = exact or "stm32" in text or "stmicroelectronics" in text
        out.append(PortInfo(p.device, p.description or "", p.vid, p.pid, p.manufacturer or "", exact, likely))
    return sorted(out, key=lambda q: (len(q.device), q.device))


def describe_ports(ports):
    return "\n".join(f"    {p}" for p in ports) if ports else "    (el sistema no lista ningún puerto serie)"


def find_blackpill_port(usb_ids=DEFAULT_USB_IDS, preferred=None):
    """
    Nombre del puerto de la Black Pill. Si `preferred` está dado (por ejemplo 'COM5') se usa tal cual, sin buscar:
    si no existe, el error lo da open(). Si no, se busca por VID:PID y, en segundo lugar, por nombre.
    """
    if preferred:
        return str(preferred)
    ports = list_serial_ports(usb_ids)
    pool = [p for p in ports if p.exact] or [p for p in ports if p.likely]
    if not pool:
        wanted = ", ".join(f"{v:04X}:{p:04X}" for v, p in usb_ids)
        raise PortNotFound(
            f"No se encontró la Black Pill (USB {wanted}). ¿Está enchufada por el USB de la placa?\n"
            f"  Puertos serie que ve el sistema:\n{describe_ports(ports)}\n"
            f"  Si aparece pero con otro nombre, fijala en config/defaults.py (BLACKPILL_PORT = \"COM5\").")
    return pool[0].device
