import os,copy,time
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
import pyembroidery as emb
from PySide6.QtWidgets import QApplication,QDialog,QComboBox,QCheckBox,QMessageBox,QFileDialog
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
import fabric,design,lettering,core
from studio2 import Studio2

@pytest.fixture(scope='module')
def app():return QApplication.instance() or QApplication([])

def square(size=20,x=0,**options):
    return design.new_object([dict(x=x-size/2,y=-size/2),dict(x=x+size/2,y=-size/2),dict(x=x+size/2,y=size/2),dict(x=x-size/2,y=size/2)],**options)

@pytest.mark.parametrize('profile',list(fabric.PROFILES))
@pytest.mark.parametrize('mode',['fill','satin','both'])
def test_profile_underlay_precedes_top_and_export_max_length(profile,mode,tmp_path):
    obj=square(fill=mode);obj['holes']=[[dict(x=-3,y=-3),dict(x=3,y=-3),dict(x=3,y=3),dict(x=-3,y=3)]];original=copy.deepcopy(obj)
    p=design.digitize_objects([obj],fabric_key=profile)
    layers=[r['layer'] for r in p.extras['route']];assert 'under' in layers
    assert max(i for i,x in enumerate(layers) if x=='under')<min(i for i,x in enumerate(layers) if x!='under')
    assert obj==original and p.extras['fabric_profile']==profile
    # The 6 mm hole may only shrink by the profile's pull compensation plus
    # the 0.2 mm fill allowance (rows reach just under the outline).
    edge=3-float(fabric.apply([obj],profile)[0].get('compensation',0))-.2-1e-6
    previous=None
    for x,y,c in p.stitches:
        if previous and (c&emb.COMMAND_MASK)==emb.STITCH:
            mid=((x+previous[0])/20,(y+previous[1])/20);assert not (-edge<mid[0]<edge and -edge<mid[1]<edge)
        if (c&emb.COMMAND_MASK) in (emb.STITCH,emb.JUMP):previous=(x,y)
    assert core.export_bundle(p,tmp_path/(profile+mode+'.exp'),145,255,True).exists()


def test_underlay_only_when_needed_and_presets_are_idempotent():
    tiny=square(1,fill='satin');p=design.digitize_objects([tiny],fabric_key='thin');assert not any(t['layer']=='under' for t in p.extras['route'])
    outline=square(fill='run');assert not any(t['layer']=='under' for t in design.digitize_objects([outline],fabric_key='fleece').extras['route'])
    objects=[square()];first=fabric.apply(objects,'fleece');second=fabric.apply(objects,'fleece');assert first==second
    assert first[0]['compensation']>.1 and fabric.apply(objects,'thin')[0]['spacing']>fabric.apply(objects,'fleece')[0]['spacing']


def test_dotted_letters_are_atomic_and_dots_finished_before_stems(app):
    raw=lettering.text_objects('jij','DejaVu Sans',14,0,1,fill='satin',spacing=.45,length=2.5,satin=2)
    logical=design.logical_objects(raw);p=design.digitize_objects(raw,fabric_key='fleece')
    route=p.extras['route'];seen=[]
    for r in route:
        if not seen or seen[-1]!=r['unit']:seen.append(r['unit'])
    assert len(seen)==len(set(seen))==3
    for unit in seen:
        members=[o for o in logical if o.get('letter_id')==unit];dot=members[0]['id'];body=members[-1]['id'];records=[r for r in route if r['unit']==unit]
        assert max(i for i,r in enumerate(records) if r['object']==dot)<min(i for i,r in enumerate(records) if r['object']==body)
        assert any(r['object']==dot and r['layer']=='satin' for r in records)


def test_atomic_objects_no_interleave_and_safe_connector_skips_holes():
    objects=[square(20,x=0),square(20,x=40)]
    p=design.digitize_objects(objects,fabric_key='standard');ids=[t['object'] for t in p.extras['route']];changes=[i for i in range(1,len(ids)) if ids[i]!=ids[i-1]];assert len(changes)==1
    obj=square();mask,lo,_=design.raster_object(obj);assert design._safe_segment(mask,lo,(0,0),(1,0))
    obj['holes']=[[dict(x=-1,y=-1),dict(x=1,y=-1),dict(x=1,y=1),dict(x=-1,y=1)]];mask,lo,_=design.raster_object(obj);assert not design._safe_segment(mask,lo,(-2,0),(2,0))


