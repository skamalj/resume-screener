import json
import boto3
import io
import os
from email.message import EmailMessage
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

ses_client = boto3.client('ses', region_name=os.environ.get('AWS_REGION', 'ap-south-1'))

def create_pdf_report(match_data):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    
    title_style = styles['Heading1']
    normal_style = styles['Normal']
    
    story = []
    
    story.append(Paragraph(f"Fitment Report", title_style))
    story.append(Spacer(1, 12))
    
    story.append(Paragraph(f"<b>Job Description:</b> {match_data['jd_filename']}", normal_style))
    story.append(Paragraph(f"<b>Candidate Resume:</b> {match_data['resume_filename']}", normal_style))
    story.append(Paragraph(f"<b>Fitment Score:</b> {match_data['score']} / 10", normal_style))
    story.append(Spacer(1, 12))
    
    story.append(Paragraph("<b>Detailed Summary:</b>", styles['Heading2']))
    story.append(Spacer(1, 6))
    story.append(Paragraph(match_data['match_summary'], normal_style))
    
    doc.build(story)
    return buffer.getvalue()

def generate_matrix_html(matches):
    # Extract unique JDs and Resumes
    jds = sorted(list(set([m['jd_filename'] for m in matches])))
    resumes = sorted(list(set([m['resume_filename'] for m in matches])))
    
    # Build dictionary map
    score_map = {}
    for m in matches:
        score_map[(m['jd_filename'], m['resume_filename'])] = m['score']
        
    html = """
    <h2>Fitment Matrix</h2>
    <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse;">
        <thead>
            <tr>
                <th style="background-color: #f2f2f2;">Job Description \\ Resume</th>
    """
    for res in resumes:
        html += f"<th style='background-color: #f2f2f2;'>{res}</th>"
    html += "</tr></thead><tbody>"
    
    for jd in jds:
        html += f"<tr><td><b>{jd}</b></td>"
        for res in resumes:
            score = score_map.get((jd, res), "N/A")
            color = ""
            if isinstance(score, int):
                if score >= 8: color = "background-color: #d4edda;" # green
                elif score >= 5: color = "background-color: #fff3cd;" # yellow
                else: color = "background-color: #f8d7da;" # red
            html += f"<td style='text-align: center; {color}'>{score}</td>"
        html += "</tr>"
        
    html += "</tbody></table>"
    return html

def handler(event, context):
    print("Responder received event:", json.dumps(event)[:500])
    
    sender = event['sender']
    subject = event['subject']
    matches = event['matches']
    
    msg = EmailMessage()
    msg['Subject'] = f"Re: {subject} - Fitment Analysis Complete"
    msg['From'] = "resume@screener.mockify.ai" # The verified SES sender
    msg['To'] = sender
    
    # Body
    html_content = f"""
    <html>
        <body>
            <p>Hello,</p>
            <p>Your documents have been successfully analyzed by our AI screener. Please find the detailed reports attached.</p>
            {generate_matrix_html(matches)}
            <p>Best regards,<br>Mockify Resume Screener Agent</p>
        </body>
    </html>
    """
    msg.set_content("Please view this email in an HTML compatible client.")
    msg.add_alternative(html_content, subtype='html')
    
    # Attachments
    for m in matches:
        pdf_bytes = create_pdf_report(m)
        safe_jd = m['jd_filename'].replace('.pdf', '').replace('.docx', '')
        safe_res = m['resume_filename'].replace('.pdf', '').replace('.docx', '')
        filename = f"Fitment_{safe_jd}_vs_{safe_res}.pdf"
        
        msg.add_attachment(pdf_bytes, maintype='application', subtype='pdf', filename=filename)
        
    # Send
    try:
        response = ses_client.send_raw_email(
            Source=msg['From'],
            Destinations=[msg['To']],
            RawMessage={'Data': msg.as_bytes()}
        )
        print("Email sent! Message ID:", response['MessageId'])
    except Exception as e:
        print("Error sending SES email:", e)
        raise e
        
    return {"status": "Email sent successfully"}
