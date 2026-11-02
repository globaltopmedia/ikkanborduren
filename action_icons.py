"""Small high-contrast vector icons, always accompanied by Dutch labels."""
from pathlib import Path
from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QPushButton, QToolBar

DRAWINGS = {
 'overlap':'<path d="M2 9h7v6h6v7H2z" fill="#e6e6e6"/><rect x="9" y="2" width="13" height="13" fill="#edb248"/><path d="M3 17h8M3 20h8M12 6h7M12 10h7"/><path d="M5 5l2 2M7 5L5 7" stroke="#a24c22"/>',
 'hole':'<rect x="2" y="2" width="20" height="20"/><circle cx="12" cy="12" r="6" stroke-dasharray="2 2"/>',
 'close_hole':'<rect x="2" y="2" width="20" height="20"/><circle cx="12" cy="12" r="6"/><path d="M8 12h8M12 8v8"/>',
 'select':'<rect x="4" y="4" width="16" height="16" stroke-dasharray="3 2"/><path d="M9 8v11l3-3 3 5 2-1-3-5 4-1z" fill="#087862"/>',
 'move':'<path d="M12 2v20M2 12h20M8 6l4-4 4 4M8 18l4 4 4-4M6 8l-4 4 4 4M18 8l4 4-4 4"/>',
 'rotate':'<path d="M5 8a8 8 0 1 1 0 9M5 2v6h6"/><rect x="9" y="10" width="7" height="5"/>',
 'paste':'<rect x="6" y="4" width="14" height="18" rx="2"/><rect x="9" y="2" width="8" height="4" rx="1" fill="white"/><path d="M10 11h6M10 15h6M10 19h4"/>',
 'color':'<path d="M12 2C9 7 5 11 5 15a7 7 0 0 0 14 0c0-4-4-8-7-13z" fill="#edb248"/><path d="M8 15a4 4 0 0 0 4 4"/>',
 'size':'<rect x="7" y="7" width="14" height="14"/><path d="M7 3h14M7 1v4M21 1v4M3 7v14M1 7h4M1 21h4"/>',
 'direction':'<path d="M3 20L20 3M12 3h8v8M3 10l7 7M7 6l7 7"/>',
 'save':'<path d="M3 3h15l3 3v15H3z"/><path d="M7 3v6h10V3M7 21v-8h10v8"/>',
 'open':'<path d="M2 7V4h8l3 3h9v14H2zM2 10h20"/>',
 'undo':'<path d="M3 9h11a7 7 0 0 1 0 14M3 3v6h6"/>',
 'redo':'<path d="M21 9H10a7 7 0 0 0 0 14M21 3v6h-6"/>',
 'delete':'<path d="M4 6h16M9 2h6v4M6 6l1 16h10l1-16M10 10v8M14 10v8"/>',
 'draw':'<path d="M3 21l2-7L17 2l5 5-12 12zM5 14l5 5M3 21l7-2"/>',
 'stitch':'<path d="M2 4l5 5 5-5 5 5 5-5M2 13l5 5 5-5 5 5 5-5"/>',
 'view':'<path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z"/><circle cx="12" cy="12" r="3"/>',
 'compact':'<rect x="2" y="3" width="20" height="18" rx="1"/><path d="M7 3v18M17 3v18M10 8l-3 4 3 4M14 8l3 4-3 4"/>',
 'play':'<path d="M6 3l15 9-15 9z"/>',
 'action':'<circle cx="12" cy="12" r="9"/><path d="M8 12h8M12 8v8"/>',
 'wand':'<path d="M3 21L15 9M13 7l4 4"/><path d="M18 2v4M16 4h4M21 8v3M19.5 9.5h3M10 2v2M9 3h2" stroke="#d08a00"/>',
 'auto':'<rect x="3" y="3" width="18" height="18" rx="3"/><path d="M7 16l3-8 3 8M8 13h4M16 8v8" />',
 'border':'<rect x="2" y="2" width="20" height="20" rx="6" stroke-width="2.6"/><circle cx="12" cy="12" r="4" fill="#edb248"/>',
 'applique':'<path d="M4 8l8-5 8 5v8l-8 5-8-5z" fill="#f3c8d6"/><path d="M4 8l8-5 8 5v8l-8 5-8-5z" stroke-dasharray="2 1.5"/>',
 'knife':'<path d="M3 21L14 10l3 3-11 9z" fill="#edb248"/><path d="M14 10l6-7 1 1-4 9"/><path d="M2 14l3-3M9 3l-2 6" stroke-dasharray="2 2"/>',
 'group':'<rect x="2" y="2" width="20" height="20" rx="2" stroke-dasharray="3 2"/><rect x="5" y="5" width="7" height="7" fill="#edb248"/><circle cx="15.5" cy="15.5" r="3.5" fill="#9fd3c7"/>',
 'hoop':'<ellipse cx="12" cy="12" rx="8" ry="10"/><ellipse cx="12" cy="12" rx="5.5" ry="7.5" stroke-dasharray="2 2"/><path d="M20 10h3v4h-3"/>',
}

