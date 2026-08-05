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
        ["Erro Relativo Estimado", f"{data_summary['error']:.2f} %"],
        ["Coeficiente de Determinação (R²)", f"{data_summary['r2']:.4f}"]
    ]
    t_results = Table(result_data, colWidths=[200, 300])
    t_results.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (1,0), colors.HexColor('#e3f2fd')),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('FONTNAME', (0,0), (1,0), 'Helvetica-Bold'),
    ]))
    story.append(t_results)
    story.append(Spacer(1, 15))
    
    # --- 4. Gráficos ---
    if graph_image_path and os.path.exists(graph_image_path):
        story.append(Paragraph("3. Análise Gráfica", section_style))
        img = Image(graph_image_path, width=480, height=220)
        story.append(img)
        story.append(Spacer(1, 15))
        
    # --- 5. Notas Adicionais ---
    notas = meta_data.get("notes", "")
    if notas:
        story.append(Paragraph("4. Observações do Pesquisador", section_style))
        story.append(Paragraph(notas, notes_style))

    doc.build(story)