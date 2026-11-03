"""BorduurStudio: artwork preparation, editable projects and EXP/PES export.
Coordinates in embroidery patterns are tenths of a millimetre.
"""
from pathlib import Path
import io,json,math,zipfile
import numpy as np
from PIL import Image,ImageDraw
from scipy import ndimage
import contourpy
import pyembroidery as emb

VERSION='2.5.6-tatami-overlap'

def prepare_image(image, colors=8, remove_background=True):
    im=image.convert('RGBA').copy();im.thumbnail((1600,1600))
    a=np.asarray(im).copy()
    if remove_background:
        # Remove only near-white areas connected to an outside edge, not white eyes/numbers.
        white=(a[:,:,:3].min(axis=2)>238)&(a[:,:,3]>0)
        lab,_=ndimage.label(white);edge=np.unique(np.r_[lab[0],lab[-1],lab[:,0],lab[:,-1]])
        edge=edge[edge!=0];a[np.isin(lab,edge),3]=0
    visible=a[:,:,3]>128
    if not visible.any():raise ValueError('Geen zichtbare afbeelding over na achtergrond verwijderen.')
    yy,xx=np.where(visible);a=a[yy.min():yy.max()+1,xx.min():xx.max()+1]
    rgb=Image.fromarray(a[:,:,:3]);alpha=a[:,:,3]
    # Preserve the original RGB values whenever the artwork fits the selected
    # palette size. This keeps pure white, black, yellow, etc. exactly unchanged.
    # Quantization is only necessary when the image contains more visible RGB
    # colors than the user-selected embroidery palette can hold.
    visible=alpha>128
    pixels=a[:,:,:3]
    source_colors, inverse=np.unique(pixels[visible],axis=0,return_inverse=True)
    if len(source_colors) <= int(colors):
        palette=[tuple(map(int,c)) for c in source_colors]
        labels=np.full(visible.shape,-1,dtype=np.int32)
        labels[visible]=inverse
    else:
        samples=pixels[visible].reshape(1,-1,3)
        sample_image=Image.fromarray(samples.astype(np.uint8))
        q=sample_image.quantize(colors=int(colors),method=Image.Quantize.MEDIANCUT,dither=Image.Dither.NONE)
        indices=np.array(q).ravel();raw=np.array(q.getpalette(),np.uint8).reshape(-1,3)
        used=np.unique(indices);palette=[tuple(map(int,raw[k])) for k in used]
        pal=np.array(palette,np.float32)
        labels=np.empty(visible.shape,np.int16)
        for row in range(0,pixels.shape[0],64):
            block=pixels[row:row+64].astype(np.float32)
            labels[row:row+64]=np.argmin(((block[:,:,None,:]-pal[None,None,:,:])**2).sum(axis=3),axis=2)
        labels[~visible]=-1
        labels=ndimage.median_filter(labels,size=3);labels[~visible]=-1
    result=Image.fromarray(np.array(palette,np.uint8)[np.maximum(labels,0)]).convert('RGBA')
    result.putalpha(Image.fromarray((visible*255).astype(np.uint8)))
    return result,palette

def pattern_stats(p):
    stitches=[s for s in p.stitches if (s[2]&emb.COMMAND_MASK) in (emb.STITCH,emb.JUMP)]
    if not stitches:return {'width':0,'height':0,'stitches':0,'colors':len(p.threadlist),'changes':0}
    a=np.array(stitches);return {'width':float(np.ptp(a[:,0]))/10,'height':float(np.ptp(a[:,1]))/10,
        'stitches':sum((s[2]&emb.COMMAND_MASK)==emb.STITCH for s in p.stitches),
        'colors':len(p.threadlist),'changes':sum((s[2]&emb.COMMAND_MASK)==emb.COLOR_CHANGE for s in p.stitches)}

def center_pattern(p):
    if not p.stitches:return
    x0,y0,x1,y1=p.bounds();cx=(x0+x1)/2;cy=(y0+y1)/2
    for s in p.stitches:s[0]-=cx;s[1]-=cy

def resize_pattern(p,width,height=None):
    st=pattern_stats(p)
    if st['width']<=0:return
    fx=width/st['width'];fy=(height/st['height']) if height is not None and st['height'] else fx
    for s in p.stitches:s[0]*=fx;s[1]*=fy
    center_pattern(p)

