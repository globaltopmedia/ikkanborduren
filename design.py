"""Editable vector objects and stitch routing. Vector coordinates are millimetres.
Independent implementation; no BERNINA software code or ART reader.
"""
import copy, math, uuid, html, re
import fabric
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
import pyembroidery as emb
import core
import line_fill

FILL_NAMES={'fill':'Tatami — dicht vlak','column':'Satijnsteek — volgt de vorm (lijnen, smalle delen)','satin_fill':'Satijnvulling — van rand tot rand in de steekrichting','satin':'Satijnrand langs de contour','both':'Tatami + satijnrand',
            'run':'Enkele stiklijn','double':'Dubbele stiklijn (heen en terug)','triple':'Drievoudige stiklijn','cross':'Kruissteekvulling','zigzag':'Zigzaglijn','dash':'Onderbroken stiklijn','star4':'Sterretjes — 4 stralen','star6':'Sterretjes — 6 stralen','star8':'Sterretjes — 8 stralen','star12':'Sterretjes — 12 stralen','diamond':'Ruitjesvulling','circle_pattern':'Cirkeltjesvulling','chevron':'Chevronvulling','flower_pattern':'Bloemetjesvulling','applique':'Applicatie — plaatsing, vastzetten, satijnrand'}
LINE_FILLS=('run','double','triple','dash')
APPLIQUE_TACKS={'zigzag':'Open zigzag','double':'Dubbele stiklijn','run':'Enkele stiklijn'}
HOOPS=[('Eigen maat',None,None,False),('Medium — 100 × 130 mm',100,130,True),
       ('Large Oval — 145 × 255 mm',145,255,True),('Mega Hoop — 150 × 400 mm',150,400,False)]

def new_object(nodes,color='#159552',name='Vlak',**settings):
    return dict(id=uuid.uuid4().hex,name=name,nodes=copy.deepcopy(nodes),holes=[],color=color,
        fill=settings.get('fill','fill'),spacing=settings.get('spacing',.45),length=settings.get('length',2.5),
        satin=settings.get('satin',2),angle=settings.get('angle',0),underlay=settings.get('underlay',True),
        compensation=settings.get('compensation',0),stitch_phase=settings.get('stitch_phase',1),route_reversed=settings.get('route_reversed',False),visible=True,closed=settings.get('closed',True))

def segments(nodes,closed=True):
    """Cubic handles use local chords. Corner clicks keep straight adjoining segments.
    Smooth clicks get a symmetric tangent, bounded to prevent large overshoot.
    """
    n=len(nodes)
    if n<2:return []
    pts=[np.array([float(p['x']),float(p['y'])]) for p in nodes]
    def tangent(i):
        if nodes[i].get('kind','corner')!='smooth':return np.zeros(2)
        if not closed and i==0:return (pts[1]-pts[0])/3
        if not closed and i==n-1:return (pts[-1]-pts[-2])/3
        a,b=pts[(i-1)%n],pts[(i+1)%n];t=(b-a)/6
        cap=min(np.linalg.norm(pts[i]-a),np.linalg.norm(b-pts[i]))/2
        norm=np.linalg.norm(t)
        return t*(min(1,cap/norm) if norm else 0)
    out=[]
    for i in range(n if closed else n-1):
        j=(i+1)%n;p,q=pts[i],pts[j]
        curved=nodes[i].get('kind')=='smooth' or nodes[j].get('kind')=='smooth'
        out.append((p,p+tangent(i),q-tangent(j),q,curved))
    return out

def flattened(nodes,closed=True,step=.15):
    result=[]
    for p,a,b,q,curved in segments(nodes,closed):
        count=max(1,math.ceil((np.linalg.norm(a-p)+np.linalg.norm(b-a)+np.linalg.norm(q-b))/step))
        for t in np.linspace(0,1,count,endpoint=False):
            v=(1-t)**3*p+3*(1-t)**2*t*a+3*(1-t)*t*t*b+t**3*q if curved else p+(q-p)*t
            result.append(tuple(v))
    if result:result.append(result[0] if closed else (nodes[-1]['x'],nodes[-1]['y']))
    return result

def object_bounds(obj):
    points=flattened(obj['nodes'],obj.get('closed',True))
    if not points:raise ValueError('Vlak heeft te weinig punten.')
    a=np.array(points);return (*a.min(axis=0),*a.max(axis=0))

def validate_object(obj):
    minimum_nodes=3 if obj.get('closed',True) else 2
    if len(obj.get('nodes',[]))<minimum_nodes:raise ValueError('Een gesloten vlak heeft drie punten nodig; een open lijn twee.')
    if not obj.get('closed',True) and obj.get('fill') not in LINE_FILLS+('satin','zigzag'):raise ValueError('Een open lijn gebruikt stik-, onderbroken, zigzag- of satijnsteken.')
    if obj.get('fill','fill') not in FILL_NAMES:raise ValueError('Onbekende vlakvulling.')
    for k,lo,hi in [('length',.5,5),('spacing',.3,5),('satin',.5,5),('compensation',0,1)]:
        value=float(obj.get(k,{'length':2.5,'spacing':.45,'satin':2,'compensation':0}[k]))
        if not lo<=value<=hi:raise ValueError(f'{k}: waarde moet tussen {lo} en {hi} liggen.')
    for ring in [obj['nodes']]+obj.get('holes',[]):
        if len(ring)<minimum_nodes:raise ValueError('Te weinig contourpunten.')
        for node in ring:
            if not all(math.isfinite(float(node[k])) and abs(float(node[k]))<=1000 for k in ('x','y')):raise ValueError('Ongeldig contourpunt.')
    x0,y0,x1,y1=object_bounds(obj)
    if max(x1-x0,y1-y0)>400:raise ValueError('Eén vlak mag maximaal 400 mm groot zijn.')
    minimum=.01 if not obj.get('closed',True) or obj.get('fill') in LINE_FILLS+('zigzag',) else .3
    too_small=max(x1-x0,y1-y0)<minimum if not obj.get('closed',True) else min(x1-x0,y1-y0)<minimum
    if too_small:raise ValueError('Vlak is te smal om te vullen; kies een contourstiklijn.')

def raster_object(obj,angle=0,compensate=True):
    validate_object(obj)
    theta=math.radians(angle);c,s=math.cos(theta),math.sin(theta)
    def rotated(ring):
        return [(c*x+s*y,-s*x+c*y) for x,y in flattened(ring)]
    outer=rotated(obj['nodes']);a=np.asarray(outer);lo=np.floor(a.min(axis=0)*10)/10-1.2;hi=np.ceil(a.max(axis=0)*10)/10+1.2
    size=np.ceil((hi-lo)*10).astype(int)+1
    im=Image.new('L',tuple(size),0);d=ImageDraw.Draw(im)
    def pixels(points):return [(round((x-lo[0])*10),round((y-lo[1])*10)) for x,y in points]
    d.polygon(pixels(outer),fill=255)
    for hole in obj.get('holes',[]):d.polygon(pixels(rotated(hole)),fill=0)
    mask=np.asarray(im)>128
    radius=int(round(float(obj.get('compensation',0))*10)) if compensate else 0
    if radius:
        yy,xx=np.mgrid[-radius:radius+1,-radius:radius+1]
        mask=ndimage.binary_dilation(mask,structure=xx*xx+yy*yy<=radius*radius)
    # An overlap cut stays empty even after fabric pull compensation.
    if obj.get('overlap_exclusions'):
        excluded=Image.new('L',tuple(size),0);draw=ImageDraw.Draw(excluded)
        for piece in obj['overlap_exclusions']:
            local=Image.new('L',tuple(size),0);ld=ImageDraw.Draw(local)
            ld.polygon(pixels(rotated(piece['nodes'])),fill=255)
            for hole in piece.get('holes',[]):ld.polygon(pixels(rotated(hole)),fill=0)
            from PIL import ImageChops
            excluded=ImageChops.lighter(excluded,local)
        mask &= np.asarray(excluded)<128
    return mask,lo,(c,s)

def subdivide(points,limit,closed=False):
    if not points:return []
    out=[tuple(points[0])]
    route=list(points[1:])+([points[0]] if closed else [])
    for q in route:
        p=out[-1];n=max(1,math.ceil(math.dist(p,q)/limit))
        out.extend((p[0]+(q[0]-p[0])*k/n,p[1]+(q[1]-p[1])*k/n) for k in range(1,n+1))
    return out

