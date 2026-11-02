"""Toverstaf, automatisch digitaliseren, rand rondom het ontwerp en raamgegevens.
Alle maten in millimeters; geen Qt-afhankelijkheid zodat dit los te testen is.
Zelfstandige implementatie, geen code van BERNINA of Hatch.
"""
import copy, math
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
import core, design

# Werkelijk borduurbereik (veld) van de B540-ringen in deze applicatie.
# De buitenmaat van de ring is een illustratie: veld + frame aan alle kanten.
HOOP_DRAWINGS = {
    1: dict(name='Medium', field=(100, 130), frame=13, oval=True),
    2: dict(name='Large Oval', field=(145, 255), frame=15, oval=True),
    3: dict(name='Mega Hoop', field=(150, 400), frame=17, oval=False),
}


def _pixel(image, width_mm, x_mm, y_mm):
    w, h = image.size; scale = width_mm / w
    return int(math.floor(x_mm / scale + w / 2)), int(math.floor(y_mm / scale + h / 2)), scale


def wand_region(image, width_mm, x_mm, y_mm, tolerance=32, remove_white=True,
                fill_holes_mm2=1.0, smooth_mm=0.15, contiguous=True):
    """Toverstaf: één klik selecteert het aaneengesloten gebied met een kleur
    die binnen `tolerance` (RGB-afstand 0-255) van de aangeklikte kleur valt.
    Kleine gaatjes (anti-aliasing, glimlichtjes) worden dichtgezet zodat de
    vulling één net vlak wordt. Geeft bewerkbare vectorvlakken terug."""
    rgba = np.array(image.convert('RGBA')); h, w = rgba.shape[:2]
    x, y, scale = _pixel(image, width_mm, x_mm, y_mm)
    if not (0 <= x < w and 0 <= y < h) or rgba[y, x, 3] < 128:
        raise ValueError('Klik met de toverstaf binnen een zichtbaar deel van de afbeelding.')
    seed = rgba[y, x, :3].astype(float)
    if remove_white and (seed >= 245).all():
        raise ValueError('Dit is de witte achtergrond. Zet "Witte achtergrond weghalen" uit als wit wel geborduurd moet worden.')
    distance = np.sqrt(((rgba[:, :, :3].astype(float) - seed) ** 2).sum(axis=2))
    mask = (rgba[:, :, 3] >= 128) & (distance <= float(tolerance))
    if contiguous:
        labels, _ = ndimage.label(mask); mask = labels == labels[y, x]
    radius = int(round(float(smooth_mm) / scale))
    if radius > 0:
        disk = _disk(radius)
        mask = ndimage.binary_opening(ndimage.binary_closing(mask, disk), disk) | (mask & ndimage.binary_erosion(mask, disk))
        labels, _ = ndimage.label(mask)
        if contiguous and labels[y, x]:mask = labels == labels[y, x]
    if fill_holes_mm2 > 0:
        holes = ndimage.binary_fill_holes(mask) & ~mask
        lab, n = ndimage.label(holes)
        if n:
            sizes = ndimage.sum(holes, lab, range(1, n + 1))
            small = np.where(sizes * scale * scale < fill_holes_mm2)[0] + 1
            mask |= np.isin(lab, small)
    if mask.sum() * scale * scale < .3:
        raise ValueError('Dit deel is te klein om te borduren. Vergroot het ontwerp of verhoog de tolerantie.')
    colour = tuple(int(round(v)) for v in rgba[:, :, :3][mask].mean(axis=0))
    out = np.zeros_like(rgba); out[mask, :3] = colour; out[mask, 3] = 255
    objects = design.objects_from_art(Image.fromarray(out), width_mm, .3)
    if not objects:
        raise ValueError('Dit deel is te klein om te borduren. Vergroot het ontwerp of verhoog de tolerantie.')
    return objects


def _disk(radius):
    yy, xx = np.mgrid[-radius:radius + 1, -radius:radius + 1]
    return xx * xx + yy * yy <= radius * radius


def shape_metrics(obj):
    """Grootste breedte (2 x grootste afstand tot de rand) en oppervlak in mm."""
    mask, _, _ = design.raster_object(obj, compensate=False)
    if not mask.any():return 0., 0.
    return float(ndimage.distance_transform_edt(mask).max() * 2 / 10), float(mask.sum() / 100)


def _line_network(obj, line_mm=3.5, share=.5):
    import line_fill
    mask, _, _ = design.raster_object(obj, 0, compensate=False)
    return line_fill.narrow_fraction(mask, line_mm) >= share


