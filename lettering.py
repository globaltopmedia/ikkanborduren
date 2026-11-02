"""Editable lettering from installed outline fonts, in millimetres.
Not pre-digitised embroidery alphabets. Font outlines are traced at 0.1 mm.
"""
import math,uuid
from PIL import Image
from PySide6.QtGui import QFont,QFontMetricsF,QPainterPath,QTransform,QImage,QPainter,QColor
from PySide6.QtCore import Qt
import design

def text_objects(text,family,height=12,arc=0,tracking=1,color='#159552',bold=False,**options):
    if not text.strip():raise ValueError('Typ eerst een tekst.')
    if '\n' in text or len(text)>80:raise ValueError('Gebruik één regel met maximaal 80 tekens.')
    if not 3<=height<=80 or not -180<=arc<=180 or not 0<=tracking<=20:raise ValueError('Controleer letterhoogte, boog en letterafstand.')
    font=QFont(family);font.setPixelSize(1000);font.setBold(bold)
    cap=QPainterPath();cap.addText(0,0,font,'H');factor=height/max(1,cap.boundingRect().height())
    metrics=QFontMetricsF(font);advances=[metrics.horizontalAdvance(c)*factor for c in text]
    length=sum(advances)+tracking*(len(text)-1)
    if length>380:raise ValueError('Deze tekst is te breed. Verklein de letters of de afstand.')
    curvature=math.radians(arc)/length if arc else 0
    group=uuid.uuid4().hex;result=[];position=-length/2
    for index,(char,advance) in enumerate(zip(text,advances)):
        path=QPainterPath();path.addText(0,0,font,char)
        scaled=QTransform.fromScale(factor*10,factor*10).map(path);rect=scaled.boundingRect()
        if not path.isEmpty():
            size=(math.ceil(rect.width())+6,math.ceil(rect.height())+6)
            image=QImage(*size,QImage.Format.Format_RGBA8888);image.fill(Qt.GlobalColor.transparent)
            painter=QPainter(image);painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor(color));painter.translate(3-rect.left(),3-rect.top());painter.drawPath(scaled);painter.end()
            pixels=Image.frombytes('RGBA',size,bytes(image.constBits()),'raw','RGBA',image.bytesPerLine())
            letters=design.objects_from_art(pixels,size[0]/10,0)
            # Trace is centred on its raster. Restore the glyph's baseline origin,
            # then position and rotate each glyph about its advance centre.
            centre=(rect.left()-3+size[0]/2)/10
            cy=(rect.top()-3+size[1]/2)/10
            s=position+advance/2
            angle=curvature*s
            bx=math.sin(angle)/curvature if curvature else s
            by=(1-math.cos(angle))/curvature if curvature else 0
            for obj in letters:
                obj.update(options);obj['letter_id']=group+':'+str(index);obj['letter_index']=index;obj['text_options']=dict(text=text,family=family,height=height,arc=arc,tracking=tracking,bold=bold,color=color,fill=options.get('fill','fill'));obj.update(name=f'Letter {index+1}: {char}',color=color,text_group=group,text=text,font_family=family)
                design.transform_object(obj,dx=centre-advance/2,dy=cy)
                design.transform_object(obj,angle=math.degrees(angle),center=(0,0))
                design.transform_object(obj,dx=bx,dy=by)
                result.append(obj)
        position+=advance+tracking
    if not result:raise ValueError('Dit lettertype bevat geen bruikbare contouren voor deze tekst.')
    # Centre the visible text as one group inside the selected hoop.
    boxes=[design.object_bounds(o) for o in result];cx=(min(b[0] for b in boxes)+max(b[2] for b in boxes))/2;cy=(min(b[1] for b in boxes)+max(b[3] for b in boxes))/2
    for obj in result:design.transform_object(obj,dx=-cx,dy=-cy)
    return result
