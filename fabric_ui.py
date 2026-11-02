"""Fabric selection at every project save or machine export, with deferred regeneration."""
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog,QVBoxLayout,QFormLayout,QLabel,QComboBox,QCheckBox,QDialogButtonBox
import fabric,design

class FabricUI:
    def build_fabric(self):
        self.fabric_combo=QComboBox()
        for key,profile in fabric.PROFILES.items():self.fabric_combo.addItem(profile['label'],key)
        self.fabric_combo.setCurrentIndex(self.fabric_combo.findData(self.fabric_key));self.fabric_combo.currentIndexChanged.connect(self.fabric_changed)
        page=self.tabs.widget(1).widget();form=QFormLayout();page.layout().insertLayout(1,form);form.addRow('Stofprofiel',self.fabric_combo)
        self.fabric_notice=QLabel();self.fabric_notice.setWordWrap(True);self.fabric_notice.setMaximumWidth(350);form.addRow(self.fabric_notice);self.update_fabric_notice()
        self.optimize.setChecked(True);self.optimize.setEnabled(False);self.optimize.setText('Korte sprongen; vlakken en letters als geheel')
        self._after_generation_action=None;self._generation_ok=False
    def update_fabric_notice(self):
        profile=fabric.PROFILES[self.fabric_key]
        if hasattr(self,'fabric_notice'):self.fabric_notice.setText(fabric.describe(self.fabric_key))
    def fabric_changed(self,index):
        key=self.fabric_combo.currentData()
        if key and key!=self.fabric_key:
            self.fabric_key=key
            if self.objects or self.image:self.mark_objects_changed()
        self.update_fabric_notice()
    def fabric_dialog(self):
        dialog=QDialog(self);dialog.setWindowTitle('Voor welke stof wil je dit ontwerp opslaan?');dialog.setMinimumWidth(480);layout=QVBoxLayout(dialog)
        label=QLabel('Kies bij iedere opslag de stof. Bij een nieuwe omzetting past het programma rijafstand, trekcompensatie en de onderlaag aan.');label.setWordWrap(True);layout.addWidget(label)
        combo=QComboBox()
        for key,profile in fabric.PROFILES.items():combo.addItem(profile['label'],key)
        combo.setCurrentIndex(combo.findData(self.fabric_key));layout.addWidget(combo)
        description=QLabel();description.setWordWrap(True);layout.addWidget(description)
        def update():
            description.setText(fabric.describe(combo.currentData()))
        combo.currentIndexChanged.connect(update);update()
        preserve=QCheckBox('Bestaande steken behouden — stofkeuze alleen als notitie');layout.addWidget(preserve)
        imported=self.pattern is not None and not self.objects and self.image is None
        edited=bool(self.pattern and self.pattern.extras.get('generated_fingerprint') and self.pattern.extras['generated_fingerprint']!=fabric.fingerprint(self.pattern))
        preserve.setChecked(imported or edited or bool(self.pattern and self.pattern.extras.get('manual_selection_edit')));preserve.setEnabled(self.pattern is not None and not imported)
        info=QLabel('Zonder deze optie worden zo nodig nieuwe steken uit de vlakken/afbeelding gemaakt. Dat vervangt handmatige steekbewerkingen. Met deze optie veranderen dichtheid en onderlaag van bestaande steken niet. Een geïmporteerd machinebestand zonder contouren kan alleen als bestaand patroon worden bewaard.');info.setWordWrap(True);layout.addWidget(info)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return None
        return combo.currentData(),preserve.isChecked()
    def request_fabric(self,action,require_pattern=False):
        if self.worker and self.worker.isRunning():return self.error('Wacht tot het maken van steken klaar is.')
        if self.draft:return self.error('Sluit of annuleer eerst de contour.')
        choice=self.fabric_dialog()
        if choice is None:return
        key,preserve=choice;previous=self.fabric_key;self.fabric_key=key;self.fabric_combo.blockSignals(True);self.fabric_combo.setCurrentIndex(self.fabric_combo.findData(key));self.fabric_combo.blockSignals(False);self.update_fabric_notice()
        if previous!=key and (self.objects or self.image) and not preserve:self.mark_objects_changed()
        if self.pattern:self.pattern.extras['fabric_selection']=key
        if require_pattern and not preserve:
            needs=self.art_changed or not self.pattern or self.pattern.extras.get('fabric_profile')!=key or self.pattern.extras.get('routing_version')!='2.5' or (self.pattern.extras.get('generated_fingerprint') and self.pattern.extras['generated_fingerprint']!=fabric.fingerprint(self.pattern))
            if needs:
                if not self.objects and self.image:
                    try:
                        cleaned,palette=design.clean_art(self.image,self.detail_min.value(),self.width.value(),self.smooth.value(),self.color_tolerance.value())
                        objects=design.objects_from_art(cleaned,self.width.value(),self.detail_min.value())
                        for obj in objects:design.transform_object(obj,*self.image_offset);obj.update(fill=['fill','satin','both'][self.stitch_mode.currentIndex()],spacing=self.spacing.value(),length=self.length.value(),satin=self.satin_width.value(),angle=self.global_fill_angle)
                        if not objects:raise ValueError('Geen bruikbare vlakken gevonden.')
                        self.checkpoint();self.objects=objects;self.image=cleaned;self.palette=palette;self.reference_only=True;self.reference_checkbox.setChecked(True);self.refresh()
                    except Exception as e:return self.error(e)
                if self.objects:
                    self.launch_objects(after=action);return
        # If only recording the chosen material, retain the original pattern,
        # including any edits, but distinguish selected vs actually applied fabric.
        self._preserving_for_save=preserve
        try:action()
        finally:self._preserving_for_save=False
    def launch_objects(self,after=None,checkpoint=True):
        from studio2 import ObjectWorker
        if checkpoint:self.checkpoint()
        self.stop_playback();self._after_generation_action=after;self._generation_ok=False;self.set_busy(True)
        self.worker=ObjectWorker(self.generation_objects(),self.optimize.isChecked(),self.order_mode.currentIndex()==1,self.fabric_key,self.min_stitch.value() if hasattr(self,'min_stitch') else 0)
        self.worker.progress.connect(self.on_progress);self.worker.done.connect(self.generated);self.worker.failed.connect(self.failed);self.worker.finished.connect(self.fabric_generation_finished);self.worker.start()
    def fabric_generation_finished(self):
        self.set_busy(False);action=self._after_generation_action;self._after_generation_action=None
        if self._generation_ok and action:QTimer.singleShot(0,action)
