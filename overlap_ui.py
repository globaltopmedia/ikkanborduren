"""Cut older layers underneath selected filled foreground objects."""
import copy, math, uuid
from PySide6.QtCore import QPointF
from PySide6.QtGui import QPainterPath, QPainterPathStroker
from PySide6.QtWidgets import QLabel,QPushButton
import design, fabric
from holes_ui import path_rings

def exclusion_path(obj):
    from studio2 import object_path
    path=QPainterPath()
    for piece in obj.get('overlap_exclusions',[]):path=path.united(object_path(piece))
    return path

def foreground_path(obj, fabric_key):
    from studio2 import object_path
    applied=fabric.apply([obj],fabric_key)[0] if fabric_key else obj
    path=object_path(obj)
    pad=float(applied.get('compensation',0))
    if obj.get('fill')=='both':pad+=float(obj.get('satin',2))/2
    if pad:
        stroke=QPainterPathStroker();stroke.setWidth(pad*20)
        path=path.united(stroke.createStroke(path))
    return path

def cut_older_overlaps(objects, selected_ids, fabric_key=None):
    from studio2 import object_path
    cutters=[(i,o) for i,o in enumerate(objects) if o['id'] in selected_ids and o.get('visible',True)]
    if not cutters:raise ValueError('Selecteer eerst het nieuwe vlak dat moet blijven bestaan.')
    if any(not o.get('closed',True) or o.get('fill') not in ('fill','both') for _,o in cutters):
        raise ValueError('Selecteer een gesloten vlak met Tatami of Tatami + satijnrand. Een losse stiklijn of satijncontour bedekt geen volledig vlak.')
    footprints={i:foreground_path(o,fabric_key) for i,o in cutters}
    output=[];count=0
    for i,obj in enumerate(objects):
        if obj['id'] in selected_ids or not obj.get('visible',True):output.append(copy.deepcopy(obj));continue
        marker=QPainterPath()
        for j,_ in cutters:
            if j>i:marker=marker.united(footprints[j])
        if marker.isEmpty():output.append(copy.deepcopy(obj));continue
        original=object_path(obj)
        # Closed planes are changed geometrically. Open lines are clipped only
        # while generating their stitches; they must never become filled shapes.
        line_only=not obj.get('closed',True) or obj.get('fill') in ('run','double','triple','dash','satin','zigzag')
        if line_only:
            width=float(obj.get('satin',2)) if obj.get('fill') in ('satin','zigzag') else .3
            stroke=QPainterPathStroker();stroke.setWidth(width*10)
            touched=stroke.createStroke(original).intersects(marker)
        else:touched=foreground_path(obj,fabric_key).intersects(marker)
        if not touched:output.append(copy.deepcopy(obj));continue
        pieces=path_rings(original.subtracted(marker)) if not line_only else [dict(nodes=obj['nodes'],holes=obj.get('holes',[]))]
        exclusions=obj.get('overlap_exclusions',[])+[dict(nodes=p['nodes'],holes=p['holes'],closed=True) for p in path_rings(marker)]
        for n,piece in enumerate(pieces):
            edited=copy.deepcopy(obj);edited.update(nodes=copy.deepcopy(piece['nodes']),holes=copy.deepcopy(piece['holes']),overlap_exclusions=copy.deepcopy(exclusions))
            if obj.get('fill')=='both' and not obj.get('overlap_satin_source'):
                # Keep the original satin outline; a cut must not invent a
                # new satin border around the remaining pieces.
                edited['overlap_satin_source']=dict(nodes=copy.deepcopy(obj['nodes']),holes=copy.deepcopy(obj.get('holes',[])))
            if n:edited['id']=uuid.uuid4().hex;edited['name']+=' deel '+str(n+1)
            edited.pop('entry_hint',None);edited.pop('exit_hint',None)
            output.append(edited)
        count+=1
    if not count:raise ValueError('Geen ouder vlak onder de selectie gevonden. Nieuwe vlakken staan bovenaan in de laagvolgorde; gebruik zo nodig Laag omhoog.')
    return output,count

def clip_overlap_tasks(tasks,obj):
    """Remove all sewn segments in the cut, including new edge underlay/satin.

    Keep ordinary stitch endpoints; subdivide only for locating intersections.
    Crossing endpoints are resolved to better than 0.001 mm.
    """
    path=exclusion_path(obj)
    if path.isEmpty():return tasks
    def inside(q):return path.contains(QPointF(q[0]*10,q[1]*10))
    result=[]
    for task in tasks:
        points=task['points'];run=[]
        def flush():
            nonlocal run
            if len(run)>1:
                edited=task|dict(points=run,closed=False)
                if task['layer']=='satin':edited['no_connector']=True
                result.append(edited)
            run=[]
        if not points:continue
        if not inside(points[0]):run=[points[0]]
        for a,b in zip(points,points[1:]):
            n=max(1,math.ceil(math.dist(a,b)/.05));previous=a;was=inside(a)
            for k in range(1,n+1):
                q=(a[0]+(b[0]-a[0])*k/n,a[1]+(b[1]-a[1])*k/n);now=inside(q)
                if now!=was:
                    low=previous;high=q
                    for _ in range(10):
                        mid=((low[0]+high[0])/2,(low[1]+high[1])/2)
                        if inside(mid)==was:low=mid
                        else:high=mid
                    boundary=low if not was else high
                    if now:run.append(boundary);flush()
                    else:run=[boundary]
                previous=q;was=now
            if not was:
                if not run:run=[b]
                elif math.dist(run[-1],b)>1e-8:run.append(b)
        flush()
    return result

class OverlapUI:
    def build_overlap(self):
        page=self.tabs.widget(3).widget();layout=page.layout()
        self.overlap_button=QPushButton('Overlap uitsnijden — nieuw vlak behouden')
        self.overlap_button.clicked.connect(self.cut_selected_overlap)
        layout.insertWidget(3,self.overlap_button)
        notice=QLabel('Selecteer het nieuwe gevulde vlak en klik op Overlap uitsnijden. Alleen oudere lagen eronder worden uitgesneden, inclusief onderlaag en satijnrand. Het nieuwe vlak en de rest van het ontwerp blijven bestaan. De steken worden opnieuw gemaakt; Ongedaan maken herstelt de vorige versie.')
        notice.setWordWrap(True);layout.insertWidget(4,notice)

    def cut_selected_overlap(self):
        if self.worker and self.worker.isRunning():return self.error('Wacht tot de steken klaar zijn.')
        if self.draft:return self.error('Sluit of annuleer eerst het nieuwe vlak.')
        try:
            ids=self.chosen_ids();objects,count=cut_older_overlaps(self.objects,ids,self.fabric_key)
            for obj in objects:design.validate_object(obj)
            self.checkpoint();self.objects=objects;self.selected.clear();self.active_node=None;self.generation_scope=None
            self.mark_objects_changed();self.refresh();self.sync_object_controls()
            self.launch_objects(checkpoint=False)
        except Exception as exc:self.error(exc)