def test_real_material_dialog_can_accept_and_cancel(app):
    w=Studio2()
    def accept():
        d=app.activeModalWidget();assert isinstance(d,QDialog);combo=d.findChild(QComboBox);combo.setCurrentIndex(combo.findData('fleece'));d.accept()
    QTimer.singleShot(0,accept);assert w.fabric_dialog()==('fleece',False)
    QTimer.singleShot(0,lambda:app.activeModalWidget().reject());assert w.fabric_dialog() is None;w.close()


def test_save_export_usb_always_ask_and_cancel_changes_nothing(app,tmp_path,monkeypatch):
    w=Studio2();w.objects=[square()];w.pattern=design.digitize_objects(w.objects);before=copy.deepcopy(w.pattern.stitches);calls=[]
    w.fabric_dialog=lambda:(calls.append('asked') or None)
    w.save();w.export();w.save_usb();assert calls==['asked']*3 and w.pattern.stitches==before
    w.close()


def test_save_material_regenerates_async_and_only_saves_after_success(app,tmp_path,monkeypatch):
    w=Studio2();w.objects=[square()];w.pattern=design.digitize_objects(w.objects);w.fabric_dialog=lambda:('fleece',False);actions=[]
    w.request_fabric(lambda:actions.append(w.pattern.extras['fabric_profile']),require_pattern=True)
    deadline=time.time()+15
    while not actions and time.time()<deadline:app.processEvents();QTest.qWait(10)
    assert actions==['fleece'] and not w.art_changed and w.centralWidget().isEnabled()
    w.close()


def test_imported_stitches_keep_geometry_and_note_only(app):
    w=Studio2();w.pattern=design.digitize_objects([square()]);before=copy.deepcopy(w.pattern.stitches);w.fabric_dialog=lambda:('fleece',True);actions=[]
    w.request_fabric(lambda:actions.append(True),require_pattern=True)
    assert actions and w.pattern.stitches==before and w.pattern.extras['fabric_selection']=='fleece' and not w.pattern.extras['fabric_profile'];w.close()


def test_svg_save_asks_material_too(app):
    w=Studio2();calls=[];w.fabric_dialog=lambda:(calls.append('asked') or None);w.export_svg();w.export_objects_svg();assert calls==['asked','asked'];w.close()


def test_fabric_failure_does_not_continue_to_export(app):
    w=Studio2();bad=square();bad['nodes'][0]['x']=float('nan');w.objects=[bad];w.fabric_dialog=lambda:('standard',False);actions=[];errors=[];w.error=errors.append
    w.request_fabric(lambda:actions.append('saved'),require_pattern=True)
    deadline=time.time()+10
    while w.worker.isRunning() and time.time()<deadline:app.processEvents();QTest.qWait(10)
    app.processEvents();assert errors and not actions and w.centralWidget().isEnabled();w.close()


def test_explicit_satin_points_before_overlapping_straight_cover_lines():
    stroke=square(20,fill='satin',stitch_phase=2);point=square(4,x=7,fill='satin',stitch_phase=0)
    p=design.digitize_objects([stroke,point],fabric_key='standard');ids=[r['object'] for r in p.extras['route']]
    assert max(i for i,x in enumerate(ids) if x==point['id'])<min(i for i,x in enumerate(ids) if x==stroke['id'])
    manual=design.digitize_objects([stroke,point],fabric_key='standard',manual_order=True)
    assert manual.extras['route'][0]['object']==stroke['id']


def test_overlapping_letter_units_wait_for_whole_unit_dependencies(app):
    objects=lettering.text_objects('ij','DejaVu Sans',14,0,0,fill='satin',spacing=.45,length=2.5,satin=2)
    units=list(dict.fromkeys(o['letter_id'] for o in objects))
    for obj in objects:
        if obj['letter_id']==units[1]:design.transform_object(obj,dx=-3)
    p=design.digitize_objects(objects,fabric_key='fleece');sequence=[]
    for record in p.extras['route']:
        if not sequence or sequence[-1]!=record['unit']:sequence.append(record['unit'])
    assert len(sequence)==len(set(sequence))==2
