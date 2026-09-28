"""AgriGaurd backend tests — hit the live uvicorn process (conftest client rooted at /api)."""

import time
import uuid

ADMIN_EMAIL = "aishwaryajk701@gmail.com"
ADMIN_PASSWORD = "AgriGaurd@2026"


def _register(client):
    email = f"{uuid.uuid4().hex[:10]}@test.dev"
    r = client.post("/auth/register", json={"email": email, "password": "TestPass1",
                                            "name": "Test Farmer"})
    assert r.status_code == 200, r.text
    return r.json()


def test_root(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["message"] == "AgriGaurd API"


def test_register_login_me(client):
    data = _register(client)
    assert data["access_token"] and data["user"]["role"] == "FARMER"
    # cookie session works
    me = client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == data["user"]["email"]
    # Bearer works too
    me2 = client.get("/auth/me", headers={"Authorization": f"Bearer {data['access_token']}"})
    assert me2.status_code == 200


def test_register_weak_password(client):
    r = client.post("/auth/register", json={"email": f"{uuid.uuid4().hex[:6]}@t.dev",
                                            "password": "abcdefgh", "name": "x"})
    assert r.status_code == 422


def test_login_invalid(client):
    r = client.post("/auth/login", json={"email": "nobody@test.dev", "password": "WrongPass1"})
    assert r.status_code == 401


def test_protected_endpoints_require_auth(client):
    for path in ("/fields", "/analyses", "/notifications", "/alerts/preferences"):
        assert client.get(path).status_code == 401


def test_invalid_token(client):
    r = client.get("/auth/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert r.status_code == 401


def test_field_crud_and_polygon_validation(client):
    _register(client)
    # invalid polygon: fewer than 3 points
    r = client.post("/fields", json={"name": "Bad", "coordinates": [[77.2, 28.5], [77.3, 28.6]]})
    assert r.status_code == 400
    # zero-area (degenerate, collinear)
    r = client.post("/fields", json={"name": "Bad2", "coordinates": [[77.2, 28.5], [77.2, 28.5], [77.2, 28.5]]})
    assert r.status_code == 400
    # out-of-bounds
    r = client.post("/fields", json={"name": "Bad3", "coordinates": [[200.0, 28.5], [77.3, 28.6], [77.3, 28.5]]})
    assert r.status_code == 400
    # valid
    coords = [[77.20, 28.55], [77.22, 28.55], [77.22, 28.57], [77.20, 28.57], [77.20, 28.55]]
    r = client.post("/fields", json={"name": "North Plot", "state": "Delhi", "district": "New Delhi",
                                     "village": "Jharoda", "coordinates": coords})
    assert r.status_code == 200, r.text
    f = r.json()
    assert f["area_ha"] > 4.0 and f["bbox"][0] == 77.20
    fid = f["id"]
    assert client.get(f"/fields/{fid}").status_code == 200
    r = client.patch(f"/fields/{fid}", json={"name": "North Plot 2"})
    assert r.json()["name"] == "North Plot 2"
    assert client.get("/fields").json()[0]["id"] == fid
    assert client.delete(f"/fields/{fid}").status_code == 200


def test_cross_user_isolation(client):
    a = _register(client)
    coords = [[77.20, 28.55], [77.22, 28.55], [77.22, 28.57], [77.20, 28.57], [77.20, 28.55]]
    fid = client.post("/fields", json={"name": "A", "coordinates": coords}).json()["id"]
    import httpx
    with httpx.Client(base_url="http://localhost:8001/api", timeout=30) as b:
        b.post("/auth/register", json={"email": f"{uuid.uuid4().hex[:8]}@t.dev",
                                       "password": "TestPass1", "name": "B"})
        assert b.get(f"/fields/{fid}").status_code == 404
        assert b.get(f"/analyses/{fid}").status_code == 404


def test_analyze_invalid_polygon(client):
    _register(client)
    r = client.post("/analyze", json={"coordinates": [[77.2, 28.5]]})
    assert r.status_code == 400


def _wait_job(client, job_id, timeout_s=120):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        j = client.get(f"/analysis/jobs/{job_id}").json()
        if j["state"] in ("COMPLETED", "PARTIAL", "FAILED"):
            return j
        time.sleep(2)
    raise AssertionError("job did not finish in time")


def test_demo_analysis_pipeline(client):
    _register(client)
    coords = [[77.20, 28.55], [77.22, 28.55], [77.22, 28.57], [77.20, 28.57], [77.20, 28.55]]
    r = client.post("/analyze", json={"coordinates": coords, "demo": True})
    assert r.status_code == 200
    job = _wait_job(client, r.json()["job_id"])
    assert job["state"] in ("COMPLETED", "PARTIAL"), job
    assert all(s["status"] == "done" for s in job["stages"].values()), job["stages"]
    a = client.get(f"/analyses/{job['analysis_id']}").json()
    assert a["demo"] is True
    flood = a["flood"]
    assert flood["available"] is True                      # demo SAR pair processed
    assert flood["agricultural_flood_pct"] is not None     # never fabricated — computed
    assert flood["confidence"]["score"] >= 0
    assert a["land_suitability"]["score"] >= 0
    assert 1 <= len(a["crops"]["recommendations"]) <= 5
    assert a["data_quality"]["score"] >= 0
    assert a["sources"]["sentinel1"].startswith("NOT CONFIGURED") or "Sentinel" in a["sources"]["sentinel1"]
    # stages recorded for the pipeline tracker
    assert job["stages"]["processing_sar"]["status"] == "done"


def test_real_mode_never_fabricates_flood(client):
    _register(client)
    status = client.get("/satellite/status").json()
    if status["sentinel_hub_configured"]:
        return  # real mode active; flood availability is data-driven
    coords = [[77.20, 28.55], [77.22, 28.55], [77.22, 28.57], [77.20, 28.57], [77.20, 28.55]]
    r = client.post("/analyze", json={"coordinates": coords, "demo": False})
    job = _wait_job(client, r.json()["job_id"])
    assert job["state"] in ("COMPLETED", "PARTIAL")
    a = client.get(f"/analyses/{job['analysis_id']}").json()
    assert a["flood"]["available"] is False                # DATA UNAVAILABLE, not fake
    assert a["flood"]["status"] == "UNAVAILABLE"
    assert "not configured" in a["flood"]["sar"]["reason"].lower()


def test_crop_recommendation_endpoint(client):
    _register(client)
    coords = [[77.20, 28.55], [77.22, 28.55], [77.22, 28.57], [77.20, 28.57], [77.20, 28.55]]
    r = client.post("/crops/recommend", json={"coordinates": coords, "state": "Delhi"})
    assert r.status_code == 200, r.text
    recs = r.json()["recommendations"]
    assert 3 <= len(recs) <= 5
    scores = [c["score"] for c in recs]
    assert scores == sorted(scores, reverse=True)
    assert all(c.get("why") or c.get("risks") for c in recs)


def test_crops_kb(client):
    _register(client)
    r = client.get("/crops")
    assert r.status_code == 200
    assert r.json()["count"] >= 10
    rice = [c for c in r.json()["crops"] if "Rice" in c["name"]][0]
    assert rice["flood_tolerance"] == 5 and rice["ph_min"] <= 7.0


def test_notifications_after_flood_demo(client):
    _register(client)
    coords = [[77.20, 28.55], [77.22, 28.55], [77.22, 28.57], [77.20, 28.57], [77.20, 28.55]]
    job = _wait_job(client, client.post("/analyze", json={"coordinates": coords, "demo": True}).json()["job_id"])
    a = client.get(f"/analyses/{job['analysis_id']}").json()
    notes = client.get("/notifications").json()
    if a["flood"]["severity"] in ("low", "moderate", "high", "critical"):
        assert any(n["kind"] == "flood" for n in notes)
    assert client.post("/notifications/read-all").json()["ok"] is True


def test_report_pdf(client):
    _register(client)
    coords = [[77.20, 28.55], [77.22, 28.55], [77.22, 28.57], [77.20, 28.57], [77.20, 28.55]]
    job = _wait_job(client, client.post("/analyze", json={"coordinates": coords, "demo": True}).json()["job_id"])
    r = client.get(f"/reports/analyses/{job['analysis_id']}/report.pdf")
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"
    # ReportLab compresses page text, so assert on the PDF metadata title instead
    assert b"AgriGaurd Analysis Report" in r.content
    assert len(r.content) > 3000


def test_export_csv(client):
    _register(client)
    coords = [[77.20, 28.55], [77.22, 28.55], [77.22, 28.57], [77.20, 28.57], [77.20, 28.55]]
    job = _wait_job(client, client.post("/analyze", json={"coordinates": coords, "demo": True}).json()["job_id"])
    r = client.get(f"/analyses/{job['analysis_id']}/export/csv")
    assert r.status_code == 200 and "agricultural_flood_pct" in r.text
    assert client.get("/export/csv").status_code == 200


def test_compare(client):
    _register(client)
    coords = [[77.20, 28.55], [77.22, 28.55], [77.22, 28.57], [77.20, 28.57], [77.20, 28.55]]
    j1 = _wait_job(client, client.post("/analyze", json={"coordinates": coords, "demo": True}).json()["job_id"])
    j2 = _wait_job(client, client.post("/analyze", json={"coordinates": coords, "demo": True}).json()["job_id"])
    r = client.get(f"/analyses/{j1['analysis_id']}/compare/{j2['analysis_id']}")
    assert r.status_code == 200
    assert "agricultural_flood_pct" in r.json()["deltas"]


def test_field_analyze_and_monitoring(client):
    _register(client)
    coords = [[77.20, 28.55], [77.22, 28.55], [77.22, 28.57], [77.20, 28.57], [77.20, 28.55]]
    fid = client.post("/fields", json={"name": "M", "coordinates": coords}).json()["id"]
    job = _wait_job(client, client.post(f"/fields/{fid}/analyze?demo=true").json()["job_id"])
    assert job["state"] in ("COMPLETED", "PARTIAL")
    f = client.get(f"/fields/{fid}").json()
    assert f["flood_status"] != "UNKNOWN" and f["land_suitability"] is not None
    r = client.put(f"/fields/{fid}/monitoring", json={"frequency": "weekly", "enabled": True})
    assert r.status_code == 200 and r.json()["enabled"] is True
    r = client.post(f"/fields/{fid}/monitoring/scan")
    assert r.status_code == 200 and "job_id" in r.json()
    assert client.get(f"/fields/{fid}/history").status_code == 200


def test_admin_roles(client):
    _register(client)  # farmer
    assert client.get("/admin/overview").status_code == 403
    r = client.post("/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200
    assert client.get("/admin/overview").status_code == 200
    assert "counts" in client.get("/admin/overview").json()


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    checks = r.json()["checks"]
    assert {"MongoDB", "Open-Meteo weather & DEM"} <= {c["service"] for c in checks}
    assert all(c["status"] in ("CONNECTED", "NOT CONFIGURED", "ERROR", "OPTIONAL") for c in checks)


def test_geocode(client):
    _register(client)
    r = client.get("/satellite/geocode", params={"q": "New Delhi"})
    assert r.status_code == 200
    assert len(r.json()["results"]) >= 1


def test_satellite_discovery_unconfigured(client):
    _register(client)
    status = client.get("/satellite/status").json()
    coords = [[77.20, 28.55], [77.22, 28.55], [77.22, 28.57], [77.20, 28.57], [77.20, 28.55]]
    r = client.post("/satellite/discover", json={"coordinates": coords})
    assert r.status_code == 200
    if not status["sentinel_hub_configured"]:
        assert r.json()["sentinel_hub_configured"] is False
        assert r.json()["observations"] == []


def test_seed_ai_requires_valid_image(client):
    _register(client)
    r = client.post("/seed/analyze", json={"image_base64": "!!!not-base64!!!"})
    assert r.status_code == 400
