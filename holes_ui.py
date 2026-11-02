"""Mark curved regions to cut embroidery holes or close marked holes."""
import copy,uuid
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainterPath,QPen,QColor,QBrush
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QCheckBox
import design

def path_rings(path):
    """Convert boolean result into separate outside rings and their holes."""
    from studio2 import contour_path
    rings=[]
    for polygon in path.toSubpathPolygons():
        points=[(p.x()/10,p.y()/10) for p in polygon]
        if len(points)>1 and points[0]==points[-1]:points.pop()
        if len(points)<3:continue
        area=abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(points,points[1:]+points[:1])))/2
        if area<.01:continue
        nodes=[dict(x=x,y=y,kind='corner') for x,y in points]
        rings.append(dict(nodes=nodes,area=area,path=contour_path(nodes),point=polygon[0]))
    rings.sort(key=lambda r:-r['area'])
    groups=[]
    for i,ring in enumerate(rings):
        parents=[j for j in range(i) if rings[j]['path'].contains(ring['point'])]
        ring['depth']=len(parents)
        if len(parents)%2==0:groups.append(dict(index=i,nodes=ring['nodes'],holes=[]))
        else:
            outside=next(g for g in reversed(groups) if g['index'] in parents)
            outside['holes'].append(ring['nodes'])
    return groups

def edit_marked_holes(objects,ids,nodes,operation):
    from studio2 import contour_path,object_path
    if len(nodes)<3:raise ValueError('Markeer het gebied met minstens drie punten.')
    marker=contour_path(nodes).simplified()
    if marker.isEmpty() or marker.boundingRect().width()<1 or marker.boundingRect().height()<1:raise ValueError('De markering heeft geen bruikbaar oppervlak.')
    out=[];changed_ids=set();count=0
    for obj in objects:
        if obj['id'] not in ids or not obj.get('visible',True) or not obj.get('closed',True):out.append(copy.deepcopy(obj));continue
        if operation=='close':
            keep=[];removed=0
            for hole in obj.get('holes',[]):
                hp=contour_path(hole)
                if hp.intersects(marker) or marker.contains(hp) or hp.contains(marker):removed+=1
                else:keep.append(copy.deepcopy(hole))
            edited=copy.deepcopy(obj);edited['holes']=keep;out.append(edited)
            if removed:changed_ids.add(obj['id']);count+=removed
        else:
            original=object_path(obj)
            if original.intersected(marker).isEmpty():out.append(copy.deepcopy(obj));continue
            pieces=path_rings(original.subtracted(marker))
            for i,piece in enumerate(pieces):
                edited=copy.deepcopy(obj);edited['nodes']=piece['nodes'];edited['holes']=piece['holes']
                if i:edited['id']=uuid.uuid4().hex;edited['name']+=' deel '+str(i+1)
                # Entry hints can fall inside the new empty region.
                edited.pop('entry_hint',None);edited.pop('exit_hint',None)
                out.append(edited);changed_ids.add(edited['id'])
            count+=1
    if not count:raise ValueError('Geen gat binnen de markering gevonden.' if operation=='close' else 'De markering raakt geen gevuld deel van de gekozen vlakken.')
    return out,changed_ids,count