def hoop_fits(p,width,height,oval=False,margin=2):
    rx=width*5-margin*10;ry=height*5-margin*10
    if rx<=0 or ry<=0:return False
    for x,y,c in p.stitches:
        if (c&emb.COMMAND_MASK) not in (emb.STITCH,emb.JUMP):continue
        if abs(x)>rx+.01 or abs(y)>ry+.01:return False
        if oval and (x/rx)**2+(y/ry)**2>1.00001:return False
    return True

def remove_stitches(p,selected):
    selected=set(selected);new=[];gap=False
    for i,s in enumerate(p.stitches):
        cmd=s[2]&emb.COMMAND_MASK
        if i in selected and cmd in (emb.STITCH,emb.JUMP):gap=True;continue
        if gap and cmd==emb.STITCH:
            # Resume without sewing a long line across a deleted region.
            new.append([s[0],s[1],emb.TRIM]);new.append([s[0],s[1],emb.JUMP]);gap=False
        new.append(list(s))
    p.stitches=new

def _spans(mask,spacing):
    active=[];groups=[]
    for y in np.arange(1,mask.shape[0],spacing):
        yi=int(round(y))
        if yi>=mask.shape[0]:break
        d=np.diff(np.r_[False,mask[yi],False].astype(np.int8));starts=np.where(d==1)[0];ends=np.where(d==-1)[0]-1
        current=[];used=set()
        for left,right in zip(starts,ends):
            if right-left<2:continue
            options=[(min(r,right)-max(l,left),i,t) for i,(l,r,t) in enumerate(active)
                if i not in used and min(r,right)-max(l,left)>0]
            if options:_,i,t=max(options,key=lambda z:z[0]);used.add(i)
            else:t=[];groups.append(t)
            t.append((float(left),float(right),float(yi)));current.append((left,right,t))
        active=current
    return groups

def _group_cover(rows,shape,spacing):
    """Pixels a group of tatami rows will cover (rows are spacing apart)."""
    cover=np.zeros(shape,bool);half=max(1,int(math.ceil(spacing/2)))
    for left,right,y in rows:
        y=int(y);cover[max(0,y-half):y+half+1,max(0,int(left)):int(right)+1]=True
    return cover

def _ordered_fill(region,travel,groups,max_stitch,ox,oy,spacing,start=None):
    """Sew all tatami groups of one area as one continuous path.

    Each group is sewn in serpentine rows. The next group is the nearest
    one that can be reached by travelling through area that is still to be
    filled (or along the outer edge), so every travel stitch is hidden under
    later rows instead of lying on top of finished fill.
    """
    from continuous_route import inside_path
    items=[]
    for rows in groups:
        pts=_fill_points(rows,max_stitch,0,0)
        if len(pts)>1:items.append((pts,_group_cover(rows,region.shape,spacing)))
    if not items:return []
    edge=travel&~ndimage.binary_erosion(region,iterations=4)
    done=np.zeros(region.shape,bool);path=[];current=None if start is None else (start[0]-ox,start[1]-oy)
    def entries(k):
        pts=items[k][0];return [(pts,pts[0]),(pts[::-1],pts[-1])]
    left=list(range(len(items)))
    while left:
        if current is None:
            # Start at the group nearest the top-left of the area.
            k=min(left,key=lambda k:min(q[1]*1000+q[0] for _,q in entries(k)));pts=items[k][0];connector=None
        else:
            options=sorted(((math.dist(current,q),k,pts) for k in left for pts,q in entries(k)),key=lambda z:z[0])
            allowed=(travel&~done)|edge;choice=None
            for _,k,pts in options[:12]:
                mask=allowed.copy()
                for q in (current,pts[0]):
                    x,y=int(round(q[0])),int(round(q[1]))
                    mask[max(0,y-3):y+4,max(0,x-3):x+4]=travel[max(0,y-3):y+4,max(0,x-3):x+4]
                connector=inside_path(mask,current,pts[0])
                if connector is not None:choice=(k,pts);break
            if choice is None:
                _,k,pts=options[0];connector=inside_path(travel,current,pts[0])
            else:k,pts=choice
            if connector is None:return None  # disconnected: caller sews groups separately
        if connector:path.extend(tuple(map(float,q)) for q in connector[1:-1])
        path.extend(pts);current=pts[-1];done|=items[k][1];left.remove(k)
    return [(x+ox,y+oy) for x,y in path]