def choose_fill(obj, satin_max=5.0, applique_cm2=0.0):
    """Hatch-achtige automatische steekkeuze: heel smal = stiklijn, smal = satijnsteek die de vorm volgt,
    breed = tatami en (optioneel) heel groot = applicatie."""
    if not obj.get('closed', True):return obj
    width, area = shape_metrics(obj)
    if width <= .6:
        obj['fill'] = 'run'
    elif width <= 3.5:
        # Lijnen: satijnsteek die de vorm volgt (draait mee met de lijn).
        obj['fill'] = 'column'; obj['satin'] = round(min(5., max(.5, width / 2 + .2)), 2)
    elif _line_network(obj):
        # Lijnenwerk met hier en daar een dikker stuk: lijnen satijn, dikke stukken tatami.
        obj['fill'] = 'fill'; obj['narrow_mm'] = 3.5
    elif width <= satin_max * 1.6:
        # Smalle vlakken: satijn van rand tot rand in de steekrichting.
        obj['fill'] = 'satin_fill'; obj['satin'] = round(min(5., max(.5, width / 2 + .2)), 2)
    elif applique_cm2 and area >= applique_cm2 * 100:
        obj['fill'] = 'applique'; obj['satin'] = 3.; obj.setdefault('applique_tack', 'zigzag')
    else:
        obj['fill'] = 'fill'
    return obj


def auto_objects(image, width_mm, colors=6, min_area_mm2=2.0, smooth_mm=.15, remove_background=True,
                 color_tolerance=18, satin_max=5.0, applique_cm2=0.0, angle=45., spacing=.4, length=3.):
    """Eén knop: kleuren vereenvoudigen, kleine details weglaten, vlakken maken
    en per vlak de steeksoort kiezen. Geeft (objecten, schone afbeelding, palet)."""
    cleaned, palette = core.prepare_image(image, colors, remove_background)
    cleaned, palette = design.clean_art(cleaned, min_area_mm2, width_mm, smooth_mm, color_tolerance)
    objects = design.objects_from_art(cleaned, width_mm, min_area_mm2)
    kept = []
    for obj in objects:
        obj.update(angle=angle, spacing=spacing, length=length)
        try:
            design.validate_object(obj); choose_fill(obj, satin_max, applique_cm2)
        except ValueError:
            continue
        kept.append(obj)
    if not kept:raise ValueError('Geen bruikbare vlakken gevonden. Verlaag "Kleine details weglaten" of verhoog het aantal kleuren.')
    names = {'fill': 'Tatami', 'column': 'Lijn satijn', 'satin_fill': 'Satijn', 'satin': 'Satijnrand', 'run': 'Lijn', 'applique': 'Applicatie'}
    for i, obj in enumerate(kept, 1):obj['name'] = f'{"Lijnen" if obj.get("narrow_mm") else names.get(obj["fill"], "Vlak")} {i}'
    return kept, cleaned, palette


def design_mask(objects, pad_mm):
    """Rastermasker (0,1 mm) van alle zichtbare vlakken en lijnen, gaten dicht."""
    rings = []; lines = []
    for obj in objects:
        if not obj.get('visible', True) or obj.get('border'):continue
        pts = design.flattened(obj['nodes'], obj.get('closed', True))
        (rings if obj.get('closed', True) else lines).append((pts, obj))
    if not rings and not lines:raise ValueError('Teken of importeer eerst vlakken; daarna kan er een rand omheen.')
    allpts = np.array([q for pts, _ in rings + lines for q in pts])
    lo = allpts.min(axis=0) - pad_mm - 2; hi = allpts.max(axis=0) + pad_mm + 2
    size = np.ceil((hi - lo) * 10).astype(int) + 1
    if size.max() > 5000:raise ValueError('Het ontwerp is te groot voor een rand (max. 500 mm).')
    im = Image.new('L', tuple(size), 0); d = ImageDraw.Draw(im)
    px = lambda pts: [((x - lo[0]) * 10, (y - lo[1]) * 10) for x, y in pts]
    for pts, _ in rings:d.polygon(px(pts), fill=255)
    for pts, obj in lines:
        width = float(obj.get('satin', 1)) if obj.get('fill') in ('satin', 'zigzag') else .6
        d.line(px(pts), fill=255, width=max(2, int(round(width * 10))), joint='curve')
    return ndimage.binary_fill_holes(np.asarray(im) > 128), lo


