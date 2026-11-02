"""Line-following satin, satin fill and direction regions.

Works on raster masks with 0.1 mm pixels (the same grid as design.raster_object).
Coordinates returned are pixel (x, y) floats in that grid. No Qt.
"""
import math
import numpy as np
from scipy import ndimage

N8 = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))
SATIN_MAX_MM = 4.8  # project-wide machine limit: longer satin is split


def disk(radius):
    yy, xx = np.mgrid[-radius:radius + 1, -radius:radius + 1]
    return xx * xx + yy * yy <= radius * radius


def thin(mask):
    """Zhang–Suen thinning; returns a one pixel wide skeleton."""
    img = np.pad(np.asarray(mask, bool).astype(np.uint8), 1)
    while True:
        changed = False
        for step in (0, 1):
            p2 = img[:-2, 1:-1]; p3 = img[:-2, 2:]; p4 = img[1:-1, 2:]; p5 = img[2:, 2:]
            p6 = img[2:, 1:-1]; p7 = img[2:, :-2]; p8 = img[1:-1, :-2]; p9 = img[:-2, :-2]
            c = img[1:-1, 1:-1]
            ring = (p2, p3, p4, p5, p6, p7, p8, p9, p2)
            b = sum(r.astype(np.int16) for r in ring[:8])
            a = sum(((ring[k] == 0) & (ring[k + 1] == 1)).astype(np.int16) for k in range(8))
            if step == 0:cond = ((p2 & p4 & p6) == 0) & ((p4 & p6 & p8) == 0)
            else:cond = ((p2 & p4 & p8) == 0) & ((p2 & p6 & p8) == 0)
            remove = (c == 1) & (b >= 2) & (b <= 6) & (a == 1) & cond
            if remove.any():
                c[remove] = 0; changed = True
        if not changed:break
    return _clean_staircase(img[1:-1, 1:-1].astype(bool))


RING = ((-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1))


def _clean_staircase(skel):
    """Drop corner pixels of 4-connected steps: they look like junctions but are not."""
    skel = np.pad(skel, 1); h, w = skel.shape
    four = skel[:-2, 1:-1].astype(int) + skel[2:, 1:-1] + skel[1:-1, :-2] + skel[1:-1, 2:]
    candidates = np.argwhere(skel[1:-1, 1:-1] & (four >= 2)) + 1
    for y, x in candidates:
        if not skel[y, x]:continue
        present = [(dy, dx) for dy, dx in RING if skel[y + dy, x + dx]]
        if len(present) < 2:continue
        # Keep the pixel when its neighbours would fall apart without it.
        seen = {present[0]}; todo = [present[0]]
        while todo:
            a = todo.pop()
            for b in present:
                if b not in seen and max(abs(a[0] - b[0]), abs(a[1] - b[1])) == 1:seen.add(b); todo.append(b)
        if len(seen) == len(present):skel[y, x] = False
    return skel[1:-1, 1:-1]


def _neighbours(skel, y, x):
    h, w = skel.shape
    for dy, dx in N8:
        v, u = y + dy, x + dx
        if 0 <= v < h and 0 <= u < w and skel[v, u]:yield v, u


