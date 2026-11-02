import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import copy
from pathlib import Path
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication,QColorDialog
from PySide6.QtCore import QRectF,QPointF
from PySide6.QtGui import QColor
from main import Studio,open_art,Digitizer
import core

@pytest.fixture(scope='module')
def app():
    app=QApplication.instance() or QApplication([])
    yield app

@pytest.fixture
def editor(app):
    w=Studio();w.load_path(str(Path(__file__).parent/'Voorbeelden'/'Schildpad.png'))
    w.pattern=core.digitize(w.image,w.palette,60,underlay=False);w.refresh()
    yield w
    w.close()

def test_svg_import(app):
    image=open_art(str(Path(__file__).parent/'Voorbeelden'/'Strakke_lijnen.svg'))
    assert image.width>image.height and np.array(image)[:,:,3].max()==255

def test_editor_selection_move_delete_undo(editor):
    w=editor;original=copy.deepcopy(w.pattern.stitches)
    w.select_region(QRectF(-300,-400,600,800));assert len(w.selected)>1000
    w.move_selected(2,3)
    i=min(w.selected);assert w.pattern.stitches[i][0]==pytest.approx(original[i][0]+20)
    w.undo();assert w.pattern.stitches==original
    w.select_region(QRectF(-300,-400,600,800));w.delete_selected();assert core.pattern_stats(w.pattern)['stitches']==0
    w.undo();assert w.pattern.stitches==original
    w.redo();assert core.pattern_stats(w.pattern)['stitches']==0

def test_single_point_and_thread_color(editor,monkeypatch):
    w=editor;i=next(i for i,s in enumerate(w.pattern.stitches) if s[2]==0)
    w.selected={i};w.ex.setValue(12.3);w.ey.setValue(4.5);w.edit_point()
    assert w.pattern.stitches[i][:2]==[123,45]
    w.command.setCurrentIndex(1);w.change_command();assert w.pattern.stitches[i][2]==1
    monkeypatch.setattr(QColorDialog,'getColor',lambda *args:QColor('#aabbcc'))
    w.thread_list.setCurrentRow(0);w.thread_color();assert w.pattern.threadlist[0].color==0xaabbcc

def test_paint_and_erase(editor):
    w=editor;w.palette_list.setCurrentRow(0);w.brush.setValue(8)
    point=QPointF(0,0);before=np.array(w.image)
    w.checkpoint();w.paint_at(point,False);painted=np.array(w.image)
    assert np.any(before!=painted)
    w.paint_at(point,True);assert np.array(w.image)[w.image.height//2,w.image.width//2,3]==0
    w.undo();assert np.array_equal(np.array(w.image),before)

def test_large_stitch_repair_and_rotate(editor):
    w=editor;i=next(i for i,s in enumerate(w.pattern.stitches) if i>2 and s[2]==0)
    w.pattern.stitches[i][0]+=400;w.split_long();last=None
    for x,y,c in w.pattern.stitches:
        if c==0 and last is not None:assert np.hypot(x-last[0],y-last[1])<=49.001
        last=(x,y)
    old=core.pattern_stats(w.pattern);w.rotate();new=core.pattern_stats(w.pattern)
    assert new['width']==pytest.approx(old['height'])
