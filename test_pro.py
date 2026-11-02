"""Extra functies 2.6: toverstaf, automatisch borduren, rand, dubbele stiklijn, applicatie, raam."""
import math, os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import numpy as np, pytest
import pyembroidery as emb
from PIL import Image, ImageDraw
import core, design, pro_tools

def square(cx=0, cy=0, r=20):
    return [dict(x=cx+x, y=cy+y, kind='corner') for x, y in [(-r, -r), (r, -r), (r, r), (-r, r)]]

def art():
    im = Image.new('RGBA', (400, 300), (255, 255, 255, 255)); d = ImageDraw.Draw(im)
    d.ellipse((40, 40, 240, 260), fill=(200, 30, 60, 255)); d.rectangle((280, 120, 300, 280), fill=(20, 90, 200, 255))
    d.ellipse((120, 130, 124, 134), fill=(205, 35, 66, 255))  # bijna dezelfde tint: moet mee met de toverstaf
    return im

def stitch_lengths(p):
    return [math.dist(a[:2], b[:2]) / 10 for a, b in zip(p.stitches, p.stitches[1:]) if (b[2] & emb.COMMAND_MASK) == emb.STITCH and (a[2] & emb.COMMAND_MASK) == emb.STITCH]

def test_double_run_goes_out_and_back():
    line = design.new_object([dict(x=0, y=0, kind='corner'), dict(x=20, y=0, kind='corner')], '#000000', 'L', fill='double', closed=False)
    design.validate_object(line); p = design.digitize_objects([line])
    xs = [round(s[0] / 10, 2) for s in p.stitches if s[2] == emb.STITCH]
    assert xs[0] == 0 and max(xs) == 20 and xs[-1] == 0 and len(xs) == 17

def test_applique_has_three_stages_and_two_stops():
    obj = design.new_object(square(), '#cc3366', 'Hart', fill='applique', satin=3); obj['holes'] = [square(r=5)]
    for tack in design.APPLIQUE_TACKS:
        obj['applique_tack'] = tack; p = design.digitize_objects([obj])
        changes = sum((c & emb.COMMAND_MASK) == emb.COLOR_CHANGE for _, _, c in p.stitches)
        assert changes == 2 and len(p.threadlist) == 3
        assert {t.color for t in p.threadlist} == {p.threadlist[0].color}
        layers = [r['layer'] for r in p.extras['route']]
        assert layers == sorted(layers, key=['under', 'top', 'satin'].index)
        assert max(stitch_lengths(p)) <= 4.81

def test_drop_short_stitches_keeps_owners_aligned_and_lengths():
    circle = [dict(x=15*math.cos(k*math.pi/8), y=15*math.sin(k*math.pi/8), kind='smooth') for k in range(16)]
    obj = design.new_object(circle, '#159552', 'Vlak', fill='fill', angle=30)
    full = design.digitize_objects([obj]); trimmed = design.digitize_objects([obj], min_stitch=.5)
    assert trimmed.extras['short_stitches_removed'] > 0 and len(trimmed.stitches) < len(full.stitches)
    assert len(trimmed.extras['owners']) == len(trimmed.stitches)
    assert max(stitch_lengths(trimmed)) <= 4.81
    assert trimmed.extras['generated_fingerprint'] == __import__('fabric').fingerprint(trimmed)
    assert min(stitch_lengths(trimmed)) >= min(stitch_lengths(full))

def test_wand_takes_similar_shade_and_fills_small_holes():
    im = art(); objs = pro_tools.wand_region(im, 100, -40, 0, tolerance=32)
    assert len(objs) == 1 and not objs[0]['holes']
    assert objs[0]['color'].startswith('#c')
    strict = pro_tools.wand_region(im, 100, -40, 0, tolerance=2, fill_holes_mm2=0)
    assert strict[0]['holes']  # zonder dichtzetten blijft het stipje een gat
    with pytest.raises(ValueError):pro_tools.wand_region(im, 100, -48, -36)  # witte achtergrond

def rect(w, h):
    return design.new_object([dict(x=x, y=y, kind='corner') for x, y in [(0, 0), (w, 0), (w, h), (0, h)]], '#159552', 'R')

def test_choose_fill_by_width_and_area():
    assert pro_tools.choose_fill(rect(.4, 30))['fill'] == 'run'
    narrow = pro_tools.choose_fill(rect(3, 30)); assert narrow['fill'] == 'column' and 1.5 <= narrow['satin'] <= 2
    assert pro_tools.choose_fill(rect(6, 30))['fill'] == 'satin_fill'
    assert pro_tools.choose_fill(rect(30, 30))['fill'] == 'fill'
    assert pro_tools.choose_fill(rect(30, 30), applique_cm2=5)['fill'] == 'applique'

