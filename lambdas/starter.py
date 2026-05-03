import json
import os
import boto3

sfn_client = boto3.client('stepfunctions')

def handler(event, context):
    print("Received SNS event:", json.dumps(event))
    
    state_machine_arn = os.environ.get('STATE_MACHINE_ARN')
    
    # Process each record in the SNS event
    for record in event.get('Records', []):
        sns_message_str = record['Sns']['Message']
        
        # The SNS message from SES is a JSON string
        try:
            ses_event = json.loads(sns_message_str)
            mail = ses_event.get('mail', {})
            message_id = mail.get('messageId')
            
            if not message_id:
                print("No messageId found in SES SNS notification")
                continue
                
            bucket_name = os.environ.get('EMAIL_BUCKET')
            object_key = message_id # SES saves emails using messageId as the key
            
            payload = {
                "bucket": bucket_name,
                "key": object_key
            }
            
            print(f"Starting execution for s3://{bucket_name}/{object_key}")
            
            response = sfn_client.start_execution(
                stateMachineArn=state_machine_arn,
                input=json.dumps(payload)
            )
            print("Started execution:", response['executionArn'])

        except Exception as e:
            print(f"Error processing SNS record: {e}")
            raise

    return {"status": "success"}
