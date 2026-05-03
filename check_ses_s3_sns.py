#!/usr/bin/env python3
import boto3
from datetime import datetime, timezone

REGION = "ap-south-1"
BUCKET = "resumescreenerstack-incomingemailsbucket6251efa3-j3mmwotfwqyh"
TOPIC_ARN = f"arn:aws:sns:{REGION}:719030485523:resume-screener-topic"

s3  = boto3.client("s3",  region_name=REGION)
sns = boto3.client("sns", region_name=REGION)
cw  = boto3.client("logs", region_name=REGION)

# ── 1. S3 — did the email land? ──────────────────────────────────────────────
print("\n=== S3 Bucket Contents ===")
objs = s3.list_objects_v2(Bucket=BUCKET)
contents = objs.get("Contents", [])
if not contents:
    print("  ❌  Bucket is EMPTY — email did NOT reach S3")
else:
    contents.sort(key=lambda x: x["LastModified"], reverse=True)
    for obj in contents:
        print(f"  key  : {obj['Key']}")
        print(f"  size : {obj['Size']} bytes")
        print(f"  time : {obj['LastModified']}")
        print()

# ── 2. SNS — was a notification published? (check CloudWatch SNS metrics) ────
print("=== SNS Topic Delivery (last publish check via topic attributes) ===")
attrs = sns.get_topic_attributes(TopicArn=TOPIC_ARN)["Attributes"]
print(f"  Subscriptions confirmed : {attrs.get('SubscriptionsConfirmed')}")
print(f"  Subscriptions pending   : {attrs.get('SubscriptionsPending')}")

# List subscriptions to confirm Lambda is wired up
print("\n=== SNS Subscriptions ===")
subs = sns.list_subscriptions_by_topic(TopicArn=TOPIC_ARN)["Subscriptions"]
if not subs:
    print("  ❌  No subscriptions")
for s in subs:
    arn = s["SubscriptionArn"]
    status = "✅ confirmed" if arn != "PendingConfirmation" else "⚠️  PENDING"
    print(f"  {status}  protocol={s['Protocol']}  endpoint={s['Endpoint']}")
