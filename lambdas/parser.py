import json
import boto3
import email
from email import policy
import urllib.parse
import os
import base64

s3_client = boto3.client('s3')
ssm_client = boto3.client('ssm')

def handler(event, context):
    print("Parser received event:", json.dumps(event)[:500])

    bucket = event.get('bucket')
    key = urllib.parse.unquote_plus(event.get('key'))

    response = s3_client.get_object(Bucket=bucket, Key=key)
    raw_email = response['Body'].read()

    msg = email.message_from_bytes(raw_email, policy=policy.default)
    sender = msg.get('From')
    subject = msg.get('Subject', 'No Subject')

    documents = []

    for part in msg.walk():
        if part.get_content_maintype() == 'multipart': continue
        if part.get('Content-Disposition') is None: continue

        filename = part.get_filename()
        if not filename: continue

        payload = part.get_payload(decode=True)
        if not payload: continue

        if filename.lower().endswith('.pdf'):
            mime_type = "application/pdf"
        elif filename.lower().endswith('.docx'):
            mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        else:
            continue

        b64 = base64.b64encode(payload).decode('utf-8')
        documents.append({
            "filename": filename,
            "mime_type": mime_type,
            "file_data": f"data:{mime_type};base64,{b64}"
        })
        print(f"Encoded {filename} ({mime_type}) — {len(payload)} bytes")

    if not documents:
        raise ValueError("No valid PDF or DOCX attachments found.")

    print(f"Parsed {len(documents)} document(s): {[d['filename'] for d in documents]}")

    return {
        "sender": sender,
        "subject": subject,
        "bucket": bucket,
        "key": key,
        "documents": documents
    }
