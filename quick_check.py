#!/usr/bin/env python3
import boto3, json
from datetime import datetime, timezone

REGION = "ap-south-1"
sfn = boto3.client("stepfunctions", region_name=REGION)
cw  = boto3.client("logs", region_name=REGION)
lam = boto3.client("lambda", region_name=REGION)

# Step Functions - latest 3 executions
machines = sfn.list_state_machines()["stateMachines"]
sm = next(m for m in machines if "ResumeScreener" in m["name"])
execs = sfn.list_executions(stateMachineArn=sm["stateMachineArn"], maxResults=3)["executions"]

print(f"=== Step Functions: {sm['name']} ===")
for ex in execs:
    status = ex["status"]
    icon = "✅" if status == "SUCCEEDED" else ("🔄" if status == "RUNNING" else "❌")
    print(f"{icon} {status}  {ex['startDate'].strftime('%H:%M:%S')}")
    d = sfn.describe_execution(executionArn=ex["executionArn"])
    if status not in ("SUCCEEDED", "RUNNING"):
        print(f"   error : {d.get('error')}")
        print(f"   cause : {d.get('cause','')[:200]}")
    else:
        print(f"   output: {d.get('output','')[:200]}")

    # last 5 history events
    h = sfn.get_execution_history(executionArn=ex["executionArn"], maxResults=10, reverseOrder=True)["events"]
    for ev in h[:6]:
        ts = ev["timestamp"].strftime("%H:%M:%S")
        dk = next((k for k in ev if k.endswith("EventDetails") and k != "previousEventId"), None)
        dv = json.dumps(ev.get(dk,{}))[:150] if dk else ""
        print(f"   [{ts}] {ev['type']}")
        if dv and dv != "{}": print(f"           {dv}")
    print()

# Quick log tail for each lambda
fns = {f["FunctionName"]: f for f in lam.list_functions()["Functions"] if "ResumeScreener" in f["FunctionName"]}
for role in ["Parser", "Analyzer", "Responder", "Error"]:
    fn_name = next((n for n in fns if role in n), None)
    if not fn_name:
        continue
    log_group = f"/aws/lambda/{fn_name}"
    print(f"=== {role}Lambda logs ===")
    try:
        streams = cw.describe_log_streams(logGroupName=log_group, orderBy="LastEventTime", descending=True, limit=1)["logStreams"]
        if not streams:
            print("  (never invoked)\n")
            continue
        events = cw.get_log_events(logGroupName=log_group, logStreamName=streams[0]["logStreamName"], limit=15, startFromHead=False)["events"]
        for e in events:
            ts = datetime.fromtimestamp(e["timestamp"]/1000, tz=timezone.utc).strftime("%H:%M:%S")
            msg = e["message"].strip()
            if msg:
                print(f"  [{ts}] {msg}")
    except Exception as ex:
        print(f"  (log group not found)")
    print()
