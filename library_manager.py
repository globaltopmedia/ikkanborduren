"""Lokale ontwerp-bibliotheek voor Ikkanborduren."""
from pathlib import Path
import shutil, os
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QListWidget,QPushButton,QFileDialog,QMessageBox,QInputDialog)

class LibraryDialog(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent); self.setWindowTitle('Ikkanborduren — Bibliotheek'); self.resize(720,480)
        self.root=Path.home()/'Documents'/'Ikkanborduren'/'Bibliotheek'; self.root.mkdir(parents=True,exist_ok=True)
        layout=QVBoxLayout(self);layout.addWidget(QLabel(f'Persoonlijke bibliotheek op deze laptop: {self.root}\nOndersteund: .PES, .EXP en Ikkanborduren-projecten (.BST).'))
        self.items=QListWidget();layout.addWidget(self.items)
        row=QHBoxLayout();layout.addLayout(row)
        for label,fn in [('Importeren…',self.import_files),('Verwijderen',self.remove_item),('Map openen',self.open_folder),('Sluiten',self.accept)]:
            b=QPushButton(label);b.clicked.connect(fn);row.addWidget(b)
        self.refresh()
    def refresh(self):
        self.items.clear()
        for p in sorted(self.root.iterdir(),key=lambda x:x.name.lower()):
            if p.is_file() and p.suffix.lower() in {'.pes','.exp','.bst'}:self.items.addItem(p.name)
    def import_files(self):
        files,_=QFileDialog.getOpenFileNames(self,'Borduurontwerpen toevoegen','', 'Borduurbestanden (*.pes *.exp *.bst)')
        for f in files:
            src=Path(f);dst=self.root/src.name
            if dst.exists():
                answer=QMessageBox.question(self,'Bestand bestaat',f'{src.name} bestaat al. Overschrijven?')
                if answer!=QMessageBox.StandardButton.Yes:continue
            try:shutil.copy2(src,dst)
            except Exception as e:QMessageBox.warning(self,'Importeren mislukt',str(e))
        self.refresh()
    def remove_item(self):
        item=self.items.currentItem()
        if not item:return
        p=self.root/item.text()
        if QMessageBox.question(self,'Verwijderen',f'{p.name} definitief uit de bibliotheek verwijderen?')==QMessageBox.StandardButton.Yes:
            try:p.unlink();self.refresh()
            except Exception as e:QMessageBox.warning(self,'Verwijderen mislukt',str(e))
    def open_folder(self):
        try:
            if os.name=='nt':os.startfile(str(self.root))
            else:QMessageBox.information(self,'Bibliotheek',str(self.root))
        except Exception as e:QMessageBox.warning(self,'Map openen mislukt',str(e))