def clone_pattern(p):
    if p is None:return None
    import copy
    result=p.copy();result.stitches=copy.deepcopy(p.stitches);result.threadlist=copy.deepcopy(p.threadlist);result.extras=copy.deepcopy(p.extras)
    return result

def _fill_points(rows,max_stitch,ox,oy):
    """Generate tatami rows with alternating half-step penetration phase.

    Adjacent rows keep the same boundary coverage but interior penetrations
    alternate by half a stitch interval. The row pitch is controlled separately
    by the fill spacing setting and should normally be around 0.35–0.45 mm. This avoids stacked, ruler-straight
    penetration columns while keeping every stitch below the configured limit.
    Coordinates are tenths of a millimetre.
    """
    points=[]
    target=max(10.0,min(float(max_stitch)*10.0,50.0))  # 1.0–5.0 mm maximum fill stitch
    edge_margin=1.5  # only 0.15 mm inside the (slightly expanded) fill boundary
    for ri,(left,right,y) in enumerate(rows):
        l=float(left)+edge_margin
        r=float(right)-edge_margin
        span=r-l
        # Do not create dense clusters in tiny fragments; narrow details need
        # a satin/run treatment rather than a row of machine-stalling stitches.
        if span < 5.0:
            continue
        intervals=max(1,int(math.ceil(span/target)))
        step=span/intervals
        if ri % 2:
            xs=[l]
            xs.extend(l+(i+0.5)*step for i in range(intervals) if i+0.5 < intervals)
            xs.append(r)
        else:
            xs=[l+step*i for i in range(intervals+1)]
        # Remove any near-duplicate points and keep all segments safely above
        # 0.8 mm; evenly distributed endpoints prevent tiny remainder stitches.
        row=[];gap=min(8.0,span*.99)
        for x in xs:
            if not row or x-row[-1] >= gap:
                row.append(x)
        if len(row)<2:
            continue
        if ri%2:
            row.reverse()
        for x in row:
            q=(x+ox,float(y)+oy)
            # Keep the edge penetration of every row (rows end neatly at the
            # outline); only drop true duplicates.
            if not points or math.dist(points[-1],q)>=3.0:
                points.append(q)
    return points

def _satin_paths(region,ox,oy,width,spacing):
    """A satin band INSIDE each contour; stroke width in tenths of mm."""
    padded=np.pad(region.astype(float),1)
    generator=contourpy.contour_generator(x=np.arange(padded.shape[1])-1,y=np.arange(padded.shape[0])-1,z=padded)
    def inside(q):
        x,y=np.rint(q).astype(int)
        return 0<=x<region.shape[1] and 0<=y<region.shape[0] and bool(region[y,x])
    paths=[]
    for contour in generator.lines(.5):
        if len(contour)<5:continue
        lengths=np.r_[0,np.cumsum(np.linalg.norm(np.diff(contour,axis=0),axis=1))]
        if lengths[-1]<spacing*2:continue
        steps=np.arange(0,lengths[-1],spacing)
        curve=np.column_stack([np.interp(steps,lengths,contour[:,j]) for j in range(2)])
        points=[]
        for i,q in enumerate(curve):
            tangent=curve[(i+1)%len(curve)]-curve[(i-1)%len(curve)];norm=np.linalg.norm(tangent)
            if norm<.01:continue
            normal=np.array([-tangent[1],tangent[0]])/norm
            if not inside(q+normal*1.2):normal=-normal
            if not inside(q+normal*1.2):continue
            outer=q+normal*.7;inner=outer.copy()
            # Stop before an inner edge, hole or narrow part of a letter.
            for distance in np.arange(1,width+.01,1):
                candidate=outer+normal*distance
                if not inside(candidate):break
                inner=candidate
            if np.linalg.norm(inner-outer)<2:continue
            points.extend([(float(outer[0]+ox),float(outer[1]+oy)),(float(inner[0]+ox),float(inner[1]+oy))])
        if len(points)>4:paths.append(points)
    return paths

