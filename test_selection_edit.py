import os,copy
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import numpy as np
import pytest,pyembroidery as emb
from PIL import Image
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtCore import QRectF,QPointF,Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from studio2 import Studio2
import core,design

@pytest.fixture(scope='module')
def app():return QApplication.instance() or QApplication([])
@pytest.fixture
def w(app):
 window=Studio2();window.error=lambda msg:pytest.fail(str(msg));window.show();app.processEvents()
 yield window
 window.close()

def pattern():
 p=emb.EmbPattern();p.add_thread('#ff0000')
 for x,y in [(-40,-20),(-20,20),(20,-20),(40,20)]:p.add_stitch_absolute(emb.STITCH,x,y)
 p.add_stitch_absolute(emb.END,40,20);return p

def stitched_colors(p):
 result=[];block=0
 for x,y,c in p.stitches:
  if c&emb.COMMAND_MASK==emb.COLOR_CHANGE:block+=1
  if c&emb.COMMAND_MASK==emb.STITCH:result.append((x,y,p.threadlist[block].color))
 return result

def rectangle(x0,y0,x1,y1,color='#ff0000'):
 return design.new_object([{'x':x,'y':y,'kind':'corner'} for x,y in [(x0,y0),(x1,y0),(x1,y1),(x0,y1)]],color,'vlak',fill='fill',underlay=False)

def test_rotate_stitches_art_and_undo(w):
 w.image=Image.fromarray(np.array([[[255,0,0,255],[0,255,0,255],[0,0,255,255]],[[255,255,0,255],[0,255,255,255],[255,0,255,255]]],dtype=np.uint8));w.width.setValue(30)
 w.pattern=pattern();old=copy.deepcopy(w.pattern.stitches);original=np.array(w.image)
 w.rotate()
 assert np.array_equal(np.array(w.image),np.rot90(original,k=-1))
 assert w.width.value()==pytest.approx(20)
 assert w.pattern.stitches[0][:2]==[20,-40]
 w.undo();assert np.array_equal(np.array(w.image),original);assert w.pattern.stitches==old;assert w.width.value()==30
 w.redo();assert w.pattern.stitches[0][:2]==[20,-40]
 for _ in range(3):w.rotate()
 assert np.array_equal(np.array(w.image),original);assert w.image_offset==pytest.approx([0,0])

def test_mouse_drag_multiple_points_move_once(w,app):
 w.pattern=pattern();w.selection_mode.setCurrentIndex(1);w.refresh();w.fit();app.processEvents()
 a=w.canvas.mapFromScene(QPointF(-50,-30));b=w.canvas.mapFromScene(QPointF(0,30))
 QTest.mousePress(w.canvas.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,a)
 QTest.mouseMove(w.canvas.viewport(),b)
 QTest.mouseRelease(w.canvas.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,b)
 assert w.selected=={0,1}
 old=copy.deepcopy(w.pattern.stitches);w.tool.setCurrentIndex(1)
 a=w.canvas.mapFromScene(QPointF(0,0));b=w.canvas.mapFromScene(QPointF(50,30))
 delta=w.canvas.mapToScene(b)-w.canvas.mapToScene(a)
 QTest.mousePress(w.canvas.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,a)
 QTest.mouseMove(w.canvas.viewport(),b)
 QTest.mouseRelease(w.canvas.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,b)
 for i in (0,1):assert w.pattern.stitches[i][:2]==pytest.approx([old[i][0]+delta.x(),old[i][1]+delta.y()])
 assert w.pattern.stitches[2:]==old[2:]

def test_group_owned_stitches_and_contours(w):
 w.objects=[rectangle(-8,-4,-2,4),rectangle(2,-4,8,4)]
 w.pattern=design.digitize_objects(w.objects,optimize=False)
 w.select_region(QRectF(-100,-60,200,120));assert len(w.chosen_ids())==2
 old=[list(s) for s in w.pattern.stitches];before=copy.deepcopy(w.objects)
 w.move_selected(3,5)
 for i,s in enumerate(w.pattern.stitches):
  if s[2]&emb.COMMAND_MASK in (emb.STITCH,emb.JUMP):assert s[:2]==pytest.approx([old[i][0]+30,old[i][1]+50])
 assert w.objects[0]['nodes'][0]['x']==before[0]['nodes'][0]['x']+3
 assert not w.art_changed
 w.rotate_selection();assert w.objects[0]['angle']==pytest.approx(90)
 assert len(w.pattern.extras['owners'])==len(w.pattern.stitches)

def test_selected_color_only_and_export_roundtrip(w,tmp_path):
 w.pattern=pattern();w.selected={1,2};w.set_selection_color('#00ff00')
 assert [c for x,y,c in stitched_colors(w.pattern)]==[0xff0000,0x00ff00,0x00ff00,0xff0000]
 assert len(w.selected)==2
 out=tmp_path/'selectie.exp';core.export_bundle(w.pattern,out,145,255,False,2,'exp')
 p=emb.read(str(out));points=[s[:2] for s in p.stitches if s[2]&emb.COMMAND_MASK==emb.STITCH]
 assert all([x,y] in points for x,y in [(-40,-20),(-20,20),(20,-20),(40,20)])
 assert sum(s[2]&emb.COMMAND_MASK==emb.COLOR_CHANGE for s in p.stitches)==2
 last=None
 for x,y,c in p.stitches:
  if last is not None and c&emb.COMMAND_MASK==emb.STITCH:assert np.linalg.norm(np.array([x,y])-last)<=50
  if c&emb.COMMAND_MASK in (emb.STITCH,emb.JUMP):last=np.array([x,y])
 w.undo();assert all(c==0xff0000 for x,y,c in stitched_colors(w.pattern))

