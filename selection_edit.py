"""Group editing in physical millimetres; artwork and stitches share transforms."""
import copy, math
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
import pyembroidery as emb
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QAction, QKeySequence, QColor, QPen
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QFormLayout,
    QComboBox, QCheckBox, QLabel, QColorDialog, QMessageBox, QToolBar)
import core, design
from advanced_canvas import AdvancedCanvas


class SelectionCanvas(AdvancedCanvas):
    def mousePressEvent(self, event):
        e = self.editor
        if event.button() == Qt.MouseButton.LeftButton and e.tool.currentIndex() in (0, 1):
            self.start = self.mapToScene(event.position().toPoint())
            if e.tool.currentIndex() == 0:
                self.box = self.scene().addRect(QRectF(self.start, self.start), QPen(QColor('#167ed0'), 2))
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.start is not None and self.editor.tool.currentIndex() in (0, 1):
            if self.box:
                self.box.setRect(QRectF(self.start, self.mapToScene(event.position().toPoint())).normalized())
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.start is not None and self.editor.tool.currentIndex() in (0, 1):
            if event.button() != Qt.MouseButton.LeftButton: return
            p = self.mapToScene(event.position().toPoint())
            start = self.start
            self.start = None
            self.box = None
            if self.editor.tool.currentIndex() == 0:
                self.editor.select_region(QRectF(start, p).normalized(), bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier))
            else:
                self.editor.move_selected((p.x()-start.x())/10, (p.y()-start.y())/10)
            self.editor.refresh()
            return
        super().mouseReleaseEvent(event)


