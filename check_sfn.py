#!/usr/bin/env python3
import boto3

REGION = "ap-south-1"
sfn = boto3.client("stepfunctions", region_name=REGION)
cw  = boto3.client("logs", region_name=REGION)
lam = boto3.client("lambda", region_name=REGION)
from datetime import datetime, timezone

# Step Functions
machines = sfn.list_state_machines()["stateMachines"]
sm = next(m for m in machines if "ResumeScreener" in m["name"])
print(f"State machine: {sm['name']}\n")

execs = sfn.list_executions(stateMachineArn=sm["stateMachineArn"], maxResults=3)["executions"]
if not execs:
    print("No executions yet")
else:
    for ex in execs:
        status = ex["status"]
        icon = "✅" if status == "SUCCEEDED" else ("🔄" if status == "RUNNING" else "❌")
        print(f"{icon} {status}  started={ex['startDate']}")
        d = sfn.describe_execution(executionArn=ex["executionArn"])
        print(f"   input  : {d.get('input','')[:200]}")
        if status == "SUCCEEDED":
            print(f"   output : {d.get('output','')[:300]}")
        elif status not in ("RUNNING",):
            print(f"   error  : {d.get('error','N/A')}")
            print(f"   cause  : {d.get('cause','')[:400]}")

        # execution history
        history = sfn.get_execution_history(executionArn=ex["executionArn"], maxResults=20, reverseOrder=True)["events"]
        print(f"\n   Execution history (latest first):")
        for ev in history[:15]:
            ts = ev["timestamp"].strftime("%H:%M:%S")
            etype = ev["type"]
            detail_key = next((k for k in ev if k.endswith("EventDetails") and k != "previousEventId"), None)
            detail_val = ""
            if detail_key:
                import json
                detail_val = json.dumps(ev.get(detail_key, {}))[:250]
            print(f"   [{ts}] {etype}")
            if detail_val and detail_val != "{}":
                print(f"           {detail_val}")
        print()

# Starter Lambda logs
print("="*50)
print("StarterLambda latest logs:")
fns = lam.list_functions()["Functions"]
starter = next((f for f in fns if "Starter" in f["FunctionName"]), None)
if starter:
    log_group = f"/aws/lambda/{starter['FunctionName']}"
    streams = cw.describe_log_streams(logGroupName=log_group, orderBy="LastEventTime", descending=True, limit=1)["logStreams"]
    if streams:
        events = cw.get_log_events(logGroupName=log_group, logStreamName=streams[0]["logStreamName"], limit=20, startFromHead=False)["events"]
        for e in events:
            ts = datetime.fromtimestamp(e["timestamp"]/1000, tz=timezone.utc).strftime("%H:%M:%S")
            print(f"  [{ts}] {e['message'].strip()}")

# Parser Lambda logs
print("\n" + "="*50)
print("ParserLambda latest logs:")
parser = next((f for f in fns if "Parser" in f["FunctionName"]), None)
if parser:
    log_group = f"/aws/lambda/{parser['FunctionName']}"
    try:
        streams = cw.describe_log_streams(logGroupName=log_group, orderBy="LastEventTime", descending=True, limit=1)["logStreams"]
        if streams:
            events = cw.get_log_events(logGroupName=log_group, logStreamName=streams[0]["logStreamName"], limit=30, startFromHead=False)["events"]
            for e in events:
                ts = datetime.fromtimestamp(e["timestamp"]/1000, tz=timezone.utc).strftime("%H:%M:%S")
                print(f"  [{ts}] {e['message'].strip()}")
        else:
            print("  (no log streams - never invoked)")
    except Exception as ex:
        print(f"  (log group not found - never invoked)")
