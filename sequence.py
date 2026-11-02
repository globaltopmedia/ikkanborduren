"""Reorder whole colour blocks of imported stitch files, preserving absolute geometry."""
import copy
import pyembroidery as emb
import core

def colour_blocks(pattern):
    blocks=[];points=[];owners=[];index=0;mapping=pattern.extras.get('owners',[])
    for i,stitch in enumerate(pattern.stitches):
        cmd=stitch[2]&emb.COMMAND_MASK
        if cmd in (emb.COLOR_CHANGE,emb.END):
            if any((s[2]&emb.COMMAND_MASK)==emb.STITCH for s in points):
                thread=pattern.get_thread_or_filler(index)
                blocks.append(dict(points=points,owners=owners,thread=copy.deepcopy(thread)))
            points=[];owners=[]
            if cmd==emb.COLOR_CHANGE:index+=1
        else:points.append(list(stitch));owners.append(mapping[i] if len(mapping)==len(pattern.stitches) else None)
    if points and any((s[2]&emb.COMMAND_MASK)==emb.STITCH for s in points):blocks.append(dict(points=points,owners=owners,thread=copy.deepcopy(pattern.get_thread_or_filler(index))))
    return blocks

def reorder_blocks(pattern,order):
    blocks=colour_blocks(pattern)
    if sorted(order)!=list(range(len(blocks))):raise ValueError('Ongeldige kleurblokvolgorde.')
    p=emb.EmbPattern();owners=[];last=(0,0)
    for n,index in enumerate(order):
        block=blocks[index];p.add_thread(block['thread'])
        if n:
            p.add_stitch_absolute(emb.TRIM,*last);owners.append(None)
            p.add_stitch_absolute(emb.COLOR_CHANGE,*last);owners.append(None)
        # A first stitch may rely on the prior block's position. Always travel
        # to its absolute location before sewing a reordered block.
        first=next(s for s in block['points'] if (s[2]&emb.COMMAND_MASK) in (emb.STITCH,emb.JUMP))
        p.add_stitch_absolute(emb.JUMP,first[0],first[1]);owners.append(None)
        for s,owner in zip(block['points'],block['owners']):
            p.stitches.append(list(s));owners.append(owner)
            if (s[2]&emb.COMMAND_MASK) in (emb.STITCH,emb.JUMP):last=tuple(s[:2])
    p.add_stitch_absolute(emb.END,*last);owners.append(None);p.extras=copy.deepcopy(pattern.extras);p.extras.pop('route',None)
    if pattern.extras.get('owners'):p.extras['owners']=owners
    return p
