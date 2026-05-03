#!/usr/bin/env python3
"""
SES → S3 → SNS → Lambda diagnostic script
"""
import boto3
import json
from botocore.exceptions import ClientError

REGION = "ap-south-1"
ACCOUNT = "719030485523"
TOPIC_ARN = f"arn:aws:sns:{REGION}:{ACCOUNT}:resume-screener-topic"
BUCKET = "resumescreenerstack-incomingemailsbucket6251efa3-j3mmwotfwqyh"
ROLE_NAME = "resume-app-role"
RULE_SET = "resume"
RULE_NAME = "resume-screener"
EMAIL_ADDRESS = "resume@screener.mockify.ai"

ok   = lambda msg: print(f"  ✅  {msg}")
warn = lambda msg: print(f"  ⚠️   {msg}")
fail = lambda msg: print(f"  ❌  {msg}")
info = lambda msg: print(f"  ℹ️   {msg}")

ses    = boto3.client("ses",    region_name=REGION)
sns    = boto3.client("sns",    region_name=REGION)
s3     = boto3.client("s3",     region_name=REGION)
iam    = boto3.client("iam")
lam    = boto3.client("lambda", region_name=REGION)
sfn    = boto3.client("stepfunctions", region_name=REGION)

# ── 1. SES receipt rule ──────────────────────────────────────────────────────
print("\n=== 1. SES Receipt Rule ===")
try:
    rs = ses.describe_active_receipt_rule_set()
    meta = rs.get("Metadata", {})
    rules = rs.get("Rules", [])
    ok(f"Active rule set: {meta.get('Name')}")

    rule = next((r for r in rules if r["Name"] == RULE_NAME), None)
    if not rule:
        fail(f"Rule '{RULE_NAME}' not found in active rule set")
    else:
        ok(f"Rule '{RULE_NAME}' exists, enabled={rule['Enabled']}")
        recipients = rule.get("Recipients", [])
        if EMAIL_ADDRESS in recipients:
            ok(f"Recipient {EMAIL_ADDRESS} is configured")
        else:
            fail(f"Recipient {EMAIL_ADDRESS} NOT in rule. Found: {recipients}")

        actions = rule.get("Actions", [])
        s3_action = next((a.get("S3Action") for a in actions if "S3Action" in a), None)
        if s3_action:
            ok(f"S3Action present → bucket: {s3_action.get('BucketName')}")
            if s3_action.get("TopicArn"):
                ok(f"S3Action SNS notification → {s3_action['TopicArn']}")
            else:
                warn("S3Action has no TopicArn — SNS notification from S3Action is not set")
            if s3_action.get("IamRoleArn"):
                ok(f"S3Action IAM role → {s3_action['IamRoleArn']}")
            else:
                warn("S3Action has no IamRoleArn — SES will use bucket policy instead")
        else:
            fail("No S3Action found in rule")
except Exception as e:
    fail(f"Could not describe SES rule set: {e}")

# ── 2. SES domain/email verification ────────────────────────────────────────
print("\n=== 2. SES Domain Verification ===")
try:
    domain = "screener.mockify.ai"
    resp = ses.get_identity_verification_attributes(Identities=[domain, EMAIL_ADDRESS])
    attrs = resp.get("VerificationAttributes", {})
    for identity, attr in attrs.items():
        status = attr.get("VerificationStatus")
        if status == "Success":
            ok(f"{identity} → verified")
        else:
            fail(f"{identity} → status={status} (NOT verified — SES will reject inbound mail)")
    if not attrs:
        fail(f"Neither {domain} nor {EMAIL_ADDRESS} are registered with SES")
except Exception as e:
    fail(f"Could not check SES verification: {e}")

# ── 3. S3 bucket policy ──────────────────────────────────────────────────────
print("\n=== 3. S3 Bucket Policy (SES write permission) ===")
try:
    pol = s3.get_bucket_policy(Bucket=BUCKET)
    policy = json.loads(pol["Policy"])
    stmts = policy.get("Statement", [])
    ses_write = any(
        "ses.amazonaws.com" in json.dumps(s.get("Principal", {})) and
        any(a in json.dumps(s.get("Action", [])) for a in ["s3:PutObject", "s3:*"])
        for s in stmts
    )
    role_write = any(
        ROLE_NAME in json.dumps(s.get("Principal", {})) and
        any(a in json.dumps(s.get("Action", [])) for a in ["s3:PutObject", "s3:*"])
        for s in stmts
    )
    if ses_write:
        ok("Bucket policy allows ses.amazonaws.com to PutObject")
    elif role_write:
        ok(f"Bucket policy allows {ROLE_NAME} to write (SES uses this role)")
    else:
        fail("Bucket policy does NOT grant SES or the IAM role write access — emails won't be saved!")
        info("Need a statement like: Principal={Service: ses.amazonaws.com}, Action: s3:PutObject")
        info(f"Or grant PutObject to arn:aws:iam::{ACCOUNT}:role/{ROLE_NAME}")
    info(f"Current statements: {json.dumps(stmts, indent=2)}")
except ClientError as e:
    if e.response["Error"]["Code"] == "NoSuchBucketPolicy":
        fail("Bucket has NO policy — SES cannot write emails to it unless using IAM role with bucket ACL")
    else:
        fail(f"Could not get bucket policy: {e}")