def skeleton_graph(skel):
    """Nodes are clusters of end/junction pixels; edges are pixel chains between them."""
    deg = ndimage.convolve(skel.astype(np.int16), np.ones((3, 3), np.int16), mode='constant') - 1
    deg[~skel] = 0
    node_px = skel & (deg != 2)
    labels, count = ndimage.label(node_px, structure=np.ones((3, 3)))
    edges = []; used = set()
    for y, x in zip(*np.nonzero(node_px)):
        start_node = labels[y, x]
        for v, u in _neighbours(skel, y, x):
            if labels[v, u] == start_node:continue
            if ((y, x), (v, u)) in used:continue
            path = [(y, x), (v, u)]; prev = (y, x); cur = (v, u)
            while not labels[cur]:
                nxt = [q for q in _neighbours(skel, *cur) if q != prev and q not in path[-3:]]
                if not nxt:break
                # Prefer orthogonal steps; keeps chains from cutting corners.
                nxt.sort(key=lambda q: abs(q[0] - cur[0]) + abs(q[1] - cur[1]))
                prev, cur = cur, nxt[0]; path.append(cur)
                if len(path) > skel.size:break
            used.add((path[0], path[1])); used.add((path[-1], path[-2]))
            edges.append((start_node, int(labels[cur]) if labels[cur] else -1, path))
    # Closed loops without any end or junction pixel.
    seen = np.zeros_like(skel)
    for _, _, path in edges:
        for q in path:seen[q] = True
    loose = skel & ~seen & ~node_px
    while loose.any():
        y, x = map(int, np.argwhere(loose)[0]); path = [(y, x)]; prev = None; cur = (y, x)
        while True:
            nxt = [q for q in _neighbours(skel, *cur) if q != prev and loose[q] and q not in path[-3:]]
            if not nxt:break
            prev, cur = cur, nxt[0]
            if cur == path[0]:break
            path.append(cur)
            if len(path) > skel.size:break
        for q in path:loose[q] = False
        count += 1; path.append(path[0]); edges.append((count, count, path))
    return edges, count, deg


def prune(skel, edt, passes=2):
    """Remove short spurs that thinning grows from bumps in the outline."""
    skel = skel.copy()
    for _ in range(passes):
        edges, _, deg = skeleton_graph(skel); removed = False
        for a, b, path in edges:
            ends = [path[0], path[-1]]
            tips = [q for q in ends if deg[q] <= 1]
            if len(tips) != 1 or len(ends) == len(tips):continue
            joint = ends[1] if tips[0] == ends[0] else ends[0]
            if len(path) < max(4, 1.6 * edt[joint] + 2):
                for q in path:
                    if q != joint:skel[q] = False
                removed = True
        if not removed:break
    return skel


def _smooth(points, closed, sigma=2.5):
    if len(points) < 5:return points
    return ndimage.gaussian_filter1d(points, sigma, axis=0, mode='wrap' if closed else 'nearest')


def _inside(mask, pts):
    xy = np.rint(pts).astype(int); h, w = mask.shape
    ok = (xy[..., 0] >= 0) & (xy[..., 0] < w) & (xy[..., 1] >= 0) & (xy[..., 1] < h)
    out = np.zeros(ok.shape, bool)
    out[ok] = mask[xy[..., 1][ok], xy[..., 0][ok]]
    return out


def _extend_tip(mask, pts, at_end):
    """Continue a skeleton end into the rounded tip of the stroke."""
    if len(pts) < 3:return pts
    tip = pts[-1] if at_end else pts[0]; back = pts[max(0, len(pts) - 6)] if at_end else pts[min(len(pts) - 1, 5)]
    d = tip - back; n = np.linalg.norm(d)
    if n < 1e-6:return pts
    d = d / n; extra = []
    for t in np.arange(1, 80, 1.0):
        q = tip + d * t
        if not _inside(mask, q[None])[0]:break
        extra.append(q)
    extra = extra[:-1]
    if not extra:return pts
    extra = np.array(extra)
    return np.vstack([pts, extra]) if at_end else np.vstack([extra[::-1], pts])


