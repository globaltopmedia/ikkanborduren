"""Onderdeel aanklikken, laten oplichten en direct aanpassen; richtingspijlen.

Klik op een geborduurd deel: het onderdeel wordt in de onderdelenkolom en in de
garenkleurenlijst geselecteerd en licht op in de tekening. Kleur, steeksoort,
steekrichting en gaten zijn daarna direct aan te passen; de steken worden meteen
opnieuw gemaakt.
"""
import copy, math, uuid
import numpy as np
import pyembroidery as emb
from PySide6.QtCore import Qt, QPointF, QItemSelectionModel
from PySide6.QtGui import QColor, QPen, QPainterPath, QPolygonF, QAction, QKeySequence
from PySide6.QtWidgets import (QApplication, QGroupBox, QFormLayout, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QCheckBox,
    QPushButton, QColorDialog, QListWidget, QToolBar)
import design
from direction_input import DirectionSpinBox
from selection_edit import SelectionCanvas

GLOW = QColor(255, 230, 0, 150)
HIGHLIGHT = QColor('#ff1ea8')
NEW_ARROW = QColor('#ff6a00')
SAVED_ARROW = QColor('#7a3cff')
ARROW_FILLS = ('fill', 'both', 'satin_fill')
LINE_KINDS = ('run', 'double', 'triple', 'dash', 'applique', 'cross', 'star4', 'star6', 'star8', 'star12',
              'diamond', 'circle_pattern', 'chevron', 'flower_pattern')


class PartCanvas(SelectionCanvas):
    def __init__(self, editor):
        super().__init__(editor); self.arrow_start = None

    def mousePressEvent(self, event):
        e = self.editor
        if e.tool.currentIndex() == e.knife_mode and event.button() == Qt.MouseButton.LeftButton:
            p = self.mapToScene(event.position().toPoint()); e.knife_points = [(p.x(), p.y())]; e.refresh(); return
        if e.tool.currentIndex() == e.arrow_mode:
            p = self.mapToScene(event.position().toPoint())
            if event.button() == Qt.MouseButton.LeftButton:
                self.arrow_start = p; e.arrow_preview = (p, p); e.refresh(); return
            if event.button() == Qt.MouseButton.RightButton:
                e.remove_arrow_near(p); return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        e = self.editor
        if e.tool.currentIndex() == e.knife_mode and e.knife_points:
            p = self.mapToScene(event.position().toPoint()); last = e.knife_points[-1]
            if math.hypot(p.x() - last[0], p.y() - last[1]) * max(self.transform().m11(), .01) > 3:e.knife_points.append((p.x(), p.y())); e.refresh()
            return
        if self.arrow_start is not None:
            self.editor.arrow_preview = (self.arrow_start, self.mapToScene(event.position().toPoint())); self.editor.refresh(); return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        e = self.editor
        if e.tool.currentIndex() == e.knife_mode and e.knife_points:
            p = self.mapToScene(event.position().toPoint()); e.knife_points.append((p.x(), p.y()))
            points = e.knife_points; e.knife_points = []; e.knife_cut([(x / 10, y / 10) for x, y in points]); return
        if self.arrow_start is not None:
            a = self.arrow_start; b = self.mapToScene(event.position().toPoint())
            self.arrow_start = None; self.editor.arrow_preview = None; self.editor.add_arrow(a, b); return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        e = self.editor
        if e.tool.currentIndex() == e.knife_mode and event.key() == Qt.Key.Key_Escape:
            e.knife_points = []; e.tool.setCurrentIndex(0); return
        if e.tool.currentIndex() == e.arrow_mode:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):e.apply_arrows(); return
            if event.key() == Qt.Key.Key_Escape:e.cancel_arrows(); return
            if event.key() in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):e.pop_arrow(); return
        super().keyPressEvent(event)