# ── 4. IAM role permissions ──────────────────────────────────────────────────
print("\n=== 4. IAM Role (resume-app-role) ===")
try:
    role = iam.get_role(RoleName=ROLE_NAME)["Role"]
    trust = role["AssumeRolePolicyDocument"]
    principals = [
        s.get("Principal", {})
        for s in trust.get("Statement", [])
    ]
    ses_trusted = any("ses.amazonaws.com" in json.dumps(p) for p in principals)
    if ses_trusted:
        ok("Trust policy allows ses.amazonaws.com to assume this role")
    else:
        fail(f"ses.amazonaws.com is NOT in the trust policy. Found: {principals}")

    # inline policies
    inline = iam.list_role_policies(RoleName=ROLE_NAME)["PolicyNames"]
    for pname in inline:
        doc = iam.get_role_policy(RoleName=ROLE_NAME, PolicyName=pname)["PolicyDocument"]
        stmts = doc.get("Statement", [])
        s3_write = any(
            any(a in json.dumps(s.get("Action", [])) for a in ["s3:PutObject", "s3:*"])
            for s in stmts
        )
        if s3_write:
            ok(f"Inline policy '{pname}' grants S3 write")
        else:
            info(f"Inline policy '{pname}': {json.dumps(stmts)}")

    # attached policies
    attached = iam.list_attached_role_policies(RoleName=ROLE_NAME)["AttachedPolicies"]
    for p in attached:
        ok(f"Attached managed policy: {p['PolicyName']} ({p['PolicyArn']})")
    if not inline and not attached:
        fail("Role has NO policies — it cannot write to S3!")
except Exception as e:
    fail(f"Could not inspect IAM role: {e}")

# ── 5. SNS topic & subscriptions ────────────────────────────────────────────
print("\n=== 5. SNS Topic & Subscriptions ===")
try:
    attrs = sns.get_topic_attributes(TopicArn=TOPIC_ARN)["Attributes"]
    ok(f"Topic exists: {attrs.get('TopicArn')}")
    ok(f"Confirmed subscriptions: {attrs.get('SubscriptionsConfirmed')}")
    ok(f"Pending subscriptions:   {attrs.get('SubscriptionsPending')}")

    policy = json.loads(attrs.get("Policy", "{}"))
    ses_publish = any(
        "ses.amazonaws.com" in json.dumps(s.get("Principal", {}))
        for s in policy.get("Statement", [])
    )
    if ses_publish:
        ok("SNS topic policy allows ses.amazonaws.com to Publish")
    else:
        fail("SNS topic policy does NOT allow ses.amazonaws.com to Publish — SES can't send notifications!")

    # list subscriptions
    subs = sns.list_subscriptions_by_topic(TopicArn=TOPIC_ARN)["Subscriptions"]
    if subs:
        for sub in subs:
            status = "confirmed" if sub["SubscriptionArn"] != "PendingConfirmation" else "PENDING"
            ok(f"Subscription [{status}]: {sub['Protocol']} → {sub['Endpoint']}")
    else:
        fail("No subscriptions on this topic — nothing will receive the SNS notification!")
except Exception as e:
    fail(f"Could not inspect SNS topic: {e}")

# ── 6. Lambda (StarterLambda) ────────────────────────────────────────────────
print("\n=== 6. Lambda Functions ===")
try:
    fns = lam.list_functions()["Functions"]
    screener_fns = [f for f in fns if "ResumeScreener" in f["FunctionName"] or "resume" in f["FunctionName"].lower()]
    if not screener_fns:
        warn("No ResumeScreener Lambda functions found (may be named differently)")
    for fn in screener_fns:
        name = fn["FunctionName"]
        state = fn.get("State", "Active")
        ok(f"{name} — state={state}, runtime={fn['Runtime']}")
        # check env vars
        env = fn.get("Environment", {}).get("Variables", {})
        if "EMAIL_BUCKET" in env:
            ok(f"  EMAIL_BUCKET={env['EMAIL_BUCKET']}")
        if "STATE_MACHINE_ARN" in env:
            ok(f"  STATE_MACHINE_ARN set")
        elif "Starter" in name or "starter" in name.lower():
            fail(f"  STATE_MACHINE_ARN missing from {name}!")
except Exception as e:
    fail(f"Could not list Lambda functions: {e}")

# ── 7. Step Functions ────────────────────────────────────────────────────────
print("\n=== 7. Step Functions State Machine ===")
try:
    machines = sfn.list_state_machines()["stateMachines"]
    screener_sm = [m for m in machines if "ResumeScreener" in m["name"] or "resume" in m["name"].lower()]
    if screener_sm:
        for sm in screener_sm:
            ok(f"State machine: {sm['name']} ({sm['stateMachineArn']})")
    else:
        fail("No ResumeScreener state machine found")
except Exception as e:
    fail(f"Could not list state machines: {e}")

# ── 8. Recent S3 objects (did any emails land?) ──────────────────────────────
print("\n=== 8. Recent Emails in S3 Bucket ===")
try:
    objs = s3.list_objects_v2(Bucket=BUCKET, MaxKeys=5)
    contents = objs.get("Contents", [])
    if contents:
        ok(f"Found {objs['KeyCount']} object(s) in bucket (showing up to 5):")
        for obj in contents:
            info(f"  {obj['Key']}  ({obj['Size']} bytes, {obj['LastModified']})")
    else:
        warn("Bucket is empty — no emails have been received yet (or they were deleted)")
except Exception as e:
    fail(f"Could not list S3 objects: {e}")

print("\n=== Diagnosis Complete ===\n")
