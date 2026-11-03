"""Meaningful round-trip and edit checks; no machine sewing claims."""
import copy,math,sys
from pathlib import Path
import pytest
import numpy as np
from PIL import Image,ImageDraw
import pyembroidery as emb
import core

def art():
    im=Image.new('RGBA',(140,100),'white');d=ImageDraw.Draw(im)
    d.rectangle((12,10,60,90),fill='#139552');d.ellipse((65,15,125,85),fill='#f13c24');d.ellipse((80,30,110,60),fill='white')
    return core.prepare_image(im,3,True)

def test_palette_transparency_and_enclosed_white():
    im,palette=art();a=np.array(im)
    assert a[0,-1,3]==0
    assert np.any((a[:,:,:3].min(axis=2)>230)&(a[:,:,3]==255))
    assert 2<=len(palette)<=3
    assert all(tuple(c) in palette for c in np.unique(a[:,:,:3][a[:,:,3]>128],axis=0))

@pytest.mark.parametrize('vertical',[False,True])
@pytest.mark.parametrize('fmt',['exp','pes'])
def test_digitize_export_roundtrip(tmp_path,vertical,fmt):
    im,palette=art();p=core.digitize(im,palette,70,underlay=True,vertical=vertical)
    assert core.pattern_stats(p)['stitches']>500
    last=None
    for x,y,c in p.stitches:
        if (c&emb.COMMAND_MASK)==emb.STITCH and last is not None:assert math.dist(last,(x,y))<=25.001
        if (c&emb.COMMAND_MASK) in (emb.STITCH,emb.JUMP):last=(x,y)
    path=core.export_bundle(p,tmp_path/f'test.{fmt}',100,100,False,2,fmt)
    loaded=emb.read(str(path))
    assert np.allclose(p.bounds(),loaded.bounds(),atol=2)
    assert core.hoop_fits(loaded,100,100,False,2)
    if fmt=='exp':
        assert path.with_suffix('.inf').exists() and path.with_suffix('.bmp').exists()
        threads=emb.EmbPattern()
        with open(path.with_suffix('.inf'),'rb') as f:emb.InfReader.read(f,threads)
        assert [t.color for t in threads.threadlist]==[t.color for t in p.threadlist]


def test_delete_jumps_over_removed_area():
    p=emb.EmbPattern();p.add_thread('red')
    for x in range(10):p.add_stitch_absolute(emb.STITCH,x*10,0)
    core.remove_stitches(p,[3,4,5])
    i=next(i for i,s in enumerate(p.stitches) if s[0]==60 and s[2]==emb.STITCH)
    assert p.stitches[i-1][2]==emb.JUMP
    assert all(s[0] not in (30,40,50) for s in p.stitches)


def test_hoop_rectangle_and_oval_reject_corners(tmp_path):
    p=emb.EmbPattern();p.add_thread('red');p.add_stitch_absolute(emb.JUMP,380,380);p.add_stitch_absolute(emb.STITCH,400,400)
    assert core.hoop_fits(p,100,100,False)
    assert not core.hoop_fits(p,100,100,True)
    with pytest.raises(ValueError):core.export_bundle(p,tmp_path/'outside.exp',100,100,True)
    assert not (tmp_path/'outside.exp').exists()


def test_project_roundtrip_and_svg(tmp_path):
    im,pal=art();p=core.digitize(im,pal,60);path=tmp_path/'project.bst'
    core.save_project(path,im,pal,p,{'width':60,'oval':True})
    im2,pal2,p2,settings=core.load_project(path)
    assert np.array_equal(np.array(im),np.array(im2))
    assert p2.stitches==p.stitches and [t.color for t in p2.threadlist]==[t.color for t in p.threadlist]
    assert settings['width']==60
    svg=tmp_path/'logo.svg';core.vectorize(im,svg)
    from PySide6.QtSvg import QSvgRenderer
    assert QSvgRenderer(str(svg)).isValid()


def test_resize_preserves_aspect_ratio():
    im,pal=art();p=core.digitize(im,pal,60);old=core.pattern_stats(p)
    core.resize_pattern(p,120);new=core.pattern_stats(p)
    assert new['width']==pytest.approx(120)
    assert new['height']/new['width']==pytest.approx(old['height']/old['width'])


def test_empty_pattern_not_exported(tmp_path):
    p=emb.EmbPattern();p.add_command(emb.END)
    with pytest.raises(ValueError):core.export_bundle(p,tmp_path/'empty.exp',100,100)

