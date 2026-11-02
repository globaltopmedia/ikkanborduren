import os,copy
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtWidgets import QApplication,QFileDialog,QMessageBox
from PySide6.QtCore import QPointF,Qt,QRectF
from PySide6.QtTest import QTest
from studio2 import Studio2
import design,core

@pytest.fixture(scope='module')
def app():return QApplication.instance() or QApplication([])
@pytest.fixture
def studio(app):
    w=Studio2();w.fabric_dialog=lambda:('standard',True);w.show();app.processEvents();w.fit();yield w;w.close()

def draw_square(w):
    w.start_shape()
    for p in [(-10,-10),(10,-10),(10,10),(-10,10)]:w.add_node(QPointF(p[0]*10,p[1]*10),False)
    w.finish_shape()

def test_mouse_left_straight_right_smooth(studio,app):
    w=studio;w.start_shape();canvas=w.canvas
    for coords,button in [((-100,-100),Qt.MouseButton.LeftButton),((100,-100),Qt.MouseButton.RightButton),((100,100),Qt.MouseButton.LeftButton),((-100,100),Qt.MouseButton.LeftButton)]:
        QTest.mouseClick(canvas.viewport(),button,Qt.KeyboardModifier.NoModifier,canvas.mapFromScene(QPointF(*coords)))
    assert [n['kind'] for n in w.draft]==['corner','smooth','corner','corner']
    QTest.keyClick(canvas,Qt.Key.Key_Return);assert len(w.objects)==1 and not w.draft


def test_object_edit_and_undo(studio):
    w=studio;draw_square(w);original=copy.deepcopy(w.objects)
    w.move_selected(5,3);assert w.objects[0]['nodes'][0]['x']==-5
    w.undo();assert w.objects==original
    w.redo();assert w.objects[0]['nodes'][0]['x']==-5
    w.selected_object=w.objects[0]['id'];w.duplicate_object();assert len(w.objects)==2
    w.delete_object();assert len(w.objects)==1


def test_save_reload_simulation_and_selection(studio,tmp_path,monkeypatch):
    w=studio;draw_square(w);w.pattern=design.digitize_objects(w.objects);w.art_changed=False;w.refresh();original=copy.deepcopy(w.pattern.stitches)
    monkeypatch.setattr(__import__('PySide6.QtWidgets',fromlist=['QInputDialog']).QInputDialog,'getText',lambda *a,**k:('my',True))
    path=tmp_path/'my.bst';monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *a:(str(path),''));w.save();w.objects=[];w.load_path(path)
    assert len(w.objects)==1 and w.pattern.stitches==original
    w.sim_toggle.setChecked(True);assert w.play_index==0;w.step();assert w.play_index==1
    w.tick();assert w.play_index>1;assert w.pattern.stitches==original
    w.slider.setValue(4);assert w.play_index==4;w.sim_toggle.setChecked(False)
    w.selected_object=w.objects[0]['id'];w.select_object_stitches();assert len(w.selected)>50
    w.delete_selected();assert not w.pattern.extras.get('owners');w.undo();assert w.pattern.stitches==original


def test_presets_and_mega_export_guard(studio,monkeypatch):
    w=studio;w.presets.setCurrentIndex(1);assert (w.hoop_w.value(),w.hoop_h.value())==(100,130)
    w.presets.setCurrentIndex(3);assert (w.hoop_w.value(),w.hoop_h.value())==(150,400) and not w.oval.isChecked()
    obj=design.new_object([dict(x=-10,y=-160),dict(x=10,y=-160),dict(x=10,y=160),dict(x=-10,y=160)],fill='run')
    w.pattern=design.digitize_objects([obj]);messages=[];w.error=messages.append;w.export();assert 'Mega' in messages[0]


def test_change_size_and_reference_import(studio):
    w=studio;draw_square(w);w.width.setValue(40);w.resize_objects();assert design.object_bounds(w.objects[0])[2]-design.object_bounds(w.objects[0])[0]==40
    w.center_objects();b=design.object_bounds(w.objects[0]);assert b[0]==-20

def test_worker_real_completion(studio,app):
    import time
    w=studio;draw_square(w);w.generate_objects();assert not w.centralWidget().isEnabled()
    deadline=time.time()+10
    while w.worker.isRunning() and time.time()<deadline:
        app.processEvents();QTest.qWait(10)
    app.processEvents();assert w.pattern is not None and core.pattern_stats(w.pattern)['stitches']>100
    assert w.centralWidget().isEnabled() and not w.art_changed


def test_shortcut_paths_are_literal(tmp_path,monkeypatch):
    import windows_setup,subprocess
    exe=tmp_path/'python.exe';exe.write_text('');exe.with_name('pythonw.exe').write_text('');entry=tmp_path/"Gebruiker's map"/'launch.py';calls=[]
    def run(args,**kwargs):calls.append((args,kwargs));return subprocess.CompletedProcess(args,0,'Desktop\\BorduurStudio 2.lnk\n','')
    monkeypatch.setattr(subprocess,'run',run);assert windows_setup.make_shortcut(exe,entry).endswith('.lnk')
    script=calls[0][0][-1];assert "Gebruiker''s map" in script and '-ExecutionPolicy' not in calls[0][0]

def test_open_line_and_node_add_remove(studio):
    w=studio;w.start_shape(line=True);w.add_node(QPointF(-100,0));w.add_node(QPointF(100,0));w.finish_shape()
    assert not w.objects[0]['closed'] and w.objects[0]['fill']=='run'
    w.insert_contour_node(QPointF(0,0),True);assert len(w.objects[0]['nodes'])==3 and w.objects[0]['nodes'][1]['kind']=='smooth'
    w.delete_contour_node();assert len(w.objects[0]['nodes'])==2;w.undo();assert len(w.objects[0]['nodes'])==3


def test_ctrl_constrains_drawing_direction(studio):
    import math
    w=studio;w.start_shape();canvas=w.canvas;w.add_node(QPointF(0,0))
    QTest.mouseClick(canvas.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.ControlModifier,canvas.mapFromScene(QPointF(120,30)))
    node=w.draft[-1];angle=math.degrees(math.atan2(node['y'],node['x']));assert angle==pytest.approx(15)
    w.cancel_shape()
