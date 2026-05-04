import json
import boto3
import os
import email
from email import policy
import urllib.parse

s3_client  = boto3.client('s3')
ses_client = boto3.client('ses', region_name=os.environ.get('AWS_REGION', 'ap-south-1'))

def load_error_messages():
    path = os.path.join(os.path.dirname(__file__), "error_messages.json")
    with open(path) as f:
        return json.load(f)

def classify_error(raw_error: str, error_config: dict) -> dict:
    for variant in error_config.get("variants", []):
        if variant["match"].lower() in raw_error.lower():
            return variant
    return error_config["default"]

def extract_sender_from_s3(bucket, key):
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        raw_email = response['Body'].read()
        msg = email.message_from_bytes(raw_email, policy=policy.default)
        return msg.get('From'), msg.get('Subject', 'No Subject')
    except Exception as e:
        print("Failed to extract sender from S3:", e)
        return None, None

def build_html(title: str, message: str) -> str:
    return f"""
    <html>
      <body style="font-family:Arial,sans-serif; color:#333;">
        <p>Hello,</p>
        <p><strong>{title}</strong></p>
        <p>{message}</p>
        <br/>
        <p>Best regards,<br/>Mockify Resume Screener Agent</p>
      </body>
    </html>
    """

def handler(event, context):
    print("Error handler received event:", json.dumps(event)[:500])

    sender     = event.get('sender')
    subject    = event.get('subject', 'Resume Screener Request')
    error_info = event.get('error_info', {})

    if not sender:
        bucket = event.get('bucket') or error_info.get('bucket')
        key    = event.get('key')    or error_info.get('key')
        if bucket and key:
            sender, sub = extract_sender_from_s3(bucket, urllib.parse.unquote_plus(key))
            if sub:
                subject = sub

    if not sender:
        print("Cannot send error email: sender address is unknown.")
        return {"status": "Failed to notify sender"}

    # Extract raw error text from Step Functions Cause
    raw_cause = error_info.get('Cause', '')
    try:
        cause_obj = json.loads(raw_cause)
        raw_error = cause_obj.get('errorMessage', raw_cause)
    except (json.JSONDecodeError, TypeError):
        raw_error = raw_cause

    print("Raw error for classification:", raw_error[:300])

    error_config = load_error_messages()
    variant      = classify_error(raw_error, error_config)

    html_content = build_html(variant["title"], variant["message"])
    email_subject = f"Re: {subject} — {variant['subject_suffix']}"

    try:
        response = ses_client.send_email(
            Source="resume@screener.mockify.ai",
            Destination={'ToAddresses': [sender]},
            Message={
                'Subject': {'Data': email_subject},
                'Body':    {'Html': {'Data': html_content}}
            }
        )
        print("Error email sent! Message ID:", response['MessageId'])
    except Exception as e:
        print("Error sending SES error email:", e)
        raise e

    return {"status": "Error email sent"}
