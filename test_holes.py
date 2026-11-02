import copy,time
import pytest
import pyembroidery as emb
from PySide6.QtCore import Qt,QPointF
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
import design,core
from studio2 import Studio2,object_path
from holes_ui import edit_marked_holes

def box(x0,y0,x1,y1):return [dict(x=x0,y=y0,kind='corner'),dict(x=x1,y=y0,kind='corner'),dict(x=x1,y=y1,kind='corner'),dict(x=x0,y=y1,kind='corner')]
def outer():return design.new_object(box(-20,-15,20,15))
@pytest.fixture(scope='module')
def app():return QApplication.instance() or QApplication([])

def test_cut_and_close_keep_other_hole_and_roundtrip(tmp_path):
    obj=outer();obj['holes']=[box(10,5,14,9)];original=copy.deepcopy(obj)
    mark=box(-5,-5,5,5);out,ids,count=edit_marked_holes([obj],{obj['id']},mark,'cut')
    assert obj==original and len(out)==1 and len(out[0]['holes'])==2
    assert not object_path(out[0]).contains(QPointF(0,0))
    assert object_path(out[0]).contains(QPointF(-100,0))
    p=design.digitize_objects(out,fabric_key='fleece');previous=None
    for x,y,c in p.stitches:
        if c&emb.COMMAND_MASK==emb.STITCH and previous:
            middle=((x/10+previous[0])/2,(y/10+previous[1])/2)
            assert not (-4.7<middle[0]<4.7 and -4.7<middle[1]<4.7)
        if c&emb.COMMAND_MASK in (emb.STITCH,emb.JUMP):previous=(x/10,y/10)
    assert core.export_bundle(p,tmp_path/'hole.exp',145,255,True).exists()
    filled,_,n=edit_marked_holes(out,ids,box(-2,-2,2,2),'close')
    assert n==1 and len(filled[0]['holes'])==1
    assert object_path(filled[0]).contains(QPointF(0,0))
    assert not object_path(filled[0]).contains(QPointF(120,70))
    core.save_project(tmp_path/'hole.bst',None,[],p,dict(objects=out))
    _,_,_,settings=core.load_project(tmp_path/'hole.bst');assert len(settings['objects'][0]['holes'])==2

def test_cut_across_edge_splits_objects_and_keeps_settings():
    obj=outer();obj['angle']=43;out,ids,_=edit_marked_holes([obj],{obj['id']},box(-2,-30,2,30),'cut')
    assert len(out)==2 and len(ids)==2 and all(o['angle']==43 for o in out)
    assert all(not object_path(o).contains(QPointF(0,0)) for o in out)

def test_curved_mark_and_selected_scope():
    obj=outer();other=outer();other['color']='#ee4411'
    mark=box(-5,-5,5,5)
    for node in mark:node['kind']='smooth'
    out,_,_=edit_marked_holes([obj,other],{obj['id']},mark,'cut')
    assert len(out[0]['holes'])==1 and not out[1]['holes']
    assert not object_path(out[0]).contains(QPointF(0,0))

def test_mouse_left_right_enter_auto_stitches_undo(app):
    w=Studio2();obj=outer();w.objects=[obj];w.selected_object=obj['id'];w.selected_object_ids={obj['id']};w.show();w.refresh();w.fit();app.processEvents();errors=[];w.error=errors.append
    w.start_hole_mark('cut')
    for x,y,button in [(-5,-5,Qt.MouseButton.LeftButton),(5,-5,Qt.MouseButton.RightButton),(5,5,Qt.MouseButton.LeftButton),(-5,5,Qt.MouseButton.LeftButton)]:
        QTest.mouseClick(w.canvas.viewport(),button,pos=w.canvas.mapFromScene(QPointF(x*10,y*10)))
    assert len(w.draft)==4 and w.draft[1]['kind']=='smooth'
    QTest.keyClick(w.canvas,Qt.Key.Key_Return)
    deadline=time.time()+15
    while w.worker and w.worker.isRunning() and time.time()<deadline:app.processEvents();QTest.qWait(10)
    app.processEvents();assert not errors and len(w.objects[0]['holes'])==1 and w.pattern and not w.art_changed
    w.undo();assert not w.objects[0]['holes']
    w.start_hole_mark('cut');QTest.mouseClick(w.canvas.viewport(),Qt.MouseButton.LeftButton,pos=w.canvas.mapFromScene(QPointF(0,0)));QTest.keyClick(w.canvas,Qt.Key.Key_Escape);assert not w.draft and w.hole_operation is None
    w.close()
