import math,copy,os
from pathlib import Path
import numpy as np
import pytest
import pyembroidery as emb
from PIL import Image,ImageDraw
import core,design

def square(x=0,y=0,size=12,color='#168954',**options):
    return design.new_object([dict(x=x,y=y,kind='corner'),dict(x=x+size,y=y,kind='corner'),dict(x=x+size,y=y+size,kind='corner'),dict(x=x,y=y+size,kind='corner')],color,**options)

def assert_limit(p,limit=50.01):
    last=None
    for x,y,c in p.stitches:
        if (c&emb.COMMAND_MASK)==emb.STITCH and last is not None:assert math.dist(last,(x,y))<=limit
        if (c&emb.COMMAND_MASK) in (emb.STITCH,emb.JUMP):last=(x,y)

@pytest.mark.parametrize('fill',list(design.FILL_NAMES))
@pytest.mark.parametrize('fmt',['exp','pes'])
def test_fills_holes_and_export(tmp_path,fill,fmt):
    obj=square(-10,-10,20,fill=fill,length=5,spacing=1.5 if fill=='cross' else .45,satin=5,angle=35)
    hole=square(-2,-2,4);obj['holes']=[hole['nodes']]
    p=design.digitize_objects([obj]);assert core.pattern_stats(p)['stitches']>20;assert_limit(p)
    # No stitch passes through the central hole, including both diagonals of cross fill.
    last=None
    for x,y,c in p.stitches:
        if c==emb.STITCH and last is not None:
            for t in np.linspace(0,1,9):
                xx=(last[0]*(1-t)+x*t)/10;yy=(last[1]*(1-t)+y*t)/10
                assert not (-1.5<xx<1.5 and -1.5<yy<1.5)
        if c in (emb.STITCH,emb.JUMP):last=(x,y)
    out=core.export_bundle(p,tmp_path/f'{fill}.{fmt}',100,130,True,fmt=fmt)
    assert_limit(emb.read(str(out)))
    assert len(p.extras['owners'])==len(p.stitches)


def test_same_colour_nearest_reversal_and_overlap_order():
    a=square(-30,-20,10,fill='run');b=square(25,-20,10,fill='run');c=square(-12,-20,10,fill='run');c['color']='#ff3300'
    p=design.digitize_objects([a,c,b]);route=p.extras['route']
    assert route[0]['object']==b['id'] or route[0]['object']==c['id']
    # Separated objects sharing a colour form one block, even when another is in the list.
    green_indices=[i for i,t in enumerate(route) if t['color']==a['color']]
    assert green_indices==list(range(min(green_indices),max(green_indices)+1))
    foreground=square(-28,-18,5,color='#ffff22')
    p=design.digitize_objects([a,foreground]);order=[t['object'] for t in p.extras['route']]
    assert max(i for i,o in enumerate(order) if o==a['id'])<min(i for i,o in enumerate(order) if o==foreground['id'])


def test_underlay_before_top_and_satin():
    obj=square(-15,-15,30,fill='both');p=design.digitize_objects([obj]);layers=[r['layer'] for r in p.extras['route']]
    assert 'under' in layers and 'top' in layers and 'satin' in layers
    assert max(i for i,x in enumerate(layers) if x=='under')<min(i for i,x in enumerate(layers) if x=='top')
    assert max(i for i,x in enumerate(layers) if x=='top')<min(i for i,x in enumerate(layers) if x=='satin')


def test_points_curves_and_svg_roundtrip(tmp_path):
    obj=square();straight=design.flattened(obj['nodes']);obj['nodes'][1]['kind']='smooth';curved=design.flattened(obj['nodes'])
    assert any(abs(y)>0.05 for x,y in curved if 1<x<10)
    svg=tmp_path/'curves.svg';design.objects_svg([obj],svg)
    assert 'C ' in svg.read_text()
    from PySide6.QtSvg import QSvgRenderer
    assert QSvgRenderer(str(svg)).isValid()


