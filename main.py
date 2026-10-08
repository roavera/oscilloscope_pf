"""
===============================================================================
PUNTO DE ENTRADA PRINCIPAL (APPLICATION ENTRY POINT)
===============================================================================
Proyecto:       Osciloscopio y Analizador de Audio por Software (DSO)
Framework:      PySide6 (Qt for Python)
Descripción:
    Inicializa el contexto de ejecución de Qt (QApplication), instancia el
    controlador principal de la interfaz de usuario (MainWindow) y gestiona
    el ciclo de vida del proceso mediante el despacho del Event Loop principal.
===============================================================================
"""
import sys
from PySide6.QtWidgets import QApplication, QMainWindow

from gui.main_window import MainWindow

def main():
    
    # Crear la aplicación 
    app = QApplication(sys.argv)                    
    # Crear la ventana principal
    window = MainWindow()                         
                      
    window.show()                                   
    sys.exit(app.exec())

if __name__ == "__main__":
    main()