def key(text):
 t=text.lower()
 if t=='mes' or t.startswith('mes:') or t.startswith('mes ('):return 'knife'
 if 'groep' in t or 'groeperen' in t:return 'group'
 if 'overlap uitsnijden' in t:return 'overlap'
 if 'steekrichting' in t:return 'direction'
 if 'gat' in t:return 'close_hole' if 'sluit' in t else 'hole'
 for words,k in [(['toverstaf'],'wand'),(['automatisch borduren'],'auto'),(['applicatie','snijpatroon'],'applique'),(['rand toevoegen','rand verwijderen','randkleur'],'border'),(['ware grootte','borduurraam'],'hoop'),(['ongedaan'],'undo'),(['opnieuw'],'redo'),(['plakken'],'paste'),(['90°','draai'],'rotate'),(['richting','hoek'],'direction'),(['verplaatsen','centreren'],'move'),(['kleur'],'color'),(['maat','breedte','schaal'],'size'),(['selecteren','selectie','selectielijn'],'select'),(['opslaan','bewaren','export','usb'],'save'),(['openen'],'open'),(['verwijder','gum','annuleren'],'delete'),(['compact','kolom'],'compact'),(['beeld','tonen','zichtbaar'],'view'),(['afspelen','pauze','stap'],'play'),(['teken','vlak','contour','vorm'],'draw'),(['steek','borduur','patroon'],'stitch')]:
  if any(w in t for w in words):return k
 return 'action'

def install_icons(editor):
 folder=Path(__file__).resolve().parent/'Pictogrammen';folder.mkdir(exist_ok=True)
 for name,drawing in DRAWINGS.items():
  path=folder/(name+'.svg')
  if not path.exists():path.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><g fill="none" stroke="#087862" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'+drawing+'</g></svg>',encoding='utf-8')
 icons={k:QIcon(str(folder/(k+'.svg'))) for k in DRAWINGS}
 for button in editor.findChildren(QPushButton):
  button.setIcon(icons[key(button.text())]);button.setIconSize(QSize(22,22));button.setToolTip(button.text())
 for toolbar in editor.findChildren(QToolBar):
  toolbar.setToolButtonStyle(__import__('PySide6.QtCore',fromlist=['Qt']).Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
  toolbar.setIconSize(QSize(22,22))
  for action in toolbar.actions():action.setIcon(icons[key(action.text())]);action.setToolTip(action.text())
 for action in editor.findChildren(__import__('PySide6.QtGui',fromlist=['QAction']).QAction):
  if action.text() and not action.menu():action.setIcon(icons[key(action.text())])
 for i in range(editor.tool.count()):editor.tool.setItemIcon(i,icons[key(editor.tool.itemText(i))])
 editor.setStyleSheet(editor.styleSheet()+' QPushButton {text-align:left;padding:5px;}')
