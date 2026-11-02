"""Optional self-test after installation; no machine connection required."""
from pathlib import Path
import sys,tempfile,traceback
from PIL import Image,ImageDraw
import core,pyembroidery as emb
from PySide6.QtWidgets import QApplication
from main import open_art
from studio2 import Studio2
import design

def check():
    app=QApplication([]);w=Studio2()
    im=Image.new('RGBA',(120,80),'white');d=ImageDraw.Draw(im);d.rectangle((10,10,50,65),fill='green');d.ellipse((65,15,110,65),fill='red')
    image,palette=core.prepare_image(im,3,True)
    with tempfile.TemporaryDirectory() as directory:
        base=Path(directory)
        for mode in ('fill','satin','both'):
            p=core.digitize(image,palette,60,mode=mode,satin_width=5,max_stitch=5)
            for fmt in ('exp','pes'):
                out=core.export_bundle(p,base/f'{mode}.{fmt}',100,100,False,2,fmt)
                assert core.pattern_stats(emb.read(str(out)))['stitches']>0
        core.save_project(base/'test.bst',image,palette,p,{'width':60})
        image2,palette2,p2,settings=core.load_project(base/'test.bst');assert p2.stitches==p.stitches
        core.vectorize(image,base/'test.svg');assert open_art(base/'test.svg').width>0
    obj=design.new_object([dict(x=-10,y=-10),dict(x=10,y=-10),dict(x=10,y=10),dict(x=-10,y=10)],fill='both')
    p=design.digitize_objects([obj]);assert len(p.extras['owners'])==len(p.stitches)
    w.close();print('OK: scherm, afbeeldingen, satijn/vulling, project, SVG en EXP/PES werken.')
    print('Dit is een softwarecontrole, geen fysieke borduurtest op je machine.')

if __name__=='__main__':
    try:check()
    except Exception:traceback.print_exc();sys.exit(1)
