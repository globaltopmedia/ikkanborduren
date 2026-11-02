"""Editable offset outlines around selected objects or a complete design."""
import math
import numpy as np
from scipy import ndimage
import contourpy
import design

def make_outlines(objects,kind='satin',width=2,spacing=.4,distance=0,length=2.5,color='#159552'):
    if kind not in ('satin','run'):raise ValueError('Kies satijn of stiksteken.')
    if not .5<=width<=5 or not .3<=spacing<=1.5 or not .5<=length<=5 or not 0<=distance<=10:raise ValueError('Ongeldige contourinstelling.')
    objects=[o for o in objects if o.get('visible',True) and o.get('closed',True)]
    if not objects:raise ValueError('Selecteer minstens één gesloten vlak.')
    masks=[design.raster_object(o,compensate=False)[:2] for o in objects]
    pad=math.ceil((distance+width+2)*10)
    lo=np.minimum.reduce([origin for mask,origin in masks])-pad/10
    hi=np.maximum.reduce([origin+np.asarray(mask.shape[::-1])/10 for mask,origin in masks])+pad/10
    size=np.ceil((hi-lo)*10).astype(int)
    if np.prod(size)>25_000_000:raise ValueError('Ontwerp is te groot voor een contour.')
    union=np.zeros((size[1],size[0]),bool)
    for mask,origin in masks:
        x,y=np.rint((origin-lo)*10).astype(int);union[y:y+mask.shape[0],x:x+mask.shape[1]]|=mask
    # Distance is clearance from the original edge to the nearest satin edge.
    radius=distance+(width/2 if kind=='satin' else 0)
    expanded=union if radius==0 else ndimage.distance_transform_edt(~union)<=radius*10
    cg=contourpy.contour_generator(z=expanded.astype(float),fill_type='OuterOffset')
    polygons,offsets=cg.filled(.5,1.5);out=[]
    for pp,oo in zip(polygons,offsets):
        # First ring is the outside; holes are intentionally left unoutlined.
        ring=design.simplify_polyline(pp[oo[0]:oo[1]],.5)
        if len(ring)<4:continue
        if np.linalg.norm(ring[0]-ring[-1])<.01:ring=ring[:-1]
        nodes=[dict(x=float(x/10+lo[0]),y=float(y/10+lo[1]),kind='corner') for x,y in ring]
        if kind=='satin':nodes.append(dict(nodes[0]))
        obj=design.new_object(nodes,color=color,name='Contour '+('satijn' if kind=='satin' else 'stiksteken'),fill=kind,satin=width,spacing=spacing,length=length,underlay=True,closed=kind!='satin',stitch_phase=2)
        obj['outline_settings']=dict(width=width,spacing=spacing,distance=distance,length=length)
        out.append(obj)
    if not out:raise ValueError('Geen contour gevonden.')
    return out
