# How to Attach Base64 `.docx` Files for Summarization with OpenAI

If you've been trying to pass base64-encoded Word documents (`.docx`) to OpenAI and encountering MIME type errors like `Invalid MIME type` or `unsupported MIME type`, you are not alone. This guide explains how to fix this and successfully attach `.docx` files natively.

## The Problem
Many developers attempt to pass base64 documents using the standard **Chat Completions API** (`client.chat.completions.create()`) via the `type: "file"` or `type: "image_url"` message schemas. 

However, the Chat Completions API strictly enforces PDF for base64 file payloads and will throw an error when it sees the `.docx` MIME type (`application/vnd.openxmlformats-officedocument.wordprocessingml.document`).

## The Solution: Use the Responses API
To successfully attach `.docx` files as base64, you **must use the new OpenAI Responses API** (`client.responses.create()`). 

This endpoint officially supports native text extraction from `.docx`, `.pptx`, `.csv`, `.xlsx`, and many other non-PDF file formats.

### Key Schema Differences
When using the Responses API:
1. Use `input` instead of `messages`.
2. Use `type: "input_file"` instead of `type: "file"`.
3. Provide the full data URI with the `.docx` MIME type.
4. Include the `filename` attribute.

## Full Python Implementation Example

Below is a complete, working example of how to attach **multiple** `.docx` files (e.g., a Job Description and a Resume) as base64 and force the model to return a structured JSON response.

```python
import os
import base64
from openai import OpenAI

def get_base64_file(filepath):
    """Helper function to read a file and encode it in base64."""
    with open(filepath, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def analyze_resume_match():
    # 1. Initialize the OpenAI Client
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    # 2. Get the Base64 strings of your documents
    jd_base64 = get_base64_file("citi_jd.docx")
    resume_base64 = get_base64_file("Kamaljeet_Singh.docx")

    # 3. Call the Responses API (Note: NOT chat.completions!)
    response = client.responses.create(
        model="gpt-4o",  # Must be a vision-capable model like gpt-4o
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "You are an expert technical recruiter."},
                    
                    # Attach Document 1
                    {"type": "input_text", "text": "Here is the Job Description:"},
                    {
                        "type": "input_file",
                        "filename": "citi_jd.docx",
                        "file_data": f"data:application/vnd.openxmlformats-officedocument.wordprocessingml.document;base64,{jd_base64}"
                    },
                    
                    # Attach Document 2
                    {"type": "input_text", "text": "Here is the Candidate's Resume:"},
                    {
                        "type": "input_file",
                        "filename": "Kamaljeet_Singh.docx",
                        "file_data": f"data:application/vnd.openxmlformats-officedocument.wordprocessingml.document;base64,{resume_base64}"
                    },
                    
                    # Prompt & JSON Formatting Instruction
                    {
                        "type": "input_text", 
                        "text": "Analyze how well the resume matches the job description. Return the summary and a match score from 1 to 10. Ensure the output is strictly valid JSON format matching this schema:\n{\n  \"res_match_score\": 8,\n  \"res_match_summary\": \"...\",\n  \"res_key_strengths\": [\"...\"],\n  \"res_key_gaps\": [\"...\"]\n}\n\nDo not include any markdown backticks, just the raw JSON."
                    }
                ]
            }
        ]
    )

    # 4. Print the resulting JSON string
    print(response.output_text)

if __name__ == "__main__":
    analyze_resume_match()
```

## Important Notes on Wrappers (LangChain / Pydantic-AI)
If you are using third-party wrappers, you will likely encounter issues:
* **Pydantic-AI**: Currently does not expose a structured way to pass `input_file` dicts into its `UserPromptPart`. If you pass the data URI as a string, it will be treated as raw text and fail to decode the binary document.
* **LangChain**: The standard `ChatOpenAI` wrapper hardcodes requests to the `/v1/chat/completions` API endpoint, which will result in the MIME type validation error. 

**Recommendation:** For attaching base64 `.docx` files, bypass your wrappers and use the official `openai` Python SDK with `client.responses.create()` exactly as shown in the example above.
