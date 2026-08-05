# ui/components/export_dialog.py
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLineEdit, 
                               QTextEdit, QDialogButtonBox)

class ExportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Metadados do Relatório")
        self.resize(450, 350)
        
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        self.input_author = QLineEdit()
        self.input_author.setPlaceholderText("Ex: João da Silva")
        
        self.input_location = QLineEdit()
        self.input_location.setPlaceholderText("Ex: Laboratório de Física - Senac")
        
        self.input_notes = QTextEdit()
        self.input_notes.setPlaceholderText("Insira observações sobre anomalias no equipamento, temperatura ambiente, etc.")
        
        form.addRow("Autor / Pesquisador:", self.input_author)
        form.addRow("Local da Coleta:", self.input_location)
        form.addRow("Notas Adicionais:", self.input_notes)
        
        layout.addLayout(form)
        
        # Botões padrão de OK e Cancelar
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        
    def get_data(self) -> dict:
        return {
            "author": self.input_author.text().strip(),
            "location": self.input_location.text().strip(),
            "notes": self.input_notes.toPlainText().strip()
        }