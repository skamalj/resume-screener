#!/usr/bin/env python3
"""
Trace the full pipeline: StarterLambda → StepFunctions → Parser → Analyzer → Responder
Just observe and report - no fixes.
"""
import boto3, json
from datetime import datetime, timezone

REGION = "ap-south-1"
cw  = boto3.client("logs",          region_name=REGION)
lam = boto3.client("lambda",        region_name=REGION)
sfn = boto3.client("stepfunctions", region_name=REGION)

def get_latest_logs(fn_name, num_events=40):
    log_group = f"/aws/lambda/{fn_name}"
    try:
        streams = cw.describe_log_streams(
            logGroupName=log_group,
            orderBy="LastEventTime",
            descending=True,
            limit=1
        )["logStreams"]
        if not streams:
            return ["  (no log streams found - Lambda has never been invoked)"]
        stream = streams[0]["logStreamName"]
        events = cw.get_log_events(
            logGroupName=log_group,
            logStreamName=stream,
            limit=num_events,
            startFromHead=False
        )["events"]
        lines = []
        for e in events:
            ts = datetime.fromtimestamp(e["timestamp"]/1000, tz=timezone.utc)
            lines.append(f"  [{ts.strftime('%H:%M:%S')}] {e['message'].strip()}")
        return lines or ["  (log stream exists but no events)"]
    except cw.exceptions.ResourceNotFoundException:
        return [f"  (log group {log_group} does not exist yet)"]
    except Exception as e:
        return [f"  ERROR fetching logs: {e}"]

# ── Get all function names ────────────────────────────────────────────────────
fns = lam.list_functions()["Functions"]
fn_map = {}
for f in fns:
    name = f["FunctionName"]
    if "ResumeScreener" in name:
        for role in ["Starter", "Parser", "Analyzer", "Responder", "Error"]:
            if role in name:
                fn_map[role] = name

print(f"\nFound Lambda functions: {json.dumps(fn_map, indent=2)}")

# ── 1. StarterLambda ─────────────────────────────────────────────────────────
print("\n" + "="*60)
print("STEP 1: StarterLambda")
print("  PURPOSE: Receives SNS notification from SES, extracts")
print("           messageId, builds S3 payload, starts Step Functions")
print("="*60)
if "Starter" in fn_map:
    print(f"\n  Function: {fn_map['Starter']}")
    print("\n  Latest logs:")
    for line in get_latest_logs(fn_map["Starter"]):
        print(line)
else:
    print("  ❌ StarterLambda not found")

# ── 2. Step Functions executions ─────────────────────────────────────────────
print("\n" + "="*60)
print("STEP 2: Step Functions State Machine")
print("  PURPOSE: Orchestrates Parser → Analyzer → Responder")
print("="*60)
machines = sfn.list_state_machines()["stateMachines"]
screener = [m for m in machines if "ResumeScreener" in m["name"]]
if not screener:
    print("  ❌ No state machine found")
else:
    sm = screener[0]
    print(f"\n  Machine: {sm['name']}")
    execs = sfn.list_executions(stateMachineArn=sm["stateMachineArn"], maxResults=5)["executions"]
    if not execs:
        print("  ❌ No executions — StarterLambda never successfully triggered Step Functions")
    for ex in execs:
        status = ex["status"]
        icon = "✅" if status == "SUCCEEDED" else ("🔄" if status == "RUNNING" else "❌")
        print(f"\n  {icon} Execution: {ex['name']}")
        print(f"     status  : {status}")
        print(f"     started : {ex['startDate']}")
        detail = sfn.describe_execution(executionArn=ex["executionArn"])
        print(f"     input   : {detail.get('input','')[:300]}")
        if status not in ("SUCCEEDED", "RUNNING"):
            print(f"     error   : {detail.get('error','N/A')}")
            print(f"     cause   : {detail.get('cause','N/A')[:400]}")
        if status == "SUCCEEDED":
            print(f"     output  : {detail.get('output','')[:300]}")

        # execution history - find failed events
        if status not in ("RUNNING",):
            try:
                history = sfn.get_execution_history(
                    executionArn=ex["executionArn"],
                    maxResults=50,
                    reverseOrder=True
                )["events"]
                print(f"\n     Last execution events (most recent first):")
                for ev in history[:15]:
                    etype = ev["type"]
                    ts = ev["timestamp"].strftime("%H:%M:%S")
                    detail_key = next((k for k in ev if k.endswith("EventDetails") and k != "previousEventId"), None)
                    detail_val = json.dumps(ev.get(detail_key, {}))[:200] if detail_key else ""
                    print(f"     [{ts}] {etype}")
                    if detail_val and detail_val != "{}":
                        print(f"             {detail_val}")
            except Exception as e:
                print(f"     Could not get execution history: {e}")

# ── 3. ParserLambda ──────────────────────────────────────────────────────────
print("\n" + "="*60)
print("STEP 3: ParserLambda")
print("  PURPOSE: Reads raw email from S3, extracts PDF/DOCX")
print("           attachments, uploads them to OpenAI Files API")
print("="*60)
if "Parser" in fn_map:
    print(f"\n  Function: {fn_map['Parser']}")
    print("\n  Latest logs:")
    for line in get_latest_logs(fn_map["Parser"]):
        print(line)
else:
    print("  ❌ ParserLambda not found")

# ── 4. AnalyzerLambda ────────────────────────────────────────────────────────
print("\n" + "="*60)
print("STEP 4: AnalyzerLambda")
print("  PURPOSE: Takes OpenAI file IDs, calls GPT for fitment")
print("           scoring between JDs and resumes")
print("="*60)
if "Analyzer" in fn_map:
    print(f"\n  Function: {fn_map['Analyzer']}")
    print("\n  Latest logs:")
    for line in get_latest_logs(fn_map["Analyzer"]):
        print(line)
else:
    print("  ❌ AnalyzerLambda not found")

# ── 5. ResponderLambda ───────────────────────────────────────────────────────
print("\n" + "="*60)
print("STEP 5: ResponderLambda")
print("  PURPOSE: Generates PDF report, sends response email via SES")
print("="*60)
if "Responder" in fn_map:
    print(f"\n  Function: {fn_map['Responder']}")
    print("\n  Latest logs:")
    for line in get_latest_logs(fn_map["Responder"]):
        print(line)
else:
    print("  ❌ ResponderLambda not found")

# ── 6. ErrorLambda ───────────────────────────────────────────────────────────
print("\n" + "="*60)
print("STEP 6: ErrorLambda")
print("  PURPOSE: Catches errors from any step, sends error email")
print("="*60)
if "Error" in fn_map:
    print(f"\n  Function: {fn_map['Error']}")
    print("\n  Latest logs:")
    for line in get_latest_logs(fn_map["Error"]):
        print(line)
else:
    print("  ❌ ErrorLambda not found")

print("\n" + "="*60)
print("TRACE COMPLETE")
print("="*60)
