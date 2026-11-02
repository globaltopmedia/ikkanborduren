"""Real Enter, shortcuts and direction handles update the generated stitches."""
import copy
import math
import os
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
import pyembroidery as emb
from PIL import Image, ImageDraw
from PySide6.QtCore import QPointF, Qt, QLocale
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox
import core, design
from studio2 import Studio2


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def w(app):
    window=Studio2();window.error=lambda message:pytest.fail(str(message))
    window.show();window.activateWindow();app.processEvents()
    yield window
    while window.worker and window.worker.isRunning():
        app.processEvents();QTest.qWait(10)
    window.close();app.processEvents()


def rectangle(x, angle, color):
    return design.new_object([dict(x=x+a,y=b,kind='corner') for a,b in [(-5,-4),(5,-4),(5,4),(-5,4)]],
        color,angle=angle,spacing=.7,length=2.5,underlay=False)


def populated(w, selected=(0,)):
    w.objects=[rectangle(-18,0,'#ff0000'),rectangle(0,15,'#009900'),rectangle(18,30,'#0000ff')]
    w.pattern=design.digitize_objects(w.objects,fabric_key=w.fabric_key)
    w.selected_object_ids={w.objects[i]['id'] for i in selected}
    w.selected_object=w.objects[selected[0]]['id'] if selected else None
    w.sync_object_controls();w.refresh();w.fit();w.open_direction_page()


def wait(w, app):
    deadline=time.monotonic()+20
    while time.monotonic()<deadline:
        app.processEvents()
        if w.worker and not w.worker.isRunning() and w._generation_ok and w.direction_result.text():break
        QTest.qWait(10)
    app.processEvents()
    assert w._generation_ok and w.centralWidget().isEnabled()
    assert w.direction_result.text()


def assert_stitch_direction(pattern, identity, angle):
    owners=pattern.extras['owners'];previous=None;directions=[]
    for (x,y,cmd),owner in zip(pattern.stitches,owners):
        if previous and owner==identity and previous[2]==identity and cmd&emb.COMMAND_MASK==emb.STITCH:
            dx,dy=x-previous[0],y-previous[1]
            if math.hypot(dx,dy)>=15:
                directions.append(math.degrees(math.atan2(dy,dx)))
        previous=(x,y,owner)
    aligned=[a for a in directions if abs((a-angle+90)%180-90)<1]
    # Edge underlay and connecting stitches follow the contour; only the fill
    # rows should match the chosen angle.
    assert len(aligned)>=5


@pytest.mark.parametrize('selection,whole', [((0,),False),((0,1),False),((),True),((0,1,2),False)])
@pytest.mark.parametrize('enter', [Qt.Key.Key_Return,Qt.Key.Key_Enter])
def test_enter_changes_actual_stitches_for_one_many_or_all(w,app,selection,whole,enter):
    populated(w,selection);before=copy.deepcopy(w.objects);old=copy.deepcopy(w.pattern.stitches)
    w.direction_scope.setCurrentIndex(int(whole));w.show_sew.setChecked(False)
    w.sim_toggle.setChecked(True)
    edit=w.global_angle.lineEdit();edit.setFocus();edit.selectAll();QTest.keyClicks(edit,'63.5')
    assert w.objects==before and w.pattern.stitches==old
    QTest.keyClick(edit,enter);wait(w,app)
    targets=set(range(3)) if whole else set(selection)
    for i,obj in enumerate(w.objects):
        assert obj['angle']==(63.5 if i in targets else before[i]['angle'])
        assert obj['nodes']==before[i]['nodes'] and obj['holes']==before[i]['holes']
        assert_stitch_direction(w.pattern,obj['id'],obj['angle'])
    assert w.pattern.stitches!=old
    assert w.show_sew.isChecked() and not w.playback and not w.sim_toggle.isChecked()
    assert not w.art_changed and len(w.history)==1
    w.undo();assert w.objects==before and w.pattern.stitches==old
    assert w.global_fill_angle==45
    w.redo();assert all(w.objects[i]['angle']==63.5 for i in targets)


def test_dutch_decimal_angle_commits_on_enter(w,app):
    populated(w);w.global_angle.setLocale(QLocale('nl_NL'))
    edit=w.global_angle.lineEdit();edit.setFocus();edit.selectAll();QTest.keyClicks(edit,'27,5')
    QTest.keyClick(edit,Qt.Key.Key_Return);wait(w,app)
    assert w.objects[0]['angle']==27.5
    assert_stitch_direction(w.pattern,w.objects[0]['id'],27.5)


@pytest.mark.parametrize('angle,key',[(90,Qt.Key.Key_9),(180,Qt.Key.Key_1)])
@pytest.mark.parametrize('whole',[False,True])
def test_real_shortcuts_apply_to_chosen_scope(w,app,angle,key,whole):
    populated(w,(0,1));w.direction_scope.setCurrentIndex(int(whole));w.canvas.setFocus();app.processEvents()
    QTest.keyClick(w.canvas,key,Qt.KeyboardModifier.ControlModifier);wait(w,app)
    for i,obj in enumerate(w.objects):
        assert obj['angle']==(angle if whole or i<2 else 30)
        assert_stitch_direction(w.pattern,obj['id'],obj['angle'])


