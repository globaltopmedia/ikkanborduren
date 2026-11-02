import os,time,copy,math
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest,pyembroidery as emb
from PIL import Image,ImageDraw
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPointF,Qt
from PySide6.QtTest import QTest
import design,core,part_geometry
from studio2 import Studio2

@pytest.fixture(scope='module')
def app():return QApplication.instance() or QApplication([])
@pytest.fixture
def w(app):
    window=Studio2();window.show();app.processEvents();yield window
    while window.worker and window.worker.isRunning():app.processEvents();QTest.qWait(10)
    window.close()

def square(x=0,size=12,**options):return design.new_object([dict(x=x-size/2,y=-size/2),dict(x=x+size/2,y=-size/2),dict(x=x+size/2,y=size/2),dict(x=x-size/2,y=size/2)],**options)

def wait(window,app):
    until=time.time()+15
    while window.worker and window.worker.isRunning() and time.time()<until:app.processEvents();QTest.qWait(10)
    app.processEvents();assert window.centralWidget().isEnabled()


def test_lasso_isolated_objects_and_stitches():
    objects=[square(0),square(30)];p=design.digitize_objects(objects);polygon=[(-80,-80),(80,-80),(80,80),(-80,80)]
    ids,stitches=part_geometry.lasso_selection(objects,p,polygon);assert ids=={objects[0]['id']} and not stitches
    ids,stitches=part_geometry.lasso_selection(objects,p,polygon,False);assert not ids and stitches
    assert all(abs(p.stitches[i][0])<80 for i in stitches)


def test_real_mouse_select_line_and_direction_handle(w,app):
    w.objects=[square(),square(30)];w.selected_object=w.objects[0]['id'];w.selected_object_ids={w.selected_object};w.refresh();w.fit();w.tool.setCurrentIndex(8)
    for point in [(-90,-90),(90,-90),(90,90),(-90,90)]:QTest.mouseClick(w.canvas.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,w.canvas.mapFromScene(QPointF(*point)))
    QTest.keyClick(w.canvas,Qt.Key.Key_Return);assert w.selected_object_ids=={w.objects[0]['id']}
    w.tool.setCurrentIndex(9);a,b,centre,angle=w.direction_geometry();QTest.mousePress(w.canvas.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,w.canvas.mapFromScene(b));target=centre+QPointF(120,120);QTest.mouseMove(w.canvas.viewport(),w.canvas.mapFromScene(target));QTest.mouseRelease(w.canvas.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,w.canvas.mapFromScene(target));assert w.global_angle.value()==pytest.approx(45,abs=1)
    QTest.keyClick(w.canvas,Qt.Key.Key_Return);wait(w,app);assert w.objects[0]['angle']==pytest.approx(45,abs=1)
    assert w.objects[1].get('angle',0)==0


def test_clicked_bitmap_component_excludes_adjacent_and_disconnected_colours():
    image=Image.new('RGBA',(120,80),'white');d=ImageDraw.Draw(image);d.rectangle((10,10,45,60),fill='red');d.rectangle((46,10,85,60),fill='blue');d.rectangle((95,15,110,35),fill='red')
    objects=part_geometry.clicked_region(image,120,-35,0);assert len(objects)==1 and objects[0]['color']=='#ff0000'
    assert design.object_bounds(objects[0])[2]<-10
    with pytest.raises(ValueError):part_geometry.clicked_region(image,120,0,-35)


def test_click_and_sew_only_one_part_and_persist_scope(w,app,tmp_path):
    w.objects=[square(),square(30)];w.refresh();w.click_and_sew(QPointF(0,0));wait(w,app)
    owners=set(w.pattern.extras['owners'])-{None};assert owners=={w.objects[0]['id']} and len(w.objects)==2
    path=tmp_path/'one.bst';core.save_project(path,None,[],w.pattern,w.settings());w.generation_scope=None;w.load_path(path);assert w.generation_scope==[w.objects[0]['id']]
    w.launch_objects();wait(w,app);assert set(w.pattern.extras['owners'])-{None}==owners


def test_open_satin_ribbon_and_reversed_endpoints(tmp_path):
    obj=design.new_object([dict(x=0,y=0),dict(x=20,y=0)],closed=False,fill='satin',satin=4,length=5,spacing=.45)
    p=design.digitize_objects([obj]);bounds=core.pattern_stats(p);assert bounds['height']<=4.01
    end=part_geometry.endpoints(p)[obj['id']];obj['route_reversed']=True;obj['entry_hint']=[v/10 for v in end['end']];obj['exit_hint']=[v/10 for v in end['start']]
    reversed_pattern=design.digitize_objects([obj]);new=part_geometry.endpoints(reversed_pattern)[obj['id']];assert new['start']==end['end'] and new['end']==end['start']
    assert core.export_bundle(reversed_pattern,tmp_path/'line.exp',145,255,True).exists()


