import json
import boto3
import io
import os
from email.message import EmailMessage
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT

ses_client = boto3.client('ses', region_name=os.environ.get('AWS_REGION', 'ap-south-1'))

BLUE       = colors.HexColor("#1a5276")
LIGHT_BLUE = colors.HexColor("#d6eaf8")
GREEN      = colors.HexColor("#28a745")
YELLOW     = colors.HexColor("#ffc107")
RED        = colors.HexColor("#dc3545")
GREY_BG    = colors.HexColor("#f2f2f2")
DARK_HDR   = colors.HexColor("#2c3e50")
WHITE      = colors.white

def _fmt_score(score: float) -> str:
    return str(int(score)) if score == int(score) else str(score)

def _score_color(score: float) -> colors.Color:
    if score >= 8: return GREEN
    if score >= 5: return YELLOW
    return RED

def _rec_color(rec: str) -> colors.Color:
    if "Strong Hire" in rec: return GREEN
    if "Consider"   in rec: return YELLOW
    return RED

def create_pdf_report(match: dict) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        leftMargin=0.75*inch, rightMargin=0.75*inch,
        topMargin=0.75*inch,  bottomMargin=0.75*inch,
    )
    styles = getSampleStyleSheet()
    W = letter[0] - 1.5*inch  # usable width

    title_style = ParagraphStyle("Title",  parent=styles["Normal"],
                                 fontSize=16, textColor=BLUE,
                                 fontName="Helvetica-Bold", alignment=TA_CENTER, spaceAfter=2)
    sub_style   = ParagraphStyle("Sub",    parent=styles["Normal"],
                                 fontSize=9, textColor=colors.HexColor("#555555"),
                                 alignment=TA_CENTER, spaceAfter=4)
    h2_style    = ParagraphStyle("H2",     parent=styles["Normal"],
                                 fontSize=11, textColor=BLUE,
                                 fontName="Helvetica-Bold", spaceBefore=8, spaceAfter=2)
    normal      = styles["Normal"]
    bullet_style= ParagraphStyle("Bullet", parent=normal, leftIndent=12, spaceAfter=2,
                                 fontSize=9, leading=13)
    footer_style= ParagraphStyle("Footer", parent=normal, fontSize=8,
                                 textColor=colors.grey, alignment=TA_LEFT)

    story = []

    # ── Title ─────────────────────────────────────────────────────────────────
    story.append(Paragraph("Resume vs. Job Description Review", title_style))
    story.append(Paragraph(
        f"<b>Candidate:</b> {match.get('candidate_name', '—')}&nbsp;&nbsp;|&nbsp;&nbsp;"
        f"<b>Role:</b> {match.get('role_title', '—')}",
        sub_style
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey))
    story.append(Spacer(1, 5))

    # ── Score banner ──────────────────────────────────────────────────────────
    score    = match["score"]
    rec      = match["overall_recommendation"]
    headline = match.get("headline", "")

    score_para = Paragraph(
        f'<font color="{_score_color(score).hexval()}"><b>{_fmt_score(score)}</b></font>',
        ParagraphStyle("ScoreCell", parent=normal, alignment=TA_CENTER,
                       fontSize=30, leading=30, spaceBefore=0, spaceAfter=0)
    )
    rec_para = Paragraph(
        f'<b>Recommendation:</b> <font color="{_rec_color(rec).hexval()}">{rec}</font><br/>'
        f'<b>Headline:</b> {headline}',
        ParagraphStyle("RecCell", parent=normal, fontSize=9, leading=13)
    )

    banner = Table([[score_para, rec_para]], colWidths=[1.1*inch, W - 1.1*inch])
    banner.setStyle(TableStyle([
        ("BOX",          (0, 0), (-1, -1), 0.75, colors.HexColor("#cccccc")),
        ("BACKGROUND",   (0, 0), (-1, -1), LIGHT_BLUE),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",   (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 7),
        ("LEFTPADDING",  (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("LINEAFTER",    (0, 0), (0, -1),  0.5, colors.HexColor("#aaaaaa")),
    ]))
    story.append(banner)
    story.append(Spacer(1, 8))

    # ── Criteria breakdown table ───────────────────────────────────────────────
    story.append(Paragraph("Skills &amp; Experience Match Breakdown", h2_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
    story.append(Spacer(1, 3))

    hdr_style  = ParagraphStyle("TH", parent=normal, fontName="Helvetica-Bold",
                                 fontSize=9, textColor=WHITE)
    cell_style = ParagraphStyle("TD", parent=normal, fontSize=9, leading=11)

    table_data = [[
        Paragraph("Criterion",  hdr_style),
        Paragraph("Score",      hdr_style),
        Paragraph("Assessment", hdr_style),
    ]]

    for cs in match.get("criteria_scores", []):
        cs_score = cs["score"]
        sc_color = _score_color(cs_score).hexval()
        table_data.append([
            Paragraph(cs["criterion"], cell_style),
            Paragraph(f'<font color="{sc_color}"><b>{_fmt_score(cs_score)}</b></font>', cell_style),
            Paragraph(cs["assessment"], cell_style),
        ])

    col_w = [2.1*inch, 0.65*inch, W - 2.75*inch]
    criteria_table = Table(table_data, colWidths=col_w, repeatRows=1)
    criteria_table.setStyle(TableStyle([
        # Header row
        ("BACKGROUND",   (0, 0), (-1, 0),  DARK_HDR),
        ("TEXTCOLOR",    (0, 0), (-1, 0),  WHITE),
        ("FONTNAME",     (0, 0), (-1, 0),  "Helvetica-Bold"),
        # Alternating row shading
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, GREY_BG]),
        # Grid
        ("BOX",          (0, 0), (-1, -1), 0.5, colors.grey),
        ("INNERGRID",    (0, 0), (-1, -1), 0.25, colors.lightgrey),
        # Padding & alignment
        ("VALIGN",       (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",   (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
        ("LEFTPADDING",  (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("ALIGN",        (1, 0), (1, -1),  "CENTER"),
    ]))
    story.append(criteria_table)
    story.append(Spacer(1, 4))

    # ── Strengths ──────────────────────────────────────────────────────────────
    story.append(Paragraph("Strengths", h2_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
    story.append(Spacer(1, 3))
    for item in match.get("strengths", []):
        story.append(Paragraph(f"&#8226;&nbsp;&nbsp;{item}", bullet_style))
    story.append(Spacer(1, 4))

    # ── Gaps & Risks ───────────────────────────────────────────────────────────
    story.append(Paragraph("Gaps &amp; Risks", h2_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
    story.append(Spacer(1, 3))
    for item in match.get("gaps", []):
        story.append(Paragraph(f"&#8226;&nbsp;&nbsp;{item}", bullet_style))
    story.append(Spacer(1, 6))

    # ── Rating scale footer ────────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "<i>Rating scale: 10 = perfect match, 8–9 = strong match, "
        "6–7 = partial match, 4–5 = weak match, ≤3 = not a match.</i>",
        footer_style
    ))

    doc.build(story)
    return buffer.getvalue()


def generate_matrix_html(matches: list) -> str:
    jds     = sorted(set(m["jd_filename"]    for m in matches))
    resumes = sorted(set(m["resume_filename"] for m in matches))
    idx     = {(m["jd_filename"], m["resume_filename"]): m for m in matches}

    def cell_style(score):
        if not isinstance(score, int): return ""
        if score >= 8: return "background-color:#d4edda; color:#155724;"
        if score >= 5: return "background-color:#fff3cd; color:#856404;"
        return "background-color:#f8d7da; color:#721c24;"

    html = """
    <h2 style="font-family:Arial,sans-serif;">JD vs Candidate Fitment Matrix</h2>
    <table border="1" cellpadding="8" cellspacing="0"
           style="border-collapse:collapse; font-family:Arial,sans-serif; font-size:13px;">
      <thead>
        <tr>
          <th style="background-color:#2c3e50; color:#fff; text-align:left; padding:8px;">
            Job Description \\ Candidate
          </th>
    """
    for res in resumes:
        m0 = next((m for m in matches if m["resume_filename"] == res), None)
        label = m0.get("candidate_name", res) if m0 else res
        html += f'<th style="background-color:#2c3e50; color:#fff; padding:8px;">{label}</th>'
    html += "</tr></thead><tbody>"

    for jd in jds:
        m0 = next((m for m in matches if m["jd_filename"] == jd), None)
        role = m0.get("role_title", jd) if m0 else jd
        html += f'<tr><td style="font-weight:bold; background-color:#f2f2f2; padding:8px;">{role}</td>'
        for res in resumes:
            match = idx.get((jd, res))
            if match:
                score = match["score"]
                rec   = match["overall_recommendation"]
                style = cell_style(score)
                html += (
                    f'<td style="text-align:center; {style}">'
                    f'<strong>{score}/10</strong><br/>'
                    f'<small>{rec}</small>'
                    f'</td>'
                )
            else:
                html += '<td style="text-align:center; color:#999;">N/A</td>'
        html += "</tr>"

    html += "</tbody></table>"
    return html


def handler(event, context):
    print("Responder received event:", json.dumps(event)[:500])

    sender  = event["sender"]
    subject = event["subject"]
    matches = event["matches"]

    msg = EmailMessage()
    msg["Subject"] = f"Re: {subject} — Fitment Analysis Complete"
    msg["From"]    = "resume@screener.mockify.ai"
    msg["To"]      = sender

    html_content = f"""
    <html>
      <body style="font-family:Arial,sans-serif;">
        <p>Hello,</p>
        <p>Your documents have been analysed. Please find the detailed per-pair reports
           attached, and the summary matrix below.</p>
        {generate_matrix_html(matches)}
        <br/>
        <p>Best regards,<br/>Mockify Resume Screener Agent</p>
      </body>
    </html>
    """
    msg.set_content("Please view this email in an HTML-compatible client.")
    msg.add_alternative(html_content, subtype="html")

    for m in matches:
        pdf_bytes = create_pdf_report(m)
        candidate = m.get("candidate_name", m["resume_filename"].rsplit(".", 1)[0])
        role      = m.get("role_title",     m["jd_filename"].rsplit(".", 1)[0])
        safe = lambda s: s.replace("/", "-").replace("\\", "-").replace(" ", "_")[:40]
        filename  = f"Review_{safe(candidate)}_vs_{safe(role)}.pdf"
        msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename=filename)

    try:
        response = ses_client.send_raw_email(
            Source=msg["From"],
            Destinations=[msg["To"]],
            RawMessage={"Data": msg.as_bytes()},
        )
        print("Email sent! Message ID:", response["MessageId"])
    except Exception as e:
        print("Error sending SES email:", e)
        raise e

    return {"status": "Email sent successfully"}
