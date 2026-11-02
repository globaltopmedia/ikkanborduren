"""2.7: dunne lijnen vullen, satijn dat de vorm volgt, richtingspijlen, onderdeel aanklikken."""
import math, time
import numpy as np
import pytest
import pyembroidery as emb
from PIL import Image, ImageDraw
from scipy import ndimage
import design, line_fill


def circle(cx, cy, r, n=48):
    return [dict(x=cx + r * math.cos(2 * math.pi * i / n), y=cy + r * math.sin(2 * math.pi * i / n), kind='corner') for i in range(n)]


def ring(width=.8, r=15, **kw):
    obj = design.new_object(circle(0, 0, r), kw.pop('color', '#000000'), 'Lijn', **kw)
    obj['holes'] = [circle(0, 0, r - width)]
    return obj


def coverage(obj, p, ids=None):
    ids = ids or {obj['id']}
    mask, lo, _ = design.raster_object(obj, 0, compensate=False)
    cov = Image.new('L', mask.shape[::-1], 0); draw = ImageDraw.Draw(cov); last = None
    for (x, y, c), owner in zip(p.stitches, p.extras['owners']):
        cmd = c & emb.COMMAND_MASK; q = ((x / 10 - lo[0]) * 10, (y / 10 - lo[1]) * 10)
        if cmd == emb.STITCH and last is not None and owner in ids:draw.line([last, q], fill=255, width=5)
        if cmd in (emb.STITCH, emb.JUMP):last = q
    inner = ndimage.binary_erosion(mask, iterations=1)
    return ((np.asarray(cov) > 0) & inner).sum() / inner.sum()


def stitch_lengths(p):
    last = None; out = []
    for x, y, c in p.stitches:
        cmd = c & emb.COMMAND_MASK
        if cmd == emb.STITCH and last is not None:out.append(math.dist(last, (x, y)) / 10)
        if cmd in (emb.STITCH, emb.JUMP):last = (x, y)
    return out


@pytest.mark.parametrize('fill', ['fill', 'column', 'both', 'satin_fill'])
def test_thin_ring_is_filled_completely(fill):
    obj = ring(.8, fill=fill, angle=45)
    p = design.digitize_objects([obj])
    assert coverage(obj, p) >= .95
    assert max(stitch_lengths(p)) <= 4.81


def test_old_tatami_left_gaps_in_thin_lines():
    # Regression guard: the bare tatami rows alone miss thin strokes crossing them.
    obj = ring(.8, fill='fill', angle=45)
    mask, lo, (c, s) = design.raster_object(obj, 45)
    wide, narrow = line_fill.split_narrow(mask)
    assert narrow.sum() > .8 * mask.sum()


def test_wide_shapes_keep_plain_tatami():
    square = design.new_object([dict(x=-10, y=-10), dict(x=10, y=-10), dict(x=10, y=10), dict(x=-10, y=10)], fill='fill')
    mask, _, _ = design.raster_object(square, 30)
    wide, narrow = line_fill.split_narrow(mask)
    assert not narrow.any()


def test_shape_with_thin_tail_gets_satin_on_the_tail():
    nodes = [dict(x=-10, y=-10), dict(x=10, y=-10), dict(x=10, y=-.4), dict(x=30, y=-.4), dict(x=30, y=.4), dict(x=10, y=.4), dict(x=10, y=10), dict(x=-10, y=10)]
    obj = design.new_object(nodes, fill='fill', angle=90)
    p = design.digitize_objects([obj])
    assert coverage(obj, p) >= .95
    # Rows at 90° cannot cover a horizontal 0.8 mm tail; the stroke satin must.
    tail = [(x, y) for x, y, c in p.stitches if (c & emb.COMMAND_MASK) == emb.STITCH and x > 150]
    assert len(tail) > 40


def test_column_stitches_cross_the_line():
    obj = ring(1.2, fill='column')
    p = design.digitize_objects([obj])
    crossings = [d for d in stitch_lengths(p) if d > .8]
    assert len(crossings) > 150 and max(stitch_lengths(p)) <= 4.81
    assert design.route_metrics(p)['jumps'] <= 1


def test_column_arrows_tilt_the_stitches():
    obj = ring(1.5, r=12, fill='column')
    plain = design.digitize_objects([obj])
    obj['direction_guides'] = [dict(x=-12, y=0, angle=45), dict(x=12, y=0, angle=-45)]
    tilted = design.digitize_objects([obj])
    assert coverage(obj, tilted) >= .95
    def mean_len(p):
        values = [d for d in stitch_lengths(p) if d > .5]
        return sum(values) / len(values)
    # Tilted crossings are longer than straight ones across the same line.
    assert mean_len(tilted) > mean_len(plain) * 1.1