def test_open_straight_line_endpoint_reverse_exact():
    obj=design.new_object([dict(x=0,y=0),dict(x=20,y=0)],closed=False,fill='run');p=design.digitize_objects([obj]);ends=part_geometry.endpoints(p)[obj['id']]
    obj.update(route_reversed=True,entry_hint=[v/10 for v in ends['end']],exit_hint=[v/10 for v in ends['start']]);q=design.digitize_objects([obj]);new=part_geometry.endpoints(q)[obj['id']];assert new['start']==ends['end'] and new['end']==ends['start']

@pytest.mark.parametrize('kind',['star4','star6','star8','star12','diamond','circle_pattern','chevron','flower_pattern'])
def test_motifs_fit_mask_and_holes_and_export(kind,tmp_path):
    obj=square(size=30,fill=kind,spacing=3,length=2.5);obj['holes']=[[dict(x=-3,y=-3),dict(x=3,y=-3),dict(x=3,y=3),dict(x=-3,y=3)]]
    p=design.digitize_objects([obj],fabric_key='fleece');previous=None
    for x,y,cmd in p.stitches:
        if previous and (cmd&emb.COMMAND_MASK)==emb.STITCH:
            mx,my=(x+previous[0])/20,(y+previous[1])/20;assert not(-2.9<mx<2.9 and -2.9<my<2.9)
        if (cmd&emb.COMMAND_MASK) in (emb.STITCH,emb.JUMP):previous=x,y
    assert core.export_bundle(p,tmp_path/(kind+'.pes'),145,255,True,fmt='pes').exists()
    if kind.startswith('star'):
        tasks=design._object_tasks(obj);points=tasks[0]['points'];assert len(points)==int(kind[4:])*2+1
        assert all(points[i]==points[0] for i in range(0,len(points),2))

@pytest.mark.parametrize('mode',[11,12,13])
def test_native_shapes_editable_and_generate_only_requested_shape(w,app,mode):
    w.auto_shape.setChecked(False);w.make_shape(mode,QPointF(-150,-100),QPointF(150,100));assert len(w.objects)==1
    bounds=design.object_bounds(w.objects[0]);assert bounds[2]-bounds[0]==pytest.approx(30,abs=.05)
    if mode==13:assert bounds[3]-bounds[1]==pytest.approx(30,abs=.05)
    w.generate_selection();wait(w,app);assert w.pattern is not None and core.pattern_stats(w.pattern)['stitches']>20


def test_real_mouse_rectangle_creation(w,app):
    w.auto_shape.setChecked(False);w.tool.setCurrentIndex(11);QTest.mousePress(w.canvas.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,w.canvas.mapFromScene(QPointF(-100,-80)));QTest.mouseMove(w.canvas.viewport(),w.canvas.mapFromScene(QPointF(100,80)));QTest.mouseRelease(w.canvas.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,w.canvas.mapFromScene(QPointF(100,80)));assert w.objects[0]['name']=='Rechthoek'


def test_true_overlap_excludes_an_island_inside_a_hole():
    ring=square(size=30);ring['holes']=[[dict(x=-8,y=-8),dict(x=8,y=-8),dict(x=8,y=8),dict(x=-8,y=8)]];island=square(size=8)
    assert design._bbox_overlap(ring,island) and not design._objects_overlap(ring,island,{})

@pytest.mark.parametrize('kind',['satin','zigzag'])
def test_open_band_has_centre_underlay_before_top(kind):
    obj=design.new_object([dict(x=0,y=0),dict(x=20,y=0)],closed=False,fill=kind,satin=4,length=5)
    import fabric
    prepared=fabric.apply([obj],'fleece')[0];tasks=design._object_tasks(prepared)
    assert tasks[0]['layer']=='under' and tasks[1]['layer']=='satin'
    assert all(y==0 for x,y in tasks[0]['points'])
    p=design.digitize_objects([obj],fabric_key='fleece')
    previous=None
    for x,y,cmd in p.stitches:
        if previous and cmd&emb.COMMAND_MASK==emb.STITCH:assert math.dist(previous,(x,y))<=50.001
        if cmd&emb.COMMAND_MASK in (emb.STITCH,emb.JUMP):previous=x,y


def test_undo_restores_scope_and_global_angle(w,app):
    w.objects=[square(),square(30)];w.generation_scope=[w.objects[0]['id']];w.global_angle.setValue(35);w.checkpoint()
    w.generation_scope=None;w.global_angle.setValue(-55);w.restore(w.history,w.future)
    assert w.generation_scope==[w.objects[0]['id']] and w.global_angle.value()==35