def test_trace_preserves_white_detail_and_hole():
    im=Image.new('RGBA',(120,100),(0,0,0,0));d=ImageDraw.Draw(im);d.rectangle((5,5,90,90),fill='#159552');d.ellipse((20,20,50,50),fill=(0,0,0,0));d.ellipse((65,20,80,35),fill='white')
    objects=design.objects_from_art(im,60)
    assert len(objects)>=2 and any(o['color']=='#ffffff' for o in objects)
    green=next(o for o in objects if o['color']=='#159552')
    assert green['holes'];assert not design.point_inside(green,(35-60)*.5,(35-50)*.5)


def test_project_owners_and_vector_restore(tmp_path):
    obj=square(fill='run');p=design.digitize_objects([obj]);path=tmp_path/'drawing.bst'
    core.save_project(path,None,[],p,dict(objects=[obj],hoop_index=3));_,_,q,settings=core.load_project(path)
    assert settings['objects']==[obj];assert q.extras==p.extras
    duplicate=core.clone_pattern(q);duplicate.extras['owners'][0]='changed';assert duplicate.extras!=q.extras


def test_actual_position_and_compensation():
    a=square(20,30,10);p=design.digitize_objects([a]);bounds=np.array(p.bounds())/10
    assert np.allclose(bounds,[20,30,30,40],atol=.3)
    a['compensation']=.4;q=design.digitize_objects([a]);assert core.pattern_stats(q)['width']>core.pattern_stats(p)['width']


def test_ring_marking_and_large_mega():
    p=emb.EmbPattern();p.add_thread('red');p.add_stitch_absolute(emb.JUMP,700,1900);p.add_stitch_absolute(emb.STITCH,720,1930)
    assert design.outside_indices(p,150,400,False,2)==[]
    assert design.outside_indices(p,145,255,True,2)


def test_cleanup_tiny_fragments():
    im=Image.new('RGBA',(100,100),(0,0,0,0));d=ImageDraw.Draw(im);d.rectangle((10,10,80,80),fill='green');d.point((90,90),fill='red')
    cleaned,palette=design.clean_art(im,.3,50,0)
    assert cleaned.getpixel((90,90))[3]==0 and cleaned.getpixel((40,40))[3]==255


def test_stitch_limit_half_mm_and_validation():
    p=design.digitize_objects([square(fill='run',length=.5)]);assert_limit(p,5.01)
    with pytest.raises(ValueError):design.digitize_objects([square(length=5.1)])

def test_similar_palette_cleanup():
    im=Image.new('RGBA',(100,100),'#001351');ImageDraw.Draw(im).rectangle((40,10,60,90),fill='#031754')
    out,palette=design.clean_art(im,0,50,0,12);assert len(palette)==1
    out,palette=design.clean_art(im,0,50,0,0);assert len(palette)==2

@pytest.mark.parametrize('fill',['run','triple'])
def test_open_stitch_line_no_closing_edge(tmp_path,fill):
    obj=design.new_object([dict(x=-10,y=0,kind='corner'),dict(x=0,y=0,kind='smooth'),dict(x=10,y=4,kind='corner')],fill=fill,closed=False,length=2)
    p=design.digitize_objects([obj]);assert_limit(p,20.01)
    # Closing the path would add a 20 mm return, which must be absent.
    assert np.allclose(p.stitches[-1][:2],[100,40],atol=1) or np.allclose(p.stitches[-1][:2],[-100,0],atol=1)
    assert sum(s[2]==emb.JUMP for s in p.stitches)==1
    svg=tmp_path/'line.svg';design.objects_svg([obj],svg);assert 'fill="none"' in svg.read_text() and ' Z' not in svg.read_text()


def test_horizontal_open_line_allowed():
    obj=design.new_object([dict(x=-10,y=0),dict(x=10,y=0)],fill='run',closed=False)
    p=design.digitize_objects([obj]);assert core.pattern_stats(p)['height']==0 and core.pattern_stats(p)['width']==20
