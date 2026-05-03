import json
import boto3
import os
import email
from email import policy
import urllib.parse

s3_client = boto3.client('s3')
ses_client = boto3.client('ses', region_name=os.environ.get('AWS_REGION', 'ap-south-1'))

def extract_sender_from_s3(bucket, key):
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        raw_email = response['Body'].read()
        msg = email.message_from_bytes(raw_email, policy=policy.default)
        return msg.get('From'), msg.get('Subject', 'No Subject')
    except Exception as e:
        print("Failed to extract sender from S3:", e)
        return None, None

def handler(event, context):
    print("Error handler received event:", json.dumps(event)[:500])
    
    sender = event.get('sender')
    subject = event.get('subject', 'Resume Screener Request')
    error_info = event.get('error_info', {})
    
    # If the parser failed early, we might not have the sender yet. Try to fetch from S3 if bucket/key exist.
    if not sender:
        bucket = event.get('bucket')
        key = event.get('key')
        if not key and 'bucket' in error_info: # sometimes step functions passes original input differently
             bucket = error_info.get('bucket')
             key = error_info.get('key')
             
        if bucket and key:
             sender, sub = extract_sender_from_s3(bucket, urllib.parse.unquote_plus(key))
             if sub: subject = sub
             
    if not sender:
        print("Cannot send error email: Sender address is unknown.")
        return {"status": "Failed to notify sender"}
        
    # Parse the Cause field - Step Functions wraps it as a JSON string
    raw_cause = error_info.get('Cause', 'An unknown error occurred during processing.')
    try:
        cause_obj = json.loads(raw_cause)
        error_message = cause_obj.get('errorMessage', raw_cause)
    except (json.JSONDecodeError, TypeError):
        error_message = raw_cause
    
    html_content = f"""
    <html>
        <body>
            <p>Hello,</p>
            <p>We received your request to analyze resumes, but an error occurred during processing.</p>
            <p><b>Error Details:</b></p>
            <pre>{error_message}</pre>
            <p>Please ensure you have attached valid PDF or DOCX files and try again.</p>
            <br>
            <p>Best regards,<br>Mockify Resume Screener Agent</p>
        </body>
    </html>
    """
    
    try:
        response = ses_client.send_email(
            Source="resume@screener.mockify.ai",
            Destination={'ToAddresses': [sender]},
            Message={
                'Subject': {'Data': f"Re: {subject} - Processing Error"},
                'Body': {'Html': {'Data': html_content}}
            }
        )
        print("Error email sent! Message ID:", response['MessageId'])
    except Exception as e:
        print("Error sending SES error email:", e)
        raise e
        
    return {"status": "Error email sent"}
