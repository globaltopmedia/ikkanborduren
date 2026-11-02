import os,copy,math
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
import pyembroidery as emb
from PySide6.QtWidgets import QApplication,QMessageBox,QInputDialog
from PySide6.QtGui import QFontDatabase
from PySide6.QtCore import Qt,QSettings
import design,core,lettering,sequence,usb_export
from studio2 import Studio2

@pytest.fixture(scope='module')
def app():return QApplication.instance() or QApplication([])

def line(x,color='#159552'):
    return design.new_object([dict(x=x,y=0),dict(x=x+7.6,y=0)],color,fill='run',closed=False,underlay=False,length=2.5)

def test_manual_order_keeps_distant_objects_and_underlay():
    objects=[line(60),line(-10),line(10)]
    automatic=design.digitize_objects(objects);manual=design.digitize_objects(objects,manual_order=True)
    assert manual.extras['route'][0]['object']==objects[0]['id']
    assert [t['object'] for t in manual.extras['route']]==[o['id'] for o in objects]
    assert automatic.extras['route'][0]['object']==objects[1]['id']

def test_run_corner_distribution_avoids_tiny_grid_remnants():
    obj=design.new_object([dict(x=0,y=0),dict(x=7.6,y=0),dict(x=7.6,y=7.6)],fill='run',closed=False,length=2.5)
    tasks=design._object_tasks(obj);points=tasks[0]['points'];lengths=[math.dist(a,b) for a,b in zip(points,points[1:])]
    assert min(lengths)>1.8 and max(lengths)<=2.5
    assert (7.6,0) in points

@pytest.mark.parametrize('arc',[-120,0,120])
def test_letters_holes_curve_and_export(app,arc,tmp_path):
    family='DejaVu Sans' if 'DejaVu Sans' in QFontDatabase.families() else QFontDatabase.families()[0]
    objects=lettering.text_objects('BO',family,12,arc,1,fill='fill',spacing=.45,length=2.5,underlay=False)
    assert len(objects)>=2 and sum(len(o['holes']) for o in objects)>=3
    assert all(o['text']=='BO' for o in objects)
    boxes=[design.object_bounds(o) for o in objects]
    assert min(b[0] for b in boxes)==pytest.approx(-max(b[2] for b in boxes))
    # Contour coordinates change with the signed arc; not just the preview.
    straight=lettering.text_objects('BO',family,12,0,1)
    if arc:assert objects[0]['nodes']!=straight[0]['nodes']
    p=design.digitize_objects(objects,manual_order=True)
    path=core.export_bundle(p,tmp_path/f'letters{arc}.exp',145,255,True)
    assert core.pattern_stats(emb.read(str(path)))['stitches']>50


def test_letter_validation(app):
    for text,height,arc in [('',12,0),('a\nb',12,0),('A'*81,12,0),('A',2,0),('A',12,181)]:
        with pytest.raises(ValueError):lettering.text_objects(text,'DejaVu Sans',height,arc)


def test_reorder_import_preserves_thread_colours_and_absolute_stitches():
    p=design.digitize_objects([line(-20,'#ff0000'),line(20,'#0000ff')],manual_order=True);original=copy.deepcopy(p.stitches)
    q=sequence.reorder_blocks(p,[1,0]);assert p.stitches==original
    assert q.threadlist[0].color==p.threadlist[1].color
    old=sequence.colour_blocks(p);new=sequence.colour_blocks(q)
    for a,b in zip(new,reversed(old)):
        assert [s for s in a['points'] if (s[2]&emb.COMMAND_MASK)==emb.STITCH]==[s for s in b['points'] if (s[2]&emb.COMMAND_MASK)==emb.STITCH]
    assert len(q.extras['owners'])==len(q.stitches)


def test_usb_complete_project_no_mutation_or_silent_overwrite(tmp_path):
    p=design.digitize_objects([line(0)]);before=copy.deepcopy(p.stitches)
    files=usb_export.save_bundle(p,tmp_path,'Ontwerp',145,255,True,settings={'manual_order':True})
    assert {p.suffix for p in files}>={'.exp','.inf','.bmp','.bst','.txt','.png'}
    assert core.load_project(tmp_path/'Ontwerp.bst')[3]['manual_order']
    assert p.stitches==before
    with pytest.raises(FileExistsError):usb_export.save_bundle(p,tmp_path,'Ontwerp',145,255,True)
    with pytest.raises(ValueError):usb_export.save_bundle(p,tmp_path/'missing','Ontwerp',145,255)
    with pytest.raises(ValueError):usb_export.save_bundle(p,tmp_path,'../bad',145,255)


