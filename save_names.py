"""Explicit naming at every user save; companion files share the design name."""
from pathlib import Path
import re
from PySide6.QtWidgets import QInputDialog,QFileDialog,QMessageBox

EXTENSIONS={'.bst','.exp','.pes','.svg'}

def ask_name(parent,suggested,usb=False):
    default=Path(suggested).name
    if Path(default).suffix.lower() in EXTENSIONS:default=Path(default).stem
    while True:
        name,ok=QInputDialog.getText(parent,'Bestandsnaam kiezen','Hoe moet dit bestand heten? (zonder bestandsextensie)',text=default)
        if not ok:return None
        name=name.strip()
        if Path(name).suffix.lower() in EXTENSIONS:name=Path(name).stem
        try:
            if usb:
                from usb_export import safe_name
                name=safe_name(name)
            else:
                if not name or len(name)>120 or re.search(r'[<>:"/\\|?*\x00-\x1f]',name) or name.endswith('.'):
                    raise ValueError('Kies 1–120 tekens. Gebruik geen / \\ : * ? " < > | of punt aan het einde.')
                base=name.split('.')[0].upper()
                if base in {'CON','PRN','AUX','NUL'} or re.fullmatch(r'(COM|LPT)[1-9]',base):raise ValueError('Deze naam is gereserveerd door Windows.')
            return name
        except ValueError as error:
            QMessageBox.warning(parent,'Andere bestandsnaam kiezen',str(error));default=name

def choose_save_file(parent,title,suggested,filters):
    name=ask_name(parent,suggested)
    if name is None:return '', ''
    default=Path(suggested);extension=default.suffix if default.suffix.lower() in EXTENSIONS else ''
    return QFileDialog.getSaveFileName(parent,title+' — kies de opslagmap',str(default.with_name(name+extension)),filters)
