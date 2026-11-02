from save_names import choose_save_file
"""BorduurStudio 2: object digitising, contour nodes and playback."""
import copy, math, os, uuid, subprocess
from pathlib import Path
import numpy as np
from PIL import Image
import pyembroidery as emb
from PySide6.QtCore import Qt,QPointF,QRectF,QTimer,QThread,Signal
from PySide6.QtGui import QColor,QPen,QPainterPath,QAction,QKeySequence,QBrush,QTransform
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QPushButton,
    QComboBox,QCheckBox,QListWidget,QListWidgetItem,QLineEdit,QSlider,QScrollArea,QTabWidget,
    QFileDialog,QMessageBox,QColorDialog,QGroupBox)
from main import Studio,Canvas,ROOT
import core,design
from extra_ui import ExtraUI
from fabric_ui import FabricUI
from advanced_ui import AdvancedUI
from direction_input import DirectionSpinBox

class ObjectWorker(QThread):
    progress=Signal(int,str);done=Signal(object);failed=Signal(str)
    def __init__(self,objects,optimize,manual_order=False,fabric_key=None,min_stitch=0):super().__init__();self.objects=copy.deepcopy(objects);self.optimize=optimize;self.manual_order=manual_order;self.fabric_key=fabric_key;self.min_stitch=min_stitch
    def run(self):
        try:self.done.emit(design.digitize_objects(self.objects,self.progress.emit,self.optimize,manual_order=self.manual_order,fabric_key=self.fabric_key,min_stitch=self.min_stitch))
        except Exception as e:self.failed.emit(str(e))

def contour_path(nodes,closed=True):
    path=QPainterPath()
    if not nodes:return path
    path.moveTo(nodes[0]['x']*10,nodes[0]['y']*10)
    for p,a,b,q,curved in design.segments(nodes,closed):
        if curved:path.cubicTo(a[0]*10,a[1]*10,b[0]*10,b[1]*10,q[0]*10,q[1]*10)
        else:path.lineTo(q[0]*10,q[1]*10)
    if closed:path.closeSubpath()
    return path

def object_path(obj):
    p=contour_path(obj['nodes'],obj.get('closed',True));p.setFillRule(Qt.FillRule.OddEvenFill)
    for hole in obj.get('holes',[]):p.addPath(contour_path(hole))
    return p

class VectorCanvas(Canvas):
    def __init__(self,editor):super().__init__(editor);self.node_drag=None;self.pan_start=None;self.moving_object=False
    def contextMenuEvent(self,event):event.accept()
    def mousePressEvent(self,event):
        e=self.editor;mode=e.tool.currentIndex();p=self.mapToScene(event.position().toPoint())
        if event.button()==Qt.MouseButton.MiddleButton:
            self.pan_start=event.position();return
        if mode==4 and event.button() in (Qt.MouseButton.LeftButton,Qt.MouseButton.RightButton):
            if event.modifiers()&Qt.KeyboardModifier.ControlModifier and e.draft:
                origin=QPointF(e.draft[-1]['x']*10,e.draft[-1]['y']*10);d=p-origin;r=math.hypot(d.x(),d.y());a=round(math.atan2(d.y(),d.x())/math.pi*12)*math.pi/12;p=origin+QPointF(r*math.cos(a),r*math.sin(a))
            e.add_node(p,event.button()==Qt.MouseButton.RightButton);return
        if mode==5:
            if event.button()==Qt.MouseButton.LeftButton:e.pick_object(p)
            elif event.button()==Qt.MouseButton.RightButton:e.pick_object(p);e.choose_object_color()
            return
        if mode==7:
            if event.button() in (Qt.MouseButton.LeftButton,Qt.MouseButton.RightButton):e.insert_contour_node(p,event.button()==Qt.MouseButton.RightButton)
            return
        if mode==6:
            found=e.nearest_node(p)
            if found:
                obj,ring,i=found;e.selected_object=obj['id'];e.active_node=(obj['id'],([obj['nodes']]+obj.get('holes',[])).index(ring),i);e.checkpoint()
                if event.button()==Qt.MouseButton.RightButton:
                    ring[i]['kind']='corner' if ring[i].get('kind')=='smooth' else 'smooth';e.mark_objects_changed();e.refresh()
                else:self.node_drag=(ring,i)
            return
        if mode==1 and e.selected_object:
            e.checkpoint();self.start=p;self.moving_object=True;return
        super().mousePressEvent(event)
    def mouseMoveEvent(self,event):
        if self.pan_start is not None:
            delta=event.position()-self.pan_start;self.pan_start=event.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value()-round(delta.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value()-round(delta.y()));return
        if self.node_drag:
            p=self.mapToScene(event.position().toPoint());ring,i=self.node_drag;ring[i]['x']=p.x()/10;ring[i]['y']=p.y()/10
            self.editor.mark_objects_changed();self.editor.refresh();return
        if self.moving_object:return
        super().mouseMoveEvent(event)
    def mouseReleaseEvent(self,event):
        if self.pan_start is not None:self.pan_start=None;return
        if self.node_drag:self.node_drag=None;self.editor.refresh();return
        if self.moving_object:
            p=self.mapToScene(event.position().toPoint());delta=p-self.start
            self.editor.move_selected(delta.x()/10,delta.y()/10,checkpoint=False);self.start=None;self.moving_object=False;return
        super().mouseReleaseEvent(event)
    def keyPressEvent(self,event):
        if self.editor.tool.currentIndex()==4:
            if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter):self.editor.finish_shape();return
            if event.key()==Qt.Key.Key_Escape:self.editor.cancel_shape();return
            if event.key() in (Qt.Key.Key_Backspace,Qt.Key.Key_Delete):self.editor.pop_node();return
        if event.key()==Qt.Key.Key_Delete and self.editor.tool.currentIndex()==6 and self.editor.active_node:self.editor.delete_contour_node();return
        if event.key()==Qt.Key.Key_Delete and self.editor.selected_object:self.editor.delete_object();return
        super().keyPressEvent(event)

    def mouseDoubleClickEvent(self,event):
        if self.editor.tool.currentIndex()==5:
            self.editor.pick_object(self.mapToScene(event.position().toPoint()));self.editor.tabs.setCurrentIndex(3);return
        super().mouseDoubleClickEvent(event)

from selection_edit import SelectionEdit
from contour_ui import ContourUI
from holes_ui import HolesUI
from overlap_ui import OverlapUI
from pro_ui import ProUI
from part_edit_ui import PartEditUI

