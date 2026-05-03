#!/usr/bin/env python3
import boto3, json
from datetime import datetime, timezone, timedelta

REGION = "ap-south-1"
BUCKET = "resumescreenerstack-incomingemailsbucket6251efa3-j3mmwotfwqyh"
TOPIC_ARN = f"arn:aws:sns:{REGION}:719030485523:resume-screener-topic"

s3  = boto3.client("s3",            region_name=REGION)
lam = boto3.client("lambda",        region_name=REGION)
sfn = boto3.client("stepfunctions", region_name=REGION)
cw  = boto3.client("logs",          region_name=REGION)

# ── 1. S3 — did the email land? ──────────────────────────────────────────────
print("\n=== 1. S3 Bucket — Recent Objects ===")
objs = s3.list_objects_v2(Bucket=BUCKET, MaxKeys=10)
contents = objs.get("Contents", [])
if contents:
    # sort newest first
    contents.sort(key=lambda x: x["LastModified"], reverse=True)
    print(f"  Found {len(contents)} object(s). Most recent:")
    for obj in contents[:5]:
        print(f"  ✅  {obj['Key']}  ({obj['Size']} bytes)  @ {obj['LastModified']}")
else:
    print("  ❌  Bucket is EMPTY — email did not reach S3")

# ── 2. Step Functions — recent executions ────────────────────────────────────
print("\n=== 2. Step Functions — Recent Executions ===")
machines = sfn.list_state_machines()["stateMachines"]
screener = [m for m in machines if "ResumeScreener" in m["name"] or "resume" in m["name"].lower()]

if not screener:
    print("  ❌  No ResumeScreener state machine found")
else:
    sm_arn = screener[0]["stateMachineArn"]
    print(f"  State machine: {screener[0]['name']}")
    execs = sfn.list_executions(stateMachineArn=sm_arn, maxResults=5)["executions"]
    if not execs:
        print("  ❌  No executions found — StarterLambda may not have triggered")
    for ex in execs:
        status = ex["status"]
        icon = "✅" if status == "SUCCEEDED" else ("🔄" if status == "RUNNING" else "❌")
        print(f"  {icon}  {ex['name']}  status={status}  started={ex['startDate']}")

        # if failed or running, get details
        if status in ("FAILED", "TIMED_OUT", "ABORTED", "RUNNING"):
            detail = sfn.describe_execution(executionArn=ex["executionArn"])
            if status == "RUNNING":
                print(f"       Still running... input={detail.get('input','')[:200]}")
            else:
                print(f"       cause={detail.get('cause','N/A')[:300]}")
                print(f"       error={detail.get('error','N/A')}")

# ── 3. Lambda logs — StarterLambda ───────────────────────────────────────────
print("\n=== 3. StarterLambda — Recent Log Events ===")
try:
    fns = lam.list_functions()["Functions"]
    starter = next((f for f in fns if "Starter" in f["FunctionName"] or "starter" in f["FunctionName"].lower()), None)
    if not starter:
        print("  ❌  StarterLambda not found")
    else:
        fn_name = starter["FunctionName"]
        log_group = f"/aws/lambda/{fn_name}"
        print(f"  Log group: {log_group}")
        # get most recent log stream
        streams = cw.describe_log_streams(
            logGroupName=log_group,
            orderBy="LastEventTime",
            descending=True,
            limit=1
        )["logStreams"]
        if not streams:
            print("  ⚠️   No log streams found — Lambda may never have run")
        else:
            stream = streams[0]["logStreamName"]
            events = cw.get_log_events(
                logGroupName=log_group,
                logStreamName=stream,
                limit=30,
                startFromHead=False
            )["events"]
            for e in events:
                ts = datetime.fromtimestamp(e["timestamp"]/1000, tz=timezone.utc)
                print(f"  [{ts.strftime('%H:%M:%S')}] {e['message'].strip()}")
except Exception as e:
    print(f"  ❌  Could not fetch logs: {e}")

# ── 4. Lambda logs — ParserLambda ────────────────────────────────────────────
print("\n=== 4. ParserLambda — Recent Log Events ===")
try:
    parser = next((f for f in fns if "Parser" in f["FunctionName"] or "parser" in f["FunctionName"].lower()), None)
    if not parser:
        print("  ❌  ParserLambda not found")
    else:
        fn_name = parser["FunctionName"]
        log_group = f"/aws/lambda/{fn_name}"
        streams = cw.describe_log_streams(
            logGroupName=log_group,
            orderBy="LastEventTime",
            descending=True,
            limit=1
        )["logStreams"]
        if not streams:
            print("  ⚠️   No log streams — Lambda may never have run")
        else:
            stream = streams[0]["logStreamName"]
            events = cw.get_log_events(
                logGroupName=log_group,
                logStreamName=stream,
                limit=30,
                startFromHead=False
            )["events"]
            for e in events:
                ts = datetime.fromtimestamp(e["timestamp"]/1000, tz=timezone.utc)
                print(f"  [{ts.strftime('%H:%M:%S')}] {e['message'].strip()}")
except Exception as e:
    print(f"  ❌  Could not fetch logs: {e}")

print("\n=== Done ===\n")