def test_auto_objects_simplifies_and_classifies():
    objs, cleaned, palette = pro_tools.auto_objects(art(), 100, colors=4, min_area_mm2=1)
    assert len(objs) == 2 and len(palette) <= 4 and all(o['fill'] in ('fill', 'column', 'satin_fill', 'run') for o in objs)
    with_app, _, _ = pro_tools.auto_objects(art(), 100, colors=4, min_area_mm2=1, applique_cm2=5)
    assert 'applique' in [o['fill'] for o in with_app]
    p = design.digitize_objects(objs, min_stitch=.4); assert len(p.extras['owners']) == len(p.stitches)

@pytest.mark.parametrize('shape', ['contour', 'rect', 'oval', 'circle'])
@pytest.mark.parametrize('stitch', ['satin', 'run', 'double', 'triple'])
def test_border_keeps_distance_from_work(shape, stitch):
    work = [design.new_object(square(r=15), '#159552', 'A'), design.new_object(square(40, 0, 8), '#159552', 'B')]
    borders = pro_tools.border_objects(work, 4, 3, stitch, shape)
    assert borders and all(b['border'] and b['fill'] == stitch for b in borders)
    mask, lo = pro_tools.design_mask(work, 60)
    far = __import__('scipy.ndimage', fromlist=['x']).distance_transform_edt(~mask) / 10
    centre = 4 + (1.5 if stitch == 'satin' else 0)
    for b in borders:
        for x, y in design.flattened(b['nodes'], b.get('closed', True))[::5]:
            assert far[int((y - lo[1]) * 10), int((x - lo[0]) * 10)] >= centre - .35
    p = design.digitize_objects(work + borders)
    assert p.extras['owners'][-2] in {b['id'] for b in borders}  # rand als laatste genaaid

def test_border_rejects_bad_values():
    work = [design.new_object(square(), '#159552', 'A')]
    with pytest.raises(ValueError):pro_tools.border_objects(work, 3, 8, 'satin')
    with pytest.raises(ValueError):pro_tools.border_objects(work, 3, 3, 'zigzag')
    with pytest.raises(ValueError):pro_tools.border_objects([], 3, 3, 'satin')

def test_hoop_drawings_match_real_fields():
    assert [pro_tools.hoop_outline(i)[:2] for i in (1, 2, 3)] == [(100, 130), (145, 255), (150, 400)]
    assert all(design.HOOPS[i][1:3] == pro_tools.hoop_outline(i)[:2] for i in (1, 2, 3))
    assert pro_tools.hoop_outline(0) is None

@pytest.fixture
def window(qtbot=None):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from studio2 import Studio2
    w = Studio2(); yield w, app; w.close()

def wait(w, app):
    while w.worker and w.worker.isRunning():app.processEvents(); w.worker.wait(20)
    app.processEvents(); app.processEvents()

def test_gui_wand_auto_border_applique_roundtrip(window, tmp_path):
    from PySide6.QtCore import QPointF
    w, app = window
    w.image = art(); w.width.setValue(100); w.refresh()
    w.choose_wand(); assert w.tool.currentIndex() == w.wand_mode
    w.magic_wand(QPointF(-400, 0)); wait(w, app)
    assert len(w.objects) == 1 and w.pattern is not None
    w.undo(); assert not w.objects
    w.auto_digitize(); wait(w, app)
    assert len(w.objects) >= 2 and w.min_stitch.value() == .4 and w.pattern.extras['short_stitches_removed'] >= 0
    w.border_stitch.setCurrentIndex(w.border_stitch.findData('triple')); w.add_border(); wait(w, app)
    assert sum(o.get('border', False) for o in w.objects) == 1 and w.objects[-1]['fill'] == 'triple'
    w.add_border(); wait(w, app); assert sum(o.get('border', False) for o in w.objects) == 1  # vervangen, niet stapelen
    wide = next(o for o in w.objects if o['fill'] == 'fill')
    w.selected_object = wide['id']; w.selected_object_ids = {wide['id']}; w.selection_to_applique()
    assert wide['fill'] == 'applique'; w.launch_objects(); wait(w, app)
    assert any('Applicatie 3/3' in t.description for t in w.pattern.threadlist)
    w.toolbar_hoop.setCurrentIndex(1); assert w.presets.currentIndex() == 1 and w.hoop_choice.currentIndex() == 1
    w.true_size(); assert abs(w.canvas.transform().m11() - w.screen().logicalDotsPerInchX() / 254) < 1e-9
    path = tmp_path / 'p.bst'; core.save_project(str(path), w.image, w.palette, w.pattern, w.settings())
    w.load_path(str(path)); assert sum(o['fill'] == 'applique' for o in w.objects) == 1 and w.min_stitch.value() == .4
    w.remove_border(); wait(w, app); assert not any(o.get('border') for o in w.objects)
