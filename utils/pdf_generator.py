import io
import datetime
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

def generate_registre_pdf(events: list, site_id: str, date_debut: str, date_fin: str) -> bytes:
    """Génère un rapport PDF élégant du registre de la main courante."""
    buffer = io.BytesIO()
    
    # Orientation Paysage (A4) pour avoir la place d'afficher toutes les colonnes
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=20,
        leftMargin=20,
        topMargin=20,
        bottomMargin=20
    )

    elements = []
    styles = getSampleStyleSheet()

    # Style personnalisé
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor("#1E293B"),
        spaceAfter=6
    )
    
    subtitle_style = ParagraphStyle(
        'DocSubTitle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor("#64748B"),
        spaceAfter=15
    )

    cell_style = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#0F172A")
    )

    cell_header_style = ParagraphStyle(
        'TableHead',
        parent=styles['Normal'],
        fontSize=9,
        leading=11,
        fontName="Helvetica-Bold",
        textColor=colors.white
    )

    # 1. En-tête du document
    now_str = datetime.datetime.now().strftime("%d/%m/%Y à %H:%M")
    elements.append(Paragraph(f"<b>REGISTRE DE MAIN COURANTE — {site_id.upper()}</b>", title_style))
    elements.append(Paragraph(f"Période du <b>{date_debut}</b> au <b>{date_fin}</b> | Document extrait le {now_str}", subtitle_style))

    # 2. Préparation du tableau des événements
    # En-têtes des colonnes
    data = [[
        Paragraph("Horodatage", cell_header_style),
        Paragraph("Référence", cell_header_style),
        Paragraph("Agent", cell_header_style),
        Paragraph("Type", cell_header_style),
        Paragraph("Description des faits", cell_header_style),
        Paragraph("Actions menées", cell_header_style),
        Paragraph("Alerte", cell_header_style)
    ]]

    # Remplissage des lignes
    for evt in events:
        # Formatage de la date
        raw_date = evt.get("horodatage", "")
        try:
            formatted_date = datetime.datetime.fromisoformat(raw_date.replace("Z", "")).strftime("%d/%m/%Y %H:%M")
        except Exception:
            formatted_date = raw_date

        data.append([
            Paragraph(formatted_date, cell_style),
            Paragraph(evt.get("reference", "-"), cell_style),
            Paragraph(evt.get("agent_nom", "-"), cell_style),
            Paragraph(evt.get("type_evenement", "-"), cell_style),
            Paragraph(evt.get("description", "-").replace("\n", "<br/>"), cell_style),
            Paragraph(evt.get("actions_menees", "-").replace("\n", "<br/>") if evt.get("actions_menees") else "-", cell_style),
            Paragraph("OUI" if evt.get("notified_authority") else "NON", cell_style)
        ])

    # Largeurs des colonnes (Total = ~800pt pour du A4 paysage)
    col_widths = [80, 110, 90, 85, 230, 160, 45]

    t = Table(data, colWidths=col_widths, repeatRows=1)
    
    # Style du tableau (couleurs sombres/élégantes)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0F172A")), # En-tête bleu nuit
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")), # Lignes grises
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]), # Alternance de couleurs
    ]))

    elements.append(t)

    # Construction du PDF
    doc.build(elements)
    
    pdf_data = buffer.getvalue()
    buffer.close()
    return pdf_data