def _object_tasks(obj):
    tasks=[];kind=obj.get('fill','fill');limit=min(float(obj['length']),4.8)
    if not obj.get('closed',True) and kind in ('satin','zigzag'):
        dense=flattened(obj['nodes'],False,step=.1);arr=np.asarray(dense);arc=np.r_[0,np.cumsum(np.linalg.norm(np.diff(arr,axis=0),axis=1))]
        if arc[-1]<=0:raise ValueError('De lijn heeft geen lengte.')
        steps=np.linspace(0,arc[-1],max(1,math.ceil(arc[-1]/max(.3,float(obj['spacing']))))+1)
        centres=np.column_stack([np.interp(steps,arc,arr[:,i]) for i in (0,1)]);points=[];half=min(4.8,float(obj['satin']))/2
        for i,q in enumerate(centres):
            tangent=centres[min(i+1,len(centres)-1)]-centres[max(0,i-1)];norm=np.linalg.norm(tangent)
            if norm==0:continue
            normal=np.array([-tangent[1],tangent[0]])/norm*half
            for v in (q+normal,q-normal) if kind=='satin' or i%2==0 else (q-normal,q+normal):points.append(tuple(v))
        tasks=[dict(points=subdivide(points,limit),layer='satin',closed=False,component=None)]
        if obj.get('fabric_underlay') and arc[-1]*float(obj['satin'])>=float(obj['fabric_underlay_area']):
            steps=np.linspace(0,arc[-1],max(1,math.ceil(arc[-1]/limit))+1);centre_points=list(zip(np.interp(steps,arc,arr[:,0]),np.interp(steps,arc,arr[:,1])));tasks.insert(0,dict(points=centre_points,layer='under',closed=False,component=None))
        return tasks
    if kind=='applique':return _applique_tasks(obj)
    if kind=='zigzag':kind='satin'
    if kind in LINE_FILLS:
        for ring in [obj['nodes']]+obj.get('holes',[]):
            dense=flattened(ring,closed=obj.get('closed',True),step=.1);arr=np.asarray(dense);arc=np.r_[0,np.cumsum(np.linalg.norm(np.diff(arr,axis=0),axis=1))]
            anchors=sorted(set([0.,float(arc[-1])]+[float(arc[int(np.argmin(np.linalg.norm(arr-np.array([n['x'],n['y']]),axis=1)))]) for n in ring if n.get('kind')!='smooth']))
            # Distribute stitches between corners instead of adding corner points
            # to a global grid (which caused pairs of almost coincident stitches).
            steps=np.unique(np.concatenate([np.linspace(a,b,max(1,math.ceil((b-a)/limit))+1) for a,b in zip(anchors,anchors[1:]) if b>a]))
            points=list(zip(np.interp(steps,arc,arr[:,0]),np.interp(steps,arc,arr[:,1])))
            if kind=='dash':
                for a,b in zip(points[::2],points[1::2]):tasks.append(dict(points=[a,b],layer='top',closed=False,no_connector=True))
                continue
            if kind=='triple':
                result=[points[0]]
                for a,b in zip(points,points[1:]):result.extend([b,a,b])
                points=result
            if kind=='double':points=points+list(reversed(points))[1:]
            tasks.append(dict(points=points,layer='top',closed=kind=='run' and obj.get('closed',True)))
        return tasks
    if kind=='column':return _column_tasks(obj)
    if len(obj.get('direction_guides') or [])>=2 and kind in ('fill','both','satin_fill'):return _guided_tasks(obj)
    angle=float(obj.get('angle',0));mask,lo,(c,s)=raster_object(obj,angle)
    if obj.get('start_hint') is not None:
        # Closest connection: begin where the previous part of this colour ended.
        X,Y=obj['start_hint'];obj=obj|{'_start_px':((c*X+s*Y-lo[0])*10,(-s*X+c*Y-lo[1])*10)}
    def world(points):return [(c*(x+lo[0])+(-s)*(y+lo[1]),s*(x+lo[0])+c*(y+lo[1])) for x,y in points]
    if kind in ('fill','both','satin_fill'):
        # Satin fill follows the chosen direction everywhere, also in thin strokes.
        wide,narrow=(mask,np.zeros_like(mask)) if kind=='satin_fill' else line_fill.split_narrow(mask,round(float(obj.get('narrow_mm',1.8))*5))
        # A mostly wide area keeps one stitch direction everywhere: thin necks
        # and tips are sewn with the same tatami rows. Only line work (mostly
        # thin) gets satin that follows the stroke.
        if kind!='satin_fill' and narrow.sum()<.5*mask.sum():wide,narrow=mask,np.zeros_like(mask)
        if narrow.any() or kind=='satin_fill':
            tasks=_split_tasks(obj,kind,mask,wide,narrow,world)
            if obj.get('fabric_underlay'):tasks=_fabric_underlay(obj)+tasks
            return tasks
    if kind in ('star4','star6','star8','star12','diamond','circle_pattern','chevron','flower_pattern'):
        cell=float(obj['spacing']);radius=cell*.35
        if mask.sum()/100/cell**2>3000:raise ValueError('Te veel motieven. Vergroot de patroonmaat of verklein het vlak.')
        for y in np.arange(cell/2,mask.shape[0]/10-cell/2,cell):
            for x in np.arange(cell/2,mask.shape[1]/10-cell/2,cell):
                if kind.startswith('star'):
                    points=[(x,y)]
                    for i in range(int(kind[4:])):
                        a=2*math.pi*i/int(kind[4:]);points.extend([(x+radius*math.cos(a),y+radius*math.sin(a)),(x,y)])
                elif kind=='diamond':points=[(x,y-radius),(x+radius,y),(x,y+radius),(x-radius,y),(x,y-radius)]
                elif kind=='chevron':points=[(x-radius,y-radius/2),(x,y+radius/2),(x+radius,y-radius/2)]
                else:
                    points=[]
                    for a in np.linspace(0,2*math.pi,49):
                        r=radius if kind=='circle_pattern' else radius*(.7+.3*math.cos(6*a));points.append((x+r*math.cos(a),y+r*math.sin(a)))
                check=subdivide(points,.1);xy=np.rint(np.asarray(check)*10).astype(int)
                if (xy>=0).all() and (xy[:,0]<mask.shape[1]).all() and (xy[:,1]<mask.shape[0]).all() and mask[xy[:,1],xy[:,0]].all():tasks.append(dict(points=world(subdivide(points,limit)),layer='top',closed=False,no_connector=True))
        if not tasks:raise ValueError('Geen volledig motief past in dit vlak. Verklein de patroonmaat of vergroot het vlak.')
        return tasks
    if kind=='cross':
        cell=float(obj['spacing']);half=cell/2
        if mask.sum()/100/cell**2*2>6000:raise ValueError('Te veel kruisdiagonalen. Vergroot Rijafstand / kruisvak (bijvoorbeeld 2 mm) of verklein het vlak.')
        for y in np.arange(half,mask.shape[0]/10-half,cell):
            for x in np.arange(half,mask.shape[1]/10-half,cell):
                # Whole diagonal must be inside: prevents crossing holes.
                diagonals=[[(x-half,y-half),(x+half,y+half)],[(x-half,y+half),(x+half,y-half)]]
                for diagonal in diagonals:
                    check=subdivide(diagonal,.1);xy=np.rint(np.array(check)*10).astype(int)
                    if (xy>=0).all() and (xy[:,0]<mask.shape[1]).all() and (xy[:,1]<mask.shape[0]).all() and mask[xy[:,1],xy[:,0]].all():
                        tasks.append(dict(points=world(subdivide(diagonal,limit)),layer='top',closed=False))
        return tasks
    rgba=np.zeros((*mask.shape,4),np.uint8);rgb=tuple(int(obj['color'][i:i+2],16) for i in (1,3,5));rgba[:,:,:3]=rgb;rgba[:,:,3]=mask*255
    # Keep the raster coordinate origin so separately drawn objects retain their positions.
    try:
        p=core.digitize(Image.fromarray(rgba),[rgb],width_mm=mask.shape[1]/10,spacing=min(1.5,float(obj['spacing'])),
            max_stitch=max(1,limit),underlay=obj.get('underlay',True),mode=kind,satin_width=float(obj['satin']),center_output=False,start=obj.get('_start_px'))
    except ValueError as e:
        if 'Geen steken gegenereerd' in str(e):
            return _object_tasks(obj|{'fill':'run'})
        raise
    for record in p.extras.get('route',[]):
        run=[]
        def finish_run():
            if run:tasks.append(dict(points=world(run),layer=record['layer'],closed=False,component=record['component'],fixed=record.get('fixed',False)))
        for x,y,cmd in p.stitches[record['start']:record['end']]:
            cmd &= emb.COMMAND_MASK
            if cmd==emb.STITCH:run.append((x/10+mask.shape[1]/20,y/10+mask.shape[0]/20))
            elif run:finish_run();run=[]
        finish_run()
    if obj.get('fabric_underlay'):
        tasks=_fabric_underlay(obj)+tasks
    return tasks

