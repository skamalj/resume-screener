#!/usr/bin/env python3
import boto3, json

iam = boto3.client("iam")
ROLE = "resume-app-role"

print(f"\n=== Inline Policies on {ROLE} ===")
inline = iam.list_role_policies(RoleName=ROLE)["PolicyNames"]
if not inline:
    print("  (none)")
for name in inline:
    doc = iam.get_role_policy(RoleName=ROLE, PolicyName=name)["PolicyDocument"]
    print(f"\n  Policy: {name}")
    print(json.dumps(doc, indent=4))

print(f"\n=== Attached Managed Policies on {ROLE} ===")
attached = iam.list_attached_role_policies(RoleName=ROLE)["AttachedPolicies"]
if not attached:
    print("  (none)")
for p in attached:
    print(f"\n  {p['PolicyName']}  ({p['PolicyArn']})")
    version = iam.get_policy(PolicyArn=p["PolicyArn"])["Policy"]["DefaultVersionId"]
    doc = iam.get_policy_version(PolicyArn=p["PolicyArn"], VersionId=version)["PolicyVersion"]["Document"]
    print(json.dumps(doc, indent=4))