class PartEditUI:
    # Opbouw -------------------------------------------------------------
    def build_part_edit(self):
        self.pending_arrows = []; self.arrow_preview = None; self.arrow_targets = set(); self._tool_before_arrows = 0
        self.arrow_mode = self.tool.count(); self.tool.addItem('Richtingspijlen zetten (Enter past toe)')
        self.knife_mode = self.tool.count(); self.tool.addItem('Mes: trek een lijn om een vlak te splitsen'); self.knife_points = []
        old = self.canvas; layout = old.parentWidget().layout()
        self.canvas = PartCanvas(self); layout.replaceWidget(old, self.canvas); old.hide(); old.deleteLater()
        self.canvas.setMinimumSize(220, 240)
        self.tool.currentIndexChanged.connect(self._arrow_tool_changed)

        box = QGroupBox('Geselecteerd onderdeel aanpassen'); lay = QVBoxLayout(box)
        self.part_info = QLabel('Klik op een deel van het borduursel of kies een onderdeel in de lijst.'); self.part_info.setWordWrap(True); lay.addWidget(self.part_info)
        f = QFormLayout(); lay.addLayout(f)
        self.part_color_button = QPushButton('Kleur wijzigen'); self.part_color_button.clicked.connect(self.change_part_color); f.addRow('Garenkleur', self.part_color_button)
        self.part_fill = QComboBox()
        for key, label in design.FILL_NAMES.items():self.part_fill.addItem(label, key)
        self.part_fill.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon); self.part_fill.setMinimumContentsLength(14)
        self.part_fill.activated.connect(self.change_part_fill); f.addRow('Steeksoort', self.part_fill)
        row = QHBoxLayout(); self.part_angle = DirectionSpinBox(); row.addWidget(self.part_angle, 1)
        self.part_angle.enterPressed.connect(self.change_part_angle)
        self.button(row, 'Toepassen', self.change_part_angle); f.addRow('Steekrichting', row)
        row = QHBoxLayout(); lay.addLayout(row)
        self.button(row, 'Richtingspijlen zetten', self.start_arrows); self.button(row, 'Pijlen wissen', self.clear_arrows)
        row = QHBoxLayout(); lay.addLayout(row)
        self.button(row, 'Gat maken', lambda: self.start_hole_mark('cut')); self.button(row, 'Gat sluiten', lambda: self.start_hole_mark('close'))
        self.button(lay, 'Alle gaten in dit onderdeel dichtmaken', self.close_all_holes)
        row = QHBoxLayout(); lay.addLayout(row)
        self.button(row, 'Groeperen', self.group_parts); self.button(row, 'Groep losmaken', self.ungroup_parts)
        self.button(lay, 'Mes: onderdeel in delen snijden', self.start_knife)
        self.button(lay, 'Lassen: aanrakende vlakken (zelfde kleur) samenvoegen', self.weld_parts)
        self.button(lay, 'Borduurvolgorde optimaliseren: gelijke kleuren samen, korte sprongen', self.optimise_order)
        self.part_live = QCheckBox('Steken direct opnieuw maken na een wijziging'); self.part_live.setChecked(True); lay.addWidget(self.part_live)
        dock_layout = self.parts_list.parentWidget().layout(); dock_layout.insertWidget(dock_layout.indexOf(self.parts_list) + 1, box)
        self.part_box = box

        self.thread_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.thread_list.itemClicked.connect(self.thread_row_clicked)
        self.thread_list.setToolTip('Klik op een garenkleur: de onderdelen in die kleur lichten op.')

        toolbar = next((t for t in self.findChildren(QToolBar) if t.objectName() == 'extra_toolbar'), None)
        if toolbar is not None:
            action = QAction('Richtingspijlen', self); action.triggered.connect(self.start_arrows); toolbar.addAction(action)
            action = QAction('Mes', self); action.setShortcut(QKeySequence('K')); action.triggered.connect(self.start_knife); toolbar.addAction(action)
            action = QAction('Groeperen', self); action.setShortcut(QKeySequence('Ctrl+G')); action.triggered.connect(self.group_parts); toolbar.addAction(action)
            action = QAction('Groep losmaken', self); action.setShortcut(QKeySequence('Ctrl+Shift+G')); action.triggered.connect(self.ungroup_parts); toolbar.addAction(action)
            action = QAction('Lassen', self); action.setShortcut(QKeySequence('Ctrl+L')); action.triggered.connect(self.weld_parts); toolbar.addAction(action)
            action = QAction('Volgorde optimaliseren', self); action.setShortcut(QKeySequence('Ctrl+Shift+O')); action.triggered.connect(self.optimise_order); toolbar.addAction(action)
        from action_icons import install_icons
        install_icons(self)

    # Aanklikken en oplichten ------------------------------------------
    def part_at(self, x, y, tolerance_mm=None):
        """Topmost part at scene point (0,1 mm units): first the stitch under the mouse, then the shape."""
        tolerance = tolerance_mm if tolerance_mm is not None else 8 / max(self.canvas.transform().m11(), .01) / 10
        owners = self.pattern.extras.get('owners', []) if self.pattern else []
        visible = {o['id'] for o in self.objects if o.get('visible', True)}
        if self.pattern and len(owners) == len(self.pattern.stitches) and self.show_sew.isChecked():
            best = None; last = None
            for (sx, sy, c), owner in zip(self.pattern.stitches, owners):
                cmd = c & emb.COMMAND_MASK
                if cmd == emb.STITCH and owner in visible:
                    d = math.hypot(sx - x, sy - y)
                    if last is not None:
                        # Distance to the stitch segment, not only to the needle point.
                        ax, ay = last; vx, vy = sx - ax, sy - ay; n = vx * vx + vy * vy
                        t = 0 if n == 0 else max(0, min(1, ((x - ax) * vx + (y - ay) * vy) / n))
                        d = math.hypot(ax + t * vx - x, ay + t * vy - y)
                    if best is None or d <= best[0]:best = (d, owner)
                if cmd in (emb.STITCH, emb.JUMP):last = (sx, sy)
            if best and best[0] <= tolerance * 10:
                return next((o for o in self.objects if o['id'] == best[1]), None)
        for obj in reversed(self.objects):
            if obj.get('visible', True) and design.point_inside(obj, x / 10, y / 10):return obj
        return None

    def select_region(self, rect, add=False):
        click = rect.width() < 5 and rect.height() < 5
        if click and self.objects and self.selection_mode.currentIndex() == 0:
            obj = self.part_at(rect.center().x(), rect.center().y())
            if obj is not None:return self.select_part(obj['id'], add)
        result = super().select_region(rect, add)
        if not click and self.selected_object_ids:
            expanded = set().union(*(self.group_members(i) for i in self.selected_object_ids))
            if expanded != self.selected_object_ids:self.selected_object_ids = expanded; self.refresh()
        return result

    def group_members(self, identity):
        obj = next((o for o in self.objects if o['id'] == identity), None)
        gid = obj.get('group_id') if obj else None
        return {o['id'] for o in self.objects if gid and o.get('group_id') == gid} or {identity}

    def select_part(self, identity, add=False, single=None):
        # Alt+klik kiest één onderdeel binnen een groep.
        if single is None:single = bool(QApplication.keyboardModifiers() & Qt.KeyboardModifier.AltModifier)
        members = {identity} if single else self.group_members(identity)
        if add:
            ids = self.chosen_ids()
            ids = ids - members if identity in ids else ids | members
        else:ids = set(members)
        self.selected_object_ids = set(ids); self.selected_object = identity if identity in ids else next(iter(ids), None)
        self.selected.clear(); self.edit_rect = None; self.active_node = None
        if self.parts_dock.isHidden():self.parts_dock.show(); self.parts_dock.raise_()
        self.sync_object_controls(); self.refresh()

    def stitch_blocks(self):
        """Per stitch: colour block number (= row in the garenkleuren list)."""
        block = 0; out = []
        for s in self.pattern.stitches:
            if (s[2] & emb.COMMAND_MASK) == emb.COLOR_CHANGE:block += 1
            out.append(block)
        return out

    def blocks_of(self, ids):
        owners = self.pattern.extras.get('owners', []) if self.pattern else []
        if not ids or len(owners) != len(self.pattern.stitches):return []
        blocks = self.stitch_blocks()
        return sorted({b for b, s, o in zip(blocks, self.pattern.stitches, owners) if o in ids and (s[2] & emb.COMMAND_MASK) == emb.STITCH})

    def owners_of_block(self, row):
        owners = self.pattern.extras.get('owners', []) if self.pattern else []
        if len(owners) != len(self.pattern.stitches):return []
        found = []
        for b, s, o in zip(self.stitch_blocks(), self.pattern.stitches, owners):
            if b == row and o and o not in found and (s[2] & emb.COMMAND_MASK) == emb.STITCH:found.append(o)
        return found

    def thread_row_clicked(self, item):
        if not self.pattern:return
        ids = self.owners_of_block(self.thread_list.row(item))
        if not ids:return
        known = [o['id'] for o in self.objects if o['id'] in ids]
        if not known:return
        self.selected_object_ids = set(known); self.selected_object = known[0]; self.selected.clear(); self.edit_rect = None
        if self.parts_dock.isHidden():self.parts_dock.show()
        self.sync_object_controls(); self.refresh()
        self._sync_thread_rows()

    def _sync_thread_rows(self):
        lw = self.thread_list
        if not self.pattern or lw.count() != len(self.pattern.threadlist):return
        ids = self.chosen_ids() if not self.playback else set()
        owners = self.pattern.extras.get('owners', [])
        names = {o['id']: o['name'] for o in self.objects}; parts = {}; blocks = set()
        if len(owners) == len(self.pattern.stitches):
            block = 0
            for s, owner in zip(self.pattern.stitches, owners):
                cmd = s[2] & emb.COMMAND_MASK
                if cmd == emb.COLOR_CHANGE:block += 1
                elif cmd == emb.STITCH and owner:
                    found = parts.setdefault(block, [])
                    if owner not in found:found.append(owner)
                    if owner in ids:blocks.add(block)
        lw.blockSignals(True)
        for i, t in enumerate(self.pattern.threadlist):
            text = f'{i+1}   #{t.get_red():02X}{t.get_green():02X}{t.get_blue():02X}'
            members = [names[o] for o in parts.get(i, []) if o in names]
            if members:text += '   ' + ', '.join(members[:3]) + (f' +{len(members) - 3}' if len(members) > 3 else '')
            elif t.description:text += '   ' + t.description
            item = lw.item(i); item.setText(('▶ ' if i in blocks else '') + text); item.setSelected(i in blocks)
        if blocks:
            lw.setCurrentRow(min(blocks), QItemSelectionModel.SelectionFlag.NoUpdate); lw.scrollToItem(lw.item(min(blocks)))
        lw.blockSignals(False)

    def draw_part_highlight(self):
        scene = self.canvas.scene(); ids = self.chosen_ids()
        if not ids or self.playback:return
        drew_stitches = False
        if self.pattern and self.show_sew.isChecked():
            owners = self.pattern.extras.get('owners', [])
            if len(owners) == len(self.pattern.stitches):
                path = QPainterPath(); last = None
                for (x, y, c), owner in zip(self.pattern.stitches, owners):
                    cmd = c & emb.COMMAND_MASK
                    if cmd == emb.STITCH and last is not None and owner in ids:path.moveTo(*last); path.lineTo(x, y)
                    if cmd in (emb.STITCH, emb.JUMP):last = (x, y)
                if not path.isEmpty():
                    glow = QPen(GLOW, 7); glow.setCosmetic(True); glow.setCapStyle(Qt.PenCapStyle.RoundCap); glow.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                    scene.addPath(path, glow).setZValue(4)
                    pen = QPen(HIGHLIGHT, 1.6); pen.setCosmetic(True); scene.addPath(path, pen).setZValue(4.5)
                    drew_stitches = True
        if drew_stitches:
            # The grey selection hatching hides the stitches; the glow replaces it.
            for item in scene.items():
                if item.data(0) == 'work_hatching':scene.removeItem(item)
        from studio2 import object_path
        pen = QPen(HIGHLIGHT, 2, Qt.PenStyle.DashLine); pen.setCosmetic(True)
        for obj in self.objects:
            if obj['id'] in ids and obj.get('visible', True):scene.addPath(object_path(obj), pen).setZValue(4.6)

    def _sync_part_box(self):
        if not hasattr(self, 'part_info'):return
        targets = self.part_targets()
        enabled = bool(targets)
        for w in (self.part_color_button, self.part_fill, self.part_angle):w.setEnabled(enabled)
        if not targets:
            self.part_info.setText('Klik op een deel van het borduursel of kies een onderdeel in de lijst. Ctrl+klik voegt onderdelen toe.')
            self.part_color_button.setStyleSheet(''); return
        obj = targets[0]
        count = 0
        owners = self.pattern.extras.get('owners', []) if self.pattern else []
        if owners and len(owners) == len(self.pattern.stitches):
            ids = {o['id'] for o in targets}
            count = sum(1 for s, o in zip(self.pattern.stitches, owners) if o in ids and (s[2] & emb.COMMAND_MASK) == emb.STITCH)
        guides = len(obj.get('direction_guides') or [])
        name = obj['name'] if len(targets) == 1 else f'{len(targets)} onderdelen ({obj["name"]} …)'
        text = f'<b>{name}</b><br>{design.FILL_NAMES.get(obj["fill"], obj["fill"])}'
        if obj['fill'] == 'column' and not guides:text += ' · richting volgt de lijn'
        elif guides > 1:text += f' · {guides} richtingspijlen'
        else:text += f' · richting {float(obj.get("angle", 0)):g}°'
        groups = {o.get('group_name') for o in targets if o.get('group_name')}
        if groups:text += ' · ' + ', '.join(sorted(groups))
        if obj.get('holes'):text += f' · {len(obj["holes"])} gat' + ('en' if len(obj['holes']) != 1 else '')
        if count:text += f' · {count:,} steken'.replace(',', '.')
        self.part_info.setText(text)
        self.part_color_button.setStyleSheet(f'background:{obj["color"]};color:' + ('white' if QColor(obj['color']).lightness() < 140 else 'black'))
        self.part_fill.blockSignals(True); self.part_fill.setCurrentIndex(max(0, self.part_fill.findData(obj['fill']))); self.part_fill.blockSignals(False)
        self.part_angle.blockSignals(True); self.part_angle.setValue(float(obj.get('angle', 0))); self.part_angle.blockSignals(False)

    # Direct aanpassen ---------------------------------------------------
    def part_targets(self):
        ids = self.chosen_ids() if hasattr(self, 'selected_object_ids') else set()
        return [o for o in self.objects if o['id'] in ids]

    def change_parts(self, update, message):
        if self.worker and self.worker.isRunning():return
        targets = self.part_targets()
        if not targets:return self.error('Klik eerst op een onderdeel in de tekening of kies het in de onderdelenkolom.')
        trial = [copy.deepcopy(o) for o in targets]
        try:
            for obj in trial:update(obj); design.validate_object(obj)
        except Exception as e:
            self._sync_part_box(); return self.error(e)
        self.checkpoint()
        for obj, new in zip(targets, trial):obj.clear(); obj.update(new)
        self.mark_objects_changed(); self.sync_object_controls(); self.refresh()
        self.regenerate_after_edit(message)

    def regenerate_after_edit(self, message):
        if self.part_live.isChecked() and self.objects:
            self.launch_objects(checkpoint=False, after=lambda: self.status.setText(message))
        else:self.status.setText(message + ' Maak opnieuw steken om het borduursel bij te werken.')

    def change_part_color(self):
        targets = self.part_targets()
        if not targets:return self.error('Klik eerst op een onderdeel in de tekening of kies het in de onderdelenkolom.')
        color = QColorDialog.getColor(QColor(targets[0]['color']), self, 'Nieuwe garenkleur voor dit onderdeel')
        if not color.isValid():return
        self.object_color = color.name()
        self.change_parts(lambda o: o.update(color=color.name()), f'Nieuwe kleur {color.name()} voor {len(targets)} onderdeel' + ('en.' if len(targets) != 1 else '.'))

    def change_part_fill(self, *args):
        key = self.part_fill.currentData()
        def update(obj):
            if not obj.get('closed', True) and key not in design.LINE_FILLS + ('satin', 'zigzag'):
                raise ValueError(f'{obj["name"]} is een open lijn: kies een stiklijn, zigzag of satijn.')
            obj['fill'] = key
            if key == 'satin':
                import pro_tools
                obj['satin'] = round(min(5., max(.5, pro_tools.shape_metrics(obj)[0] / 2 + .2)), 2)
            if key in ('cross', 'star4', 'star6', 'star8', 'star12', 'diamond', 'circle_pattern', 'chevron', 'flower_pattern') and float(obj.get('spacing', .45)) < 1:obj['spacing'] = 2.
            if key not in ('cross', 'star4', 'star6', 'star8', 'star12', 'diamond', 'circle_pattern', 'chevron', 'flower_pattern') and float(obj.get('spacing', .45)) > 1.5:obj['spacing'] = .45
            if key == 'applique':obj.setdefault('applique_tack', 'zigzag')
        self.change_parts(update, 'Steeksoort gewijzigd: ' + design.FILL_NAMES[key] + '.')

    def change_part_angle(self):
        self.part_angle.interpretText(); angle = self.part_angle.value()
        def update(obj):
            obj['angle'] = angle; obj['direction_guides'] = []
            if obj['fill'] == 'column':
                # One angle for the whole line-following satin.
                x0, y0, x1, y1 = design.object_bounds(obj); obj['direction_guides'] = [dict(x=(x0 + x1) / 2, y=(y0 + y1) / 2, angle=angle)]
        self.change_parts(update, f'Steekrichting {angle:g}° toegepast.')

    def close_all_holes(self):
        targets = self.part_targets()
        if not any(o.get('holes') for o in targets):return self.error('Dit onderdeel heeft geen gaten.')
        self.change_parts(lambda o: o.update(holes=[]), 'Gaten gesloten.')

    def after_object_edit(self, message):
        """Called by the Vlakken tab after a colour or settings change."""
        if hasattr(self, 'part_live'):self.regenerate_after_edit(message)

    def thread_color(self):
        i = self.thread_list.currentRow()
        if not self.pattern or i < 0 or i >= len(self.pattern.threadlist):return super().thread_color()
        ids = set(self.owners_of_block(i)); before = self.pattern.threadlist[i].color
        super().thread_color()
        t = self.pattern.threadlist[i]
        if t.color != before:
            color = f'#{t.get_red():02x}{t.get_green():02x}{t.get_blue():02x}'
            # The editable parts keep the new colour, so it survives new stitches.
            for obj in self.objects:
                if obj['id'] in ids:obj['color'] = color
            self.sync_object_controls(); self.refresh()

    # Groeperen ---------------------------------------------------------
    def group_parts(self):
        targets = self.part_targets()
        if len(targets) < 2:return self.error('Selecteer eerst twee of meer onderdelen: Ctrl+klik in de tekening of in de onderdelenkolom.')
        used = {o.get('group_name') for o in self.objects if o.get('group_name')}
        number = 1
        while f'Groep {number}' in used:number += 1
        self.checkpoint(); gid = uuid.uuid4().hex
        for obj in targets:obj['group_id'] = gid; obj['group_name'] = f'Groep {number}'
        self.status.setText(f'Groep {number}: {len(targets)} onderdelen. Klik op één ervan om de hele groep te kiezen; Alt+klik kiest één onderdeel.')
        self.sync_object_controls(); self.refresh()

    def ungroup_parts(self):
        targets = [o for o in self.part_targets() if o.get('group_id')]
        if not targets:return self.error('Het geselecteerde onderdeel zit niet in een groep.')
        self.checkpoint()
        for obj in targets:obj.pop('group_id', None); obj.pop('group_name', None)
        self.status.setText(f'Groep losgemaakt: {len(targets)} losse onderdelen.')
        self.sync_object_controls(); self.refresh()

    def _label_groups(self):
        names = {o['id']: o.get('group_name') for o in self.objects}
        for i in range(self.parts_list.count()):
            item = self.parts_list.item(i); group = names.get(item.data(Qt.ItemDataRole.UserRole))
            if group and not item.text().endswith(']'):item.setText(item.text() + f'   [{group}]')

    # Lassen ------------------------------------------------------------
    def weld_parts(self):
        if self.worker and self.worker.isRunning():return
        targets = [o for o in self.part_targets() if o.get('closed', True)]
        if len(targets) < 2:return self.error('Selecteer eerst twee of meer vlakken in dezelfde kleur (Ctrl+klik of sleep een rechthoek), dan Lassen.')
        try:pieces = design.weld_objects(targets)
        except ValueError as e:return self.error(e)
        self.checkpoint(); ids = {o['id'] for o in targets}; result = []; placed = False
        for obj in self.objects:
            if obj['id'] not in ids:result.append(obj)
            elif not placed:result.extend(pieces); placed = True
        self.objects = result; new_ids = {p['id'] for p in pieces}
        if self.generation_scope is not None:self.generation_scope = sorted((set(self.generation_scope) - ids) | new_ids)
        self.selected_object_ids = new_ids; self.selected_object = pieces[0]['id']; self.selected.clear()
        self.mark_objects_changed(); self.sync_object_controls(); self.refresh()
        apart = len(pieces) - 1
        message = (f'Gelast: {len(targets)} vlakken zijn nu {len(pieces)} onderdelen; {apart} deel/delen raakten de rest niet en bleven los.' if apart
                   else f'Gelast: {len(targets)} vlakken zijn nu één onderdeel en worden zonder sprong geborduurd.')
        self.regenerate_after_edit(message)

    # Borduurvolgorde -------------------------------------------------
    def optimise_order(self):
        """One button: tints that look the same become one thread colour,
        every colour is sewn in one go with short jumps, and the colours
        follow each other with a short jump too."""
        if self.worker and self.worker.isRunning():return
        if not self.objects:return self.error('Maak eerst bewerkbare vlakken (bijvoorbeeld met de toverstaf of Automatisch borduren).')
        before = len({o['color'] for o in self.objects})
        self.checkpoint(); changed = design.unify_colours(self.objects); after = len({o['color'] for o in self.objects})
        self.order_mode.blockSignals(True); self.order_mode.setCurrentIndex(0); self.order_mode.blockSignals(False)
        self.optimize.setChecked(True); self.generation_scope = None
        self.mark_objects_changed(); self.sync_object_controls(); self.refresh()
        message = (f'Volgorde geoptimaliseerd: {before} tinten zijn {after} garenkleuren; iedere kleur in één keer met korte sprongen.' if changed
                   else f'Volgorde geoptimaliseerd: {after} garenkleuren, iedere kleur in één keer met korte sprongen.')
        self.launch_objects(checkpoint=False, after=lambda: self.status.setText(message))

    # Mes ---------------------------------------------------------------
    def start_knife(self):
        if not self.objects:return self.error('Maak eerst bewerkbare vlakken (bijvoorbeeld met de toverstaf of Automatisch borduren).')
        self.knife_points = []; self.tool.setCurrentIndex(self.knife_mode); self.canvas.setFocus()
        self.status.setText('Mes: houd de linkermuisknop ingedrukt en trek een lijn helemaal over het vlak. Met een geselecteerd onderdeel wordt alleen dat gesneden. Esc stopt.')

    def knife_cut(self, line):
        if self.worker and self.worker.isRunning():return
        xs = [p[0] for p in line]; ys = [p[1] for p in line]
        if len(line) < 2 or math.hypot(xs[-1] - xs[0], ys[-1] - ys[0]) < .3:self.refresh(); return
        chosen = self.chosen_ids()
        candidates = [o for o in self.objects if o.get('visible', True) and o.get('closed', True) and (not chosen or o['id'] in chosen)]
        result = []; cut = []; message = None
        for obj in self.objects:
            if obj not in candidates:result.append(obj); continue
            x0, y0, x1, y1 = design.object_bounds(obj)
            if max(xs) < x0 or min(xs) > x1 or max(ys) < y0 or min(ys) > y1:result.append(obj); continue
            try:pieces = design.split_object(obj, line)
            except ValueError as e:message = str(e); result.append(obj); continue
            result.extend(pieces); cut.append(pieces)
        if not cut:
            self.refresh(); return self.error(message or 'De lijn loopt niet over een vlak. Trek de lijn helemaal over het vlak dat je wilt splitsen.')
        self.checkpoint(); self.objects = result
        new_ids = {p['id'] for pieces in cut for p in pieces}
        if self.generation_scope is not None:self.generation_scope = sorted(set(self.generation_scope) | new_ids)
        self.selected_object_ids = new_ids; self.selected_object = cut[0][-1]['id']; self.selected.clear()
        self.mark_objects_changed(); self.sync_object_controls(); self.refresh()
        count = sum(len(p) for p in cut)
        self.regenerate_after_edit(f'Gesneden: {len(cut)} vlak' + ('ken' if len(cut) != 1 else '') + f' → {count} losse onderdelen. Elk deel is nu zelfstandig aan te passen.')

    def draw_knife(self):
        if len(self.knife_points) < 2:return
        path = QPainterPath(); path.moveTo(*self.knife_points[0])
        for q in self.knife_points[1:]:path.lineTo(*q)
        pen = QPen(QColor('#d1001f'), 2, Qt.PenStyle.DashLine); pen.setCosmetic(True)
        self.canvas.scene().addPath(path, pen).setZValue(32)

    # Richtingspijlen ---------------------------------------------------
    def start_arrows(self):
        if not self.objects:return self.error('Maak eerst bewerkbare vlakken (bijvoorbeeld met de toverstaf of Automatisch borduren).')
        if self.tool.currentIndex() != self.arrow_mode:self._tool_before_arrows = self.tool.currentIndex()
        self.arrow_targets = self.chosen_ids()
        self.pending_arrows = [dict(g) for o in self.part_targets() for g in (o.get('direction_guides') or [])]
        self.tool.blockSignals(True); self.tool.setCurrentIndex(self.arrow_mode); self.tool.blockSignals(False)
        self.status.setText('Richtingspijlen: klik in een vlak en sleep in de steekrichting. Zet zoveel pijlen als je wilt, ook in andere vlakken. '
                            'Enter past alles toe · rechtsklik verwijdert een pijl · Backspace haalt de laatste weg · Esc annuleert.')
        self.status.setStyleSheet('color:#a64300;font-weight:600;')
        self.canvas.setFocus(); self.refresh()

    def _arrow_tool_changed(self, index):
        if index != self.arrow_mode and self.pending_arrows:self.pending_arrows = []; self.refresh()
        elif index == self.arrow_mode and not self.pending_arrows and not self.arrow_targets:
            self.arrow_targets = self.chosen_ids()
            self.pending_arrows = [dict(g) for o in self.part_targets() for g in (o.get('direction_guides') or [])]

    def add_arrow(self, a, b):
        zoom = max(self.canvas.transform().m11(), .01); dx, dy = b.x() - a.x(), b.y() - a.y()
        if math.hypot(dx, dy) * zoom < 12:angle = self.part_angle.value()  # click: use the angle in the box
        else:angle = math.degrees(math.atan2(dy, dx))
        self.pending_arrows.append(dict(x=a.x() / 10, y=a.y() / 10, angle=round(angle, 1)))
        self.status.setText(f'{len(self.pending_arrows)} richtingspijl' + ('en' if len(self.pending_arrows) != 1 else '') + ' gezet. Zet er meer of druk Enter om toe te passen.')
        self.refresh()

    def remove_arrow_near(self, p):
        if not self.pending_arrows:return
        zoom = max(self.canvas.transform().m11(), .01)
        d, i = min((math.hypot(a['x'] * 10 - p.x(), a['y'] * 10 - p.y()), i) for i, a in enumerate(self.pending_arrows))
        if d * zoom <= 40:self.pending_arrows.pop(i); self.refresh()

    def pop_arrow(self):
        if self.pending_arrows:self.pending_arrows.pop(); self.refresh()

    def cancel_arrows(self):
        self.pending_arrows = []; self.arrow_preview = None; self.arrow_targets = set()
        self.status.setStyleSheet(''); self.tool.setCurrentIndex(self._tool_before_arrows if self._tool_before_arrows != self.arrow_mode else 0); self.refresh()

    def _arrow_owner(self, arrow):
        x, y = arrow['x'], arrow['y']
        inside = [o for o in self.objects if o.get('visible', True) and o.get('closed', True) and design.point_inside(o, x, y)]
        preferred = [o for o in inside if o['id'] in self.arrow_targets]
        if preferred:return preferred[-1]
        if inside:return inside[-1]
        # Thin lines are hard to hit exactly: take the nearest part within 3 mm.
        best = None
        for obj in self.objects:
            if not obj.get('visible', True) or not obj.get('closed', True):continue
            for ring in [obj['nodes']] + obj.get('holes', []):
                pts = np.asarray(design.flattened(ring, True, .3))
                d = float(np.min(np.hypot(pts[:, 0] - x, pts[:, 1] - y)))
                bonus = -.5 if obj['id'] in self.arrow_targets else 0
                if best is None or d + bonus < best[0]:best = (d + bonus, obj)
        return best[1] if best and best[0] <= 3 else None

    def apply_arrows(self):
        if self.worker and self.worker.isRunning():return
        if not self.pending_arrows:
            # Enter without arrows: all arrows of the selected parts were removed.
            targets = [o for o in self.part_targets() if o.get('direction_guides')]
            if targets:return self.clear_arrows()
            return self.error('Zet eerst een of meer richtingspijlen: klik in een vlak en sleep in de gewenste steekrichting.')
        groups = {}; outside = 0
        for arrow in self.pending_arrows:
            obj = self._arrow_owner(arrow)
            if obj is None:outside += 1; continue
            groups.setdefault(obj['id'], []).append(arrow)
        if not groups:return self.error('Zet de pijlen binnen een vlak of op een lijn van het ontwerp.')
        skipped = [o['name'] for o in self.objects if o['id'] in groups and o['fill'] in LINE_KINDS]
        self.checkpoint(); changed = 0
        for obj in self.objects:
            if obj['id'] not in groups or obj['fill'] in LINE_KINDS:continue
            arrows = groups[obj['id']]
            guides = [dict(x=float(a['x']), y=float(a['y']), angle=float(a['angle'])) for a in arrows]
            obj['angle'] = guides[0]['angle']
            if obj['fill'] in ARROW_FILLS:
                # Tatami / satin fill: each area takes the direction of its nearest arrow.
                obj['direction_guides'] = guides if len(guides) > 1 else []
            else:
                # Lines: the satin keeps following the line; arrows tilt the stitches locally.
                if obj['fill'] in ('satin', 'zigzag'):obj['fill'] = 'column'
                obj['direction_guides'] = guides
            changed += 1
        for obj in self.objects:
            if obj['id'] in self.arrow_targets and obj['id'] not in groups and obj.get('direction_guides'):obj['direction_guides'] = []
        self.selected_object_ids = set(groups); self.selected_object = next(iter(groups))
        self.pending_arrows = []; self.arrow_preview = None; self.arrow_targets = set(); self.status.setStyleSheet('')
        self.tool.blockSignals(True); self.tool.setCurrentIndex(self._tool_before_arrows if self._tool_before_arrows != self.arrow_mode else 0); self.tool.blockSignals(False)
        self.mark_objects_changed(); self.sync_object_controls(); self.refresh()
        message = f'Steekrichting met pijlen toegepast op {changed} onderdeel' + ('en' if changed != 1 else '') + '.'
        if outside:message += f' {outside} pijl(en) buiten het ontwerp genegeerd.'
        if skipped:message += ' Stiklijnen en patronen hebben geen steekrichting: ' + ', '.join(skipped) + '.'
        if changed:self.launch_objects(checkpoint=False, after=lambda: self.status.setText(message))
        else:self.status.setText(message)

    def clear_arrows(self):
        targets = [o for o in self.part_targets() if o.get('direction_guides')]
        if not targets:
            if self.tool.currentIndex() == self.arrow_mode:self.pending_arrows = []; self.refresh(); return
            return self.error('Het geselecteerde onderdeel heeft geen richtingspijlen.')
        self.pending_arrows = []
        self.change_parts(lambda o: o.update(direction_guides=[]), 'Richtingspijlen gewist; het onderdeel gebruikt weer één steekrichting.')

    def _draw_arrow(self, scene, x, y, angle, color, length=None):
        zoom = max(self.canvas.transform().m11(), .01); length = length or 55 / zoom
        a = math.radians(angle); ux, uy = math.cos(a), math.sin(a)
        start = QPointF(x, y); end = QPointF(x + ux * length, y + uy * length)
        pen = QPen(color, 3); pen.setCosmetic(True); pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        halo = QPen(QColor(255, 255, 255, 220), 6); halo.setCosmetic(True); halo.setCapStyle(Qt.PenCapStyle.RoundCap)
        head = 12 / zoom
        tip = QPolygonF([end, QPointF(end.x() - ux * head - uy * head * .55, end.y() - uy * head + ux * head * .55),
                         QPointF(end.x() - ux * head + uy * head * .55, end.y() - uy * head - ux * head * .55)])
        scene.addLine(start.x(), start.y(), end.x(), end.y(), halo).setZValue(29)
        scene.addLine(start.x(), start.y(), end.x(), end.y(), pen).setZValue(30)
        scene.addPolygon(tip, pen, color).setZValue(30)
        r = 4 / zoom; scene.addEllipse(x - r, y - r, 2 * r, 2 * r, pen, QColor('white')).setZValue(31)

    def draw_arrows(self):
        scene = self.canvas.scene()
        if self.tool.currentIndex() == self.arrow_mode:
            for i, a in enumerate(self.pending_arrows):
                self._draw_arrow(scene, a['x'] * 10, a['y'] * 10, a['angle'], NEW_ARROW)
                label = scene.addText(str(i + 1)); label.setDefaultTextColor(NEW_ARROW); label.setFlag(label.GraphicsItemFlag.ItemIgnoresTransformations)
                label.setPos(a['x'] * 10, a['y'] * 10); label.setZValue(31)
            if self.arrow_preview:
                a, b = self.arrow_preview; length = math.hypot(b.x() - a.x(), b.y() - a.y())
                if length > 0:self._draw_arrow(scene, a.x(), a.y(), math.degrees(math.atan2(b.y() - a.y(), b.x() - a.x())), NEW_ARROW, length)
        elif not self.playback:
            for obj in self.part_targets():
                for g in obj.get('direction_guides') or []:
                    self._draw_arrow(scene, g['x'] * 10, g['y'] * 10, g['angle'], SAVED_ARROW)

    # Verversen ----------------------------------------------------------
    def draw_part_overlay(self):
        if not hasattr(self, 'part_info') or not hasattr(self, 'canvas'):return
        self.draw_part_highlight(); self.draw_arrows(); self.draw_knife(); self._label_groups(); self._sync_thread_rows()
        if not self.playback:self._sync_part_box()