def test_object_and_art_recolor_does_not_change_same_color_neighbour(w):
 w.image=Image.new('RGBA',(20,10),(255,0,0,255));w.width.setValue(20)
 w.objects=[rectangle(-10,-5,-1,5),rectangle(1,-5,10,5)]
 w.pattern=design.digitize_objects(w.objects,optimize=False)
 w.select_region(QRectF(-110,-60,105,120));assert len(w.chosen_ids())==1
 w.set_selection_color('#00ff00')
 assert w.objects[0]['color']=='#00ff00';assert w.objects[1]['color']=='#ff0000'
 assert w.image.getpixel((2,5))[:3]==(0,255,0);assert w.image.getpixel((18,5))[:3]==(255,0,0)
 owners=w.pattern.extras['owners'];cols=stitched_colors(w.pattern)
 # All stitches in the right-hand object keep the original thread.
 assert all(c==0xff0000 for x,y,c in cols if x>10)


def test_size_ratio_and_actual_dimensions(w):
 w.pattern=pattern();w.refresh()
 assert '8.00 × 4.00 mm' in w.size_label.text()
 w.edit_width.setValue(16);assert w.edit_height.value()==8
 w.apply_size();b=w.edit_bounds(True);assert b[2]-b[0]==16;assert b[3]-b[1]==8
 w.undo();w.lock_ratio.setChecked(False);w.edit_width.setValue(16);w.edit_height.setValue(4);w.apply_size()
 b=w.edit_bounds(True);assert b[2]-b[0]==16;assert b[3]-b[1]==4


def test_paste_clipboard_image_and_undo(w,app,monkeypatch):
 w.pattern=pattern();old=copy.deepcopy(w.pattern.stitches)
 q=QImage(17,8,QImage.Format.Format_RGBA8888);q.fill(0xffff0000);QApplication.clipboard().setImage(q)
 monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.StandardButton.Yes)
 w.paste_art();assert w.image.size==(17,8);assert w.pattern is None;assert not w.objects
 w.undo();assert w.pattern.stitches==old;assert w.image is None


def test_raster_partial_move_undo_and_project_offsets(w,tmp_path):
 w.image=Image.new('RGBA',(20,10),(0,0,0,0));w.image.putpixel((2,5),(255,0,0,255));w.image.putpixel((17,5),(0,0,255,255));w.width.setValue(20)
 w.selection_mode.setCurrentIndex(2);w.select_region(QRectF(-100,-50,80,100));original=np.array(w.image)
 w.move_selected(-3,0)
 x0,y0,x1,y1=w.image_bounds_mm();unit=w.width.value()/w.image.width
 assert w.image.getpixel((round((-11-x0)/unit),round((0-y0)/unit)))==(255,0,0,255)
 assert w.image.getpixel((round((7-x0)/unit),round((0-y0)/unit)))==(0,0,255,255)
 assert w.image_offset[0]!=0
 path=tmp_path/'offset.bst';core.save_project(path,w.image,w.palette,w.pattern,w.settings())
 other=Studio2();other.load_path(str(path));assert other.image_offset==pytest.approx(w.image_offset);other.close()
 w.undo();assert np.array_equal(np.array(w.image),original);assert w.image_offset==[0,0]


def test_direction_toggle_and_small_screen(w,app):
 assert not w.show_direction.isChecked()
 action=next(a for t in w.findChildren(__import__('PySide6.QtWidgets',fromlist=['QToolBar']).QToolBar) for a in t.actions() if a.text()=='Steekrichting')
 action.trigger();assert w.show_direction.isChecked();action.trigger();assert not w.show_direction.isChecked()
 w.compact_screen();w.resize(1024,700);app.processEvents();assert w.minimumSizeHint().width()<=1024
 assert not w.parts_dock.isVisible();assert not w.stitches_dock.isVisible()
 assert all(not b.icon().isNull() for b in w.findChildren(__import__('PySide6.QtWidgets',fromlist=['QPushButton']).QPushButton))

def test_existing_rotation_button_also_updates_reference(w):
 w.image=Image.new('RGBA',(20,10),(255,0,0,255));w.width.setValue(20)
 w.objects=[rectangle(-10,-5,10,5)];w.pattern=design.digitize_objects(w.objects,optimize=False)
 w.select_all();w.object_scale.setValue(100);w.object_rotation.setValue(90);w.scale_rotate_object()
 assert w.image.size==(10,20);assert w.width.value()==pytest.approx(10)
 assert w.objects[0]['angle']==pytest.approx(90)

def test_manual_selection_edits_preserved_by_default(w,monkeypatch):
 from PySide6.QtWidgets import QDialog,QCheckBox
 w.pattern=pattern();w.selected={1};w.set_selection_color('#00ff00')
 w.image=Image.new('RGBA',(20,10),(255,0,0,255))
 def inspect(dialog):
  preserve=next(c for c in dialog.findChildren(QCheckBox) if c.text().startswith('Bestaande steken behouden'))
  assert preserve.isChecked();return QDialog.DialogCode.Rejected
 monkeypatch.setattr(QDialog,'exec',inspect)
 assert w.fabric_dialog() is None