def satin_points(mask, centre, spacing_px, ext_px=.6, closed=False, direction_at=None, max_tilt=60.):
    """Zigzag across the stroke at every sample of the centre line."""
    centre = np.asarray(centre, float)
    if len(centre) < 2:return []
    smooth = _smooth(centre, closed)
    seg = np.linalg.norm(np.diff(smooth, axis=0), axis=1); arc = np.r_[0, np.cumsum(seg)]
    if arc[-1] < .5:return []
    count = max(1, int(math.ceil(arc[-1] / spacing_px)))
    s = np.linspace(0, arc[-1], count + 1)
    q = np.column_stack([np.interp(s, arc, smooth[:, i]) for i in (0, 1)])
    look = max(1.5, spacing_px)
    ahead = np.column_stack([np.interp(np.minimum(s + look, arc[-1]), arc, smooth[:, i]) for i in (0, 1)])
    behind = np.column_stack([np.interp(np.maximum(s - look, 0), arc, smooth[:, i]) for i in (0, 1)])
    tangent = ahead - behind; norm = np.linalg.norm(tangent, axis=1); good = norm > 1e-6
    q, tangent, norm = q[good], tangent[good], norm[good]
    if not len(q):return []
    normal = np.column_stack([-tangent[:, 1], tangent[:, 0]]) / norm[:, None]
    inside = _inside(mask, q); q, normal = q[inside], normal[inside]
    if not len(q):return []
    if direction_at is not None:
        # Stitch angle from the direction arrows; the satin keeps following the
        # line, the tilt against the line's normal stays within max_tilt.
        angle = direction_at(q)
        if angle is not None:
            want = np.column_stack([np.cos(angle), np.sin(angle)])
            flip = (want * normal).sum(axis=1) < 0; want[flip] *= -1
            diff = np.arctan2(normal[:, 0] * want[:, 1] - normal[:, 1] * want[:, 0], (normal * want).sum(axis=1))
            diff = np.clip(diff, -math.radians(max_tilt), math.radians(max_tilt))
            c, s = np.cos(diff), np.sin(diff)
            normal = np.column_stack([c * normal[:, 0] - s * normal[:, 1], s * normal[:, 0] + c * normal[:, 1]])
    steps = np.arange(.5, 120, .5)

    def extent(direction):
        probe = q[:, None, :] + direction[:, None, :] * steps[None, :, None]
        ok = _inside(mask, probe)
        first_out = np.where(ok.all(axis=1), len(steps), np.argmin(ok, axis=1))
        return np.where(first_out > 0, steps[np.maximum(first_out - 1, 0)], 0.)

    a = extent(normal); b = extent(-normal)
    left = q + normal * (a + ext_px)[:, None]; right = q - normal * (b + ext_px)[:, None]
    out = []
    for l, r in zip(left, right):out.extend([tuple(l), tuple(r)])
    return out


