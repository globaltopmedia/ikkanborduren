"""Letter library, manual sequencing and direct USB saving for Studio2."""
from pathlib import Path
import copy,os
from PySide6.QtCore import Qt,QSettings,QStorageInfo,QTimer
from PySide6.QtGui import QFont,QFontDatabase,QColor,QPixmap,QPainter,QPen
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QPushButton,QComboBox,QCheckBox,QListWidget,QListWidgetItem,QLineEdit,QFontComboBox,QFileDialog,QMessageBox,QAbstractItemView)
import design,lettering,sequence,usb_export

class ExtraUI:
    def build_extras(self):
        self.preferences=QSettings('BorduurStudio','BorduurStudio2')
        # Persistent favourites are names of fonts installed on this laptop.
        page=QWidget();lay=QVBoxLayout(page);form=QFormLayout();lay.addLayout(form)
        self.text_input=QLineEdit('NJORD');form.addRow('Tekst',self.text_input)
        self.font_picker=QFontComboBox();self.font_picker.setFontFilters(QFontComboBox.FontFilter.ScalableFonts);form.addRow('Lettertypebibliotheek',self.font_picker)
        self.font_favourites=QComboBox();self.font_favourites.addItem('Kies een favoriet…');form.addRow('Mijn favorieten',self.font_favourites)
        self.button(lay,'Lettertype aan favorieten toevoegen',self.add_font_favourite);self.button(lay,'Eigen TTF / OTF toevoegen',self.import_font)
        self.load_font_library()
        self.tabs.setTabText(1,'Ring')
        self.optimize.toggled.connect(self.routing_changed)
        self.font_favourites.activated.connect(self.select_font_favourite)
        self.text_bold=QCheckBox('Vet');form.addRow(self.text_bold)
        self.text_height=self.number(3,80,12,' mm');form.addRow('Hoofdletterhoogte',self.text_height)
        self.text_tracking=self.number(0,20,1,' mm',2);form.addRow('Extra letterafstand',self.text_tracking)
        self.text_arc=self.number(-180,180,0,'°');form.addRow('Boog: 0° is recht',self.text_arc)
        self.text_fill=QComboBox()
        for key in ('fill','satin','both','run','triple'):self.text_fill.addItem(design.FILL_NAMES[key],key)
        form.addRow('Lettersteken',self.text_fill)
        self.text_color='#159552';self.text_color_button=QPushButton('Letterkleur kiezen');lay.addWidget(self.text_color_button);self.text_color_button.clicked.connect(self.choose_text_color)
        self.text_preview=QLabel();self.text_preview.setMinimumHeight(130);self.text_preview.setStyleSheet('background:white;border:1px solid #c8cdd2;');lay.addWidget(self.text_preview)
        self.text_notice=QLabel();self.text_notice.setWordWrap(True);lay.addWidget(self.text_notice)
        self.button(lay,'Tekst als vlakken aan ontwerp toevoegen',self.add_lettering)
        self.button(lay,'Geselecteerde tekstgroep vervangen',lambda:self.add_lettering(replace=True))
        self.button(lay,'Hele tekstgroep verschuiven (X/Y)',self.move_text_group)
        info=QLabel('Lettertypes worden naar bewerkbare contouren omgezet. Vulling en satijn gebruiken de instellingen op Vlakken. Satijn is een contourband. Voor kleine letters zijn dikke, eenvoudige lettertypes het meest bruikbaar. Eigen fonts blijven lokaal; gebruik een font waarvoor je toestemming hebt.');info.setWordWrap(True);lay.addWidget(info);lay.addStretch();self.add_page(page,'Letters')
        for control in (self.text_input,self.text_height,self.text_tracking,self.text_arc):
            signal=control.textChanged if isinstance(control,QLineEdit) else control.valueChanged;signal.connect(self.schedule_text_preview)
        self.font_picker.currentFontChanged.connect(self.schedule_text_preview);self.text_bold.toggled.connect(self.schedule_text_preview);self.text_fill.currentIndexChanged.connect(self.schedule_text_preview)
        self.preview_timer=QTimer(self);self.preview_timer.setSingleShot(True);self.preview_timer.setInterval(200);self.preview_timer.timeout.connect(self.update_text_preview)
        # A separate order list covers editable objects and imported colour blocks.
        page=QWidget();lay=QVBoxLayout(page);self.order_mode=QComboBox();self.order_mode.addItems(['Automatisch: kleur en kortste beschikbare sprong','Handmatig: exact de volgorde hieronder']);lay.addWidget(self.order_mode)
        self.order_mode.currentIndexChanged.connect(self.order_mode_changed)
        info=QLabel('Sleep onderdelen of gebruik de knoppen. Dit schakelt naar Handmatig. Letters blijven heel; puntjes en accenten komen vóór de hoofdvorm. Onderlaag blijft vóór vulling. De volgorde bepaalt ook welke overlappende vlakken bovenop komen. Bij een EXP/PES-bestand zonder vlakken verplaats je complete kleurblokken.');info.setWordWrap(True);lay.addWidget(info)
        self.order_list=QListWidget();self.order_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove);lay.addWidget(self.order_list)
        self.order_list.model().rowsMoved.connect(self.order_dragged)
        row=QHBoxLayout();lay.addLayout(row);self.button(row,'Eerder ↑',lambda:self.move_sequence(-1));self.button(row,'Later ↓',lambda:self.move_sequence(1))
        row=QHBoxLayout();lay.addLayout(row);self.button(row,'Als eerste',lambda:self.move_sequence(-10000));self.button(row,'Als laatste',lambda:self.move_sequence(10000))
        self.button(lay,'Maak steken in gekozen volgorde',self.generate)
        self.order_notice=QLabel();self.order_notice.setWordWrap(True);lay.addWidget(self.order_notice);self.add_page(page,'Volgorde')
        self._order_refreshing=False
        # One click exports to the remembered destination; initial setup asks for
        # the actual USB folder. Missing media never creates a substitute folder.
        self.usb_button=QPushButton('Opslaan op USB');self.usb_button.clicked.connect(self.save_usb)
        # The top action bar is a sibling of the tab/canvas row.
        self.centralWidget().layout().itemAt(0).layout().addWidget(self.usb_button)
        page=self.tabs.widget(1).widget();form=QFormLayout();page.layout().insertLayout(2,form)
        self.usb_name=QLineEdit(str(self.preferences.value('usb_name','Mijn_ontwerp')));form.addRow('USB-bestandsnaam',self.usb_name)
        self.usb_format=QComboBox();self.usb_format.addItems(['Bernina — EXP + INF + BMP','Brother — PES']);form.addRow('USB-formaat',self.usb_format)
        self.usb_format.setCurrentIndex(int(self.preferences.value('usb_format',0)))
        self.usb_target=QLabel(str(self.preferences.value('usb_directory','Nog geen USB-map gekozen')));self.usb_target.setWordWrap(True);form.addRow('USB-map',self.usb_target)
        self.button(form,'USB-stick / map kiezen',self.choose_usb)
        self.schedule_text_preview()
    def routing_changed(self,*args):
        if self.objects:self.mark_objects_changed()
        self.refresh()
    def load_font_library(self):
        self.font_favourites.blockSignals(True);self.font_favourites.clear();self.font_favourites.addItem('Kies een favoriet…')
        paths=self.preferences.value('font_files',[]) or []
        if isinstance(paths,str):paths=[paths]
        if not getattr(self,'_fonts_loaded',False):
            for path in paths:
                if Path(path).is_file():QFontDatabase.addApplicationFont(path)
            self._fonts_loaded=True
        favourites=self.preferences.value('font_favourites',[]) or []
        if isinstance(favourites,str):favourites=[favourites]
        self.font_favourites.addItems([f for f in favourites if f in QFontDatabase.families()]);self.font_favourites.blockSignals(False)
    def add_font_favourite(self):
        family=self.font_picker.currentFont().family();items=[self.font_favourites.itemText(i) for i in range(1,self.font_favourites.count())]
        if family not in items:items.append(family)
        self.preferences.setValue('font_favourites',items);self.load_font_library()
    def select_font_favourite(self,index):
        if index:self.font_picker.setCurrentFont(QFont(self.font_favourites.itemText(index)))
    def import_font(self):
        path,_=QFileDialog.getOpenFileName(self,'Eigen lettertype toevoegen','','Lettertypes (*.ttf *.otf)')
        if not path:return
        font_id=QFontDatabase.addApplicationFont(path)
        if font_id<0:return self.error('Dit lettertype kon niet worden gelezen.')
        # Keep a durable private local copy so moving the original doesn't break
        # the font library at the next start. Never bundle it into a USB project.
        import shutil,hashlib
        from PySide6.QtCore import QStandardPaths
        target=Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))/'fonts';target.mkdir(parents=True,exist_ok=True)
        copied=target/(hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]+Path(path).suffix.lower());shutil.copyfile(path,copied)
        paths=self.preferences.value('font_files',[]) or []
        if isinstance(paths,str):paths=[paths]
        if str(copied) not in paths:paths.append(str(copied))
        self.preferences.setValue('font_files',paths);self.font_picker.setCurrentFont(QFont(QFontDatabase.applicationFontFamilies(font_id)[0]));self.add_font_favourite()
    def choose_text_color(self):
        from PySide6.QtWidgets import QColorDialog
        color=QColorDialog.getColor(QColor(self.text_color),self,'Letterkleur')
        if color.isValid():self.text_color=color.name();self.schedule_text_preview()
    def lettering_objects(self):
        options=self.object_options();options['fill']=self.text_fill.currentData()
        return lettering.text_objects(self.text_input.text(),self.font_picker.currentFont().family(),self.text_height.value(),self.text_arc.value(),self.text_tracking.value(),self.text_color,self.text_bold.isChecked(),**options)
    def schedule_text_preview(self,*args):
        if hasattr(self,'preview_timer'):self.preview_timer.start()
    def update_text_preview(self):
        try:
            objects=self.lettering_objects();bounds=[design.object_bounds(o) for o in objects];x0=min(b[0] for b in bounds);y0=min(b[1] for b in bounds);x1=max(b[2] for b in bounds);y1=max(b[3] for b in bounds)
            width=max(280,self.text_preview.width());height=130;scale=min((width-20)/max(1,x1-x0),(height-20)/max(1,y1-y0));pix=QPixmap(width,height);pix.fill(Qt.GlobalColor.white);p=QPainter(pix);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.translate(width/2,height/2);p.scale(scale/10,scale/10);p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(self.text_color))
            from studio2 import object_path
            for obj in objects:p.drawPath(object_path(obj))
            p.end();self.text_preview.setPixmap(pix);self.text_notice.setText(f'{x1-x0:.1f} × {y1-y0:.1f} mm · {len(objects)} bewerkbare lettervlakken · positief/negatief buigt naar beide kanten.');self.text_color_button.setStyleSheet('background:'+self.text_color+';color:white;')
        except Exception as e:self.text_preview.clear();self.text_notice.setText(str(e))
    def add_lettering(self,replace=False):
        if self.draft:return self.error('Sluit of annuleer eerst de contour.')
        try:
            objects=self.lettering_objects();current=self.current_object();group=current.get('text_group') if current else None
            if replace and not group:raise ValueError('Selecteer eerst een letter uit de tekstgroep die je wilt vervangen.')
            self.checkpoint()
            if replace:
                previous=[o for o in self.objects if o.get('text_group')==group];boxes=[design.object_bounds(o) for o in previous];cx=(min(b[0] for b in boxes)+max(b[2] for b in boxes))/2;cy=(min(b[1] for b in boxes)+max(b[3] for b in boxes))/2
                index=next(i for i,o in enumerate(self.objects) if o.get('text_group')==group);self.objects=[o for o in self.objects if o.get('text_group')!=group]
                for obj in objects:design.transform_object(obj,dx=cx,dy=cy)
                self.objects[index:index]=objects
            else:self.objects.extend(objects)
            self.selected_object=objects[0]['id'];self.mark_objects_changed();self.refresh();self.fit()
        except Exception as e:self.error(e)
    def move_text_group(self):
        current=self.current_object();group=current.get('text_group') if current else None
        if not group:return self.error('Selecteer eerst een letter uit de tekstgroep.')
        self.checkpoint()
        for obj in self.objects:
            if obj.get('text_group')==group:design.transform_object(obj,dx=self.dx.value(),dy=self.dy.value())
        self.mark_objects_changed();self.refresh()
    def sync_lettering(self,obj):
        values=obj.get('text_options')
        if not values or not hasattr(self,'text_input'):return
        self.text_input.setText(values['text']);self.font_picker.setCurrentFont(QFont(values['family']));self.text_height.setValue(values['height']);self.text_arc.setValue(values['arc']);self.text_tracking.setValue(values['tracking']);self.text_bold.setChecked(values['bold']);self.text_color=values['color'];self.text_fill.setCurrentIndex(self.text_fill.findData(values['fill']));self.schedule_text_preview()
    def order_mode_changed(self,index):
        if getattr(self,'_order_refreshing',False):return
        if self.objects:self.mark_objects_changed()
        self.refresh()
    def refresh_sequence(self):
        if not hasattr(self,'order_list'):return
        self._order_refreshing=True;current=self.order_list.currentItem();key=current.data(Qt.ItemDataRole.UserRole) if current else None;self.order_list.clear()
        blocks=sequence.colour_blocks(self.pattern) if self.pattern and not self.objects else []
        entries=[(o['id'],o['name'],o['color']) for o in self.objects] if self.objects else [(i,f'Kleurblok {i+1}: {b["thread"].description or ""}',b['thread'].hex_color()) for i,b in enumerate(blocks)]
        for i,(identity,name,color) in enumerate(entries):
            item=QListWidgetItem(f'{i+1}. {name}');item.setData(Qt.ItemDataRole.UserRole,identity);item.setForeground(QColor(color));self.order_list.addItem(item)
            if identity==key:self.order_list.setCurrentItem(item)
        self.order_notice.setText('Maak opnieuw steken na een wijziging van de vlakvolgorde.' if self.objects else 'Kleurblokken worden direct verplaatst. Losse details binnen een geïmporteerd kleurblok zijn geen vlakken.')
        self._order_refreshing=False
    def apply_sequence(self,keys):
        if self.objects:
            mapping={o['id']:o for o in self.objects}
            if set(keys)!=set(mapping):return
            self.checkpoint();self.objects=[mapping[k] for k in keys];self.order_mode.setCurrentIndex(1);self.mark_objects_changed()
        elif self.pattern:
            self.checkpoint();self.pattern=sequence.reorder_blocks(self.pattern,keys);self.stop_playback();self.selected.clear()
        self.refresh()
    def order_dragged(self,*args):
        if self._order_refreshing:return
        keys=[self.order_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.order_list.count())]
        QTimer.singleShot(0,lambda:self.apply_sequence(keys))
    def move_sequence(self,delta):
        i=self.order_list.currentRow();count=self.order_list.count()
        if i<0:return self.error('Selecteer eerst een onderdeel in de volgordelijst.')
        j=max(0,min(count-1,i+delta))
        if i==j:return
        keys=[self.order_list.item(k).data(Qt.ItemDataRole.UserRole) for k in range(count)];key=keys.pop(i);keys.insert(j,key);self.apply_sequence(keys);self.order_list.setCurrentRow(j)
    def choose_usb(self):
        initial=str(self.preferences.value('usb_directory',''))
        if not Path(initial).is_dir() or not initial:
            if os.name=='nt':
                import ctypes
                drives=[chr(i)+':\\' for i in range(65,91) if ctypes.windll.kernel32.GetDriveTypeW(chr(i)+':\\')==2]
                initial=drives[0] if drives else ''
            else:
                roots=[s.rootPath() for s in QStorageInfo.mountedVolumes() if s.isReady() and not s.isReadOnly() and s.rootPath().startswith(('/media/','/run/media/','/Volumes/'))];initial=roots[0] if roots else ''
        directory=QFileDialog.getExistingDirectory(self,'Kies de USB-stick of de map op je USB-stick',initial)
        if directory:self.preferences.setValue('usb_directory',directory);self.usb_target.setText(directory)
        return directory
    def save_usb(self):
        self.request_fabric(self._save_usb_ready,require_pattern=True)
    def _save_usb_ready(self):
        if self.draft:return self.error('Sluit of annuleer eerst de contour.')
        if not self.pattern:return self.error('Maak of open eerst borduursteken.')
        if self.art_changed and not self._preserving_for_save:return self.error('Het ontwerp is gewijzigd. Maak eerst opnieuw steken voordat je het op USB opslaat.')
        if self.presets.currentIndex()==3 and __import__('core').pattern_stats(self.pattern)['height']>251:return self.error('Dit ontwerp vereist meerdere Mega-posities; automatische positiedeling ontbreekt.')
        directory=str(self.preferences.value('usb_directory',''))
        if not directory or not Path(directory).is_dir():
            directory=self.choose_usb()
            if not directory:return
        from save_names import ask_name
        name=ask_name(self,self.usb_name.text(),usb=True)
        if name is None:return
        self.usb_name.setText(name)
        try:
            fmt='exp' if self.usb_format.currentIndex()==0 else 'pes'
            options=dict(pattern=self.pattern,directory=directory,name=name,hoop_width=self.hoop_w.value(),hoop_height=self.hoop_h.value(),oval=self.oval.isChecked(),margin=self.margin.value(),fmt=fmt,image=self.image,palette=self.palette,settings=self.settings())
            try:files=usb_export.save_bundle(**options)
            except FileExistsError:
                if QMessageBox.question(self,'Ontwerp vervangen',f'{name} bestaat al in {directory}. Dit ontwerp en de bijbehorende bestanden vervangen?')!=QMessageBox.StandardButton.Yes:return
                files=usb_export.save_bundle(**options,overwrite=True)
            self.preferences.setValue('usb_name',name);self.preferences.setValue('usb_format',self.usb_format.currentIndex());self.status.setText('Op USB opgeslagen: '+str(Path(directory)/(name+'.'+fmt)))
            QMessageBox.information(self,'USB klaar',f'Ontwerp opgeslagen in:\n{directory}\n\n'+('EXP, INF en BMP staan samen op de stick.\n' if fmt=='exp' else 'PES staat op de stick.\n')+'Ook het bewerkbare BST-project, de kleurenlijst en het steekvoorbeeld zijn bewaard. Werp de USB-stick veilig uit via Windows.')
        except Exception as e:self.error(e)