def border_objects(objects, distance=3., width=3., stitch='satin', shape='contour', color='#1d3557', smooth_mm=None):
    """Rand rondom het hele ontwerp of de selectie.
    distance = afstand van de buitenrand van het werk tot de binnenkant van de rand.
    width = satijnbreedte (alleen bij satijn). stitch = satin/run/double/triple.
    shape = contour (volgt de vorm), rect, oval of circle."""
    if stitch not in ('satin', 'run', 'double', 'triple'):raise ValueError('Kies satijn, enkele, dubbele of drievoudige stiklijn.')
    if not 0 <= distance <= 50:raise ValueError('Afstand moet tussen 0 en 50 mm liggen.')
    if stitch == 'satin' and not 1 <= width <= 5:raise ValueError('Satijnbreedte moet tussen 1 en 5 mm liggen.')
    centre = distance + (width / 2 if stitch == 'satin' else 0)
    rings = []
    if shape in ('rect', 'oval', 'circle'):
        mask, lo = design_mask(objects, centre * 2 + 5)
        ys, xs = np.nonzero(mask)
        x0, x1 = xs.min() / 10 + lo[0] - centre, xs.max() / 10 + lo[0] + centre
        y0, y1 = ys.min() / 10 + lo[1] - centre, ys.max() / 10 + lo[1] + centre
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if shape == 'rect':
            rings.append([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
        else:
            rx, ry = (x1 - x0) / 2, (y1 - y0) / 2
            if shape == 'circle':rx = ry = max(rx, ry)
            # Start bij de ellips binnen het vergrote kader en groei tot de
            # middellijn overal minstens de gevraagde afstand van het werk ligt.
            far = ndimage.distance_transform_edt(~mask) / 10; minimum = centre - .05; n = 120
            for _ in range(60):
                ring = [(cx + rx * math.cos(2 * math.pi * k / n), cy + ry * math.sin(2 * math.pi * k / n)) for k in range(n)]
                if _clear_of_design(far, lo, ring, minimum):break
                rx *= 1.02; ry *= 1.02
            rings.append(ring)
    else:
        mask, lo = design_mask(objects, centre + 3)
        region = ndimage.distance_transform_edt(~mask) <= centre * 10
        # Afronden van binnenhoeken voorkomt satijnsteken die elkaar kruisen.
        radius = int(round((smooth_mm if smooth_mm is not None else max(1.5, width)) * 10))
        if radius:
            region = ndimage.binary_closing(np.pad(region, radius + 2), _disk(radius))[radius + 2:-radius - 2, radius + 2:-radius - 2]
        region = ndimage.binary_fill_holes(region)
        import contourpy
        lab, n = ndimage.label(region)
        for j in range(1, n + 1):
            part = lab == j
            if part.sum() < 50:continue
            gen = contourpy.contour_generator(z=np.pad(part.astype(float), 1), fill_type='OuterOffset')
            polygons, offsets = gen.filled(.5, 1.5)
            for pp, oo in zip(polygons, offsets):
                outer = pp[oo[0]:oo[1]] - 1
                outer = design.simplify_polyline(outer, 1.0)
                if len(outer) > 1 and np.linalg.norm(outer[0] - outer[-1]) < .01:outer = outer[:-1]
                rings.append([(x / 10 + lo[0], y / 10 + lo[1]) for x, y in outer])
    out = []
    for i, ring in enumerate(rings):
        nodes = [dict(x=float(x), y=float(y), kind='corner') for x, y in ring]
        if len(nodes) < 3:continue
        name = 'Rand rondom ontwerp' + (f' {i + 1}' if len(rings) > 1 else '')
        if stitch == 'satin':
            loop = design._ring_loop(nodes, .4) if shape in ('oval', 'circle') else copy.deepcopy(nodes) + [copy.deepcopy(nodes[0])]
            obj = design.new_object(loop, color, name, fill='satin', satin=width, spacing=.4, length=3, closed=False, underlay=True)
        else:
            obj = design.new_object(nodes, color, name, fill=stitch, length=2.5, closed=True, underlay=False)
        obj.update(border=True, border_settings=dict(distance=distance, width=width, stitch=stitch, shape=shape), stitch_phase=2)
        design.validate_object(obj); out.append(obj)
    if not out:raise ValueError('Er kon geen rand worden gemaakt.')
    return out


def _clear_of_design(far, lo, poly, minimum):
    for (ax, ay), (bx, by) in zip(poly, poly[1:] + poly[:1]):
        for t in np.linspace(0, 1, 6):
            x = int((ax + (bx - ax) * t - lo[0]) * 10); y = int((ay + (by - ay) * t - lo[1]) * 10)
            if 0 <= y < far.shape[0] and 0 <= x < far.shape[1] and far[y, x] < minimum:return False
    return True


def make_applique(obj, cover=3., tack='zigzag'):
    if not obj.get('closed', True):raise ValueError('Een applicatie heeft een gesloten vlak nodig, geen open lijn.')
    if tack not in design.APPLIQUE_TACKS:raise ValueError('Onbekende vastzetsteek.')
    obj.update(fill='applique', satin=float(cover), applique_tack=tack)
    if not obj['name'].lower().startswith('applicatie'):obj['name'] = 'Applicatie — ' + obj['name']
    return obj


def hoop_outline(index):
    """(veldbreedte, veldhoogte, framebreedte, ovaal) of None voor Eigen maat."""
    data = HOOP_DRAWINGS.get(index)
    return None if data is None else (*data['field'], data['frame'], data['oval'])
