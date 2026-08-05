# ui/tabs/tab_references.py
"""Aba de Referências: os documentos em que este software se baseia."""
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QGroupBox, QPushButton, QScrollArea, QFrame,
                               QMessageBox)
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices

from content.referencias import REFERENCIAS, PASTA_DOCS, Referencia


class TabReferences(QWidget):
    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        cabecalho = QLabel(
            "Documentos que fundamentam este software. A cópia local fica em "
            f"<code>{PASTA_DOCS.name}/</code>, e o caminho oficial de acesso está "
            "ao lado de cada item — use-o para citar ou para conferir se houve "
            "revisão do documento."
        )
        cabecalho.setWordWrap(True)
        cabecalho.setTextFormat(Qt.RichText)
        layout.addWidget(cabecalho)

        # As fichas são longas: vão dentro de uma área rolável.
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)

        conteudo = QWidget()
        layout_conteudo = QVBoxLayout(conteudo)
        layout_conteudo.setSpacing(12)

        for ref in REFERENCIAS:
            layout_conteudo.addWidget(self._construir_ficha(ref))

        layout_conteudo.addStretch()
        area.setWidget(conteudo)
        layout.addWidget(area)

        rodape = QLabel(
            "Os PDFs da Tektronix guardados em Docs/ foram conferidos por MD5 "
            "contra o arquivo servido por download.tek.com e são idênticos. "
            "O artigo do RBEF é de acesso aberto."
        )
        rodape.setWordWrap(True)
        rodape.setStyleSheet("color: #a0a0a0; font-size: 11px;")
        layout.addWidget(rodape)

    def _construir_ficha(self, ref: Referencia) -> QGroupBox:
        caixa = QGroupBox(ref.titulo)
        caixa_layout = QVBoxLayout(caixa)

        def linha(rotulo: str, valor: str) -> QLabel:
            etiqueta = QLabel(f"<b>{rotulo}:</b> {valor}")
            etiqueta.setWordWrap(True)
            etiqueta.setTextFormat(Qt.RichText)
            return etiqueta

        caixa_layout.addWidget(linha("Autoria", ref.autoria))
        caixa_layout.addWidget(linha("Publicação", ref.publicacao))
        caixa_layout.addWidget(linha("Identificador", ref.identificador))
        caixa_layout.addWidget(linha("Acesso", ref.acesso))

        uso = QLabel(ref.uso_no_software)
        uso.setWordWrap(True)
        uso.setStyleSheet("padding: 6px 0px;")
        caixa_layout.addWidget(uso)

        if ref.trechos_usados:
            itens = "".join(f"<li>{t}</li>" for t in ref.trechos_usados)
            trechos = QLabel(f"<b>O que este software usa daqui:</b><ul>{itens}</ul>")
            trechos.setWordWrap(True)
            trechos.setTextFormat(Qt.RichText)
            caixa_layout.addWidget(trechos)

        # Caminho oficial — clicável, e também visível como texto para citação.
        oficial = QLabel(
            f'<b>Caminho oficial:</b> <a href="{ref.url_documento}">{ref.url_documento}</a>'
        )
        oficial.setWordWrap(True)
        oficial.setTextFormat(Qt.RichText)
        oficial.setTextInteractionFlags(Qt.TextBrowserInteraction)
        oficial.setOpenExternalLinks(True)
        caixa_layout.addWidget(oficial)

        botoes = QHBoxLayout()

        btn_local = QPushButton("📄 Abrir cópia local")
        btn_local.clicked.connect(lambda _=False, r=ref: self._abrir_local(r))
        if not ref.disponivel_localmente:
            btn_local.setEnabled(False)
            btn_local.setToolTip(f"Arquivo não encontrado em {ref.caminho_local}")
        else:
            btn_local.setToolTip(str(ref.caminho_local))
        botoes.addWidget(btn_local)

        btn_doc = QPushButton("🌐 Abrir documento oficial")
        btn_doc.clicked.connect(lambda _=False, r=ref: self._abrir_url(r.url_documento))
        botoes.addWidget(btn_doc)

        btn_pagina = QPushButton("🔗 Página do editor/fabricante")
        btn_pagina.clicked.connect(lambda _=False, r=ref: self._abrir_url(r.url_pagina))
        botoes.addWidget(btn_pagina)

        botoes.addStretch()
        caixa_layout.addLayout(botoes)

        return caixa

    def _abrir_local(self, ref: Referencia):
        if not ref.disponivel_localmente:
            QMessageBox.warning(
                self, "Arquivo não encontrado",
                f"A cópia local não está em:\n{ref.caminho_local}\n\n"
                "Use o botão do documento oficial para baixá-lo de novo."
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(ref.caminho_local)))

    def _abrir_url(self, url: str):
        QDesktopServices.openUrl(QUrl(url))