@pytest.mark.parametrize('mode',['satin','both'])
def test_satin_and_combined_limit_and_roundtrip(tmp_path,mode):
    im,pal=art();p=core.digitize(im,pal,60,mode=mode,satin_width=5,max_stitch=5)
    assert core.pattern_stats(p)['stitches']>300
    assert any(t['layer']=='satin' for t in p.extras['route'])
    path=core.export_bundle(p,tmp_path/f'{mode}.exp',100,100,False)
    loaded=emb.read(str(path));last=None
    for x,y,c in loaded.stitches:
        if c==emb.STITCH and last is not None:assert math.dist(last,(x,y))<=50.001
        if c in (emb.STITCH,emb.JUMP):last=(x,y)


def test_nearest_entry_includes_all_details_and_reverse():
    tasks=[{'points':[(0,0),(5,0)],'component':1,'layer':'top'},
           {'points':[(100,0),(50,0)],'component':2,'layer':'top'},
           {'points':[(15,15),(15,0)],'component':3,'layer':'top'}]
    reference=(49,0);distance,i,entry=core.nearest_entry(tasks,reference,{})
    assert (distance,i,entry)==(1,1,-1)
    # A top layer is not available before its underlay is finished.
    distance,i,entry=core.nearest_entry(tasks,reference,{2:1})
    assert i==2 and entry==-1


def test_clone_has_independent_stitches_and_threads():
    p=emb.EmbPattern();p.add_thread('red');p.add_stitch_absolute(emb.STITCH,0,0)
    q=core.clone_pattern(p);q.stitches[0][0]=50;q.threadlist[0].set_color(1,2,3)
    assert p.stitches[0][0]==0 and p.threadlist[0].color!=q.threadlist[0].color


def test_over_limit_settings_rejected():
    im,pal=art()
    with pytest.raises(ValueError):core.digitize(im,pal,satin_width=5.1)
    with pytest.raises(ValueError):core.digitize(im,pal,max_stitch=5.1)


def test_manual_long_stitches_capped_on_export(tmp_path):
    p=emb.EmbPattern();p.add_thread('red');p.add_stitch_absolute(emb.JUMP,-200,-200);p.add_stitch_absolute(emb.STITCH,200,200);p.add_command(emb.END)
    path=core.export_bundle(p,tmp_path/'manual.exp',100,100,False);q=emb.read(str(path));last=None
    for x,y,c in q.stitches:
        if c==emb.STITCH and last is not None:assert math.dist(last,(x,y))<=50.001
        if c in (emb.STITCH,emb.JUMP):last=(x,y)


def test_satin_border_follows_all_fill_layers():
    im,pal=art();p=core.digitize(im,pal,60,mode='both',satin_width=2)
    route=p.extras['route']
    for i,t in enumerate(route):
        if t['layer']=='satin':assert not any(u['color']==t['color'] and u['component']==t['component'] and u['layer'] in ('under','top') for u in route[i+1:])


def test_tatami_fill_rows_are_staggered_and_have_no_micro_segments():
    rows=[(0,100,10),(0,100,15),(0,100,20),(0,100,25)]
    pts=core._fill_points(rows,2.5,0,0)
    # Each row has alternating direction; compare sorted interior penetrations.
    row_x=[]
    for y in (10,15,20,25):
        row_x.append(sorted(x for x,yy in pts if yy==y))
    assert row_x[0][1:-1] != row_x[1][1:-1]
    assert row_x[1][1:-1] != row_x[2][1:-1]
    # Stitches inside a row stay >= 0.8 mm; the turn at the edge is exactly
    # one row spacing, so rows end neatly at the outline.
    assert min(math.dist(a,b) for a,b in zip(pts,pts[1:]) if a[1]==b[1]) >= 7.99
    assert min(math.dist(a,b) for a,b in zip(pts,pts[1:])) >= 4.99
    assert sum(a[1]!=b[1] for a,b in zip(pts,pts[1:]))==3
    assert max(math.dist(a,b) for a,b in zip(pts,pts[1:])) <= 25.001


def test_tatami_accepts_five_mm_maximum_stitch():
    rows=[(0,100,10),(0,100,15),(0,100,20)]
    pts=core._fill_points(rows,5.0,0,0)
    assert pts
    assert max(math.dist(a,b) for a,b in zip(pts,pts[1:])) <= 50.001