def test_ctrl_a_then_enter_changes_all_selected_planes(w,app):
    populated(w,(0,));w.canvas.setFocus();QTest.keyClick(w.canvas,Qt.Key.Key_A,Qt.KeyboardModifier.ControlModifier)
    assert len(w.chosen_ids())==3
    w.global_angle.setValue(82.7);QTest.keyClick(w.canvas,Qt.Key.Key_Return);wait(w,app)
    assert all(obj['angle']==82.7 for obj in w.objects)


def test_per_plane_angle_enter_updates_multiple_selection(w,app):
    populated(w,(0,1));w.tabs.setCurrentIndex(3)
    edit=w.object_angle.lineEdit();edit.setFocus();edit.selectAll();QTest.keyClicks(edit,'116.2')
    QTest.keyClick(edit,Qt.Key.Key_Return);wait(w,app)
    assert [o['angle'] for o in w.objects]==[116.2,116.2,30]
    assert_stitch_direction(w.pattern,w.objects[0]['id'],116.2)


@pytest.mark.parametrize('whole',[False,True])
def test_direction_handle_then_enter_updates_scope_and_undo(w,app,whole):
    populated(w,(0,1));before=copy.deepcopy(w.objects);old=copy.deepcopy(w.pattern.stitches)
    w.direction_scope.setCurrentIndex(int(whole));w.show_direction.setChecked(True);w.tool.setCurrentIndex(9);w.fit();app.processEvents()
    _,end,centre,_=w.direction_geometry();target=centre+QPointF(120,240)
    QTest.mousePress(w.canvas.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,w.canvas.mapFromScene(end))
    QTest.mouseMove(w.canvas.viewport(),w.canvas.mapFromScene(target))
    QTest.mouseRelease(w.canvas.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,w.canvas.mapFromScene(target))
    chosen=w.global_angle.value();assert chosen==pytest.approx(63.4,abs=1)
    assert w.objects==before and w.pattern.stitches==old and not w.history
    QTest.keyClick(w.canvas,Qt.Key.Key_Return);wait(w,app)
    assert [o['angle'] for o in w.objects]==[chosen,chosen,chosen if whole else 30]
    w.undo();assert w.objects==before and w.pattern.stitches==old


def test_all_overrides_previous_partial_generation(w,app):
    populated(w,());w.generation_scope=[w.objects[0]['id']]
    w.pattern=design.digitize_objects(w.objects[:1],fabric_key=w.fabric_key)
    w.direction_scope.setCurrentIndex(1);w.global_angle.setValue(90)
    QTest.keyClick(w.global_angle,Qt.Key.Key_Enter);wait(w,app)
    assert w.generation_scope is None
    assert set(w.pattern.extras['owners'])-{None}=={o['id'] for o in w.objects}


def test_new_design_and_shapes_default_to_45_degrees(w,app,monkeypatch):
    assert w.global_fill_angle==w.global_angle.value()==w.object_options()['angle']==45
    w.auto_shape.setChecked(False);w.make_shape(11,QPointF(-100,-80),QPointF(100,80))
    assert w.objects[0]['angle']==45
    monkeypatch.setattr(QMessageBox,'question',lambda *a:QMessageBox.StandardButton.Yes)
    w.global_angle.setValue(110);w.new_design()
    assert w.global_angle.value()==w.object_options()['angle']==45


def test_enter_all_traces_image_and_generates_at_default_angle(w,app):
    w.image=Image.new('RGBA',(60,30),(0,0,0,0));d=ImageDraw.Draw(w.image)
    d.rectangle((2,3,23,26),fill='#ff0000');d.rectangle((35,3,57,26),fill='#009900')
    w.width.setValue(35);w.open_direction_page();w.direction_scope.setCurrentIndex(1)
    QTest.keyClick(w.global_angle,Qt.Key.Key_Return);wait(w,app)
    assert len(w.objects)==2 and all(o['angle']==45 for o in w.objects)
    assert w.reference_only
    for obj in w.objects:assert_stitch_direction(w.pattern,obj['id'],45)
    w.undo();assert not w.objects and w.pattern is None and w.image is not None


def test_enter_without_selection_preserves_design(w,app):
    populated(w,());errors=[];w.error=errors.append
    before=copy.deepcopy(w.objects);old=copy.deepcopy(w.pattern.stitches)
    w.global_angle.setValue(90);QTest.keyClick(w.global_angle,Qt.Key.Key_Return)
    assert errors and not w.worker and not w.history
    assert w.objects==before and w.pattern.stitches==old


def test_enter_finishes_a_drawn_contour_instead_of_applying_angle(w,app):
    w.start_shape()
    for p in [QPointF(-30,-30),QPointF(30,-30),QPointF(30,30)]:w.add_node(p)
    QTest.keyClick(w.canvas,Qt.Key.Key_Return)
    assert len(w.objects)==1 and not w.draft and not w.worker
    assert w.objects[0]['angle']==45


def test_saved_angles_survive_loading_an_existing_project(w,app,tmp_path):
    populated(w,(0,1));path=tmp_path/'richtingen.bst'
    core.save_project(path,None,[],w.pattern,w.settings());w.load_path(str(path))
    assert [o['angle'] for o in w.objects]==[0,15,30]
    assert w.global_fill_angle==45