class HolesUI:
    def build_holes(self):
        self.hole_operation=None;self.hole_target_ids=set();self.hole_mark_modes={self.tool.count(),self.tool.count()+1}
        self.hole_cut_mode=self.tool.count();self.tool.addItem('Gat maken: links recht / rechts curve')
        self.hole_close_mode=self.tool.count();self.tool.addItem('Gaten sluiten: links recht / rechts curve')
        page=QWidget();lay=QVBoxLayout(page)
        text=QLabel('Markeer met muisklikken een gebied. Links plaatst een recht hoekpunt; rechts plaatst een curvepunt. Enter voert de bewerking uit. Backspace verwijdert het laatste punt; Esc annuleert.');text.setWordWrap(True);lay.addWidget(text)
        self.hole_scope=QComboBox();self.hole_scope.addItems(['Geselecteerde vlakken (zonder selectie: hele ontwerp)','Hele ontwerp']);lay.addWidget(self.hole_scope)
        self.button(lay,'Gat maken — gebied markeren',lambda:self.start_hole_mark('cut'))
        self.button(lay,'Gaten sluiten — gebied markeren',lambda:self.start_hole_mark('close'))
        row=QHBoxLayout();lay.addLayout(row);self.button(row,'Markering toepassen',self.finish_hole_mark);self.button(row,'Markering annuleren',self.cancel_hole_mark)
        self.hole_auto=QCheckBox('Steken na wijziging automatisch bijwerken');self.hole_auto.setChecked(True);lay.addWidget(self.hole_auto)
        self.hole_notice=QLabel('Gat maken verwijdert zowel de onderlaag als de bovenlaag in het gemarkeerde gebied. Gaten sluiten vult bestaande gaten die je met de markering raakt of omsluit; een geraakt gat wordt volledig gesloten. De overige gaten blijven open.');self.hole_notice.setWordWrap(True);lay.addWidget(self.hole_notice)
        lay.addStretch();self.add_page(page,'Gaten');self.holes_page_index=self.tabs.count()-1
    def start_hole_mark(self,operation):
        if self.worker and self.worker.isRunning():return self.error('Wacht tot de steken klaar zijn.')
        if self.draft:return self.error('Sluit of annuleer eerst de huidige markering of contour.')
        ids=self.chosen_ids() if self.hole_scope.currentIndex()==0 else set()
        if not self.objects and self.image is not None:self.trace_image()
        if not self.objects:return self.error('Open een tekening of een project met bewerkbare vlakken. Een los machinebestand heeft geen vlakcontouren om gaten opnieuw te vullen.')
        self.hole_target_ids=ids or {o['id'] for o in self.objects if o.get('visible',True)}
        self.hole_operation=operation;self.draft_hole=False;self.draft_open=False
        self.stop_playback();self.tool.setCurrentIndex(self.hole_cut_mode if operation=='cut' else self.hole_close_mode)
        self.tabs.setCurrentIndex(self.holes_page_index);self.canvas.setFocus();self.refresh()
    def cancel_hole_mark(self):
        self.draft=[];self.hole_operation=None;self.hole_target_ids=set();self.tool.setCurrentIndex(5);self.refresh()
    def finish_hole_mark(self):
        if not self.hole_operation:return self.error('Kies eerst Gat maken of Gaten sluiten en markeer een gebied.')
        try:
            objects,changed,count=edit_marked_holes(self.objects,self.hole_target_ids,self.draft,self.hole_operation)
            if not objects:raise ValueError('De markering verwijdert het hele ontwerp. Maak een kleiner gebied.')
            for obj in objects:design.validate_object(obj)
            self.checkpoint();self.objects=objects;self.selected_object_ids=changed;self.selected_object=next(iter(changed),None);self.selected.clear();self.generation_scope=None
            self.draft=[];self.hole_operation=None;self.hole_target_ids=set();self.tool.setCurrentIndex(5)
            self.mark_objects_changed();self.refresh();self.sync_object_controls()
            if self.hole_auto.isChecked():self.launch_objects(checkpoint=False)
        except Exception as e:self.error(e)
    def draw_hole_mark(self):
        if not self.hole_operation or len(self.draft)<3:return
        from studio2 import contour_path
        pen=QPen(QColor('#a24c22' if self.hole_operation=='cut' else '#168159'),2,Qt.PenStyle.DashLine);pen.setCosmetic(True)
        item=self.canvas.scene().addPath(contour_path(self.draft),pen,QBrush(QColor('#c4c4c4'),Qt.BrushStyle.BDiagPattern));item.setZValue(18)
