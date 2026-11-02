"""Windows pythonw entry point with a visible error and local diagnostic log."""
from pathlib import Path
import sys,traceback
ROOT=Path(__file__).resolve().parent

def report(kind,value,tb):
    message=''.join(traceback.format_exception(kind,value,tb))
    try:
        with open(ROOT/'foutmelding.txt','a',encoding='utf-8') as f:f.write(message+'\n')
    except OSError:pass
    try:
        from PySide6.QtWidgets import QApplication,QMessageBox
        app=QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None,'Ikkanborduren',f'Er is een fout opgetreden:\n{value}\n\nMeer informatie staat in foutmelding.txt. Voer zo nodig Installatie.bat opnieuw uit.')
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0,'Start mislukt. Zie foutmelding.txt en voer Installatie.bat opnieuw uit.','Ikkanborduren',0x10)
        except Exception:pass
sys.excepthook=report
try:
    from main import run
    run()
except Exception:
    report(*sys.exc_info())
