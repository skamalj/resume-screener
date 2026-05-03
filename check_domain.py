#!/usr/bin/env python3
import boto3
import socket
import dns.resolver  # dnspython

REGION = "ap-south-1"
DOMAIN = "screener.mockify.ai"
EMAIL  = "resume@screener.mockify.ai"

ses = boto3.client("ses", region_name=REGION)

# ── 1. SES domain/email verification ─────────────────────────────────────────
print("\n=== SES Verification Status ===")
resp = ses.get_identity_verification_attributes(Identities=[DOMAIN, EMAIL])
attrs = resp.get("VerificationAttributes", {})
if not attrs:
    print(f"  ❌  Neither {DOMAIN} nor {EMAIL} are registered with SES at all")
for identity, attr in attrs.items():
    status = attr.get("VerificationStatus")
    icon = "✅" if status == "Success" else "❌"
    print(f"  {icon}  {identity}  →  {status}")

# ── 2. MX record check ────────────────────────────────────────────────────────
print("\n=== MX Record for screener.mockify.ai ===")
try:
    answers = dns.resolver.resolve(DOMAIN, "MX")
    for r in answers:
        mx = str(r.exchange).rstrip(".")
        pref = r.preference
        expected = f"inbound-smtp.{REGION}.amazonaws.com"
        icon = "✅" if expected in mx else "⚠️ "
        print(f"  {icon}  priority={pref}  mx={mx}")
        if expected not in mx:
            print(f"       Expected: {expected}")
except dns.resolver.NXDOMAIN:
    print(f"  ❌  No DNS records found for {DOMAIN} at all")
except dns.resolver.NoAnswer:
    print(f"  ❌  No MX record set for {DOMAIN} — SES cannot receive mail for this domain")
except Exception as e:
    print(f"  ❌  DNS lookup failed: {e}")

# ── 3. SES sandbox status ─────────────────────────────────────────────────────
print("\n=== SES Account Sending Status ===")
try:
    quota = ses.get_send_quota()
    print(f"  Max 24hr send    : {quota['Max24HourSend']}")
    print(f"  Sent last 24hrs  : {quota['SentLast24Hours']}")
    if quota['Max24HourSend'] == 200.0:
        print("  ⚠️   Looks like SES sandbox (200/day limit) — but inbound is NOT affected by sandbox")
    else:
        print("  ✅  SES is out of sandbox (production access)")
except Exception as e:
    print(f"  Could not check quota: {e}")