class Studio2(PartEditUI,ProUI,OverlapUI,HolesUI,ContourUI,SelectionEdit,AdvancedUI,FabricUI,ExtraUI,Studio):
    def __init__(self):
        self.image_offset=[0.,0.];self.edit_rect=None;self._size_updating=False
        self.fabric_key='standard';self._preserving_for_save=False;self.objects=[];self.selected_object=None;self.draft=[];self.draft_hole=False;self.draft_open=False;self.active_node=None;self.reference_only=False
        self.playback=False;self.play_index=0;self._updating=False;self._simulation_busy=False
        super().__init__();self.setWindowTitle('Ikkanborduren — ontwerpstudio voor Bernina 540');self.resize(1120,780)
        library_menu=self.menuBar().addMenu('Bibliotheek')
        library_action=library_menu.addAction('Mijn borduurbibliotheek…')
        library_action.triggered.connect(self.open_library)
        self.timer=QTimer(self);self.timer.setInterval(80);self.timer.timeout.connect(self.tick)
        self.refresh();self.fit()
    def open_library(self):
        from library_manager import LibraryDialog
        LibraryDialog(self).exec()

    def build(self):
        super().build();self.tabs=self.findChild(QTabWidget);self.tabs.setMaximumWidth(445);self.tabs.setMinimumWidth(430)
        old=self.canvas;layout=old.parentWidget().layout();self.canvas=VectorCanvas(self);layout.replaceWidget(old,self.canvas);old.hide();old.deleteLater()
        self.tool.addItems(['Vlak tekenen','Vlak selecteren','Contourpunten aanpassen','Contourpunt toevoegen'])
        self.tool.currentIndexChanged.connect(self.tool_changed)
        self.presets.blockSignals(True);self.presets.clear();self.presets.addItems([h[0] for h in design.HOOPS]);self.presets.setCurrentIndex(2);self.presets.blockSignals(False)
        # Drawing page
        page=QWidget();lay=QVBoxLayout(page)
        text=QLabel('Volg een buitenlijn met punten. Links = hoek/rechte lijn; rechts = soepel curvepunt. Enter sluit het vlak. Backspace verwijdert het laatste punt. Esc annuleert. Sleep punten met Contourpunten aanpassen; rechts wisselt hoek/curve.');text.setWordWrap(True);lay.addWidget(text)
        self.button(lay,'Nieuw leeg ontwerp',self.new_design)
        self.button(lay,'Begin nieuw vlak',self.start_shape)
        self.button(lay,'Begin open stiklijn',lambda:self.start_shape(line=True))
        self.button(lay,'Uitsparing in geselecteerd vlak tekenen',lambda:self.start_shape(True))
        row=QHBoxLayout();lay.addLayout(row);self.button(row,'Vlak sluiten',self.finish_shape);self.button(row,'Annuleren',self.cancel_shape)
        self.draft_label=QLabel('Geen contour in bewerking');lay.addWidget(self.draft_label)
        self.object_list=QListWidget();self.object_list.setMinimumHeight(105);lay.addWidget(self.object_list);self.object_list.currentRowChanged.connect(self.object_selected)
        f=QFormLayout();lay.addLayout(f);self.object_name=QLineEdit('Nieuw vlak');f.addRow('Naam',self.object_name)
        self.object_color='#159552';self.color_button=QPushButton('Vlak- / garenkleur kiezen');self.color_button.clicked.connect(self.choose_object_color);lay.addWidget(self.color_button)
        self.object_fill=QComboBox()
        for key,label in design.FILL_NAMES.items():self.object_fill.addItem(label,key)
        f.addRow('Steekvulling',self.object_fill)
        self.object_phase=QComboBox();self.object_phase.addItems(['Punt / accent eerst','Normale laagvolgorde','Rechte satijnlijn als laatste']);self.object_phase.setCurrentIndex(1);f.addRow('Borduurfase',self.object_phase)
        self.object_fill.currentIndexChanged.connect(self.fill_choice_changed)
        self.object_spacing=self.number(.3,5,.45,' mm',2);f.addRow('Rijafstand / patroonmaat',self.object_spacing)
        self.object_length=self.number(.5,5,2.5,' mm',2);f.addRow('Max. steeklengte',self.object_length)
        self.object_satin=self.number(.5,5,2,' mm',2);f.addRow('Satijnbreedte',self.object_satin)
        self.object_angle=DirectionSpinBox();f.addRow('Vulrichting (Enter: selectie)',self.object_angle)
        self.object_compensation=self.number(0,1,0,' mm',2);f.addRow('Trekcompensatie',self.object_compensation)
        self.object_underlay=QCheckBox('Onderlaag vóór de vulling');self.object_underlay.setChecked(True);f.addRow(self.object_underlay)
        self.button(lay,'Instellingen toepassen op geselecteerd vlak',self.apply_object)
        self.button(lay,'Contourpunt toevoegen (klik op de lijn)',lambda:self.tool.setCurrentIndex(7))
        self.button(lay,'Geselecteerd contourpunt verwijderen',self.delete_contour_node)
        self.button(lay,'Maak steken uit alle vlakken',self.generate_objects)
        self.optimize=QCheckBox('Dezelfde kleur en kortste beschikbare sprong');self.optimize.setChecked(True);lay.addWidget(self.optimize)
        info=QLabel('Overlappende vlakken blijven van onder naar boven. Satijnsteek volgt de vorm van een lijn; Satijnvulling gaat van rand tot rand in de steekrichting; Satijnrand is een band langs de contour. Dunne lijnen in tatami krijgen vanzelf satijn. Bij tatami maximaal 1,50 mm rijafstand; kruisvak gebruikt de opgegeven maat.');info.setWordWrap(True);lay.addWidget(info)
        lay.addStretch();self.add_page(page,'Vlakken')
        # Additional object editing controls on editing page
        ep=self.tabs.widget(2).widget();el=ep.layout()
        box=QGroupBox('Hele vlakken bewerken');f=QFormLayout(box);el.insertWidget(1,box)
        self.object_scale=self.number(5,1000,100,' %');f.addRow('Vlak vergroten/verkleinen',self.object_scale)
        self.object_rotation=self.number(-180,180,0,'°');f.addRow('Vlak draaien',self.object_rotation)
        self.button(f,'Schaal en draai geselecteerd vlak',self.scale_rotate_object)
        self.button(f,'Geselecteerd vlak dupliceren',self.duplicate_object)
        self.button(f,'Geselecteerd vlak verwijderen',self.delete_object)
        row=QHBoxLayout();f.addRow(row);self.button(row,'Laag omhoog',lambda:self.layer(1));self.button(row,'Laag omlaag',lambda:self.layer(-1))
        self.button(f,'Steken van geselecteerd vlak selecteren',self.select_object_stitches)
        self.button(f,'Alle vlakken op Ontwerpbreedte zetten',self.resize_objects)
        self.button(f,'Alle vlakken centreren in het raam',self.center_objects)
        # Image conversion/cleanup controls
        ap=self.tabs.widget(0).widget();al=ap.layout();box=QGroupBox('Contouren en details');f=QFormLayout(box);al.insertWidget(1,box)
        self.detail_min=self.number(0,5,.12,' mm²',2);f.addRow('Kleine details weglaten',self.detail_min)
        self.smooth=self.number(0,.5,.1,' mm',2);f.addRow('Contour gladmaken',self.smooth)
        self.color_tolerance=self.number(0,50,12,'',0);f.addRow('Vergelijkbare kleuren samen',self.color_tolerance)
        self.button(f,'Afbeelding opschonen',self.cleanup_image)
        self.button(f,'Afbeelding naar bewerkbare vlakken',self.trace_image)
        self.reference_checkbox=QCheckBox('Afbeelding alleen als overtrekvoorbeeld');self.reference_checkbox.setChecked(False);self.reference_checkbox.toggled.connect(self.reference_toggled);f.addRow(self.reference_checkbox)
        # Simulator lives underneath canvas, always reachable.
        panel=QWidget();v=QVBoxLayout(panel);row=QHBoxLayout();v.addLayout(row)
        self.sim_toggle=QCheckBox('Simulatie');self.sim_toggle.toggled.connect(self.simulation_changed);row.addWidget(self.sim_toggle)
        self.play_button=QPushButton('Afspelen');self.play_button.clicked.connect(self.play_pause);row.addWidget(self.play_button)
        self.button(row,'Eén stap',self.step);self.button(row,'Begin',self.rewind)
        self.speed=QComboBox();self.speed.addItems(['Langzaam — 20 punten/s','Normaal — 200 punten/s','Snel — 2000 punten/s']);self.speed.setCurrentIndex(1);details=QHBoxLayout();v.addLayout(details);details.addWidget(self.speed)
        self.sim_label=QLabel('Nog geen steken');details.addWidget(self.sim_label,1)
        self.slider=QSlider(Qt.Orientation.Horizontal);self.slider.valueChanged.connect(self.seek);v.addWidget(self.slider)
        self.canvas.parentWidget().layout().addWidget(panel)
        self.show_objects=QCheckBox('Vlakken');self.show_objects.setChecked(True);self.show_objects.toggled.connect(self.refresh)
        self.canvas.parentWidget().layout().itemAt(1).layout().insertWidget(1,self.show_objects)
        self.hoop_notice=QLabel();self.hoop_notice.setWordWrap(True);self.hoop_notice.setStyleSheet('color:#945400;');self.tabs.widget(1).widget().layout().insertWidget(1,self.hoop_notice)
        a=QAction('Nieuw ontwerp',self);a.setShortcut(QKeySequence('Ctrl+N'));a.triggered.connect(self.new_design);self.menuBar().actions()[0].menu().insertAction(self.menuBar().actions()[0].menu().actions()[0],a)
        a=QAction('Bureaubladsnelkoppeling maken',self);a.triggered.connect(self.make_shortcut);self.menuBar().actions()[-1].menu().addAction(a)
        a=QAction('Vlakken als SVG bewaren',self);a.triggered.connect(self.export_objects_svg);self.menuBar().actions()[0].menu().addAction(a)
        self.build_extras()
        self.build_fabric()
        self.build_advanced()
        from advanced_canvas import AdvancedCanvas
        old=self.canvas;layout=old.parentWidget().layout();self.canvas=AdvancedCanvas(self);layout.replaceWidget(old,self.canvas);old.hide();old.deleteLater()
        self.start_full_button=QPushButton('Start borduren — tekening naar EXP / PES')
        self.start_full_button.setToolTip('Alle vlakken: stofinstellingen, onderlaag, bovenlaag, ringcontrole en borduurbestand maken.')
        self.start_full_button.clicked.connect(self.start_full_embroidery)
        self.tabs.widget(1).widget().layout().insertWidget(0,self.start_full_button)
        self.build_contour()
        self.build_holes()
        self.build_overlap()
        self.build_selection_edit()
        self.build_pro()
        self.build_part_edit()
        self.direction.hide()
        for label in self.direction.parentWidget().findChildren(QLabel):
            if label.text()=='Vulrichting':label.setText('Hoek → onderdelenkolom')
    def add_page(self,page,title):
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(page);self.tabs.addTab(scroll,title)
    def tool_changed(self,index):
        if index==4:self.tabs.setCurrentIndex(3)
        if index==0:self.selected_object=None
        self.refresh()
    def current_object(self):return next((o for o in self.objects if o['id']==self.selected_object),None)
    def fill_choice_changed(self,index):
        if self.object_fill.currentData() in ('cross','star4','star6','star8','star12','diamond','circle_pattern','chevron','flower_pattern') and hasattr(self,'object_spacing') and self.object_spacing.value()<1:self.object_spacing.setValue(2)
    def object_options(self):
        return dict(fill=self.object_fill.currentData(),spacing=self.object_spacing.value(),length=self.object_length.value(),
            satin=self.object_satin.value(),angle=self.object_angle.value(),compensation=self.object_compensation.value(),underlay=self.object_underlay.isChecked(),stitch_phase=self.object_phase.currentIndex())
    def mark_objects_changed(self):
        if self.pattern:self.art_changed=True
        self.stop_playback()
    def settings(self):
        return super().settings()|dict(objects=copy.deepcopy(self.objects),reference_only=self.reference_only,hoop_index=self.presets.currentIndex(),optimize=self.optimize.isChecked(),manual_order=self.order_mode.currentIndex()==1,fabric_key=self.fabric_key,generation_scope=self.generation_scope,global_fill_angle=self.global_fill_angle,image_offset=self.image_offset)|self.pro_settings()
    def checkpoint(self):
        # Base class calls this before its widgets are built only on explicit edits.
        self.history.append((self.image.copy() if self.image else None,copy.deepcopy(self.palette),core.clone_pattern(self.pattern),self.art_changed,copy.deepcopy(self.objects),self.reference_only,self.width.value(),self.order_mode.currentIndex(),copy.deepcopy(self.generation_scope),self.global_fill_angle,copy.deepcopy(self.image_offset)))
        self.history=self.history[-16:];self.future.clear()
    def restore(self,back,forward):
        if not back:return
        forward.append((self.image.copy() if self.image else None,copy.deepcopy(self.palette),core.clone_pattern(self.pattern),self.art_changed,copy.deepcopy(self.objects),self.reference_only,self.width.value(),self.order_mode.currentIndex(),copy.deepcopy(self.generation_scope),self.global_fill_angle,copy.deepcopy(self.image_offset)))
        image,palette,pattern,changed,objects,reference,width,order_mode,scope,angle,image_offset=back.pop();self.image_offset=image_offset;self.edit_rect=None;self.generation_scope=scope;self.global_fill_angle=angle;self.image=image;self.palette=palette;self.pattern=pattern;self.objects=objects;self.art_changed=changed;self.reference_only=reference
        self.width.blockSignals(True);self.width.setValue(width);self.width.blockSignals(False)
        self.order_mode.blockSignals(True);self.order_mode.setCurrentIndex(order_mode);self.order_mode.blockSignals(False)
        self.global_angle.blockSignals(True);self.global_angle.setValue(angle);self.global_angle.blockSignals(False)
        self.reset_direction_preview()
        self.selected.clear();self.selected_object=None;self.active_node=None;self.draft=[];self.hole_operation=None;self.hole_target_ids=set();self.selected_object_ids.clear();self.stop_playback();self.reference_checkbox.blockSignals(True);self.reference_checkbox.setChecked(reference);self.reference_checkbox.blockSignals(False);self.refresh()
    def load_path(self,path):
        # Let base load pixels/stitches and retain old v1 compatibility.
        self.selected_object_ids.clear();before=self.objects;super().load_path(path)
        if Path(path).suffix.lower()=='.bst':
            try:
                _,_,_,settings=core.load_project(path);self.objects=copy.deepcopy(settings.get('objects',[]));self.reference_only=settings.get('reference_only',False)
                self.order_mode.blockSignals(True);self.order_mode.setCurrentIndex(1 if settings.get('manual_order',False) else 0);self.order_mode.blockSignals(False)
                self.optimize.setChecked(True)
                self.fabric_key=settings.get('fabric_key','standard')
                if self.fabric_key not in __import__('fabric').PROFILES:self.fabric_key='standard'
                self.fabric_combo.blockSignals(True);self.fabric_combo.setCurrentIndex(self.fabric_combo.findData(self.fabric_key));self.fabric_combo.blockSignals(False);self.update_fabric_notice()
                self.image_offset=list(settings.get('image_offset',[0.,0.]));self.generation_scope=settings.get('generation_scope');self.global_fill_angle=float(settings.get('global_fill_angle',0));self.global_angle.blockSignals(True);self.global_angle.setValue(self.global_fill_angle);self.global_angle.blockSignals(False)
                index=settings.get('hoop_index')
                if index is not None:
                    self.presets.blockSignals(True);self.presets.setCurrentIndex(index);self.presets.blockSignals(False)
                self.load_pro_settings(settings)
                if not settings.get('art_changed',False):self.art_changed=False
            except Exception:return
        else:self.objects=[];self.reference_only=False;self.generation_scope=None;self.image_offset=[0.,0.]
        self.reset_direction_preview();self.object_angle.blockSignals(True);self.object_angle.setValue(self.global_fill_angle);self.object_angle.blockSignals(False)
        self.edit_rect=None;self.draft=[];self.hole_operation=None;self.hole_target_ids=set();self.selected_object=None;self.active_node=None;self.reference_checkbox.blockSignals(True);self.reference_checkbox.setChecked(self.reference_only);self.reference_checkbox.blockSignals(False);self.stop_playback();self.refresh();self.fit()
    def new_design(self):
        if self.image or self.objects or self.pattern:
            if QMessageBox.question(self,'Nieuw ontwerp','Een leeg ontwerp openen? Sla je huidige project eerst op als je het wilt bewaren.')!=QMessageBox.StandardButton.Yes:return
        self.checkpoint();self.image_offset=[0.,0.];self.edit_rect=None;self.image=None;self.palette=[];self.pattern=None;self.source=None;self.objects=[];self.selected.clear();self.selected_object=None;self.draft=[];self.path=None;self.art_changed=False;self.generation_scope=None;self.selected_object_ids.clear();self.reference_only=False
        self.global_fill_angle=45.;self.reset_direction_preview()
        for widget in (self.global_angle,self.object_angle):widget.blockSignals(True);widget.setValue(45);widget.blockSignals(False)
        self.stop_playback();self.refresh();self.fit()
    def start_shape(self,hole=False,line=False):
        if not self.draft:self.hole_operation=None;self.hole_target_ids=set()
        if hole and not self.current_object():return self.error('Selecteer eerst het vlak waarin je een uitsparing wilt maken.')
        if hole and not self.current_object().get('closed',True):return self.error('Een uitsparing kan alleen in een gesloten vlak.')
        if self.draft:return self.error('Sluit of annuleer eerst de contour die je tekent.')
        self.draft_hole=bool(hole);self.draft_open=bool(line)
        if line:self.object_fill.setCurrentIndex(self.object_fill.findData('run'))
        if not hole:self.selected_object=None;self.selected_object_ids.clear();self.selected.clear();self.active_node=None
        self.tool.setCurrentIndex(4);self.tabs.setCurrentIndex(3);self.canvas.setFocus();self.refresh()
    def add_node(self,p,smooth=False):
        if self.draft and math.hypot(p.x()/10-self.draft[-1]['x'],p.y()/10-self.draft[-1]['y'])<.05:return
        self.draft.append(dict(x=p.x()/10,y=p.y()/10,kind='smooth' if smooth else 'corner'));self.refresh()
    def pop_node(self):
        if self.draft:self.draft.pop();self.refresh()
    def cancel_shape(self):
        if getattr(self,'hole_operation',None):return self.cancel_hole_mark()
        self.draft=[];self.draft_hole=False;self.tool.setCurrentIndex(5);self.refresh()
    def finish_shape(self):
        if getattr(self,'hole_operation',None):return self.finish_hole_mark()
        if len(self.draft)<(2 if self.draft_open else 3):return self.error('Zet minstens drie punten voor een vlak, of twee voor een open stiklijn.')
        obj=self.current_object() if self.draft_hole else design.new_object(self.draft,self.object_color,self.object_name.text().strip() or f'Vlak {len(self.objects)+1}',closed=not self.draft_open,**self.object_options())
        try:
            if not self.draft_hole:design.validate_object(obj)
            elif not all(design.point_inside(obj,n['x'],n['y']) for n in self.draft):raise ValueError('De uitsparing moet volledig binnen het geselecteerde vlak liggen.')
            self.checkpoint()
            if self.draft_hole:obj['holes'].append(copy.deepcopy(self.draft))
            else:self.objects.append(obj);self.selected_object=obj['id'];self.selected_object_ids={obj['id']};self.selected.clear();self.active_node=None
            self.draft=[];self.draft_hole=False;self.tool.setCurrentIndex(5);self.mark_objects_changed();self.refresh()
        except Exception as e:self.error(e)
    def pick_object(self,p):
        self.selected_object=next((o['id'] for o in reversed(self.objects) if design.point_inside(o,p.x()/10,p.y()/10)),None)
        self.selected_object_ids={self.selected_object} if self.selected_object else set();self.selected.clear();self.refresh();self.sync_object_controls()
    def nearest_node(self,p):
        objects=[self.current_object()] if self.current_object() else self.objects
        choices=[]
        for obj in objects:
            for ring in [obj['nodes']]+obj.get('holes',[]):
                for i,n in enumerate(ring):choices.append((math.hypot(n['x']*10-p.x(),n['y']*10-p.y()),obj,ring,i))
        if not choices:return None
        best=min(choices,key=lambda c:c[0])
        return best[1:] if best[0]<12/max(self.canvas.transform().m11(),.001) else None
    def insert_contour_node(self,p,smooth=False):
        obj=self.current_object()
        if not obj:return self.error('Selecteer eerst een vlak of lijn.')
        choices=[]
        for ri,ring in enumerate([obj['nodes']]+obj.get('holes',[])):
            for i,segment in enumerate(design.segments(ring,obj.get('closed',True))):
                a,b,c,d,curved=segment
                for t in np.linspace(0,1,35):
                    q=(1-t)**3*a+3*(1-t)**2*t*b+3*(1-t)*t*t*c+t**3*d if curved else a+(d-a)*t
                    choices.append((math.dist(q,(p.x()/10,p.y()/10)),ri,i,q))
        if not choices:return
        distance,ri,i,q=min(choices,key=lambda x:x[0])
        if distance*10>15/max(self.canvas.transform().m11(),.01):return self.error('Klik dichter bij de geselecteerde contour.')
        ring=([obj['nodes']]+obj.get('holes',[]))[ri]
        if any(math.dist(q,(n['x'],n['y']))<.05 for n in ring):return
        self.checkpoint();ring.insert(i+1,dict(x=float(q[0]),y=float(q[1]),kind='smooth' if smooth else 'corner'));self.active_node=(obj['id'],ri,i+1);self.mark_objects_changed();self.tool.setCurrentIndex(6);self.refresh()
    def delete_contour_node(self):
        obj=self.current_object()
        if not obj or not self.active_node or self.active_node[0]!=obj['id']:return self.error('Klik eerst een contourpunt met Contourpunten aanpassen.')
        _,ri,i=self.active_node;rings=[obj['nodes']]+obj.get('holes',[])
        if ri>=len(rings) or i>=len(rings[ri]):self.active_node=None;return
        ring=rings[ri];minimum=3 if obj.get('closed',True) or ri else 2
        if len(ring)<=minimum:return self.error('Te weinig punten over. Verwijder het hele vlak of de hele lijn.')
        self.checkpoint();ring.pop(i);self.active_node=None;self.mark_objects_changed();self.refresh()
    def object_selected(self,row):
        if self._updating:return
        self.selected_object=self.objects[row]['id'] if 0<=row<len(self.objects) else None;self.selected_object_ids={self.selected_object} if self.selected_object else set();self.active_node=None;self.selected.clear();self.sync_object_controls();self.refresh()
    def sync_object_controls(self):
        if hasattr(self,'part_info'):self._sync_part_box()
        obj=self.current_object()
        if not obj:self.sync_direction_selection();return
        self.sync_lettering(obj)
        self.object_phase.setCurrentIndex(int(obj.get('stitch_phase',1)))
        self.object_name.setText(obj['name']);self.object_color=obj['color'];self.object_fill.setCurrentIndex(self.object_fill.findData(obj['fill']))
        for key,widget in [('spacing',self.object_spacing),('length',self.object_length),('satin',self.object_satin),('angle',self.object_angle),('compensation',self.object_compensation)]:
            blocked=widget.blockSignals(True);widget.setValue(obj.get(key,0));widget.blockSignals(blocked)
        self.sync_direction_selection()
        self.object_underlay.setChecked(obj.get('underlay',True));self.color_button.setStyleSheet(f'background:{self.object_color};color:'+('white' if QColor(self.object_color).lightness()<140 else 'black'))
    def choose_object_color(self):
        color=QColorDialog.getColor(QColor(self.object_color),self,'Kleur van vlak en garen')
        if not color.isValid():return
        self.object_color=color.name();obj=self.current_object()
        if obj:self.checkpoint();obj['color']=self.object_color;self.mark_objects_changed()
        self.color_button.setStyleSheet(f'background:{self.object_color};');self.refresh()
        if obj:self.after_object_edit('Kleur gewijzigd.')
    def apply_object(self):
        obj=self.current_object()
        if not obj:return self.error('Selecteer eerst een vlak in de lijst of op de tekening.')
        updated=copy.deepcopy(obj);updated.update(self.object_options());updated['name']=self.object_name.text().strip() or obj['name'];updated['color']=self.object_color
        try:design.validate_object(updated)
        except Exception as e:return self.error(e)
        changed=updated!=obj
        self.checkpoint();obj.update(updated);self.mark_objects_changed();self.refresh()
        if changed:self.after_object_edit('Instellingen toegepast.')
    def move_object(self,dx,dy,checkpoint=True):
        obj=self.current_object()
        if not obj:return
        if checkpoint:self.checkpoint()
        design.transform_object(obj,dx,dy);self.mark_objects_changed();self.refresh()
    def legacy_move_selected(self,dx,dy,checkpoint=True):
        if len(self.selected_object_ids)>1 and not self.selected:
            if checkpoint:self.checkpoint()
            for obj in self.objects:
                if obj['id'] in self.selected_object_ids:design.transform_object(obj,dx,dy)
            self.mark_objects_changed();self.refresh();return
        if self.current_object() and not self.selected:return self.move_object(dx,dy,checkpoint)
        super().move_selected(dx,dy,checkpoint)
    def legacy_scale_rotate_object(self):
        obj=self.current_object()
        if not obj:return self.error('Selecteer een vlak.')
        x0,y0,x1,y1=design.object_bounds(obj);self.checkpoint();design.transform_object(obj,scale=self.object_scale.value()/100,angle=self.object_rotation.value(),center=((x0+x1)/2,(y0+y1)/2));self.mark_objects_changed();self.refresh()
    def duplicate_object(self):
        obj=self.current_object()
        if not obj:return
        self.checkpoint();obj=copy.deepcopy(obj);obj['id']=uuid.uuid4().hex;obj['name']+=' kopie';design.transform_object(obj,dx=5,dy=5);self.objects.append(obj);self.selected_object=obj['id'];self.mark_objects_changed();self.refresh()
    def delete_object(self):
        if not self.current_object():return
        self.checkpoint();self.objects=[o for o in self.objects if o['id']!=self.selected_object];self.selected_object=None;self.mark_objects_changed();self.refresh()
    def layer(self,delta):
        obj=self.current_object()
        if not obj:return
        i=self.objects.index(obj);j=i+delta
        if not 0<=j<len(self.objects):return
        self.checkpoint();self.objects[i],self.objects[j]=self.objects[j],self.objects[i];self.mark_objects_changed();self.refresh()
    def resize_objects(self):
        if not self.objects:return self.error('Er zijn geen vlakken.')
        boxes=[design.object_bounds(o) for o in self.objects];x0=min(b[0] for b in boxes);x1=max(b[2] for b in boxes);y0=min(b[1] for b in boxes);y1=max(b[3] for b in boxes)
        self.checkpoint();scale=self.width.value()/max(.1,x1-x0)
        for obj in self.objects:design.transform_object(obj,scale=scale,center=((x0+x1)/2,(y0+y1)/2))
        self.mark_objects_changed();self.refresh();self.fit()
    def center_objects(self):
        if not self.objects:return
        boxes=[design.object_bounds(o) for o in self.objects];cx=(min(b[0] for b in boxes)+max(b[2] for b in boxes))/2;cy=(min(b[1] for b in boxes)+max(b[3] for b in boxes))/2
        self.checkpoint()
        for obj in self.objects:design.transform_object(obj,dx=-cx,dy=-cy)
        self.mark_objects_changed();self.refresh();self.fit()
    def select_object_stitches(self):
        if not self.pattern or not self.selected_object:return
        owners=self.pattern.extras.get('owners',[])
        if len(owners)!=len(self.pattern.stitches):return self.error('Maak opnieuw steken uit de vlakken om de steekselectie te koppelen.')
        self.selected={i for i,o in enumerate(owners) if o==self.selected_object and (self.pattern.stitches[i][2]&emb.COMMAND_MASK) in (emb.STITCH,emb.JUMP)}
        self.selected_object_ids.clear();self.selected_object=None;self.edit_rect=None;self.tool.setCurrentIndex(0);self.refresh()
    def delete_selected(self):
        if self.selected_object and not self.selected:return self.delete_object()
        super().delete_selected()
        if self.pattern:self.pattern.extras.pop('owners',None)
    def reference_toggled(self,value):self.reference_only=value;self.refresh()
    def cleanup_image(self):
        if self.image is None:return self.error('Open eerst een afbeelding.')
        try:
            image,palette=design.clean_art(self.image,self.detail_min.value(),self.width.value(),self.smooth.value(),self.color_tolerance.value());self.checkpoint();self.image=image;self.palette=palette;self.art_changed=self.pattern is not None;self.refresh()
        except Exception as e:self.error(e)
    def trace_image(self):
        if self.image is None:return self.error('Open en vereenvoudig eerst een afbeelding.')
        if self.objects and QMessageBox.question(self,'Vlakken vervangen','Bestaande vlakken vervangen door contouren uit de afbeelding?')!=QMessageBox.StandardButton.Yes:return
        try:
            cleaned,palette=design.clean_art(self.image,self.detail_min.value(),self.width.value(),self.smooth.value(),self.color_tolerance.value())
            objects=design.objects_from_art(cleaned,self.width.value(),self.detail_min.value())
            for obj in objects:
                obj['angle']=self.global_fill_angle;design.transform_object(obj,*self.image_offset)
            if not objects:raise ValueError('Geen voldoende grote kleurvlakken gevonden.')
            self.checkpoint();self.image=cleaned;self.palette=palette;self.objects=objects;self.selected_object=objects[0]['id'];self.reference_only=True;self.reference_checkbox.setChecked(True);self.mark_objects_changed();self.refresh();self.sync_object_controls();self.tabs.setCurrentIndex(3)
        except Exception as e:self.error(e)
    def start_full_embroidery(self):
        if self.worker and self.worker.isRunning():return
        if self.draft:return self.error('Sluit of annuleer eerst de contour.')
        if not self.objects and self.image is None:return self.error('Open of plak eerst een tekening, of teken vlakken.')
        path,filter_=choose_save_file(self,'Borduren starten — bestand bewaren','Mijn_borduurpatroon.exp','Bernina EXP (*.exp);;Brother / PES (*.pes)')
        if not path:return
        choice=self.fabric_dialog()
        if choice is None:return
        key,_=choice
        try:
            self.checkpoint()
            if not self.objects:
                cleaned,palette=core.prepare_image(self.image,self.colors.value(),self.background.isChecked())
                cleaned,palette=design.clean_art(cleaned,self.detail_min.value(),self.width.value(),self.smooth.value(),self.color_tolerance.value())
                objects=design.objects_from_art(cleaned,self.width.value(),self.detail_min.value())
                for obj in objects:
                    design.transform_object(obj,*self.image_offset)
                    obj.update(fill=['fill','satin','both'][self.stitch_mode.currentIndex()],spacing=self.spacing.value(),length=self.length.value(),satin=self.satin_width.value(),angle=self.global_fill_angle)
                if not objects:raise ValueError('Geen bruikbare vlakken gevonden.')
                self.objects=objects;self.image=cleaned;self.palette=palette
                self.reference_only=True;self.reference_checkbox.setChecked(True)
            self.generation_scope=None;self.fabric_key=key
            self.fabric_combo.blockSignals(True);self.fabric_combo.setCurrentIndex(self.fabric_combo.findData(key));self.fabric_combo.blockSignals(False)
            self.update_fabric_notice();self.mark_objects_changed();self.refresh()
            fmt='pes' if 'PES' in filter_ else 'exp'
            self.launch_objects(after=lambda:self.finish_full_embroidery(path,fmt))
        except Exception as e:self.error(e)
    def finish_full_embroidery(self,path,fmt):
        try:
            if self.presets.currentIndex()==3 and core.pattern_stats(self.pattern)['height']>251:
                raise ValueError('Dit ontwerp vereist meerdere Mega-raamposities. Verdeel het eerst in aparte projecten.')
            out=core.export_bundle(self.pattern,path,self.hoop_w.value(),self.hoop_h.value(),self.oval.isChecked(),self.margin.value(),fmt)
            metrics=design.route_metrics(self.pattern)
            self.status.setText(f'Borduurbestand klaar: {out.name} — {metrics["jumps"]} sprongen')
            QMessageBox.information(self,'Borduurbestand klaar',f'Opgeslagen: {out}\nAlle vlakken zijn verwerkt: eerst onderlaag, daarna bovenlaag.\n'+('Zet EXP, INF en BMP met dezelfde naam samen op de USB-stick.' if fmt=='exp' else 'Het PES-bestand is klaar.'))
        except Exception as e:self.error(e)
    def generate_objects(self):
        if self.worker and self.worker.isRunning():return
        if not self.objects:return self.error('Teken eerst een vlak of zet een afbeelding om naar vlakken.')
        if self.pattern and QMessageBox.question(self,'Nieuwe steken','Nieuwe steken vervangen de bestaande steekbewerkingen. Doorgaan?')!=QMessageBox.StandardButton.Yes:return
        self.launch_objects()
    def generate(self):
        if self.objects:return self.generate_objects()
        if self.image is not None:
            self.trace_image()
            if self.objects:return self.generate_objects()
            return
        self.stop_playback();super().generate()
    def generated(self,p):
        self._generation_ok=True;self.stop_playback();self.play_index=len(p.stitches);super().generated(p)
    def set_preset(self,index):
        if index>=len(design.HOOPS):return
        _,w,h,oval=design.HOOPS[index]
        if w:self.hoop_w.setValue(w);self.hoop_h.setValue(h);self.oval.setChecked(oval)
        self.refresh()
        if hasattr(self,'canvas'):self.fit()
    def stop_playback(self):
        if hasattr(self,'timer'):self.timer.stop()
        if hasattr(self,'play_button'):self.play_button.setText('Afspelen')
    def simulation_changed(self,value):
        self.stop_playback();self.playback=value
        if value and self.pattern:self.play_index=0
        self.refresh()
    def play_pause(self):
        if not self.pattern:return self.error('Maak eerst borduursteken.')
        if self.timer.isActive():self.stop_playback();return
        if not self.sim_toggle.isChecked():self.sim_toggle.setChecked(True)
        if self.play_index>=len(self.pattern.stitches):self.play_index=0
        self.timer.start();self.play_button.setText('Pauze')
    def tick(self):
        if not self.pattern:self.stop_playback();return
        self.play_index=min(len(self.pattern.stitches),self.play_index+[2,16,160][self.speed.currentIndex()])
        if self.play_index>=len(self.pattern.stitches):self.stop_playback()
        self.refresh()
    def step(self):
        if not self.pattern:return
        self.stop_playback()
        if not self.sim_toggle.isChecked():self.sim_toggle.setChecked(True)
        self.play_index=min(len(self.pattern.stitches),self.play_index+1);self.refresh()
    def rewind(self):self.stop_playback();self.play_index=0;self.refresh()
    def seek(self,value):
        if self._simulation_busy:return
        self.stop_playback();self.play_index=value;self.refresh()
    def refresh(self,*args):
        if not hasattr(self,'canvas'):return
        full=self.pattern
        # Base renderer draws only the already sewn prefix during playback.
        if self.playback and full:
            self.play_index=min(self.play_index,len(full.stitches));partial=core.clone_pattern(full);partial.stitches=full.stitches[:self.play_index];self.pattern=partial
            original_selected=self.selected;self.selected={i for i in self.selected if i<self.play_index}
        try:super().refresh()
        finally:
            self.pattern=full
            if self.playback and full:self.selected=original_selected
        if not hasattr(self,'object_list'):return
        scene=self.canvas.scene()
        if self.reference_only and self.show_art.isChecked():
            # Reference remains visible underneath traced vector objects.
            for item in scene.items():
                if hasattr(item,'pixmap'):item.setOpacity(.22)
        if self.show_objects.isChecked() and not self.playback:
            for obj in self.objects:
                if not obj.get('visible',True):continue
                pen=QPen(QColor('#167ed0' if obj['id']==self.selected_object else obj['color']),2 if obj['id']==self.selected_object else 1);pen.setCosmetic(True)
                item=scene.addPath(object_path(obj),pen,QColor(obj['color']) if obj.get('closed',True) else Qt.BrushStyle.NoBrush);item.setZValue(1);item.setOpacity(.22 if full and self.show_sew.isChecked() else .78)
                working_ids=getattr(self,'selected_object_ids',set())|({self.selected_object} if self.selected_object else set())
                if obj['id'] in working_ids and obj.get('closed',True):
                    # Display-only overlay: the odd-even object path keeps holes
                    # clear. Keep the hatch spacing legible at the current zoom.
                    brush=QBrush(QColor('#c4c4c4'),Qt.BrushStyle.BDiagPattern)
                    inverse,ok=self.canvas.transform().inverted()
                    if ok:brush.setTransform(QTransform(inverse.m11(),inverse.m12(),inverse.m21(),inverse.m22(),0,0))
                    hatch=scene.addPath(object_path(obj),QPen(Qt.PenStyle.NoPen),brush)
                    hatch.setZValue(3);hatch.setData(0,'work_hatching');hatch.setData(1,obj['id'])
                if obj['id']==self.selected_object and self.tool.currentIndex()==6:
                    for ring in [obj['nodes']]+obj.get('holes',[]):
                        for n in ring:
                            r=4/max(self.canvas.transform().m11(),.1);dot=scene.addEllipse(-r,-r,r*2,r*2,QPen(QColor('#0068ee')),QColor('white' if n.get('kind')=='corner' else '#ffb342'));dot.setPos(n['x']*10,n['y']*10);dot.setZValue(5)
        if self.draft:
            pen=QPen(QColor('#ff7b12'),2);pen.setCosmetic(True);item=scene.addPath(contour_path(self.draft,False),pen);item.setZValue(8)
            for n in self.draft:
                dot=scene.addEllipse(-3,-3,6,6,QPen(QColor('#ff7b12')),QColor('#ffb342'));dot.setPos(n['x']*10,n['y']*10);dot.setZValue(8)
        self.draft_label.setText(f'{len(self.draft)} punten — '+('uitsparing' if self.draft_hole else 'nieuw vlak') if self.draft else 'Geen contour in bewerking')
        self._updating=True;self.object_list.clear();selected_row=-1
        for i,obj in enumerate(self.objects):
            item=QListWidgetItem(f'{i+1}. {obj["name"]} — {design.FILL_NAMES[obj["fill"]]}');item.setForeground(QColor(obj['color']));self.object_list.addItem(item)
            if obj['id']==self.selected_object:selected_row=i
        self.object_list.setCurrentRow(selected_row);self._updating=False
        self.refresh_sequence()
        self.art_notice.setText('Ontwerp gewijzigd. Maak opnieuw steken om de wijzigingen in het borduurpatroon op te nemen.')
        mega=self.presets.currentIndex()==3
        self.hoop_notice.setText('Mega: 150 × 400 mm is het totale ontwerpbereik. De B540 gebruikt raamposities. Deze versie maakt geen automatische positiedeling; export van ontwerpen hoger dan 251 mm is geblokkeerd.' if mega else 'Raamomtrek is een conservatieve benadering; controleer het borduurgebied op de machine.')
        if full:
            outside=design.outside_indices(full,self.hoop_w.value(),self.hoop_h.value(),self.oval.isChecked(),self.margin.value())
            for i in outside:
                if i and (not self.playback or i<self.play_index):
                    a=full.stitches[i-1];b=full.stitches[i];pen=QPen(QColor('#ec2424'),2);pen.setCosmetic(True);line=scene.addLine(a[0],a[1],b[0],b[1],pen);line.setZValue(7)
            st=core.pattern_stats(full);metrics=design.route_metrics(full)
            self.status.setText(f'{st["width"]:.1f} × {st["height"]:.1f} mm | {st["stitches"]:,} steken | {st["colors"]} kleurblokken | {metrics["jumps"]} sprongen, {metrics["travel"]:.0f} mm totaal | '+(f'{len(outside)} PUNTEN BUITEN RAAM (rood)' if outside else 'PAST IN INGESTELD BEREIK')+(' | Mega: posities apart controleren' if mega else ''))
            self.status.setStyleSheet('color:'+('#b22222' if outside else '#187b51')+';font-weight:600;')
        elif self.objects:self.status.setText(f'{len(self.objects)} bewerkbare vlakken. Maak borduursteken om de ringcontrole uit te voeren.')
        self.selection_label.setText(self.current_object()['name']+' geselecteerd' if self.current_object() else f'{len(self.selected)} steekpunten geselecteerd')
        total=len(full.stitches) if full else 0;index=self.play_index if self.playback else total
        self._simulation_busy=True;self.slider.setRange(0,total);self.slider.setValue(index);self._simulation_busy=False
        block=sum((s[2]&emb.COMMAND_MASK)==emb.COLOR_CHANGE for s in (full.stitches[:index] if full else []))
        cmd=(full.stitches[index-1][2]&emb.COMMAND_MASK) if full and index else None
        names={emb.STITCH:'steek',emb.JUMP:'sprong',emb.TRIM:'knip',emb.COLOR_CHANGE:'kleurwissel',emb.END:'einde'}
        self.sim_label.setText(f'Punt {index:,}/{total:,} · kleur {block+1} · {names.get(cmd,"start")}')
        if self.playback and full and index:
            x,y,_=full.stitches[index-1];pen=QPen(QColor('#e62424'),2);pen.setCosmetic(True)
            line=scene.addLine(x-8,y,x+8,y,pen);line.setZValue(10);line=scene.addLine(x,y-8,x,y+8,pen);line.setZValue(10)
        scene.setSceneRect(scene.itemsBoundingRect().adjusted(-50,-50,50,50))
        self.draw_pro()
        self.draw_advanced()
        self.draw_hole_mark()
        self.draw_part_overlay()
    def save(self):
        self.request_fabric(self._save_ready)
    def _save_ready(self):
        if self.draft:return self.error('Sluit of annuleer de contour voordat je het project opslaat.')
        if not self.objects:return super().save()
        path,_=choose_save_file(self,'Project bewaren',self.path or 'Mijn_ontwerp.bst','BorduurStudio project (*.bst)')
        if path:
            path=str(Path(path).with_suffix('.bst'))
            try:core.save_project(path,self.image,self.palette,self.pattern,self.settings());self.path=path;self.status.setText('Project bewaard: '+path)
            except Exception as e:self.error(e)
    def export_objects_svg(self):
        self.request_fabric(self._export_objects_svg_ready)
    def _export_objects_svg_ready(self):
        if not self.objects:return self.error('Teken of importeer eerst bewerkbare vlakken.')
        path,_=choose_save_file(self,'Vlakken als vector bewaren','Mijn_ontwerp.svg','SVG (*.svg)')
        if path:
            try:design.objects_svg(self.objects,Path(path).with_suffix('.svg'));self.status.setText('Vectorontwerp bewaard.')
            except Exception as e:self.error(e)
    def export_svg(self):
        self.request_fabric(self._export_svg_ready)
    def _export_svg_ready(self):
        if self.objects:return self._export_objects_svg_ready()
        super().export_svg()
    def export(self):
        self.request_fabric(self._export_ready,require_pattern=True)
    def _export_ready(self):
        if self.draft:return self.error('Sluit of annuleer eerst de contour.')
        if self.presets.currentIndex()==3 and self.pattern and core.pattern_stats(self.pattern)['height']>251:
            return self.error('Het ontwerp gebruikt meerdere Mega-posities. Automatische positiedeling en registratie zijn nog niet aanwezig. Verdeel het ontwerp in aparte projecten of gebruik software die de B540 Mega-posities ondersteunt; deze versie exporteert dit lange ontwerp niet.')
        if self._preserving_for_save:
            changed=self.art_changed;self.art_changed=False
            try:super().export()
            finally:self.art_changed=changed
        else:super().export()
    def make_shortcut(self):
        if os.name!='nt':return self.error('De bureaubladsnelkoppeling wordt op Windows gemaakt.')
        try:
            from windows_setup import make_shortcut
            location=make_shortcut(Path(os.sys.executable),ROOT/'launch.py');QMessageBox.information(self,'Snelkoppeling klaar',f'BorduurStudio 2 staat nu op je bureaublad.\n{location}')
        except Exception as e:self.error(e)
    def closeEvent(self,event):
        self.stop_playback();super().closeEvent(event)
