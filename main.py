from save_names import choose_save_file
"""Nederlandstalige desktop editor. Start: python main.py"""
import sys,copy,math,traceback,io
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from PySide6.QtCore import Qt,QRectF,QPointF,QThread,Signal,QStandardPaths,QBuffer,QIODevice
from PySide6.QtGui import QImage,QPixmap,QPainterPath,QPen,QColor,QPainter,QAction,QKeySequence
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,
    QPushButton,QLabel,QDoubleSpinBox,QSpinBox,QCheckBox,QComboBox,QListWidget,QListWidgetItem,
    QFileDialog,QMessageBox,QGraphicsView,QGraphicsScene,QTabWidget,QSplitter,QProgressBar,QColorDialog,QGroupBox,QScrollArea)
from PySide6.QtSvg import QSvgRenderer
import pyembroidery as emb
import core

ROOT=Path(__file__).resolve().parent

def pixmap(image):
    a=image.convert('RGBA');raw=a.tobytes()
    q=QImage(raw,a.width,a.height,a.width*4,QImage.Format.Format_RGBA8888).copy()
    return QPixmap.fromImage(q)

def open_art(path):
    if Path(path).suffix.lower()=='.svg':
        renderer=QSvgRenderer(str(path))
        if not renderer.isValid():raise ValueError('Dit SVG-bestand kon niet worden gelezen.')
        size=renderer.defaultSize();w,h=size.width(),size.height()
        if not w or not h:w,h=1000,1000
        scale=1600/max(w,h);w,h=max(1,round(w*scale)),max(1,round(h*scale))
        q=QImage(w,h,QImage.Format.Format_RGBA8888);q.fill(Qt.GlobalColor.transparent)
        painter=QPainter(q);renderer.render(painter);painter.end()
        return Image.frombytes('RGBA',(w,h),bytes(q.bits()))
    with Image.open(path) as im:
        im.load();return im.convert('RGBA')

class Digitizer(QThread):
    progress=Signal(int,str);done=Signal(object);failed=Signal(str)
    def __init__(self,image,palette,options):
        super().__init__();self.image=image.copy();self.palette=copy.deepcopy(palette);self.options=options
    def run(self):
        try:self.done.emit(core.digitize(self.image,self.palette,progress=self.progress.emit,**self.options))
        except Exception as e:self.failed.emit(str(e))

class Canvas(QGraphicsView):
    def __init__(self,editor):
        super().__init__();self.editor=editor;self.setScene(QGraphicsScene(self));self.start=None;self.box=None
        self.setRenderHint(QPainter.RenderHint.Antialiasing);self.setBackgroundBrush(QColor('#e7ecf1'))
        self.setMinimumSize(440,360);self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
    def wheelEvent(self,event):
        self.scale(1.15 if event.angleDelta().y()>0 else 1/1.15,1.15 if event.angleDelta().y()>0 else 1/1.15)
    def mousePressEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton:return super().mousePressEvent(event)
        p=self.mapToScene(event.position().toPoint());mode=self.editor.tool.currentIndex()
        if mode in (2,3):
            self.editor.checkpoint();self.editor.paint_at(p,mode==3);self.start=p;return
        self.start=p
        if mode==0:
            self.box=self.scene().addRect(QRectF(p,p),QPen(QColor('#167ed0'),2))
        if mode==1 and self.editor.selected:self.editor.checkpoint()
    def mouseMoveEvent(self,event):
        if self.start is None:return super().mouseMoveEvent(event)
        p=self.mapToScene(event.position().toPoint());mode=self.editor.tool.currentIndex()
        if mode in (2,3):self.editor.paint_at(p,mode==3)
        elif mode==0 and self.box:self.box.setRect(QRectF(self.start,p).normalized())
    def mouseReleaseEvent(self,event):
        if self.start is None:return super().mouseReleaseEvent(event)
        p=self.mapToScene(event.position().toPoint());mode=self.editor.tool.currentIndex()
        if mode==0:
            rect=QRectF(self.start,p).normalized();add=bool(event.modifiers()&Qt.KeyboardModifier.ControlModifier)
            self.editor.select_region(rect,add)
        elif mode==1 and self.editor.pattern and self.editor.selected:
            delta=p-self.start;self.editor.move_selected(delta.x()/10,delta.y()/10,checkpoint=False)
        self.start=None;self.box=None;self.editor.refresh()
    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Delete:self.editor.delete_selected()
        else:super().keyPressEvent(event)

