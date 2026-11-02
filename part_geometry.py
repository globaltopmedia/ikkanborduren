"""Selection and isolated tracing in millimetres; route reversal preserves underlay."""
import copy,math
import numpy as np
from PIL import Image
from scipy import ndimage
from PySide6.QtCore import QPointF
from PySide6.QtGui import QPainterPath,QPolygonF
import design,pyembroidery as emb

def lasso_path(points):
    p=QPainterPath();p.addPolygon(QPolygonF([QPointF(x,y) for x,y in points]));p.closeSubpath();return p

def lasso_selection(objects,pattern,points,whole_objects=True):
    if len(points)<3:return set(),set()
    path=lasso_path(points);ids=set();stitches=set()
    if whole_objects:
        for obj in objects:
            polygon=design.flattened(obj['nodes'],obj.get('closed',True))
            if polygon and all(path.contains(QPointF(x*10,y*10)) for x,y in polygon):ids.add(obj['id'])
    elif pattern:
        stitches={i for i,(x,y,cmd) in enumerate(pattern.stitches) if (cmd&emb.COMMAND_MASK) in (emb.STITCH,emb.JUMP) and path.contains(QPointF(x,y))}
    return ids,stitches

def clicked_region(image,width_mm,x_mm,y_mm,remove_white=True):
    rgba=np.array(image.convert('RGBA'));h,w=rgba.shape[:2];scale=width_mm/w;x=int(math.floor(x_mm/scale+w/2));y=int(math.floor(y_mm/scale+h/2))
    if not (0<=x<w and 0<=y<h) or rgba[y,x,3]<128:raise ValueError('Klik binnen een zichtbaar kleurvlak.')
    color=rgba[y,x,:3]
    if remove_white and (color>=245).all():raise ValueError('De witte achtergrond wordt niet geborduurd. Zet achtergrond verwijderen uit als dit een wit ontwerpvlak is.')
    mask=(rgba[:,:,3]>128)&np.all(rgba[:,:,:3]==color,axis=2);labels,_=ndimage.label(mask);selected=labels==labels[y,x]
    rgba[:,:,3]=selected*255;objects=design.objects_from_art(Image.fromarray(rgba),width_mm,0)
    if not objects:raise ValueError('Dit detail is te klein; vergroot het ontwerp of teken de contour zelf.')
    return objects

def endpoints(pattern):
    result={};owners=pattern.extras.get('owners',[]) if pattern else []
    if not pattern or len(owners)!=len(pattern.stitches):return result
    for owner,(x,y,cmd) in zip(owners,pattern.stitches):
        if owner and (cmd&emb.COMMAND_MASK)==emb.STITCH:
            record=result.setdefault(owner,{'start':(x,y),'end':(x,y)});record['end']=(x,y)
    return result