def _satin_px(obj):
    return 10*min(.6,max(.3,float(obj.get('spacing',.45))))

def _edge_px(obj):
    return .6+float(obj.get('compensation',0))*5

def _core_tasks(obj,mask,mode,world,component=None):
    """Tatami / contour satin from core on a raster mask (rotated object grid)."""
    tasks=[];limit=min(float(obj['length']),4.8)
    if not mask.any():return tasks
    rgba=np.zeros((*mask.shape,4),np.uint8);rgb=tuple(int(obj['color'][i:i+2],16) for i in (1,3,5));rgba[:,:,:3]=rgb;rgba[:,:,3]=mask*255
    try:
        p=core.digitize(Image.fromarray(rgba),[rgb],width_mm=mask.shape[1]/10,spacing=min(1.5,float(obj['spacing'])),
            max_stitch=max(1,limit),underlay=obj.get('underlay',True),mode=mode,satin_width=float(obj['satin']),center_output=False,start=obj.get('_start_px'))
    except ValueError as e:
        if 'Geen steken gegenereerd' in str(e) or 'geen zichtbare' in str(e).lower():return tasks
        raise
    for record in p.extras.get('route',[]):
        run=[]
        for x,y,cmd in p.stitches[record['start']:record['end']]+[(0,0,emb.END)]:
            cmd&=emb.COMMAND_MASK
            if cmd==emb.STITCH:run.append((x/10+mask.shape[1]/20,y/10+mask.shape[0]/20))
            elif run:
                tasks.append(dict(points=world(run),layer=record['layer'],closed=False,component=record['component'] if component is None else component,fixed=record.get('fixed',False)));run=[]
    return tasks

def _split_tasks(obj,kind,mask,wide,narrow,world):
    """Wide parts: tatami or satin fill. Thin strokes: satin that follows the stroke."""
    def mm(points):return world([(x/10,y/10) for x,y in points])
    tasks=[];limit=min(float(obj['length']),4.8)
    if kind=='satin_fill':
        if obj.get('underlay',True) and wide.sum()>1800:
            for rows in core._spans(ndimage.binary_erosion(wide,iterations=4),24):
                points=core._fill_points(rows,limit,0,0)
                if len(points)>1:tasks.append(dict(points=mm(points),layer='under',closed=False,component='satin_fill'))
        for points in line_fill.satin_rows(wide,_satin_px(obj)):
            tasks.append(dict(points=mm(points),layer='top',closed=False,component='satin_fill',max_stitch=line_fill.SATIN_MAX_MM))
    elif kind=='both':
        # The contour satin also covers thin strokes edge to edge.
        tasks+=_core_tasks(obj,wide,'fill',world,'all')
        tasks+=_core_tasks(obj,mask,'satin',world,'all')
        return tasks
    else:tasks+=_core_tasks(obj,wide,'fill',world)
    for points in line_fill.column_paths(narrow,_satin_px(obj),_edge_px(obj)):
        tasks.append(dict(points=mm(points),layer='top',closed=False,component='narrow',max_stitch=line_fill.SATIN_MAX_MM))
    if not tasks:return _object_tasks(obj|{'fill':'run'})
    return tasks

def _column_tasks(obj):
    mask,lo,_=raster_object(obj,0)
    guides=obj.get('direction_guides') or []
    direction_at=None
    if guides:
        # Each part of the line takes the stitch angle of the nearest arrow (measured along the line).
        labels=line_fill.geodesic_labels(mask,[((float(g['x'])-lo[0])*10,(float(g['y'])-lo[1])*10) for g in guides]) if len(guides)>1 else None
        angles=np.radians([float(g['angle']) for g in guides])
        def direction_at(q):
            if labels is None:return np.full(len(q),angles[0])
            xy=np.rint(q).astype(int);x=np.clip(xy[:,0],0,labels.shape[1]-1);y=np.clip(xy[:,1],0,labels.shape[0]-1)
            return angles[np.maximum(labels[y,x],0)]
    tasks=[dict(points=[(x/10+lo[0],y/10+lo[1]) for x,y in points],layer='top',closed=False,component='column',max_stitch=line_fill.SATIN_MAX_MM)
        for points in line_fill.column_paths(mask,_satin_px(obj),_edge_px(obj),direction_at=direction_at)]
    return tasks or _object_tasks(obj|{'fill':'run'})

def _mask_shapes(region):
    """Filled raster region to (outer, holes) rings in pixel coordinates."""
    import contourpy
    generator=contourpy.contour_generator(z=np.pad(region.astype(float),1),fill_type='OuterOffset')
    polygons,offsets=generator.filled(.5,1.5);out=[]
    for pp,oo in zip(polygons,offsets):
        rings=[]
        for start,end in zip(oo[:-1],oo[1:]):
            points=simplify_polyline(pp[start:end]-1,1.0)
            if len(points)>1 and np.linalg.norm(points[0]-points[-1])<.01:points=points[:-1]
            if len(points)>=3:rings.append(points)
        if rings:out.append((rings[0],rings[1:]))
    return out