class Studio(QMainWindow):
    def __init__(self):
        super().__init__();self.setWindowTitle('BorduurStudio — Bernina 540');self.resize(1240,760)
        self.image=None;self.source=None;self.palette=[];self.pattern=None;self.selected=set();self.history=[];self.future=[];self.worker=None;self.path=None;self.art_changed=False
        self.build();self.refresh()
    def build(self):
        menu=self.menuBar().addMenu('Bestand')
        for title,fn,key in [('Open afbeelding / SVG / steken / project',self.open_file,'Ctrl+O'),('Project opslaan',self.save,'Ctrl+S'),('Logo als SVG opslaan',self.export_svg,None),('Borduurpatroon exporteren',self.export,None)]:
            a=QAction(title,self);a.triggered.connect(fn)
            if key:a.setShortcut(QKeySequence(key))
            menu.addAction(a)
        edit=self.menuBar().addMenu('Bewerken')
        for title,fn,key in [('Afbeelding kopiëren naar klembord',self.copy_image_to_clipboard,'Shift+C'),('Afbeelding plakken vanaf klembord / Print Screen',self.paste_image_from_clipboard,'Shift+V'),('Ongedaan maken',self.undo,'Ctrl+Z'),('Opnieuw',self.redo,'Ctrl+Y'),('Selectie verwijderen',self.delete_selected,'Delete')]:
            a=QAction(title,self);a.triggered.connect(fn);a.setShortcut(QKeySequence(key));a.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut);edit.addAction(a)
        helpmenu=self.menuBar().addMenu('Hulp');a=helpmenu.addAction('Aan de slag');a.triggered.connect(self.help)
        central=QWidget();self.setCentralWidget(central);outer=QVBoxLayout(central)
        top=QHBoxLayout();outer.addLayout(top)
        self.button(top,'Afbeelding openen',self.open_file);self.button(top,'Project opslaan',self.save);self.button(top,'EXP / PES exporteren',self.export)
        self.button(top,'Ongedaan',self.undo);self.button(top,'Opnieuw',self.redo)
        split=QSplitter();outer.addWidget(split,1);tabs=QTabWidget();tabs.setMinimumWidth(320);tabs.setMaximumWidth(390);split.addWidget(tabs)
        art=QWidget();lay=QVBoxLayout(art);tabs.addTab(art,'Afbeelding')
        intro=QLabel('Open een tekening, foto, logo of SVG. Shift+C kopieert de huidige afbeelding; Shift+V plakt een afbeelding vanaf het klembord. Ook werkt Shift+V na Print Screen. De bronafbeelding blijft ongewijzigd totdat je zelf Kleuren vereenvoudigen kiest.');intro.setWordWrap(True);lay.addWidget(intro)
        self.button(lay,'Afbeelding plakken (Shift+V)',self.paste_image_from_clipboard)
        self.button(lay,'Afbeelding kopiëren (Shift+C)',self.copy_image_to_clipboard)
        f=QFormLayout();lay.addLayout(f);self.colors=QSpinBox();self.colors.setRange(2,24);self.colors.setValue(8);f.addRow('Aantal kleuren',self.colors)
        self.background=QCheckBox('Witte achtergrond langs de rand weghalen');self.background.setChecked(False);lay.addWidget(self.background)
        self.button(lay,'Kleuren vereenvoudigen',self.simplify)
        self.palette_list=QListWidget();lay.addWidget(self.palette_list)
        self.palette_list.itemDoubleClicked.connect(lambda _:self.recolor())
        self.button(lay,'Geselecteerde kleur wijzigen',self.recolor);self.button(lay,'Geselecteerde kleur weglaten',self.erase_color)
        self.brush=QDoubleSpinBox();self.brush.setRange(.5,20);self.brush.setValue(3);self.brush.setSuffix(' mm');f2=QFormLayout();f2.addRow('Penseeldikte',self.brush);lay.addLayout(f2)
        self.button(lay,'Logo bewaren als vector (SVG)',self.export_svg)
        note=QLabel('SVG wordt als effen vlakken verwerkt. De export maakt vectorcontouren van deze vlakken. Kleine letters en dunne details vragen handmatige controle.');note.setWordWrap(True);lay.addWidget(note)
        lay.addStretch()
        sew=QWidget();lay=QVBoxLayout(sew);tabs.addTab(sew,'Ring & steken')
        f=QFormLayout();lay.addLayout(f);self.presets=QComboBox();self.presets.addItems(['Eigen maat','Medium — 100 × 130 mm','Large Oval — 145 × 255 mm']);f.addRow('Bernina 540: ring',self.presets)
        self.hoop_w=self.number(40,500,145,' mm');self.hoop_h=self.number(40,500,255,' mm');f.addRow('Borduurbereik breed',self.hoop_w);f.addRow('Borduurbereik hoog',self.hoop_h)
        self.oval=QCheckBox('Ovaal bereik');self.oval.setChecked(True);f.addRow(self.oval)
        self.margin=self.number(0,20,2,' mm');f.addRow('Randmarge',self.margin)
        self.width=self.number(5,400,100,' mm');f.addRow('Ontwerpbreedte',self.width)
        self.height_label=QLabel('—');f.addRow('Hoogte (zelfde verhouding)',self.height_label)
        self.button(lay,'Bestaande steken op deze breedte zetten',self.resize_stitches)
        self.button(lay,'Bestaande steken 90° draaien',self.rotate)
        density=QGroupBox('Nieuwe steken uit de afbeelding');d=QFormLayout(density);lay.addWidget(density)
        self.spacing=self.number(.3,1.5,.35,' mm',2);d.addRow('Rijafstand',self.spacing)
        self.length=self.number(1,5,2.5,' mm',2);d.addRow('Max. nieuwe steeklengte',self.length)
        self.underlay=QCheckBox('Onderlaag in grotere vlakken');self.underlay.setChecked(True);d.addRow(self.underlay)
        self.stitch_mode=QComboBox();self.stitch_mode.addItems(['Dicht vlak (stiksteken)','Satijnrij langs contouren','Dicht vlak + satijnrand']);d.addRow('Steekwijze',self.stitch_mode)
        self.satin_width=self.number(.5,5,3,' mm',2);d.addRow('Satijnbreedte (max. 5 mm)',self.satin_width)
        self.direction=QComboBox();self.direction.addItems(['Horizontaal','Verticaal']);d.addRow('Vulrichting',self.direction)
        self.generate_button=QPushButton('Maak borduursteken');self.generate_button.clicked.connect(self.generate);lay.addWidget(self.generate_button)
        self.progress=QProgressBar();self.progress.setRange(0,100);self.progress.setValue(0);lay.addWidget(self.progress)
        hint=QLabel('Gebruik het werkelijke borduurbereik uit de handleiding, niet de buitenmaat van de ring. De ovaal is een benadering. Controleer ook het borduurgebied op je machine.\n\nStiksteken en satijnsteken blijven maximaal 5 mm lang. Sprongen mogen langer zijn. De volgende beschikbare details van dezelfde kleur worden op afstand gekozen. Altijd proefborduren.');hint.setWordWrap(True);lay.addWidget(hint);lay.addStretch()
        for c in [self.hoop_w,self.hoop_h,self.margin,self.width]:c.valueChanged.connect(self.refresh)
        self.oval.toggled.connect(self.refresh);self.presets.currentIndexChanged.connect(self.set_preset);self.presets.setCurrentIndex(2)
        edit=QWidget();lay=QVBoxLayout(edit);tabs.addTab(edit,'Bewerken')
        tip=QLabel('Sleep een selectievak over steken. Ctrl voegt steken toe. Kies Verplaatsen en sleep de selectie, of gebruik de waarden hieronder. Delete verwijdert de selectie.');tip.setWordWrap(True);lay.addWidget(tip)
        self.selection_label=QLabel('0 steken geselecteerd');lay.addWidget(self.selection_label)
        f=QFormLayout();lay.addLayout(f);self.dx=self.number(-400,400,0,' mm');self.dy=self.number(-400,400,0,' mm');f.addRow('Verschuif X',self.dx);f.addRow('Verschuif Y',self.dy)
        self.button(lay,'Selectie verschuiven',lambda:self.move_selected(self.dx.value(),self.dy.value()))
        self.command=QComboBox();self.command.addItems(['Borduursteek','Sprong (geen steek)']);f.addRow('Type geselecteerde punten',self.command)
        self.button(lay,'Steektype toepassen',self.change_command);self.button(lay,'Geselecteerde steken verwijderen',self.delete_selected)
        self.button(lay,'Alle steekpunten selecteren',self.select_all)
        self.ex=self.number(-400,400,0,' mm');self.ey=self.number(-400,400,0,' mm');f.addRow('Eén punt: X',self.ex);f.addRow('Eén punt: Y',self.ey)
        self.button(lay,'Coördinaten van één punt wijzigen',self.edit_point)
        self.thread_list=QListWidget();lay.addWidget(QLabel('Garenkleuren van het borduurpatroon'));lay.addWidget(self.thread_list)
        self.button(lay,'Garenkleur wijzigen',self.thread_color)
        self.button(lay,'Patroon centreren',self.center)
        self.button(lay,'Grote steken splitsen (max. 5 mm)',self.split_long)
        lay.addStretch()
        right=QWidget();r=QVBoxLayout(right);split.addWidget(right);self.art_notice=QLabel();self.art_notice.setWordWrap(True);self.art_notice.setStyleSheet('color:#945400;background:#fff0ce;padding:6px;');r.addWidget(self.art_notice);bar=QHBoxLayout();r.addLayout(bar)
        self.tool=QComboBox();self.tool.addItems(['Selecteren','Verplaatsen','Kleurpenseel','Gum']);bar.addWidget(self.tool)
        self.show_art=QCheckBox('Afbeelding');self.show_art.setChecked(True);bar.addWidget(self.show_art)
        self.show_sew=QCheckBox('Steken');self.show_sew.setChecked(True);bar.addWidget(self.show_sew)
        self.show_jumps=QCheckBox('Sprongen');bar.addWidget(self.show_jumps)
        self.button(bar,'Passend in beeld',self.fit);self.canvas=Canvas(self);r.addWidget(self.canvas,1)
        self.show_art.toggled.connect(self.refresh);self.show_sew.toggled.connect(self.refresh);self.show_jumps.toggled.connect(self.refresh)
        self.status=QLabel();outer.addWidget(self.status);self.status.setWordWrap(True)
        for i in range(tabs.count()):
            page=tabs.widget(i);title=tabs.tabText(i);tabs.removeTab(i)
            scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(page);tabs.insertTab(i,scroll,title)
        self.setStyleSheet('QMainWindow {background:#f4f6f8;} QPushButton {padding:7px;} QTabWidget::pane {border:1px solid #d5dce4;} QLabel {padding:2px;} QGroupBox {font-weight:600;}')
    def number(self,low,high,value,suffix='',decimals=1):
        w=QDoubleSpinBox();w.setRange(low,high);w.setDecimals(decimals);w.setValue(value);w.setSuffix(suffix);return w
    def button(self,layout,title,fn):
        b=QPushButton(title);b.clicked.connect(fn);layout.addWidget(b);return b
    def error(self,error):QMessageBox.warning(self,'BorduurStudio',str(error))
    def help(self):
        QMessageBox.information(self,'Aan de slag','1. Open een afbeelding of SVG.\n2. Vereenvoudig de kleuren en werk vlakken bij met penseel/gum.\n3. Stel de ontwerpbreedte, ring en randmarge in.\n4. Maak borduursteken. Selecteer en bewerk ze indien nodig.\n5. Bewaar het project (.bst) en exporteer EXP of PES.\n\nBernina: zet EXP, INF en BMP met dezelfde naam samen op de USB-stick. Formaatondersteuning hangt af van je model.\n\nBij vergroten/verkleinen: genereer opnieuw uit de afbeelding om de rijafstand te behouden. Proefborduur eerst. Zie ook de meegeleverde handleiding.')
    def checkpoint(self):
        self.history.append((self.image.copy() if self.image else None,copy.deepcopy(self.palette),core.clone_pattern(self.pattern),self.art_changed))
        self.history=self.history[-12:];self.future.clear()
    def restore(self,back,forward):
        if not back:return
        forward.append((self.image.copy() if self.image else None,copy.deepcopy(self.palette),core.clone_pattern(self.pattern),self.art_changed))
        self.image,self.palette,self.pattern,self.art_changed=back.pop();self.selected.clear();self.refresh()
    def undo(self):self.restore(self.history,self.future)
    def redo(self):self.restore(self.future,self.history)
    def settings(self):
        return {key:getattr(self,key).value() for key in ['width','hoop_w','hoop_h','margin','spacing','length','colors','satin_width']}|{'oval':self.oval.isChecked(),'underlay':self.underlay.isChecked(),'vertical':self.direction.currentIndex()==1,'mode':['fill','satin','both'][self.stitch_mode.currentIndex()],'art_changed':self.art_changed}
    def _exact_palette_or_empty(self, image):
        """Keep imported pixels unchanged. A stitch palette is only ready when it fits the configured limit."""
        rgba=np.asarray(image.convert('RGBA'))
        visible=rgba[:,:,3]>128
        if not visible.any():
            return []
        colors=np.unique(rgba[:,:,:3][visible],axis=0)
        if len(colors)<=self.colors.value():
            return [tuple(map(int,c)) for c in colors]
        # Do not silently quantize the original artwork on import. The user can
        # explicitly choose 'Kleuren vereenvoudigen' when preparing stitch colors.
        return []

    def copy_image_to_clipboard(self):
        image=self.image if self.image is not None else self.source
        if image is None:
            return self.error('Er is nog geen afbeelding om te kopiëren.')
        QApplication.clipboard().setImage(pixmap(image).toImage())
        self.statusBar().showMessage('Afbeelding met behoud van de oorspronkelijke pixelkleuren naar het klembord gekopieerd.',5000)

    def paste_image_from_clipboard(self):
        clipboard=QApplication.clipboard()
        qimage=clipboard.image()
        if qimage.isNull():
            mime=clipboard.mimeData()
            if mime and mime.hasUrls():
                for url in mime.urls():
                    if url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in ('.png','.jpg','.jpeg','.bmp','.webp','.tif','.tiff'):
                        self.load_path(url.toLocalFile())
                        return
            return self.error('Het klembord bevat geen afbeelding. Kopieer eerst een afbeelding of druk op Print Screen en probeer daarna Shift+V opnieuw.')
        buffer=QBuffer();buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not qimage.save(buffer,'PNG'):
            buffer.close();return self.error('De afbeelding op het klembord kon niet worden gelezen.')
        try:
            image=Image.open(io.BytesIO(bytes(buffer.data()))).convert('RGBA')
            buffer.close()
            self.checkpoint();self.selected.clear();self.source=image.copy();self.image=image.copy()
            self.palette=self._exact_palette_or_empty(image);self.pattern=None;self.path=None;self.art_changed=False
            self.show_art.blockSignals(True);self.show_art.setChecked(True);self.show_art.blockSignals(False)
            self.refresh();self.fit()
            if not self.palette:
                self.statusBar().showMessage('Afbeelding geplakt met oorspronkelijke kleuren. Klik alleen indien gewenst op Kleuren vereenvoudigen voor borduursteken.',10000)
        except Exception as e:
            self.error(f'Afbeelding plakken mislukt: {e}')

    def open_file(self):
        downloads=QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation) or str(Path.home())
        path,_=QFileDialog.getOpenFileName(self,'Afbeelding, SVG, borduurpatroon of project openen',downloads,'Ondersteunde bestanden (*.png *.jpg *.jpeg *.bmp *.webp *.svg *.exp *.pes *.dst *.bst);;Alle bestanden (*)')
        if path:self.load_path(path)
    def load_path(self,path):
        try:
            self.checkpoint();self.selected.clear();suffix=Path(path).suffix.lower()
            if suffix=='.bst':
                self.image,self.palette,self.pattern,settings=core.load_project(path)
                for k in ['width','hoop_w','hoop_h','margin','spacing','length','colors','satin_width']:
                    if k in settings:getattr(self,k).setValue(settings[k])
                self.oval.setChecked(settings.get('oval',False));self.underlay.setChecked(settings.get('underlay',True));self.direction.setCurrentIndex(int(settings.get('vertical',False)));self.stitch_mode.setCurrentIndex(['fill','satin','both'].index(settings.get('mode','fill')))
                self.path=path;self.source=self.image.copy() if self.image else None
            elif suffix in ('.exp','.pes','.dst'):
                self.pattern=emb.read(path);core.center_pattern(self.pattern)
                if suffix=='.exp' and Path(path).with_suffix('.inf').exists():
                    colors=emb.EmbPattern()
                    with open(Path(path).with_suffix('.inf'),'rb') as inf:emb.InfReader.read(inf,colors)
                    self.pattern.threadlist=colors.threadlist
                if not self.pattern.threadlist:self.pattern.add_thread('#2B6777')
                self.image=None;self.source=None;self.palette=[];self.path=None
                self.width.setValue(max(5,core.pattern_stats(self.pattern)['width']))
            else:
                image=open_art(path);self.source=image.copy();self.image=image.copy();self.palette=self._exact_palette_or_empty(image);self.pattern=None;self.path=None
            if self.image is not None:
                self.show_art.blockSignals(True);self.show_art.setChecked(True);self.show_art.blockSignals(False)
            self.art_changed=bool(settings.get('art_changed',False)) if suffix=='.bst' else False;self.selected.clear();self.refresh();self.fit()
        except Exception as e:self.error(e)
    def simplify(self):
        if self.image is None:return self.error('Open eerst een afbeelding.')
        try:
            self.checkpoint();self.image,self.palette=core.prepare_image(self.image,self.colors.value(),self.background.isChecked());self.art_changed=self.pattern is not None;self.refresh();self.fit()
        except Exception as e:self.error(e)
    def recolor(self):
        i=self.palette_list.currentRow()
        if i<0 or self.image is None:return
        col=QColorDialog.getColor(QColor(*self.palette[i]),self,'Nieuwe kleur voor het vlak')
        if not col.isValid():return
        self.checkpoint();a=np.array(self.image);mask=np.all(a[:,:,:3]==self.palette[i],axis=2);new=(col.red(),col.green(),col.blue());a[mask,:3]=new
        self.image=Image.fromarray(a);self.palette[i]=new;self.art_changed=self.pattern is not None;self.refresh()
    def erase_color(self):
        i=self.palette_list.currentRow()
        if i<0 or self.image is None:return
        self.checkpoint();a=np.array(self.image);a[np.all(a[:,:,:3]==self.palette[i],axis=2),3]=0;self.image=Image.fromarray(a);self.palette.pop(i);self.art_changed=self.pattern is not None;self.refresh()
    def paint_at(self,p,erase=False):
        if self.image is None:return
        i=self.palette_list.currentRow()
        if not erase and i<0:return
        w=self.width.value()*10;h=w*self.image.height/self.image.width
        x=(p.x()-getattr(self,'image_offset',[0,0])[0]*10+w/2)*self.image.width/w;y=(p.y()-getattr(self,'image_offset',[0,0])[1]*10+h/2)*self.image.height/h
        radius=self.brush.value()*self.image.width/(2*self.width.value())
        if not (0<=x<self.image.width and 0<=y<self.image.height):return
        draw=ImageDraw.Draw(self.image);col=(0,0,0,0) if erase else tuple(self.palette[i])+(255,)
        draw.ellipse((x-radius,y-radius,x+radius,y+radius),fill=col);self.art_changed=self.pattern is not None;self.refresh()
    def set_preset(self,i):
        sizes=[None,(100,130),(145,255)]
        if sizes[i]:self.hoop_w.setValue(sizes[i][0]);self.hoop_h.setValue(sizes[i][1]);self.oval.setChecked(True)
        self.refresh()
        if hasattr(self,'canvas'):self.fit()
    def generate(self):
        if self.worker and self.worker.isRunning():return
        if self.image is None or not self.palette:return self.error('De afbeelding is geïmporteerd met behoud van de oorspronkelijke kleuren. Klik op Kleuren vereenvoudigen om een borduurkleurenpalet te maken; dit kan kleuren samenvoegen.')
        if self.pattern:
            answer=QMessageBox.question(self,'Nieuwe steken','Nieuwe steken vervangen de huidige steekbewerkingen. Doorgaan?')
            if answer!=QMessageBox.StandardButton.Yes:return
        self.checkpoint();self.set_busy(True)
        options={'satin_width':self.satin_width.value(),'width_mm':self.width.value(),'spacing':self.spacing.value(),'max_stitch':self.length.value(),'underlay':self.underlay.isChecked(),'vertical':self.direction.currentIndex()==1,'mode':['fill','satin','both'][self.stitch_mode.currentIndex()]}
        self.worker=Digitizer(self.image,self.palette,options);self.worker.progress.connect(self.on_progress);self.worker.done.connect(self.generated);self.worker.failed.connect(self.failed);self.worker.finished.connect(lambda:self.set_busy(False));self.worker.start()
    def set_busy(self,value):
        self.centralWidget().setEnabled(not value);self.menuBar().setEnabled(not value)
    def on_progress(self,value,text):self.progress.setValue(value);self.status.setText(text)
    def generated(self,p):self.pattern=p;self.art_changed=False;self.selected.clear();self.refresh();self.fit()
    def failed(self,error):self.error(error)
    def select_region(self,rect,add=False):
        if not self.pattern:return
        if not add:self.selected.clear()
        points=[(i,s) for i,s in enumerate(self.pattern.stitches) if (s[2]&emb.COMMAND_MASK) in (emb.STITCH,emb.JUMP)]
        if rect.width()<5 and rect.height()<5 and points:
            i,s=min(points,key=lambda z:math.hypot(z[1][0]-rect.center().x(),z[1][1]-rect.center().y()))
            tolerance=10/self.canvas.transform().m11()
            if math.hypot(s[0]-rect.center().x(),s[1]-rect.center().y())<=tolerance:self.selected.add(i)
        else:self.selected.update(i for i,s in points if rect.contains(QPointF(s[0],s[1])))
    def select_all(self):
        if self.pattern:self.selected={i for i,s in enumerate(self.pattern.stitches) if (s[2]&emb.COMMAND_MASK) in (emb.STITCH,emb.JUMP)};self.refresh()
    def move_selected(self,dx,dy,checkpoint=True):
        if not self.pattern or not self.selected:return
        if checkpoint:self.checkpoint()
        for i in self.selected:self.pattern.stitches[i][0]+=dx*10;self.pattern.stitches[i][1]+=dy*10
        self.refresh()
    def delete_selected(self):
        if not self.pattern or not self.selected:return
        self.checkpoint();core.remove_stitches(self.pattern,self.selected);self.selected.clear();self.refresh()
    def change_command(self):
        if not self.pattern or not self.selected:return
        self.checkpoint();cmd=emb.STITCH if self.command.currentIndex()==0 else emb.JUMP
        for i in self.selected:self.pattern.stitches[i][2]=cmd
        self.refresh()
    def edit_point(self):
        if not self.pattern or len(self.selected)!=1:return self.error('Selecteer precies één steekpunt.')
        self.checkpoint();i=next(iter(self.selected));self.pattern.stitches[i][:2]=[self.ex.value()*10,self.ey.value()*10];self.refresh()
    def resize_stitches(self):
        if not self.pattern:return
        self.checkpoint();core.resize_pattern(self.pattern,self.width.value());self.refresh();self.fit()
    def rotate(self):
        if not self.pattern:return
        self.checkpoint()
        for s in self.pattern.stitches:s[0],s[1]=-s[1],s[0]
        self.refresh();self.fit()
    def center(self):
        if self.pattern:self.checkpoint();core.center_pattern(self.pattern);self.refresh()
    def split_long(self):
        if not self.pattern:return
        self.checkpoint();out=[];last=None
        for s in self.pattern.stitches:
            if last is not None and (s[2]&emb.COMMAND_MASK)==emb.STITCH:
                n=max(1,math.ceil(math.dist(last,s[:2])/49))
                out.extend([[last[0]+(s[0]-last[0])*k/n,last[1]+(s[1]-last[1])*k/n,emb.STITCH] for k in range(1,n)])
            out.append(list(s));last=s[:2]
        self.pattern.stitches=out;self.selected.clear();self.refresh()
    def thread_color(self):
        i=self.thread_list.currentRow()
        if not self.pattern or i<0:return
        t=self.pattern.threadlist[i];col=QColorDialog.getColor(QColor(t.get_red(),t.get_green(),t.get_blue()),self)
        if col.isValid():self.checkpoint();t.set_color(col.red(),col.green(),col.blue());self.refresh()
    def refresh(self,*args):
        if not hasattr(self,'canvas'):return
        self.art_notice.setVisible(self.art_changed);self.art_notice.setText('De afbeelding is gewijzigd. Maak opnieuw steken om deze wijzigingen in het borduurpatroon op te nemen.')
        scene=self.canvas.scene();scene.clear();hw,hh=self.hoop_w.value()*10,self.hoop_h.value()*10;rect=QRectF(-hw/2,-hh/2,hw,hh)
        pen=QPen(QColor('#6c8296'),2);pen.setCosmetic(True)
        if self.oval.isChecked():scene.addEllipse(rect,pen,QColor('#ffffff'))
        else:scene.addRect(rect,pen,QColor('#ffffff'))
        margin=self.margin.value()*10;inside=rect.adjusted(margin,margin,-margin,-margin);dashed=QPen(QColor('#aebbc8'),1,Qt.PenStyle.DashLine);dashed.setCosmetic(True)
        if self.oval.isChecked():scene.addEllipse(inside,dashed)
        else:scene.addRect(inside,dashed)
        axis=QPen(QColor('#d9dfe5'),1);axis.setCosmetic(True);scene.addLine(-hw/2,0,hw/2,0,axis);scene.addLine(0,-hh/2,0,hh/2,axis)
        if self.image:
            w=self.width.value()*10;h=w*self.image.height/self.image.width;self.height_label.setText(f'{h/10:.1f} mm')
            if self.show_art.isChecked():
                item=scene.addPixmap(pixmap(self.image));item.setScale(w/self.image.width);item.setPos(-w/2+getattr(self,'image_offset',[0,0])[0]*10,-h/2+getattr(self,'image_offset',[0,0])[1]*10);item.setOpacity(.28 if self.pattern and self.show_sew.isChecked() else 1)
        else:self.height_label.setText('—')
        if self.pattern and self.show_sew.isChecked():
            paths={};jumps=QPainterPath();last=None;block=0
            for x,y,c in self.pattern.stitches:
                cmd=c&emb.COMMAND_MASK
                if cmd==emb.COLOR_CHANGE:block+=1
                if last is not None and cmd==emb.STITCH:
                    path=paths.setdefault(block,QPainterPath());path.moveTo(*last);path.lineTo(x,y)
                elif last is not None and cmd==emb.JUMP:jumps.moveTo(*last);jumps.lineTo(x,y)
                if cmd in (emb.STITCH,emb.JUMP):last=(x,y)
            for i,path in paths.items():
                t=self.pattern.threadlist[min(i,len(self.pattern.threadlist)-1)] if self.pattern.threadlist else emb.EmbThread('#263b53')
                pen=QPen(QColor(t.get_red(),t.get_green(),t.get_blue()),1.4);pen.setCosmetic(True);scene.addPath(path,pen)
            if self.show_jumps.isChecked():
                pen=QPen(QColor('#bb31b3'),1,Qt.PenStyle.DashLine);pen.setCosmetic(True);scene.addPath(jumps,pen)
            for i in self.selected:
                if i<len(self.pattern.stitches):
                    x,y,_=self.pattern.stitches[i];dot=scene.addEllipse(-3,-3,6,6,QPen(QColor('#0068ee')),QColor('#53ceff'));dot.setPos(x,y)
        row=self.palette_list.currentRow();self.palette_list.clear()
        for i,c in enumerate(self.palette):
            item=QListWidgetItem(f'{i+1}   #{c[0]:02X}{c[1]:02X}{c[2]:02X}');item.setBackground(QColor(*c));item.setForeground(QColor('white' if sum(c)<360 else 'black'));self.palette_list.addItem(item)
        if self.palette:self.palette_list.setCurrentRow(max(0,min(row,len(self.palette)-1)))
        row=self.thread_list.currentRow();self.thread_list.clear()
        if self.pattern:
            for i,t in enumerate(self.pattern.threadlist):
                item=QListWidgetItem(f'{i+1}   #{t.get_red():02X}{t.get_green():02X}{t.get_blue():02X}');item.setBackground(QColor(t.get_red(),t.get_green(),t.get_blue()));item.setForeground(QColor('white' if t.get_red()+t.get_green()+t.get_blue()<360 else 'black'));self.thread_list.addItem(item)
            if self.pattern.threadlist:self.thread_list.setCurrentRow(max(0,min(row,len(self.pattern.threadlist)-1)))
            stats=core.pattern_stats(self.pattern);fits=core.hoop_fits(self.pattern,self.hoop_w.value(),self.hoop_h.value(),self.oval.isChecked(),self.margin.value())
            self.status.setText(f'{stats["width"]:.1f} × {stats["height"]:.1f} mm  |  {stats["stitches"]:,} steken  |  {stats["colors"]} garenkleuren  |  '+('PAST IN INGESTELDE RING' if fits else 'BUITEN INGESTELDE RING — pas maat of positie aan'))
            self.status.setStyleSheet('color:'+('#187b51' if fits else '#b22222')+';font-weight:600;')
        else:self.status.setText('Tekening geopend. Maten zijn in millimeters.' if self.image is not None else 'Open een afbeelding om te beginnen. Maten zijn in millimeters.');self.status.setStyleSheet('')
        self.selection_label.setText(f'{len(self.selected)} steekpunten geselecteerd')
        if self.pattern and len(self.selected)==1:
            s=self.pattern.stitches[next(iter(self.selected))];self.ex.setValue(s[0]/10);self.ey.setValue(s[1]/10)
        scene.setSceneRect(scene.itemsBoundingRect().adjusted(-50,-50,50,50))
    def fit(self):self.canvas.fitInView(self.canvas.sceneRect(),Qt.AspectRatioMode.KeepAspectRatio)
    def save(self):
        if self.image is None and not self.pattern:return self.error('Er is nog geen project om op te slaan.')
        path,_=choose_save_file(self,'Project bewaren',self.path or 'Mijn_borduurpatroon.bst','BorduurStudio project (*.bst)')
        if path:
            try:
                if not path.lower().endswith('.bst'):path+='.bst'
                core.save_project(path,self.image,self.palette,self.pattern,self.settings());self.path=path;self.status.setText('Project bewaard: '+path)
            except Exception as e:self.error(e)
    def export_svg(self):
        if self.image is None:return self.error('Open eerst een afbeelding en vereenvoudig de kleuren.')
        path,_=choose_save_file(self,'Logo bewaren als vector','Mijn_logo.svg','SVG (*.svg)')
        if path:
            try:core.vectorize(self.image,Path(path).with_suffix('.svg'));self.status.setText('Vectorlogo bewaard: '+str(Path(path).with_suffix('.svg')))
            except Exception as e:self.error(e)
    def export(self):
        if not self.pattern:return self.error('Maak of open eerst borduursteken.')
        if self.art_changed:
            answer=QMessageBox.question(self,'Afbeelding gewijzigd','De afbeelding is gewijzigd, maar de bestaande steken zijn nog niet opnieuw gemaakt. Wil je toch de bestaande steken exporteren?')
            if answer!=QMessageBox.StandardButton.Yes:return
        path,filter_=choose_save_file(self,'Borduurpatroon exporteren','Mijn_borduurpatroon.exp','Bernina EXP (*.exp);;Brother / PES (*.pes)')
        if path:
            try:
                fmt='pes' if 'PES' in filter_ else 'exp';out=core.export_bundle(self.pattern,path,self.hoop_w.value(),self.hoop_h.value(),self.oval.isChecked(),self.margin.value(),fmt)
                QMessageBox.information(self,'Export klaar',f'Bewaard: {out}\n\n'+('EXP, INF en BMP staan samen in dezelfde map. Zet deze drie bestanden samen op USB.\n' if fmt=='exp' else '')+'Er is ook een steekvoorbeeld en een kleurenlijst. Controleer op de machine en proefborduur eerst.')
            except Exception as e:self.error(e)
    def closeEvent(self,event):
        if self.worker and self.worker.isRunning():self.error('De omzetting is bezig. Wacht tot die klaar is.');event.ignore()
        else:event.accept()

def run():
    from studio2 import Studio2
    app=QApplication(sys.argv);app.setApplicationName('BorduurStudio');w=Studio2();w.showMaximized();w.fit()
    if len(sys.argv)>1:w.load_path(sys.argv[1])
    sys.exit(app.exec())

if __name__=='__main__':run()
