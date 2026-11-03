import time
import numpy as np
import pyembroidery as emb
from PIL import Image,ImageDraw
from PySide6.QtWidgets import QApplication,QFileDialog,QMessageBox
import core,design
from studio2 import Studio2

def ring():
    obj=design.new_object([dict(x=-15,y=-15),dict(x=15,y=-15),dict(x=15,y=15),dict(x=-15,y=15)])
    obj['holes']=[[dict(x=-5,y=-5),dict(x=5,y=-5),dict(x=5,y=5),dict(x=-5,y=5)]]
    return obj

def test_connected_ring_no_internal_jumps_and_underlay_first(tmp_path):
    obj=ring();p=design.digitize_objects([obj],fabric_key='fleece')
    jumps=[s for s in p.stitches if s[2]&emb.COMMAND_MASK==emb.JUMP]
    assert len(jumps)==1
    layers=[r['layer'] for r in p.extras['route']]
    assert max(i for i,l in enumerate(layers) if l=='under')<min(i for i,l in enumerate(layers) if l!='under')
    mask,lo,_=design.raster_object(design.fabric.apply([obj],'fleece')[0])
    # Fill rows deliberately reach 0.2 mm under the outline (core.digitize).
    mask=design.ndimage.binary_dilation(mask,iterations=2)
    previous=None
    for x,y,c in p.stitches:
        if c&emb.COMMAND_MASK==emb.STITCH and previous is not None:
            assert design._safe_segment(mask,lo,previous,(x/10,y/10))
        if c&emb.COMMAND_MASK in (emb.STITCH,emb.JUMP):previous=(x/10,y/10)
    out=core.export_bundle(p,tmp_path/'ring.exp',145,255,True)
    loaded=emb.read(str(out));assert sum(s[2]&emb.COMMAND_MASK==emb.COLOR_CHANGE for s in loaded.stitches)==0

def test_raster_components_are_completed_before_next():
    im=Image.new('RGBA',(400,200));d=ImageDraw.Draw(im)
    d.rectangle((5,5,170,190),fill='red');d.rectangle((230,5,395,190),fill='red')
    p=core.digitize(im,[(255,0,0)],width_mm=40)
    ids=[r['component'] for r in p.extras['route']]
    assert sum(a!=b for a,b in zip(ids,ids[1:]))==1
    assert sum(s[2]&emb.COMMAND_MASK==emb.JUMP for s in p.stitches)==2

def test_one_button_processes_drawing_all_parts_to_exp(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([]);w=Studio2()
    im=Image.new('RGBA',(100,50));ImageDraw.Draw(im).rectangle((10,10,90,40),fill='blue');w.image=im
    w.generation_scope=['obsolete'];w.fabric_dialog=lambda:('fleece',False)
    monkeypatch.setattr(__import__('PySide6.QtWidgets',fromlist=['QInputDialog']).QInputDialog,'getText',lambda *a,**k:('auto',True))
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *a:(str(tmp_path/'auto.exp'),'Bernina EXP (*.exp)'))
    monkeypatch.setattr(QMessageBox,'information',lambda *a:None)
    errors=[];w.error=errors.append;w.start_full_embroidery()
    deadline=time.time()+25
    while not (tmp_path/'auto.exp').exists() and not errors and time.time()<deadline:app.processEvents();time.sleep(.01)
    assert not errors and (tmp_path/'auto.exp').exists()
    assert w.generation_scope is None and w.pattern.extras['routing_version']=='2.5'
    assert (tmp_path/'auto.inf').exists() and (tmp_path/'auto.bmp').exists()
    w.close()

def test_adjacent_same_color_dense_objects_connect_without_jump():
    a=design.new_object([dict(x=0,y=0),dict(x=10,y=0),dict(x=10,y=10),dict(x=0,y=10)])
    b=design.new_object([dict(x=10,y=0),dict(x=20,y=0),dict(x=20,y=10),dict(x=10,y=10)])
    p=design.digitize_objects([a,b],fabric_key='standard')
    assert sum(s[2]&emb.COMMAND_MASK==emb.JUMP for s in p.stitches)==1

def test_offset_outline_dimensions_density_and_export(tmp_path):
    import contour_outline
    obj=ring();obj['holes']=[]
    for kind in ('run','satin'):
        outlines=contour_outline.make_outlines([obj],kind=kind,width=2,spacing=.4,distance=3,length=1.5)
        x0,y0,x1,y1=design.object_bounds(outlines[0]);expected=36 if kind=='run' else 38
        assert abs((x1-x0)-expected)<.3 and abs((y1-y0)-expected)<.3
        p=design.digitize_objects([obj]+outlines,fabric_key='standard')
        assert core.export_bundle(p,tmp_path/(kind+'.exp'),145,255,True).exists()
    sparse=contour_outline.make_outlines([obj],kind='satin',spacing=.8)[0]
    dense=contour_outline.make_outlines([obj],kind='satin',spacing=.3)[0]
    assert len(design.digitize_objects([dense]).stitches)>len(design.digitize_objects([sparse]).stitches)

def test_contour_gui_adds_editable_outline():
    app=QApplication.instance() or QApplication([]);w=Studio2();obj=ring();w.objects=[obj];w.selected_object_ids={obj['id']};w.outline_distance.setValue(2);errors=[];w.error=errors.append;w.add_outline()
    assert not errors and len(w.objects)>1 and w.objects[-1]['outline_settings']['distance']==2
    w.close()
