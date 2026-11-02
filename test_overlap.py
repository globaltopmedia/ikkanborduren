import copy,time
import pytest
import pyembroidery as emb
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
import core,design
from studio2 import Studio2,object_path
from overlap_ui import cut_older_overlaps,exclusion_path,clip_overlap_tasks

def box(x0,y0,x1,y1):
    return [dict(x=x0,y=y0,kind='corner'),dict(x=x1,y=y0,kind='corner'),dict(x=x1,y=y1,kind='corner'),dict(x=x0,y=y1,kind='corner')]
def plane(x0=-10,y0=-10,x1=10,y1=10,**kw):return design.new_object(box(x0,y0,x1,y1),**kw)
@pytest.fixture(scope='module')
def app():return QApplication.instance() or QApplication([])

def test_interior_cut_preserves_new_and_settings_and_foreground_holes(app):
    old=plane(name='old',angle=37);new=plane(-5,-5,5,5,color='#ff4411');new['holes']=[box(-2,-2,2,2)]
    before=copy.deepcopy([old,new]);out,count=cut_older_overlaps([old,new],{new['id']})
    assert count==1 and out[-1]==new and [old,new]==before
    assert all(o['angle']==37 for o in out[:-1])
    assert any(object_path(o).contains(QPointF(0,0)) for o in out[:-1])
    assert not object_path(out[0]).contains(QPointF(40,0))
    assert object_path(out[0]).contains(QPointF(80,0))

def test_split_complete_cover_and_later_layers_unchanged(app):
    old=plane();new=plane(-1,-20,1,20);later=plane(color='#ff4411')
    out,count=cut_older_overlaps([old,new,later],{new['id']})
    assert count==1 and len(out)==4 and out[-2:]==[new,later]
    assert len({o['id'] for o in out})==4
    out,count=cut_older_overlaps([old,later],{later['id']})
    assert out==[later] and count==1

def test_scope_multiple_cutters_only_older_and_no_overlap_is_noop(app):
    old=plane();a=plane(-9,-9,-3,-3);b=plane(3,3,9,9)
    out,count=cut_older_overlaps([old,a,b],{a['id'],b['id']})
    assert count==1 and out[-2:]==[a,b] and len(out[0]['holes'])==2
    with pytest.raises(ValueError):cut_older_overlaps([old,a],{old['id']})
    with pytest.raises(ValueError):cut_older_overlaps([old],set())

def test_open_line_remains_open_and_clipped_segments(app):
    old=design.new_object([dict(x=-10,y=0,kind='corner'),dict(x=10,y=0,kind='corner')],fill='run',closed=False)
    new=plane(-2,-2,2,2);out,_=cut_older_overlaps([old,new],{new['id']})
    assert not out[0]['closed'] and out[0]['nodes']==old['nodes']
    tasks=clip_overlap_tasks(design._object_tasks(out[0]),out[0]);assert len(tasks)==2
    assert all(not (-1.99<(a[0]+b[0])/2<1.99) for t in tasks for a,b in zip(t['points'],t['points'][1:]))

@pytest.mark.parametrize('kind',['fill','both','satin'])
def test_generated_old_stitches_never_enter_cut_after_fabric_compensation(app,kind,tmp_path):
    old=plane(fill=kind,satin=3,color='#159552');new=plane(-3,-14,3,14,color='#ee4411',fill='both',satin=2)
    out,_=cut_older_overlaps([old,new],{new['id']},'terry');p=design.digitize_objects(out,fabric_key='terry')
    cut=exclusion_path(out[0]);old_ids={o['id'] for o in out if o['id']!=new['id']};owners=p.extras['owners']
    previous=None
    for i,(x,y,cmd) in enumerate(p.stitches):
        cmd &= emb.COMMAND_MASK
        if cmd==emb.STITCH and owners[i] in old_ids:
            assert not cut.contains(QPointF(x,y))
            if previous:
                for k in range(1,20):
                    q=QPointF(previous[0]+(x-previous[0])*k/20,previous[1]+(y-previous[1])*k/20)
                    assert not cut.contains(q)
        if cmd in (emb.JUMP,emb.STITCH):previous=(x,y)
    assert core.export_bundle(p,tmp_path/'overlap.exp',145,255,True).exists()

def test_exclusions_transform_and_project_roundtrip(app,tmp_path):
    old=plane();new=plane(-3,-3,3,3);out,_=cut_older_overlaps([old,new],{new['id']})
    design.transform_object(out[0],dx=20,dy=10,scale=2)
    assert exclusion_path(out[0]).contains(QPointF(200,100))
    assert not exclusion_path(out[0]).contains(QPointF(0,0))
    core.save_project(tmp_path/'cut.bst',None,[],None,dict(objects=out))
    _,_,_,settings=core.load_project(tmp_path/'cut.bst');assert settings['objects']==out

def test_cut_does_not_create_new_satin_edges(app):
    old=plane(fill='satin',satin=3,underlay=False);new=plane(-3,-14,3,14,color='#ee4411')
    reference=design.digitize_objects([old])
    def from_edge(x,y):return min(abs(abs(x/10)-10),abs(abs(y/10)-10))
    max_distance=max(from_edge(x,y) for x,y,c in reference.stitches if c&emb.COMMAND_MASK==emb.STITCH)
    out,_=cut_older_overlaps([old,new],{new['id']});p=design.digitize_objects(out)
    for stitch,owner in zip(p.stitches,p.extras['owners']):
        x,y,c=stitch
        if owner==old['id'] and c&emb.COMMAND_MASK==emb.STITCH:
            assert from_edge(x,y)<=max_distance+.1

def test_button_auto_generation_and_single_undo(app):
    old=plane();new=plane(-3,-3,3,3,color='#ee4411');w=Studio2();w.objects=[old,new]
    w.selected_object=new['id'];w.selected_object_ids={new['id']};w.refresh();errors=[];w.error=errors.append
    assert not w.overlap_button.icon().isNull()
    w.overlap_button.click();deadline=time.time()+30
    while w.worker and w.worker.isRunning() and time.time()<deadline:app.processEvents();QTest.qWait(10)
    app.processEvents();assert not errors and w.pattern and not w.art_changed
    assert w.objects[-1]==new and not object_path(w.objects[0]).contains(QPointF(0,0))
    w.undo();assert w.objects==[old,new] and w.pattern is None
    w.close()

def test_draw_new_shape_clears_old_selection(app):
    w=Studio2();old=plane();w.objects=[old];w.selected_object=old['id'];w.selected_object_ids={old['id']}
    w.start_shape();assert not w.chosen_ids()
    w.draft=box(-3,-3,3,3);w.finish_shape();assert w.chosen_ids()=={w.objects[-1]['id']}
    assert old['id'] not in w.chosen_ids();w.close()
