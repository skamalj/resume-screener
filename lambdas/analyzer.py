import json
import os
import boto3
from openai import OpenAI
import pydantic

ssm_client = boto3.client('ssm')

def get_openai_key():
    try:
        response = ssm_client.get_parameter(Name='/irdai/openai-api-key', WithDecryption=True)
        return response['Parameter']['Value']
    except Exception as e:
        print("Could not fetch OpenAI API Key from SSM:", e)
        return os.environ.get("OPENAI_API_KEY", "")

class Fitment(pydantic.BaseModel):
    jd_filename: str
    resume_filename: str
    score: int
    match_summary: str

class FitmentResponse(pydantic.BaseModel):
    matches: list[Fitment]

def handler(event, context):
    print("Analyzer received event:", json.dumps(event)[:500])

    sender = event['sender']
    subject = event['subject']
    documents = event['documents']

    if len(documents) < 2:
        raise ValueError("At least 2 documents are required to perform matching.")

    api_key = get_openai_key()
    if not api_key:
        raise ValueError("OPENAI_API_KEY is missing.")

    client = OpenAI(api_key=api_key)

    system_prompt = """You are an expert technical recruiter and HR specialist.
I have attached several documents. Some are Job Descriptions (JDs), and some are candidate Resumes.

Your task is to:
1. Figure out which documents are JDs and which are Resumes based on their content.
2. Evaluate EVERY possible combination of a JD and a Resume.
3. Provide a fitment score from 1 to 10 for each combination (10 being a perfect match).
4. Provide a detailed summary explaining why the candidate is or isn't a fit for that specific JD.

Return a JSON object with a "matches" array. Each element must have:
- jd_filename: string
- resume_filename: string
- score: integer 1-10
- match_summary: string
"""

    # Build content blocks using Responses API format (supports PDF + DOCX via input_file)
    content_blocks = [
        {"type": "input_text", "text": system_prompt}
    ]

    for doc in documents:
        content_blocks.append({
            "type": "input_text",
            "text": f"Document: {doc['filename']}"
        })
        content_blocks.append({
            "type": "input_file",
            "filename": doc["filename"],
            "file_data": doc["file_data"]
        })

    content_blocks.append({
        "type": "input_text",
        "text": "Analyze all JD-Resume combinations and return the structured fitment scores as JSON."
    })

    try:
        # Use Responses API — supports both PDF and DOCX via input_file
        response = client.responses.create(
            model="gpt-4o",
            input=[{"role": "user", "content": content_blocks}],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "FitmentResponse",
                    "schema": FitmentResponse.model_json_schema(),
                    "strict": True
                }
            }
        )

        result = json.loads(response.output_text)
        matches = [Fitment(**m).model_dump() for m in result["matches"]]
        print(f"Analysis complete — {len(matches)} match(es) found")

    except Exception as e:
        print("Error calling OpenAI API:", e)
        raise ValueError(f"Failed to generate fitment analysis: {str(e)}")

    return {
        "sender": sender,
        "subject": subject,
        "matches": matches
    }
