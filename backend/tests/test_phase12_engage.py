from datetime import datetime, time, timedelta, timezone as dt_tz

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.core.tenant_context import tenant_context
from apps.engagement.models import Appointment, InstitutionalRequest
from apps.tenants.models import Branch

from .test_foundation import api, login, platform_admin, platform_client, register, settled_token, two_pharmacies  # noqa: F401
from .test_phase8 import PW, customer, env, move, order_body, place, stock  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


def slot(days=2, hour=10):
    d = (timezone.now() + timedelta(days=days)).date()
    return datetime.combine(d, time(hour, 0), tzinfo=dt_tz.utc).isoformat()


@pytest.fixture
def eng(env):
    g = env["g"]
    for k, role, br in (("drv", "delivery_personnel", env["main"]), ("drv2", "delivery_personnel", env["main"]), ("drvb", "delivery_personnel", env["second"]), ("bm", "branch_manager", env["main"])):
        User.objects.create_user(f"{k}@green.test", PW, tenant=g, full_name=f"{k.upper()} Driver", role=g.roles.get(code=role), branch=br)
        env[k] = api("greenlife", login("greenlife", f"{k}@green.test", PW).data["tokens"]["access"])
    env["uid"] = {k: User.objects.get(email=f"{k}@green.test").pk for k in ("drv", "drv2", "drvb")}
    return env


def mk_service(c, **kw):
    r = c.post("/api/v1/services/", {"name": "Blood pressure check", "description": "Quick check", "requires_booking": True, "duration_minutes": 30, "capacity": 1, "price": "5.00", **kw}, format="json")
    assert r.status_code == 201, r.data
    return r.data


# ---------------- services ----------------
def test_service_catalogue_rules_and_public_listing(eng):
    s = mk_service(eng["bm"])
    assert mk_service.__name__ and eng["admin"].post("/api/v1/services/", {"name": "blood pressure check"}, format="json").status_code == 400  # unique name
    assert eng["cash"].post("/api/v1/services/", {"name": "x"}, format="json").status_code == 403 and eng["cash"].get("/api/v1/services/").status_code == 403
    assert eng["admin"].post("/api/v1/services/", {"name": "Bad", "capacity": 0}, format="json").status_code == 400
    mk_service(eng["admin"], name="Hidden service", is_available=False)
    mk_service(eng["admin"], name="Second branch only", branches=[eng["second"].pk])
    pub = api().get("/api/v1/public/pharmacies/greenlife/services/").data
    assert {x["name"] for x in pub} == {"Blood pressure check", "Second branch only"}
    assert api().get("/api/v1/public/pharmacies/bluecross/services/").data == [] and api().get("/api/v1/public/pharmacies/nope/services/").status_code == 404
    assert eng["admin"].patch(f"/api/v1/services/{s['id']}/", {"price": "7.50"}, format="json").data["price"] == __import__("decimal").Decimal("7.50")
    assert eng["admin_b"].patch(f"/api/v1/services/{s['id']}/", {"price": "1"}, format="json").status_code == 404
    bad = eng["admin"].post("/api/v1/services/", {"name": "Img", "image": SimpleUploadedFile("x.svg", b"<svg/>", "image/svg+xml")}, format="multipart")
    assert bad.status_code == 400


