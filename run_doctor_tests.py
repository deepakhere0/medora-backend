import requests, json, sys

BASE = "http://localhost:8000/api/v1"
PASS = "TestPass123!"
ORG_ADMIN_EMAIL = "testadmin_doctor@medora.com"
SUPER_ADMIN_EMAIL = "superadmin_doctor@medora.com"


def pprint(label, status_code, body):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"  HTTP {status_code}")
    print(f"  {json.dumps(body, indent=2, default=str)[:800]}")


# ── Setup: register org_admin ─────────────────────────────────────────────
r = requests.post(
    f"{BASE}/auth/register",
    json={"email": ORG_ADMIN_EMAIL, "password": PASS, "role": "org_admin"},
)
if r.status_code not in (201, 400):
    print(f"FATAL: register org_admin -> {r.status_code} {r.text}")
    sys.exit(1)
print(f"org_admin register -> {r.status_code} ({'already exists' if r.status_code == 400 else 'created'})")

# ── Setup: register super_admin ───────────────────────────────────────────
r = requests.post(
    f"{BASE}/auth/register",
    json={"email": SUPER_ADMIN_EMAIL, "password": PASS, "role": "super_admin"},
)
if r.status_code not in (201, 400):
    print(f"FATAL: register super_admin -> {r.status_code} {r.text}")
    sys.exit(1)
print(f"super_admin register -> {r.status_code} ({'already exists' if r.status_code == 400 else 'created'})")

# ── Step 1: login as org_admin ────────────────────────────────────────────
r = requests.post(f"{BASE}/auth/login", json={"email": ORG_ADMIN_EMAIL, "password": PASS})
assert r.status_code == 200, f"Login failed: {r.text}"
org_token = r.json()["access_token"]
org_headers = {"Authorization": f"Bearer {org_token}"}
print(f"\nStep 1 - JWT obtained for org_admin")

# ── Check /auth/me for existing org_id ───────────────────────────────────
r_me = requests.get(f"{BASE}/auth/me", headers=org_headers)
me = r_me.json()
org_id = me.get("organization_id")

if org_id is None:
    # Try to create org
    r = requests.post(
        f"{BASE}/organizations/",
        json={"name": "Medora Test Hospital", "city": "San Francisco", "state": "CA"},
        headers=org_headers,
    )
    if r.status_code == 201:
        created_org_id = r.json()["id"]
        print(f"Organization created: {created_org_id}")
    elif r.status_code == 400 and "already" in r.text.lower():
        print("Org already created but not approved yet")
        created_org_id = None
    else:
        print(f"FATAL: org creation -> {r.status_code} {r.text}")
        sys.exit(1)

    # Login as super_admin and approve
    r2 = requests.post(f"{BASE}/auth/login", json={"email": SUPER_ADMIN_EMAIL, "password": PASS})
    super_token = r2.json()["access_token"]
    super_headers = {"Authorization": f"Bearer {super_token}"}

    if created_org_id:
        r3 = requests.patch(f"{BASE}/organizations/{created_org_id}/approve", headers=super_headers)
        assert r3.status_code == 200, f"Approval failed: {r3.text}"
        print(f"Organization approved")
    else:
        r_pending = requests.get(f"{BASE}/organizations/pending", headers=super_headers)
        pending = r_pending.json()
        if pending:
            r3 = requests.patch(
                f"{BASE}/organizations/{pending[0]['id']}/approve", headers=super_headers
            )
            print(f"Approved pending org: {r3.status_code}")

    # Refresh org_admin token and get org_id
    r4 = requests.post(f"{BASE}/auth/login", json={"email": ORG_ADMIN_EMAIL, "password": PASS})
    org_token = r4.json()["access_token"]
    org_headers = {"Authorization": f"Bearer {org_token}"}
    r_me2 = requests.get(f"{BASE}/auth/me", headers=org_headers)
    org_id = r_me2.json()["organization_id"]
    print(f"Fresh token obtained for org_admin")

print(f"\norg_id = {org_id}")

# ── Clean up any leftover doctors from prior runs ─────────────────────────
r_list = requests.get(f"{BASE}/doctors", headers=org_headers)
existing_docs = r_list.json().get("doctors", [])
for d in existing_docs:
    requests.delete(f"{BASE}/doctors/{d['id']}", headers=org_headers)
if existing_docs:
    print(f"Cleaned up {len(existing_docs)} existing doctor(s) from prior runs")

print(f"\n{'='*60}")
print(f"  SETUP COMPLETE — Running 8 Tests")
print(f"{'='*60}")

results = {}

# ── Test A: Stats before any doctor ──────────────────────────────────────
r = requests.get(f"{BASE}/doctors/stats", headers=org_headers)
body = r.json()
pprint("Test A — GET /doctors/stats (before create)", r.status_code, body)
expected_a = {"total_doctors": 0, "on_duty_count": 0, "on_leave_count": 0, "new_this_week": 0}
if r.status_code == 200 and all(body.get(k) == v for k, v in expected_a.items()):
    results["A"] = "PASS"
    print("  >>> PASS")