class SelectionEdit:
    def build_selection_edit(self):
        old = self.canvas
        layout = old.parentWidget().layout()
        self.canvas = SelectionCanvas(self)
        layout.replaceWidget(old, self.canvas)
        old.hide(); old.deleteLater()
        self.canvas.setMinimumSize(220, 240)
        self.width.setRange(.1,2000);self.width.setDecimals(4);self.width.setReadOnly(True)
        self.width.setButtonSymbols(self.width.ButtonSymbols.NoButtons)
        self.width.setToolTip('Pas de maat aan op Selectie en maat; zo veranderen tekening en borduursel samen.')
        self.tabs.setMinimumWidth(300); self.tabs.setMaximumWidth(400)
        self.parts_dock.setMinimumWidth(210); self.stitches_dock.setMinimumWidth(210)
        self.tabifyDockWidget(self.parts_dock, self.stitches_dock)
        self.parts_dock.raise_(); self.stitches_dock.hide()
        self.tool.setItemText(0, 'Selecteren met slepen')
        self.tool.setMaximumWidth(205)
        page = QWidget(); lay = QVBoxLayout(page)
        intro = QLabel('Kies Selecteren en trek met de linker muisknop ingedrukt een rechthoek. Ctrl voegt toe. Kies daarna Verplaatsen en sleep: de hele selectie beweegt samen. Alles selecteren: Ctrl+A. Draaien en maat veranderen nemen de tekening mee.')
        intro.setWordWrap(True); lay.addWidget(intro)
        self.selection_mode = QComboBox()
        self.selection_mode.addItems(['Onderdelen + bijbehorende steken', 'Losse steekpunten', 'Alleen tekening (rechthoek)'])
        self.selection_mode.currentIndexChanged.connect(self.clear_edit_selection)
        lay.addWidget(self.selection_mode)
        self.button(lay, 'Selecteren met linkermuisknop', lambda: self.tool.setCurrentIndex(0))
        self.button(lay, 'Alles selecteren (Ctrl+A)', self.select_all)
        self.button(lay, 'Selectie gezamenlijk verplaatsen', lambda: self.tool.setCurrentIndex(1))
        self.button(lay, 'Selectie 90° draaien + tekening', self.rotate_selection)
        self.button(lay, 'Hele ontwerp 90° draaien + tekening', self.rotate)
        self.button(lay, 'Nieuwe kleur voor alleen de selectie', self.recolor_selection)
        self.size_label = QLabel(); self.size_label.setWordWrap(True); lay.addWidget(self.size_label)
        form = QFormLayout(); lay.addLayout(form)
        self.edit_width = self.number(.1, 1000, 100, ' mm', 2)
        self.edit_height = self.number(.1, 1000, 100, ' mm', 2)
        form.addRow('Nieuwe breedte', self.edit_width); form.addRow('Nieuwe hoogte', self.edit_height)
        self.lock_ratio = QCheckBox('Verhouding behouden'); self.lock_ratio.setChecked(True); lay.addWidget(self.lock_ratio)
        self.edit_width.valueChanged.connect(lambda v: self.link_size(v, True))
        self.edit_height.valueChanged.connect(lambda v: self.link_size(v, False))
        self.button(lay, 'Maat toepassen op selectie / hele ontwerp', self.apply_size)
        note = QLabel('Maten zijn in millimeters: 60 mm = 6 cm. Zonder selectie verandert de maat van het hele ontwerp. Bij bestaande steken verandert ook de steekafstand; maak voor een grotere maatwijziging opnieuw steken uit de bewerkbare vlakken. Handmatige wijzigingen aan losse punten worden daarbij vervangen.')
        note.setWordWrap(True); lay.addWidget(note)
        self.show_direction.setText('Steekrichting zichtbaar')
        self.show_direction.setChecked(False)
        self.button(lay, 'Tekening plakken (Ctrl+V)', self.paste_art)
        self.button(lay, 'Compact scherm: kolommen sluiten', self.compact_screen)
        lay.addStretch()
        self.add_page(page, 'Selectie en maat'); self.tabs.setCurrentIndex(self.tabs.count()-1)
        toolbar = QToolBar('Selectie en tekening', self); self.addToolBar(toolbar)
        for text, fn, shortcut in [('Selecteren', lambda: self.tool.setCurrentIndex(0), None),
                ('Alles selecteren', self.select_all, 'Ctrl+A'), ('Verplaatsen', lambda: self.tool.setCurrentIndex(1), None),
                ('Selectie 90°', self.rotate_selection, None), ('Tekening plakken', self.paste_art, 'Ctrl+V')]:
            action = QAction(text, self); action.triggered.connect(fn)
            if shortcut: action.setShortcut(QKeySequence(shortcut))
            toolbar.addAction(action)
        fit_button=next((b for b in self.findChildren(__import__('PySide6.QtWidgets',fromlist=['QPushButton']).QPushButton) if b.text()=='Passend in beeld'),None)
        if fit_button:
            fit_button.parentWidget().layout().removeWidget(fit_button) if fit_button.parentWidget().layout().indexOf(fit_button)>=0 else None
            toolbar.addWidget(fit_button)
        direction = QAction('Steekrichting', self); direction.setCheckable(True)
        direction.toggled.connect(self.show_direction.setChecked)
        self.show_direction.toggled.connect(direction.setChecked); toolbar.addAction(direction)
        edit_direction=QAction('Steekrichting wijzigen',self);edit_direction.triggered.connect(self.open_direction_page);toolbar.addAction(edit_direction)
        for button in self.findChildren(__import__('PySide6.QtWidgets', fromlist=['QPushButton']).QPushButton):
            if button.text() in ('Bestaande steken op deze breedte zetten','Alle vlakken op Ontwerpbreedte zetten'):button.hide()
            if button.text() == 'Bestaande steken 90° draaien': button.setText('Hele ontwerp 90° draaien + tekening')
            if button.text() == 'Schaal en draai geselecteerd vlak':button.setText('Schaal en draai selectie + tekening')
        from action_icons import install_icons
        install_icons(self)
        self.compact_screen()

    def compact_screen(self):
        self.parts_dock.hide(); self.stitches_dock.hide()
        self.fit()

    def clear_edit_selection(self, *args):
        self.selected.clear(); self.selected_object_ids.clear(); self.selected_object = None
        self.edit_rect = None; self.refresh()

    def chosen_ids(self):
        return self.selected_object_ids | ({self.selected_object} if self.selected_object else set())

    def owned_indices(self, ids):
        owners = self.pattern.extras.get('owners', []) if self.pattern else []
        return {i for i, owner in enumerate(owners) if owner in ids and i < len(self.pattern.stitches)
                and (self.pattern.stitches[i][2] & emb.COMMAND_MASK) in (emb.STITCH, emb.JUMP)}

    def select_region(self, rect, add=False):
        if not add: self.clear_edit_selection()
        mode = self.selection_mode.currentIndex()
        self.edit_rect = rect if not add or self.edit_rect is None else self.edit_rect.united(rect)
        if mode == 0 and self.objects:
            from studio2 import object_path
            ids = {o['id'] for o in self.objects if rect.contains(object_path(o).boundingRect())}
            self.selected_object_ids |= ids
            self.selected_object = next(iter(self.selected_object_ids), None)
            self.selected |= self.owned_indices(ids)
        elif mode != 2:
            # Direct call to the original point-selector avoids stale object selection.
            from main import Studio
            Studio.select_region(self, rect, add)
        self.refresh(); self.sync_object_controls()

    def select_all(self):
        self.selected_object_ids = {o['id'] for o in self.objects}
        self.selected_object = next(iter(self.selected_object_ids), None)
        self.selected = {i for i, s in enumerate(self.pattern.stitches) if (s[2] & emb.COMMAND_MASK) in (emb.STITCH, emb.JUMP)} if self.pattern else set()
        self.edit_rect = None
        if self.image is not None and not self.objects and not self.pattern:
            x0,y0,x1,y1=self.image_bounds_mm();self.edit_rect=QRectF(x0*10,y0*10,(x1-x0)*10,(y1-y0)*10)
        self.refresh(); self.sync_object_controls()

    def image_bounds_mm(self):
        w = self.width.value(); h = w*self.image.height/self.image.width
        x, y = self.image_offset
        return x-w/2, y-h/2, x+w/2, y+h/2

    def edit_bounds(self, whole=False):
        points = []; ids = self.chosen_ids()
        owned = self.owned_indices(ids)
        if self.pattern:
            for i, (x,y,c) in enumerate(self.pattern.stitches):
                if (c & emb.COMMAND_MASK) in (emb.STITCH, emb.JUMP) and (whole or i in self.selected or i in owned):
                    points.append((x/10, y/10))
        for obj in self.objects:
            if whole or obj['id'] in ids:
                x0,y0,x1,y1 = design.object_bounds(obj); points.extend([(x0,y0),(x1,y1)])
        if not points and self.image is not None and (whole or self.edit_rect is not None):
            if not whole and self.edit_rect is not None:
                r = self.edit_rect; points.extend([(r.left()/10,r.top()/10),(r.right()/10,r.bottom()/10)])
            else:
                x0,y0,x1,y1 = self.image_bounds_mm(); points.extend([(x0,y0),(x1,y1)])
        if not points:return None
        a = np.asarray(points); return (*a.min(axis=0), *a.max(axis=0))

    def has_edit_selection(self):
        return bool(self.selected or self.chosen_ids() or self.edit_rect is not None)

    def link_size(self, value, width):
        if self._size_updating or not self.lock_ratio.isChecked():return
        b = self.edit_bounds(not self.has_edit_selection())
        if not b:return
        w,h = b[2]-b[0], b[3]-b[1]
        if min(w,h) <= 0:return
        self._size_updating = True
        (self.edit_height if width else self.edit_width).setValue(value*h/w if width else value*w/h)
        self._size_updating = False

    def image_mask(self, whole=False):
        mask = Image.new('L', self.image.size, 255 if whole else 0)
        if whole:return mask
        draw = ImageDraw.Draw(mask); x0,y0,_,_ = self.image_bounds_mm(); scale = self.image.width/self.width.value()
        ids = self.chosen_ids()
        for obj in self.objects:
            if obj['id'] not in ids:continue
            coords = lambda ring: [((x-x0)*scale,(y-y0)*scale) for x,y in design.flattened(ring)]
            if obj.get('closed',True):
                # Build each mask separately, so a hole does not erase another selected object.
                part = Image.new('L', self.image.size); d = ImageDraw.Draw(part)
                d.polygon(coords(obj['nodes']), fill=255)
                for hole in obj.get('holes',[]):d.polygon(coords(hole), fill=0)
                mask = Image.fromarray(np.maximum(np.asarray(mask), np.asarray(part)))
            else:ImageDraw.Draw(mask).line(coords(obj['nodes']), fill=255, width=max(1,round(obj.get('satin',.5)*scale)))
        if not ids and self.edit_rect is not None:
            r = self.edit_rect
            ImageDraw.Draw(mask).rectangle(((r.left()/10-x0)*scale,(r.top()/10-y0)*scale,
                (r.right()/10-x0)*scale,(r.bottom()/10-y0)*scale),fill=255)
        return mask

    def transform_image(self, matrix, offset, whole=False):
        if self.image is None:return
        image = self.image.convert('RGBA'); mask = self.image_mask(whole)
        if not mask.getbbox():return
        box = mask.getbbox(); x0,y0,x1,y1 = self.image_bounds_mm(); unit = self.width.value()/image.width
        corners = np.array([[x0+box[0]*unit,y0+box[1]*unit],[x0+box[2]*unit,y0+box[1]*unit],
            [x0+box[0]*unit,y0+box[3]*unit],[x0+box[2]*unit,y0+box[3]*unit]]) @ matrix.T + offset
        lo = corners.min(axis=0); hi = corners.max(axis=0)
        if not whole:lo=np.minimum(lo,[x0,y0]);hi=np.maximum(hi,[x1,y1])
        # Preserve raster detail on enlargement and avoid rounding away boundary pixels.
        unit = unit*min(1.,float(np.linalg.svd(matrix,compute_uv=False).min()))
        size = np.maximum(1,np.ceil((hi-lo)/unit-1e-8).astype(int))
        if int(size[0])*int(size[1]) > 40_000_000:raise ValueError('De tekening wordt te groot. Kies een kleinere maat.')
        hi = lo+size*unit
        src_unit = self.width.value()/image.width
        inverse = np.linalg.inv(matrix)
        # PIL affine uses output pixel coordinates to retrieve source pixels.
        a = inverse*unit/src_unit; b=(inverse@(lo-offset)-np.array([x0,y0]))/src_unit
        patch = np.array(image); patch[:,:,3] = (patch[:,:,3].astype(np.uint16)*np.array(mask)//255).astype(np.uint8)
        transformed = Image.fromarray(patch).transform(tuple(size),Image.Transform.AFFINE,tuple([a[0,0],a[0,1],b[0],a[1,0],a[1,1],b[1]]),Image.Resampling.NEAREST)
        canvas = Image.new('RGBA',tuple(size))
        if not whole:
            rest=np.array(image);rest[:,:,3]=(rest[:,:,3].astype(np.uint16)*(255-np.array(mask))//255).astype(np.uint8)
            old=Image.fromarray(rest).transform(tuple(size),Image.Transform.AFFINE,
                (unit/src_unit,0,(lo[0]-x0)/src_unit,0,unit/src_unit,(lo[1]-y0)/src_unit),Image.Resampling.NEAREST)
            canvas.alpha_composite(old)
        canvas.alpha_composite(transformed);self.image=canvas;self.source=None
        self.image_offset=list((lo+hi)/2)
        self.width.blockSignals(True);self.width.setValue(size[0]*unit);self.width.blockSignals(False)

    def is_full_selection(self):
        if self.objects and self.chosen_ids() != {o['id'] for o in self.objects}:return False
        if self.pattern:
            allpoints={i for i,s in enumerate(self.pattern.stitches) if (s[2]&emb.COMMAND_MASK) in (emb.STITCH,emb.JUMP)}
            return allpoints <= (self.selected|self.owned_indices(self.chosen_ids()))
        if self.objects:return True
        if self.image is not None and self.edit_rect is not None:
            x0,y0,x1,y1=self.image_bounds_mm()
            return self.edit_rect.contains(QRectF(x0*10,y0*10,(x1-x0)*10,(y1-y0)*10))
        return False

    def transform_edit(self, matrix, offset, whole=False, angle=0):
        whole = whole or self.is_full_selection()
        ids = {o['id'] for o in self.objects} if whole else self.chosen_ids()
        indices = set(range(len(self.pattern.stitches))) if whole and self.pattern else self.selected | self.owned_indices(ids)
        if not whole and not self.has_edit_selection():return self.error('Selecteer eerst een gedeelte, of kies Alles selecteren.')
        self.checkpoint()
        try:self.transform_image(matrix,offset,whole)
        except Exception as exc:self.undo();return self.error(exc)
        for obj in self.objects:
            if obj['id'] not in ids:continue
            for ring in design.object_edit_rings(obj):
                for n in ring:n['x'],n['y']=map(float,matrix@np.array([n['x'],n['y']])+offset)
            # Nonuniform scaling changes the angle as well as the contour.
            v=matrix@np.array([math.cos(math.radians(obj.get('angle',0))),math.sin(math.radians(obj.get('angle',0)))])
            obj['angle']=math.degrees(math.atan2(v[1],v[0]))
            for hint in ('entry_hint','exit_hint'):
                if hint in obj:obj[hint]=list(map(float,matrix@np.array(obj[hint])+offset))
            for guide in obj.get('direction_guides') or []:
                guide['x'],guide['y']=map(float,matrix@np.array([guide['x'],guide['y']])+offset)
                v=matrix@np.array([math.cos(math.radians(guide['angle'])),math.sin(math.radians(guide['angle']))]);guide['angle']=math.degrees(math.atan2(v[1],v[0]))
        if self.pattern:
            for i in indices:
                if i < len(self.pattern.stitches):
                    s=self.pattern.stitches[i];s[0],s[1]=map(float,matrix@np.array(s[:2])+offset*10)
            # Terminal commands do not create stitched segments; owner mappings remain intact.
            self.pattern.extras['manual_selection_edit']=True
        elif ids:self.mark_objects_changed()
        if self.pattern and not indices and self.image is not None:self.art_changed=True
        if self.edit_rect is not None:
            r=self.edit_rect;corners=np.array([[r.left()/10,r.top()/10],[r.right()/10,r.top()/10],
                [r.left()/10,r.bottom()/10],[r.right()/10,r.bottom()/10]])@matrix.T+offset
            lo=corners.min(axis=0)*10;hi=corners.max(axis=0)*10;self.edit_rect=QRectF(lo[0],lo[1],hi[0]-lo[0],hi[1]-lo[1])
        if whole:
            v=matrix@np.array([math.cos(math.radians(self.global_fill_angle)),math.sin(math.radians(self.global_fill_angle))])
            self.global_fill_angle=math.degrees(math.atan2(v[1],v[0]))
            self.global_angle.blockSignals(True);self.global_angle.setValue(self.global_fill_angle);self.global_angle.blockSignals(False)
        self.stop_playback();self.refresh();self.fit()

    def scale_rotate_object(self):
        b=self.edit_bounds()
        if not b:return self.error('Selecteer eerst een vlak of gedeelte.')
        a=math.radians(self.object_rotation.value());scale=self.object_scale.value()/100
        matrix=scale*np.array([[math.cos(a),-math.sin(a)],[math.sin(a),math.cos(a)]])
        centre=np.array([(b[0]+b[2])/2,(b[1]+b[3])/2])
        self.transform_edit(matrix,centre-matrix@centre,angle=self.object_rotation.value())

    def center(self):
        b=self.edit_bounds(True)
        if b:self.transform_edit(np.eye(2),-np.array([(b[0]+b[2])/2,(b[1]+b[3])/2]),True)

    def help(self):
        QMessageBox.information(self,'BorduurStudio 2.5.2 — aan de slag',
            '1. Klik Afbeelding openen, of kopieer een afbeeldingsbestand in Downloads met Ctrl+C en plak hier met Ctrl+V.\n'
            '2. Open Selectie en maat. Houd links ingedrukt en sleep een rechthoek. Ctrl+A selecteert alles.\n'
            '3. Kies Verplaatsen en sleep om alle geselecteerde punten/onderdelen samen te verplaatsen.\n'
            '4. Selectie 90° of Hele ontwerp 90° draait de tekening mee.\n'
            '5. Geef een nieuwe breedte of hoogte in millimeters en klik Maat toepassen.\n'
            '6. Nieuwe kleur verandert alleen het geselecteerde gedeelte.\n'
            '7. Steekrichting bovenaan toont/verbergt de richtingslijn.\n'
            '   Steekrichting wijzigen: kies Geselecteerde vlakken of Alle vlakken, typ de hoek en druk Enter.\n'
            '   Standaard 45°; Ctrl+9 past 90° toe, Ctrl+1 past 180° toe op het gekozen bereik.\n'
            '8. Sla het BST-project op. Kies voor bestaande puntbewerkingen Bestaande steken behouden bij export.\n\n'
            'Voor je Bernina: EXP, INF en BMP samen op de USB-stick. Controleer de ring op de machine en maak een proefborduursel.\n'
            'Zie LEESMIJ.html voor de installatie en verdere uitleg.')

    def rotate(self):
        if self.edit_bounds(True):self.transform_edit(np.array([[0.,-1.],[1.,0.]]),np.zeros(2),True,90)

    def rotate_selection(self):
        b=self.edit_bounds()
        if not b:return self.error('Selecteer eerst een gedeelte.')
        centre=np.array([(b[0]+b[2])/2,(b[1]+b[3])/2]);matrix=np.array([[0.,-1.],[1.,0.]])
        self.transform_edit(matrix,centre-matrix@centre,angle=90)

    def move_selected(self, dx, dy, checkpoint=True):
        self.transform_edit(np.eye(2),np.array([dx,dy]))

    def apply_size(self):
        whole=not self.has_edit_selection();b=self.edit_bounds(whole)
        if not b:return self.error('Open eerst een tekening of borduursel.')
        w,h=b[2]-b[0],b[3]-b[1]
        if min(w,h)<1e-8:return self.error('Een enkele punt of rechte lijn heeft geen breedte én hoogte. Selecteer een groter gedeelte.')
        matrix=np.diag([self.edit_width.value()/w,self.edit_height.value()/h]);centre=np.array([(b[0]+b[2])/2,(b[1]+b[3])/2])
        self.transform_edit(matrix,centre-matrix@centre,whole)

    def recolor_selection(self):
        if not self.has_edit_selection():return self.error('Selecteer eerst het gedeelte dat een nieuwe kleur krijgt.')
        color=QColorDialog.getColor(QColor(self.object_color),self,'Nieuwe kleur: alleen selectie')
        if color.isValid():self.set_selection_color(color.name())

    def set_selection_color(self, color):
        self.checkpoint();ids=self.chosen_ids();indices=self.selected|self.owned_indices(ids)
        if self.image is not None:
            a=np.array(self.image.convert('RGBA'));mask=np.array(self.image_mask())>0
            a[mask,:3]=[QColor(color).red(),QColor(color).green(),QColor(color).blue()];self.image=Image.fromarray(a)
            self.palette=list(dict.fromkeys(self.palette+[(QColor(color).red(),QColor(color).green(),QColor(color).blue())]))
        for obj in self.objects:
            if obj['id'] in ids:obj['color']=color
        if self.pattern and indices:
            p=self.pattern;owners=p.extras.get('owners',[]);new=[];newowners=[];threads=[];block=0;active=None;selection=set()
            original_threads=p.threadlist or [emb.EmbThread('#263b53')]
            for i,s in enumerate(p.stitches):
                cmd=s[2]&emb.COMMAND_MASK
                if cmd==emb.COLOR_CHANGE:block+=1;continue
                original=original_threads[min(block,len(original_threads)-1)]
                target=emb.EmbThread(color) if i in indices and cmd==emb.STITCH else original
                if cmd==emb.STITCH and (active is None or active.color!=target.color):
                    if active is not None:
                        previous=next((v[:2] for v in reversed(new) if (v[2]&emb.COMMAND_MASK) in (emb.STITCH,emb.JUMP)),s[:2])
                        new.append([*previous,emb.COLOR_CHANGE]);newowners.append(None)
                    threads.append(copy.deepcopy(target));active=target
                if i in self.selected:selection.add(len(new))
                new.append(list(s));newowners.append(owners[i] if len(owners)==len(p.stitches) else None)
            p.stitches=new;p.threadlist=threads or original_threads;p.extras['owners']=newowners;p.extras['manual_selection_edit']=True;self.selected=selection
        elif self.pattern and self.image is not None:self.art_changed=True
        self.refresh();self.sync_object_controls()

    def paste_art(self):
        clipboard=QApplication.clipboard();mime=clipboard.mimeData()
        try:
            if mime is not None and mime.hasUrls():
                urls=mime.urls()
                if len(urls)!=1 or not urls[0].isLocalFile():
                    return self.error('Kopieer één afbeeldingsbestand uit Downloads en plak het hier. Gebruik voor andere bestanden Afbeelding openen.')
                path=Path(urls[0].toLocalFile())
                if path.suffix.lower() not in {'.png','.jpg','.jpeg','.bmp','.webp','.svg'}:
                    return self.error('Kopieer een PNG, JPG, BMP, WEBP of SVG. Kies Afbeelding openen voor een borduurpatroon of project.')
                if not path.is_file():return self.error('Dit afbeeldingsbestand is niet meer beschikbaar. Kopieer het opnieuw uit Downloads.')
                from main import open_art
                image=open_art(str(path))
            else:
                q=clipboard.image()
                if q.isNull():
                    return self.error('Kopieer een afbeeldingsbestand in Downloads met Ctrl+C en plak hier met Ctrl+V. Je kunt ook Afbeelding openen gebruiken.')
                from PySide6.QtGui import QImage
                q=q.convertToFormat(QImage.Format.Format_RGBA8888)
                rows=np.frombuffer(bytes(q.bits()),dtype=np.uint8).reshape(q.height(),q.bytesPerLine())
                image=Image.fromarray(rows[:,:q.width()*4].reshape(q.height(),q.width(),4).copy())
            prepared,palette=core.prepare_image(image,self.colors.value(),self.background.isChecked())
        except Exception as error:
            return self.error('De tekening kon niet worden geopend: '+str(error))
        if self.image is not None or self.objects or self.pattern:
            if QMessageBox.question(self,'Tekening plakken','De geplakte tekening vervangt het huidige ontwerp. Sla het eerst op als je het wilt bewaren. Doorgaan?') != QMessageBox.StandardButton.Yes:return
        self.checkpoint();self.image,self.palette=prepared,palette
        self.source=None;self.pattern=None;self.objects=[];self.generation_scope=None;self.art_changed=False
        self.image_offset=[0.,0.];self.reference_only=False;self.reference_checkbox.setChecked(False)
        self.draft=[];self.hole_operation=None;self.hole_target_ids=set();self.active_node=None;self.stop_playback()
        self.show_art.blockSignals(True);self.show_art.setChecked(True);self.show_art.blockSignals(False)
        self.path=None;self.clear_edit_selection();self.refresh();self.fit()

    def refresh(self, *args):
        super().refresh(*args)
        if not hasattr(self,'size_label'):return
        b=self.edit_bounds(True);s=self.edit_bounds() if self.has_edit_selection() else None
        text=lambda box:'—' if box is None else f'{box[2]-box[0]:.2f} × {box[3]-box[1]:.2f} mm'
        measure=('Borduursel: '+f"{core.pattern_stats(self.pattern)['width']:.2f} × {core.pattern_stats(self.pattern)['height']:.2f} mm\n") if self.pattern else ''
        self.size_label.setText(measure+'Ontwerp: '+text(b)+'\nSelectie: '+text(s))
        if self.edit_rect is not None:
            pen=QPen(QColor('#167ed0'),1,Qt.PenStyle.DashLine);pen.setCosmetic(True)
            self.canvas.scene().addRect(self.edit_rect,pen).setZValue(25)
        target=s or b
        if target:
            self._size_updating=True
            self.edit_width.setValue(max(.1,target[2]-target[0]));self.edit_height.setValue(max(.1,target[3]-target[1]))
            self._size_updating=False