# ---------------- appointments ----------------
def test_booking_capacity_hours_and_lifecycle(eng):
    s = mk_service(eng["admin"])
    a, b = customer(eng, "a@example.com"), customer(eng, "b@example.com")
    body = {"service": s["id"], "branch": eng["main"].pk, "start_at": slot(), "note": "First time"}
    r = a.post("/api/v1/shop/appointments/", body, format="json")
    assert r.status_code == 201 and r.data["status"] == "requested"
    assert any("Appointment request received" in m.subject for m in mail.outbox)
    assert b.post("/api/v1/shop/appointments/", body, format="json").status_code == 409  # capacity 1 per slot
    assert a.post("/api/v1/shop/appointments/", {**body, "start_at": slot(hour=11)}, format="json").status_code == 201  # next slot is free
    assert a.post("/api/v1/shop/appointments/", {**body, "start_at": (timezone.now() - timedelta(hours=1)).isoformat()}, format="json").status_code == 400
    assert a.post("/api/v1/shop/appointments/", {**body, "start_at": slot(days=120)}, format="json").status_code == 400
    assert b.post("/api/v1/shop/appointments/", {**body, "service": 99999}, format="json").status_code == 404
    walk_in = mk_service(eng["admin"], name="Walk-in advice", requires_booking=False)
    assert b.post("/api/v1/shop/appointments/", {**body, "service": walk_in["id"], "start_at": slot(hour=15)}, format="json").status_code == 409
    only2 = mk_service(eng["admin"], name="Branch two", branches=[eng["second"].pk])
    assert b.post("/api/v1/shop/appointments/", {**body, "service": only2["id"], "start_at": slot(hour=16)}, format="json").status_code == 400
    # opening hours (UTC in tests): closed on every day except 09:00-17:00 windows
    Branch.all_objects.filter(pk=eng["main"].pk).update(operating_hours={d: {"open": "09:00", "close": "17:00"} for d in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]})
    assert b.post("/api/v1/shop/appointments/", {**body, "start_at": slot(hour=20)}, format="json").status_code == 400
    assert b.post("/api/v1/shop/appointments/", {**body, "start_at": slot(hour=14)}, format="json").status_code == 201
    # staff handling stays inside the branch
    assert {x["customer_name"] for x in eng["cash"].get("/api/v1/appointments/").data["results"]} == {"Cust Omer"}
    assert eng["cash2"].get("/api/v1/appointments/").data["count"] == 0 and eng["admin_b"].get("/api/v1/appointments/").data["count"] == 0
    assert eng["tech"].get("/api/v1/appointments/").status_code == 403
    appt = r.data["id"]
    assert eng["cash2"].post(f"/api/v1/appointments/{appt}/status/", {"status": "confirmed"}, format="json").status_code == 404
    assert eng["cash"].post(f"/api/v1/appointments/{appt}/status/", {"status": "completed"}, format="json").status_code == 409  # must be confirmed first
    c = eng["cash"].post(f"/api/v1/appointments/{appt}/status/", {"status": "confirmed", "note": "See you"}, format="json")
    assert c.data["status"] == "confirmed" and any("confirmed" in m.subject for m in mail.outbox)
    assert eng["cash"].post(f"/api/v1/appointments/{appt}/status/", {"status": "completed"}, format="json").status_code == 409  # has not started
    assert b.post(f"/api/v1/shop/appointments/{appt}/cancel/").status_code == 404  # someone else's
    assert a.post(f"/api/v1/shop/appointments/{appt}/cancel/").data["status"] == "cancelled"
    assert b.post("/api/v1/shop/appointments/", body, format="json").status_code == 201  # the freed slot can be booked again
    Appointment.all_objects.filter(pk=appt)  # exists
    with tenant_context(eng["g"]):
        past = Appointment.objects.filter(status="requested").first()
        Appointment.objects.filter(pk=past.pk).update(status="confirmed", start_at=timezone.now() - timedelta(hours=2), end_at=timezone.now() - timedelta(hours=1))
    assert eng["cash"].post(f"/api/v1/appointments/{past.pk}/status/", {"status": "no_show"}, format="json").data["status"] == "no_show"
    assert {"appointment.requested", "appointment.confirmed", "appointment.no_show"} <= set(AuditLog.objects.values_list("action", flat=True))


