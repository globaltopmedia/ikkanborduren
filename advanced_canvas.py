from PySide6.QtCore import Qt,QPointF
import math
from studio2 import VectorCanvas

class AdvancedCanvas(VectorCanvas):
    def __init__(self,editor):super().__init__(editor);self.direction_drag=False;self.shape_start=None;self.lasso_drag=False;self.lasso_last=None
    def mousePressEvent(self,event):
        e=self.editor;mode=e.tool.currentIndex();p=self.mapToScene(event.position().toPoint())
        if mode in getattr(e,'hole_mark_modes',set()) and event.button() in (Qt.MouseButton.LeftButton,Qt.MouseButton.RightButton):
            if not e.hole_operation:e.start_hole_mark('cut' if mode==e.hole_cut_mode else 'close')
            if e.hole_operation:e.add_node(p,event.button()==Qt.MouseButton.RightButton)
            return
        if mode==getattr(e,'wand_mode',-1) and event.button()==Qt.MouseButton.LeftButton:e.magic_wand(p);return
        if event.button()==Qt.MouseButton.LeftButton:
            if e.show_direction.isChecked() and e.current_object():
                _,end,_,_=e.direction_geometry();distance=self.mapFromScene(end)-event.position().toPoint()
                if distance.manhattanLength()<=15:self.direction_drag=True;return
            if mode==9:
                if e.direction_scope.currentIndex()==0 and not e.current_object() and e.objects:e.pick_object(p)
                self.direction_drag=True;e.drag_direction(p);return
            if mode==8:
                e.lasso_points.append((p.x(),p.y()));self.lasso_drag=True;self.lasso_last=event.position();e.refresh();return
            if mode==10:e.click_and_sew(p);return
            if mode in (11,12,13):self.shape_start=p;e.shape_preview=(mode,p,p);e.refresh();return
        super().mousePressEvent(event)
    def mouseMoveEvent(self,event):
        e=self.editor;p=self.mapToScene(event.position().toPoint())
        if self.direction_drag:e.drag_direction(p);return
        if self.shape_start is not None:e.shape_preview=(e.tool.currentIndex(),self.shape_start,p);e.refresh();return
        if self.lasso_drag and (event.position()-self.lasso_last).manhattanLength()>4:
            e.lasso_points.append((p.x(),p.y()));self.lasso_last=event.position();e.refresh();return
        super().mouseMoveEvent(event)
    def mouseReleaseEvent(self,event):
        e=self.editor
        if self.direction_drag:self.direction_drag=False;e.refresh();return
        if self.shape_start is not None:
            a=self.shape_start;b=self.mapToScene(event.position().toPoint());self.shape_start=None;e.shape_preview=None;e.make_shape(e.tool.currentIndex(),a,b);return
        if self.lasso_drag:
            self.lasso_drag=False
            if len(e.lasso_points)>5:e.finish_lasso(bool(event.modifiers()&Qt.KeyboardModifier.ControlModifier))
            return
        super().mouseReleaseEvent(event)
    def keyPressEvent(self,event):
        e=self.editor
        if e.tool.currentIndex() in getattr(e,'hole_mark_modes',set()):
            if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter):e.finish_hole_mark();return
            if event.key()==Qt.Key.Key_Escape:e.cancel_hole_mark();return
            if event.key() in (Qt.Key.Key_Backspace,Qt.Key.Key_Delete):e.pop_node();return
        if self.editor.tool.currentIndex()==8:
            if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter) and e.lasso_points:self.editor.finish_lasso(bool(event.modifiers()&Qt.KeyboardModifier.ControlModifier));return
            if event.key()==Qt.Key.Key_Escape:self.editor.lasso_points=[];self.editor.refresh();return
            if event.key()==Qt.Key.Key_Backspace and self.editor.lasso_points:self.editor.lasso_points.pop();self.editor.refresh();return
        if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter) and not e.draft:
            e.apply_direction();return
        super().keyPressEvent(event)
    def mouseDoubleClickEvent(self,event):
        if self.editor.tool.currentIndex() in getattr(self.editor,'hole_mark_modes',set()):return
        if self.editor.tool.currentIndex()==8:self.editor.finish_lasso();return
        super().mouseDoubleClickEvent(event)