def test_tatami_arrows_split_the_shape_in_directions():
    square = design.new_object([dict(x=-20, y=-10), dict(x=20, y=-10), dict(x=20, y=10), dict(x=-20, y=10)], fill='fill', angle=0)
    square['direction_guides'] = [dict(x=-15, y=0, angle=0), dict(x=15, y=0, angle=90)]
    p = design.digitize_objects([square])
    assert coverage(square, p) >= .95
    def direction(side):
        last = None; votes = []
        for x, y, c in p.stitches:
            cmd = c & emb.COMMAND_MASK
            if cmd == emb.STITCH and last is not None and math.dist(last, (x, y)) > 15 and side * x > 50 and side * last[0] > 50:
                votes.append(abs(x - last[0]) > abs(y - last[1]))
            if cmd in (emb.STITCH, emb.JUMP):last = (x, y)
        return sum(votes) / len(votes)
    assert direction(-1) > .8      # left: horizontal rows
    assert direction(1) < .2       # right: vertical rows


def test_arrows_move_with_the_shape():
    obj = ring(1, fill='column'); obj['direction_guides'] = [dict(x=5, y=0, angle=0)]
    design.transform_object(obj, dx=3, dy=2, angle=90, center=(0, 0))
    g = obj['direction_guides'][0]
    assert abs(g['x'] - 3) < 1e-9 and abs(g['y'] - 7) < 1e-9 and abs(g['angle'] - 90) < 1e-9


def test_geodesic_labels_follow_the_shape():
    mask = np.zeros((60, 200), bool); mask[5:15, 5:195] = True; mask[5:55, 185:195] = True; mask[45:55, 5:195] = True
    labels = line_fill.geodesic_labels(mask, [(10, 10), (10, 50)])
    # The lower-left end is near seed 0 in a straight line but far along the shape.
    assert labels[50, 30] == 1 and labels[10, 30] == 0


def wait(app, window):
    while window.worker and window.worker.isRunning():app.processEvents(); time.sleep(.02)
    app.processEvents()


def test_gui_click_highlight_and_direct_edits(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox, QColorDialog
    from PySide6.QtCore import QRectF, QPointF
    from PySide6.QtGui import QColor
    app = QApplication.instance() or QApplication([])
    errors = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *a: errors.append(a[2]) or 0)
    from studio2 import Studio2
    w = Studio2()
    line = ring(.8, r=15, fill='column', color='#000000'); line['name'] = 'Lijn'
    disc = design.new_object(circle(0, 0, 13), '#e5962a', 'Bol', fill='fill', angle=45)
    w.objects = [disc, line]; w.generate_all(); wait(app, w)
    assert w.pattern and not errors
    # Click on the thin line: part selected, glowing, thread row marked.
    w.tool.setCurrentIndex(0); w.select_region(QRectF(QPointF(146, 0), QPointF(147, 1)))
    assert w.current_object()['name'] == 'Lijn' and not w.parts_dock.isHidden()
    rows = [i for i in range(w.thread_list.count()) if w.thread_list.item(i).isSelected()]
    assert len(rows) == 1 and 'Lijn' in w.thread_list.item(rows[0]).text()
    assert any(item.zValue() == 4.5 for item in w.canvas.scene().items())
    # Stitch type of one part: tatami -> satin, stitches regenerated.
    w.select_region(QRectF(QPointF(0, 0), QPointF(1, 1)))
    assert w.current_object()['name'] == 'Bol'
    before = len(w.pattern.stitches)
    w.part_fill.setCurrentIndex(w.part_fill.findData('satin_fill')); w.change_part_fill(); wait(app, w)
    assert disc['fill'] == 'satin_fill' and len(w.pattern.stitches) != before and not errors
    # Colour of just this part.
    monkeypatch.setattr(QColorDialog, 'getColor', staticmethod(lambda *a, **k: QColor('#00aa44')))
    w.change_part_color(); wait(app, w)
    assert disc['color'] == '#00aa44' and line['color'] == '#000000'
    assert {t.hex_color().lower() for t in w.pattern.threadlist} == {'#00aa44', '#000000'}
    # Arrows: two directions in the disc, Enter applies both at once.
    w.start_arrows(); assert w.tool.currentIndex() == w.arrow_mode
    w.add_arrow(QPointF(-80, 0), QPointF(20, 0)); w.add_arrow(QPointF(80, 0), QPointF(80, 100))
    assert len(w.pending_arrows) == 2
    w.apply_arrows(); wait(app, w)
    assert [g['angle'] for g in disc['direction_guides']] == [0.0, 90.0] and not errors
    # Thread list click selects the parts of that colour.
    row = next(i for i in range(w.thread_list.count()) if 'Lijn' in w.thread_list.item(i).text())
    w.thread_row_clicked(w.thread_list.item(row)); assert [o['name'] for o in w.part_targets()] == ['Lijn']
    # Garenkleur wijzigen keeps the parts in step with the thread.
    monkeypatch.setattr(QColorDialog, 'getColor', staticmethod(lambda *a, **k: QColor('#123456')))
    w.thread_list.setCurrentRow(row); w.thread_color()
    assert line['color'] == '#123456'
    # Saved with the project.
    path = tmp_path / 'pijlen.bst'
    import core
    core.save_project(str(path), w.image, w.palette, w.pattern, w.settings())
    w2 = Studio2(); w2.load_path(str(path))
    loaded = next(o for o in w2.objects if o['name'] == 'Bol')
    assert len(loaded['direction_guides']) == 2
    w.close(); w2.close()


