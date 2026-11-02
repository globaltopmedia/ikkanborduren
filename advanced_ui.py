"""Part columns, free selection, angle handles, geometric shapes and isolated digitising."""
import copy,math
from PySide6.QtCore import Qt,QPointF,QRectF
from PySide6.QtGui import QColor,QPen,QPainterPath,QPolygonF,QAction,QKeySequence
from PySide6.QtWidgets import QDockWidget,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QListWidget,QListWidgetItem,QComboBox,QCheckBox,QFormLayout,QLineEdit,QScrollArea
import design,part_geometry
from direction_input import DirectionSpinBox

class AdvancedUI:
    def build_advanced(self):
        self.tool.addItems(['Selectielijn','Vulrichting slepen','Klik onderdeel en borduur','Rechthoek tekenen','Ovaal tekenen','Cirkel tekenen'])
        self.lasso_points=[];self.selected_object_ids=set();self.generation_scope=None;self.shape_preview=None;self.global_fill_angle=45.
        self._direction_pending=False;self._direction_before_angle=45.
        view=self.menuBar().addMenu('Kolommen')
        self.parts_dock=QDockWidget('Borduuronderdelen',self);self.parts_dock.setMinimumWidth(245);self.parts_dock.setMaximumWidth(360);panel=QWidget();lay=QVBoxLayout(panel);scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(panel);self.parts_dock.setWidget(scroll)
        self.parts_list=QListWidget();self.parts_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection);lay.addWidget(self.parts_list);self.parts_list.itemSelectionChanged.connect(self.parts_selected)
        self.scope_label=QLabel();self.scope_label.setWordWrap(True);lay.addWidget(self.scope_label)
        self.button(lay,'Corrigeer geselecteerd onderdeel',lambda:self.tabs.setCurrentIndex(3))
        self.button(lay,'Borduur alleen geselecteerde onderdelen',self.generate_selection)
        self.button(lay,'Borduur alle onderdelen',self.generate_all)
        self.button(lay,'Klik op tekening om onderdeel te borduren',lambda:self.tool.setCurrentIndex(10))
        self.button(lay,'Start / eind omdraaien per vlak',self.reverse_part)
        self.show_endpoints=QCheckBox('Start + en einde △ tonen');self.show_endpoints.setChecked(True);self.show_endpoints.toggled.connect(self.refresh);lay.addWidget(self.show_endpoints)
        self.show_direction=QCheckBox('Lange richtingslijn met hoek tonen');self.show_direction.setChecked(True);self.show_direction.toggled.connect(self.refresh);lay.addWidget(self.show_direction)
        self.button(lay,'Vulrichting met eindpunt slepen',lambda:self.tool.setCurrentIndex(9))
        self.selection_kind=QComboBox();self.selection_kind.addItems(['Selectielijn: hele onderdelen','Selectielijn: losse steekpunten']);lay.addWidget(self.selection_kind)
        self.button(lay,'Selectielijn tekenen (Enter sluit)',lambda:self.tool.setCurrentIndex(8))
        self.button(lay,'Steekrichting wijzigen (Enter)',self.open_direction_page)
        self.button(lay,'Steekkolom openen',lambda:self.stitches_dock.show())
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,self.parts_dock);view.addAction(self.parts_dock.toggleViewAction())
        self.stitches_dock=QDockWidget('Steken en patronen',self);self.stitches_dock.setMinimumWidth(245);self.stitches_dock.setMaximumWidth(360);panel=QWidget();lay=QVBoxLayout(panel);scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(panel);self.stitches_dock.setWidget(scroll)
        self.stitch_palette=QListWidget()
        for key,label in design.FILL_NAMES.items():
            item=QListWidgetItem(label);item.setData(Qt.ItemDataRole.UserRole,key);self.stitch_palette.addItem(item)
        self.stitch_palette.setCurrentRow(0);lay.addWidget(self.stitch_palette);self.stitch_palette.itemClicked.connect(self.choose_stitch)
        info=QLabel('Kies een steek, selecteer een vlak of lijn en pas toe. Satijn op een open lijn vormt een band rond de lijn. Vullingen en kruispatronen gebruiken een gesloten vlak. Onderbroken lijnen laten bewust tussenruimtes open.');info.setWordWrap(True);lay.addWidget(info)
        self.button(lay,'Steek toepassen op geselecteerd onderdeel',self.apply_palette)
        self.button(lay,'Borduur alleen dit onderdeel',self.generate_selection)
        f=QFormLayout();lay.addLayout(f);self.shape_width=self.number(.5,300,30,' mm',1);self.shape_height=self.number(.5,300,20,' mm',1);f.addRow('Vormbreedte',self.shape_width);f.addRow('Vormhoogte',self.shape_height)
        self.button(lay,'Rechthoek met muis tekenen',lambda:self.tool.setCurrentIndex(11));self.button(lay,'Ovaal met muis tekenen',lambda:self.tool.setCurrentIndex(12));self.button(lay,'Cirkel met muis tekenen',lambda:self.tool.setCurrentIndex(13))
        self.button(lay,'Rechthoek met opgegeven maat maken',lambda:self.make_shape(11,QPointF(-self.shape_width.value()*5,-self.shape_height.value()*5),QPointF(self.shape_width.value()*5,self.shape_height.value()*5)))
        self.button(lay,'Ovaal met opgegeven maat maken',lambda:self.make_shape(12,QPointF(-self.shape_width.value()*5,-self.shape_height.value()*5),QPointF(self.shape_width.value()*5,self.shape_height.value()*5)))
        self.button(lay,'Cirkel met opgegeven diameter maken',lambda:self.make_shape(13,QPointF(-self.shape_width.value()*5,-self.shape_width.value()*5),QPointF(self.shape_width.value()*5,self.shape_width.value()*5)))
        self.auto_shape=QCheckBox('Nieuwe vormen direct in steken omzetten');self.auto_shape.setChecked(True);lay.addWidget(self.auto_shape)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,self.stitches_dock);self.splitDockWidget(self.parts_dock,self.stitches_dock,Qt.Orientation.Vertical);self.stitches_dock.hide();view.addAction(self.stitches_dock.toggleViewAction())
        self.parts_dock.visibilityChanged.connect(lambda *_:self.fit())
        self._parts_updating=False
        self.build_direction_controls()
        self.refresh_parts()
    def build_direction_controls(self):
        page=QWidget();lay=QVBoxLayout(page)
        note=QLabel('Kies één vlak, meerdere vlakken of alle vlakken. Stel de hoek in en druk Enter: de steken worden meteen opnieuw berekend en getoond. De standaard voor een nieuw ontwerp is 45°.');note.setWordWrap(True);lay.addWidget(note)
        f=QFormLayout();lay.addLayout(f)
        self.direction_scope=QComboBox();self.direction_scope.addItems(['Geselecteerde vlakken','Alle vlakken']);f.addRow('Toepassen op',self.direction_scope)
        self.global_angle=DirectionSpinBox();f.addRow('Steekrichting',self.global_angle)
        self.direction_scope.currentIndexChanged.connect(self.direction_scope_changed)
        self.global_angle.valueChanged.connect(self.set_global_direction)
        self.global_angle.enterPressed.connect(self.apply_direction)
        self.object_angle.valueChanged.connect(self.preview_object_direction)
        self.object_angle.enterPressed.connect(self.apply_object_direction)
        self.direction_info=QLabel();self.direction_info.setWordWrap(True);lay.addWidget(self.direction_info)
        self.direction_apply_button=self.button(lay,'Steekrichting toepassen — Enter',self.apply_direction)
        for angle,shortcut in [(45,None),(90,'Ctrl+9'),(180,'Ctrl+1')]:
            label=f'Steekrichting {angle}°'+(f' ({shortcut})' if shortcut else '')
            self.button(lay,label,lambda checked=False,a=angle:self.quick_direction(a))
            if shortcut:
                action=QAction(label,self);action.setShortcut(QKeySequence(shortcut));action.triggered.connect(lambda checked=False,a=angle:self.quick_direction(a));self.addAction(action)
        self.button(lay,'Alle vlakken selecteren (Ctrl+A)',self.select_all)
        self.button(lay,'Richtingslijn met de muis slepen',lambda:self.tool.setCurrentIndex(9))
        self.direction_result=QLabel();self.direction_result.setWordWrap(True);lay.addWidget(self.direction_result)
        lay.addStretch();self.add_page(page,'Steekrichting');self.direction_page=self.tabs.widget(self.tabs.count()-1)
    def open_direction_page(self):
        self.tabs.setCurrentWidget(self.direction_page)
    def refresh_direction_info(self):
        if not hasattr(self,'direction_info'):return
        targets=self.objects if self.direction_scope.currentIndex()==1 else [o for o in self.objects if o['id'] in self.chosen_ids()]
        self.direction_info.setText(f'{len(targets)} '+('vlakken in het hele ontwerp.' if self.direction_scope.currentIndex()==1 else 'geselecteerde vlakken. Selecteer met slepen, Ctrl+A of de onderdelenkolom.'))
    def direction_scope_changed(self,*args):
        if not self._direction_pending:
            obj=self.current_object();angle=obj.get('angle',0) if obj and self.direction_scope.currentIndex()==0 else self.global_fill_angle
            self.global_angle.blockSignals(True);self.global_angle.setValue(angle);self.global_angle.blockSignals(False)
        self.refresh()
    def reset_direction_preview(self):
        self._direction_pending=False;self._direction_before_angle=self.global_fill_angle;self.direction_result.clear()
    def sync_direction_selection(self):
        if not hasattr(self,'global_angle'):return
        if self._direction_pending:self.global_fill_angle=self._direction_before_angle
        self.reset_direction_preview();self.direction_scope_changed()
    def generation_objects(self):
        if self.generation_scope is None:return self.objects
        letters={o.get('letter_id') for o in self.objects if o['id'] in self.generation_scope and o.get('letter_id')}
        return [o for o in self.objects if o['id'] in self.generation_scope or o.get('letter_id') in letters]
    def refresh_parts(self):
        if not hasattr(self,'parts_list'):return
        self._parts_updating=True;self.parts_list.clear();known={o['id'] for o in self.objects};self.selected_object_ids&=known
        if self.selected_object:self.selected_object_ids.add(self.selected_object)
        for i,obj in enumerate(self.objects):
            enabled=self.generation_scope is None or obj['id'] in self.generation_scope
            item=QListWidgetItem(f'{i+1}. {obj["name"]}'+(' (buiten borduurselectie)' if not enabled else ''));item.setData(Qt.ItemDataRole.UserRole,obj['id']);item.setForeground(QColor(obj['color']));self.parts_list.addItem(item);item.setSelected(obj['id'] in self.selected_object_ids)
        self.scope_label.setText('Borduuruitvoer: alle onderdelen' if self.generation_scope is None else f'Borduuruitvoer: alleen {len(self.generation_scope)} geselecteerde onderdelen. Andere vlakken blijven bewerkbaar.')
        self._parts_updating=False
        self.refresh_direction_info()
    def parts_selected(self):
        if self._parts_updating:return
        self.selected_object_ids={i.data(Qt.ItemDataRole.UserRole) for i in self.parts_list.selectedItems()};item=self.parts_list.currentItem();self.selected_object=item.data(Qt.ItemDataRole.UserRole) if item and item.isSelected() else next(iter(self.selected_object_ids),None);self.selected.clear();self.sync_object_controls();self.refresh()
    def palette_key(self):return self.stitch_palette.currentItem().data(Qt.ItemDataRole.UserRole) if self.stitch_palette.currentItem() else 'fill'
    def choose_stitch(self,item):
        self.object_fill.setCurrentIndex(self.object_fill.findData(item.data(Qt.ItemDataRole.UserRole)))
    def apply_palette(self):
        obj=self.current_object()
        if not obj:return self.error('Selecteer eerst een vlak of lijn.')
        changed=copy.deepcopy(obj);changed.update(self.object_options());changed['fill']=self.palette_key()
        try:design.validate_object(changed)
        except Exception as e:return self.error(e)
        self.checkpoint();obj.update(changed);self.mark_objects_changed();self.sync_object_controls();self.refresh()
    def generate_selection(self):
        ids=set(self.selected_object_ids)
        if self.selected_object:ids.add(self.selected_object)
        if not ids:return self.error('Selecteer een onderdeel of meerdere onderdelen in de kolom.')
        self.generation_scope=sorted(ids);self.mark_objects_changed();self.refresh();self.launch_objects()
    def generate_all(self):
        if not self.objects:return self.error('Teken of trace eerst bewerkbare onderdelen.')
        self.generation_scope=None;self.mark_objects_changed();self.refresh();self.launch_objects()
    def click_and_sew(self,p):
        if self.worker and self.worker.isRunning():return
        key=self.palette_key();self.pick_object(p)
        if not self.current_object():
            if self.image is None:return self.error('Klik op een bewerkbaar vlak of open een afbeelding.')
            try:
                objects=part_geometry.clicked_region(self.image,self.width.value(),p.x()/10-self.image_offset[0],p.y()/10-self.image_offset[1],self.background.isChecked())
                self.checkpoint()
                for obj in objects:design.transform_object(obj,*self.image_offset);obj.update(self.object_options());obj['fill']=key;obj['name']=f'Aangeklikt vlak {len(self.objects)+1}';self.objects.append(obj)
                self.selected_object=objects[0]['id'];self.reference_only=True;self.reference_checkbox.setChecked(True)
            except Exception as e:return self.error(e)
        obj=self.current_object();candidate=obj|{'fill':key}
        try:design.validate_object(candidate)
        except Exception as e:return self.error(e)
        self.checkpoint();obj['fill']=key;self.selected_object_ids={obj['id']};self.sync_object_controls();self.generate_selection()
    def finish_lasso(self,add=False):
        ids,stitches=part_geometry.lasso_selection(self.objects,self.pattern,self.lasso_points,self.selection_kind.currentIndex()==0)
        if add:self.selected_object_ids|=ids;self.selected|=stitches
        else:self.selected_object_ids=ids;self.selected=stitches
        self.selected_object=next(iter(self.selected_object_ids),None);self.lasso_points=[];self.refresh();self.sync_object_controls()
    def direction_geometry(self):
        obj=self.current_object() if self.direction_scope.currentIndex()==0 else None
        if obj:
            x0,y0,x1,y1=design.object_bounds(obj);centre=QPointF((x0+x1)*5,(y0+y1)*5);length=max(300,min(1000,math.hypot(x1-x0,y1-y0)*8));angle=float(obj.get('angle',0))
        else:
            boxes=[design.object_bounds(o) for o in self.objects]
            centre=QPointF((min(b[0] for b in boxes)+max(b[2] for b in boxes))*5,(min(b[1] for b in boxes)+max(b[3] for b in boxes))*5) if boxes else QPointF(0,0)
            length=700;angle=self.global_angle.value()
        if self._direction_pending:angle=self.global_angle.value()
        radians=math.radians(angle);delta=QPointF(math.cos(radians)*length/2,math.sin(radians)*length/2)
        return centre-delta,centre+delta,centre,angle
    def drag_direction(self,p):
        _,_,centre,_=self.direction_geometry();angle=math.degrees(math.atan2(p.y()-centre.y(),p.x()-centre.x()))
        self.global_angle.setValue(angle)
        self.object_angle.blockSignals(True);self.object_angle.setValue(self.global_angle.value());self.object_angle.blockSignals(False)
    def set_global_direction(self,value):
        if not self._direction_pending:self._direction_before_angle=self.global_fill_angle
        self._direction_pending=True;self.global_fill_angle=float(value);self.direction_result.clear();self.refresh()
    def preview_object_direction(self,value):
        self.direction_scope.blockSignals(True);self.direction_scope.setCurrentIndex(0);self.direction_scope.blockSignals(False)
        self.global_angle.blockSignals(True);self.global_angle.setValue(value);self.global_angle.blockSignals(False)
        self.set_global_direction(value)
    def quick_direction(self,angle):
        if self.worker and self.worker.isRunning():return
        self.global_angle.setValue(angle);self.apply_direction()
    def apply_object_direction(self):
        self.preview_object_direction(self.object_angle.value());self.apply_direction()
    def apply_selected_angle(self):
        self.direction_scope.setCurrentIndex(0);self.apply_direction()
    def apply_all_angle(self):
        self.direction_scope.setCurrentIndex(1);self.apply_direction()
    def apply_direction(self):
        if self.worker and self.worker.isRunning():return
        if self.draft or self.lasso_points:return self.error('Sluit of annuleer eerst de contour of selectielijn.')
        self.global_angle.interpretText();angle=self.global_angle.value();whole=self.direction_scope.currentIndex()==1
        objects=self.objects;prepared=None
        if not objects:
            if self.image is None:return self.error('Open een tekening of een BST-project met bewerkbare vlakken om de steekrichting te veranderen.')
            if not whole:return self.error('Kies Alle vlakken om de tekening eerst naar bewerkbare vlakken om te zetten.')
            try:
                import core
                image,palette=core.prepare_image(self.image,self.colors.value(),self.background.isChecked())
                image,palette=design.clean_art(image,self.detail_min.value(),self.width.value(),self.smooth.value(),self.color_tolerance.value())
                objects=design.objects_from_art(image,self.width.value(),self.detail_min.value())
                for obj in objects:
                    design.transform_object(obj,*self.image_offset)
                    obj.update(fill=['fill','satin','both'][self.stitch_mode.currentIndex()],spacing=self.spacing.value(),length=self.length.value(),satin=self.satin_width.value(),underlay=self.underlay.isChecked())
                prepared=image,palette
            except Exception as e:return self.error(e)
        ids={o['id'] for o in objects} if whole else self.chosen_ids()&{o['id'] for o in objects}
        if not ids:return self.error('Selecteer één of meer vlakken, of kies Alle vlakken.')
        if self._direction_pending:self.global_fill_angle=self._direction_before_angle
        self.checkpoint()
        self.global_fill_angle=angle;self.objects=objects
        for obj in objects:
            if obj['id'] in ids:obj['angle']=angle
        if prepared:
            self.image,self.palette=prepared;self.reference_only=True
            self.reference_checkbox.blockSignals(True);self.reference_checkbox.setChecked(True);self.reference_checkbox.blockSignals(False)
        if whole:self.generation_scope=None
        elif self.generation_scope is not None:self.generation_scope=sorted(set(self.generation_scope)|ids)
        self.reset_direction_preview();self.selected.clear();self.mark_objects_changed()
        self.show_sew.blockSignals(True);self.show_sew.setChecked(True);self.show_sew.blockSignals(False)
        self.sim_toggle.blockSignals(True);self.sim_toggle.setChecked(False);self.sim_toggle.blockSignals(False);self.playback=False
        self.sync_object_controls();self.refresh()
        self.launch_objects(checkpoint=False,after=lambda:self.direction_result.setText(f'Steekrichting {angle:g}° toegepast op {len(ids)} vlak'+('ken.' if len(ids)!=1 else '.')))
    def reverse_part(self):
        obj=self.current_object()
        if not obj:return self.error('Selecteer eerst een borduurvlak.')
        ends=part_geometry.endpoints(self.pattern).get(obj['id']);self.checkpoint();obj['route_reversed']=not obj.get('route_reversed',False)
        if ends:obj['entry_hint']=[v/10 for v in ends['end']];obj['exit_hint']=[v/10 for v in ends['start']]
        self.mark_objects_changed();self.refresh()
        if self.pattern:self.launch_objects()
    def make_shape(self,mode,a,b):
        x0,x1=sorted((a.x()/10,b.x()/10));y0,y1=sorted((a.y()/10,b.y()/10))
        if mode==13:
            size=max(x1-x0,y1-y0);x1=x0+size;y1=y0+size
        if min(x1-x0,y1-y0)<.5:return self.error('Maak de vorm minimaal 0,5 mm groot.')
        if mode==11:nodes=[dict(x=x0,y=y0,kind='corner'),dict(x=x1,y=y0,kind='corner'),dict(x=x1,y=y1,kind='corner'),dict(x=x0,y=y1,kind='corner')];name='Rechthoek'
        else:
            nodes=[dict(x=(x0+x1)/2+(x1-x0)/2*math.cos(i*math.pi/8),y=(y0+y1)/2+(y1-y0)/2*math.sin(i*math.pi/8),kind='smooth') for i in range(16)];name='Cirkel' if mode==13 else 'Ovaal'
        options=self.object_options();options['fill']=self.palette_key();obj=design.new_object(nodes,self.object_color,name,**options)
        try:design.validate_object(obj)
        except Exception as e:return self.error(e)
        self.checkpoint();self.objects.append(obj);self.selected_object=obj['id'];self.selected_object_ids={obj['id']};self.generation_scope=None;self.mark_objects_changed();self.refresh();self.sync_object_controls()
        if self.auto_shape.isChecked():self.launch_objects()
    def draw_advanced(self):
        if not hasattr(self,'parts_list'):return
        self.refresh_parts();scene=self.canvas.scene()
        if self.lasso_points:
            p=QPainterPath();p.moveTo(*self.lasso_points[0])
            for point in self.lasso_points[1:]:p.lineTo(*point)
            pen=QPen(QColor('#ce31ac'),2,Qt.PenStyle.DashLine);pen.setCosmetic(True);scene.addPath(p,pen).setZValue(20)
        if self.shape_preview:
            mode,a,b=self.shape_preview;rect=QRectF(a,b).normalized()
            if mode==13:rect.setWidth(max(rect.width(),rect.height()));rect.setHeight(rect.width())
            pen=QPen(QColor('#ce31ac'),2,Qt.PenStyle.DashLine);pen.setCosmetic(True)
            item=scene.addRect(rect,pen) if mode==11 else scene.addEllipse(rect,pen);item.setZValue(20)
        if self.show_direction.isChecked() and not self.playback and (self.current_object() or self.tool.currentIndex()==9 or (self.direction_scope.currentIndex()==1 and self.objects)):
            a,b,centre,angle=self.direction_geometry();pen=QPen(QColor('#bb187c'),2);pen.setCosmetic(True);scene.addLine(a.x(),a.y(),b.x(),b.y(),pen).setZValue(20);r=6/max(.1,self.canvas.transform().m11());dot=scene.addEllipse(-r,-r,2*r,2*r,pen,QColor('white'));dot.setPos(b);dot.setZValue(21);label=scene.addText(f'{angle:.1f}°');label.setDefaultTextColor(QColor('#bb187c'));label.setFlag(label.GraphicsItemFlag.ItemIgnoresTransformations);label.setPos(centre);label.setZValue(21)
        if self.show_endpoints.isChecked() and self.pattern:
            ends=part_geometry.endpoints(self.pattern);size=7/max(.1,self.canvas.transform().m11())
            for identity,record in ends.items():
                pen=QPen(QColor('#009660'),2);pen.setCosmetic(True);x,y=record['start'];scene.addLine(x-size,y,x+size,y,pen).setZValue(22);scene.addLine(x,y-size,x,y+size,pen).setZValue(22)
                x,y=record['end'];pen=QPen(QColor('#e57613'),2);pen.setCosmetic(True);triangle=QPolygonF([QPointF(x,y-size),QPointF(x-size,y+size),QPointF(x+size,y+size)]);scene.addPolygon(triangle,pen,QColor('#fff3df')).setZValue(22)
        scene.setSceneRect(scene.itemsBoundingRect().adjusted(-50,-50,50,50))
