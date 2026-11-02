"""Downloaded files and hidden previews must import without Paint."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import copy

import pytest
from PIL import Image
from PySide6.QtCore import QMimeData, QStandardPaths, QUrl
from PySide6.QtWidgets import QApplication, QFileDialog, QGraphicsPixmapItem, QMessageBox

import design
import core
from studio2 import Studio2


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app):
    w = Studio2()
    w.error = lambda message: pytest.fail(str(message))
    w.show()
    app.processEvents()
    QApplication.clipboard().clear()
    yield w
    QApplication.clipboard().clear()
    w.close()


def drawing(path):
    image = Image.new('RGBA', (24, 12), (0, 0, 0, 0))
    image.paste((255, 0, 0, 255), (0, 0, 9, 12))
    image.paste((0, 131, 65, 255), (15, 0, 24, 12))
    image.save(path)
    return image


def copy_files(*paths):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])
    QApplication.clipboard().setMimeData(mime)


def visible_drawing(w):
    return any(isinstance(item, QGraphicsPixmapItem) for item in w.canvas.scene().items())


def existing_design(w):
    w.objects = [design.new_object([
        {'x': -4, 'y': -3, 'kind': 'corner'},
        {'x': 4, 'y': -3, 'kind': 'corner'},
        {'x': 4, 'y': 3, 'kind': 'corner'},
        {'x': -4, 'y': 3, 'kind': 'corner'},
    ], '#ff0000', 'vlak', fill='fill', underlay=False)]
    w.pattern = design.digitize_objects(w.objects, optimize=False)
    return copy.deepcopy(w.objects), copy.deepcopy(w.pattern.stitches)


def test_open_file_starts_in_downloads_and_restores_preview(window, tmp_path, monkeypatch):
    path = tmp_path / 'gedownloade tekening.png'
    drawing(path)
    window.show_art.setChecked(False)
    directories = []

    def choose_file(parent, title, directory, filters):
        directories.append(directory)
        return str(path), ''

    monkeypatch.setattr(QFileDialog, 'getOpenFileName', choose_file)
    window.open_file()
    assert directories == [QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)]
    assert window.image.size == (24, 12)
    assert window.show_art.isChecked()
    assert visible_drawing(window)
    assert 'Tekening geopend' in window.status.text()


def test_copy_downloaded_png_with_spaces_and_unicode_and_undo(window, tmp_path, monkeypatch):
    path = tmp_path / 'bloem met cafés.png'
    drawing(path)
    objects, stitches = existing_design(window)
    window.show_art.setChecked(False)
    copy_files(path)
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    window.paste_art()
    assert window.image.size == (24, 12)
    assert window.image.getpixel((4, 6)) == (255, 0, 0, 255)
    assert window.image.getpixel((12, 6))[3] == 0
    assert window.pattern is None and not window.objects
    assert window.show_art.isChecked() and visible_drawing(window)
    assert 'Tekening geopend' in window.status.text()
    window.undo()
    assert window.objects == objects
    assert window.pattern.stitches == stitches


def test_copy_local_svg_uses_drawing_not_file_icon(window, tmp_path):
    path = tmp_path / 'logo.svg'
    path.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20"><rect x="5" y="5" width="25" height="10" fill="#008341"/></svg>', encoding='utf-8')
    copy_files(path)
    window.paste_art()
    assert window.image.width > window.image.height
    assert (0, 131, 65) in window.palette
    assert visible_drawing(window)


@pytest.mark.parametrize('kind', ['corrupt', 'missing', 'multiple'])
def test_invalid_clipboard_file_preserves_design(window, tmp_path, kind):
    objects, stitches = existing_design(window)
    path = tmp_path / 'niet-leesbaar.png'
    path.write_text('geen afbeelding', encoding='utf-8')
    if kind == 'missing':
        path = tmp_path / 'ontbreekt.png'
    copy_files(path, tmp_path / 'tweede.png') if kind == 'multiple' else copy_files(path)
    errors = []
    window.error = errors.append
    history = len(window.history)
    window.paste_art()
    assert len(errors) == 1
    assert window.objects == objects and window.pattern.stitches == stitches
    assert len(window.history) == history


def test_cancel_file_paste_preserves_design(window, tmp_path, monkeypatch):
    objects, stitches = existing_design(window)
    path = tmp_path / 'logo.png'
    drawing(path)
    copy_files(path)
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.No)
    window.paste_art()
    assert window.objects == objects and window.pattern.stitches == stitches




def test_prepare_image_preserves_exact_flat_colors_and_white():
    image = Image.new("RGBA", (4, 1))
    image.putdata([
        (255, 255, 255, 255),
        (0, 0, 0, 255),
        (255, 255, 0, 255),
        (255, 255, 255, 0),
    ])
    prepared, palette = core.prepare_image(image, colors=8, remove_background=False)
    assert prepared.getpixel((0, 0)) == (255, 255, 255, 255)
    assert prepared.getpixel((1, 0)) == (0, 0, 0, 255)
    assert prepared.getpixel((2, 0)) == (255, 255, 0, 255)
    assert (255, 255, 255) in palette
    assert (0, 0, 0) in palette
    assert (255, 255, 0) in palette