def test_knife_splits_shape_into_independent_parts():
    square = design.new_object([dict(x=-10, y=-10), dict(x=10, y=-10), dict(x=10, y=10), dict(x=-10, y=10)], '#3366cc', 'Blok', fill='fill', angle=30)
    pieces = design.split_object(square, [(0, -9), (0, 9)])   # stops short of the edge: still cuts through
    assert len(pieces) == 2 and pieces[0]['id'] == square['id'] and pieces[1]['id'] != square['id']
    assert all(p['color'] == '#3366cc' and p['fill'] == 'fill' and p['angle'] == 30 for p in pieces)
    areas = sorted((design.object_bounds(p)[2] - design.object_bounds(p)[0]) for p in pieces)
    assert all(9 < a < 11 for a in areas)
    p = design.digitize_objects(pieces)
    assert coverage(square, p, {q['id'] for q in pieces}) >= .95  # no open seam along the cut
    with pytest.raises(ValueError):design.split_object(square, [(-5, -5), (-1, -1)])


def test_gui_group_ungroup_and_knife(monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox
    from PySide6.QtCore import QRectF, QPointF
    app = QApplication.instance() or QApplication([])
    errors = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *a: errors.append(a[2]) or 0)
    from studio2 import Studio2
    w = Studio2()
    a = design.new_object(circle(-20, 0, 6), '#cc0000', 'A', fill='fill')
    b = design.new_object(circle(20, 0, 6), '#00cc00', 'B', fill='fill')
    c = design.new_object([dict(x=-10, y=20), dict(x=10, y=20), dict(x=10, y=30), dict(x=-10, y=30)], '#0000cc', 'C', fill='fill')
    w.objects = [a, b, c]; w.part_live.setChecked(False); w.refresh()
    w.tool.setCurrentIndex(0)
    w.select_region(QRectF(QPointF(-200, 0), QPointF(-199, 1)))
    w.select_region(QRectF(QPointF(200, 0), QPointF(201, 1)), True)
    w.group_parts(); assert a.get('group_id') and a['group_id'] == b['group_id'] and not errors
    w.select_region(QRectF(QPointF(0, 250), QPointF(1, 251)))       # C alone
    w.select_region(QRectF(QPointF(-200, 0), QPointF(-199, 1)))      # click A selects the whole group
    assert w.chosen_ids() == {a['id'], b['id']}
    assert any('[Groep 1]' in w.parts_list.item(i).text() for i in range(w.parts_list.count()))
    w.select_part(a['id'], single=True); assert w.chosen_ids() == {a['id']}
    w.select_part(a['id']); w.ungroup_parts(); assert 'group_id' not in a and 'group_id' not in b
    # Knife across C only.
    w.select_part(c['id']); w.start_knife(); assert w.tool.currentIndex() == w.knife_mode
    w.knife_cut([(0, 18), (0, 32)])
    names = [o['name'] for o in w.objects]
    assert len(w.objects) == 4 and 'C deel 2' in names and not errors
    w.undo(); assert len(w.objects) == 3
    w.close()