def _resample(points, step):
    points = np.asarray(points, float)
    if len(points) < 2:return [tuple(p) for p in points]
    arc = np.r_[0, np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
    s = np.linspace(0, arc[-1], max(1, int(math.ceil(arc[-1] / step))) + 1)
    return [tuple(v) for v in np.column_stack([np.interp(s, arc, points[:, i]) for i in (0, 1)])]


def column_paths(mask, spacing_px=4., ext_px=.6, run_px=15., direction_at=None):
    """Line-following satin for each connected stroke in mask.

    Every skeleton edge is walked twice: a running stitch along the centre on
    the way out (doubles as underlay and hidden travel) and the satin on the
    way back. One continuous stitch path per connected piece, no jumps.
    """
    mask = np.asarray(mask, bool); paths = []
    labels, n = ndimage.label(mask, structure=np.ones((3, 3)))
    for index, sl in enumerate(ndimage.find_objects(labels), 1):
        if sl is None:continue
        pad = 2
        y0, x0 = max(0, sl[0].start - pad), max(0, sl[1].start - pad)
        y1, x1 = min(mask.shape[0], sl[0].stop + pad), min(mask.shape[1], sl[1].stop + pad)
        local = labels[y0:y1, x0:x1] == index
        if local.sum() < 4:continue
        edt = ndimage.distance_transform_edt(local)
        skel = prune(thin(local), edt)
        if not skel.any():continue
        edges, _, deg = skeleton_graph(skel)
        if not edges:
            # A dot: one short satin along its long axis.
            ys, xs = np.nonzero(local)
            pts = np.column_stack([xs, ys]).astype(float); c = pts.mean(axis=0)
            u, _, vt = np.linalg.svd(pts - c, full_matrices=False); axis = vt[0]
            half = max(1., np.abs((pts - c) @ axis).max())
            centre = [c - axis * half, c + axis * half]
            zig = satin_points(local, centre, spacing_px, ext_px, direction_at=_shift(direction_at, x0, y0))
            if zig:paths.append([(x + x0, y + y0) for x, y in zig])
            continue
        adjacency = {}
        polylines = []
        for k, (a, b, path) in enumerate(edges):
            pts = np.array([(x, y) for y, x in path], float)
            closed = a == b and len(path) > 3 and path[0] == path[-1]
            if not closed:
                if deg[path[0]] <= 1:pts = _extend_tip(local, pts, False)
                if deg[path[-1]] <= 1:pts = _extend_tip(local, pts, True)
            polylines.append((pts, closed))
            adjacency.setdefault(a, []).append((k, True)); adjacency.setdefault(b, []).append((k, False))
        # Start at a stroke end when there is one.
        ends = [a for a, b, path in edges if deg[path[0]] <= 1] + [b for a, b, path in edges if deg[path[-1]] <= 1]
        start = ends[0] if ends else edges[0][0]
        sequence = []; used = set(); visited = {start}; entering = {}
        stack = [(start, iter(adjacency.get(start, [])))]
        while stack:
            node, it = stack[-1]; moved = False
            for k, forward in it:
                if k in used:continue
                used.add(k); pts, closed = polylines[k]
                pts = pts if forward else pts[::-1]
                other = edges[k][1] if forward else edges[k][0]
                sequence.append(('run', pts, closed))
                if other in visited:
                    sequence.append(('satin', pts[::-1], closed)); continue
                visited.add(other); entering[other] = (pts, closed)
                stack.append((other, iter(adjacency.get(other, [])))); moved = True; break
            if not moved:
                stack.pop()
                if node in entering:
                    pts, closed = entering[node]; sequence.append(('satin', pts[::-1], closed))
        route = []
        for kind, pts, closed in sequence:
            if kind == 'run':
                route.extend(_resample(_smooth(pts, closed), run_px))
            else:
                route.extend(satin_points(local, pts, spacing_px, ext_px, closed, _shift(direction_at, x0, y0)))
        cleaned = []
        for q in route:
            if not cleaned or math.dist(cleaned[-1], q) > .3:cleaned.append(q)
        if len(cleaned) > 1:paths.append([(x + x0, y + y0) for x, y in cleaned])
    return paths


def _shift(direction_at, x0, y0):
    if direction_at is None:return None
    return lambda q: direction_at(np.asarray(q) + (x0, y0))


def opening(mask, radius_px):
    """Morphological opening with a round brush (fast, via distance transforms)."""
    padded = np.pad(np.asarray(mask, bool), 1)
    core = ndimage.distance_transform_edt(padded) > radius_px
    if not core.any():return np.zeros_like(np.asarray(mask, bool))
    return (ndimage.distance_transform_edt(~core) <= radius_px)[1:-1, 1:-1] & np.asarray(mask, bool)


def narrow_fraction(mask, width_mm):
    mask = np.asarray(mask, bool); total = mask.sum()
    return 0. if not total else float((mask & ~opening(mask, width_mm * 5)).sum() / total)


def split_narrow(mask, radius_px=9, min_area_px=None):
    """Return (wide, narrow) parts. Narrow = strokes thinner than 2 × radius."""
    mask = np.asarray(mask, bool)
    if not mask.any():return mask, mask
    min_area_px = max(60, .6 * radius_px * radius_px) if min_area_px is None else min_area_px
    wide = ndimage.binary_dilation(opening(mask, radius_px), iterations=2) & mask
    narrow = mask & ~wide
    labels, n = ndimage.label(narrow, structure=np.ones((3, 3)))
    if n:
        sizes = ndimage.sum(narrow, labels, range(1, n + 1))
        keep = np.zeros(n + 1, bool); keep[1:] = sizes >= min_area_px
        narrow = keep[labels]
        # Let a stroke reach a little under the neighbouring fill: no gap at the joint.
        narrow = ndimage.binary_dilation(narrow, iterations=2) & mask
    return wide, narrow


def satin_rows(mask, spacing_px):
    """Satin fill: one stitch from edge to edge per row, rows along x."""
    import core
    out = []
    for rows in core._spans(mask, spacing_px):
        pts = []
        for left, right, y in rows:
            if right - left < 2:continue
            pts.extend([(left - .2, y), (right + .2, y)])
        if len(pts) > 2:out.append(pts)
    return out


def geodesic_labels(mask, seeds, step=4):
    """Label each mask pixel with the index of the nearest seed, measured inside the shape."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import dijkstra
    mask = np.asarray(mask, bool); h, w = mask.shape
    ch, cw = -(-h // step), -(-w // step)
    padded = np.zeros((ch * step, cw * step), bool); padded[:h, :w] = mask
    coarse = padded.reshape(ch, step, cw, step).any(axis=(1, 3))
    ids = -np.ones(coarse.shape, int); valid = np.argwhere(coarse); ids[coarse] = np.arange(len(valid))
    rows, cols, weights = [], [], []
    for dy, dx in ((0, 1), (1, 0), (1, 1), (1, -1)):
        ya, yb = slice(0, ch - dy), slice(dy, ch)
        xa, xb = (slice(0, cw - dx), slice(dx, cw)) if dx >= 0 else (slice(-dx, cw), slice(0, cw + dx))
        a = ids[ya, xa]; b = ids[yb, xb]
        good = (a >= 0) & (b >= 0)
        rows.append(a[good]); cols.append(b[good]); weights.append(np.full(int(good.sum()), math.hypot(dx, dy)))
    rows = np.concatenate(rows); cols = np.concatenate(cols); weights = np.concatenate(weights)
    graph = coo_matrix((weights, (rows, cols)), shape=(len(valid), len(valid))).tocsr()
    # Each seed snaps to the nearest coarse cell inside the shape.
    _, (iy, ix) = ndimage.distance_transform_edt(~coarse, return_indices=True)
    sources = []
    for x, y in seeds:
        cy = int(np.clip(round(y / step), 0, ch - 1)); cx = int(np.clip(round(x / step), 0, cw - 1))
        sources.append(int(ids[iy[cy, cx], ix[cy, cx]]))
    _, _, nearest = dijkstra(graph, directed=False, indices=sorted(set(sources)), min_only=True, return_predecessors=True)
    seed_of = {}
    for k, node in enumerate(sources):seed_of.setdefault(node, k)
    lab = np.full(len(valid), -1); reached = nearest >= 0
    lab[reached] = [seed_of[int(v)] for v in nearest[reached]]
    grid = -np.ones(coarse.shape, int); grid[coarse] = lab
    # Unreachable islands take the straight-line nearest seed.
    if (grid[coarse] < 0).any():
        centres = np.array([(x / step, y / step) for x, y in seeds])
        for cy, cx in np.argwhere(coarse & (grid < 0)):
            grid[cy, cx] = int(np.argmin(np.hypot(centres[:, 0] - cx, centres[:, 1] - cy)))
    full = np.repeat(np.repeat(grid, step, axis=0), step, axis=1)[:h, :w]
    # Fine pixels whose coarse cell was empty after cropping: nearest labelled cell.
    missing = mask & (full < 0)
    if missing.any():
        _, (fy, fx) = ndimage.distance_transform_edt(full < 0, return_indices=True)
        full = np.where(missing, full[fy, fx], full)
    full[~mask] = -1
    return full
