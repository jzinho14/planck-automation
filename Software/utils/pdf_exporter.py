# utils/pdf_exporter.py
import os
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

def generate_planck_report(filepath: str, data_summary: dict, sim_params: dict, meta_data: dict, graph_image_path: str = None):
    doc = SimpleDocTemplate(filepath, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    story = []
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle('DocTitle', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#1a237e'), alignment=1)
    section_style = ParagraphStyle('SectionHeading', parent=styles['Heading2'], fontSize=12, textColor=colors.HexColor('#0d47a1'), spaceBefore=10, spaceAfter=5)
    body_style = ParagraphStyle('BodyTextCustom', parent=styles['Normal'], fontSize=10, leading=14)
    notes_style = ParagraphStyle('NotesText', parent=styles['Normal'], fontSize=10, leading=14, textColor=colors.grey, leftIndent=10)

    # --- 1. Cabeçalho e Metadados ---
    story.append(Paragraph("Relatório Analítico: Determinação da Constante de Planck", title_style))
    story.append(Spacer(1, 15))
    
    data_hora = datetime.now().strftime("%d/%m/%Y às %H:%M")
    autor = meta_data.get("author", "Não informado") or "Não informado"
    local = meta_data.get("location", "Não informado") or "Não informado"
    
    story.append(Paragraph(f"<b>Pesquisador:</b> {autor}", body_style))
    story.append(Paragraph(f"<b>Local/Laboratório:</b> {local}", body_style))
    story.append(Paragraph(f"<b>Data e Hora do Registo:</b> {data_hora}", body_style))
    story.append(Spacer(1, 15))
    
    # --- 2. Parâmetros da Simulação / Experimento ---
    story.append(Paragraph("1. Condições e Parâmetros Iniciais", section_style))
    param_data = [["Parâmetro", "Valor Configurado"]]
    for k, v in sim_params.items():
        param_data.append([k, str(v)])
        
    t_params = Table(param_data, colWidths=[200, 300])
    t_params.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (1,0), colors.HexColor('#e0e0e0')),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('FONTNAME', (0,0), (1,0), 'Helvetica-Bold'),
    ]))
    story.append(t_params)
    story.append(Spacer(1, 15))
    
    # --- 3. Resultados Analíticos ---
    story.append(Paragraph("2. Resultados Calculados", section_style))
    result_data = [
        ["Métrica Experimental", "Valor Obtido"],
        ["Constante de Planck (Referência)", f"{data_summary['h_ref']:.6e} J.s"],
        ["Constante de Planck (Experimental)", f"{data_summary['h_exp']:.6e} J.s"],
    ]

    # O resultado com incerteza só existe quando a análise completa rodou.
    if data_summary.get('texto'):
        result_data.append(["Resultado declarado", data_summary['texto']])
    if data_summary.get('incerteza_expandida') is not None:
        result_data.append([
            f"Incerteza expandida U (k={data_summary.get('k', 2):g})",
            f"{data_summary['incerteza_expandida']:.3e} J.s"
        ])

    result_data.append(["Erro Relativo Estimado", f"{data_summary['error']:.2f} %"])
    result_data.append(["Coeficiente de Determinação (R²)", f"{data_summary['r2']:.4f}"])

    if data_summary.get('chi2_reduzido') is not None:
        result_data.append(["Qui-quadrado reduzido",
                            f"{data_summary['chi2_reduzido']:.3f}"])
    if data_summary.get('compativel') is not None:
        result_data.append([
            "Compatível com a CODATA?",
            "Sim — o valor de referência cai dentro da incerteza"
            if data_summary['compativel'] else
            "Não — há erro sistemático não contabilizado"
        ])

    t_results = Table(result_data, colWidths=[200, 300])
    t_results.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (1,0), colors.HexColor('#e3f2fd')),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('FONTNAME', (0,0), (1,0), 'Helvetica-Bold'),
    ]))
    story.append(t_results)
    story.append(Spacer(1, 15))

    # --- 3b. Orçamento de incertezas ---
    orcamento = data_summary.get('orcamento') or []
    if orcamento:
        story.append(Paragraph("3. Orçamento de Incertezas", section_style))
        story.append(Paragraph(
            "Contribuição de cada fonte para a variância da constante de Planck. "
            "A soma fecha em 100%.", body_style))
        story.append(Spacer(1, 6))
        orc_data = [["Fonte de incerteza", "Contribuição"]]
        for nome, pct in orcamento:
            orc_data.append([nome, f"{pct:.1f} %"])
        t_orc = Table(orc_data, colWidths=[200, 300])
        t_orc.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (1,0), colors.HexColor('#fff3e0')),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('FONTNAME', (0,0), (1,0), 'Helvetica-Bold'),
        ]))
        story.append(t_orc)
        story.append(Spacer(1, 15))

    # --- 4. Gráficos ---
    if graph_image_path and os.path.exists(graph_image_path):
        story.append(Paragraph("4. Análise Gráfica", section_style))
        img = Image(graph_image_path, width=480, height=220)
        story.append(img)
        story.append(Spacer(1, 15))
        
    # --- 5. Notas Adicionais ---
    notas = meta_data.get("notes", "")
    if notas:
        story.append(Paragraph("5. Observações do Pesquisador", section_style))
        story.append(Paragraph(notas, notes_style))

    doc.build(story)