def test_usb_copy_failure_keeps_previous_files(tmp_path,monkeypatch):
    p=design.digitize_objects([line(0)]);usb_export.save_bundle(p,tmp_path,'Ontwerp',145,255)
    originals={f.name:f.read_bytes() for f in tmp_path.iterdir()}
    original_replace=os.replace;count=0
    def fail(source,target):
        nonlocal count
        count+=1
        if count==4:raise OSError('Stick losgekoppeld tijdens schrijven')
        return original_replace(source,target)
    monkeypatch.setattr(os,'replace',fail)
    with pytest.raises(OSError):usb_export.save_bundle(p,tmp_path,'Ontwerp',145,255,overwrite=True)
    assert {f.name:f.read_bytes() for f in tmp_path.iterdir()}==originals


def test_gui_order_text_replace_and_usb_stale_guard(app,tmp_path,monkeypatch):
    w=Studio2();w.fabric_dialog=lambda:('standard',True);w.preferences=QSettings(str(tmp_path/'settings.ini'),QSettings.Format.IniFormat);w.objects=[line(-20),line(20)];w.refresh()
    first=w.objects[0]['id'];w.order_list.setCurrentRow(0);w.move_sequence(1)
    assert w.objects[1]['id']==first and w.order_mode.currentIndex()==1
    w.undo();assert w.objects[0]['id']==first and w.order_mode.currentIndex()==0
    w.text_input.setText('BO');w.text_height.setValue(12);w.text_arc.setValue(90);w.add_lettering();group=w.current_object()['text_group'];old_ids={o['id'] for o in w.objects if o.get('text_group')==group}
    w.text_input.setText('GO');w.add_lettering(replace=True);assert not old_ids&{o['id'] for o in w.objects}
    w.pattern=design.digitize_objects([line(0)]);w.art_changed=True;messages=[];w.error=messages.append;w._save_usb_ready();assert 'opnieuw' in messages[0]
    w.art_changed=False;w.preferences.setValue('usb_directory',str(tmp_path));w.usb_name.setText('Ontwerp');monkeypatch.setattr(QMessageBox,'information',lambda *a:None)
    monkeypatch.setattr(QInputDialog,'getText',lambda *a,**k:('Ontwerp',True))
    w.save_usb();assert (tmp_path/'Ontwerp.exp').exists()
    w.close()


def test_manual_order_project_roundtrip(app,tmp_path):
    w=Studio2();w.fabric_dialog=lambda:('standard',True);w.objects=[line(20),line(-20)];w.order_mode.setCurrentIndex(1);w.pattern=design.digitize_objects(w.objects,manual_order=True);path=tmp_path/'order.bst';core.save_project(path,None,[],w.pattern,w.settings())
    w.order_mode.setCurrentIndex(0);w.load_path(path);assert w.order_mode.currentIndex()==1 and w.objects[0]['nodes'][0]['x']==20;w.close()


def test_real_order_list_drag_event(app):
    w=Studio2();w.fabric_dialog=lambda:('standard',True);w.objects=[line(20),line(-20),line(0)];original=[o['id'] for o in w.objects];w.refresh()
    model=w.order_list.model()
    assert model.moveRow(model.index(-1,-1),0,model.index(-1,-1),3)
    app.processEvents()
    assert [o['id'] for o in w.objects]==original[1:]+original[:1]
    assert w.order_mode.currentIndex()==1
    w.undo();assert [o['id'] for o in w.objects]==original;w.close()


def test_letter_group_restores_properties_and_moves_together(app):
    w=Studio2();w.fabric_dialog=lambda:('standard',True);w.font_picker.setCurrentFont(__import__('PySide6.QtGui',fromlist=['QFont']).QFont('DejaVu Sans'));w.text_input.setText('BO');w.text_arc.setValue(-90);w.add_lettering();group=w.current_object()['text_group'];before=copy.deepcopy(w.objects)
    w.dx.setValue(5);w.dy.setValue(3);w.move_text_group()
    assert all(o['nodes'][0]['x']==pytest.approx(b['nodes'][0]['x']+5) for o,b in zip(w.objects,before))
    w.text_input.setText('OTHER');w.text_arc.setValue(0);w.sync_object_controls();assert w.text_input.text()=='BO' and w.text_arc.value()==-90
    w.undo();assert w.objects==before;w.close()


def test_font_import_saved_copy_and_favourite(app,tmp_path,monkeypatch):
    from pathlib import Path
    from PySide6.QtCore import QStandardPaths
    from PySide6.QtWidgets import QFileDialog
    font=Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
    if not font.exists():pytest.skip('No local font file available for import test')
    w=Studio2();w.fabric_dialog=lambda:('standard',True);w.preferences=QSettings(str(tmp_path/'preferences.ini'),QSettings.Format.IniFormat)
    monkeypatch.setattr(QFileDialog,'getOpenFileName',lambda *a:(str(font),''));monkeypatch.setattr(QStandardPaths,'writableLocation',lambda *a:str(tmp_path/'appdata'))
    w.import_font();saved=w.preferences.value('font_files');assert len(saved)==1 and Path(saved[0]).read_bytes()==font.read_bytes()
    assert 'DejaVu Sans' in w.preferences.value('font_favourites')
    w.close()