def nearest_entry(tasks,reference,pending):
    """Greedy nearest available endpoint; closed satin loops permit any entry point.
    Underlay dependencies prevent top stitches from preceding their underlay.
    """
    choice=None
    for i,t in enumerate(tasks):
        if t['layer']=='top' and pending.get(t['component'],0):continue
        if t['layer']=='satin' and pending.get(('fill',t['component']),0):continue
        pts=t['points']
        if t.get('closed'):
            arr=np.asarray(pts);dist=((arr-np.asarray(reference))**2).sum(axis=1);j=int(np.argmin(dist));distance=float(np.sqrt(dist[j]));candidate=(distance,i,j)
        elif t.get('fixed'):candidate=(math.dist(reference,pts[0]),i,0)
        else:
            a,b=math.dist(reference,pts[0]),math.dist(reference,pts[-1]);candidate=(min(a,b),i,-1 if b<a else 0)
        if choice is None or candidate<choice:choice=candidate
    if choice is None:raise ValueError('Geen beschikbaar volgend detail.')
    return choice

def digitize(image,palette,width_mm=100,spacing=.45,max_stitch=2.5,underlay=True,vertical=False,progress=None,mode='fill',satin_width=3,center_output=True,start=None):
    """start: optional pixel (x, y) where sewing should begin (closest connection)."""
    if not (0.3<=spacing<=1.5):raise ValueError('Rijafstand moet 0,30–1,50 mm zijn.')
    if not (1<=max_stitch<=5):raise ValueError('Steeklengte moet 1–5 mm zijn.')
    if not (.5<=satin_width<=5):raise ValueError('Satijnbreedte moet 0,5–5 mm zijn.')
    if mode not in ('fill','satin','both'):raise ValueError('Onbekende steekwijze.')
    if not palette:raise ValueError('Er zijn geen kleuren om te borduren.')
    if width_mm<=0:raise ValueError('De breedte moet groter dan nul zijn.')
    height_mm=width_mm*image.height/image.width
    if width_mm>400 or height_mm>400:raise ValueError('Maximale ontwerpmaat is 400 × 400 mm.')
    w=max(10,round(width_mm*10));h=max(10,round(height_mm*10))
    image=image.convert('RGBA').resize((w,h),Image.Resampling.NEAREST)
    a=np.array(image);opaque=a[:,:,3]>128;pal=np.array(palette,np.float32);labels=np.full((h,w),-1,np.int16)
    for y in range(0,h,64):
        block=a[y:y+64,:,:3].astype(np.float32)
        labels[y:y+64]=np.argmin(((block[:,:,None,:]-pal[None,None,:,:])**2).sum(axis=3),axis=2)
    labels[~opaque]=-1
    if vertical:labels=np.rot90(labels)
    mh,mw=labels.shape;p=emb.EmbPattern();last=None;route=[]
    def xy(q):
        x,y=q
        if vertical:x,y=w-1-y,x
        return x-w/2,y-h/2
    def add(cmd,q):
        nonlocal last
        x,y=xy(q);p.add_stitch_absolute(cmd,x,y);last=q
    def line(q,limit):
        if last is None:add(emb.STITCH,q);return
        ax,ay=last;n=max(1,math.ceil(math.dist(last,q)/limit))
        for k in range(1,n+1):add(emb.STITCH,(ax+(q[0]-ax)*k/n,ay+(q[1]-ay)*k/n))
    counts=np.bincount(labels[labels>=0],minlength=len(palette))
    order=sorted((i for i in range(len(palette)) if counts[i]>=6),key=lambda i:sum(palette[i]),reverse=True)
    if not order:raise ValueError('Er zijn geen zichtbare vlakken om te borduren.')
    for block,k in enumerate(order):
        if progress:progress(int(block*100/len(order)),f'Kleur {block+1} van {len(order)} — dichtstbijzijnde details')
        if block:p.add_command(emb.COLOR_CHANGE)
        col=palette[k];p.add_thread({'color':'#%02x%02x%02x'%tuple(col),'description':f'Kleur {block+1}','brand':'Eigen palet'})
        mask=labels==k;components,n=ndimage.label(mask);tasks=[];pending={}
        for j,sl in enumerate(ndimage.find_objects(components),1):
            if sl is None:continue
            region=components[sl]==j
            if region.sum()<6:continue
            # Add a 0.2 mm compensation allowance so the fill extends beneath
            # the final contour instead of leaving the fabric colour peeking through.
            y0=max(0,sl[0].start-2);y1=min(mh,sl[0].stop+2)
            x0=max(0,sl[1].start-2);x1=min(mw,sl[1].stop+2)
            ox,oy=x0,y0
            source_region=components[y0:y1,x0:x1]==j
            travel=ndimage.binary_dilation(source_region,iterations=2)
            region=travel
            def task(points,layer,closed=False):
                if not points:return
                tasks.append({'points':points,'travel':travel,'offset':(ox,oy),'component':j,'layer':layer,'closed':closed})
                if layer=='under':pending[j]=pending.get(j,0)+1
                if layer in ('under','top'):pending[('fill',j)]=pending.get(('fill',j),0)+1
            if mode in ('fill','both'):
                if underlay and region.sum()>1800 and min(region.shape)>=24:
                    local=ndimage.binary_erosion(region,iterations=3)
                    groups=_spans(local,24)
                    ordered=_ordered_fill(local,travel,groups,max_stitch,ox,oy,24,start) if len(groups)>1 else None
                    if ordered:task(ordered,'under');tasks[-1]['fixed']=True
                    else:
                        for rows in groups:task(_fill_points(rows,max_stitch,ox,oy),'under')
                groups=_spans(region,spacing*10)
                ordered=_ordered_fill(region,travel,groups,max_stitch,ox,oy,spacing*10,start) if len(groups)>1 else None
                if ordered:task(ordered,'top');tasks[-1]['fixed']=True
                else:
                    for rows in groups:task(_fill_points(rows,max_stitch,ox,oy),'top')
            if mode in ('satin','both'):
                # Slight allowance for diagonals and 0.1 mm machine quantisation.
                band=min(satin_width*10,48)
                for points in _satin_paths(region,ox,oy,band,spacing*10):task(points,'satin',True)
        active_component=None
        from continuous_route import inside_path
        while tasks:
            eligible=[t for t in tasks if active_component is None or t['component']==active_component]
            reference=last if last is not None else (tuple(start) if start is not None else (mw/2,mh/2))
            distance,i,entry=nearest_entry(eligible,reference,pending);t=eligible[i];tasks.pop(next(n for n,u in enumerate(tasks) if u is t));active_component=t['component'];points=t['points']
            if t['closed']:
                points=points[entry:]+points[:entry];points=points+[points[0]]
            elif entry==-1:points=list(reversed(points))
            route.append({'color':block,'jump_mm':distance/10,'layer':t['layer'],'component':t['component'],'start':len(p.stitches),'fixed':bool(t.get('fixed'))})
            ox,oy=t['offset'];travel=t['travel']
            connector=None if last is None else inside_path(travel,(last[0]-ox,last[1]-oy),(points[0][0]-ox,points[0][1]-oy))
            if connector is not None:
                route[-1]['jump_mm']=0
                for x,y in connector[1:]:line((x+ox,y+oy),min(max_stitch*10,49))
            else:
                if last is not None:add(emb.TRIM,last)
                add(emb.JUMP,points[0]);add(emb.STITCH,points[0])
            for q in points[1:]:
                if math.dist(last,q)<.5:continue
                count=max(2,int(math.dist(last,q))+1)
                xs=np.rint(np.linspace(last[0]-ox,q[0]-ox,count)).astype(int)
                ys=np.rint(np.linspace(last[1]-oy,q[1]-oy,count)).astype(int)
                safe=(xs>=0)&(xs<travel.shape[1])&(ys>=0)&(ys<travel.shape[0])
                if safe.all() and travel[ys,xs].all():line(q,49 if t['layer']=='satin' else min(max_stitch*10,49))
                else:
                    connector=inside_path(travel,(last[0]-ox,last[1]-oy),(q[0]-ox,q[1]-oy))
                    if connector is None:add(emb.TRIM,last);add(emb.JUMP,q);add(emb.STITCH,q)
                    else:
                        for x,y in connector[1:]:line((x+ox,y+oy),min(max_stitch*10,49))
            route[-1]['end']=len(p.stitches)
            if not any(u['component']==active_component for u in tasks):active_component=None
            if t['layer']=='under':pending[t['component']]-=1
            if t['layer'] in ('under','top'):pending[('fill',t['component'])]-=1
            if len(p.stitches)>250000:raise ValueError('Meer dan 250.000 steken. Verklein of vereenvoudig het ontwerp.')
    if not any((s[2]&emb.COMMAND_MASK)==emb.STITCH for s in p.stitches):raise ValueError('Geen steken gegenereerd. Vergroot of vereenvoudig de afbeelding.')
    p.add_command(emb.END)
    if center_output:center_pattern(p)
    p.extras['route']=route
    if progress:progress(100,'Borduurpatroon klaar')
    return p

