"""Find sewn travel inside a raster region, without crossing holes."""
import heapq
import math
import numpy as np

def inside_path(mask, start, end):
    """Pixel coordinates in/out. Return None for disconnected endpoints."""
    def pixel(q): return tuple(np.rint(q).astype(int))
    a,b=pixel(start),pixel(end)
    h,w=mask.shape
    def valid(q): return 0<=q[0]<w and 0<=q[1]<h and bool(mask[q[1],q[0]])
    if not valid(a) or not valid(b):return None
    def straight(p,q):
        n=max(2,int(math.dist(p,q)*2)+1)
        pts=np.rint(np.linspace(p,q,n)).astype(int)
        return bool(mask[pts[:,1],pts[:,0]].all())
    if straight(a,b):return [tuple(start),tuple(end)]
    queue=[(math.dist(a,b),0,a)];cost={a:0};parent={}
    while queue:
        _,g,q=heapq.heappop(queue)
        if g!=cost[q]:continue
        if q==b:break
        for dx,dy in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
            v=(q[0]+dx,q[1]+dy)
            if not valid(v):continue
            if dx and dy and (not valid((q[0]+dx,q[1])) or not valid((q[0],q[1]+dy))):continue
            ng=g+math.hypot(dx,dy)
            if ng<cost.get(v,float('inf')):
                cost[v]=ng;parent[v]=q;heapq.heappush(queue,(ng+math.dist(v,b),ng,v))
    else:return None
    points=[b]
    while points[-1]!=a:points.append(parent[points[-1]])
    points.reverse()
    # Only remove points on straight runs: retains the exact safe raster route.
    reduced=[points[0]]
    for i in range(1,len(points)-1):
        if (points[i][0]-points[i-1][0],points[i][1]-points[i-1][1])!=(points[i+1][0]-points[i][0],points[i+1][1]-points[i][1]):reduced.append(points[i])
    reduced.append(points[-1]);reduced[0]=tuple(start);reduced[-1]=tuple(end)
    return reduced
