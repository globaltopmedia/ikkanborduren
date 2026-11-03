"""Tabblad Extra: toverstaf, automatisch borduren, rand, applicatie en realistisch borduurraam."""
import copy
from pathlib import Path
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QPen, QPainterPath, QBrush, QLinearGradient, QTransform, QAction, QKeySequence, QFont
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QGroupBox, QLabel, QComboBox, QCheckBox,
    QSpinBox, QToolBar, QMessageBox, QGraphicsEllipseItem, QGraphicsRectItem)
import design, pro_tools
from save_names import choose_save_file

WAND_FILLS = [('auto', 'Automatisch (smal = satijnsteek, breed = tatami)'), ('fill', 'Tatami — dicht vlak'), ('column', 'Satijnsteek — volgt de vorm'),
              ('satin_fill', 'Satijnvulling — rand tot rand'), ('satin', 'Satijnrand langs de contour'),
              ('both', 'Tatami + satijnrand'), ('applique', 'Applicatie'), ('run', 'Alleen contourlijn')]
BORDER_STITCHES = [('satin', 'Satijnsteek'), ('run', 'Enkele stiklijn'), ('double', 'Dubbele stiklijn'), ('triple', 'Drievoudige stiklijn')]
BORDER_SHAPES = [('contour', 'Volgt de vorm van het ontwerp'), ('rect', 'Rechthoek'), ('oval', 'Ovaal'), ('circle', 'Cirkel')]


