import json
import boto3
import email
from email import policy
import urllib.parse
import os

s3_client = boto3.client('s3')

def handler(event, context):
    print("Parser received event:", json.dumps(event)[:500])

    bucket = event.get('bucket')
    key = urllib.parse.unquote_plus(event.get('key'))

    response = s3_client.get_object(Bucket=bucket, Key=key)
    raw_email = response['Body'].read()

    msg = email.message_from_bytes(raw_email, policy=policy.default)
    sender = msg.get('From')
    subject = msg.get('Subject', 'No Subject')

    # Use the email message ID (S3 key) as a unique prefix for extracted files
    prefix = f"parsed/{key}/"
    documents = []

    for part in msg.walk():
        if part.get_content_maintype() == 'multipart':
            continue
        if part.get('Content-Disposition') is None:
            continue

        filename = part.get_filename()
        if not filename:
            continue

        payload = part.get_payload(decode=True)
        if not payload:
            continue

        if filename.lower().endswith('.pdf'):
            mime_type = "application/pdf"
        elif filename.lower().endswith('.docx'):
            mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        else:
            continue

        # Save extracted file to S3 instead of embedding base64 in state payload
        doc_key = f"{prefix}{filename}"
        s3_client.put_object(Bucket=bucket, Key=doc_key, Body=payload, ContentType=mime_type)
        print(f"Saved {filename} ({mime_type}) — {len(payload)} bytes → s3://{bucket}/{doc_key}")

        documents.append({
            "filename": filename,
            "mime_type": mime_type,
            "s3_key": doc_key
        })

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