def render_pattern(p,max_size=1600):
    x0,y0,x1,y1=p.bounds() if p.stitches else (-50,-50,50,50)
    width=max(10,x1-x0);height=max(10,y1-y0);scale=min(max_size/width,max_size/height,2)
    im=Image.new('RGB',(round(width*scale)+30,round(height*scale)+30),'#fffdf7');d=ImageDraw.Draw(im)
    last=(0,0);block=0
    for x,y,c in p.stitches:
        cmd=c&emb.COMMAND_MASK
        if cmd==emb.COLOR_CHANGE:block+=1
        if cmd==emb.STITCH:
            color=p.threadlist[min(block,len(p.threadlist)-1)].get_red() if p.threadlist else 0
            if p.threadlist:
                t=p.threadlist[min(block,len(p.threadlist)-1)];color=(t.get_red(),t.get_green(),t.get_blue())
            else:color=(25,40,70)
            d.line([((last[0]-x0)*scale+15,(last[1]-y0)*scale+15),((x-x0)*scale+15,(y-y0)*scale+15)],fill=color,width=max(1,round(scale*2)))
        last=(x,y)
    return im

def export_bundle(p,destination,hoop_width,hoop_height,oval=False,margin=2,fmt='exp'):
    if not any((s[2]&emb.COMMAND_MASK)==emb.STITCH for s in p.stitches):raise ValueError('Er zijn nog geen borduursteken.')
    if not hoop_fits(p,hoop_width,hoop_height,oval,margin):raise ValueError('Het patroon valt buiten de ingestelde borduurring. Pas maat of positie aan.')
    path=Path(destination).with_suffix('.'+fmt);path.parent.mkdir(parents=True,exist_ok=True)
    # Quantisation of both ends may add up to sqrt(2) tenths: reserve 0.2 mm.
    p=clone_pattern(p);out=[];last=None
    for x,y,c in p.stitches:
        cmd=c&emb.COMMAND_MASK
        if cmd==emb.STITCH and last is not None:
            n=max(1,math.ceil(math.dist(last,(x,y))/48))
            out.extend([[last[0]+(x-last[0])*k/n,last[1]+(y-last[1])*k/n,emb.STITCH] for k in range(1,n)])
        out.append([x,y,c])
        if cmd in (emb.STITCH,emb.JUMP):last=(x,y)
    p.stitches=out
    settings={'max_stitch':48,'max_jump':127 if fmt=='exp' else 2040,'explicit_trim':True,'version':1}
    if fmt=='exp':emb.write_exp(p,str(path),settings)
    elif fmt=='pes':emb.write_pes(p,str(path),settings)
    else:raise ValueError('Exportformaat moet EXP of PES zijn.')
    # Ensure coordinates survive encoding; invalid files are removed instead of offered as working exports.
    loaded=emb.read(str(path));a=p.bounds();b=loaded.bounds()
    last=None
    for x,y,c in loaded.stitches:
        cmd=c&emb.COMMAND_MASK
        if cmd==emb.STITCH and last is not None and math.dist(last,(x,y))>50.0001:
            path.unlink(missing_ok=True);raise ValueError('Export bevat een steek langer dan 5 mm; bestand niet bewaard.')
        if cmd in (emb.STITCH,emb.JUMP):last=(x,y)
    if any(abs(x-y)>2 for x,y in zip(a,b)):
        path.unlink(missing_ok=True);raise ValueError('Controle van het geëxporteerde formaat is mislukt.')
    if fmt=='exp':
        with open(path.with_suffix('.inf'),'wb') as f:emb.InfWriter.write(p,f)
        thumb=render_pattern(p,280);thumb.save(path.with_suffix('.bmp'))
    render_pattern(p).save(path.with_name(path.stem+'_steekvoorbeeld.png'))
    import fabric
    chosen=p.extras.get('fabric_selection') or p.extras.get('fabric_profile');applied=p.extras.get('fabric_profile')
    material_note=('Stofkeuze: '+fabric.PROFILES[chosen]['label']+'\n' if chosen in fabric.PROFILES else '')+('Stofinstellingen toegepast: '+fabric.PROFILES[applied]['label']+'\n' if applied in fabric.PROFILES else 'Stofinstellingen niet automatisch toegepast op deze bestaande steken.\n')
    if chosen in fabric.PROFILES:material_note+=fabric.describe(chosen)+'\n'
    colors=[f'{i+1}. #{t.get_red():02X}{t.get_green():02X}{t.get_blue():02X} {t.description or ""}' for i,t in enumerate(p.threadlist)]
    st=pattern_stats(p)
    path.with_name(path.stem+'_kleuren.txt').write_text('BorduurStudio — proefpatroon\n'+material_note+f'Maat: {st["width"]:.1f} x {st["height"]:.1f} mm\nSteken: {st["stitches"]}\n'+'\n'.join(colors)+'\n\nEerst proefborduren met passende versteviging.\n',encoding='utf-8')
    return path