class ProUI:
    def build_pro(self):
        self.wand_mode = self.tool.count(); self.tool.addItem('Toverstaf: klik op een kleurvlak')
        page = QWidget(); lay = QVBoxLayout(page)
        intro = QLabel('Extra functies: toverstaf, automatisch borduren met één knop, een rand rondom het werk, applicaties en een borduurraam op ware grootte.')
        intro.setWordWrap(True); lay.addWidget(intro)

        box = QGroupBox('Toverstaf — deel van de afbeelding met 1 klik'); f = QFormLayout(box); lay.addWidget(box)
        self.wand_tolerance = QSpinBox(); self.wand_tolerance.setRange(0, 160); self.wand_tolerance.setValue(32); f.addRow('Kleurtolerantie', self.wand_tolerance)
        self.wand_fill = QComboBox()
        for key, label in WAND_FILLS:self.wand_fill.addItem(label, key)
        f.addRow('Steek voor dit deel', self.wand_fill)
        self.wand_holes = self.number(0, 50, 2, ' mm²', 1); f.addRow('Gaatjes kleiner dan dichtzetten', self.wand_holes)
        self.wand_direct = QCheckBox('Direct steken maken na de klik'); self.wand_direct.setChecked(True); f.addRow(self.wand_direct)
        self.button(f, 'Toverstaf kiezen en klik op de tekening', self.choose_wand)
        note = QLabel('Klik op een kleurvlak in de afbeelding. Hogere tolerantie neemt meer gelijkende tinten mee. Het vlak blijft daarna gewoon bewerkbaar.'); note.setWordWrap(True); f.addRow(note)

        box = QGroupBox('Automatisch borduren — 1 knop'); f = QFormLayout(box); lay.addWidget(box)
        self.auto_colors = QSpinBox(); self.auto_colors.setRange(2, 16); self.auto_colors.setValue(10); f.addRow('Maximaal aantal kleuren', self.auto_colors)
        self.auto_detail = self.number(0, 50, 2, ' mm²', 1); f.addRow('Kleine details weglaten', self.auto_detail)
        self.min_stitch = self.number(0, 1.5, 0, ' mm', 2); self.min_stitch.setSpecialValueText('uit'); f.addRow('Kleine steken weglaten onder', self.min_stitch)
        self.auto_applique = self.number(0, 500, 0, ' cm²', 0); self.auto_applique.setSpecialValueText('uit'); f.addRow('Grote vlakken als applicatie vanaf', self.auto_applique)
        self.button(f, 'Automatisch borduren (kleuren, details, steken)', self.auto_digitize)
        note = QLabel('Vereenvoudigt de kleuren, laat kleine details en te korte steken weg en kiest per vlak stiklijn, satijn, tatami of applicatie. Ideaal voor tekeningen en logo’s; foto’s worden niet als foto-borduursel verwerkt.'); note.setWordWrap(True); f.addRow(note)

        box = QGroupBox('Afwerking — rand rondom het ontwerp'); f = QFormLayout(box); lay.addWidget(box)
        self.border_stitch = QComboBox()
        for key, label in BORDER_STITCHES:self.border_stitch.addItem(label, key)
        f.addRow('Steek', self.border_stitch)
        self.border_width = self.number(1, 5, 3, ' mm', 1); f.addRow('Satijnbreedte', self.border_width)
        self.border_distance = self.number(0, 50, 3, ' mm', 1); f.addRow('Afstand vanaf buitenrand werk', self.border_distance)
        self.border_shape = QComboBox()
        for key, label in BORDER_SHAPES:self.border_shape.addItem(label, key)
        f.addRow('Vorm', self.border_shape)
        self.border_scope = QComboBox(); self.border_scope.addItems(['Hele ontwerp', 'Alleen geselecteerde vlakken']); f.addRow('Rand om', self.border_scope)
        self.border_color = '#1d3557'; self.border_color_button = self.button(f, 'Randkleur kiezen', self.choose_border_color)
        self.border_color_button.setStyleSheet(f'background:{self.border_color};color:white;')
        self.border_stitch.currentIndexChanged.connect(lambda *_:self.border_width.setEnabled(self.border_stitch.currentData() == 'satin'))
        self.button(f, 'Rand toevoegen of vervangen', self.add_border)
        self.button(f, 'Rand verwijderen', self.remove_border)

        box = QGroupBox('Applicatie — automatisch of met de hand in delen'); f = QFormLayout(box); lay.addWidget(box)
        self.applique_cover = self.number(1, 5, 3, ' mm', 1); f.addRow('Breedte satijnrand', self.applique_cover)
        self.applique_tack = QComboBox()
        for key, label in design.APPLIQUE_TACKS.items():self.applique_tack.addItem(label, key)
        f.addRow('Vastzetsteek', self.applique_tack)
        self.button(f, 'Geselecteerde vlakken worden applicatie', self.selection_to_applique)
        self.button(f, 'Applicatiedeel met de hand tekenen', self.draw_applique)
        self.button(f, 'Snijpatroon applicatiedelen bewaren (SVG)', self.export_applique_svg)
        note = QLabel('Iedere applicatie: 1) plaatsingslijn — machine stopt, stof neerleggen; 2) vastzetsteek — machine stopt, stof bijknippen; 3) satijnrand. Teken meerdere delen voor een applicatie in delen; de volgorde staat in de onderdelenlijst.'); note.setWordWrap(True); f.addRow(note)

        box = QGroupBox('Borduurraam'); f = QFormLayout(box); lay.addWidget(box)
        self.hoop_choice = QComboBox(); self.hoop_choice.addItems([h[0] for h in design.HOOPS]); self.hoop_choice.setCurrentIndex(self.presets.currentIndex()); f.addRow('Raam', self.hoop_choice)
        self.hoop_choice.currentIndexChanged.connect(self.presets.setCurrentIndex)
        self.presets.currentIndexChanged.connect(self._sync_hoop_choice)
        self.real_hoop = QCheckBox('Borduurraam realistisch tonen'); self.real_hoop.setChecked(True); self.real_hoop.toggled.connect(self.refresh); f.addRow(self.real_hoop)
        self.hoop_grid = QCheckBox('Raamsjabloon: raster van 1 cm'); self.hoop_grid.setChecked(True); self.hoop_grid.toggled.connect(self.refresh); f.addRow(self.hoop_grid)
        self.button(f, 'Ware grootte op het scherm (100%)', self.true_size)
        note = QLabel('Het borduurbereik is op ware maat. De buitenkant van de ring is een illustratie. Ware grootte gebruikt de schermresolutie van Windows; controleer zo nodig met een liniaal.'); note.setWordWrap(True); f.addRow(note)
        lay.addStretch(); self.add_page(page, 'Extra'); self.pro_page = self.tabs.widget(self.tabs.count() - 1)

        self.addToolBarBreak(); toolbar = QToolBar('Extra functies', self); toolbar.setObjectName('extra_toolbar'); self.addToolBar(toolbar)
        for text, fn, key in [('Toverstaf', self.choose_wand, 'W'), ('Automatisch borduren', self.auto_digitize, None),
                              ('Rand toevoegen', self.add_border, None), ('Applicatie', self.selection_to_applique, None),
                              ('Ware grootte', self.true_size, None)]:
            action = QAction(text, self); action.triggered.connect(fn)
            if key:action.setShortcut(QKeySequence(key))
            toolbar.addAction(action)
        toolbar.addWidget(QLabel(' Raam: ')); self.toolbar_hoop = QComboBox(); self.toolbar_hoop.addItems([h[0] for h in design.HOOPS]); self.toolbar_hoop.setCurrentIndex(self.presets.currentIndex()); toolbar.addWidget(self.toolbar_hoop)
        self.toolbar_hoop.currentIndexChanged.connect(self.presets.setCurrentIndex)
        from action_icons import install_icons
        install_icons(self)

    def _sync_hoop_choice(self, index):
        for combo in (getattr(self, 'hoop_choice', None), getattr(self, 'toolbar_hoop', None)):
            if combo is not None and combo.currentIndex() != index:
                combo.blockSignals(True); combo.setCurrentIndex(index); combo.blockSignals(False)

    def pro_settings(self):
        if not hasattr(self, 'min_stitch'):return {}
        return dict(min_stitch_mm=self.min_stitch.value(), real_hoop=self.real_hoop.isChecked(), hoop_grid=self.hoop_grid.isChecked())

    def load_pro_settings(self, settings):
        if not hasattr(self, 'min_stitch'):return
        self.min_stitch.setValue(float(settings.get('min_stitch_mm', 0)))
        self._sync_hoop_choice(self.presets.currentIndex())

    # Toverstaf ---------------------------------------------------------
    def choose_wand(self):
        if self.image is None:return self.error('Open of plak eerst een afbeelding; daarna klik je met de toverstaf op een kleurvlak.')
        self.tool.setCurrentIndex(self.wand_mode); self.tabs.setCurrentWidget(self.pro_page)
        self.status.setText('Toverstaf actief: klik op een kleurvlak in de afbeelding.')

    def magic_wand(self, p):
        if self.worker and self.worker.isRunning():return
        if self.image is None:return self.error('Open of plak eerst een afbeelding.')
        try:
            objects = pro_tools.wand_region(self.image, self.width.value(), p.x() / 10 - self.image_offset[0], p.y() / 10 - self.image_offset[1],
                                            self.wand_tolerance.value(), self.background.isChecked(), self.wand_holes.value())
            key = self.wand_fill.currentData()
            for obj in objects:
                design.transform_object(obj, *self.image_offset)
                obj.update(self.object_options()); obj['angle'] = self.global_fill_angle
                if key == 'auto':pro_tools.choose_fill(obj)
                elif key == 'applique':pro_tools.make_applique(obj, self.applique_cover.value(), self.applique_tack.currentData())
                else:obj['fill'] = key
                obj['name'] = f'Toverstaf {len(self.objects) + 1}'
                # Same-looking tint as an existing part: use that thread, so the
                # parts are sewn in one colour block instead of one block per click.
                same = design.matching_colour(obj['color'], [o['color'] for o in self.objects])
                if same:obj['color'] = same
                design.validate_object(obj)
        except Exception as e:return self.error(e)
        self.checkpoint(); self.objects.extend(objects)
        self.selected_object = objects[0]['id']; self.selected_object_ids = {o['id'] for o in objects}; self.selected.clear()
        self.reference_only = True; self.reference_checkbox.blockSignals(True); self.reference_checkbox.setChecked(True); self.reference_checkbox.blockSignals(False)
        self.mark_objects_changed(); self.sync_object_controls(); self.refresh()
        if self.wand_direct.isChecked():
            self.generation_scope = None; self.launch_objects(checkpoint=False)

    # Automatisch -------------------------------------------------------
    def auto_digitize(self):
        if self.worker and self.worker.isRunning():return
        if self.image is None:return self.error('Open of plak eerst een tekening of logo.')
        if self.objects and QMessageBox.question(self, 'Automatisch borduren', 'De bestaande vlakken vervangen door een automatisch gemaakt ontwerp?') != QMessageBox.StandardButton.Yes:return
        try:
            objects, cleaned, palette = pro_tools.auto_objects(self.image, self.width.value(), self.auto_colors.value(), self.auto_detail.value(),
                self.smooth.value(), self.background.isChecked(), self.color_tolerance.value(), applique_cm2=self.auto_applique.value(),
                angle=self.global_fill_angle, spacing=self.spacing.value(), length=self.length.value())
            for obj in objects:
                design.transform_object(obj, *self.image_offset)
                if obj['fill'] == 'applique':obj.update(satin=self.applique_cover.value(), applique_tack=self.applique_tack.currentData())
        except Exception as e:return self.error(e)
        self.checkpoint()
        if not self.min_stitch.value():self.min_stitch.setValue(.4)
        self.objects = objects; self.image = cleaned; self.palette = palette; self.generation_scope = None
        self.selected_object = None; self.selected_object_ids = set(); self.selected.clear()
        self.reference_only = True; self.reference_checkbox.blockSignals(True); self.reference_checkbox.setChecked(True); self.reference_checkbox.blockSignals(False)
        self.mark_objects_changed(); self.refresh()
        counts = {}
        for obj in objects:counts[design.FILL_NAMES[obj['fill']].split(' —')[0]] = counts.get(design.FILL_NAMES[obj['fill']].split(' —')[0], 0) + 1
        summary = ', '.join(f'{n}× {k}' for k, n in counts.items())
        self.launch_objects(checkpoint=False, after=lambda: self.status.setText(f'Automatisch ontwerp: {len(objects)} vlakken ({summary}); {self.pattern.extras.get("short_stitches_removed", 0)} korte steken weggelaten.'))

    # Rand --------------------------------------------------------------
    def choose_border_color(self):
        from PySide6.QtWidgets import QColorDialog
        color = QColorDialog.getColor(QColor(self.border_color), self, 'Kleur van de rand')
        if not color.isValid():return
        self.border_color = color.name(); self.border_color_button.setStyleSheet(f'background:{self.border_color};color:' + ('white' if color.lightness() < 140 else 'black'))
        for obj in self.objects:
            if obj.get('border'):obj['color'] = self.border_color
        self.refresh()

    def add_border(self):
        if self.worker and self.worker.isRunning():return
        source = [o for o in self.objects if not o.get('border')]
        if self.border_scope.currentIndex() == 1:
            ids = self.chosen_ids() if hasattr(self, 'chosen_ids') else self.selected_object_ids
            source = [o for o in source if o['id'] in ids]
            if not source:return self.error('Selecteer eerst de vlakken waar de rand omheen moet.')
        try:
            borders = pro_tools.border_objects(source, self.border_distance.value(), self.border_width.value(), self.border_stitch.currentData(),
                                               self.border_shape.currentData(), self.border_color)
        except Exception as e:return self.error(e)
        self.checkpoint(); self.objects = [o for o in self.objects if not o.get('border')] + borders
        self.selected_object = borders[0]['id']; self.selected_object_ids = {b['id'] for b in borders}; self.generation_scope = None
        self.mark_objects_changed(); self.sync_object_controls(); self.refresh()
        if self.pattern or self.auto_shape.isChecked():self.launch_objects(checkpoint=False)

    def remove_border(self):
        if not any(o.get('border') for o in self.objects):return self.error('Er is geen rand in dit ontwerp.')
        self.checkpoint(); self.objects = [o for o in self.objects if not o.get('border')]; self.selected_object = None; self.selected_object_ids = set()
        self.mark_objects_changed(); self.refresh()
        if self.pattern:self.launch_objects(checkpoint=False)

    # Applicatie --------------------------------------------------------
    def selection_to_applique(self):
        ids = set(self.chosen_ids()) if hasattr(self, 'chosen_ids') else set(self.selected_object_ids)
        if self.selected_object:ids.add(self.selected_object)
        targets = [o for o in self.objects if o['id'] in ids]
        if not targets:return self.error('Selecteer eerst één of meer gesloten vlakken (klik, sleep of Ctrl+A).')
        try:
            changed = [pro_tools.make_applique(copy.deepcopy(o), self.applique_cover.value(), self.applique_tack.currentData()) for o in targets]
            for obj in changed:design.validate_object(obj)
        except Exception as e:return self.error(e)
        self.checkpoint()
        for obj, new in zip(targets, changed):obj.clear(); obj.update(new)
        self.mark_objects_changed(); self.sync_object_controls(); self.refresh()
        self.status.setText(f'{len(targets)} applicatiedeel/delen. Maak steken om plaatsingslijn, stops en satijnrand te zien.')

    def draw_applique(self):
        self.object_fill.setCurrentIndex(self.object_fill.findData('applique')); self.object_satin.setValue(self.applique_cover.value())
        self.object_name.setText('Applicatie'); self.start_shape()

    def export_applique_svg(self):
        pieces = [o for o in self.objects if o.get('fill') == 'applique' and o.get('visible', True)]
        if not pieces:return self.error('Er zijn nog geen applicatiedelen.')
        path, _ = choose_save_file(self, 'Snijpatroon bewaren', 'Applicatie_snijpatroon.svg', 'SVG (*.svg)')
        if not path:return
        try:design.objects_svg(pieces, Path(path).with_suffix('.svg')); self.status.setText('Snijpatroon op ware grootte bewaard (in mm). Print op 100%.')
        except Exception as e:self.error(e)

    # Borduurraam -------------------------------------------------------
    def true_size(self):
        screen = self.screen() or self.canvas.screen()
        dpi = screen.logicalDotsPerInchX() if screen else 96.
        factor = dpi / 254.  # scene-eenheid is 0,1 mm
        self.canvas.setTransform(QTransform.fromScale(factor, factor)); self.canvas.centerOn(0, 0)
        self.status.setText(f'Ware grootte: 1 mm op tekening = 1 mm op scherm (bij {dpi:.0f} dpi).')
        self.refresh()

    def draw_pro(self):
        if not hasattr(self, 'real_hoop'):return
        scene = self.canvas.scene(); hw, hh = self.hoop_w.value() * 10, self.hoop_h.value() * 10; oval = self.oval.isChecked()
        field = QRectF(-hw / 2, -hh / 2, hw, hh)
        for item in scene.items():
            if isinstance(item, (QGraphicsEllipseItem, QGraphicsRectItem)) and item.rect() == field and item.zValue() == 0:item.setZValue(-1)
        if self.hoop_grid.isChecked():
            import math
            grid = QPainterPath(); rx, ry = hw / 2, hh / 2
            def span(v, r, other):
                # Halve lengte van een rasterlijn binnen ovaal of rechthoek.
                return other * math.sqrt(max(0., 1 - (v / r) ** 2)) if oval else other
            for k in range(-int(rx // 100), int(rx // 100) + 1):
                x = k * 100; half = span(x, rx, ry)
                if half > 0:grid.moveTo(x, -half); grid.lineTo(x, half)
            for k in range(-int(ry // 100), int(ry // 100) + 1):
                y = k * 100; half = span(y, ry, rx)
                if half > 0:grid.moveTo(-half, y); grid.lineTo(half, y)
            pen = QPen(QColor('#cfe1f2'), 1); pen.setCosmetic(True); scene.addPath(grid, pen).setZValue(-.6)
            pen = QPen(QColor('#7aa7d1'), 1, Qt.PenStyle.DashLine); pen.setCosmetic(True)
            scene.addLine(-rx, 0, rx, 0, pen).setZValue(-.5); scene.addLine(0, -ry, 0, ry, pen).setZValue(-.5)
        outline = pro_tools.hoop_outline(self.presets.currentIndex())
        if not self.real_hoop.isChecked() or outline is None:return
        _, _, frame, hoop_oval = outline; frame *= 10
        inner = field.adjusted(-25, -25, 25, 25); outer = field.adjusted(-frame - 25, -frame - 25, frame + 25, frame + 25)
        def shape(rect, radius):
            path = QPainterPath()
            if hoop_oval:path.addEllipse(rect)
            else:path.addRoundedRect(rect, radius, radius)
            return path
        ring = shape(outer, 220).subtracted(shape(inner, 120))
        gradient = QLinearGradient(outer.topLeft(), outer.bottomRight()); gradient.setColorAt(0, QColor('#e9edf1')); gradient.setColorAt(.5, QColor('#c3cad2')); gradient.setColorAt(1, QColor('#9aa4af'))
        edge = QPen(QColor('#68737e'), 1.5); edge.setCosmetic(True)
        scene.addPath(ring, edge, QBrush(gradient)).setZValue(-3)
        split = QPen(QColor('#7e8994'), 1); split.setCosmetic(True)
        scene.addPath(shape(outer.adjusted(frame * .45, frame * .45, -frame * .45, -frame * .45), 180), split).setZValue(-2.9)
        def rounded(rect, radius, colour):
            path = QPainterPath(); path.addRoundedRect(rect, radius, radius); return scene.addPath(path, edge, colour)
        # Spanschroef rechts en bevestigingsbeugel links (illustratie).
        screw = QRectF(outer.right() - 40, -170, 230, 340)
        rounded(screw, 40, QColor('#b3bcc5')).setZValue(-3.1)
        scene.addEllipse(QRectF(screw.right() - 150, -60, 120, 120), edge, QColor('#8b96a1')).setZValue(-3)
        bracket = QRectF(outer.left() - 330, -280, 380, 560)
        rounded(bracket, 30, QColor('#5d6873')).setZValue(-3.2)
        for dy in (-160, 160):scene.addEllipse(QRectF(bracket.left() + 90, dy - 45, 90, 90), edge, QColor('#d0d6dc')).setZValue(-3.1)
        mark = QPen(QColor('#3a4651'), 2); mark.setCosmetic(True)
        for a, b in [((0, inner.top()), (0, outer.top() + frame * .3)), ((0, inner.bottom()), (0, outer.bottom() - frame * .3)),
                     ((inner.left(), 0), (outer.left() + frame * .3, 0)), ((inner.right(), 0), (outer.right() - frame * .3, 0))]:
            scene.addLine(a[0], a[1], b[0], b[1], mark).setZValue(-2.8)
        name = design.HOOPS[self.presets.currentIndex()][0]
        label = scene.addText(f'{name} — borduurbereik op ware grootte'); label.setDefaultTextColor(QColor('#3a4651'))
        label.setFlag(label.GraphicsItemFlag.ItemIgnoresTransformations); label.setPos(outer.left(), outer.bottom() + 20); label.setZValue(-2.8)