else:
    results["A"] = "FAIL"
    print(f"  >>> FAIL  expected {expected_a}, got {body}")

# ── Test B: Create doctor ─────────────────────────────────────────────────
doctor_payload = {
    "name": "Dr. John Doe",
    "gender": "male",
    "specialization": "Cardiology",
    "experience_years": 12,
    "license_number": "MD-992384-CA",
    "license_expiry": "2027-10-24",
    "employment_type": "full_time",
    "phone": "+1 555 123 4567",
    "email": "john.doe@medora.com",
    "education": "Johns Hopkins University, MD",
    "certifications": ["Board Certified Cardiologist", "ACLS Certified"],
}
r = requests.post(f"{BASE}/doctors", json=doctor_payload, headers=org_headers)
body = r.json()
pprint("Test B — POST /doctors", r.status_code, body)
if r.status_code == 201 and body.get("name") == "Dr. John Doe":
    doctor_id = body["id"]
    results["B"] = "PASS"
    print(f"  >>> PASS  doctor_id={doctor_id}")
else:
    results["B"] = "FAIL"
    print(f"  >>> FAIL  status={r.status_code} detail={body.get('detail')}")
    sys.exit(1)

# ── Test C: List doctors ──────────────────────────────────────────────────
r = requests.get(f"{BASE}/doctors", headers=org_headers)
body = r.json()
pprint("Test C — GET /doctors", r.status_code, body)
if r.status_code == 200 and body.get("total") == 1 and len(body.get("doctors", [])) == 1:
    results["C"] = "PASS"
    print("  >>> PASS")
else:
    results["C"] = "FAIL"
    print(f"  >>> FAIL  total={body.get('total')} count={len(body.get('doctors', []))}")

# ── Test D: Get single doctor ─────────────────────────────────────────────
r = requests.get(f"{BASE}/doctors/{doctor_id}", headers=org_headers)
body = r.json()
pprint("Test D — GET /doctors/{id}", r.status_code, body)
if r.status_code == 200 and body.get("id") == doctor_id and body.get("license_number") == "MD-992384-CA":
    results["D"] = "PASS"
    print("  >>> PASS")
else:
    results["D"] = "FAIL"
    print(f"  >>> FAIL  status={r.status_code}")

# ── Test E: Update status ─────────────────────────────────────────────────
r = requests.patch(
    f"{BASE}/doctors/{doctor_id}/status",
    json={"status": "on_duty"},
    headers=org_headers,
)
body = r.json()
pprint("Test E — PATCH /doctors/{id}/status", r.status_code, body)
if r.status_code == 200 and body.get("status") == "on_duty":
    results["E"] = "PASS"
    print("  >>> PASS")
else:
    results["E"] = "FAIL"
    print(f"  >>> FAIL  status={r.status_code} doctor_status={body.get('status')}")

# ── Test F: Stats after doctor exists ────────────────────────────────────
r = requests.get(f"{BASE}/doctors/stats", headers=org_headers)
body = r.json()
pprint("Test F — GET /doctors/stats (after create)", r.status_code, body)
if (
    r.status_code == 200
    and body.get("total_doctors") == 1
    and body.get("on_duty_count") == 1
    and body.get("new_this_week") == 1
):
    results["F"] = "PASS"
    print("  >>> PASS")
else:
    results["F"] = "FAIL"
    print(f"  >>> FAIL  {body}")

# ── Test G: Duplicate license ─────────────────────────────────────────────
r = requests.post(f"{BASE}/doctors", json=doctor_payload, headers=org_headers)
body = r.json()
pprint("Test G — POST /doctors (duplicate license)", r.status_code, body)
if r.status_code == 400 and "license" in body.get("detail", "").lower():
    results["G"] = "PASS"
    print("  >>> PASS")
else:
    results["G"] = "FAIL"
    print(f"  >>> FAIL  status={r.status_code} detail={body.get('detail')}")

# ── Test H: Soft delete + verify list empty ───────────────────────────────
r = requests.delete(f"{BASE}/doctors/{doctor_id}", headers=org_headers)
body = r.json()
pprint("Test H — DELETE /doctors/{id}", r.status_code, body)
if r.status_code == 200 and body.get("message") == "Doctor deactivated successfully":
    r2 = requests.get(f"{BASE}/doctors", headers=org_headers)
    b2 = r2.json()
    if b2.get("total") == 0 and len(b2.get("doctors", [])) == 0:
        results["H"] = "PASS"
        print("  >>> PASS  (deleted + list confirmed empty)")
    else:
        results["H"] = "FAIL"
        print(f"  >>> FAIL  list after delete: {b2}")
else:
    results["H"] = "FAIL"
    print(f"  >>> FAIL  status={r.status_code} body={body}")

# ── Summary ───────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print("  RESULTS SUMMARY")
print(f"{'='*60}")
for test, result in results.items():
    icon = "✓" if result == "PASS" else "✗"
    print(f"  {icon} Test {test}: {result}")
passed = sum(1 for v in results.values() if v == "PASS")
print(f"\n  {passed}/{len(results)} tests passed")
print(f"{'='*60}\n")