# ---------------- inquiries and feedback ----------------
def test_inquiries_and_feedback(eng):
    stock(eng, eng["para"])
    a, b = customer(eng, "a@example.com"), customer(eng, "b@example.com")
    assert a.post("/api/v1/shop/inquiries/", {"kind": "availability", "message": "Do you have insulin?", "branch": eng["main"].pk}, format="json").status_code == 201
    assert a.post("/api/v1/shop/inquiries/", {"kind": "nonsense", "message": "x"}, format="json").status_code == 400
    assert a.post("/api/v1/shop/inquiries/", {"kind": "inquiry", "message": " "}, format="json").status_code == 400
    iid = eng["cash"].get("/api/v1/inquiries/").data["results"][0]["id"]
    assert eng["cash2"].post(f"/api/v1/inquiries/{iid}/respond/", {"response": "x"}, format="json").status_code == 404
    assert eng["cash"].post(f"/api/v1/inquiries/{iid}/respond/", {}, format="json").status_code == 400
    assert eng["cash"].post(f"/api/v1/inquiries/{iid}/respond/", {"response": "Yes, in stock."}, format="json").status_code == 200
    assert any(m.subject == "Reply to your enquiry" and m.to == ["a@example.com"] for m in mail.outbox)
    assert a.get("/api/v1/shop/inquiries/").data["results"][0]["response"] == "Yes, in stock." and b.get("/api/v1/shop/inquiries/").data["count"] == 0
    oid = place(a, order_body(eng)).data["id"]
    assert a.post("/api/v1/shop/feedback/", {"rating": 6}, format="json").status_code == 400
    assert a.post("/api/v1/shop/feedback/", {"rating": 5, "comment": "Great", "order": oid}, format="json").status_code == 201
    assert a.post("/api/v1/shop/feedback/", {"rating": 4, "order": oid}, format="json").status_code == 400  # one per order
    assert b.post("/api/v1/shop/feedback/", {"rating": 3, "order": oid}, format="json").status_code == 404  # not their order
    b.post("/api/v1/shop/feedback/", {"rating": 3, "comment": "OK"}, format="json")
    fb = eng["admin"].get("/api/v1/feedback/").data
    assert fb["count"] == 2 and fb["average_rating"] == 4.0
    assert eng["cash"].get("/api/v1/feedback/").data["count"] == 1  # branch staff see feedback tied to their branch
    fid = fb["results"][0]["id"]
    assert eng["admin"].post(f"/api/v1/feedback/{fid}/respond/", {"response": "Thank you!"}, format="json").status_code == 200
    assert eng["admin_b"].get("/api/v1/feedback/").data["count"] == 0 and a.get("/api/v1/feedback/").status_code == 403


# ---------------- institutional requests ----------------
def test_institutional_requests(eng):
    body = {"organisation": "City Hospital", "contact_person": "Dr Sesay", "email": "proc@hospital.example", "phone": "077", "service_required": "Bulk supply", "products_required": "Gloves, masks", "quantity": "5000", "requested_date": "2027-02-01"}
    c = api()
    r = c.post("/api/v1/public/pharmacies/greenlife/institutional-requests/", body, format="json")
    assert r.status_code == 201 and any(m.to == ["proc@hospital.example"] and "received your request" in m.body for m in mail.outbox)
    assert c.post("/api/v1/public/pharmacies/greenlife/institutional-requests/", {**body, "website": "spam"}, format="json").status_code == 201
    assert InstitutionalRequest.all_objects.count() == 1  # honeypot dropped
    assert c.post("/api/v1/public/pharmacies/greenlife/institutional-requests/", {**body, "email": "bad"}, format="json").status_code == 400
    assert c.post("/api/v1/public/pharmacies/nope/institutional-requests/", body, format="json").status_code == 404
    lst = eng["cash"].get("/api/v1/institutional-requests/").data["results"]
    assert len(lst) == 1 and lst[0]["organisation"] == "City Hospital"
    rid = lst[0]["id"]
    assert eng["cash"].post(f"/api/v1/institutional-requests/{rid}/respond/", {"status": "quoted"}, format="json").status_code == 400  # a quote needs content
    assert eng["cash"].post(f"/api/v1/institutional-requests/{rid}/respond/", {"status": "bogus"}, format="json").status_code == 400
    ok = eng["cash"].post(f"/api/v1/institutional-requests/{rid}/respond/", {"status": "quoted", "response": "Quotation: 5000 gloves at 0.10 each."}, format="json")
    assert ok.status_code == 200 and ok.data["status"] == "quoted"
    assert any(m.to == ["proc@hospital.example"] and "Quotation" in m.body for m in mail.outbox)
    assert eng["tech"].get("/api/v1/institutional-requests/").status_code == 403 and eng["admin_b"].get("/api/v1/institutional-requests/").data["count"] == 0
    assert customer(eng, "a@example.com").get("/api/v1/institutional-requests/").status_code == 403


# ---------------- delivery ----------------
def delivery_order(eng, cl):
    stock(eng, eng["para"])
    oid = place(cl, order_body(eng, fulfilment="delivery", payment_method="cash_on_delivery", delivery_address="12 Main St")).data["id"]
    for to in ("payment_confirmed", "processing", "preparing"):
        move(eng["cash"], oid, to)
    return oid


