import copy
import pytest
from pathlib import Path
from PySide6.QtWidgets import QApplication,QInputDialog,QFileDialog,QMessageBox
import fabric,design,core
from studio2 import Studio2

@pytest.fixture(scope='module')
def app():return QApplication.instance() or QApplication([])

def square():return design.new_object([dict(x=-5,y=-5),dict(x=5,y=-5),dict(x=5,y=5),dict(x=-5,y=5)])

def test_each_project_save_asks_again_and_uses_chosen_name(app,tmp_path,monkeypatch):
    w=Studio2();w.objects=[square()];w.fabric_dialog=lambda:('terry',False)
    names=iter(['Handdoek Tobias','Handdoek David']);asked=[]
    def name_dialog(*a,**k):asked.append(k['text']);return next(names),True
    monkeypatch.setattr(QInputDialog,'getText',name_dialog)
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda parent,title,suggested,filters:(str(tmp_path/Path(suggested).name),filters))
    w.save();w.save()
    assert len(asked)==2 and asked[1]=='Handdoek Tobias'
    assert (tmp_path/'Handdoek Tobias.bst').exists() and (tmp_path/'Handdoek David.bst').exists()
    assert w.path==str(tmp_path/'Handdoek David.bst');w.close()

def test_cancel_name_keeps_existing_files(app,tmp_path,monkeypatch):
    w=Studio2();w.objects=[square()];w.fabric_dialog=lambda:('standard',False);w.path=str(tmp_path/'old.bst');Path(w.path).write_bytes(b'unchanged')
    monkeypatch.setattr(QInputDialog,'getText',lambda *a,**k:('',False))
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *a:pytest.fail('Cancel must not open a file picker'))
    w.save();assert Path(w.path).read_bytes()==b'unchanged';w.close()

def test_usb_asks_every_time_and_names_all_companions(app,tmp_path,monkeypatch):
    w=Studio2();w.objects=[square()];w.pattern=design.digitize_objects(w.objects,fabric_key='terry');w.art_changed=False;w.preferences.setValue('usb_directory',str(tmp_path));w.fabric_dialog=lambda:('terry',True)
    names=iter(['Tobias','David']);calls=[]
    monkeypatch.setattr(QInputDialog,'getText',lambda *a,**k:(calls.append(True) or next(names),True))
    monkeypatch.setattr(QMessageBox,'information',lambda *a:None)
    w.save_usb();w.save_usb();assert len(calls)==2
    for name in ('Tobias','David'):
        for ext in ('exp','inf','bmp','bst'):assert (tmp_path/f'{name}.{ext}').exists()
        assert (tmp_path/f'{name}_kleuren.txt').exists()
    w.close()

def test_new_profile_settings_apply_and_original_stays_editable():
    required={'terry','satin_fabric','jersey','polyester','lycra','denim','velour'}
    assert required<=fabric.PROFILES.keys()
    obj=square();obj['length']=5;obj['spacing']=.3;original=copy.deepcopy(obj)
    for key in required:
        out=fabric.apply([obj],key)[0];profile=fabric.PROFILES[key]
        assert out['spacing']>=profile['spacing'] and out['length']<=profile['length']
        assert out['compensation']>=profile['pull'] and out['fabric_underlay']==profile['under']
        assert all(word in fabric.describe(key) for word in ('Versteviging','Topping','Naald'))
    assert obj==original