def split_object(obj,line,gap_mm=.2,extend_mm=4):
    """Knife: cut a closed shape along a drawn line (mm points) into independent parts.
    The largest part keeps the id; every part keeps fill, colour and settings."""
    if not obj.get('closed',True):raise ValueError(f'{obj["name"]} is een open lijn; het mes werkt op vlakken.')
    pts=np.asarray(line,float)
    if len(pts)<2 or np.linalg.norm(pts[-1]-pts[0])<.2:raise ValueError('Trek een lijn met het mes over het vlak.')
    def unit(v):
        n=np.linalg.norm(v);return v/n if n>1e-9 else v
    # A stroke that stops just short of the edge still cuts through.
    start=unit(pts[0]-pts[min(3,len(pts)-1)]);end=unit(pts[-1]-pts[max(-4,-len(pts))])
    pts=np.vstack([pts[0]+start*extend_mm,pts,pts[-1]+end*extend_mm])
    mask,lo,_=raster_object(obj,0,compensate=False)
    cut=Image.new('L',mask.shape[::-1],0)
    ImageDraw.Draw(cut).line([((x-lo[0])*10,(y-lo[1])*10) for x,y in pts],fill=255,width=max(2,round(gap_mm*10)))
    rest=mask&~(np.asarray(cut)>0)
    labels,n=ndimage.label(rest)
    sizes=ndimage.sum(rest,labels,range(1,n+1)) if n else []
    parts=[k+1 for k in np.argsort(sizes)[::-1] if sizes[k]>=30]
    if len(parts)<2:raise ValueError(f'De lijn snijdt {obj["name"]} niet in twee delen. Trek de lijn helemaal over het vlak.')
    grow=max(1,round(gap_mm*10)//2+1);out=[]
    for k in parts:
        # Pieces reach back over the cut a little: no open seam in the embroidery.
        region=ndimage.binary_dilation(labels==k,iterations=grow)&mask
        for outer,holes in _mask_shapes(region):
            ring=lambda r:[dict(x=float(x/10+lo[0]),y=float(y/10+lo[1]),kind='corner') for x,y in r]
            piece=copy.deepcopy(obj);piece.update(nodes=ring(outer),holes=[ring(h) for h in holes],overlap_exclusions=[])
            for key in ('overlap_satin_source','entry_hint','exit_hint'):piece.pop(key,None)
            if out:piece['id']=uuid.uuid4().hex;piece['name']=f'{obj["name"]} deel {len(out)+1}'
            guides=[g for g in obj.get('direction_guides') or [] if point_inside(piece,g['x'],g['y'])]
            if obj.get('direction_guides') and not guides:
                x0,y0,x1,y1=object_bounds(piece);c=((x0+x1)/2,(y0+y1)/2)
                nearest=min(obj['direction_guides'],key=lambda g:math.dist(c,(g['x'],g['y'])))
                piece['angle']=float(nearest['angle']);guides=[] if obj['fill']!='column' else [dict(nearest)]
            piece['direction_guides']=guides if (len(guides)>1 or obj['fill']=='column') else []
            if len(guides)==1:piece['angle']=float(guides[0]['angle'])
            try:validate_object(piece)
            except ValueError:continue
            out.append(piece)
    if len(out)<2:raise ValueError(f'De lijn snijdt {obj["name"]} niet in twee bruikbare delen.')
    return out

def weld_objects(objs,gap_mm=.3):
    """Lassen: merge parts of one colour into one part wherever they touch or
    overlap (gaps up to gap_mm are closed). Parts that do not touch stay
    separate pieces. The largest part keeps its id and stitch settings."""
    objs=[o for o in objs if o.get('closed',True)]
    if len(objs)<2:raise ValueError('Kies twee of meer vlakken om te lassen.')
    if len({o['color'].lower() for o in objs})>1:raise ValueError('Lassen werkt op onderdelen in dezelfde garenkleur. Geef ze eerst dezelfde kleur.')
    rasters=[raster_object(o,0,compensate=False)[:2] for o in objs]
    lo=np.min([r[1] for r in rasters],axis=0);hi=np.max([r[1]+np.array(r[0].shape[::-1])/10 for r in rasters],axis=0)
    size=np.ceil((hi-lo)*10).astype(int)+2;union=np.zeros((size[1],size[0]),bool)
    for mask,origin in rasters:
        x,y=np.rint((origin-lo)*10).astype(int);union[y:y+mask.shape[0],x:x+mask.shape[1]]|=mask
    reach=max(1,round(gap_mm*10/2))
    joined=ndimage.binary_closing(np.pad(union,reach+1),iterations=reach)[reach+1:-reach-1,reach+1:-reach-1]|union
    areas=[m.sum() for m,_ in rasters];base=objs[int(np.argmax(areas))];out=[]
    labels,n=ndimage.label(joined)
    order=np.argsort(ndimage.sum(joined,labels,range(1,n+1)))[::-1] if n else []
    for k in order:
        region=labels==k+1
        if region.sum()<30:continue
        for outer,holes in _mask_shapes(region):
            ring=lambda r:[dict(x=float(x/10+lo[0]),y=float(y/10+lo[1]),kind='corner') for x,y in r]
            piece=copy.deepcopy(base);piece.update(nodes=ring(outer),holes=[ring(h) for h in holes],overlap_exclusions=[],direction_guides=[])
            for key in ('overlap_satin_source','entry_hint','exit_hint','group_id','group_name'):piece.pop(key,None)
            if out:piece['id']=uuid.uuid4().hex;piece['name']=f'{base["name"]} deel {len(out)+1}'
            try:validate_object(piece)
            except ValueError:continue
            out.append(piece)
    if not out:raise ValueError('Lassen gaf geen bruikbaar vlak.')
    return out

def _guided_tasks(obj):
    """Several direction arrows: each part of the shape takes the angle of the nearest arrow."""
    guides=obj['direction_guides'];kind=obj['fill']
    mask,lo,_=raster_object(obj,0)
    labels=line_fill.geodesic_labels(mask,[((float(g['x'])-lo[0])*10,(float(g['y'])-lo[1])*10) for g in guides])
    tasks=[]
    for k,g in enumerate(guides):
        region=labels==k
        if region.sum()<20:continue
        # Neighbouring parts overlap slightly so the seam never opens.
        region=ndimage.binary_dilation(region,iterations=3)&mask
        for outer,holes in _mask_shapes(region):
            nodes=lambda ring:[dict(x=float(x/10+lo[0]),y=float(y/10+lo[1]),kind='corner') for x,y in ring]
            sub=obj|dict(nodes=nodes(outer),holes=[nodes(h) for h in holes],angle=float(g['angle']),direction_guides=[],compensation=0,overlap_exclusions=[],
                fill='fill' if kind=='both' else kind,fabric_underlay=None)
            try:local=_object_tasks(sub)
            except ValueError:continue
            for t in local:t['component']='all' if kind=='both' else (k,str(t.get('component')))
            tasks+=local
    if kind=='both':
        band=_object_tasks(obj|dict(fill='satin',direction_guides=[],underlay=False,fabric_underlay=None))
        for t in band:t['component']='all'
        tasks+=band
    if obj.get('fabric_underlay'):tasks=_fabric_underlay(obj)+tasks
    return tasks or _object_tasks(obj|{'direction_guides':[]})

def _ring_loop(ring,step=.25):
    """A closed contour as an open corner polyline that returns to its start."""
    return [dict(x=float(x),y=float(y),kind='corner') for x,y in flattened(ring,True,step=step)]

def _offset_ring(ring,d):
    """Contour moved outward by d mm (for a hole: away from the hole, onto the fabric)."""
    if d<=0:return _ring_loop(ring)
    import contourpy
    pts=np.asarray(flattened(ring));lo=pts.min(axis=0)-d-1;size=np.ceil((pts.max(axis=0)+d+1-lo)*10).astype(int)+1
    im=Image.new('L',tuple(size),0);ImageDraw.Draw(im).polygon([((x-lo[0])*10,(y-lo[1])*10) for x,y in pts],fill=255)
    region=ndimage.distance_transform_edt(np.asarray(im)<128)<=d*10
    polygons,offsets=contourpy.contour_generator(z=np.pad(region.astype(float),1),fill_type='OuterOffset').filled(.5,1.5)
    best=max(((pp,oo) for pp,oo in zip(polygons,offsets)),key=lambda item:len(item[0]))
    outer=simplify_polyline(best[0][best[1][0]:best[1][1]]-1,.5)
    return [dict(x=float(x/10+lo[0]),y=float(y/10+lo[1]),kind='corner') for x,y in outer]

def _applique_tasks(obj):
    """Placement line, machine stop, tack-down, machine stop, satin cover.
    Every ring (outer contour and holes) gets all three stages. Stages are kept
    apart by the existing under/top/satin layer order of one object."""
    rings=[obj['nodes']]+obj.get('holes',[]);tasks=[]
    base={k:v for k,v in obj.items() if k not in ('overlap_exclusions','overlap_satin_source')}
    base.update(holes=[],fabric_underlay=None,underlay=False)
    cover=min(5.,max(1.,float(obj.get('satin',3))));tack=obj.get('applique_tack','zigzag')
    for index,ring in enumerate(rings):
        for t in _object_tasks(base|dict(nodes=ring,closed=True,fill='run')):
            t.update(layer='under',closed=False,no_connector=True,stop_before=None,thread_note='Applicatie 1/3: plaatsingslijn');tasks.append(t)
        # Around a hole the cover overlaps the cut edge by only 0.5 mm, so the
        # opening stays open; on the outer contour the satin straddles the edge.
        loop=_ring_loop(ring) if index==0 else _offset_ring(ring,max(0.,cover/2-.5))
        if index and tack!='zigzag':ring=[dict(n) for n in loop[:-1]]
        if tack=='zigzag':stage=_object_tasks(base|dict(nodes=loop,closed=False,fill='zigzag',satin=min(2.,cover*.6),spacing=1.6))
        else:stage=_object_tasks(base|dict(nodes=ring,closed=True,fill=tack if tack in ('run','double') else 'double'))
        for t in stage:t.update(layer='top',closed=False,no_connector=True,stop_before='applique_tack',thread_note='Applicatie 2/3: stof neerleggen en vastzetten');tasks.append(t)
        spacing=min(.6,max(.3,float(obj.get('spacing',.4))))
        for t in _object_tasks(base|dict(nodes=loop,closed=False,fill='satin',satin=cover,spacing=spacing)):
            t.update(layer='satin',closed=False,no_connector=True,stop_before='applique_cover',thread_note='Applicatie 3/3: stof bijknippen, daarna satijnrand');tasks.append(t)
    return tasks

def drop_short_stitches(p,min_mm,max_mm=4.8):
    """Remove interior stitch points closer than min_mm to the previous point.
    The first stitch after a jump, the last stitch before any command and every
    point whose removal would make a stitch longer than max_mm are kept."""
    if not min_mm or min_mm<=0:return 0
    st=p.stitches;owners=p.extras.get('owners');aligned=owners is not None and len(owners)==len(st)
    out=[];own=[];removed=0;last=None;previous=None
    for i,(x,y,c) in enumerate(st):
        cmd=c&emb.COMMAND_MASK
        if cmd==emb.STITCH and previous==emb.STITCH and last is not None and i+1<len(st):
            nx,ny,nc=st[i+1]
            if (nc&emb.COMMAND_MASK)==emb.STITCH and math.dist(last,(x,y))<min_mm*10 and math.dist(last,(nx,ny))<=max_mm*10:
                removed+=1;continue
        out.append([x,y,c])
        if aligned:own.append(owners[i])
        if cmd in (emb.STITCH,emb.JUMP):last=(x,y)
        previous=cmd
    p.stitches=out
    if aligned:p.extras['owners']=own
    p.extras['short_stitches_removed']=p.extras.get('short_stitches_removed',0)+removed
    return removed

def _bbox_overlap(a,b):
    aa=object_bounds(a);bb=object_bounds(b)
    pad=float(a.get('compensation',0))+float(b.get('compensation',0))
    return not (aa[2]+pad<bb[0] or bb[2]+pad<aa[0] or aa[3]+pad<bb[1] or bb[3]+pad<aa[1])

def _objects_overlap(a,b,cache):
    if not _bbox_overlap(a,b):return False
    if not a.get('closed',True) or not b.get('closed',True):return True
    for obj in (a,b):
        if obj['id'] not in cache:cache[obj['id']]=raster_object(obj)[:2]
    am,ao=cache[a['id']];bm,bo=cache[b['id']]
    lo=np.maximum(ao,bo);hi=np.minimum(ao+(np.array(am.shape[::-1])-1)/10,bo+(np.array(bm.shape[::-1])-1)/10)
    size=np.floor((hi-lo)*10+.001).astype(int)+1
    if (size<=0).any():return False
    aa=np.rint((lo-ao)*10).astype(int);bb=np.rint((lo-bo)*10).astype(int);w,h=size
    left=am[aa[1]:aa[1]+h,aa[0]:aa[0]+w];right=bm[bb[1]:bb[1]+h,bb[0]:bb[0]+w]
    return bool(np.any(left & right))

def _objects_cover(a,b,cache):
    """True when one part really lies on top of the other.

    Parts traced from one picture (magic wand) only touch along their edges;
    with fill allowance they overlap by a hair. That seam must not fix the
    sewing order, otherwise colours alternate in click order."""
    if not _bbox_overlap(a,b):return False
    if not a.get('closed',True) or not b.get('closed',True):return _objects_overlap(a,b,cache)
    key='cover'
    for obj in (a,b):
        if (key,obj['id']) not in cache:
            mask,lo,_=raster_object(obj,compensate=False)
            cache[(key,obj['id'])]=(ndimage.binary_erosion(mask,iterations=2),lo,int(mask.sum()))
    am,ao,aa_=cache[(key,a['id'])];bm,bo,ba_=cache[(key,b['id'])]
    lo=np.maximum(ao,bo);hi=np.minimum(ao+(np.array(am.shape[::-1])-1)/10,bo+(np.array(bm.shape[::-1])-1)/10)
    size=np.floor((hi-lo)*10+.001).astype(int)+1
    if (size<=0).any():return False
    pa=np.rint((lo-ao)*10).astype(int);pb=np.rint((lo-bo)*10).astype(int);w,h=size
    shared=int(np.count_nonzero(am[pa[1]:pa[1]+h,pa[0]:pa[0]+w]&bm[pb[1]:pb[1]+h,pb[0]:pb[0]+w]))
    return shared>=max(4,.03*min(aa_,ba_))

def _hex_rgb(colour):
    return [int(colour[i:i+2],16) for i in (1,3,5)]

def matching_colour(colour,existing,separation=12.):
    """An existing thread colour that looks the same as `colour` (CIE Lab
    distance below `separation`), else None."""
    import core
    existing=[c for c in dict.fromkeys(existing) if c]
    if not existing:return None
    lab=core.to_lab(np.array([_hex_rgb(colour)]+[_hex_rgb(c) for c in existing],np.float32))
    d=np.sqrt(((lab[1:]-lab[0])**2).sum(axis=1));i=int(np.argmin(d))
    return existing[i] if d[i]<separation else None

def _area(obj):
    pts=np.asarray(flattened(obj['nodes'],obj.get('closed',True)) or [(0,0)],float)
    if len(pts)<3:return 1.
    x,y=pts[:,0],pts[:,1];return abs(float(np.dot(x,np.roll(y,1))-np.dot(y,np.roll(x,1))))/2+1.

def unify_colours(objects,separation=12.):
    """Give parts that only differ by an invisible tint (e.g. each toverstaf
    click averages slightly different pixels) one and the same thread colour,
    so they are sewn in one colour block. The colour covering the largest
    area wins. Returns the number of parts that changed colour."""
    area={}
    for obj in objects:area[obj['color']]=area.get(obj['color'],0.)+_area(obj)
    chosen={}
    for colour in sorted(area,key=lambda c:-area[c]):
        chosen[colour]=matching_colour(colour,list(dict.fromkeys(chosen.values())),separation) or colour
    changed=0
    for obj in objects:
        if chosen[obj['color']]!=obj['color']:obj['color']=chosen[obj['color']];changed+=1
    return changed

def _lightness(colour):
    r,g,b=(int(colour[i:i+2],16) for i in (1,3,5));return .299*r+.587*g+.114*b

def _colour_tours(objects):
    """Per thread colour a short open tour through its parts (nearest
    neighbour + 2-opt on edge-to-edge distances): {object index: rank}."""
    by_colour={}
    for i,obj in enumerate(objects):by_colour.setdefault(obj['color'],[]).append(i)
    rank={};size={}
    for colour,members in by_colour.items():
        n=len(members);size[colour]=n
        if n<3:
            for k,i in enumerate(members):rank[i]=k
            continue
        from scipy.spatial import cKDTree
        rings=[np.asarray(flattened(objects[i]['nodes'],objects[i].get('closed',True),step=.5)) for i in members]
        trees=[cKDTree(r) for r in rings];centre=np.array([r.mean(axis=0) for r in rings])
        d=np.zeros((n,n))
        for a in range(n):
            for b in range(a+1,n):
                small,big=(a,b) if len(rings[a])<len(rings[b]) else (b,a)
                d[a,b]=d[b,a]=float(trees[big].query(rings[small])[0].min())
        def length(t):return float(sum(d[a,b] for a,b in zip(t,t[1:])))
        best=None
        for start in range(n) if n<=60 else np.argsort(centre[:,0])[:: max(1,n//40)]:
            tour=[int(start)];left=set(range(n))-{int(start)}
            while left:
                nxt=min(left,key=lambda j:d[tour[-1],j]);tour.append(nxt);left.remove(nxt)
            if best is None or length(tour)<length(best):best=tour
        improved=True;rounds=0
        while improved and rounds<50:
            improved=False;rounds+=1
            for a in range(n-2):
                for b in range(a+2,n):
                    before=d[best[a],best[a+1]]+(d[best[b],best[b+1]] if b+1<n else 0)
                    after=d[best[a],best[b]]+(d[best[a+1],best[b+1]] if b+1<n else 0)
                    if after<before-1e-9:best[a+1:b+1]=best[a+1:b+1][::-1];improved=True
        for k,j in enumerate(best):rank[members[j]]=k
    return rank,size

def logical_objects(objects):
    objects=copy.deepcopy(objects);groups={};order=[]
    for obj in objects:
        if obj.get('text_group') and not obj.get('letter_id'):
            match=re.match(r'Letter (\d+):',obj.get('name',''))
            if match:obj['letter_id']=obj['text_group']+':'+match.group(1)
        unit=obj.get('letter_id',obj['id'])
        if unit not in groups:groups[unit]=[];order.append(unit)
        groups[unit].append(obj)
    out=[]
    for unit in order:
        members=groups[unit]
        if members[0].get('letter_id') and len(members)>1:
            # Largest piece is normally the stem/body; disconnected smaller
            # pieces (dots, accents) are completed before the covering body.
            areas=[]
            for obj in members:
                def area(ring):
                    pts=flattened(ring);return abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(pts,pts[1:])))/2
                areas.append(area(obj['nodes'])-sum(area(h) for h in obj.get('holes',[])))
            body=max(range(len(members)),key=lambda i:areas[i]);members=[o for i,o in enumerate(members) if i!=body]+[members[body]]
            for obj in members[:-1]:
                obj['letter_part']='dot_or_accent'
                if obj['fill'] in ('satin','both'):obj['fill']='satin'
            members[-1]['letter_part']='body'
        out.extend(members)
    return out

def _safe_segment(mask,lo,a,b):
    points=subdivide([a,b],.1);xy=np.rint((np.asarray(points)-lo)*10).astype(int)
    return bool((xy>=0).all() and (xy[:,0]<mask.shape[1]).all() and (xy[:,1]<mask.shape[0]).all() and mask[xy[:,1],xy[:,0]].all())

def _fabric_underlay(obj):
    mask,lo,_=raster_object(obj,compensate=False)
    if mask.sum()/100<float(obj['fabric_underlay_area']):return []
    tasks=[]
    # Light running outline, keeping corners and holes; these stay underneath
    # the compensated top contour. Every underlay belongs to this same object.
    edge=obj|{'fill':'run','fabric_underlay':None,'underlay':False}
    for task in _object_tasks(edge):task.update(layer='under',component=None);tasks.append(task)
    if obj['fabric_underlay']=='edge_fill':
        mask=ndimage.binary_erosion(mask,iterations=1)
        for rows in core._spans(mask,float(obj['fabric_underlay_spacing'])*10):
            points=[(x/10+lo[0],y/10+lo[1]) for x,y in core._fill_points(rows,min(obj['length'],4.8),0,0)]
            run=[]
            for q in points:
                if run and not _safe_segment(mask,lo,run[-1],q):
                    if len(run)>1:tasks.append(dict(points=run,layer='under',closed=False,component=None))
                    run=[]
                run.append(q)
            if len(run)>1:tasks.append(dict(points=run,layer='under',closed=False,component=None))
    return tasks

def _join_mask(obj):
    """Object raster, padded so endpoints just over the edge stay on the grid."""
    mask,lo,_=raster_object(obj);pad=4
    return np.pad(mask,pad),np.asarray(lo)-pad/10

def _join_path(mask,lo,a,b):
    """Connector inside the object. Fill rows end up to 0.2 mm over the
    outline, so only a small disc around both endpoints may lie outside."""
    from continuous_route import inside_path
    a=(np.asarray(a)-lo)*10;b=(np.asarray(b)-lo)*10;mask=mask.copy();h,w=mask.shape
    yy,xx=np.ogrid[:h,:w]
    for q in (a,b):mask|=(xx-q[0])**2+(yy-q[1])**2<=9
    path=inside_path(mask,a,b)
    return None if path is None else [tuple(np.asarray(q)/10+lo) for q in path]

def digitize_objects(objects,progress=None,optimize=True,min_jump=1.5,manual_order=False,fabric_key=None,min_stitch=0):
    """Greedy same-colour routing, respecting overlapping object order and local underlay.
    Running/cross tasks may reverse; generated fills preserve their local layer sequence.
    """
    objects=logical_objects([o for o in objects if o.get('visible',True)])
    if fabric_key:objects=fabric.apply(objects,fabric_key)
    if not objects:raise ValueError('Teken of importeer eerst een vlak.')
    tasks=[];deps={};remaining={}
    # Plan: lightest colour first, each colour along a short tour; every part
    # starts where the previous one ended (closest connection).
    tour_rank,tour_size=_colour_tours(objects)
    # Walk each colour's tour from the end nearest to where the previous colour
    # stopped (the needle starts in the middle of the hoop).
    def centre(i):
        b=object_bounds(objects[i]);return ((b[0]+b[2])/2,(b[1]+b[3])/2)
    reference=(0.,0.)
    for colour in sorted(tour_size,key=lambda c:-_lightness(c)):
        members=sorted((i for i in tour_rank if objects[i]['color']==colour),key=lambda i:tour_rank[i])
        if math.dist(reference,centre(members[-1]))<math.dist(reference,centre(members[0])):
            for k,i in enumerate(reversed(members)):tour_rank[i]=k
            members.reverse()
        reference=centre(members[-1])
    plan=list(range(len(objects)))
    if optimize and not manual_order:plan.sort(key=lambda i:(-_lightness(objects[i]['color']),objects[i]['color'],tour_rank[i]))
    previous_end=None
    for step,i in enumerate(plan):
        obj=objects[i]
        if previous_end is not None and optimize and not manual_order and not obj.get('entry_hint'):obj=obj|{'start_hint':previous_end}
        if progress:progress(int(step*55/len(objects)),f'Steken voor {obj["name"]}')
        local=_object_tasks(obj|{'overlap_exclusions':[]} if obj.get('overlap_exclusions') and obj.get('fill') in ('satin','zigzag') else obj)
        if obj.get('overlap_satin_source') and obj.get('fill')=='both':
            source=obj|obj['overlap_satin_source']|dict(fill='satin',underlay=False,fabric_underlay=None,overlap_exclusions=[])
            border=[t for t in _object_tasks(source) if t['layer']=='satin']
            # Each split keeps only its own section of the old outline.
            if obj.get('overlap_exclusions'):
                from overlap_ui import clip_overlap_tasks
                border=clip_overlap_tasks(border,obj)
            mask,lo,_=raster_object(obj)
            def belongs(t):
                return any(_safe_segment(mask,lo,q,q) for q in t['points'])
            local=[t for t in local if t['layer']!='satin']+[t for t in border if belongs(t)]
        if obj.get('overlap_exclusions'):
            from overlap_ui import clip_overlap_tasks
            local=clip_overlap_tasks(local,obj)
        deps[i]=set()
        remaining[i]=len(local)
        for task in local:task.update(object=i,color=obj['color'],id=obj['id']);tasks.append(task)
        if local:previous_end=tuple(local[-1]['points'][-1])
    # Explicit point/line phases override layer order only where the shapes
    # overlap. Uniform unit ranks keep a whole letter from getting deadlocked
    # on another letter's body/point dependency.
    units={}
    for i,obj in enumerate(objects):units.setdefault(obj.get('letter_id',obj['id']),[]).append(i)
    unit_phase={key:min(int(objects[i].get('stitch_phase',1)) for i in members) for key,members in units.items()}
    overlap_cache={}
    for i,obj in enumerate(objects):
        a=obj.get('letter_id',obj['id'])
        for j in range(i):
            if not _objects_cover(obj,objects[j],overlap_cache):continue
            b=objects[j].get('letter_id',objects[j]['id'])
            if not manual_order and a!=b and unit_phase[a]<unit_phase[b]:deps[j].add(i)
            else:deps[i].add(j)
    unit_dependencies={key:set() for key in units}
    for i,required in deps.items():
        a=objects[i].get('letter_id',objects[i]['id'])
        for j in required:
            b=objects[j].get('letter_id',objects[j]['id'])
            if a!=b:unit_dependencies[a].add(b)
    # Non-sewing objects cannot hold dependencies forever.
    done={i for i,n in remaining.items() if not n};p=emb.EmbPattern();last=(0.,0.);color=None;owners=[];audit=[]
    under_pending={};fill_pending={}
    for t in tasks:
        key=(t['object'],t.get('component'))
        if t['layer']=='under':under_pending[key]=under_pending.get(key,0)+1
        if t['layer'] in ('under','top'):fill_pending[key]=fill_pending.get(key,0)+1
    initial_remaining=remaining.copy()
    stops_done=set()
    active_unit=None;last_object=None;join_masks={};done_units={key for key,members in units.items() if all(i in done for i in members)}
    tour_reverse={colour:False for colour in tour_size}
    def tour_position(i):
        colour=objects[i]['color'];k=tour_rank[i]
        return tour_size[colour]-1-k if tour_reverse.get(colour) else k
    while tasks:
        available=[];first_in_unit={};stage_records={}
        for u in tasks:
            unit=objects[u['object']].get('letter_id',objects[u['object']]['id']);first_in_unit[unit]=min(first_in_unit.get(unit,u['object']),u['object']);stage_records.setdefault((u['object'],u['layer']),[]).append(u)
        earliest_object=min(u['object'] for u in tasks)
        for n,t in enumerate(tasks):
            i=t['object'];unit=objects[i].get('letter_id',objects[i]['id'])
            if active_unit is not None and unit!=active_unit:continue
            if active_unit is None and not unit_dependencies[unit]<=done_units:continue
            if first_in_unit[unit]!=i:continue
            if not deps[i]<=done:continue
            if t['layer']=='top' and (under_pending.get((i,t.get('component')),0) or (i,'under') in stage_records):continue
            if t['layer']=='satin' and (fill_pending.get((i,t.get('component')),0) or (i,'under') in stage_records):continue
            if (manual_order or not optimize) and earliest_object<i:continue
            obj=objects[i];exit_hint=obj.get('exit_hint')
            same_stage=stage_records[(i,t['layer'])]
            ends_near=exit_hint is not None and min(math.dist(exit_hint,t['points'][0]),math.dist(exit_hint,t['points'][-1]))<.15
            if ends_near and len(same_stage)>1 and any(min(math.dist(exit_hint,u['points'][0]),math.dist(exit_hint,u['points'][-1]))>=.15 for u in same_stage):continue
            hint=obj.get('entry_hint') if remaining[i]==initial_remaining[i] else None
            reference=tuple(hint) if hint is not None else last
            pts=t['points'];d0=math.dist(reference,pts[0]);d1=math.dist(reference,pts[-1]);reverse=d1<d0 and not t.get('fixed')
            if obj.get('route_reversed') and hint is None:reverse=True
            if exit_hint is not None and len(same_stage)==1 and hint is None:reverse=math.dist(exit_hint,pts[0])<math.dist(exit_hint,pts[-1])
            entry=0;distance=d1 if reverse else d0
            if t.get('closed'):
                entry=min(range(len(pts)),key=lambda k:math.dist(reference,pts[k]));distance=math.dist(reference,pts[entry]);reverse=False
            if hint is not None:
                # Pick the preferred entry task inside this object, independent
                # of global unit choice; actual distance remains the travel cost.
                legal_hint=distance
            else:legal_hint=0
            actual_entry=pts[entry] if t.get('closed') else pts[-1] if reverse else pts[0]
            if t['color']==color:priority=(0,0,tour_position(i))
            else:
                # New colour: lightest first, starting at an end of its tour.
                priority=(1,-_lightness(t['color']),tour_rank[i])
            available.append((priority,math.dist(last,actual_entry),n,reverse,entry,legal_hint if hint is not None else None,i))
        if not available:raise ValueError('Vlakvolgorde kon niet worden bepaald.')
        preferred={}
        for candidate in available:
            if candidate[5] is not None:preferred[candidate[6]]=min(preferred.get(candidate[6],float('inf')),candidate[5])
        available=[candidate for candidate in available if candidate[5] is None or candidate[5]<=preferred[candidate[6]]+1e-6]
        _,distance,n,reverse,entry=(min(available) if optimize else min(available,key=lambda x:x[2]))[:5]
        t=tasks.pop(n);pts=t['points'];active_unit=objects[t['object']].get('letter_id',objects[t['object']]['id'])
        if t.get('closed'):
            pts=pts[entry:]+pts[:entry]+[pts[entry]]
            if objects[t['object']].get('route_reversed'):pts=list(reversed(pts))
        elif reverse:pts=list(reversed(pts))
        distance=math.dist(last,pts[0])
        def add(cmd,q):p.add_stitch_absolute(cmd,q[0]*10,q[1]*10);owners.append(t['id'])
        stop=t.get('stop_before') and (t['object'],t['stop_before']) not in stops_done
        if t.get('stop_before'):stops_done.add((t['object'],t['stop_before']))
        # A machine stop is an extra colour change with the same thread colour.
        colour_changed=color!=t['color'] or bool(stop and color is not None)
        if colour_changed:
            if color is not None:add(emb.TRIM,last);add(emb.COLOR_CHANGE,last)
            name=objects[t['object']]['name'];note=t.get('thread_note')
            p.add_thread({'color':t['color'],'description':f'{name} — {note}' if note else name});color=t['color']
        connector=None
        obj=objects[t['object']]
        if last_object==t['id'] and not colour_changed and p.stitches and obj.get('closed',True) and not t.get('no_connector'):
            if obj['id'] not in join_masks:join_masks[obj['id']]=_join_mask(obj)
            mask,lo=join_masks[obj['id']];connector=_join_path(mask,lo,last,pts[0])
        # Adjacent pieces of the same dense fill can sew through their union.
        # Never bridge an empty gap or patterned/open area.
        if connector is None and last_object and last_object!=t['id'] and not colour_changed and obj.get('fill') in ('fill','both'):
            previous=next(o for o in objects if o['id']==last_object)
            if previous.get('fill') in ('fill','both') and previous.get('closed',True) and obj.get('closed',True):
                masks=[]
                for member in (previous,obj):
                    if member['id'] not in join_masks:join_masks[member['id']]=_join_mask(member)
                    masks.append(join_masks[member['id']])
                lo=np.minimum(masks[0][1],masks[1][1]);hi=np.maximum(*[origin+np.asarray(mask.shape[::-1])/10 for mask,origin in masks])
                size=np.ceil((hi-lo)*10).astype(int);union=np.zeros((size[1],size[0]),bool)
                for mask,origin in masks:
                    x,y=np.rint((origin-lo)*10).astype(int);union[y:y+mask.shape[0],x:x+mask.shape[1]]|=mask
                connector=_join_path(union,lo,last,pts[0])
        if connector is not None and (obj.get('overlap_exclusions') or (last_object and next((o for o in objects if o['id']==last_object),{}).get('overlap_exclusions'))):
            # Never travel through (or along) an area cut away for a newer part.
            from overlap_ui import exclusion_path
            from PySide6.QtCore import QPointF
            cuts=[exclusion_path(o) for o in objects if o['id'] in (obj['id'],last_object) and o.get('overlap_exclusions')]
            if any(cut.contains(QPointF(x*10,y*10)) for cut in cuts for x,y in subdivide(connector,.05)):connector=None
        join=connector is not None
        connector_length=0
        if join:
            connector_length=sum(math.dist(a,b) for a,b in zip(connector,connector[1:]))
            for q in subdivide(connector,min(float(obj['length']),4.8))[1:]:add(emb.STITCH,q)
        else:
            if p.stitches and not colour_changed and distance>min_jump:add(emb.TRIM,last)
            add(emb.JUMP,pts[0]);add(emb.STITCH,pts[0])
        limit=t.get('max_stitch') or min(float(objects[t['object']]['length']),4.8)
        for q in subdivide(pts,limit)[1:]:add(emb.STITCH,q)
        last=pts[-1];remaining[t['object']]-=1
        key=(t['object'],t.get('component'))
        if t['layer']=='under':under_pending[key]-=1
        if t['layer'] in ('under','top'):fill_pending[key]-=1
        if remaining[t['object']]==0:done.add(t['object'])
        audit.append(dict(object=t['id'],unit=active_unit,color=color,jump_mm=0 if join else distance,connector_mm=connector_length if join else 0,layer=t['layer']))
        last_object=t['id']
        if not any(objects[u['object']].get('letter_id',objects[u['object']]['id'])==active_unit for u in tasks):done_units.add(active_unit);active_unit=None
        if len(p.stitches)>250000:raise ValueError('Meer dan 250.000 steken. Vergroot de rijafstand of vereenvoudig.')
    if not any(s[2]==emb.STITCH for s in p.stitches):raise ValueError('Geen steken gegenereerd; controleer de vlakgrootte.')
    p.add_stitch_absolute(emb.END,last[0]*10,last[1]*10);owners.append(None);p.extras.update(owners=owners,route=audit,routing_version='2.5',fabric_profile=fabric_key)
    if min_stitch:drop_short_stitches(p,min_stitch)
    p.extras['generated_fingerprint']=fabric.fingerprint(p)
    if progress:progress(100,'Borduurpatroon klaar')
    return p

def point_inside(obj,x,y):
    if not obj.get('closed',True):
        points=flattened(obj['nodes'],False)
        return any(math.dist((x,y),q)<1 for q in points)
    def ring_contains(nodes):
        polygon=flattened(nodes,step=.4);inside=False
        for (a,b),(c,d) in zip(polygon,polygon[1:]):
            if (b>y)!=(d>y) and x<(c-a)*(y-b)/(d-b)+a:inside=not inside
        return inside
    return ring_contains(obj['nodes']) and not any(ring_contains(h) for h in obj.get('holes',[]))

def merge_similar_colors(image,tolerance=12):
    a=np.array(image.convert('RGBA'));visible=a[:,:,3]>128
    colors,counts=np.unique(a[:,:,:3][visible],axis=0,return_counts=True)
    chosen=[]
    for i in np.argsort(-counts):
        color=colors[i];nearest=min(chosen,key=lambda c:np.linalg.norm(color.astype(float)-c),default=None)
        if nearest is not None and np.linalg.norm(color.astype(float)-nearest)<=tolerance:
            mask=visible&np.all(a[:,:,:3]==color,axis=2);a[mask,:3]=nearest
        else:chosen.append(color)
    return Image.fromarray(a)

def clean_art(image,min_area_mm2,width_mm,smooth_mm=.1,color_tolerance=0):
    """Remove tiny disconnected colour fragments; preserve significant holes."""
    image=merge_similar_colors(image,color_tolerance) if color_tolerance else image
    a=np.array(image.convert('RGBA'));scale=a.shape[1]/float(width_mm);result=a.copy();visible=a[:,:,3]>128
    colors=np.unique(a[:,:,:3][visible],axis=0)
    if len(colors)>24:raise ValueError('Vereenvoudig eerst de kleuren.')
    # Smooth label boundaries using a majority filter. Transparent perimeter remains transparent.
    radius=max(0,round(smooth_mm*scale));labels=np.full(a.shape[:2],-1,int)
    for i,color in enumerate(colors):labels[visible&np.all(a[:,:,:3]==color,axis=2)]=i
    if radius:labels=ndimage.median_filter(labels,size=min(7,2*radius+1));labels[~visible]=-1
    for i,color in enumerate(colors):
        mask=labels==i;lab,n=ndimage.label(mask);counts=np.bincount(lab.ravel());small=np.where(counts<min_area_mm2*scale*scale)[0];small=small[small!=0]
        labels[np.isin(lab,small)]=-1
    result[:,:,3]=(labels>=0)*255
    for i,color in enumerate(colors):result[labels==i,:3]=color
    return Image.fromarray(result),[tuple(map(int,c)) for i,c in enumerate(colors) if np.any(labels==i)]

def objects_from_art(image,width_mm,min_area_mm2=.1):
    import contourpy
    a=np.array(image.convert('RGBA'));h,w=a.shape[:2];scale=width_mm/w;out=[]
    for col in np.unique(a[:,:,:3][a[:,:,3]>128],axis=0):
        mask=(a[:,:,3]>128)&np.all(a[:,:,:3]==col,axis=2)
        lab,n=ndimage.label(mask)
        for j,sl in enumerate(ndimage.find_objects(lab),1):
            if sl is None:continue
            region=lab[sl]==j
            if region.sum()*scale**2<min_area_mm2:continue
            generator=contourpy.contour_generator(z=np.pad(region.astype(float),1),fill_type='OuterOffset')
            polygons,offsets=generator.filled(.5,1.5)
            for pp,oo in zip(polygons,offsets):
                rings=[]
                for start,end in zip(oo[:-1],oo[1:]):
                    points=pp[start:end]-1
                    # Ramer–Douglas–Peucker removes raster stair steps, to 0.12 mm.
                    points=simplify_polyline(points,.12/scale)
                    if len(points)>1 and np.linalg.norm(points[0]-points[-1])<.01:points=points[:-1]
                    nodes=[dict(x=float((x+sl[1].start-w/2)*scale),y=float((y+sl[0].start-h/2)*scale),kind='corner') for x,y in points]
                    if len(nodes)>=3:rings.append(nodes)
                if rings:
                    obj=new_object(rings[0],'#%02x%02x%02x'%tuple(col),f'Vlak {len(out)+1}');obj['holes']=rings[1:]
                    bounds=object_bounds(obj)
                    if min(bounds[2]-bounds[0],bounds[3]-bounds[1])<.5:obj['fill']='run'
                    out.append(obj)
                    if len(out)>600:raise ValueError('Meer dan 600 vlakken. Vereenvoudig of verhoog de minimale detailgrootte.')
    return out

def simplify_polyline(points,epsilon):
    points=np.asarray(points)
    if len(points)<3:return points
    # Closed rings split at a far vertex so the baseline has nonzero length.
    if np.linalg.norm(points[0]-points[-1])<1e-8:
        mid=int(np.argmax(np.linalg.norm(points-points[0],axis=1)))
        return np.vstack([simplify_polyline(points[:mid+1],epsilon)[:-1],simplify_polyline(points[mid:],epsilon)])
    vector=points[-1]-points[0];norm=np.linalg.norm(vector)
    distance=np.abs(vector[0]*(points[:,1]-points[0,1])-vector[1]*(points[:,0]-points[0,0]))/max(norm,1e-9)
    index=int(np.argmax(distance))
    if distance[index]<=epsilon:return points[[0,-1]]
    return np.vstack([simplify_polyline(points[:index+1],epsilon)[:-1],simplify_polyline(points[index:],epsilon)])

def transform_object(obj,dx=0,dy=0,scale=1,angle=0,center=(0,0)):
    c,s=math.cos(math.radians(angle)),math.sin(math.radians(angle));cx,cy=center
    for key in ('entry_hint','exit_hint'):
        if obj.get(key) is not None:
            x,y=(obj[key][0]-cx)*scale,(obj[key][1]-cy)*scale;obj[key]=[cx+c*x-s*y+dx,cy+s*x+c*y+dy]
    for ring in object_edit_rings(obj):
        for node in ring:
            x,y=(node['x']-cx)*scale,(node['y']-cy)*scale
            node['x']=cx+c*x-s*y+dx;node['y']=cy+s*x+c*y+dy
    for guide in obj.get('direction_guides') or []:
        x,y=(guide['x']-cx)*scale,(guide['y']-cy)*scale
        guide['x']=cx+c*x-s*y+dx;guide['y']=cy+s*x+c*y+dy;guide['angle']=(float(guide['angle'])+angle+180)%360-180

def object_edit_rings(obj):
    rings=[obj['nodes']]+obj.get('holes',[])
    for piece in obj.get('overlap_exclusions',[]):rings+= [piece['nodes']]+piece.get('holes',[])
    if obj.get('overlap_satin_source'):
        source=obj['overlap_satin_source'];rings += [source['nodes']]+source.get('holes',[])
    return rings

def objects_svg(objects,path):
    if not objects:raise ValueError('Er zijn geen vlakken.')
    boxes=[object_bounds(o) for o in objects if o.get('visible',True)]
    x0=min(b[0] for b in boxes);y0=min(b[1] for b in boxes);x1=max(b[2] for b in boxes);y1=max(b[3] for b in boxes)
    lines=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{x1-x0:.3f}mm" height="{y1-y0:.3f}mm" viewBox="{x0:.3f} {y0:.3f} {x1-x0:.3f} {y1-y0:.3f}">']
    for obj in objects:
        if not obj.get('visible',True):continue
        commands=[]
        for ring in [obj['nodes']]+obj.get('holes',[]):
            commands.append(f'M {ring[0]["x"]:.4f} {ring[0]["y"]:.4f}')
            for p,a,b,q,curved in segments(ring,obj.get('closed',True)):
                commands.append(f'C {a[0]:.4f} {a[1]:.4f} {b[0]:.4f} {b[1]:.4f} {q[0]:.4f} {q[1]:.4f}' if curved else f'L {q[0]:.4f} {q[1]:.4f}')
            if obj.get('closed',True):commands.append('Z')
        appearance=f'fill="{html.escape(obj["color"])}"' if obj.get('closed',True) else f'fill="none" stroke="{html.escape(obj["color"])}" stroke-width="0.3"'
        lines.append(f'<path {appearance} fill-rule="evenodd" d="{" ".join(commands)}"><title>{html.escape(obj["name"])}</title></path>')
    lines.append('</svg>');Path(path).write_text('\n'.join(lines),encoding='utf-8')

def outside_indices(pattern,width,height,oval,margin):
    rx=width/2-margin;ry=height/2-margin
    return [i for i,(x,y,c) in enumerate(pattern.stitches) if (c&emb.COMMAND_MASK) in (emb.STITCH,emb.JUMP) and
        (rx<=0 or ry<=0 or abs(x/10)>rx+.001 or abs(y/10)>ry+.001 or (oval and (x/10/rx)**2+(y/10/ry)**2>1.00001))]

def route_metrics(pattern):
    last=(0,0);total=0;count=0;longest=0
    for x,y,c in pattern.stitches:
        cmd=c&emb.COMMAND_MASK
        if cmd==emb.JUMP:
            length=math.dist(last,(x,y))/10;total+=length;count+=int(length>.1);longest=max(longest,length)
        if cmd in (emb.STITCH,emb.JUMP):last=(x,y)
    return dict(jumps=count,travel=total,longest=longest)
