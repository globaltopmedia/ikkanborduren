from PySide6.QtWidgets import QWidget,QVBoxLayout,QFormLayout,QComboBox,QLabel
import contour_outline

class ContourUI:
    def build_contour(self):
        page=QWidget();lay=QVBoxLayout(page);form=QFormLayout();lay.addLayout(form)
        self.outline_scope=QComboBox();self.outline_scope.addItems(['Geselecteerde vlakken samen','Hele ontwerp']);form.addRow('Contour om',self.outline_scope)
        self.outline_kind=QComboBox();self.outline_kind.addItems(['Satijn','Stiksteken']);form.addRow('Steeksoort',self.outline_kind)
        self.outline_width=self.number(.5,5,2,' mm',2);form.addRow('Satijnbreedte',self.outline_width)
        self.outline_spacing=self.number(.3,1.5,.4,' mm',2);form.addRow('Satijn rijafstand',self.outline_spacing)
        self.outline_length=self.number(.5,5,2.5,' mm',2);form.addRow('Stiksteeklengte',self.outline_length)
        self.outline_distance=self.number(0,10,0,' mm',2);form.addRow('Afstand tot vlak',self.outline_distance)
        self.outline_kind.currentIndexChanged.connect(lambda i:(self.outline_width.setEnabled(i==0),self.outline_spacing.setEnabled(i==0),self.outline_length.setEnabled(i==1)))
        self.outline_length.setEnabled(False)
        note=QLabel('Kleinere rijafstand geeft dichter satijn; kortere steeklengte geeft meer stiksteken. Afstand is de ruimte tussen het vlak en de binnenrand van de contour. De contour gebruikt de gekozen vlak-/garenkleur en blijft apart bewerkbaar. Bij het hele ontwerp worden aansluitende vlakken samengenomen; losstaande delen krijgen een eigen contour.');note.setWordWrap(True);lay.addWidget(note)
        self.button(lay,'Contour toevoegen',self.add_outline);lay.addStretch();self.add_page(page,'Contour')
    def add_outline(self):
        if not self.objects and self.image is not None:self.trace_image()
        ids=set(self.selected_object_ids)
        if self.selected_object:ids.add(self.selected_object)
        chosen=[o for o in self.objects if not o.get('outline_settings') and (self.outline_scope.currentIndex()==1 or o['id'] in ids)]
        try:
            outlines=contour_outline.make_outlines(chosen,kind=['satin','run'][self.outline_kind.currentIndex()],width=self.outline_width.value(),spacing=self.outline_spacing.value(),distance=self.outline_distance.value(),length=self.outline_length.value(),color=self.object_color)
            self.checkpoint();self.objects.extend(outlines);self.generation_scope=None;self.selected_object=outlines[0]['id'];self.selected_object_ids={o['id'] for o in outlines};self.mark_objects_changed();self.refresh();self.sync_object_controls()
        except Exception as e:self.error(e)