def save_project(path,image,palette,pattern,settings):
    data={'version':VERSION,'palette':palette,'settings':settings,'stitches':pattern.stitches if pattern else [],
          'threads':[{'color':t.color,'description':t.description} for t in pattern.threadlist] if pattern else [], 'extras':pattern.extras if pattern else {}}
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('project.json',json.dumps(data))
        if image is not None:
            buf=io.BytesIO();image.save(buf,format='PNG');z.writestr('drawing.png',buf.getvalue())

def load_project(path):
    with zipfile.ZipFile(path) as z:
        if sum(i.file_size for i in z.infolist())>150_000_000:raise ValueError('Projectbestand is te groot.')
        data=json.loads(z.read('project.json'));image=Image.open(io.BytesIO(z.read('drawing.png'))).convert('RGBA') if 'drawing.png' in z.namelist() else None
    p=emb.EmbPattern();p.stitches=[list(s) for s in data.get('stitches',[])]
    for t in data.get('threads',[]):p.add_thread(t)
    p.extras=data.get('extras',{})
    return image,data.get('palette',[]),p,data.get('settings',{})

def vectorize(image,path):
    """Trace simplified flat artwork; paths remain editable in vector editors."""
    a=np.array(image.convert('RGBA'));h,w=a.shape[:2];valid=a[:,:,3]>128
    colors=np.unique(a[:,:,:3][valid],axis=0)
    if len(colors)>24:raise ValueError('Vereenvoudig eerst tot maximaal 24 kleuren.')
    svg=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}">']
    for col in colors:
        mask=valid&np.all(a[:,:,:3]==col,axis=2)
        cg=contourpy.contour_generator(x=np.arange(w+2)-1,y=np.arange(h+2)-1,z=np.pad(mask.astype(float),1),fill_type='OuterOffset')
        points,offsets=cg.filled(.5,1.5)
        for pp,oo in zip(points,offsets):
            rings=[]
            for s,e in zip(oo[:-1],oo[1:]):
                ring=pp[s:e]
                if len(ring)<4:continue
                rings.append('M '+' L '.join(f'{x:.1f},{y:.1f}' for x,y in ring)+' Z')
            if rings:svg.append(f'<path fill="#{col[0]:02x}{col[1]:02x}{col[2]:02x}" fill-rule="evenodd" d="{" ".join(rings)}"/>')
    svg.append('</svg>');Path(path).write_text('\n'.join(svg),encoding='utf-8')