def test_delivery_assignment_and_driver_workflow(eng):
    cl = customer(eng)
    oid = delivery_order(eng, cl)
    pickup_oid = place(cl, order_body(eng)).data["id"]
    for to in ("payment_confirmed", "processing", "preparing"):
        move(eng["cash"], pickup_oid, to)
    assign = lambda c, order, driver: c.post("/api/v1/deliveries/", {"order": order, "driver": driver}, format="json")  # noqa: E731
    assert assign(eng["cash"], pickup_oid, eng["uid"]["drv"]).status_code == 409  # pickup orders are not delivered
    assert assign(eng["cash"], oid, eng["uid"]["drvb"]).status_code == 400  # driver belongs to another branch
    assert assign(eng["cash"], oid, eng["uid"]["drv"]).status_code == 201
    assert assign(eng["cash"], oid, eng["uid"]["drv"]).status_code == 201  # reassigning replaces the active one
    assert assign(eng["cash2"], oid, eng["uid"]["drv"]).status_code == 404 and assign(eng["tech"], oid, eng["uid"]["drv"]).status_code == 403
    assert [d["status"] for d in eng["cash"].get("/api/v1/deliveries/").data["results"]].count("assigned") == 1
    assert [d["name"] for d in eng["cash"].get("/api/v1/deliveries/drivers/").data] == ["DRV Driver", "DRV2 Driver"]
    mine = eng["drv"].get("/api/v1/deliveries/mine/").data
    assert len(mine) == 1 and mine[0]["address"] == "12 Main St" and mine[0]["collect"] == "22.00" and mine[0]["customer_phone"] == "077"
    did = mine[0]["id"]
    assert eng["drv2"].post(f"/api/v1/deliveries/{did}/pickup/").status_code == 404  # drivers only touch their own deliveries
    assert eng["drv"].post(f"/api/v1/deliveries/{did}/deliver/").status_code == 409  # pick up first
    assert eng["cash"].post(f"/api/v1/deliveries/{did}/pickup/").status_code == 403  # staff are not drivers
    assert eng["drv"].post(f"/api/v1/deliveries/{did}/pickup/").data["order_status"] == "out_for_delivery"
    assert cl.get(f"/api/v1/shop/orders/{oid}/delivery/").data == {"status": "picked_up", "driver_name": "DRV", "picked_up_at": cl.get(f"/api/v1/shop/orders/{oid}/delivery/").data["picked_up_at"], "finished_at": None}
    assert eng["drv"].post(f"/api/v1/deliveries/{did}/deliver/", {"note": "Left with neighbour"}, format="json").data["order_status"] == "delivered"
    assert cl.get(f"/api/v1/shop/orders/{oid}/").data["status"] == "delivered"
    assert eng["drv"].get("/api/v1/deliveries/mine/").data == []
    assert eng["drv"].get("/api/v1/orders/").status_code == 403 and eng["drv"].get("/api/v1/prescriptions/").status_code == 403  # drivers see nothing else
    assert {"delivery.assigned", "delivery.picked_up", "delivery.delivered"} <= set(AuditLog.objects.values_list("action", flat=True))


def test_failed_delivery_keeps_the_order_open_for_reassignment(eng):
    cl = customer(eng)
    oid = delivery_order(eng, cl)
    eng["cash"].post("/api/v1/deliveries/", {"order": oid, "driver": eng["uid"]["drv"]}, format="json")
    did = eng["drv"].get("/api/v1/deliveries/mine/").data[0]["id"]
    assert eng["drv"].post(f"/api/v1/deliveries/{did}/fail/", {}, format="json").status_code == 400
    assert eng["drv"].post(f"/api/v1/deliveries/{did}/fail/", {"reason": "Customer unreachable"}, format="json").data["status"] == "failed"
    assert eng["drv"].post(f"/api/v1/deliveries/{did}/fail/", {"reason": "again"}, format="json").status_code == 409
    assert cl.get(f"/api/v1/shop/orders/{oid}/").data["status"] == "preparing"
    assert eng["cash"].post("/api/v1/deliveries/", {"order": oid, "driver": eng["uid"]["drv2"]}, format="json").status_code == 201
    assert len(eng["drv2"].get("/api/v1/deliveries/mine/").data) == 1
    assert customer(eng, "other@example.com").get(f"/api/v1/shop/orders/{oid}/delivery/").status_code == 404
