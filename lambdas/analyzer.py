import json
import os
import base64
import boto3
from openai import OpenAI
import pydantic
from typing import Literal

ssm_client = boto3.client('ssm')
s3_client  = boto3.client('s3')

def get_openai_key():
    try:
        response = ssm_client.get_parameter(Name='/irdai/openai-api-key', WithDecryption=True)
        return response['Parameter']['Value']
    except Exception as e:
        print("Could not fetch OpenAI API Key from SSM:", e)
        return os.environ.get("OPENAI_API_KEY", "")

def load_prompt():
    prompt_path = os.path.join(os.path.dirname(__file__), "prompt.txt")
    with open(prompt_path, "r") as f:
        return f.read()

class CriterionScore(pydantic.BaseModel):
    criterion: str   # key skill/requirement extracted from the JD
    score: float     # 1–10 in steps of 0.5
    assessment: str  # one-sentence evidence from the resume

class Fitment(pydantic.BaseModel):
    jd_filename: str
    resume_filename: str
    candidate_name: str   # full name extracted from the resume content
    role_title: str       # job title extracted from the JD content
    score: float          # overall 1–10 in steps of 0.5
    headline: str         # one-sentence candidate characterisation (strengths + gaps in brief)
    overall_recommendation: Literal["Strong Hire", "Consider", "Reject"]
    criteria_scores: list[CriterionScore]  # per-criterion breakdown table
    strengths: list[str]  # 4-6 detailed bullet points
    gaps: list[str]       # 4-6 detailed bullet points (gaps & risks)
    match_summary: str    # 3-5 sentence paragraph

class FitmentResponse(pydantic.BaseModel):
    matches: list[Fitment]

def handler(event, context):
    print("Analyzer received event:", json.dumps(event)[:500])

    sender    = event['sender']
    subject   = event['subject']
    documents = event['documents']
    bucket    = event['bucket']

    if len(documents) < 2:
        raise ValueError("At least 2 documents are required to perform matching.")

    api_key = get_openai_key()
    if not api_key:
        raise ValueError("OPENAI_API_KEY is missing.")

    client = OpenAI(api_key=api_key)
    system_prompt = load_prompt()

    content_blocks = [{"type": "input_text", "text": system_prompt}]

    for doc in documents:
        obj = s3_client.get_object(Bucket=bucket, Key=doc['s3_key'])
        raw_bytes = obj['Body'].read()
        b64 = base64.b64encode(raw_bytes).decode('utf-8')
        file_data = f"data:{doc['mime_type']};base64,{b64}"
        print(f"Loaded {doc['filename']} from S3 — {len(raw_bytes)} bytes")

        content_blocks.append({"type": "input_text", "text": f"Document: {doc['filename']}"})
        content_blocks.append({"type": "input_file", "filename": doc["filename"], "file_data": file_data})

    content_blocks.append({
        "type": "input_text",
        "text": "Analyze all JD-Resume combinations and return the structured fitment scores as JSON."
    })

    try:
        schema = FitmentResponse.model_json_schema()
        schema["additionalProperties"] = False
        for defn in schema.get("$defs", {}).values():
            defn["additionalProperties"] = False

        response = client.responses.create(
            model="gpt-4o",
            input=[{"role": "user", "content": content_blocks}],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "FitmentResponse",
                    "schema": schema,
                    "strict": True
                }
            }
        )

        result  = json.loads(response.output_text)
        matches = [Fitment(**m).model_dump() for m in result["matches"]]
        print(f"Analysis complete — {len(matches)} match(es) found")

    except Exception as e:
        print("Error calling OpenAI API:", e)
        raise ValueError(f"Failed to generate fitment analysis: {str(e)}")

    return {"sender": sender, "subject": subject, "matches": matches}
