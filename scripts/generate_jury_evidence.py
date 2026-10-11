"""Generate the local evidence document used by the jury walkthrough."""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "pdf" / "constancia_curso_investigacion.pdf"


def build_document():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    navy = colors.HexColor("#17324D")
    teal = colors.HexColor("#087F83")
    muted = colors.HexColor("#61768A")
    pale = colors.HexColor("#EFF5F7")
    border = colors.HexColor("#D6E2E8")
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Eyebrow", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=teal, alignment=TA_CENTER, spaceAfter=8))
    styles.add(ParagraphStyle(name="TitleCustom", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=25, leading=30, textColor=navy, alignment=TA_CENTER, spaceAfter=8))
    styles.add(ParagraphStyle(name="Intro", parent=styles["BodyText"], fontSize=11, leading=17, textColor=muted, alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="NameCustom", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=24, leading=29, textColor=navy, alignment=TA_CENTER, spaceBefore=13, spaceAfter=14))
    styles.add(ParagraphStyle(name="BodyCustom", parent=styles["BodyText"], fontSize=11, leading=17, textColor=navy, alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="LabelCustom", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=navy))
    styles.add(ParagraphStyle(name="ValueCustom", parent=styles["BodyText"], fontSize=10, leading=14, textColor=navy))
    styles.add(ParagraphStyle(name="FootnoteCustom", parent=styles["BodyText"], fontSize=8, leading=12, textColor=muted, alignment=TA_CENTER))

    def frame(canvas, doc):
        canvas.saveState()
        width, height = A4
        canvas.setFillColor(navy)
        canvas.rect(0, height - 22 * mm, width, 22 * mm, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawString(20 * mm, height - 13 * mm, "INGENIERÍA DE SISTEMAS")
        canvas.setFont("Helvetica", 9)
        canvas.drawRightString(width - 20 * mm, height - 13 * mm, "REGISTRO DE ACTIVIDAD ACADÉMICA")
        canvas.setFillColor(teal)
        canvas.rect(0, 0, width, 5 * mm, fill=1, stroke=0)
        canvas.setStrokeColor(border)
        canvas.setLineWidth(0.8)
        canvas.roundRect(18 * mm, 18 * mm, width - 36 * mm, height - 48 * mm, 9 * mm, fill=0, stroke=1)
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(OUTPUT), pagesize=A4,
        rightMargin=28 * mm, leftMargin=28 * mm,
        topMargin=34 * mm, bottomMargin=28 * mm,
        title="Declaración de participación académica",
        author="UPEA Talent+",
    )
    story = [Spacer(1, 18 * mm),
             Paragraph("DOCUMENTO PRESENTADO PARA REVISIÓN", styles["Eyebrow"]),
             Paragraph("Declaración de participación", styles["TitleCustom"]),
             HRFlowable(width="20%", thickness=2, color=teal, hAlign="CENTER", spaceBefore=5, spaceAfter=19),
             Paragraph("La estudiante declara haber participado en la siguiente actividad académica:", styles["Intro"]),
             Paragraph("Valeria Quispe", styles["NameCustom"]),
             Paragraph("Taller <b>Investigación aplicada y gestión de datos</b>, con una duración declarada de 12 horas académicas, realizado el 18 de septiembre de 2026.", styles["BodyCustom"]),
             Spacer(1, 14 * mm)]
    rows = [
        [Paragraph("ACTIVIDAD", styles["LabelCustom"]), Paragraph("Investigación aplicada y gestión de datos", styles["ValueCustom"])],
        [Paragraph("ASIGNATURA", styles["LabelCustom"]), Paragraph("Metodología de la Investigación · MET201", styles["ValueCustom"])],
        [Paragraph("PARTICIPACIÓN", styles["LabelCustom"]), Paragraph("Asistente · 12 horas académicas", styles["ValueCustom"])],
        [Paragraph("FECHA", styles["LabelCustom"]), Paragraph("18 de septiembre de 2026", styles["ValueCustom"])],
    ]
    table = Table(rows, colWidths=[44 * mm, 100 * mm], rowHeights=[17 * mm] * 4)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), pale),
        ("BOX", (0, 0), (-1, -1), 0.6, border),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, border),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    story.extend([table, Spacer(1, 22 * mm),
                  KeepTogether([
                      Paragraph("Presentado por Valeria Quispe", styles["BodyCustom"]),
                      Spacer(1, 3 * mm),
                      Paragraph("Estado en UPEA Talent+: pendiente de revisión docente", styles["FootnoteCustom"]),
                  ]),
                  Spacer(1, 16 * mm),
                  Paragraph("El contenido corresponde a una declaración de la estudiante y requiere revisión académica antes de su validación.", styles["FootnoteCustom"])])
    doc.build(story, onFirstPage=frame, onLaterPages=frame)


if __name__ == "__main__":
    build_document()
