import streamlit as st
import json
import pandas as pd
from datetime import datetime, timedelta, timezone
import random
import re
import math
from supabase import create_client, Client
import plotly.express as px
import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
import threading
import requests
import logging

import rbac
from supabase import create_client
from production import render_production_board
from dispatch import render_dispatch_module
from warehouse import render_warehouse_module
from messaging import send_departmental_alert

# ═══════════════════════════════════════════════════════════════════
# 0. LOGGING
# ═══════════════════════════════════════════════════════════════════
# Streamlit Cloud / most container platforms capture stdout, so a plain
# StreamHandler is enough to get these into whatever log viewer you deploy
# with. This replaces 30+ bare "except Exception: return <empty>" blocks
# that previously failed with zero trace — the app kept working (defaults
# kicked in) but nobody could see WHY a fetch or write failed until a user
# reported something wrong days later.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("appointed_time")

# ═══════════════════════════════════════════════════════════════════
# 1. PAGE CONFIGURATION
# ═══════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Appointed Time | Secured Enterprise Suite",
    layout="wide",
    page_icon="⚙️",
    initial_sidebar_state="expanded"
)

# ═══════════════════════════════════════════════════════════════════
# 2. SESSION STATE INITIALIZATION
# ═══════════════════════════════════════════════════════════════════
if "user_email" not in st.session_state:
    st.session_state.user_email = "Guest"
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "app_mode" not in st.session_state:
    st.session_state.app_mode = "Command Center"
if "last_raised_order" not in st.session_state:
    st.session_state.last_raised_order = None
if "user_profile" not in st.session_state:
    st.session_state.user_profile = None
if "resubmit_order_data" not in st.session_state:
    st.session_state.resubmit_order_data = None
# PRESS cart
if "cart_items" not in st.session_state:
    st.session_state.cart_items = []
if "cart_client_name" not in st.session_state:
    st.session_state.cart_client_name = ""
if "cart_client_phone" not in st.session_state:
    st.session_state.cart_client_phone = ""
if "last_raised_batch" not in st.session_state:
    st.session_state.last_raised_batch = []
if "editing_cart_idx" not in st.session_state:
    st.session_state.editing_cart_idx = None
# GARMENT cart
if "garment_cart_items" not in st.session_state:
    st.session_state.garment_cart_items = []
if "garment_cart_client_name" not in st.session_state:
    st.session_state.garment_cart_client_name = ""
if "garment_cart_client_phone" not in st.session_state:
    st.session_state.garment_cart_client_phone = ""
if "editing_garment_cart_idx" not in st.session_state:
    st.session_state.editing_garment_cart_idx = None
if "last_raised_garment_batch" not in st.session_state:
    st.session_state.last_raised_garment_batch = []

# Form-version counters — bump only on a SUCCESSFUL submission. Widget
# keys include this number, so incrementing it makes Streamlit render
# fresh (blank) widgets next rerun. Leaving it unchanged on a FAILED
# submission (missing required field, accidental early Enter) means the
# same widgets re-render with whatever the user already typed, instead
# of clear_on_submit=True wiping everything regardless of outcome.
if "press_item_form_v" not in st.session_state:
    st.session_state.press_item_form_v = 0
if "garment_item_form_v" not in st.session_state:
    st.session_state.garment_item_form_v = 0
if "press_resubmit_form_v" not in st.session_state:
    st.session_state.press_resubmit_form_v = 0
if "garment_resubmit_form_v" not in st.session_state:
    st.session_state.garment_resubmit_form_v = 0

# Authorization Center — pagination cursor
if "ac_page" not in st.session_state:
    st.session_state.ac_page = 0
# Session inactivity timer — used by 30-min auto-logout guard below
if "last_activity_ts" not in st.session_state:
    st.session_state.last_activity_ts = datetime.now()
# Global search state — drives the Search Results route
if "global_search_q" not in st.session_state:
    st.session_state.global_search_q = ""

# ═══════════════════════════════════════════════════════════════════
# 3. GLOBAL SETUP & MACHINE REGISTRY
# ═══════════════════════════════════════════════════════════════════
CURRENCY = "GH₵"

# Sales/marketing rep who brought the client in -- distinct from
# created_by (whoever at Front Desk typed the order in). Used to CC the
# rep at raise time so they see what was actually submitted against
# what they promised the client, before MD/FM even approves it.
# EDIT THIS with your real sales team's names and emails -- these three
# are placeholders and won't reach anyone until replaced.
SALES_REP_EMAILS = {
    "Mabel Ampofo":   "mabel.ampofo@appointedtime.com.gh",
    "Daphne Sarpong":   "d.sarpong@appointedtime.com.gh",
    "Reginald Aidam": "reginald.aidam@appointedtime.com.gh",
    "Charles Adoo": "charles.adoo@appointedtime.com.gh",
    "Isaac Kum": "isaac.kum@appointedtime.com.gh",
    "Bertha Tackie": "bertha.tackie@appointedtime.com.gh",
    "Christian Mante": "christian.mante@appointedtime.com.gh",
    "Jacqueline Afful": "jacqueline.afful@appointedtime.com.gh",
    "Mohammed Seidu Bunyamin": "m.seidu@appointedtime.com.gh",
}


SHIFT_START_HOUR = 8
SHIFT_END_HOUR = 17
DAILY_CAPACITY_HOURS = 8.0
MACHINE_DATA = {
    'SM102-CX FOUR COLOUR':         {'rate': 8000,  'setup_hours': 1.5},
    'SM102-P FIVE COLOUR':          {'rate': 7500,  'setup_hours': 1.5},
    'SM 52':                        {'rate': 7000,  'setup_hours': 1.5},
    'GTO 52 SEMI-AUTO-2 COLOUR':    {'rate': 4500,  'setup_hours': 1.5},
    'GTO 52 MANUAL-2 COLOUR':       {'rate': 4000,  'setup_hours': 2.0},
    'FOLDING UNIT CONTINUOUS FOLD': {'rate': 8000,  'setup_hours': 1.5},
    'MBO-B30E SINGLE FOLD':         {'rate': 16000, 'setup_hours': 1.5},
    'POLAR MACHINE FOR BOOKS':      {'rate': 2000,  'setup_hours': 1.0},
    'POLAR MACHINE FOR SHEETS':     {'rate': 50000, 'setup_hours': 1.0},
    '3 WAY TRIMMER':                {'rate': 5000,  'setup_hours': 1.0},
    'PERFECT BINDING':              {'rate': 500,   'setup_hours': 1.5},
    'LAMINATION UNIT':              {'rate': 2500,  'setup_hours': 1.5},
    'PEDDLER SADDLE STITCH':        {'rate': 1000,  'setup_hours': 1.5},
    'DIE CUTTER':                   {'rate': 3000,  'setup_hours': 1.5},
    'FOLDER GLUER':                 {'rate': 12000, 'setup_hours': 1.5},
    'CANON DIGITAL C10000':         {'rate': 6000,  'setup_hours': 0.5},
    'CANON DIGITAL C800':           {'rate': 4000,  'setup_hours': 0.5},
}

STAGE_DAYS_WARNING_THRESHOLD = 30  # working days (~6 calendar weeks) — see _estimate_working_days

# ── Overlap-scheduling rule ──────────────────────────────────────────
# A downstream stage doesn't need the upstream stage to be 100% finished —
# it needs enough of a head start that stock is actually ready. Both are
# measured from the upstream stage's START time, not its finish, so a
# large press run no longer holds up Die Cutter (and everything after it)
# for its own full multi-day duration. Same rule for every printing
# machine (any press → Die Cutter, Die Cutter → Folder Gluer): the
# downstream stage can begin the next calendar working day after the
# upstream stage started — see _next_working_day_start().

def _estimate_working_days(impressions, machine_name):
    """Rough pre-flight estimate only — NOT the real scheduler (that's
    calculate_production_time, which walks the calendar day by day and
    accounts for weekends/existing backlog). This exists purely to catch
    a fat-fingered quantity (an extra zero or two) at data-entry time,
    before it silently jams a machine's schedule for a year+."""
    mach = MACHINE_DATA.get(machine_name, {'rate': 1000})
    rate = mach.get('rate') or 1000
    hours_needed = impressions / rate
    return hours_needed / max(1, (SHIFT_END_HOUR - SHIFT_START_HOUR))

# ═══════════════════════════════════════════════════════════════════
# 4. ASYNCHRONOUS RESEND NOTIFICATION ENGINE
# ═══════════════════════════════════════════════════════════════════
def _send_resend_email(api_key, sender_email, recipients, subject, html_body, log_context):
    """
    Shared Resend HTTP call. Every notify_* function below builds its own
    content, then hands off here to actually send it.

    api_key / sender_email / recipients are read from st.secrets by the
    CALLER on the main thread and passed in as plain values — the worker
    thread itself makes zero Streamlit API calls. st.secrets happens to
    work from a background thread today, but Streamlit doesn't document
    that as supported, so removing the dependency is cheap insurance
    against a future Streamlit upgrade changing that. requests.post and
    the logging module are both fine to call from any thread.

    Failures are logged instead of silently discarded: previously a Resend
    outage or bad API key meant a manager just never got an email, with no
    record anywhere that it was supposed to send.
    """
    def worker():
        if not api_key or not recipients:
            logger.warning(
                "Resend email skipped (%s): api_key set=%s, recipients=%r",
                log_context, bool(api_key), recipients,
            )
            return
        try:
            _resp = requests.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"from": f"Appointed Time Hub <{sender_email}>",
                      "to": recipients, "subject": subject, "html": html_body},
                timeout=10,
            )
            if _resp.status_code >= 400:
                logger.error(
                    "Resend rejected email (%s): status=%s body=%s subject=%r",
                    log_context, _resp.status_code, _resp.text[:500], subject,
                )
        except Exception:
            logger.exception("Resend email failed (%s): subject=%r", log_context, subject)
    threading.Thread(target=worker, daemon=True).start()


def _email_shell(accent_bg, heading, subheading, intro, rows, footer, accent_fg="#ffffff"):
    """
    One shared HTML letterhead for every outbound notification, replacing
    four copy-pasted templates that had already drifted apart (some used
    raw emoji in headings, others used HTML entities for the same glyph —
    harmless today, but exactly the kind of inconsistency that compounds
    as more notification types get added). Change the letterhead once,
    every email type picks it up.
    `rows` is a list of (label, value, value_color_or_None) tuples.
    """
    row_html = "".join(
        f'<tr style="background:{"#f8fafc" if i % 2 == 0 else "#ffffff"};">'
        f'<td style="padding:9px 10px;font-weight:600;color:#64748b;'
        f'border-bottom:1px solid #e2e8f0;">{label}</td>'
        f'<td style="padding:9px 10px;font-weight:700;border-bottom:1px solid #e2e8f0;'
        f'color:{color or "#0f172a"};">{value}</td></tr>'
        for i, (label, value, color) in enumerate(rows)
    )
    return f"""<div style="font-family:'Segoe UI',Tahoma,sans-serif;color:#0f172a;max-width:600px;
        margin:0 auto;border:1px solid #e2e8f0;border-radius:12px;overflow:hidden;">
      <div style="background:{accent_bg};color:{accent_fg};padding:24px;text-align:center;">
        <h2 style="margin:0;font-size:19px;letter-spacing:0.03em;">{heading}</h2>
        <p style="margin:4px 0 0 0;color:#cbd5e1;font-size:13px;">{subheading}</p>
      </div>
      <div style="padding:24px;background:#ffffff;">
        <p style="font-size:15px;">{intro}</p>
        <table style="width:100%;border-collapse:collapse;margin:18px 0;font-size:14px;">
          {row_html}
        </table>
        <p style="font-size:13px;color:#64748b;text-align:center;">{footer}</p>
      </div>
    </div>"""


def _approval_recipients():
    """
    Recipients for new-order-submitted alerts, configurable via the
    APPROVAL_NOTIFY_EMAILS secret (comma-separated) so a staffing change is
    a secrets update, not a code deploy. Falls back to MD/FM's real
    addresses (not a placeholder) if that secret is ever unset, so a
    dropped secret still lands somewhere real instead of a dead inbox.
    """
    raw = st.secrets.get("APPROVAL_NOTIFY_EMAILS", "")
    emails = [e.strip() for e in raw.split(",") if e.strip()]
    return emails or ["jacqueline.afful@appointedtime.com.gh", "emmanuel.ametepe@appointedtime.com.gh", "enoch.obeng@appointedtime.com.gh"]


def _scheduler_recipients():
    """
    The Planner/scheduler is a distinct role from MD/FM approval —
    separate secret so it can be reassigned to a different person without
    touching who approves orders. Falls back to the real current
    scheduler's address, not a placeholder.
    """
    raw = st.secrets.get("SCHEDULER_NOTIFY_EMAILS", "")
    emails = [e.strip() for e in raw.split(",") if e.strip()]
    return emails or ["s.mensah@appointedtime.com.gh"]


def _collection_alert_recipients():
    """
    Comma-separated per slot, same convention as _approval_recipients —
    NOTIFY_EMAIL_1 and NOTIFY_EMAIL_2 each split into as many addresses as
    listed, rather than being treated as exactly two single addresses.
    Falls back to MD/FM's real addresses if both secrets are ever unset.
    """
    raw = ",".join(filter(None, [
        st.secrets.get("NOTIFY_EMAIL_1", ""),
        st.secrets.get("NOTIFY_EMAIL_2", ""),
    ]))
    emails = [e.strip() for e in raw.split(",") if e.strip()]
    return emails or ["jacqueline.afful@appointedtime.com.gh", "emmanuel.ametepe@appointedtime.com.gh"]


def send_resend_notification(payload):
    """Notify management that a new order needs authorization sign-off.
    Also CCs the sales/marketing rep who brought the job, if one was
    selected -- so they see what was actually submitted against what
    they told the client, before it's even approved."""
    api_key      = st.secrets.get("RESEND_API_KEY")
    sender_email = st.secrets.get("RESEND_SENDER_EMAIL", "onboarding@resend.dev")
    dept_label   = payload.get('department', 'PRESS')
    _rows = [
        ("Job Order No:",   str(payload.get('job_order_no', 'PENDING')), "#0369a1"),
        ("Customer:",       str(payload.get('customer_name', '—')),      None),
        ("Contract Value:", f"{CURRENCY} {float(payload.get('total_amount', 0) or 0):,.2f}", None),
        ("Sales Rep:",      str(payload.get('sales_rep') or '—'),        None),
    ]
    _lpo_url = payload.get('lpo_file_url')
    if _lpo_url:
        _rows.append(("LPO:", f'<a href="{_lpo_url}">Open LPO</a>', None))
    html = _email_shell(
        accent_bg="#0f172a",
        heading="EXECUTIVE APPROVAL REQUIRED",
        subheading=f"Appointed Time Printing Enterprise Hub &mdash; {dept_label} DEPT",
        intro="A new order requires authorization sign-off.",
        rows=_rows,
        footer="Access Authorization Center to proceed.",
    )
    _recipients = list(_approval_recipients())
    _rep_name = payload.get('sales_rep')
    _rep_email = SALES_REP_EMAILS.get(_rep_name) if _rep_name else None
    if _rep_email and _rep_email.lower() not in [r.lower() for r in _recipients]:
        _recipients.append(_rep_email)
    _send_resend_email(
        api_key, sender_email, _recipients,
        subject=f"Executive Action: Order {payload.get('job_order_no','PENDING')} Submitted",
        html_body=html, log_context="new-order-submitted",
    )


def _approval_cc_recipients():
    """Finance and Warehouse get a copy of every approval, so they see
    what's coming before it reaches their own stage. Falls back to the
    real current Finance/Warehouse addresses, not a placeholder."""
    raw = st.secrets.get("APPROVAL_CC_EMAILS", "")
    emails = [e.strip() for e in raw.split(",") if e.strip()]
    return emails or ["celestina.foli@appointedtime.com.gh", "appointedtime.supplychain@gmail.com"]


def notify_order_approved(order_data: dict) -> None:
    """Email the order creator when management approves their order.
    Finance and Warehouse are CC'd on every approval (see
    _approval_cc_recipients), and the sales rep (if one was selected at
    raise time) is CC'd too — they were only told the order was
    *submitted* before; this is the "it actually went through" email."""
    d = order_data
    recipient = str(d.get("created_by", "") or "")
    if "@" not in recipient:
        return
    api_key      = st.secrets.get("RESEND_API_KEY", "")
    sender_email = st.secrets.get("RESEND_SENDER_EMAIL", "onboarding@resend.dev")
    _rep_name  = d.get('sales_rep')
    _rep_email = SALES_REP_EMAILS.get(_rep_name) if _rep_name else None
    html = _email_shell(
        accent_bg="#064e3b",
        heading="✅ ORDER APPROVED",
        subheading=f"Appointed Time Printing &mdash; {d.get('department','PRESS')} Dept",
        intro="Your order has been <strong>approved</strong> and is now active in the production pipeline.",
        rows=[
            ("Order No",       str(d.get('job_order_no', '—')), "#0369a1"),
            ("Customer",       str(d.get('customer_name', '—')), None),
            ("Contract Value", f"{CURRENCY} {float(d.get('total_amount',0) or 0):,.2f}", None),
            ("Sales Rep",      str(_rep_name or '—'), None),
        ],
        footer=f"Approved by: {d.get('approved_by','Management')} &middot; Date: {d.get('approval_date','')}",
    )
    _recipients = [recipient] + [e for e in _approval_cc_recipients() if e.lower() != recipient.lower()]
    if _rep_email and _rep_email.lower() not in [r.lower() for r in _recipients]:
        _recipients.append(_rep_email)
    _send_resend_email(
        api_key, sender_email, _recipients,
        subject=f"Approved: Order {d.get('job_order_no','—')} is live",
        html_body=html, log_context="order-approved",
    )


def notify_order_rejected(order_data: dict) -> None:
    """Email the order creator when management returns/rejects their order."""
    d = order_data
    recipient = str(d.get("created_by", "") or "")
    if "@" not in recipient:
        return
    api_key      = st.secrets.get("RESEND_API_KEY", "")
    sender_email = st.secrets.get("RESEND_SENDER_EMAIL", "onboarding@resend.dev")
    html = _email_shell(
        accent_bg="#7f1d1d",
        heading="⚠️ ORDER RETURNED FOR REVISION",
        subheading="Action Required",
        intro="Your order has been <strong>returned</strong> by management. "
              "Log in, review the note below, correct, and resubmit.",
        rows=[
            ("Order No",        str(d.get('job_order_no', '—')), "#b91c1c"),
            ("Customer",        str(d.get('customer_name', '—')), None),
            ("Management Note", str(d.get('rejection_note', 'See system for details')), "#b91c1c"),
        ],
        footer="Use Modify & Resubmit in My Order Tracker.",
    )
    _send_resend_email(
        api_key, sender_email, [recipient],
        subject=f"Action Required: Order {d.get('job_order_no','—')} returned",
        html_body=html, log_context="order-rejected",
    )


def notify_needs_scheduling(order_data: dict) -> None:
    """Goes to the actual scheduler (s.mensah), not the MD/FM approval
    list — scheduling and approval are different people doing different
    jobs, even though both alerts fire off the same approval event."""
    d = order_data
    api_key      = st.secrets.get("RESEND_API_KEY", "")
    sender_email = st.secrets.get("RESEND_SENDER_EMAIL", "onboarding@resend.dev")
    html = _email_shell(
        accent_bg="#1e3a8a",
        heading="📋 READY TO SCHEDULE",
        subheading=f"Appointed Time Printing &mdash; {d.get('department','PRESS')} Dept",
        intro="This order is approved and waiting in Production Layout Builder.",
        rows=[
            ("Order No",       str(d.get('job_order_no', '—')), "#0369a1"),
            ("Customer",       str(d.get('customer_name', '—')), None),
            ("Contract Value", f"{CURRENCY} {float(d.get('total_amount',0) or 0):,.2f}", None),
        ],
        footer="Schedule it in Production Layout Builder.",
    )
    _send_resend_email(
        api_key, sender_email, _scheduler_recipients(),
        subject=f"Ready to Schedule: Order {d.get('job_order_no','—')}",
        html_body=html, log_context="needs-scheduling",
    )


def _warehouse_recipients():
    """Falls back to the real warehouse address, not a placeholder, if
    WAREHOUSE_NOTIFY_EMAILS is ever unset."""
    raw = st.secrets.get("WAREHOUSE_NOTIFY_EMAILS", "")
    return [e.strip() for e in raw.split(",") if e.strip()] or ["appointedtime.supplychain@gmail.com"]


def notify_sent_to_warehouse(order_data: dict) -> None:
    d = order_data
    api_key      = st.secrets.get("RESEND_API_KEY", "")
    sender_email = st.secrets.get("RESEND_SENDER_EMAIL", "onboarding@resend.dev")
    html = _email_shell(
        accent_bg="#4f46e5",
        heading="📥 ORDER SENT TO WAREHOUSE",
        subheading="Appointed Time Printing &mdash; Warehouse Receiving",
        intro="Production has completed this order and marked it ready for pickup at the warehouse.",
        rows=[
            ("Order No", str(d.get('job_order_no', '—')), "#4338ca"),
            ("Customer", str(d.get('customer_name', '—')), None),
        ],
        footer="Confirm receipt in the Warehouse module.",
    )
    _send_resend_email(
        api_key, sender_email, _warehouse_recipients(),
        subject=f"Warehouse: Order {d.get('job_order_no','—')} arrived",
        html_body=html, log_context="sent-to-warehouse",
    )


def _finance_recipients():
    """Falls back to the real finance address, not a placeholder, if
    FINANCE_NOTIFY_EMAILS is ever unset."""
    raw = st.secrets.get("FINANCE_NOTIFY_EMAILS", "")
    return [e.strip() for e in raw.split(",") if e.strip()] or ["celestina.foli@appointedtime.com.gh"]


def notify_ready_for_finance(order_data: dict) -> bool:
    """Warehouse's one action. Also flips warehouse_notified_finance so the
    Warehouse module doesn't re-send this every time someone revisits."""
    d = order_data
    api_key      = st.secrets.get("RESEND_API_KEY", "")
    sender_email = st.secrets.get("RESEND_SENDER_EMAIL", "onboarding@resend.dev")
    html = _email_shell(
        accent_bg="#065f46",
        heading="📦 READY FOR DISPATCH",
        subheading="Appointed Time Printing &mdash; Finance",
        intro="Warehouse has prepared this order for delivery. Collect any outstanding balance and finalize dispatch.",
        rows=[
            ("Order No", str(d.get('job_order_no', '—')), "#065f46"),
            ("Customer", str(d.get('customer_name', '—')), None),
        ],
        footer="Finalize in the Dispatch module.",
    )
    try:
        _send_resend_email(
            api_key, sender_email, _finance_recipients(),
            subject=f"Ready for Dispatch: Order {d.get('job_order_no','—')}",
            html_body=html, log_context="ready-for-finance",
        )
        if d.get('id'):
            supabase.table('job_orders').update({"warehouse_notified_finance": True}).eq('id', d['id']).execute()
        return True
    except Exception:
        logger.exception("notify_ready_for_finance failed for order id=%s.", d.get('id'))
        return False


def notify_collection_due(order_data: dict, days_remaining: int) -> None:
    """Alert management when an order collection date is approaching or overdue."""
    d, days = order_data, days_remaining
    api_key      = st.secrets.get("RESEND_API_KEY", "")
    sender_email = st.secrets.get("RESEND_SENDER_EMAIL", "onboarding@resend.dev")
    _uc  = "#b91c1c" if days <= 0 else ("#d97706" if days <= 2 else "#0369a1")
    _ul  = "OVERDUE" if days <= 0 else f"DUE IN {days} DAY(S)"
    _bal = max(0.0, float(d.get('total_amount', 0) or 0) - float(d.get('deposit_amount', 0) or 0))
    html = _email_shell(
        accent_bg=_uc,
        heading=f"📦 COLLECTION ALERT &mdash; {_ul}",
        subheading="",
        intro="",
        rows=[
            ("Order No",         str(d.get('job_order_no', '—')), _uc),
            ("Customer",         str(d.get('customer_name', '—')), None),
            ("Collection Date",  str(d.get('date_of_collection', '—')), _uc),
            ("Balance Due",      f"{CURRENCY} {_bal:,.2f}", None),
        ],
        footer="",
    )
    _send_resend_email(
        api_key, sender_email, _collection_alert_recipients(),
        subject=f"Collection {_ul}: {d.get('customer_name','—')} — {d.get('job_order_no','—')}",
        html_body=html, log_context="collection-due",
    )


# ═══════════════════════════════════════════════════════════════════
# 5. PREMIUM CSS TYPOGRAPHY & STYLING
# ═══════════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

/* ── Design tokens ────────────────────────────────────────────────────
   Centralizing the values that were previously repeated as raw hex
   dozens of times across this stylesheet. Scope: this converts the
   ~20 classes defined in THIS block to reference tokens — it does not
   reach the ~130 one-off unsafe_allow_html inline styles scattered
   through route bodies elsewhere in the file (flagged separately as
   follow-up work; that's a larger, riskier refactor than one CSS pass
   should attempt blind). Still a real win where it applies: change the
   brand navy once, here, instead of hunting N call sites. */
:root {
    --at-navy: #0f172a; --at-navy-soft: #1e293b; --at-slate: #64748b;
    --at-slate-light: #94a3b8; --at-border: #e2e8f0; --at-bg: #f8fafc;
    --at-white: #ffffff; --at-accent: #0369a1;
    --at-success: #10b981; --at-success-bg: #d1fae5; --at-success-text: #065f46;
    --at-warning: #f59e0b; --at-danger: #ef4444; --at-danger-soft: #fca5a5;
    --at-radius-sm: 6px; --at-radius: 10px; --at-radius-lg: 12px;
    --at-shadow-sm: 0 4px 6px -1px rgba(15,23,42,0.04);
    --at-shadow-md: 0 8px 15px -3px rgba(15,23,42,0.08);
}

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    background-color: var(--at-bg); color: var(--at-navy);
}
/* Executive-grade body copy: the signature "premium SaaS" typographic
   move is contrast between TIGHT headings (existing negative
   letter-spacing below) and LOOSE, readable body text — Streamlit's
   markdown default line-height is tighter than that. [Likely — this
   testid has been stable across recent Streamlit versions but isn't
   something I can verify without a live instance running this exact
   version; if a future Streamlit upgrade renames it, this rule simply
   stops matching rather than breaking anything.] */
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li { line-height: 1.65; color: var(--at-navy-soft); }

button:focus-visible, input:focus-visible,
textarea:focus-visible, select:focus-visible {
    outline: 2px solid var(--at-accent); outline-offset: 2px;
}

.main-title { font-size: 2.25rem; font-weight: 800; color: var(--at-navy); margin-bottom: 0.25rem; letter-spacing: -0.03em; }
.main-subtitle { font-size: 1.1rem; color: var(--at-slate); margin-bottom: 2rem; font-weight: 500; }
.section-header { font-size: 1.5rem; font-weight: 700; color: var(--at-navy-soft); margin-bottom: 1.5rem; padding-bottom: 0.5rem; border-bottom: 2px solid var(--at-border); letter-spacing: -0.01em; }
.form-group-header { font-size: 1rem; font-weight: 600; color: var(--at-accent); margin-top: 1rem; margin-bottom: 0.5rem; text-transform: uppercase; letter-spacing: 0.05em; }
.metric-card { background: var(--at-white); border-radius: var(--at-radius-lg); border: 1px solid var(--at-border); box-shadow: var(--at-shadow-sm); padding: 1.5rem; border-bottom: 4px solid var(--at-navy); transition: transform 0.2s ease, box-shadow 0.2s ease; }
.metric-card:hover { transform: translateY(-2px); box-shadow: var(--at-shadow-md); }
.metric-label { font-size: 0.8rem; color: var(--at-slate); text-transform: uppercase; font-weight: 700; letter-spacing: 0.05em; }
.metric-value { font-size: 2rem; font-weight: 800; color: var(--at-navy); margin-top: 0.5rem; letter-spacing: -0.02em; }
.waybill-card { background: var(--at-white); border: 1px solid var(--at-border); border-radius: var(--at-radius-lg); padding: 2rem; margin-bottom: 1.5rem; box-shadow: var(--at-shadow-sm); }
.tag-chip { display: inline-block; background-color: #f1f5f9; color: #475569; font-size: 0.75rem; font-weight: 600; padding: 0.25rem 0.6rem; border-radius: 9999px; margin: 0.15rem; border: 1px solid var(--at-border); }
.tag-chip-active { display: inline-block; background-color: var(--at-navy); color: var(--at-white); font-size: 0.75rem; font-weight: 600; padding: 0.25rem 0.6rem; border-radius: 9999px; margin: 0.15rem; }
.sf-machine-card { background: var(--at-white); border-radius: var(--at-radius-lg); border: 1px solid var(--at-border); padding: 1.5rem; margin-bottom: 1.2rem; box-shadow: var(--at-shadow-sm); transition: box-shadow 0.2s ease; }
.sf-machine-card:hover { box-shadow: var(--at-shadow-md); }
.sf-status-badge { display: inline-flex; align-items: center; gap: 0.35rem; font-size: 0.75rem; font-weight: 700; padding: 0.3rem 0.75rem; border-radius: 9999px; text-transform: uppercase; letter-spacing: 0.04em; }
.sf-badge-active  { background-color: var(--at-success-bg); color: var(--at-success-text); }
.sf-badge-idle    { background-color: #f1f5f9; color: #475569; }
.sf-badge-queued  { background-color: #fef7e0; color: #b06000; }
.sf-machine-name  { font-size: 1.35rem; font-weight: 800; color: var(--at-navy); margin: 0.6rem 0 0.15rem 0; letter-spacing: -0.01em; }
.sf-progress-label { display: flex; justify-content: space-between; font-size: 0.8rem; font-weight: 700; color: #475569; margin-bottom: 0.4rem; text-transform: uppercase; letter-spacing: 0.03em; }
.sf-progress-track { background-color: #f1f5f9; height: 10px; border-radius: 9999px; overflow: hidden; border: 1px solid var(--at-border); }
[data-testid="stSidebar"] { background-color: var(--at-white); border-right: 1px solid var(--at-border); }
.sidebar-section-header { font-size: 0.75rem; font-weight: 700; color: var(--at-slate); margin-top: 2rem; margin-bottom: 0.75rem; text-transform: uppercase; letter-spacing: 0.08em; padding-left: 0.5rem; }
[data-testid="stSidebar"] [data-testid="stButton"] button { width: 100%; justify-content: flex-start; text-align: left; border: none; background-color: transparent; color: #475569; font-weight: 600; padding: 0.75rem 1rem; border-radius: 8px; transition: all 0.2s ease; }
[data-testid="stSidebar"] [data-testid="stButton"] button:hover { background-color: #f1f5f9; color: var(--at-navy); transform: translateX(4px); }
[data-testid="stSidebar"] [data-testid="stButton"] button[kind="primary"] { background-color: var(--at-danger); color: var(--at-white); justify-content: center; margin-top: 2rem; }
[data-testid="stSidebar"] [data-testid="stButton"] button[kind="primary"]:hover { background-color: #dc2626; transform: none; }
.fd-rejected-card { background: linear-gradient(135deg, #fff5f5 0%, #fff1f2 100%); border: 2px solid var(--at-danger-soft); border-left: 6px solid var(--at-danger); border-radius: var(--at-radius-lg); padding: 1.5rem 1.75rem; margin-bottom: 1.25rem; box-shadow: 0 4px 12px -2px rgba(239,68,68,0.12); }
.fd-pending-row { background: var(--at-white); border: 1px solid var(--at-border); border-left: 5px solid var(--at-warning); border-radius: var(--at-radius); padding: 1.1rem 1.5rem; margin-bottom: 0.85rem; display: flex; align-items: center; justify-content: space-between; box-shadow: var(--at-shadow-sm); }
.fd-approved-card { background: var(--at-white); border: 1px solid var(--at-border); border-left: 6px solid var(--at-success); border-radius: var(--at-radius-lg); padding: 1.5rem 1.75rem; margin-bottom: 1.25rem; box-shadow: 0 4px 10px -2px rgba(16,185,129,0.08); }
.fd-rejection-note-box { background: linear-gradient(135deg, #fef2f2 0%, #fce7e7 100%); border: 1px solid var(--at-danger-soft); border-radius: 8px; padding: 0.85rem 1.1rem; margin-top: 0.85rem; margin-bottom: 0.5rem; }
.fd-pipeline-progress-track { background-color: var(--at-success-bg); height: 8px; border-radius: 9999px; overflow: hidden; border: 1px solid #a7f3d0; margin-top: 0.5rem; }
.sidebar-active-nav { display:block; background-color:var(--at-navy) !important; color:var(--at-white) !important; font-weight:700; padding:0.75rem 1rem; border-radius:8px; margin-bottom:2px; font-size:0.875rem; letter-spacing:0.01em; cursor:default; line-height:1.4; }
.sidebar-pending-badge { display:inline-flex; align-items:center; justify-content:center; background:var(--at-danger); color:var(--at-white); font-size:0.65rem; font-weight:800; min-width:1.25rem; height:1.25rem; padding:0 0.35rem; border-radius:9999px; margin-left:0.45rem; vertical-align:middle; line-height:1; }
.ot-search-bar { background:var(--at-bg); border:1px solid var(--at-border); border-radius:10px; padding:0.85rem 1.1rem; margin-bottom:1rem; }
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════
# 6. SUPABASE BACKEND & DATABASE LAYER
# ═══════════════════════════════════════════════════════════════════
@st.cache_resource
def init_supabase():
    try:
        _supabase_secrets = st.secrets.get("supabase", {})
        url = _supabase_secrets.get("url")
        key = _supabase_secrets.get("anon_key")
        if not url or not key:
            logger.error("Supabase not initialized: [supabase].url/anon_key missing from st.secrets.")
            return None
        return create_client(url, key)
    except Exception:
        logger.exception("Supabase client initialization failed.")
        return None

supabase: Client = init_supabase()

def checkbox_multiselect(label, options, key_prefix, default=None, columns=4):
    """
    Click-only replacement for st.multiselect. Streamlit's multiselect has
    a built-in searchable text cursor and lets Backspace silently delete
    the last-selected chip — confusing for anyone expecting a plain
    dropdown, and genuinely easy to lose a selection by accident. This
    renders one checkbox per option across `columns` columns instead —
    nothing to type into, nothing removable except by unchecking it.
    Returns the list of currently-checked option labels, in the same
    order `options` was given.
    """
    default = set(default or [])
    if label:
        st.markdown(
            f'<div style="font-size:0.8rem;font-weight:600;color:#334155;margin-bottom:0.25rem;">{label}</div>',
            unsafe_allow_html=True)
    if not options:
        return []
    cols = st.columns(min(columns, len(options)))
    checked = []
    for i, opt in enumerate(options):
        with cols[i % len(cols)]:
            if st.checkbox(opt, value=opt in default, key=f"{key_prefix}_{opt}"):
                checked.append(opt)
    return checked

def sanitize_string(input_str):
    """
    Defense-in-depth for the 130+ unsafe_allow_html=True blocks that render
    this data back to the screen. Strips ONLY the characters that can break
    out of an HTML tag/attribute (< > " and backtick) instead of the old
    allowlist ([^\\w\\s-().,/]) that silently mutilated real business names
    on write — "O'Brien" became "OBrien", "Mensah & Sons" became "Mensah
    Sons". That old behavior was a data-quality bug wearing a security
    costume: apostrophes and ampersands were never the injection risk, so
    stripping them bought no safety and cost real customer data.
    The textbook-correct fix is to store input verbatim and HTML-escape at
    render time (Python's html.escape) instead of sanitizing at write time;
    that touches every unsafe_allow_html call site, so it's flagged as
    follow-up work rather than done blind in this pass.
    """
    return re.sub(r'[<>`"]', '', str(input_str or '')).strip()

def _is_garment(row):
    """Central helper – returns True when a DB row is a GARMENT department order."""
    dept = str(row.get('department') or '').strip().upper()
    if dept == 'GARMENT':
        return True
    # Fallback: check print_type for garment-specific values
    pt = str(row.get('type_of_print') or row.get('print_type') or '').strip().upper()
    return pt in ('DTF', 'UV-DTF', 'SAV', 'EMBROIDERY', 'FLEXI SCREEN PRINT')

JOBS_RECENT_WINDOW_HOURS = 72  # see get_db_jobs docstring for why this is safe, not arbitrary

def get_db_jobs():
    """
    Server-side filtered fetch of the `jobs` (machine-scheduling) table:
    only jobs finishing within the last JOBS_RECENT_WINDOW_HOURS, plus any
    future-dated ones, plus defensively any row with a null finish_time.

    Last pass I deliberately left this unbounded rather than bolt on a
    blind .limit() (truncating active floor data is worse than a slow
    query). This is a different, narrower claim — a *time-scoped* filter,
    not a row-count cap — and it's provably safe for every current
    consumer, not just probably fine:

      • get_machine_next_available_time() only ever reads
        m_df['finish_time'].max() for one machine. A row outside this
        window can mathematically never win that max() against any
        in-window row, and a machine with zero in-window rows already
        falls through to "available now" (apply_calendar_bounds on the
        requested start) — so narrowing the window cannot change what
        that function returns, for any machine that currently has work.
      • Shop Floor Control's "Completed Runs" expander (search
        `completed_jobs.sort_values`) was separately rendering EVERY
        completed job for a machine's entire history with no bound of
        its own — a live status board showing jobs finished 8 months ago
        was never useful there anyway; that history already lives in the
        Approved Orders Archive. This filter fixes that unbounded-render
        problem as a side effect, not just the fetch.

    finish_time is written as a NAIVE isoformat string (see
    add_multi_part_job → calculate_production_time → apply_calendar_bounds,
    which strips tzinfo before .isoformat()), so the cutoff below
    deliberately uses naive datetime.now() to match — using an
    timezone-aware cutoff here would silently mismatch against the stored
    format. That naive/aware split is itself a pre-existing inconsistency
    in this codebase (order lifecycle timestamps elsewhere use
    datetime.now(timezone.utc)) worth a dedicated cleanup pass on its own;
    this function matches what's actually on disk rather than papering
    over it.
    """
    if not supabase or not st.session_state.get("authenticated"):
        return pd.DataFrame()
    try:
        cutoff = (datetime.now() - timedelta(hours=JOBS_RECENT_WINDOW_HOURS)).isoformat()
        res = (
            supabase.table('jobs')
            .select("*")
            .or_(f"finish_time.gte.{cutoff},finish_time.is.null")
            .execute()
        )
        return pd.DataFrame(res.data)
    except Exception:
        logger.exception("get_db_jobs: fetch from 'jobs' failed.")
        return pd.DataFrame()

def get_shop_floor_timeline():
    """jobs rows enriched with customer_name/status from their parent
    job_orders row where job_order_no links them. Falls back to a
    'legacy' label for rows scheduled before that column existed."""
    floor_df = get_db_jobs()
    if floor_df.empty:
        return floor_df
    floor_df['start_time']  = pd.to_datetime(floor_df['start_time'],  utc=True, format='mixed', errors='coerce')
    floor_df['finish_time'] = pd.to_datetime(floor_df['finish_time'], utc=True, format='mixed', errors='coerce')

    _order_nos = floor_df.get('job_order_no', pd.Series(dtype=str)).dropna().unique().tolist()
    _ord_df = pd.DataFrame()
    if _order_nos:
        try:
            _res = (supabase.table('job_orders')
                    .select('job_order_no,customer_name,status')
                    .in_('job_order_no', _order_nos).execute())
            _ord_df = pd.DataFrame(_res.data)
        except Exception:
            logger.exception("get_shop_floor_timeline: job_orders join failed.")

    if not _ord_df.empty:
        floor_df = floor_df.merge(_ord_df, on='job_order_no', how='left')
    else:
        floor_df['customer_name'] = None
        floor_df['status'] = None

    floor_df['client_label'] = floor_df.apply(
        lambda r: f"{r.get('job_order_no')} — {r['customer_name']}"
                  if pd.notna(r.get('customer_name'))
                  else f"{r.get('job_name','—')} (legacy)",
        axis=1
    )
    floor_df['effective_finish'] = pd.to_datetime(
        floor_df.get('revised_finish'), utc=True, errors='coerce'
    ).fillna(floor_df['finish_time'])
    return floor_df

def get_job_pipeline_status(active_only=True):
    """Reads job_pipeline_status (the DB view) and attaches customer_name.
    The view itself stays a pure aggregate over jobs on purpose — it never
    needs job_orders' schema to change to stay correct."""
    if not supabase:
        return pd.DataFrame()
    try:
        _pipe_df = pd.DataFrame(supabase.table('job_pipeline_status').select("*").execute().data)
    except Exception:
        logger.exception("get_job_pipeline_status failed.")
        return pd.DataFrame()
    if _pipe_df.empty:
        return _pipe_df
    if active_only:
        _pipe_df = _pipe_df[_pipe_df['stages_complete'] < _pipe_df['stage_count']]
    if _pipe_df.empty:
        return _pipe_df
    try:
        _ord_df = pd.DataFrame(
            supabase.table('job_orders').select('job_order_no,customer_name')
            .in_('job_order_no', _pipe_df['job_order_no'].tolist()).execute().data
        )
    except Exception:
        _ord_df = pd.DataFrame()
    _pipe_df = _pipe_df.merge(_ord_df, on='job_order_no', how='left') if not _ord_df.empty else _pipe_df.assign(customer_name=None)
    _pipe_df['scheduled_start']      = pd.to_datetime(_pipe_df['scheduled_start'], utc=True, errors='coerce')
    _pipe_df['projected_completion'] = pd.to_datetime(_pipe_df['projected_completion'], utc=True, errors='coerce')
    _pipe_df['label'] = _pipe_df.apply(
        lambda r: f"{r['job_order_no']} — {r['customer_name']}" if pd.notna(r.get('customer_name'))
                  else str(r['job_order_no']), axis=1)
    return _pipe_df

def get_db_job_orders(status_filter=None):
    if not supabase or not st.session_state.get("authenticated"):
        return pd.DataFrame()
    try:
        query = supabase.table('job_orders').select("*")
        if status_filter:
            query = query.eq('status', status_filter)
        res = query.execute()
        return pd.DataFrame(res.data)
    except Exception:
        logger.exception("get_db_job_orders(status_filter=%r) failed.", status_filter)
        return pd.DataFrame()

def get_db_job_orders_multi_status(status_list):
    if not supabase or not st.session_state.get("authenticated"):
        return pd.DataFrame()
    try:
        res = supabase.table('job_orders').select("*").in_('status', status_list).execute()
        return pd.DataFrame(res.data)
    except Exception:
        logger.exception("get_db_job_orders_multi_status(%r) failed.", status_list)
        return pd.DataFrame()


@st.cache_data(ttl=20)
def fetch_pending_orders_cached() -> pd.DataFrame:
    """
    Performance-cached fetch for the Authorization Center only.

    TTL  : 20 seconds — stale data is auto-evicted.
    Write: call fetch_pending_orders_cached.clear() immediately after any
           Approve / Reject / Update so the next rerun sees fresh data
           without waiting for the TTL to expire.

    Contract: this function is intentionally session-state-blind.
    Check authentication in the caller before invoking.

    Deliberately NOT capped with .limit(): every row here is something a
    manager still needs to act on. Truncating this list doesn't reduce the
    real queue, it just hides part of it — the one place a silent row cap
    would be actively dangerous rather than a performance tradeoff. If the
    open-approvals queue ever legitimately runs into the thousands, the fix
    is a `status` index plus real server-side pagination (the Authorization
    Center already has a page cursor in the UI — see ac_page — it just
    isn't wired to .range() yet).
    """
    try:
        res = (
            supabase.table('job_orders')
            .select("*")
            .in_('status', ["Pending Approval", "Pending Revision Approval"])
            .execute()
        )
        return pd.DataFrame(res.data)
    except Exception:
        logger.exception("fetch_pending_orders_cached failed.")
        return pd.DataFrame()


@st.cache_data(ttl=60, show_spinner=False)
def get_approved_orders_cached() -> pd.DataFrame:
    """
    Cached fetch for approved orders — Command Center & Archive.
    TTL 60 s: avoids unbounded full-table scan on every rerun.
    Call get_approved_orders_cached.clear() after any Approve/Archive write.
    Session-state-blind by design; check auth in the caller.
    """
    try:
        res = (
            supabase.table('job_orders')
            .select("*")
            .eq('status', 'Approved')
            .execute()
        )
        return pd.DataFrame(res.data)
    except Exception:
        logger.exception("get_approved_orders_cached failed.")
        return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def get_orders_trend_cached(days_back: int = 180) -> pd.DataFrame:
    """
    Powers the Command Center's weekly/monthly trend chart.

    Deliberately NOT the same pattern as get_approved_orders_cached above —
    this is bounded by a created_at date filter, not by status, and only
    selects the handful of columns the trend chart actually needs. That's
    the point: as job_orders grows into the tens of thousands over years,
    this query's cost stays tied to "how many orders in the last N days",
    not "how many orders have ever existed" — so the trend view doesn't
    get slower every month the business operates.
    """
    if not supabase or not st.session_state.get("authenticated"):
        return pd.DataFrame()
    try:
        _cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime('%Y-%m-%d')
        res = (
            supabase.table('job_orders')
            .select("job_order_no,created_at,total_amount,deposit_amount,status")
            .gte('created_at', _cutoff)
            .execute()
        )
        return pd.DataFrame(res.data)
    except Exception:
        logger.exception("get_orders_trend_cached failed.")
        return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def _generate_pdf_cached(order_id: str, order_status: str,
                          order_dept: str, row_json: str) -> bytes:
    """
    Lazy, cached PDF generation for the Order Tracker.
    Keyed on (id, status, dept, row_json): auto-invalidates when
    content or status changes.  TTL 5 min.  Returns raw bytes so
    st.download_button can consume them without a BytesIO seek.
    """
    import json as _j
    row_dict = _j.loads(row_json)
    buf = dispatch_pdf_manifest(row_dict)
    return buf.getvalue()


ARCHIVE_ROW_CAP = 2000  # see get_archive_orders_cached docstring

@st.cache_data(ttl=30, show_spinner=False)
def get_archive_orders_cached() -> pd.DataFrame:
    """
    Fetch post-approval lifecycle orders for the Archive route.
    Statuses: Approved | In Production | At Warehouse | Ready for Collection | Delivered.
    Short TTL (30 s) because status changes here are frequent.
    Call get_archive_orders_cached.clear() after any lifecycle write.

    Capped at ARCHIVE_ROW_CAP, most-recent-first. Unlike the pending queue
    above, an archive is conventionally "recent history first, search for
    older" (same convention as an email or order-history archive), so a cap
    is a defensible product decision here — it just needs a visible
    "showing most recent N" note in the UI once real volume nears the cap,
    which is flagged as a UI follow-up rather than done silently.
    """
    try:
        res = (
            supabase.table('job_orders')
            .select("*")
            .in_('status', ['Approved', 'In Production', 'At Warehouse', 'Ready for Collection', 'Delivered'])
            .order('created_at', desc=True)
            .limit(ARCHIVE_ROW_CAP)
            .execute()
        )
        return pd.DataFrame(res.data)
    except Exception:
        logger.exception("get_archive_orders_cached failed.")
        return pd.DataFrame()


def record_balance_payment(order_id: str, new_deposit: float, receipt_no: str = None) -> bool:
    """
    Record a balance or partial payment by updating deposit_amount.
    Also writes last_payment_date and, if provided, receipt_no.
    Clears both approved and archive caches on success.
    """
    if not supabase:
        return False
    try:
        _ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        _update = {"deposit_amount": round(new_deposit, 2), "last_payment_date": _ts}
        if receipt_no:
            _update["receipt_no"] = receipt_no.strip()
        try:
            supabase.table('job_orders').update(_update).eq('id', order_id).execute()
        except Exception:
            logger.warning(
                "record_balance_payment: full write failed for "
                "order_id=%s, retrying with deposit_amount only.", order_id
            )
            supabase.table('job_orders').update(
                {"deposit_amount": round(new_deposit, 2)}
            ).eq('id', order_id).execute()
        if hasattr(get_approved_orders_cached, 'clear'):
            get_approved_orders_cached.clear()
        if hasattr(get_archive_orders_cached, 'clear'):
            get_archive_orders_cached.clear()
        return True
    except Exception:
        logger.exception("record_balance_payment failed for order_id=%s.", order_id)
        return False


def update_order_lifecycle_status(order_id: str, new_status: str) -> bool:
    """
    Advance an order through the production lifecycle.
    Allowed transitions: Approved → In Production → At Warehouse → Delivered.
    'Ready for Collection' remains a valid target for orders already in that
    leg of the older flow. Writes a dated timestamp field for the
    transition if the column exists.
    """
    if not supabase:
        return False
    _allowed = {'In Production', 'At Warehouse', 'Ready for Collection', 'Delivered'}
    if new_status not in _allowed:
        return False
    try:
        _ts    = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        _tscol = {
            'In Production':        'production_start_date',
            'At Warehouse':         'warehouse_date',
            'Ready for Collection': 'ready_date',
            'Delivered':            'delivered_date',
        }.get(new_status)
        _payload = {'status': new_status}
        if _tscol:
            _payload[_tscol] = _ts
        try:
            supabase.table('job_orders').update(_payload).eq('id', order_id).execute()
        except Exception:
            logger.warning(
                "update_order_lifecycle_status: timestamp column write failed "
                "for order_id=%s, retrying with status only.", order_id
            )
            supabase.table('job_orders').update({'status': new_status}).eq('id', order_id).execute()
        if hasattr(get_approved_orders_cached, 'clear'):
            get_approved_orders_cached.clear()
        if hasattr(get_archive_orders_cached, 'clear'):
            get_archive_orders_cached.clear()
        return True
    except Exception:
        logger.exception(
            "update_order_lifecycle_status(order_id=%s, new_status=%r) failed.",
            order_id, new_status
        )
        return False


@st.cache_data(ttl=120, show_spinner=False)
def get_recent_customers() -> pd.DataFrame:
    """
    Distinct recent customers for quick-lookup auto-fill in Raise Job Order.
    One representative row per customer_name (most recent).  TTL 120 s.
    """
    if not supabase:
        return pd.DataFrame()
    try:
        res = (
            supabase.table('job_orders')
            .select('customer_name,telephone_number,delivery_mode,delivery_location,delivery_contact')
            .order('created_at', desc=True)
            .limit(600)
            .execute()
        )
        df = pd.DataFrame(res.data)
        if df.empty:
            return df
        return (df.drop_duplicates(subset=['customer_name'])
                  .sort_values('customer_name')
                  .reset_index(drop=True))
    except Exception:
        logger.exception("get_recent_customers failed.")
        return pd.DataFrame()


def get_db_job_orders_by_user(user_email, status_filter=None):
    if not supabase or not st.session_state.get("authenticated"):
        return pd.DataFrame()
    try:
        query = supabase.table('job_orders').select("*").eq('created_by', user_email)
        if status_filter:
            query = query.eq('status', status_filter)
        res = query.order('created_at', desc=False).execute()
        return pd.DataFrame(res.data)
    except Exception:
        logger.exception("get_db_job_orders_by_user(user_email=%s) failed.", user_email)
        return pd.DataFrame()

def get_all_db_job_orders_by_user(user_email):
    if not supabase or not st.session_state.get("authenticated"):
        return pd.DataFrame()
    try:
        res = (
            supabase.table('job_orders')
            .select("*")
            .eq('created_by', user_email)
            .order('created_at', desc=False)
            .execute()
        )
        return pd.DataFrame(res.data)
    except Exception:
        logger.exception("get_all_db_job_orders_by_user(user_email=%s) failed.", user_email)
        return pd.DataFrame()

def handle_production_pdf_export(order_id: str, row_data: dict):
    pdf_bytes = _generate_pdf_cached(
        order_id=order_id,
        order_status="Approved",
        order_dept=row_data.get("_dept", "PRESS"),
        row_json=json.dumps(row_data) 
    )
    # Trigger the download
    st.download_button(
        label="Download PDF",
        data=pdf_bytes,
        file_name=f"Order_{order_id}.pdf",
        mime="application/pdf"
    )

def hydrate_user_profile(user_id: str):
    if not supabase:
        st.session_state.user_profile = None
        return
    try:
        res = (
            supabase.table('profiles')
            .select('id,full_name,email,phone_number,role,department')
            .eq('id', user_id)
            .single()
            .execute()
        )
        st.session_state.user_profile = res.data if res.data else None
    except Exception:
        # Fails safe: user_profile stays None, is_admin resolves False (see
        # SIDEBAR NAVIGATION), so a broken profile fetch locks a session out
        # of admin routes rather than granting them — but it should still
        # be logged, since "why did my role disappear" is a support ticket
        # you want a stack trace for, not a mystery.
        logger.exception("hydrate_user_profile(user_id=%s) failed.", user_id)
        st.session_state.user_profile = None

# ═══════════════════════════════════════════════════════════════════
# 7. CALENDAR-AWARE PRODUCTION SCHEDULING ENGINE
# ═══════════════════════════════════════════════════════════════════
def apply_calendar_bounds(dt):
    dt = dt.replace(tzinfo=None)
    if dt.hour < SHIFT_START_HOUR:
        dt = dt.replace(hour=SHIFT_START_HOUR, minute=0, second=0, microsecond=0)
    elif dt.hour >= SHIFT_END_HOUR:
        dt = (dt + timedelta(days=1)).replace(hour=SHIFT_START_HOUR, minute=0, second=0, microsecond=0)
    while dt.weekday() in [5, 6]:
        dt = (dt + timedelta(days=1)).replace(hour=SHIFT_START_HOUR, minute=0, second=0, microsecond=0)
    return dt

def _next_working_day_start(upstream_start_dt):
    """A downstream stage (Die Cutter after any press, Folder Gluer after
    Die Cutter, etc.) can begin the calendar day AFTER the upstream stage
    STARTED — not a fixed number of hours later, and not once the upstream
    stage fully finishes. This is deliberately the same rule for every
    printing machine, not a special case for one press: overnight drying
    (or, for Die Cutter → Folder Gluer, enough cut stock to start folding)
    is a next-day fact, not an hour-count. Still passed through
    get_machine_next_available_time afterward, so real machine backlog on
    the downstream machine still wins if it's busier than this."""
    _next_day = (upstream_start_dt.replace(tzinfo=None) + timedelta(days=1)).replace(
        hour=SHIFT_START_HOUR, minute=0, second=0, microsecond=0
    )
    return apply_calendar_bounds(_next_day)

def get_machine_next_available_time(machine_name, requested_start_dt):
    df = get_db_jobs()
    naive_requested = requested_start_dt.replace(tzinfo=None)
    if df.empty or 'machine' not in df.columns:
        return apply_calendar_bounds(naive_requested)
    m_df = df[df['machine'] == machine_name].copy()
    if m_df.empty:
        return apply_calendar_bounds(naive_requested)
    m_df['finish_time'] = pd.to_datetime(m_df['finish_time'], format='mixed', errors='coerce')
    m_df = m_df.dropna(subset=['finish_time'])
    if m_df.empty:
        return apply_calendar_bounds(naive_requested)
    max_finish = m_df['finish_time'].max()
    if isinstance(max_finish, pd.Timestamp):
        max_finish = max_finish.to_pydatetime()
    max_finish = max_finish.replace(tzinfo=None)
    return (apply_calendar_bounds(max_finish) if max_finish > naive_requested
            else apply_calendar_bounds(naive_requested))

def calculate_production_time(start_dt, impressions, machine_name, apply_setup=True):
    mach         = MACHINE_DATA.get(machine_name, {'rate': 1000, 'setup_hours': 1.0})
    rate         = mach['rate']
    setup        = mach['setup_hours'] if apply_setup else 0.0
    current_time = apply_calendar_bounds(start_dt)
    if apply_setup:
        current_time += timedelta(hours=setup)
        current_time  = apply_calendar_bounds(current_time)
    remaining_imps = impressions
    while remaining_imps > 0:
        current_time = apply_calendar_bounds(current_time)
        workday_end  = current_time.replace(hour=SHIFT_END_HOUR, minute=0, second=0, microsecond=0)
        available_hours = (workday_end - current_time).total_seconds() / 3600.0
        if available_hours <= 0:
            current_time = (current_time + timedelta(days=1)).replace(hour=SHIFT_START_HOUR, minute=0)
            continue
        possible_today = available_hours * rate
        if remaining_imps <= possible_today:
            current_time  += timedelta(hours=remaining_imps / rate)
            remaining_imps = 0
        else:
            remaining_imps -= possible_today
            current_time    = (current_time + timedelta(days=1)).replace(hour=SHIFT_START_HOUR, minute=0)
    return apply_calendar_bounds(current_time)

def add_multi_part_job(job_data):
    if not supabase:
        return
    # Timestamp-seeded ID: a pure 4-digit random draw (9,000 values) hits ~50%
    # collision odds by ~112 jobs (birthday paradox), and tracking_id is used
    # both for .eq() updates (line ~3915) and .nunique() dashboard counts, so a
    # collision doesn't just look wrong — it can update the wrong job or
    # undercount active jobs. Second-resolution timestamp + 3 random digits
    # keeps the same human-readable "JOB-..." shape while making a same-second
    # collision the only remaining (near-zero) risk.
    tid          = f"JOB-{datetime.now().strftime('%Y%m%d%H%M%S')}{random.randint(100, 999)}"
    total_stages = (
        sum(len(c['machines']) for c in job_data['components'])
        + len(job_data['finishing_machines'])
    )
    val_per_stage = job_data['total_val'] / total_stages if total_stages > 0 else 0
    anchor_start  = datetime.combine(job_data['start_date'], datetime.now().time()).replace(tzinfo=timezone.utc)
    printing_starts   = []
    printing_finishes = []
    records = []
    _seq = 0
    for comp in job_data['components']:
        for machine in comp['machines']:
            allocated_start = get_machine_next_available_time(machine, anchor_start)
            finish          = calculate_production_time(allocated_start, comp['impressions'], machine)
            printing_starts.append(allocated_start)
            printing_finishes.append(finish)
            _seq += 1
            records.append({
                "job_name":       job_data['name'],
                "tracking_id":    tid,
                "machine":        machine,
                "sales_rep":      job_data['sales_rep'],
                "quantity":       int(job_data['total_qty']),
                "ups":            int(job_data['type_id']),
                "impressions":    int(comp['impressions']),
                "start_time":     allocated_start.isoformat(),
                "finish_time":    finish.isoformat(),
                "contract_value": float(val_per_stage),
                "job_order_no":   job_data.get('job_order_no'),
                "sequence_no":    _seq,
                "planned_start":  allocated_start.isoformat(),
                "planned_finish": finish.isoformat(),
                "stage_status":   "Scheduled",
            })
    earliest_base = (max(printing_finishes) if printing_finishes
                     else apply_calendar_bounds(anchor_start))
    # Die Cutter can start the calendar day after printing began — not
    # once printing is fully finished. If a job has multiple press
    # components, all of them need their overnight window, so this uses
    # the LATEST press start among components, not the earliest — the
    # last press to begin is the real bottleneck.
    press_ready_for_cut = (
        _next_working_day_start(max(printing_starts))
        if printing_starts else earliest_base
    )
    ordered_finishing = sorted(
        job_data['finishing_machines'],
        key=lambda x: 0 if "DIE" in x.upper() else (1 if "FOLDER" in x.upper() else 2)
    )
    last_stage_finish     = earliest_base
    die_cutter_start_time = None
    calculation_qty       = job_data['total_qty']
    for machine_name in ordered_finishing:
        if "DIE CUTTER" in machine_name.upper():
            calculation_qty       = job_data['total_qty'] / max(1, job_data['type_id'])
            f_start               = get_machine_next_available_time(machine_name, press_ready_for_cut)
            f_finish              = calculate_production_time(f_start, calculation_qty, machine_name)
            die_cutter_start_time = f_start
            last_stage_finish     = f_finish
        elif "FOLDER GLUER" in machine_name.upper() and die_cutter_start_time is not None:
            # Folding/gluing can start the calendar day after die-cutting
            # began — it doesn't need the die-cutter's full run to finish.
            calculation_qty = job_data['total_qty']
            stagger_offset  = _next_working_day_start(die_cutter_start_time)
            f_start           = get_machine_next_available_time(machine_name, stagger_offset)
            f_finish          = calculate_production_time(f_start, calculation_qty, machine_name)
            last_stage_finish = f_finish
        else:
            calculation_qty   = job_data['total_qty']
            f_start           = get_machine_next_available_time(machine_name, last_stage_finish)
            f_finish          = calculate_production_time(f_start, calculation_qty, machine_name)
            last_stage_finish = f_finish
        _seq += 1
        records.append({
            "job_name":       job_data['name'],
            "tracking_id":    tid,
            "machine":        machine_name,
            "sales_rep":      job_data['sales_rep'],
            "quantity":       int(job_data['total_qty']),
            "ups":            int(job_data['type_id']),
            "impressions":    int(calculation_qty),
            "start_time":     f_start.isoformat(),
            "finish_time":    f_finish.isoformat(),
            "contract_value": float(val_per_stage),
            "job_order_no":   job_data.get('job_order_no'),
            "sequence_no":    _seq,
            "planned_start":  f_start.isoformat(),
            "planned_finish": f_finish.isoformat(),
            "stage_status":   "Scheduled",
        })
    try:
        for r in records:
            supabase.table('jobs').insert(r).execute()
    except Exception as e:
        st.error(f"Database insertion failed: {str(e)}")

def update_stage_status(tracking_id, new_status, revised_finish=None):
    """The only place stage status gets written. If revised_finish is given
    — a real completion, or a proactive re-estimate — the delta versus this
    stage's own planned_finish cascades to every downstream, not-yet-complete
    stage on the same order. Nothing else needs to be told; the view reads
    revised_finish directly."""
    _res = supabase.table('jobs').select('*').eq('tracking_id', tracking_id).execute()
    if not _res.data:
        return False
    _row = _res.data[0]

    _updates = {"stage_status": new_status}
    if new_status == "Complete" and revised_finish is None:
        revised_finish = datetime.now(timezone.utc)
    if revised_finish is not None:
        _updates["revised_finish"] = revised_finish.isoformat()
        if new_status == "Complete":
            _updates["actual_finish"] = revised_finish.isoformat()
    supabase.table('jobs').update(_updates).eq('tracking_id', tracking_id).execute()

    if revised_finish is None or _row.get('sequence_no') is None or not _row.get('job_order_no'):
        return True
    _baseline = _row.get('planned_finish')
    if not _baseline:
        return True
    _delta = (revised_finish - datetime.fromisoformat(str(_baseline).replace('Z', '+00:00'))).total_seconds()
    if abs(_delta) < 60:
        return True

    _sibs = (
        supabase.table('jobs')
        .select('tracking_id, planned_start, revised_start, revised_finish, planned_finish, stage_status')
        .eq('job_order_no', _row['job_order_no'])
        .gt('sequence_no', _row['sequence_no'])
        .neq('stage_status', 'Complete')
        .execute()
    ).data or []

    for _s in _sibs:
        _sib_update = {}
        _base_finish = _s.get('revised_finish') or _s.get('planned_finish')
        if _base_finish:
            _sib_update["revised_finish"] = (
                datetime.fromisoformat(str(_base_finish).replace('Z', '+00:00')) + timedelta(seconds=_delta)
            ).isoformat()
        if _s.get('stage_status') == 'Scheduled':
            _base_start = _s.get('revised_start') or _s.get('planned_start')
            if _base_start:
                _sib_update["revised_start"] = (
                    datetime.fromisoformat(str(_base_start).replace('Z', '+00:00')) + timedelta(seconds=_delta)
                ).isoformat()
        if _delta > 0:
            _sib_update["stage_status"] = "Delayed"
        if _sib_update:
            supabase.table('jobs').update(_sib_update).eq('tracking_id', _s['tracking_id']).execute()
    return True

def get_jobs_by_order_numbers(order_numbers: list[str]) -> pd.DataFrame:
    """One query for the whole page, not one per card."""
    if not supabase or not order_numbers:
        return pd.DataFrame()
    try:
        res = supabase.table('jobs').select("*").in_('job_order_no', order_numbers).execute()
        return pd.DataFrame(res.data)
    except Exception:
        logger.exception("get_jobs_by_order_numbers failed.")
        return pd.DataFrame()

def _pipeline_summary(order_no: str, jobs_df: pd.DataFrame):
    if jobs_df.empty or 'job_order_no' not in jobs_df.columns:
        return None
    _rows = jobs_df[jobs_df['job_order_no'] == order_no].copy()
    if _rows.empty:
        return None
    _rows['finish_time'] = pd.to_datetime(
        _rows.get('revised_finish'), utc=True, errors='coerce'
    ).fillna(pd.to_datetime(_rows['finish_time'], utc=True, errors='coerce'))
    _now = pd.Timestamp.now(tz='UTC')
    _pending = _rows[_rows['finish_time'] >= _now].sort_values('finish_time')
    _current  = _pending.iloc[0] if not _pending.empty else None
    _upcoming = _pending.iloc[1] if len(_pending) > 1 else None
    return {
        "current_machine": _current['machine']  if _current  is not None else None,
        "next_machine":    _upcoming['machine'] if _upcoming is not None else None,
        "eta":             _rows['finish_time'].max(),
        "all_done":        _pending.empty,
    }

# ═══════════════════════════════════════════════════════════════════
# 8a. PRESS PDF VECTOR EXPORT ENGINE
# ═══════════════════════════════════════════════════════════════════
def generate_pdf_manifest(ticket):
    buffer  = io.BytesIO()
    doc     = SimpleDocTemplate(buffer, pagesize=A4,
                                rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    elements = []
    styles   = getSampleStyleSheet()
    bold_style   = ParagraphStyle('BoldStyle',  parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9)
    normal_style = ParagraphStyle('NormStyle',  parent=styles['Normal'], fontName='Helvetica',      fontSize=9)
    small_grey   = ParagraphStyle('SmallGrey',  parent=styles['Normal'], fontName='Helvetica',
                                  fontSize=7, textColor=colors.HexColor("#64748b"))
    def cb(val, match_str):
        if isinstance(val, str) and match_str.upper() in val.upper():
            return "[X]"
        return "[  ]"
    header_data = [[
        Paragraph("<b>APPOINTED TIME PRINTING LTD.</b><br/>PO BOX AC 56 Art Centre Accra<br/>Tel: 0302 661704/6", normal_style),
        Paragraph(
            f"<font size=10 color='#64748b'>JOB ORDER / WAYBILL NO</font><br/>"
            f"<font size=14><b>{ticket.get('job_order_no', 'PENDING')}</b></font>",
            ParagraphStyle(name='R', parent=styles['Normal'], alignment=2)
        )
    ]]
    t_header = Table(header_data, colWidths=[3.5*inch, 3.5*inch])
    t_header.setStyle(TableStyle([
        ('VALIGN',       (0,0), (-1,-1), 'TOP'),
        ('LINEBELOW',    (0,0), (-1,-1), 1, colors.HexColor("#0f172a")),
        ('BOTTOMPADDING',(0,0), (-1,-1), 10)
    ]))
    elements.append(t_header)
    elements.append(Spacer(1, 12))
    total   = float(ticket.get('total_amount',  0) or 0)
    deposit = float(ticket.get('deposit_amount', 0) or 0)
    balance = total - deposit
    # order_date falls back to created_at's date portion — orders raised
    # before the insert-ordering fix have no order_date stored at all,
    # so this keeps existing/already-approved orders displaying
    # correctly too, not just new ones going forward.
    _pdf_order_date = str(ticket.get('order_date', '') or '').strip()
    if not _pdf_order_date:
        _pdf_order_date = str(ticket.get('created_at', '') or '')[:10]
    cust_data = [
        [Paragraph("Customer Name", small_grey), Paragraph("Telephone Number", small_grey),
         Paragraph("Job Order Date", small_grey), Paragraph("Date of Collection", small_grey)],
        [Paragraph(str(ticket.get('customer_name',     '') or ''), bold_style),
         Paragraph(str(ticket.get('telephone_number',  '') or ''), bold_style),
         Paragraph(_pdf_order_date, bold_style),
         Paragraph(str(ticket.get('date_of_collection','') or ''), bold_style)],
        [Paragraph("Total Amount GHC", small_grey), Paragraph("Deposit GHC", small_grey),
         Paragraph("Balance GHC", small_grey),      Paragraph("Receipt No", small_grey)],
        [Paragraph(f"{total:,.2f}", bold_style), Paragraph(f"{deposit:,.2f}", bold_style),
         Paragraph(f"{balance:,.2f}", bold_style), Paragraph(str(ticket.get('receipt_no', '') or ''), bold_style)]
    ]
    t_cust = Table(cust_data, colWidths=[2.2*inch, 1.6*inch, 1.6*inch, 1.6*inch])
    t_cust.setStyle(TableStyle([
        ('GRID',         (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
        ('BACKGROUND',   (0,0), (-1, 0), colors.HexColor("#F8FAFC")),
        ('BACKGROUND',   (0,2), (-1, 2), colors.HexColor("#F8FAFC")),
        ('VALIGN',       (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING',   (0,0), (-1,-1), 4),
        ('BOTTOMPADDING',(0,0), (-1,-1), 4)
    ]))
    elements.append(t_cust)
    elements.append(Spacer(1, 8))

    # ── Payment terms — explicit when no deposit was taken, so nobody
    # has to infer "0.00 deposit" as either an oversight or a policy ──
    _pdf_terms = str(ticket.get('payment_terms', '') or '').strip()
    if balance > 0:
        _is_30day_pdf = "30-Day Credit Terms" in _pdf_terms
        _notes_part = (
            _pdf_terms.split("|", 1)[1].strip() if "|" in _pdf_terms
            else (_pdf_terms if not _is_30day_pdf else "")
        )
        if _is_30day_pdf:
            _terms_text = "PAYMENT TERMS: 30-Day Credit — payment due within 30 days of collection."
            if _notes_part:
                _terms_text += f" Note: {_notes_part}"
        elif _notes_part:
            _terms_text = f"PAYMENT TERMS: {_notes_part}"
        else:
            _terms_text = "PAYMENT TERMS: Full payment due before collection — no arrangement specified for this outstanding balance."
        elements.append(Paragraph(
            _terms_text,
            ParagraphStyle('TermsNote', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8.5,
                           textColor=colors.HexColor("#92400e"), backColor=colors.HexColor("#fffbeb"),
                           borderColor=colors.HexColor("#fde68a"), borderWidth=1, borderPadding=6)
        ))
        elements.append(Spacer(1, 8))

    _pdf_sample = str(ticket.get('sample_attached', '') or '').strip()
    if _pdf_sample == "Yes":
        elements.append(Paragraph(
            f"SAMPLE ATTACHED — with: {str(ticket.get('sample_with','') or '—')}",
            ParagraphStyle('SampleNote', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8.5,
                           textColor=colors.HexColor("#0369a1"), backColor=colors.HexColor("#f0f9ff"),
                           borderColor=colors.HexColor("#bae6fd"), borderWidth=1, borderPadding=6)
        ))
        elements.append(Spacer(1, 8))

    _pdf_sales_rep = str(ticket.get('sales_rep', '') or '').strip()
    if _pdf_sales_rep:
        elements.append(Paragraph(
            f"SALES REP: {_pdf_sales_rep}",
            ParagraphStyle('SalesRepNote', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8.5,
                           textColor=colors.HexColor("#334155"), backColor=colors.HexColor("#f8fafc"),
                           borderColor=colors.HexColor("#e2e8f0"), borderWidth=1, borderPadding=6)
        ))
        elements.append(Spacer(1, 8))

    type_print = str(ticket.get('type_of_print', '') or '').strip() or '—'
    mat_source = str(ticket.get('material_source', '') or '').strip() or '—'
    cat_data = [
        [Paragraph("TYPE OF PRINT", bold_style), Paragraph(type_print, normal_style)],
        [Paragraph("MATERIAL SOURCE", bold_style), Paragraph(mat_source, normal_style)]
    ]
    t_cat = Table(cat_data, colWidths=[2.0*inch, 5.0*inch])
    t_cat.setStyle(TableStyle([
        ('LINEBELOW',    (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ('TOPPADDING',   (0,0), (-1,-1), 6),
        ('BOTTOMPADDING',(0,0), (-1,-1), 6)
    ]))
    elements.append(t_cat)
    elements.append(Spacer(1, 12))
    elements.append(Paragraph("JOB DESCRIPTION", small_grey))
    desc_data = [[Paragraph(str(ticket.get('job_description', '') or ''), normal_style)]]
    t_desc    = Table(desc_data, colWidths=[7.0*inch], rowHeights=[1.2*inch])
    t_desc.setStyle(TableStyle([
        ('BOX',        (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
        ('VALIGN',     (0,0), (-1,-1), 'TOP'),
        ('TOPPADDING', (0,0), (-1,-1), 8)
    ]))
    elements.append(t_desc)
    elements.append(Spacer(1, 6))
    size_data = [[
        Paragraph("PRINT SIZE: " + str(ticket.get('print_size', '') or ''), normal_style),
        Paragraph("FINISHED PRINT SIZE: " + str(ticket.get('finished_print_size', '') or ''), normal_style)
    ]]
    t_size = Table(size_data, colWidths=[3.5*inch, 3.5*inch])
    elements.append(t_size)
    elements.append(Spacer(1, 12))
    mat_grid = [
        [Paragraph("Material Description (Paper)", small_grey), Paragraph("GSM", small_grey),
         Paragraph("Size", small_grey), Paragraph("Paper Colour", small_grey)],
        [Paragraph(str(ticket.get('paper_type',   '-') or '-'), normal_style),
         Paragraph(str(ticket.get('gsm',          '-') or '-'), normal_style),
         Paragraph(str(ticket.get('paper_size',   '-') or '-'), normal_style),
         Paragraph(str(ticket.get('paper_colour', '-') or '-'), normal_style)]
    ]
    t_mat = Table(mat_grid, colWidths=[2.5*inch, 1.0*inch, 1.5*inch, 2.0*inch])
    t_mat.setStyle(TableStyle([
        ('GRID',        (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
        ('BACKGROUND',  (0,0), (-1, 0), colors.HexColor("#F8FAFC")),
        ('TOPPADDING',  (0,0), (-1,-1), 6),
        ('BOTTOMPADDING',(0,0),(-1,-1), 6)
    ]))
    elements.append(t_mat)
    elements.append(Spacer(1, 12))
    bind_type = str(ticket.get('binding_type',   '') or '')
    lam_type  = str(ticket.get('laminating_type','') or '')
    del_mode  = str(ticket.get('delivery_mode',  '') or '')
    # Field name varies by submission path (Press vs Garment, single vs
    # batch) -- check every real name quantity is ever stored under.
    _pdf_qty = (
        ticket.get('qty_to_print') or ticket.get('print_qty')
        or ticket.get('qty_to_pack') or ticket.get('quantity') or '-'
    )
    finishing_data = [
        [Paragraph("QUANTITY", bold_style),
         Paragraph(str(_pdf_qty), normal_style),
         Paragraph("IMPRESSION", bold_style),
         Paragraph(str(ticket.get('impressions_colour', '-') or '-'), normal_style)],
        [Paragraph("DELIVERY MODE", bold_style),
         Paragraph(del_mode.strip() or '—', normal_style),
         Paragraph("", normal_style), Paragraph("", normal_style)],
        [Paragraph("BINDING", bold_style),
         Paragraph(bind_type.strip() or 'None', normal_style),
         Paragraph("LAMINATING", bold_style),
         Paragraph(lam_type.strip() or 'None', normal_style)]
    ]
    t_fin = Table(finishing_data, colWidths=[1.2*inch, 2.3*inch, 1.2*inch, 2.3*inch])
    t_fin.setStyle(TableStyle([
        ('VALIGN',       (0,0), (-1,-1), 'TOP'),
        ('LINEABOVE',    (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ('TOPPADDING',   (0,0), (-1,-1), 6),
        ('BOTTOMPADDING',(0,0), (-1,-1), 6)
    ]))
    elements.append(t_fin)
    elements.append(Spacer(1, 30))

    # ── Pull live approval fields from the ticket ────────────────────────
    _fp_prep_by   = str(ticket.get('created_by',    '') or '').strip()
    _fp_auth_by   = str(ticket.get('approved_by',   '') or '').strip()
    _fp_ord_date  = _pdf_order_date
    _fp_appr_raw  = str(ticket.get('approval_date', '') or ticket.get('updated_at', '') or '').strip()

    # Format approval timestamp → "12 Jun 2025  14:35 UTC"
    def _fmt_ts(raw: str) -> str:
        if not raw or raw in ('-', 'None', 'nan'):
            return ''
        try:
            from datetime import datetime as _d
            _clean = raw.replace('Z', '+00:00')
            _dt    = _d.fromisoformat(_clean)
            return _dt.strftime('%d %b %Y  %H:%M UTC')
        except Exception:
            return raw
    _fp_appr_date_fmt = _fmt_ts(_fp_appr_raw)

    # Signature-construction helper:
    # Produces an uppercase-initials stamp + full name in italic
    # e.g.  "K.A.B" / "Kwame Asante Boateng" → "K.A.B. — Kwame Asante Boateng"
    def _build_sig(full_name: str) -> str:
        if not full_name or full_name in ('-', 'None', 'nan', 'Guest'):
            return '.......................................'
        parts    = [p for p in full_name.split() if p]
        initials = '.'.join(w[0].upper() for w in parts) + '.'
        return f"{initials}  —  {full_name}"

    _fp_is_approved = bool(_fp_auth_by and _fp_auth_by not in ('-', 'None', 'nan', 'Guest'))

    sig_style = ParagraphStyle(
        'SigStyle', parent=styles['Normal'],
        fontName='Helvetica-BoldOblique', fontSize=9,
        textColor=colors.HexColor('#0f172a')
    )

    _prep_label = (f"Prepared by:  {_fp_prep_by}"
                   if _fp_prep_by else
                   "Prepared by: .......................................")
    _auth_label = (f"Authorized by:  {_fp_auth_by}"
                   if _fp_is_approved else
                   "Authorized by: ......................................")
    _appr_date_label = (f"Approved Date:  {_fp_appr_date_fmt}"
                        if _fp_appr_date_fmt else
                        "Approved Date: .........................")

    footer_data = [
        [Paragraph(_prep_label,    normal_style),
         Paragraph("Sign: .......................", normal_style),
         Paragraph(f"Date:  {_fp_ord_date}", normal_style)],
        [Paragraph(_auth_label,    normal_style),
         Paragraph(
             _build_sig(_fp_auth_by) if _fp_is_approved else "Sign: .......................",
             sig_style if _fp_is_approved else normal_style
         ),
         Paragraph(_appr_date_label, normal_style)],
        [Paragraph("<i>JOB APPROVAL / JOB HISTORY USE ONLY</i>", normal_style), "", ""]
    ]
    t_foot = Table(footer_data, colWidths=[3.0*inch, 2.0*inch, 2.0*inch])
    t_foot.setStyle(TableStyle([
        ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
        ('LINEABOVE',     (0,0), (-1, 0), 0.75, colors.HexColor('#0f172a')),
        ('TOPPADDING',    (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
        # Shade the authorized row green if approved, light-grey if not
        ('BACKGROUND',    (0,1), (-1,1),
         colors.HexColor('#f0fdf4') if _fp_is_approved else colors.HexColor('#f8fafc')),
    ]))
    elements.append(t_foot)
    doc.build(elements)
    buffer.seek(0)
    return buffer

# ═══════════════════════════════════════════════════════════════════
# 8b. GARMENT PDF VECTOR EXPORT ENGINE
# ═══════════════════════════════════════════════════════════════════
def generate_garment_pdf_manifest(ticket):
    """Dedicated ReportLab PDF generator for Garment department orders.
    Layout mirrors the physical GARMENT waybill template exactly."""
    buffer = io.BytesIO()
    # Safe page width: A4 = 595pt. Margins 32pt each side → usable = 531pt = 7.375in
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=32, leftMargin=32, topMargin=32, bottomMargin=32)
    elements = []
    styles   = getSampleStyleSheet()
    FULL_W   = 7.375 * inch   # total usable column width

    bold_s   = ParagraphStyle('GB',  parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9)
    norm_s   = ParagraphStyle('GN',  parent=styles['Normal'], fontName='Helvetica',      fontSize=9)
    small_s  = ParagraphStyle('GS',  parent=styles['Normal'], fontName='Helvetica',
                               fontSize=7, textColor=colors.HexColor("#64748b"))
    white_b  = ParagraphStyle('GWB', parent=styles['Normal'], fontName='Helvetica-Bold',
                               fontSize=8, textColor=colors.white)
    white_n  = ParagraphStyle('GWN', parent=styles['Normal'], fontName='Helvetica',
                               fontSize=7, textColor=colors.white)
    navy     = colors.HexColor("#0f172a")
    slate    = colors.HexColor("#CBD5E1")
    light    = colors.HexColor("#F8FAFC")

    def cb(val, match_str):
        if isinstance(val, str) and match_str.upper() in val.upper():
            return "[X]"
        return "[  ]"

    def safe(v, default="-"):
        return str(v or default).strip() or default

    # ── HEADER ──────────────────────────────────────────────────────
    order_no = safe(ticket.get('job_order_no', 'PENDING'), 'PENDING')
    hdr_data = [[
        Paragraph("<b>APPOINTED TIME PRINTING</b><br/>P.O BOX AC 56 Art Centre Accra<br/>Tel: 0302 689704/6", norm_s),
        Paragraph("<b>JOB ORDER</b>", ParagraphStyle('GT', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=14)),
        Paragraph(
            f"<font size=7 color='#64748b'>WAYBILL NO:</font> <b>{order_no}</b><br/>"
            f"<font size=7 color='#64748b'>JOB ORDER NO:</font> <b>{order_no}</b>",
            ParagraphStyle('GR', parent=styles['Normal'], alignment=2, fontSize=8)
        )
    ]]
    t_hdr = Table(hdr_data, colWidths=[2.6*inch, 2.0*inch, 2.775*inch])
    t_hdr.setStyle(TableStyle([
        ('VALIGN',       (0,0), (-1,-1), 'TOP'),
        ('LINEBELOW',    (0,0), (-1,-1), 1.5, navy),
        ('BOTTOMPADDING',(0,0), (-1,-1), 8),
    ]))
    elements.append(t_hdr)
    elements.append(Spacer(1, 5))

    # ── DEPT BAR ─────────────────────────────────────────────────────
    dept_val = safe(ticket.get('department', 'GARMENT'), 'GARMENT').upper()
    dept_data = [[
        Paragraph("<b>DEPT</b>", white_b),
        Paragraph(dept_val, norm_s),
    ]]
    t_dept = Table(dept_data, colWidths=[0.6*inch, FULL_W - 0.6*inch])
    t_dept.setStyle(TableStyle([
        ('BACKGROUND',   (0,0), (0,0), navy),
        ('GRID',         (0,0), (-1,-1), 0.5, slate),
        ('TOPPADDING',   (0,0), (-1,-1), 4),
        ('BOTTOMPADDING',(0,0), (-1,-1), 4),
        ('VALIGN',       (0,0), (-1,-1), 'MIDDLE'),
    ]))
    elements.append(t_dept)
    elements.append(Spacer(1, 4))

    # ── CUSTOMER / FINANCIAL MATRIX ───────────────────────────────────
    total   = float(ticket.get('total_amount',  0) or 0)
    deposit = float(ticket.get('deposit_amount', 0) or 0)
    balance = total - deposit
    cw = FULL_W / 4
    cf_data = [
        [Paragraph("Customer Name",      small_s), Paragraph("", small_s),
         Paragraph("Total Amount GH₵",   small_s), Paragraph("", small_s)],
        [Paragraph(safe(ticket.get('customer_name')), bold_s), Paragraph("", norm_s),
         Paragraph(f"{total:,.2f}",        bold_s), Paragraph("", norm_s)],
        [Paragraph("Telephone Number",   small_s), Paragraph("", small_s),
         Paragraph("Deposit GH₵",         small_s), Paragraph("", small_s)],
        [Paragraph(safe(ticket.get('telephone_number')), bold_s), Paragraph("", norm_s),
         Paragraph(f"{deposit:,.2f}",      bold_s), Paragraph("", norm_s)],
        [Paragraph("Order Date",         small_s), Paragraph("", small_s),
         Paragraph("Balance GH₵",         small_s), Paragraph("", small_s)],
        [Paragraph(safe(ticket.get('order_date') or str(ticket.get('created_at','') or '')[:10]), bold_s), Paragraph("", norm_s),
         Paragraph(f"{balance:,.2f}",      bold_s), Paragraph("", norm_s)],
        [Paragraph("Date of Collection", small_s), Paragraph("Qty. to Print", small_s),
         Paragraph("Balance Due Date",    small_s), Paragraph("", small_s)],
        [Paragraph(safe(ticket.get('date_of_collection')), bold_s),
         Paragraph(str(int(ticket.get('qty_to_print', 0) or 0)), bold_s),
         Paragraph(safe(ticket.get('balance_due_date')), bold_s),
         Paragraph("", norm_s)],
    ]
    t_cf = Table(cf_data, colWidths=[cw, cw, cw, cw])
    t_cf.setStyle(TableStyle([
        ('GRID',         (0,0), (-1,-1), 0.5, slate),
        ('BACKGROUND',   (0,0), (-1, 0), light),
        ('BACKGROUND',   (0,2), (-1, 2), light),
        ('BACKGROUND',   (0,4), (-1, 4), light),
        ('BACKGROUND',   (0,6), (-1, 6), light),
        ('SPAN',         (0,0), (1,0)), ('SPAN', (0,1), (1,1)),
        ('SPAN',         (0,2), (1,2)), ('SPAN', (0,3), (1,3)),
        ('SPAN',         (0,4), (1,4)), ('SPAN', (0,5), (1,5)),
        ('TOPPADDING',   (0,0), (-1,-1), 3),
        ('BOTTOMPADDING',(0,0), (-1,-1), 3),
        ('VALIGN',       (0,0), (-1,-1), 'MIDDLE'),
    ]))
    elements.append(t_cf)
    elements.append(Spacer(1, 5))

    _g_pdf_terms = safe(ticket.get('payment_terms'), '')
    if balance > 0:
        _g_is_30day_pdf = "30-Day Credit Terms" in _g_pdf_terms
        _g_notes_part = (
            _g_pdf_terms.split("|", 1)[1].strip() if "|" in _g_pdf_terms
            else (_g_pdf_terms if not _g_is_30day_pdf else "")
        )
        if _g_is_30day_pdf:
            _g_terms_text = "PAYMENT TERMS: 30-Day Credit — payment due within 30 days of collection."
            if _g_notes_part:
                _g_terms_text += f" Note: {_g_notes_part}"
        elif _g_notes_part:
            _g_terms_text = f"PAYMENT TERMS: {_g_notes_part}"
        else:
            _g_terms_text = "PAYMENT TERMS: Full payment due before collection — no arrangement specified for this outstanding balance."
        elements.append(Paragraph(
            _g_terms_text,
            ParagraphStyle('GTermsNote', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8.5,
                           textColor=colors.HexColor("#92400e"), backColor=colors.HexColor("#fffbeb"),
                           borderColor=colors.HexColor("#fde68a"), borderWidth=1, borderPadding=6)
        ))
        elements.append(Spacer(1, 5))

    _g_pdf_sample = safe(ticket.get('sample_attached'), '')
    if _g_pdf_sample == "Yes":
        elements.append(Paragraph(
            f"SAMPLE ATTACHED — with: {safe(ticket.get('sample_with'))}",
            ParagraphStyle('GSampleNote', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8.5,
                           textColor=colors.HexColor("#0369a1"), backColor=colors.HexColor("#f0f9ff"),
                           borderColor=colors.HexColor("#bae6fd"), borderWidth=1, borderPadding=6)
        ))
        elements.append(Spacer(1, 5))

    _g_pdf_sales_rep = safe(ticket.get('sales_rep'), '')
    if _g_pdf_sales_rep:
        elements.append(Paragraph(
            f"SALES REP: {_g_pdf_sales_rep}",
            ParagraphStyle('GSalesRepNote', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8.5,
                           textColor=colors.HexColor("#334155"), backColor=colors.HexColor("#f8fafc"),
                           borderColor=colors.HexColor("#e2e8f0"), borderWidth=1, borderPadding=6)
        ))
        elements.append(Spacer(1, 5))

    # ── TYPE OF PRINT ─────────────────────────────────────────────────
    type_print = safe(ticket.get('print_type') or ticket.get('type_of_print'), '').strip() or '—'
    mat_source = safe(ticket.get('material_source'), '').strip() or '—'
    tp_data = [
        [Paragraph("<b>TYPE OF PRINT</b>", bold_s), Paragraph(type_print, norm_s)],
        [Paragraph("<b>MATERIAL SOURCE</b>", bold_s), Paragraph(mat_source, norm_s)],
    ]
    t_tp = Table(tp_data, colWidths=[1.5*inch, FULL_W - 1.5*inch])
    t_tp.setStyle(TableStyle([
        ('LINEBELOW',    (0,0), (-1,-1), 0.5, slate),
        ('TOPPADDING',   (0,0), (-1,-1), 5),
        ('BOTTOMPADDING',(0,0), (-1,-1), 5),
    ]))
    elements.append(t_tp)
    elements.append(Spacer(1, 4))

    # ── JOB DESCRIPTION ───────────────────────────────────────────────
    elements.append(Paragraph("JOB DESCRIPTION", small_s))
    jd_data = [[Paragraph(safe(ticket.get('job_description'), ''), norm_s)]]
    t_jd    = Table(jd_data, colWidths=[FULL_W], rowHeights=[0.75*inch])
    t_jd.setStyle(TableStyle([
        ('BOX',        (0,0), (-1,-1), 0.5, slate),
        ('VALIGN',     (0,0), (-1,-1), 'TOP'),
        ('TOPPADDING', (0,0), (-1,-1), 6),
    ]))
    elements.append(t_jd)
    elements.append(Spacer(1, 4))

    # ── PRINT SIZE / FINISHED SIZE / YARDAGE ──────────────────────────
    p_size  = safe(ticket.get('print_size'), '')
    f_size  = safe(ticket.get('finished_print_size'), '')
    yardage = safe(ticket.get('yardage'), '')
    ps_data = [
        [Paragraph("<b>PRINT SIZE</b>", bold_s),
         Paragraph(
             f"{cb(p_size,'A1')} A1  {cb(p_size,'A2')} A2  {cb(p_size,'A3')} A3  "
             f"{cb(p_size,'A4')} A4  {cb(p_size,'A5')} A5  {cb(p_size,'A6')} A6",
             norm_s
         )],
        [Paragraph("<b>FINISHED PRINT SIZE</b>", bold_s),
         Paragraph(
             f"{cb(f_size,'A1')} A1  {cb(f_size,'A2')} A2  {cb(f_size,'A3')} A3  "
             f"{cb(f_size,'A4')} A4  {cb(f_size,'A5')} A5  {cb(f_size,'A6')} A6<br/>"
             f"{cb(yardage,'1YRD')} 1YRD  {cb(yardage,'2YRD')} 2YRDs  "
             f"{cb(yardage,'3YRD')} 3YRDs  {cb(yardage,'4YRD')} 4YRDs  "
             f"{cb(yardage,'5YRD')} 5YRDs  {cb(yardage,'6YRD')} 6YRDs  "
             f"{cb(yardage,'3FTx4FT')} 3FTx4FT  {cb(yardage,'4FTx8FT')} 4FTx8FT",
             norm_s
         )],
    ]
    t_ps = Table(ps_data, colWidths=[1.5*inch, FULL_W - 1.5*inch])
    t_ps.setStyle(TableStyle([
        ('LINEBELOW',    (0,0), (-1,-1), 0.5, slate),
        ('TOPPADDING',   (0,0), (-1,-1), 4),
        ('BOTTOMPADDING',(0,0), (-1,-1), 4),
    ]))
    elements.append(t_ps)
    elements.append(Spacer(1, 4))

    # ── ADDITIONAL COMMENTS ───────────────────────────────────────────
    elements.append(Paragraph("ADDITIONAL COMMENTS", small_s))
    ac_text = safe(ticket.get('additional_comments'), '')
    ac_data = [[Paragraph(ac_text, norm_s)]]
    t_ac    = Table(ac_data, colWidths=[FULL_W], rowHeights=[0.45*inch])
    t_ac.setStyle(TableStyle([
        ('BOX',        (0,0), (-1,-1), 0.5, slate),
        ('VALIGN',     (0,0), (-1,-1), 'TOP'),
        ('TOPPADDING', (0,0), (-1,-1), 4),
    ]))
    elements.append(t_ac)
    elements.append(Spacer(1, 5))

    # ── MATERIAL DESCRIPTION TABLE ────────────────────────────────────
    mat_hdr_style = ParagraphStyle('MH', parent=styles['Normal'], fontName='Helvetica-Bold',
                                   fontSize=8, textColor=colors.white)
    mat_rows_raw = ticket.get('material_description_rows')
    if isinstance(mat_rows_raw, list) and mat_rows_raw:
        mat_rows = mat_rows_raw
    else:
        raw_text = safe(ticket.get('material_description'), '')
        mat_rows = [{"material": raw_text, "sizes": safe(ticket.get('finished_print_size'), ''), "colour": ""}] if raw_text and raw_text != '-' else []

    mat_tbl = [[
        Paragraph("Material", mat_hdr_style),
        Paragraph("Sizes [if applicable]", mat_hdr_style),
        Paragraph("Colour [if applicable]", mat_hdr_style),
    ]]
    for mr in mat_rows[:8]:
        mat_tbl.append([
            Paragraph(safe(mr.get('material'), ''), norm_s),
            Paragraph(safe(mr.get('sizes'),    ''), norm_s),
            Paragraph(safe(mr.get('colour'),   ''), norm_s),
        ])
    while len(mat_tbl) < 5:
        mat_tbl.append([Paragraph("", norm_s), Paragraph("", norm_s), Paragraph("", norm_s)])
    cw3 = FULL_W / 3
    t_mt = Table(mat_tbl, colWidths=[cw3, cw3, cw3])
    t_mt.setStyle(TableStyle([
        ('BACKGROUND',   (0,0), (-1,0), navy),
        ('GRID',         (0,0), (-1,-1), 0.5, slate),
        ('TOPPADDING',   (0,0), (-1,-1), 4),
        ('BOTTOMPADDING',(0,0), (-1,-1), 4),
        ('VALIGN',       (0,0), (-1,-1), 'TOP'),
    ]))
    elements.append(t_mt)
    elements.append(Spacer(1, 4))

    # ── OTHER SPECIFICATIONS ──────────────────────────────────────────
    other_specs = safe(ticket.get('other_specifications'), '')
    oth_data = [[
        Paragraph("Indicate any other necessary specifications", small_s),
        Paragraph(other_specs, norm_s)
    ]]
    t_oth = Table(oth_data, colWidths=[2.0*inch, FULL_W - 2.0*inch])
    t_oth.setStyle(TableStyle([
        ('BOX',         (0,0), (-1,-1), 0.5, slate),
        ('TOPPADDING',  (0,0), (-1,-1), 4),
        ('BOTTOMPADDING',(0,0),(-1,-1), 4),
        ('VALIGN',      (0,0), (-1,-1), 'TOP'),
    ]))
    elements.append(t_oth)
    elements.append(Spacer(1, 5))

    # ── PROCESS / TECHNICAL INFO ──────────────────────────────────────
    process_info = safe(ticket.get('process_info'), '')
    proc_data = [
        [Paragraph("<b>PROCESS</b>", bold_s), Paragraph(process_info, norm_s)],
        [Paragraph("Please provide additional technical Information", small_s), Paragraph("", norm_s)],
    ]
    t_proc = Table(proc_data, colWidths=[1.8*inch, FULL_W - 1.8*inch])
    t_proc.setStyle(TableStyle([
        ('LINEBELOW',    (0,0), (-1,-1), 0.5, slate),
        ('TOPPADDING',   (0,0), (-1,-1), 4),
        ('BOTTOMPADDING',(0,0), (-1,-1), 4),
        ('VALIGN',       (0,0), (-1,-1), 'TOP'),
    ]))
    elements.append(t_proc)
    elements.append(Spacer(1, 5))

    # ── PACKAGING + DELIVERY MODE ─────────────────────────────────────
    pkg_mode  = safe(ticket.get('packaging_mode'), '').strip() or '—'
    del_mode  = safe(ticket.get('delivery_mode'),  '').strip() or '—'
    qty_pack  = safe(ticket.get('qty_to_pack'),    '')
    location  = safe(ticket.get('delivery_location'), '')
    contact   = safe(ticket.get('delivery_contact'),  '')
    pkg_specs = safe(ticket.get('packaging_specs'),   '')
    half      = FULL_W / 2
    pkg_data  = [
        [Paragraph("<b>PACKAGING</b>", white_b), Paragraph("<b>DELIVERY MODE</b>", white_b)],
        [Paragraph(pkg_mode, bold_s), Paragraph(del_mode, bold_s)],
        [Paragraph(f"QTY TO PACK: {qty_pack}", norm_s),
         Paragraph(f"LOCATION: {location}", norm_s)],
        [Paragraph(pkg_specs, norm_s),
         Paragraph(f"CONTACT PERSON: {contact}", norm_s)],
    ]
    t_pkg = Table(pkg_data, colWidths=[half, half])
    t_pkg.setStyle(TableStyle([
        ('BACKGROUND',   (0,0), (-1,0), navy),
        ('GRID',         (0,0), (-1,-1), 0.5, slate),
        ('TOPPADDING',   (0,0), (-1,-1), 4),
        ('BOTTOMPADDING',(0,0), (-1,-1), 4),
        ('VALIGN',       (0,0), (-1,-1), 'TOP'),
    ]))
    elements.append(t_pkg)
    elements.append(Spacer(1, 18))

    # ── SIGNATURE FOOTER ──────────────────────────────────────────────
    _gf_prep_by  = safe(ticket.get('created_by'),    '')
    _gf_auth_by  = safe(ticket.get('approved_by'),   '')
    _gf_ord_date = safe(ticket.get('order_date') or str(ticket.get('created_at','') or '')[:10], '')
    _gf_appr_raw = safe(ticket.get('approval_date', '') or ticket.get('updated_at', ''), '')

    def _gf_fmt_ts(raw: str) -> str:
        if not raw or raw in ('-', 'None', 'nan'):
            return ''
        try:
            from datetime import datetime as _d
            _clean = raw.replace('Z', '+00:00')
            _dt    = _d.fromisoformat(_clean)
            return _dt.strftime('%d %b %Y  %H:%M UTC')
        except Exception:
            return raw
    _gf_appr_fmt = _gf_fmt_ts(_gf_appr_raw)

    def _gf_build_sig(full_name: str) -> str:
        if not full_name or full_name in ('-', 'None', 'nan', 'Guest'):
            return '.......................................'
        parts    = [p for p in full_name.split() if p]
        initials = '.'.join(w[0].upper() for w in parts) + '.'
        return f"{initials}  —  {full_name}"

    _gf_is_approved = bool(
        _gf_auth_by and _gf_auth_by not in ('-', 'None', 'nan', 'Guest', '')
    )

    gf_sig_style = ParagraphStyle(
        'GFSig', parent=styles['Normal'],
        fontName='Helvetica-BoldOblique', fontSize=9,
        textColor=navy
    )

    _gf_prep_label = (f"Prepared by:  {_gf_prep_by}"
                      if _gf_prep_by and _gf_prep_by != '-' else
                      "Prepared by: .................................")
    _gf_auth_label = (f"Authorized by:  {_gf_auth_by}"
                      if _gf_is_approved else
                      "Authorized by: .................................")
    _gf_appr_label = (f"Approved Date:  {_gf_appr_fmt}"
                      if _gf_appr_fmt else
                      "Approved Date: .........................")

    foot_data = [
        [Paragraph(_gf_prep_label, norm_s),
         Paragraph("Sign: ........................", norm_s),
         Paragraph("", norm_s)],
        [Paragraph(_gf_auth_label, norm_s),
         Paragraph(f"Prepared Date:  {_gf_ord_date}", norm_s),
         Paragraph("", norm_s)],
        [Paragraph(
             _gf_build_sig(_gf_auth_by) if _gf_is_approved else "Sign: ........................................",
             gf_sig_style if _gf_is_approved else norm_s
         ),
         Paragraph(_gf_appr_label, norm_s),
         Paragraph("", norm_s)],
    ]
    t_foot = Table(foot_data, colWidths=[2.8*inch, 2.8*inch, FULL_W - 5.6*inch])
    t_foot.setStyle(TableStyle([
        ('LINEABOVE',    (0,0), (-1,0), 0.75, navy),
        ('TOPPADDING',   (0,0), (-1,-1), 6),
        ('BOTTOMPADDING',(0,0), (-1,-1), 6),
        ('VALIGN',       (0,0), (-1,-1), 'MIDDLE'),
        ('BACKGROUND',   (0,1), (-1,2),
         colors.HexColor('#f0fdf4') if _gf_is_approved else colors.HexColor('#f8fafc')),
    ]))
    elements.append(t_foot)
    doc.build(elements)
    buffer.seek(0)
    return buffer

# ═══════════════════════════════════════════════════════════════════
# 8c. SMART PDF DISPATCHER — routes to correct engine by department
# ═══════════════════════════════════════════════════════════════════
def dispatch_pdf_manifest(row_dict):
    """Return the correct PDF buffer for a given order row dictionary."""
    if _is_garment(row_dict):
        return generate_garment_pdf_manifest(row_dict)
    return generate_pdf_manifest(row_dict)

# ═══════════════════════════════════════════════════════════════════
# 9. AUTHENTICATION GATE
# ═══════════════════════════════════════════════════════════════════
if not st.session_state.authenticated:
    st.markdown("<div style='margin-top:5rem;'></div>", unsafe_allow_html=True)
    st.markdown("<h2 style='text-align:center;color:#0f172a;margin-bottom:2rem;'>System Authentication</h2>",
                unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        with st.form("auth_form"):
            st.markdown("<div style='text-align:center;font-weight:600;font-size:14px;"
                        "margin-bottom:1rem;'>Authorized Personnel Only</div>", unsafe_allow_html=True)
            email    = st.text_input("Corporate Email Address")
            password = st.text_input("Secure Password", type="password")
            submit_login = st.form_submit_button("Login", use_container_width=True)
            if submit_login and supabase:
                try:
                    auth_res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                    if auth_res.user:
                        st.session_state.authenticated = True
                        st.session_state.user_email    = auth_res.user.email
                        hydrate_user_profile(auth_res.user.id)
                        st.rerun()
                except Exception:
                    st.error("Authentication Denied: Invalid credentials.")
    st.stop()

# ── 30-minute inactivity auto-logout ────────────────────────────────────────
_now_ts   = datetime.now()
_idle_sec = (_now_ts - st.session_state.get("last_activity_ts", _now_ts)).total_seconds()
if st.session_state.get("authenticated") and _idle_sec > 7200:
    st.session_state.authenticated    = False
    st.session_state.user_profile     = None
    st.session_state.last_activity_ts = _now_ts
    st.warning("⏱️ Session expired after 2 hours of inactivity. Please log in again.")
    st.rerun()
st.session_state.last_activity_ts = _now_ts   # refresh on every render

# ═══════════════════════════════════════════════════════════════════
# 10. SIDEBAR NAVIGATION
# ═══════════════════════════════════════════════════════════════════
with st.sidebar:
    _sb_profile     = st.session_state.get('user_profile')
    _sb_name        = (
        _sb_profile.get("full_name") or st.session_state.user_email
        if _sb_profile else st.session_state.user_email
    )
    _sb_role        = _sb_profile.get("role") or "Front Desk" if _sb_profile else "Guest"
    # is_admin now comes from rbac.py — same ADMIN_ROLES set that used to
    # live inline here, moved so there's one copy instead of two that can
    # drift apart. rbac.is_admin() reads st.session_state.user_profile
    # directly (sync_session_role() below also populates user_role for
    # code that wants that specific key), so nothing downstream that
    # branches on `is_admin` needed to change — same variable, same
    # values, sourced from one place instead of copy-pasted logic.
    rbac.sync_session_role(supabase)
    is_admin         = rbac.is_admin()
    st.sidebar.markdown(
        f'<div style="background:#f8fafc;padding:1rem;border-radius:0.75rem;'
        f'border:1px solid #e2e8f0;margin-bottom:1.5rem;">'
        f'<div style="font-size:0.75rem;color:#64748b;text-transform:uppercase;'
        f'letter-spacing:0.05em;margin-bottom:0.2rem;">{_sb_role}</div>'
        f'<div style="font-size:0.95rem;font-weight:700;color:#0f172a;word-break:break-all;">'
        f'{_sb_name}</div>'
        f'<div style="font-size:0.8rem;color:#0369a1;margin-top:0.3rem;">Connected Portal</div>'
        f'</div>',
        unsafe_allow_html=True
    )
    # 1. Define Module Access via RBAC
    ops_modules = ["Command Center", "Shop Floor Control", "Production Board"]
    if is_admin:
        ops_modules.insert(1, "Production Layout Builder")

    admin_modules = ["Raise Job Order", "My Order Tracker"]
    if rbac.check_access(rbac.ADMIN_ROLES | rbac.WAREHOUSE_ROLES):
        admin_modules.append("Warehouse")
    if rbac.check_access(rbac.ADMIN_ROLES | rbac.FINANCE_ROLES):
        admin_modules.append("Dispatch")
    if is_admin:
        admin_modules += ["Authorization Center", "Approved Orders Archive"]
    
    # ── Auth Centre pending-count badge (zero extra DB calls — uses TTL cache) ──
    _ac_pending_n  = 0
    _ac_badge_html = ''
    if is_admin and supabase and st.session_state.get("authenticated"):
        try:
            _ac_pending_n  = len(fetch_pending_orders_cached())
            if _ac_pending_n > 0:
                _ac_badge_html = (
                    f'<span class="sidebar-pending-badge">{_ac_pending_n}</span>'
                )
        except Exception:
            _ac_badge_html = ''

    def _nav_item(mod: str, badge_html: str = '') -> None:
        """Render one sidebar nav entry.
        Active route → styled <div> (no click target needed).
        Inactive     → st.button (navigates on click).

        Plain page name only — no icon/monogram prefix. An earlier version
        prefixed a two-letter monogram (CC, WH, etc.), but st.button can't
        host a styled HTML badge, so on inactive items that monogram
        rendered as literal text glued to the label ("WH Warehouse"), and
        even the styled active-item badge was visual clutter next to a
        name that's already self-explanatory. Dropped entirely rather
        than half-fixed.
        """
        if st.session_state.app_mode == mod:
            st.markdown(
                f'<span class="sidebar-active-nav">{mod}{badge_html}</span>',
                unsafe_allow_html=True,
            )
        else:
            # Inject the numeric count into the button label as plain text
            _btn_suffix = f"  ({_ac_pending_n})" if badge_html else ""
            if st.button(f"{mod}{_btn_suffix}", key=f"side_{mod}"):
                st.session_state.app_mode = mod
                st.rerun()

    st.markdown("<div class='sidebar-section-header'>Plant Operations</div>",
                unsafe_allow_html=True)
    for mod in ops_modules:
        _nav_item(mod)
    st.markdown("<div class='sidebar-section-header'>Administrative Portal</div>",
                unsafe_allow_html=True)
    for mod in admin_modules:
        _nav_item(mod, _ac_badge_html if mod == "Authorization Center" else '')
    # ── Global order search ───────────────────────────────────────────────
    st.markdown("<div class='sidebar-section-header'>Global Search</div>",
                unsafe_allow_html=True)
    _gs_input = st.text_input(
        "Global search",
        value=st.session_state.global_search_q,
        placeholder="Order No · Customer…",
        key="sidebar_global_search",
        label_visibility="collapsed",
    )
    if _gs_input != st.session_state.global_search_q:
        st.session_state.global_search_q = _gs_input
        if _gs_input.strip():
            st.session_state.app_mode = "Search Results"
        st.rerun()
    if st.button("Logout", key="btn_logout", type="primary"):
        st.session_state.authenticated    = False
        st.session_state.user_profile     = None
        st.session_state.global_search_q  = ""
        st.rerun()
    st.markdown(
        '<div style="margin-top:2.5rem;text-align:center;font-size:0.7rem;'
        'color:#94a3b8;letter-spacing:0.04em;">Version Aleph</div>',
        unsafe_allow_html=True,
    )

st.markdown('<div class="main-title">Appointed Time Printing Ltd.</div>', unsafe_allow_html=True)
st.markdown('<div class="main-subtitle">Secured Capacity Planning Engine</div>', unsafe_allow_html=True)
app_mode = st.session_state.app_mode

if app_mode != "Raise Job Order" and st.session_state.get("resubmit_order_data") is not None:
    st.session_state.resubmit_order_data  = None
    st.session_state.resubmit_active_dept = None

# ═══════════════════════════════════════════════════════════════════
# ROUTE 1: COMMAND CENTER  (dept-aware)
# ═══════════════════════════════════════════════════════════════════
if app_mode == "Command Center":
    df = get_db_jobs()
    # ── Cached fetch — 60 s TTL, no full-table scan on every rerun ──────
    approved_orders_df = (
        get_approved_orders_cached()
        if supabase and st.session_state.get("authenticated")
        else pd.DataFrame()
    )

    # ── Vectorised dept masks computed once, reused everywhere ──────────
    if not approved_orders_df.empty:
        _cc_gmt_mask  = approved_orders_df.apply(_is_garment, axis=1)
        _cc_press_df  = approved_orders_df[~_cc_gmt_mask]
        _cc_gmt_df    = approved_orders_df[_cc_gmt_mask]
        _cc_total_val = approved_orders_df['total_amount'].fillna(0).apply(lambda x: float(x or 0)).sum()
        _cc_dep_val   = approved_orders_df['deposit_amount'].fillna(0).apply(lambda x: float(x or 0)).sum()
        _cc_balance   = _cc_total_val - _cc_dep_val
    else:
        _cc_press_df = _cc_gmt_df = pd.DataFrame()
        _cc_total_val = _cc_dep_val = _cc_balance = 0.0

    # ── KPI ROW 1 — Order counts ─────────────────────────────────────────
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1:
        active_count = approved_orders_df['job_order_no'].nunique() if not approved_orders_df.empty else 0
        st.markdown(
            f'<div class="metric-card"><div class="metric-label">Active Orders (All)</div>'
            f'<div class="metric-value">{active_count}</div></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(
            f'<div class="metric-card"><div class="metric-label">Contract Value</div>'
            f'<div class="metric-value" style="font-size:1.35rem;">{CURRENCY}{_cc_total_val:,.2f}</div></div>',
            unsafe_allow_html=True)
    with c3:
        press_count = _cc_press_df['job_order_no'].nunique() if not _cc_press_df.empty else 0
        st.markdown(
            f'<div class="metric-card" style="border-bottom-color:#0369a1;">'
            f'<div class="metric-label">Press Orders</div>'
            f'<div class="metric-value" style="color:#0369a1;">{press_count}</div></div>',
            unsafe_allow_html=True)
    with c4:
        gmt_count = _cc_gmt_df['job_order_no'].nunique() if not _cc_gmt_df.empty else 0
        st.markdown(
            f'<div class="metric-card" style="border-bottom-color:#d97706;">'
            f'<div class="metric-label">Garment Orders</div>'
            f'<div class="metric-value" style="color:#d97706;">{gmt_count}</div></div>',
            unsafe_allow_html=True)
    with c5:
        books = df[df['ups'] == 1]['tracking_id'].nunique() if not df.empty else 0
        st.markdown(
            f'<div class="metric-card"><div class="metric-label">Book Runs Queue</div>'
            f'<div class="metric-value">{books}</div></div>', unsafe_allow_html=True)
    with c6:
        skillets = df[df['ups'] > 1]['tracking_id'].nunique() if not df.empty else 0
        st.markdown(
            f'<div class="metric-card"><div class="metric-label">Packaging Skillets</div>'
            f'<div class="metric-value">{skillets}</div></div>', unsafe_allow_html=True)

    # ── KPI ROW 2 — Financial summary (NEW: Outstanding Receivables) ─────
    st.markdown("<div style='height:0.6rem;'></div>", unsafe_allow_html=True)
    _fa, _fb, _fc = st.columns(3)
    with _fa:
        st.markdown(
            f'<div class="metric-card" style="border-bottom-color:#0f172a;">'
            f'<div class="metric-label">Total Pipeline Value</div>'
            f'<div class="metric-value" style="font-size:1.35rem;">{CURRENCY}{_cc_total_val:,.2f}</div></div>',
            unsafe_allow_html=True)
    with _fb:
        st.markdown(
            f'<div class="metric-card" style="border-bottom-color:#10b981;">'
            f'<div class="metric-label">Deposits Collected</div>'
            f'<div class="metric-value" style="font-size:1.35rem;color:#059669;">{CURRENCY}{_cc_dep_val:,.2f}</div></div>',
            unsafe_allow_html=True)
    with _fc:
        _bal_color = "#ef4444" if _cc_balance > 0 else "#10b981"
        st.markdown(
            f'<div class="metric-card" style="border-bottom-color:{_bal_color};">'
            f'<div class="metric-label">Outstanding Receivables</div>'
            f'<div class="metric-value" style="font-size:1.35rem;color:{_bal_color};">{CURRENCY}{_cc_balance:,.2f}</div></div>',
            unsafe_allow_html=True)

    # ── Trend — jobs raised, revenue, and collections over time ──────────
    # Everything above this line is a live snapshot: "what's true right
    # now." That answers "how are we doing today" but not "how did last
    # month compare to this one" once a reporting cycle has passed —
    # this section is that missing view, and it's built on a date-bounded
    # query (see get_orders_trend_cached), not the same "fetch everything
    # matching a status" pattern the snapshot above uses, so it keeps
    # performing the same regardless of how many years of orders exist.
    st.markdown(
        '<div class="section-header" style="margin-top:2rem;">'
        'Trend — Jobs, Revenue &amp; Collections</div>', unsafe_allow_html=True)
    _tr_period = st.radio(
        "Trend period", ["Weekly", "Monthly"], horizontal=True,
        key="cc_trend_period", label_visibility="collapsed",
    )
    _tr_lookback_days = 180 if _tr_period == "Weekly" else 365
    _tr_df = get_orders_trend_cached(days_back=_tr_lookback_days)
    if _tr_df.empty:
        st.info(f"No orders raised in the last {_tr_lookback_days} days yet.")
    else:
        _tr_df['created_at'] = pd.to_datetime(_tr_df['created_at'], utc=True, errors='coerce')
        _tr_df = _tr_df.dropna(subset=['created_at'])
        _tr_df['total_amount']   = _tr_df['total_amount'].fillna(0).apply(lambda x: float(x or 0))
        _tr_df['deposit_amount'] = _tr_df['deposit_amount'].fillna(0).apply(lambda x: float(x or 0))
        _tr_df['_period'] = (
            _tr_df['created_at'].dt.to_period('W').apply(lambda p: p.start_time)
            if _tr_period == "Weekly" else
            _tr_df['created_at'].dt.to_period('M').apply(lambda p: p.start_time)
        )
        _tr_grouped = (
            _tr_df.groupby('_period')
            .agg(jobs=('job_order_no', 'nunique'),
                 revenue=('total_amount', 'sum'),
                 collections=('deposit_amount', 'sum'))
            .reset_index()
            .sort_values('_period')
        )
        _tr_left, _tr_right = st.columns([3, 2])
        with _tr_left:
            _tr_money_fig = px.bar(
                _tr_grouped, x='_period', y=['revenue', 'collections'], barmode='group',
                labels={'_period': _tr_period, 'value': CURRENCY, 'variable': ''},
                color_discrete_map={'revenue': '#0369a1', 'collections': '#10b981'},
            )
            _tr_money_fig.update_layout(
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                margin=dict(t=10, b=10, l=10, r=10), legend_title_text='',
                legend=dict(orientation='h', yanchor='bottom', y=1.02),
            )
            st.plotly_chart(_tr_money_fig, use_container_width=True)
        with _tr_right:
            _tr_jobs_fig = px.line(
                _tr_grouped, x='_period', y='jobs', markers=True,
                labels={'_period': _tr_period, 'jobs': 'Jobs Raised'},
            )
            _tr_jobs_fig.update_traces(line_color='#0f172a')
            _tr_jobs_fig.update_layout(
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                margin=dict(t=10, b=10, l=10, r=10),
            )
            st.plotly_chart(_tr_jobs_fig, use_container_width=True)

    # ── Charts ───────────────────────────────────────────────────────────
    if not df.empty:
        df['start_time'] = pd.to_datetime(df['start_time'], utc=True, format='mixed', errors='coerce')
        st.markdown(
            '<div class="section-header" style="margin-top:2rem;">'
            'Strategic Capacity Distribution & Revenue</div>', unsafe_allow_html=True)
        left, right = st.columns([2, 1])
        with left:
            load_df  = df.groupby('machine').size().reset_index(name='Allocated Components')
            fig_load = px.bar(load_df, x='machine', y='Allocated Components',
                              color='Allocated Components', color_continuous_scale='Blues')
            fig_load.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                                   showlegend=False, margin=dict(t=10, b=10, l=10, r=10))
            st.plotly_chart(fig_load, use_container_width=True)
        with right:
            rev_df  = df.groupby('job_name')['contract_value'].sum().reset_index()
            fig_rev = px.pie(rev_df, values='contract_value', names='job_name',
                             hole=0.6, color_discrete_sequence=px.colors.qualitative.Pastel)
            fig_rev.update_layout(margin=dict(t=10, b=10, l=10, r=10),
                                  legend=dict(orientation="h", y=-0.1))
            st.plotly_chart(fig_rev, use_container_width=True)

    # ── Time-series: Daily contract-value intake (rolling history) ───────
    if not approved_orders_df.empty and 'created_at' in approved_orders_df.columns:
        _ts = approved_orders_df.copy()
        _ts['created_at'] = pd.to_datetime(_ts['created_at'], utc=True, errors='coerce')
        _ts = _ts.dropna(subset=['created_at'])
        _ts['_date'] = _ts['created_at'].dt.date
        _daily = (
            _ts.groupby('_date')['total_amount']
            .sum().reset_index()
            .rename(columns={'_date': 'Date', 'total_amount': 'Contract Value'})
        )
        _daily['Contract Value'] = _daily['Contract Value'].apply(lambda x: float(x or 0))
        if len(_daily) > 1:
            st.markdown(
                '<div class="section-header" style="margin-top:1.5rem;">'
                'Order Intake Trend — Daily Contract Value</div>', unsafe_allow_html=True)
            _fig_trend = px.area(
                _daily, x='Date', y='Contract Value',
                color_discrete_sequence=['#0369a1'],
                labels={'Contract Value': f'Contract Value ({CURRENCY})'},
            )
            _fig_trend.update_traces(
                fill='tozeroy', line=dict(width=2.5),
                fillcolor='rgba(3,105,161,0.12)',
            )
            _fig_trend.update_layout(
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                margin=dict(t=10, b=10, l=10, r=10),
                yaxis_tickprefix=f'{CURRENCY} ', yaxis_tickformat=',.0f',
                xaxis_showgrid=False, yaxis_showgrid=True,
                yaxis_gridcolor='#f1f5f9',
            )
            st.plotly_chart(_fig_trend, use_container_width=True)

    # ── Department breakdown table — formatted with column_config ────────
    if not approved_orders_df.empty:
        st.markdown(
            '<div class="section-header" style="margin-top:1.5rem;">'
            'Department Breakdown — Approved Jobs</div>', unsafe_allow_html=True)
        _ao = approved_orders_df.copy()
        _ao['_dept']    = _ao.apply(lambda r: 'GARMENT' if _is_garment(r) else 'PRESS', axis=1)
        _ao['_balance'] = (
            _ao['total_amount'].fillna(0).apply(lambda x: float(x or 0))
            - _ao['deposit_amount'].fillna(0).apply(lambda x: float(x or 0))
        )

        _tab_press, _tab_gmt = st.tabs(["PRESS Jobs", "GARMENT Jobs"])

        def _pipeline_table(subset_df, dept_label):
            if subset_df.empty:
                st.info(f"No approved {dept_label} orders in the pipeline.")
                return
            _view = pd.DataFrame({
                "Order No":       subset_df["job_order_no"],
                "Customer":       subset_df["customer_name"],
                "Qty":            subset_df["qty_to_print"].fillna(0).apply(lambda x: int(x or 0)),
                "Type":           subset_df["type_of_print"].combine_first(
                                      subset_df.get("print_type", pd.Series(dtype=str))),
                "Total (GH₵)":   subset_df["total_amount"].fillna(0).apply(lambda x: float(x or 0)),
                "Deposit (GH₵)": subset_df["deposit_amount"].fillna(0).apply(lambda x: float(x or 0)),
                "Balance (GH₵)": subset_df["_balance"],
                "Auth By":        subset_df["approved_by"],
            })
            st.dataframe(
                _view,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Total (GH₵)":   st.column_config.NumberColumn(format="GH₵ %,.2f"),
                    "Deposit (GH₵)": st.column_config.NumberColumn(format="GH₵ %,.2f"),
                    "Balance (GH₵)": st.column_config.NumberColumn(format="GH₵ %,.2f"),
                    "Qty":           st.column_config.NumberColumn(format="%,d"),
                },
            )
            # C9: CSV export per department tab
            _csv_bytes = _view.to_csv(index=False).encode('utf-8')
            st.download_button(
                label=f"⬇️ Download {dept_label} Pipeline CSV",
                data=_csv_bytes,
                file_name=f"ATP_{dept_label}_pipeline_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                key=f"dl_csv_{dept_label}",
                use_container_width=True,
            )

        with _tab_press:
            _pipeline_table(_ao[_ao['_dept'] == 'PRESS'], "PRESS")
        with _tab_gmt:
            _pipeline_table(_ao[_ao['_dept'] == 'GARMENT'], "GARMENT")

    # ── C8a: Overdue collection & balance alerts ─────────────────────────────
    if not approved_orders_df.empty and 'date_of_collection' in approved_orders_df.columns:
        _today_cc = datetime.now().date()
        _ov_df    = approved_orders_df.copy()
        _ov_df['_cdate'] = pd.to_datetime(_ov_df['date_of_collection'], errors='coerce').dt.date
        _ov_df['_dleft'] = _ov_df['_cdate'].apply(
            lambda d: (d - _today_cc).days if pd.notna(d) else None)
        _ov_df['_bal']   = (
            _ov_df['total_amount'].fillna(0).apply(lambda x: float(x or 0))
            - _ov_df['deposit_amount'].fillna(0).apply(lambda x: float(x or 0))
        )
        _overdue_rows  = _ov_df[(_ov_df['_dleft'].notna()) & (_ov_df['_dleft'] < 0)  & (_ov_df['_bal'] > 0)]
        _duesoon_rows  = _ov_df[(_ov_df['_dleft'].notna()) & (_ov_df['_dleft'].between(0, 3)) & (_ov_df['_bal'] > 0)]
        if not _overdue_rows.empty or not _duesoon_rows.empty:
            st.markdown(
                '<div class="section-header" style="margin-top:1.75rem;">Collection & Balance Alerts</div>',
                unsafe_allow_html=True)
        for _, _ov in _overdue_rows.iterrows():
            _da = abs(int(_ov['_dleft']))
            st.markdown(
                f'<div style="background:#fef2f2;border:1px solid #fca5a5;border-left:5px solid #ef4444;'
                f'border-radius:8px;padding:0.75rem 1.1rem;margin-bottom:0.5rem;display:flex;'
                f'justify-content:space-between;align-items:center;">'
                f'<div><span style="font-size:0.7rem;font-weight:700;color:#b91c1c;text-transform:uppercase;'
                f'letter-spacing:0.05em;">OVERDUE — {_da} DAY(S)</span><br>'
                f'<strong style="color:#0f172a;">{_ov.get("customer_name","—")}</strong>'
                f'<span style="color:#64748b;font-size:0.85rem;"> · {_ov.get("job_order_no","—")}</span></div>'
                f'<div style="text-align:right;font-weight:700;color:#ef4444;">'
                f'{CURRENCY} {_ov["_bal"]:,.2f} outstanding</div></div>',
                unsafe_allow_html=True)
            _nk = f"notif_coll_{_ov.get('id','')}"
            if _nk not in st.session_state:
                notify_collection_due(_ov.to_dict(), int(_ov['_dleft']))
                st.session_state[_nk] = True
        for _, _ds in _duesoon_rows.iterrows():
            st.markdown(
                f'<div style="background:#fffbeb;border:1px solid #fde68a;border-left:5px solid #f59e0b;'
                f'border-radius:8px;padding:0.75rem 1.1rem;margin-bottom:0.5rem;display:flex;'
                f'justify-content:space-between;align-items:center;">'
                f'<div><span style="font-size:0.7rem;font-weight:700;color:#b45309;text-transform:uppercase;'
                f'letter-spacing:0.05em;">DUE IN {int(_ds["_dleft"])} DAY(S)</span><br>'
                f'<strong style="color:#0f172a;">{_ds.get("customer_name","—")}</strong>'
                f'<span style="color:#64748b;font-size:0.85rem;"> · {_ds.get("job_order_no","—")}</span></div>'
                f'<div style="text-align:right;font-weight:700;color:#d97706;">'
                f'{CURRENCY} {_ds["_bal"]:,.2f} outstanding</div></div>',
                unsafe_allow_html=True)

    # ── C8b: Extended analytics row ──────────────────────────────────────────
    if not approved_orders_df.empty:
        st.markdown(
            '<div class="section-header" style="margin-top:2rem;">Extended Analytics</div>',
            unsafe_allow_html=True)
        _ea1, _ea2, _ea3 = st.columns(3)
        _avg_oval = approved_orders_df['total_amount'].fillna(0).apply(lambda x: float(x or 0)).mean()
        with _ea1:
            st.markdown(
                f'<div class="metric-card"><div class="metric-label">Avg Order Value</div>'
                f'<div class="metric-value" style="font-size:1.35rem;">{CURRENCY}{_avg_oval:,.2f}</div></div>',
                unsafe_allow_html=True)
        _rej_rate = 0.0
        try:
            _all_j = get_db_job_orders_multi_status(
                ["Pending Approval","Pending Revision Approval","Approved","Rejected"])
            _tot_s = max(len(_all_j), 1) if not _all_j.empty else 1
            _rej_n = int((_all_j['status'] == 'Rejected').sum()) if not _all_j.empty else 0
            _rej_rate = (_rej_n / _tot_s) * 100
        except Exception:
            pass
        with _ea2:
            _rc2 = "#ef4444" if _rej_rate > 20 else ("#f59e0b" if _rej_rate > 10 else "#10b981")
            st.markdown(
                f'<div class="metric-card" style="border-bottom-color:{_rc2};">'
                f'<div class="metric-label">Rejection Rate</div>'
                f'<div class="metric-value" style="font-size:1.6rem;color:{_rc2};">{_rej_rate:.1f}%</div></div>',
                unsafe_allow_html=True)
        _zero_dep = int((approved_orders_df['deposit_amount'].fillna(0)
                         .apply(lambda x: float(x or 0)) == 0).sum())
        with _ea3:
            st.markdown(
                f'<div class="metric-card" style="border-bottom-color:#f59e0b;">'
                f'<div class="metric-label">Zero-Deposit Orders</div>'
                f'<div class="metric-value" style="font-size:1.6rem;color:#d97706;">{_zero_dep}</div></div>',
                unsafe_allow_html=True)

        # C8c: Monthly revenue bar chart
        if 'created_at' in approved_orders_df.columns:
            _mo = approved_orders_df.copy()
            _mo['created_at'] = pd.to_datetime(_mo['created_at'], utc=True, errors='coerce')
            _mo = _mo.dropna(subset=['created_at'])
            _mo['_month'] = _mo['created_at'].dt.to_period('M').astype(str)
            _monthly = (_mo.groupby('_month')['total_amount'].sum().reset_index()
                          .rename(columns={'_month':'Month','total_amount':'Revenue'}))
            _monthly['Revenue'] = _monthly['Revenue'].apply(lambda x: float(x or 0))
            if len(_monthly) > 0:
                st.markdown(
                    '<div class="section-header" style="margin-top:1.5rem;">Monthly Revenue — Approved Orders</div>',
                    unsafe_allow_html=True)
                _fig_mo = px.bar(_monthly, x='Month', y='Revenue',
                                 color='Revenue', color_continuous_scale='Blues',
                                 labels={'Revenue': f'Revenue ({CURRENCY})'})
                _fig_mo.update_layout(
                    plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                    margin=dict(t=10,b=10,l=10,r=10), showlegend=False,
                    yaxis_tickprefix=f'{CURRENCY} ', yaxis_tickformat=',.0f',
                    xaxis_showgrid=False, yaxis_showgrid=True, yaxis_gridcolor='#f1f5f9')
                st.plotly_chart(_fig_mo, use_container_width=True)

        # C8d: Top 5 customers table
        _top5 = (approved_orders_df.groupby('customer_name')['total_amount']
                                   .sum().reset_index()
                                   .rename(columns={'customer_name':'Customer','total_amount':'Total Value'})
                                   .sort_values('Total Value', ascending=False).head(5))
        _top5['Total Value'] = _top5['Total Value'].apply(lambda x: float(x or 0))
        if not _top5.empty:
            st.markdown(
                '<div class="section-header" style="margin-top:1.5rem;">Top 5 Customers — Contract Value</div>',
                unsafe_allow_html=True)
            st.dataframe(
                _top5, use_container_width=True, hide_index=True,
                column_config={
                    'Total Value': st.column_config.NumberColumn(
                        f'Total Value ({CURRENCY})', format=f'{CURRENCY} %,.2f')
                })

    # ── C8e: Recent activity feed ─────────────────────────────────────────────
    _act_df = pd.DataFrame()
    try:
        _act_res = (
            supabase.table('job_orders')
            .select('job_order_no,customer_name,status,approved_by,created_by,updated_at,total_amount')
            .order('updated_at', desc=True).limit(15).execute()
        )
        if _act_res.data:
            _act_df = pd.DataFrame(_act_res.data)
    except Exception:
        pass
    if not _act_df.empty:
        st.markdown(
            '<div class="section-header" style="margin-top:2rem;">Recent Activity Feed</div>',
            unsafe_allow_html=True)
        _SICONS = {
            'Approved':'✅','Rejected':'❌','Pending Approval':'⏳',
            'Pending Revision Approval':'🔄','In Production':'⚙️',
            'Ready for Collection':'📦','Delivered':'🎯',
        }
        for _, _ar in _act_df.iterrows():
            _a_st  = str(_ar.get('status','') or '')
            _a_ico = _SICONS.get(_a_st, '•')
            _a_by  = _ar.get('approved_by') or _ar.get('created_by') or '—'
            _a_val = float(_ar.get('total_amount',0) or 0)
            try:
                _a_ts = pd.to_datetime(_ar.get('updated_at','')).strftime('%d %b  %H:%M')
            except Exception:
                _a_ts = str(_ar.get('updated_at',''))[:16]
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;align-items:center;'
                f'padding:0.6rem 0.9rem;border-radius:8px;margin-bottom:4px;background:#f8fafc;'
                f'border:1px solid #f1f5f9;">'
                f'<div style="display:flex;align-items:center;gap:0.75rem;">'
                f'<span style="font-size:1rem;">{_a_ico}</span>'
                f'<div><div style="font-size:0.82rem;font-weight:700;color:#0f172a;">'
                f'{_ar.get("job_order_no","—")} — {_ar.get("customer_name","—")}</div>'
                f'<div style="font-size:0.72rem;color:#64748b;">{_a_st} · {_a_by}</div></div></div>'
                f'<div style="text-align:right;">'
                f'<div style="font-size:0.8rem;font-weight:600;color:#0369a1;">{CURRENCY}{_a_val:,.0f}</div>'
                f'<div style="font-size:0.7rem;color:#94a3b8;">{_a_ts}</div></div></div>',
                unsafe_allow_html=True)
    else:
        st.info("No active machine runs detected. Schedule jobs via the Production Layout Builder.")

# ═══════════════════════════════════════════════════════════════════
# ROUTE 2: RAISE JOB ORDER — DEPARTMENT-FORKED CART INTERFACE
# ═══════════════════════════════════════════════════════════════════
elif app_mode == "Raise Job Order":
    resubmit_data = st.session_state.get("resubmit_order_data")

    # ── RESUBMIT MODE ───────────────────────────────────────────────
    if resubmit_data:
        st.markdown('<div class="section-header">Modify &amp; Resubmit Rejected Order</div>',
                    unsafe_allow_html=True)
        st.markdown(
            f'<div style="background:linear-gradient(135deg,#fef2f2,#ffe4e6);'
            f'border:1px solid #fca5a5;border-radius:10px;padding:1rem 1.25rem;margin-bottom:1.5rem;">'
            f'<div style="font-size:0.75rem;font-weight:700;color:#b91c1c;text-transform:uppercase;'
            f'letter-spacing:0.05em;margin-bottom:0.25rem;">Resubmission Mode Active</div>'
            f'<div style="font-size:0.9rem;color:#7f1d1d;">You are correcting and resubmitting '
            f'<strong>{resubmit_data.get("job_order_no","this order")}</strong> for '
            f'<strong>{resubmit_data.get("customer_name","")}</strong>. '
            f'All fields are pre-loaded. Make your corrections then click RESUBMIT.</div>'
            f'</div>', unsafe_allow_html=True)

        def _rd(key, default=""):
            return resubmit_data.get(key, default) if resubmit_data else default
        def _rdf(key, default=0.0):
            return float(resubmit_data.get(key, default) or default) if resubmit_data else default
        def _rdi(key, default=0):
            return int(resubmit_data.get(key, default) or default) if resubmit_data else default
        def _rdd(key, default=None):
            raw = resubmit_data.get(key) if resubmit_data else None
            if isinstance(raw, datetime):
                return raw.date()
            if raw:
                try:
                    return datetime.fromisoformat(str(raw)).date()
                except (ValueError, TypeError):
                    pass
            return default or datetime.now().date()
        def _rdl(key, opts):
            raw = _rd(key)
            if not raw or raw == "None":
                return []
            return [p.strip() for p in raw.split(",") if p.strip() in opts]

        _resub_dept = resubmit_data.get("department", "PRESS")
 
        if _resub_dept == "GARMENT":
 
            # ── GARMENT RESUBMIT FORM ────────────────────────────────────
            with st.form("resubmit_garment_form", clear_on_submit=False):
 
                # ── Client Identity ──────────────────────────────────────
                st.markdown('<div class="form-group-header">Client Identity & Contract Outline</div>',
                            unsafe_allow_html=True)
                _rg1, _rg2 = st.columns(2)
                rg_c_name  = _rg1.text_input("Customer Name ★",    value=_rd("customer_name"))
                rg_c_phone = _rg2.text_input("Telephone Number ★", value=_rd("telephone_number"))
 
                rg_j_desc  = st.text_area("Job / Item Description ★", value=_rd("job_description"))
 
                # ── Financial & Scheduling ───────────────────────────────
                st.markdown('<div class="form-group-header">Financial Ledgers & Scheduling</div>',
                            unsafe_allow_html=True)
                _rgf1, _rgf2, _rgf3, _rgf4 = st.columns(4)
                rg_t_amt  = _rgf1.number_input("Total Item Amount (GHS) ★", min_value=0.0,
                                                step=100.0, value=_rdf("total_amount"))
                rg_d_amt  = _rgf2.number_input("Deposit Paid (GHS)",         min_value=0.0,
                                                step=100.0, value=_rdf("deposit_amount"))
                rg_b_due  = _rgf3.date_input("Balance Deadline ★", value=_rdd("balance_due_date"))
                rg_c_date = _rgf4.date_input("Collection Date ★",  value=_rdd("date_of_collection"))
                rg_receipt_no = st.text_input(
                    "Receipt Number (required if a deposit is entered)",
                    value=_rd("receipt_no"), placeholder="e.g. RCT-00123")

                st.markdown('<div class="form-group-header">Attachments &amp; Terms</div>',
                            unsafe_allow_html=True)
                _rga1, _rga2 = st.columns(2)
                rg_lpo_file = _rga1.file_uploader(
                    "Upload LPO (optional) — goes to MD/FM", type=["pdf", "jpg", "jpeg", "png"],
                    key="rg_resubmit_lpo")
                rg_sample_file = _rga2.file_uploader(
                    "Upload Sample Photo (optional) — goes to the department", type=["pdf", "jpg", "jpeg", "png"],
                    key="rg_resubmit_sample")
                _rgsa1, _rgsa2 = st.columns(2)
                rg_sample_attached = _rgsa1.selectbox(
                    "Sample Attached?", ["No", "Yes"],
                    index=1 if _rd("sample_attached") == "Yes" else 0, key="rg_resubmit_sample_attached")
                rg_sample_with = _rgsa2.text_input(
                    "Sample With (required if Yes)", value=_rd("sample_with"), key="rg_resubmit_sample_with")
                rg_30day = st.checkbox(
                    "30-Day Credit Terms job",
                    value="30-Day Credit Terms" in _rd("payment_terms"), key="rg_resubmit_30day")
                rg_terms_notes = ""
                if rg_t_amt != rg_d_amt:
                    _rg_existing_terms = _rd("payment_terms")
                    _rg_existing_notes = _rg_existing_terms.split("|", 1)[1].strip() if "|" in _rg_existing_terms else (
                        _rg_existing_terms if "30-Day Credit Terms" not in _rg_existing_terms else "")
                    rg_terms_notes = st.text_area(
                        "Payment Terms Notes — not fully paid; explain the arrangement for MD/FM",
                        value=_rg_existing_notes, key="rg_resubmit_terms_notes")
 
                # ── Quantity & Material Source ───────────────────────────
                st.markdown('<div class="form-group-header">Production Quantity & Sourcing</div>',
                            unsafe_allow_html=True)
                _rgq1, _rgq2 = st.columns(2)
                rg_qty = _rgq1.number_input("Quantity to Print ★", min_value=0, step=10,
                                             value=_rdi("qty_to_print"))
 
                _rgmat_opts  = ["", "Company Material", "Customer Material"]
                _rgmat_exist = _rd("material_source")
                _rgmat_idx   = _rgmat_opts.index(_rgmat_exist) if _rgmat_exist in _rgmat_opts else 0
                rg_mat_source = _rgq2.selectbox("Material Source ★", _rgmat_opts, index=_rgmat_idx)
 
                # ── Print Type & Dimensions ──────────────────────────────
                st.markdown('<div class="form-group-header">Print Type & Dimensions</div>',
                            unsafe_allow_html=True)
                _rgpt1, _rgpt2 = st.columns(2)
 
                _rgpt_opts  = ["", "DTF", "Flexi Screen Print", "UV-DTF", "SAV", "Embroidery"]
                _rgpt_exist = _rd("print_type") or _rd("type_of_print")
                _rgpt_idx   = _rgpt_opts.index(_rgpt_exist) if _rgpt_exist in _rgpt_opts else 0
                rg_print_type = _rgpt1.selectbox("Print Type ★", _rgpt_opts, index=_rgpt_idx)
 
                _rgdel_opts  = ["Company Delivery", "Customer Pick-up"]
                _rgdel_exist = _rd("delivery_mode")
                _rgdel_idx   = _rgdel_opts.index(_rgdel_exist) if _rgdel_exist in _rgdel_opts else 0
                rg_delivery  = _rgpt2.selectbox("Delivery Mode ★", _rgdel_opts, index=_rgdel_idx)
 
                _rgps1, _rgps2 = st.columns(2)
 
                _rgps_opts  = ["", "A1", "A2", "A3", "A4", "A5", "A6"]
                _rgps_exist = _rd("print_size")
                _rgps_idx   = _rgps_opts.index(_rgps_exist) if _rgps_exist in _rgps_opts else 0
                rg_print_size = _rgps1.selectbox("Print Size", _rgps_opts, index=_rgps_idx)
 
                _rgfs_opts  = ["", "A1", "A2", "A3", "A4", "A5", "A6",
                               "1YRD", "2YRDs", "3YRDs", "4YRDs", "5YRDs", "6YRDs",
                               "3FTx4FT", "4FTx8FT"]
                _rgfs_exist = _rd("finished_print_size")
                _rgfs_idx   = _rgfs_opts.index(_rgfs_exist) if _rgfs_exist in _rgfs_opts else 0
                rg_fin_size = _rgps2.selectbox("Finished Print Size / Yardage", _rgfs_opts,
                                                index=_rgfs_idx)
 
                # ── Material Description ─────────────────────────────────
                st.markdown('<div class="form-group-header">Material Description</div>',
                            unsafe_allow_html=True)
                rg_mat_desc = st.text_area(
                    "Material Description (fabric type, colour, etc.)",
                    value=_rd("material_description"),
                    placeholder="e.g. Cotton Jersey White, Polyester Red..."
                )
                rg_add_comments = st.text_area(
                    "Additional Comments / Specifications",
                    value=_rd("additional_comments"),
                    placeholder="Any other technical requirements..."
                )
 
                # ── Packaging & Delivery ─────────────────────────────────
                st.markdown('<div class="form-group-header">Packaging & Delivery</div>',
                            unsafe_allow_html=True)
                _rgpkg1, _rgpkg2, _rgpkg3 = st.columns(3)
 
                _rgpkg_opts  = ["", "Box Packaging", "Bag Packaging", "None"]
                _rgpkg_exist = _rd("packaging_mode")
                _rgpkg_idx   = _rgpkg_opts.index(_rgpkg_exist) if _rgpkg_exist in _rgpkg_opts else 0
                rg_pkg_mode  = _rgpkg1.selectbox("Packaging Mode", _rgpkg_opts, index=_rgpkg_idx)
 
                rg_qty_pack  = _rgpkg2.number_input("Qty to Pack", min_value=0, step=1,
                                                     value=_rdi("qty_to_pack"))
                rg_pkg_specs = _rgpkg3.text_input("Packaging Specs", value=_rd("packaging_specs"))
 
                _rgloc1, _rgloc2 = st.columns(2)
                rg_location = _rgloc1.text_input("Delivery Location",      value=_rd("delivery_location"))
                rg_contact  = _rgloc2.text_input("Delivery Contact Person", value=_rd("delivery_contact"))
 
                # ── Process / Technical Info ─────────────────────────────
                st.markdown('<div class="form-group-header">Process / Technical Info</div>',
                            unsafe_allow_html=True)
                rg_process_info = st.text_area(
                    "Process / Technical Information",
                    value=_rd("process_info"),
                    placeholder="Stitching count, thread colour, press temperature..."
                )
 
                st.markdown("<br>", unsafe_allow_html=True)
                st.info(f"Handled By: {st.session_state.user_email} | Date: {datetime.now().strftime('%Y-%m-%d')}")
                rg_submit = st.form_submit_button("🔄 RESUBMIT FOR MANAGEMENT APPROVAL",
                                                   use_container_width=True)
 
                if rg_submit:
                    _rg_missing = []
                    if not rg_c_name.strip():    _rg_missing.append("Customer Name")
                    if not rg_c_phone.strip():   _rg_missing.append("Telephone Number")
                    if not rg_j_desc.strip():    _rg_missing.append("Job Description")
                    if rg_t_amt <= 0.0:          _rg_missing.append("Total Item Amount")
                    if rg_qty <= 0:              _rg_missing.append("Quantity to Print")
                    if not rg_print_type:        _rg_missing.append("Print Type")
                    if not rg_mat_source:        _rg_missing.append("Material Source")
                    if rg_d_amt > 0 and not rg_receipt_no.strip():
                        _rg_missing.append("Receipt Number (required since a deposit was entered)")
                    if rg_sample_attached == "Yes" and not rg_sample_with.strip():
                        _rg_missing.append("Sample With (required since a sample is marked attached)")
 
                    if not _rg_missing:
                        _rg_orig_pgid = resubmit_data.get("parent_group_id", None)
                        _rg_upload_pgid = _rg_orig_pgid or f"RGPG-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

                        def _upload_rg_resubmit_file(_f, _label):
                            if _f is None:
                                return None
                            try:
                                _fb = _f.getvalue()
                                _sp = f"{_rg_upload_pgid}/{_f.name}"
                                supabase.storage.from_('job-attachments').upload(
                                    _sp, _fb, {"content-type": _f.type or "application/octet-stream"})
                                return supabase.storage.from_('job-attachments').get_public_url(_sp)
                            except Exception as _rgue:
                                st.warning(f"{_label} upload failed (order will still submit without it): {_rgue}")
                                return None

                        _rg_lpo_url    = _upload_rg_resubmit_file(rg_lpo_file, "LPO")
                        _rg_sample_url = _upload_rg_resubmit_file(rg_sample_file, "Sample photo")
                        _rg_terms_parts = []
                        if rg_30day:
                            _rg_terms_parts.append("30-Day Credit Terms")
                        if rg_t_amt != rg_d_amt and rg_terms_notes.strip():
                            _rg_terms_parts.append(sanitize_string(rg_terms_notes))
                        _rg_final_terms = " | ".join(_rg_terms_parts) if _rg_terms_parts else None

                        # Build material_description_rows for PDF compatibility
                        _rg_mat_rows = []
                        for _rg_ml in rg_mat_desc.strip().splitlines():
                            if _rg_ml.strip():
                                _rg_mat_rows.append({
                                    "material": _rg_ml.strip(),
                                    "sizes": rg_fin_size,
                                    "colour": ""
                                })
                        if not _rg_mat_rows:
                            _rg_mat_rows = [{"material": rg_mat_desc, "sizes": rg_fin_size, "colour": ""}]
 
                        rg_payload = {
                            "customer_name":        sanitize_string(rg_c_name),
                            "telephone_number":     sanitize_string(rg_c_phone),
                            "job_description":      sanitize_string(rg_j_desc),
                            "total_amount":         float(rg_t_amt),
                            "deposit_amount":       float(rg_d_amt),
                            "receipt_no":           sanitize_string(rg_receipt_no) if rg_d_amt > 0 else None,
                            "sample_attached":      rg_sample_attached,
                            "sample_with":          sanitize_string(rg_sample_with) if rg_sample_attached == "Yes" else None,
                            "lpo_file_url":         _rg_lpo_url,
                            "sample_file_url":      _rg_sample_url,
                            "payment_terms":        _rg_final_terms,
                            "balance_due_date":     rg_b_due.isoformat(),
                            "date_of_collection":   rg_c_date.isoformat(),
                            "qty_to_print":         int(rg_qty),
                            "print_type":           rg_print_type,
                            "type_of_print":        rg_print_type,
                            "material_source":      rg_mat_source,
                            "delivery_mode":        rg_delivery,
                            "print_size":           rg_print_size,
                            "finished_print_size":  rg_fin_size,
                            "yardage":              rg_fin_size,
                            "material_description": sanitize_string(rg_mat_desc),
                            "additional_comments":  sanitize_string(rg_add_comments),
                            "packaging_mode":       rg_pkg_mode,
                            "qty_to_pack":          int(rg_qty_pack),
                            "packaging_specs":      sanitize_string(rg_pkg_specs),
                            "delivery_location":    sanitize_string(rg_location),
                            "delivery_contact":     sanitize_string(rg_contact),
                            "process_info":         sanitize_string(rg_process_info),
                            # Press-only fields explicitly null for schema safety
                            "paper_type":   None,
                            "gsm":          None,
                            "paper_size":   None,
                            "paper_colour": None,
                            "impressions_colour": None,
                            "binding_type":    None,
                            "laminating_type": None,
                            # Routing & status
                            "department":  "GARMENT",
                            "status":      "Pending Approval",
                            "created_by":  st.session_state.user_email,
                            "order_date":  datetime.now().strftime("%Y-%m-%d"),
                        }
 
                        if _rg_orig_pgid:
                            rg_payload["parent_group_id"] = _rg_orig_pgid
 
                        try:
                            _rg_res    = supabase.table("job_orders").insert(rg_payload).execute()
                            _rg_gen_no = (
                                _rg_res.data[0].get("job_order_no", f"AT-{random.randint(10000,99999)}")
                                if _rg_res.data else f"AT-{random.randint(10000,99999)}"
                            )
                            rg_payload["job_order_no"] = _rg_gen_no
 
                            st.session_state.last_raised_order        = rg_payload
                            st.session_state.last_raised_batch        = []
                            st.session_state.last_raised_garment_batch = []
                            st.session_state.resubmit_order_data      = None
                            st.session_state.resubmit_active_dept     = None
 
                            send_resend_notification(rg_payload)
                            st.toast("Garment order resubmitted and routed to management authorization queue.",
                                     icon="✅")
                            st.rerun()
 
                        except Exception as _rg_err:
                            st.error(f"Failed to resubmit garment order: {str(_rg_err)}")
 
                    else:
                        st.error(f"Transaction blocked. Missing required fields: {', '.join(_rg_missing)}")
 
        else:
            if resubmit_data:
                st.markdown('<div class="section-header">Modify &amp; Resubmit Rejected Order</div>',
                            unsafe_allow_html=True)
                st.markdown(
                    f'<div style="background:linear-gradient(135deg,#fef2f2,#ffe4e6);'
                    f'border:1px solid #fca5a5;border-radius:10px;padding:1rem 1.25rem;margin-bottom:1.5rem;">'
                    f'<div style="font-size:0.75rem;font-weight:700;color:#b91c1c;text-transform:uppercase;'
                    f'letter-spacing:0.05em;margin-bottom:0.25rem;">Resubmission Mode Active</div>'
                    f'<div style="font-size:0.9rem;color:#7f1d1d;">You are correcting and resubmitting '
                    f'<strong>{resubmit_data.get("job_order_no","this order")}</strong> for '
                    f'<strong>{resubmit_data.get("customer_name","")}</strong>. '
                    f'All fields are pre-loaded. Make your corrections then click RESUBMIT.</div>'
                    f'</div>', unsafe_allow_html=True)

                def _rd(key, default=""):
                    return resubmit_data.get(key, default) if resubmit_data else default
                def _rdf(key, default=0.0):
                    return float(resubmit_data.get(key, default) or default) if resubmit_data else default
                def _rdi(key, default=0):
                    return int(resubmit_data.get(key, default) or default) if resubmit_data else default

                _resub_dept = resubmit_data.get("department", "PRESS")

                def _rdd(key, default=None):
                    raw = resubmit_data.get(key) if resubmit_data else None
                    if isinstance(raw, datetime):
                        return raw.date()
                    if raw:
                        try:
                            return datetime.fromisoformat(str(raw)).date()
                        except (ValueError, TypeError):
                            pass
                    return default or datetime.now().date()
                def _rdl(key, opts):
                    raw = _rd(key)
                    if not raw or raw == "None":
                        return []
                    return [p.strip() for p in raw.split(",") if p.strip() in opts]

                # ── PRESS RESUBMIT FORM ──────────────────────────────────────────
                with st.form("resubmit_press_form", clear_on_submit=False):

                    st.markdown('<div class="form-group-header">Client Identity & Contract Outline</div>',
                                unsafe_allow_html=True)
                    _rp1, _rp2 = st.columns(2)
                    rp_c_name  = _rp1.text_input("Customer Name ★",    value=_rd("customer_name"))
                    rp_c_phone = _rp2.text_input("Telephone Number ★", value=_rd("telephone_number"))

                    rp_j_desc = st.text_area("Item Description ★", value=_rd("job_description"))

                    st.markdown('<div class="form-group-header">Financial Ledgers & Scheduling</div>',
                                unsafe_allow_html=True)
                    _rpf1, _rpf2, _rpf3, _rpf4 = st.columns(4)
                    rp_t_amt  = _rpf1.number_input("Total Item Amount (GHS) ★", min_value=0.0,
                                                    step=100.0, value=_rdf("total_amount"))
                    rp_d_amt  = _rpf2.number_input("Deposit Paid (GHS)",         min_value=0.0,
                                                    step=100.0, value=_rdf("deposit_amount"))
                    rp_b_due  = _rpf3.date_input("Balance Deadline ★", value=_rdd("balance_due_date"))
                    rp_c_date = _rpf4.date_input("Collection Date ★",  value=_rdd("date_of_collection"))
                    rp_receipt_no = st.text_input(
                        "Receipt Number (required if a deposit is entered)",
                        value=_rd("receipt_no"), placeholder="e.g. RCT-00123")

                    st.markdown('<div class="form-group-header">Attachments &amp; Terms</div>',
                                unsafe_allow_html=True)
                    _rpa1, _rpa2 = st.columns(2)
                    rp_lpo_file = _rpa1.file_uploader(
                        "Upload LPO (optional) — goes to MD/FM", type=["pdf", "jpg", "jpeg", "png"],
                        key="rp_resubmit_lpo")
                    rp_sample_file = _rpa2.file_uploader(
                        "Upload Sample Photo (optional) — goes to the department", type=["pdf", "jpg", "jpeg", "png"],
                        key="rp_resubmit_sample")
                    _rpsa1, _rpsa2 = st.columns(2)
                    rp_sample_attached = _rpsa1.selectbox(
                        "Sample Attached?", ["No", "Yes"],
                        index=1 if _rd("sample_attached") == "Yes" else 0, key="rp_resubmit_sample_attached")
                    rp_sample_with = _rpsa2.text_input(
                        "Sample With (required if Yes)", value=_rd("sample_with"), key="rp_resubmit_sample_with")
                    rp_30day = st.checkbox(
                        "30-Day Credit Terms job",
                        value="30-Day Credit Terms" in _rd("payment_terms"), key="rp_resubmit_30day")
                    rp_terms_notes = ""
                    if rp_t_amt != rp_d_amt:
                        _rp_existing_terms = _rd("payment_terms")
                        _rp_existing_notes = _rp_existing_terms.split("|", 1)[1].strip() if "|" in _rp_existing_terms else (
                            _rp_existing_terms if "30-Day Credit Terms" not in _rp_existing_terms else "")
                        rp_terms_notes = st.text_area(
                            "Payment Terms Notes — not fully paid; explain the arrangement for MD/FM",
                            value=_rp_existing_notes, key="rp_resubmit_terms_notes")

                    st.markdown('<div class="form-group-header">Production Quantity & Category</div>',
                                unsafe_allow_html=True)
                    _rpq1, _rpq2, _rpq3 = st.columns(3)
                    rp_qty = _rpq1.number_input("Quantity ★", min_value=0, step=500, value=_rdi("qty_to_print"))

                    _rppc_opts  = ["", "OFFSET", "DIGITAL PRESS", "PACKAGING"]
                    _rppc_exist = _rd("type_of_print")
                    rp_type_print = _rpq2.selectbox(
                        "Print Category ★", _rppc_opts,
                        index=_rppc_opts.index(_rppc_exist) if _rppc_exist in _rppc_opts else 0)

                    _rpmat_opts  = ["", "Customer Material", "Company Material"]
                    _rpmat_exist = _rd("material_source")
                    rp_mat_source = _rpq3.selectbox(
                        "Material Source", _rpmat_opts,
                        index=_rpmat_opts.index(_rpmat_exist) if _rpmat_exist in _rpmat_opts else 0)

                    _rpdel_opts  = ["Company Delivery", "Client Pickup"]
                    _rpdel_exist = _rd("delivery_mode")
                    rp_delivery = st.selectbox(
                        "Delivery Mode", _rpdel_opts,
                        index=_rpdel_opts.index(_rpdel_exist) if _rpdel_exist in _rpdel_opts else 0)

                    st.markdown('<div class="form-group-header">Material & Engineering Specifics</div>',
                                unsafe_allow_html=True)
                    _rpp1, _rpp2, _rpp3, _rpp4 = st.columns(4)
                    rp_p_size   = _rpp1.text_input("Print Size",     value=_rd("print_size"))
                    rp_f_size   = _rpp2.text_input("Finished Size",  value=_rd("finished_print_size"))
                    rp_pap_type = _rpp3.text_input("Paper Material", value=_rd("paper_type"))
                    rp_pap_gsm  = _rpp4.text_input("GSM",            value=_rd("gsm"))
                    _rpx1, _rpx2, _rpx3 = st.columns(3)
                    rp_pap_size = _rpx1.text_input("Paper Size",         value=_rd("paper_size"))
                    rp_pap_col  = _rpx2.text_input("Colour / Ink Specs", value=_rd("paper_colour"))
                    rp_imp_col  = _rpx3.text_input("Impressions",        value=_rd("impressions_colour"))

                    _rpbind_opts = ["Perfect Binding", "Spiral Binding", "Saddle Stitching", "Comb Binding"]
                    rp_b_type = checkbox_multiselect("Binding Selection", _rpbind_opts, "rp_bind",
                                                      default=_rdl("binding_type", _rpbind_opts))
                    _rplam_opts = ["Gloss Laminating", "Matt Laminating", "Soft Touch", "UV-Varnish"]
                    rp_l_type = checkbox_multiselect("Laminating Selection", _rplam_opts, "rp_lam",
                                                      default=_rdl("laminating_type", _rplam_opts))

                    st.info(f"Handled By: {st.session_state.user_email} | Date: {datetime.now().strftime('%Y-%m-%d')}")
                    rp_submit = st.form_submit_button("🔄 RESUBMIT FOR MANAGEMENT APPROVAL", use_container_width=True)

                    if rp_submit:
                        _rp_missing = []
                        if not rp_c_name.strip():  _rp_missing.append("Customer Name")
                        if not rp_c_phone.strip(): _rp_missing.append("Telephone Number")
                        if not rp_j_desc.strip():  _rp_missing.append("Item Description")
                        if rp_t_amt <= 0.0:        _rp_missing.append("Total Item Amount")
                        if rp_qty <= 0:            _rp_missing.append("Quantity")
                        if not rp_type_print:      _rp_missing.append("Print Category")
                        if rp_d_amt > 0 and not rp_receipt_no.strip():
                            _rp_missing.append("Receipt Number (required since a deposit was entered)")
                        if rp_sample_attached == "Yes" and not rp_sample_with.strip():
                            _rp_missing.append("Sample With (required since a sample is marked attached)")

                        if not _rp_missing:
                            _rp_orig_pgid = resubmit_data.get("parent_group_id", None)
                            _rp_upload_pgid = _rp_orig_pgid or f"RPPG-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

                            def _upload_rp_resubmit_file(_f, _label):
                                if _f is None:
                                    return None
                                try:
                                    _fb = _f.getvalue()
                                    _sp = f"{_rp_upload_pgid}/{_f.name}"
                                    supabase.storage.from_('job-attachments').upload(
                                        _sp, _fb, {"content-type": _f.type or "application/octet-stream"})
                                    return supabase.storage.from_('job-attachments').get_public_url(_sp)
                                except Exception as _rpue:
                                    st.warning(f"{_label} upload failed (order will still submit without it): {_rpue}")
                                    return None

                            _rp_lpo_url    = _upload_rp_resubmit_file(rp_lpo_file, "LPO")
                            _rp_sample_url = _upload_rp_resubmit_file(rp_sample_file, "Sample photo")
                            _rp_terms_parts = []
                            if rp_30day:
                                _rp_terms_parts.append("30-Day Credit Terms")
                            if rp_t_amt != rp_d_amt and rp_terms_notes.strip():
                                _rp_terms_parts.append(sanitize_string(rp_terms_notes))
                            _rp_final_terms = " | ".join(_rp_terms_parts) if _rp_terms_parts else None

                            rp_payload = {
                                "customer_name":       sanitize_string(rp_c_name),
                                "telephone_number":    sanitize_string(rp_c_phone),
                                "job_description":     sanitize_string(rp_j_desc),
                                "total_amount":        float(rp_t_amt),
                                "deposit_amount":      float(rp_d_amt),
                                "receipt_no":          sanitize_string(rp_receipt_no) if rp_d_amt > 0 else None,
                                "sample_attached":     rp_sample_attached,
                                "sample_with":         sanitize_string(rp_sample_with) if rp_sample_attached == "Yes" else None,
                                "lpo_file_url":        _rp_lpo_url,
                                "sample_file_url":     _rp_sample_url,
                                "payment_terms":       _rp_final_terms,
                                "balance_due_date":    rp_b_due.isoformat(),
                                "date_of_collection":  rp_c_date.isoformat(),
                                "qty_to_print":        int(rp_qty),
                                "type_of_print":       rp_type_print,
                                "material_source":     rp_mat_source,
                                "print_size":          sanitize_string(rp_p_size),
                                "finished_print_size": sanitize_string(rp_f_size),
                                "paper_type":          sanitize_string(rp_pap_type),
                                "gsm":                 sanitize_string(rp_pap_gsm),
                                "paper_size":          sanitize_string(rp_pap_size),
                                "paper_colour":        sanitize_string(rp_pap_col),
                                "impressions_colour":  rp_imp_col,
                                "delivery_mode":       rp_delivery,
                                "binding_type":        ", ".join(rp_b_type) if rp_b_type else "None",
                                "laminating_type":     ", ".join(rp_l_type) if rp_l_type else "None",
                                # Garment-only fields explicitly null for schema safety
                                "print_type": None, "yardage": None, "packaging_mode": None,
                                "process_info": None, "material_description": None,
                                "department":  "PRESS",
                                "status":      "Pending Approval",
                                "created_by":  st.session_state.user_email,
                                "order_date":  datetime.now().strftime("%Y-%m-%d"),
                            }
                            if _rp_orig_pgid:
                                rp_payload["parent_group_id"] = _rp_orig_pgid

                            try:
                                _rp_res    = supabase.table("job_orders").insert(rp_payload).execute()
                                _rp_gen_no = (
                                    _rp_res.data[0].get("job_order_no", f"AT-{random.randint(10000,99999)}")
                                    if _rp_res.data else f"AT-{random.randint(10000,99999)}"
                                )
                                rp_payload["job_order_no"] = _rp_gen_no

                                st.session_state.last_raised_order         = rp_payload
                                st.session_state.last_raised_batch         = []
                                st.session_state.last_raised_garment_batch = []
                                st.session_state.resubmit_order_data       = None
                                st.session_state.resubmit_active_dept      = None

                                send_resend_notification(rp_payload)
                                st.toast("Press order resubmitted and routed to management authorization queue.", icon="✅")
                                st.rerun()
                            except Exception as _rp_err:
                                st.error(f"Failed to resubmit press order: {str(_rp_err)}")
                        else:
                            st.error(f"Transaction blocked. Missing required fields: {', '.join(_rp_missing)}")

        if st.session_state.last_raised_order is not None:
            ticket = st.session_state.last_raised_order
            st.markdown(
                f'<div style="border:1px solid #cbd5e1;padding:24px;border-radius:12px;'
                f'background:#ffffff;color:#0f172a;font-family:Inter,sans-serif;'
                f'font-size:13px;margin-top:20px;box-shadow:0 4px 6px -1px rgba(0,0,0,0.05);">'
                f'<table style="width:100%;border-collapse:collapse;">'
                f'<tr><td colspan="2" style="border-bottom:2px solid #0f172a;padding-bottom:8px;">'
                f'<strong style="font-size:18px;">Appointed Time Printing Ltd.</strong><br>'
                f'<span style="font-size:11px;color:#64748b;text-transform:uppercase;'
                f'letter-spacing:0.05em;">Commercial Job Order Manifest</span></td>'
                f'<td colspan="2" style="border-bottom:2px solid #0f172a;padding-bottom:8px;'
                f'text-align:right;font-size:18px;color:#0369a1;">'
                f'<strong>{ticket.get("job_order_no","PENDING")}</strong></td></tr>'
                f'<tr>'
                f'<td style="padding:12px 8px;border-bottom:1px solid #e2e8f0;width:25%;">'
                f'<span style="color:#64748b;font-size:11px;display:block;margin-bottom:2px;">CUSTOMER NAME</span>'
                f'<strong style="font-size:14px;">{ticket.get("customer_name","")}</strong></td>'
                f'<td style="padding:12px 8px;border-bottom:1px solid #e2e8f0;width:25%;">'
                f'<span style="color:#64748b;font-size:11px;display:block;margin-bottom:2px;">TELEPHONE</span>'
                f'<strong style="font-size:14px;">{ticket.get("telephone_number","")}</strong></td>'
                f'<td style="padding:12px 8px;border-bottom:1px solid #e2e8f0;width:25%;">'
                f'<span style="color:#64748b;font-size:11px;display:block;margin-bottom:2px;">ORDER DATE</span>'
                f'<strong style="font-size:14px;">{ticket.get("order_date","")}</strong></td>'
                f'<td style="padding:12px 8px;border-bottom:1px solid #e2e8f0;width:25%;">'
                f'<span style="color:#64748b;font-size:11px;display:block;margin-bottom:2px;">COLLECTION</span>'
                f'<strong style="font-size:14px;">{ticket.get("date_of_collection","")}</strong></td>'
                f'</tr><tr>'
                f'<td style="padding:12px 8px;border-bottom:2px solid #0f172a;">'
                f'<span style="color:#64748b;font-size:11px;display:block;margin-bottom:2px;">CONTRACT AMOUNT</span>'
                f'<strong style="font-size:14px;">{CURRENCY} {float(ticket.get("total_amount",0)):,.2f}</strong></td>'
                f'<td style="padding:12px 8px;border-bottom:2px solid #0f172a;">'
                f'<span style="color:#64748b;font-size:11px;display:block;margin-bottom:2px;">DEPOSIT PAID</span>'
                f'<strong style="font-size:14px;">{CURRENCY} {float(ticket.get("deposit_amount",0)):,.2f}</strong></td>'
                f'<td colspan="2" style="padding:12px 8px;border-bottom:2px solid #0f172a;">'
                f'<span style="color:#64748b;font-size:11px;display:block;margin-bottom:2px;">BALANCE DUE</span>'
                f'<strong style="color:#ef4444;font-size:14px;">'
                f'{CURRENCY} {float(ticket.get("total_amount",0)) - float(ticket.get("deposit_amount",0)):,.2f}'
                f'</strong></td></tr></table></div>',
                unsafe_allow_html=True
            )
            pdf_buf = dispatch_pdf_manifest(ticket)
            st.markdown("<br>", unsafe_allow_html=True)
            st.download_button(
                label="📄 EXPORT OFFICIAL PDF MANIFEST",
                data=pdf_buf,
                file_name=f"Manifest_{ticket.get('job_order_no','PENDING')}.pdf",
                mime="application/pdf",
                use_container_width=True,
                type="primary"
            )

    # ── NORMAL MODE: DEPARTMENT-FORKED CART ──────────────────────────
    else:
        # ── Customer quick-lookup — zero new DB tables; queries job_orders ──
        _rc_df = pd.DataFrame()
        try:
            _rc_df = get_recent_customers()
        except Exception:
            pass
        if not _rc_df.empty:
            _ql_names = ["— New Customer —"] + _rc_df['customer_name'].fillna('').tolist()
            _ql_col, _ = st.columns([2, 3])
            with _ql_col:
                _ql_pick = st.selectbox(
                    "Quick-fill from past customer",
                    _ql_names, index=0,
                    key="ql_cust_pick",
                    help="Select to auto-fill their details into the form below.",
                )
            if _ql_pick and _ql_pick != "— New Customer —":
                _ql_row = _rc_df[_rc_df['customer_name'] == _ql_pick].iloc[0]
                if st.session_state.get("ql_last_pick") != _ql_pick:
                    st.session_state.ql_last_pick          = _ql_pick
                    st.session_state.cart_client_name      = str(_ql_row.get('customer_name',''))
                    st.session_state.cart_client_phone     = str(_ql_row.get('telephone_number',''))
                    st.session_state.garment_cart_client_name  = str(_ql_row.get('customer_name',''))
                    st.session_state.garment_cart_client_phone = str(_ql_row.get('telephone_number',''))
                st.markdown(
                    f'<div style="background:#f0fdf4;border:1px solid #86efac;border-radius:8px;'
                    f'padding:0.6rem 1rem;margin-bottom:0.9rem;font-size:0.85rem;color:#15803d;">'
                    f'&#x2713; <strong>{_ql_pick}</strong> prefilled — '
                    f'Tel: {_ql_row.get("telephone_number","—")}</div>',
                    unsafe_allow_html=True)
        _dept_col, _ = st.columns([2, 3])
        with _dept_col:
            _resub_dept   = st.session_state.pop("resubmit_active_dept", None)
            _dept_index   = 1 if _resub_dept == "GARMENT" else 0
            selected_department = st.selectbox(
                "Department",
                ["PRESS", "GARMENT"],
                index=_dept_index,
                key="dept_selector",
                help="Select PRESS for offset/digital/packaging orders, GARMENT for apparel & large format."
            )
        st.markdown(
            f'<div class="section-header">{selected_department} Job Order Entry</div>',
            unsafe_allow_html=True)

        # ════════════════════════════════════════════════════════════
        # PRESS CART
        # ════════════════════════════════════════════════════════════
        if selected_department == "PRESS":
            if st.session_state.cart_items:
                _cc = len(st.session_state.cart_items)
                _cn = st.session_state.cart_client_name or "—"
                st.markdown(
                    f'<div style="background:linear-gradient(135deg,#f0fdf4,#dcfce7);'
                    f'border:1px solid #86efac;border-radius:10px;padding:0.85rem 1.25rem;'
                    f'margin-bottom:1.25rem;display:flex;align-items:center;justify-content:space-between;">'
                    f'<div style="font-size:0.875rem;font-weight:700;color:#166534;">'
                    f'🛒 {_cc} item(s) in cart for <strong>{_cn}</strong></div>'
                    f'<div style="font-size:0.75rem;color:#15803d;">'
                    f'Add more items below, or scroll down to submit the batch</div></div>',
                    unsafe_allow_html=True)

            _editing_item = (
                st.session_state.cart_items[st.session_state.editing_cart_idx]
                if st.session_state.editing_cart_idx is not None
                and 0 <= st.session_state.editing_cart_idx < len(st.session_state.cart_items)
                else {}
            )
            def _ed(key, default=""):
                v = _editing_item.get(key, default)
                return v if v not in (None,) else default
            def _edf(key, default=0.0):
                v = _editing_item.get(key, default)
                try:
                    return float(v) if v not in (None, "") else default
                except (TypeError, ValueError):
                    return default
            def _edi(key, default=0):
                v = _editing_item.get(key, default)
                try:
                    return int(v) if v not in (None, "") else default
                except (TypeError, ValueError):
                    return default
            def _edd(key):
                v = _editing_item.get(key)
                if v:
                    try:
                        return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
                    except Exception:
                        pass
                return datetime.now().date()
            def _edl(key, opts):
                v = _editing_item.get(key, "")
                if not v or v == "None":
                    return []
                return [x.strip() for x in str(v).split(",") if x.strip() in opts]

            if _editing_item:
                _ec1, _ec2 = st.columns([5, 1])
                with _ec1:
                    st.info(f"Editing Item {st.session_state.editing_cart_idx + 1} — correct the fields below and click Update.")
                with _ec2:
                    if st.button("Cancel Edit", key="cancel_cart_edit", use_container_width=True):
                        st.session_state.editing_cart_idx = None
                        st.rerun()

            _pv = st.session_state.press_item_form_v
            with st.form("add_cart_item_form", clear_on_submit=False):
                st.markdown('<div class="form-group-header">Client Identity — Shared Across All Items in This Batch</div>',
                            unsafe_allow_html=True)
                _ci1, _ci2 = st.columns(2)
                item_c_name  = _ci1.text_input("Customer Name ★", value=st.session_state.cart_client_name, key=f"pi_cname_{_pv}")
                item_c_phone = _ci2.text_input("Telephone Number ★", value=st.session_state.cart_client_phone, key=f"pi_cphone_{_pv}")
                st.markdown('<div class="form-group-header">Product Item Specifications</div>', unsafe_allow_html=True)
                item_desc = st.text_area("Item Description ★", value=_ed("job_description"),
                                         placeholder="e.g. Skillet Box (250gsm Gloss), A5 Brochure, Business Cards...",
                                         key=f"pi_desc_{_pv}")
                _if1, _if2, _if3, _if4 = st.columns(4)
                item_t_amt  = _if1.number_input("Total Item Amount (GHS) ★", min_value=0.0, step=100.0, value=_edf("total_amount"), key=f"pi_tamt_{_pv}")
                item_d_amt  = _if2.number_input("Deposit Paid (GHS)",         min_value=0.0, step=100.0, value=_edf("deposit_amount"), key=f"pi_damt_{_pv}")
                item_b_due  = _if3.date_input("Balance Deadline ★", value=_edd("balance_due_date"), key=f"pi_bdue_{_pv}")
                item_c_date = _if4.date_input("Collection Date ★",  value=_edd("date_of_collection"), key=f"pi_cdate_{_pv}")
                item_receipt_no = st.text_input(
                    "Receipt Number (required if a deposit is entered)",
                    value=_ed("receipt_no"), placeholder="e.g. RCT-00123", key=f"pi_receipt_{_pv}")
                _is1, _is2, _is3, _is4 = st.columns(4)
                item_qty        = _is1.number_input("Quantity ★", min_value=0, step=500, value=_edi("qty_to_print"), key=f"pi_qty_{_pv}")
                _ipc_opts       = ["", "OFFSET", "DIGITAL PRESS", "PACKAGING"]
                _ipc_exist      = _ed("type_of_print")
                item_type_print = _is2.selectbox("Print Category ★", _ipc_opts,
                                                  index=_ipc_opts.index(_ipc_exist) if _ipc_exist in _ipc_opts else 0,
                                                  key=f"pi_typrint_{_pv}")
                _imat_opts      = ["", "Customer Material", "Company Material"]
                _imat_exist     = _ed("material_source")
                item_mat_source = _is3.selectbox("Material Source", _imat_opts,
                                                  index=_imat_opts.index(_imat_exist) if _imat_exist in _imat_opts else 0,
                                                  key=f"pi_matsrc_{_pv}")
                _idel_opts      = ["Company Delivery", "Client Pickup"]
                _idel_exist     = _ed("delivery_mode")
                item_d_mode     = _is4.selectbox("Delivery Mode", _idel_opts,
                                                  index=_idel_opts.index(_idel_exist) if _idel_exist in _idel_opts else 0,
                                                  key=f"pi_delmode_{_pv}")
                st.markdown('<div class="form-group-header">Material & Engineering Specifics</div>',
                            unsafe_allow_html=True)
                _ip1, _ip2, _ip3, _ip4 = st.columns(4)
                item_p_size   = _ip1.text_input("Print Size",     value=_ed("print_size"), key=f"pi_psize_{_pv}")
                item_f_size   = _ip2.text_input("Finished Size",  value=_ed("finished_print_size"), key=f"pi_fsize_{_pv}")
                item_pap_type = _ip3.text_input("Paper Material", value=_ed("paper_type"), key=f"pi_paptype_{_pv}")
                item_pap_gsm  = _ip4.text_input("GSM",            value=_ed("gsm"), key=f"pi_gsm_{_pv}")
                _ix1, _ix2, _ix3 = st.columns(3)
                item_pap_size = _ix1.text_input("Paper Size",         value=_ed("paper_size"), key=f"pi_papsize_{_pv}")
                item_pap_col  = _ix2.text_input("Colour / Ink Specs", value=_ed("paper_colour"), key=f"pi_papcol_{_pv}")
                item_imp_col  = _ix3.text_input("Impressions",        value=_ed("impressions_colour"), key=f"pi_impcol_{_pv}")
                _ibind_opts = ["Perfect Binding", "Spiral Binding", "Saddle Stitching", "Comb Binding"]
                item_b_type = checkbox_multiselect("Binding Selection", _ibind_opts, f"pi_bind_{_pv}",
                                                    default=_edl("binding_type", _ibind_opts))
                _ilam_opts  = ["Gloss Laminating", "Matt Laminating", "Soft Touch", "UV-Varnish"]
                item_l_type = checkbox_multiselect("Laminating Selection", _ilam_opts, f"pi_lam_{_pv}",
                                                    default=_edl("laminating_type", _ilam_opts))
                st.info(f"Handled By: {st.session_state.user_email} | Date: {datetime.now().strftime('%Y-%m-%d')}")
                add_item_clicked = st.form_submit_button(
                    "Update Item in Cart" if _editing_item else "Add Item to Cart",
                    use_container_width=True)
                if add_item_clicked:
                    _item_missing = []
                    if not item_c_name.strip():  _item_missing.append("Customer Name")
                    if not item_c_phone.strip(): _item_missing.append("Telephone Number")
                    if not item_desc.strip():    _item_missing.append("Item Description")
                    if item_t_amt <= 0.0:        _item_missing.append("Total Item Amount")
                    if item_qty <= 0:            _item_missing.append("Quantity")
                    if not item_type_print:      _item_missing.append("Print Category")
                    if item_d_amt > 0 and not item_receipt_no.strip():
                        _item_missing.append("Receipt Number (required since a deposit was entered)")
                    if not _item_missing:
                        st.session_state.cart_client_name  = item_c_name.strip()
                        st.session_state.cart_client_phone = item_c_phone.strip()
                        _new_item = {
                            "department":          "PRESS",
                            "job_description":     sanitize_string(item_desc),
                            "total_amount":        float(item_t_amt),
                            "deposit_amount":      float(item_d_amt),
                            "receipt_no":          sanitize_string(item_receipt_no) if item_d_amt > 0 else None,
                            "balance_due_date":    item_b_due.isoformat(),
                            "date_of_collection":  item_c_date.isoformat(),
                            "qty_to_print":        int(item_qty),
                            "type_of_print":       item_type_print,
                            "material_source":     item_mat_source,
                            "print_size":          sanitize_string(item_p_size),
                            "finished_print_size": sanitize_string(item_f_size),
                            "paper_type":          sanitize_string(item_pap_type),
                            "gsm":                 sanitize_string(item_pap_gsm),
                            "paper_size":          sanitize_string(item_pap_size),
                            "paper_colour":        sanitize_string(item_pap_col),
                            "impressions_colour":  item_imp_col,
                            "delivery_mode":       item_d_mode,
                            "binding_type":        ", ".join(item_b_type) if item_b_type else "None",
                            "laminating_type":     ", ".join(item_l_type) if item_l_type else "None",
                            # garment fields null for schema safety
                            "print_type": None, "yardage": None, "packaging_mode": None,
                            "process_info": None, "material_description": None,
                        }
                        if (st.session_state.editing_cart_idx is not None
                                and 0 <= st.session_state.editing_cart_idx < len(st.session_state.cart_items)):
                            st.session_state.cart_items[st.session_state.editing_cart_idx] = _new_item
                            st.session_state.editing_cart_idx = None
                            st.toast("Item updated!", icon="✏️")
                        else:
                            st.session_state.cart_items.append(_new_item)
                            st.toast(f"Item {len(st.session_state.cart_items)} added to cart!", icon="✅")
                        st.session_state.press_item_form_v += 1
                        st.rerun()
                    else:
                        st.error(f"Cannot add item — missing required fields: {', '.join(_item_missing)}")

            if st.session_state.cart_items:
                st.markdown("<br>", unsafe_allow_html=True)
                st.markdown(f"### 🛒 Active Cart — {len(st.session_state.cart_items)} Item(s) for {st.session_state.cart_client_name}")
                for _ci_idx, _ci_item in enumerate(st.session_state.cart_items):
                    _ci_preview = _ci_item['job_description'][:80] + ("…" if len(_ci_item['job_description']) > 80 else "")
                    _col_info, _col_edit, _col_rm = st.columns([6, 1, 1])
                    with _col_info:
                        st.markdown(
                            f'<div style="background:#f8fafc;border:1px solid #e2e8f0;'
                            f'border-left:4px solid #0369a1;border-radius:8px;'
                            f'padding:0.75rem 1rem;margin-bottom:0.4rem;">'
                            f'<div style="font-weight:700;color:#0f172a;font-size:0.9rem;">'
                            f'Item {_ci_idx+1}: {_ci_preview}</div>'
                            f'<div style="color:#64748b;font-size:0.78rem;margin-top:0.25rem;">'
                            f'Qty: <strong>{_ci_item["qty_to_print"]:,}</strong> &nbsp;·&nbsp; '
                            f'Category: <strong>{_ci_item["type_of_print"]}</strong> &nbsp;·&nbsp; '
                            f'Amount: <strong>{CURRENCY} {_ci_item["total_amount"]:,.2f}</strong>'
                            f' &nbsp;·&nbsp; '
                            f'Deposit: <strong>{CURRENCY} {_ci_item["deposit_amount"]:,.2f}</strong>'
                            f' &nbsp;·&nbsp; '
                            f'Collection: <strong>{_ci_item["date_of_collection"]}</strong>'
                            f'</div></div>', unsafe_allow_html=True)
                    with _col_edit:
                        if st.button("✏️ Edit", key=f"edit_cart_{_ci_idx}", use_container_width=True):
                            st.session_state.editing_cart_idx = _ci_idx
                            st.rerun()
                    with _col_rm:
                        if st.button("✕ Remove", key=f"rm_cart_{_ci_idx}", use_container_width=True):
                            st.session_state.cart_items.pop(_ci_idx)
                            if st.session_state.editing_cart_idx == _ci_idx:
                                st.session_state.editing_cart_idx = None
                            st.rerun()
                st.markdown("<br>", unsafe_allow_html=True)
                _cart_total   = sum(x.get('total_amount',   0) for x in st.session_state.cart_items)
                _cart_deposit = sum(x.get('deposit_amount', 0) for x in st.session_state.cart_items)
                _cart_has_balance = any(
                    float(x.get('total_amount', 0) or 0) != float(x.get('deposit_amount', 0) or 0)
                    for x in st.session_state.cart_items
                )
                st.markdown(
                    f'<div style="background:linear-gradient(135deg,#0f172a,#1e293b);'
                    f'color:#ffffff;border-radius:10px;padding:1rem 1.5rem;margin-bottom:1.25rem;'
                    f'display:flex;gap:2.5rem;flex-wrap:wrap;align-items:center;">'
                    f'<div><div style="font-size:0.62rem;color:#94a3b8;text-transform:uppercase;'
                    f'letter-spacing:0.06em;margin-bottom:0.15rem;">CLIENT</div>'
                    f'<div style="font-weight:700;font-size:0.95rem;">{st.session_state.cart_client_name}</div></div>'
                    f'<div><div style="font-size:0.62rem;color:#94a3b8;text-transform:uppercase;'
                    f'letter-spacing:0.06em;margin-bottom:0.15rem;">ITEMS</div>'
                    f'<div style="font-weight:700;font-size:0.95rem;">{len(st.session_state.cart_items)}</div></div>'
                    f'<div><div style="font-size:0.62rem;color:#94a3b8;text-transform:uppercase;'
                    f'letter-spacing:0.06em;margin-bottom:0.15rem;">COMBINED CONTRACT VALUE</div>'
                    f'<div style="font-weight:700;font-size:1rem;color:#34d399;">{CURRENCY} {_cart_total:,.2f}</div></div>'
                    f'<div><div style="font-size:0.62rem;color:#94a3b8;text-transform:uppercase;'
                    f'letter-spacing:0.06em;margin-bottom:0.15rem;">TOTAL DEPOSIT COLLECTED</div>'
                    f'<div style="font-weight:700;font-size:1rem;color:#7dd3fc;">{CURRENCY} {_cart_deposit:,.2f}</div></div>'
                    f'</div>', unsafe_allow_html=True)

                st.markdown("### 📎 Attachments &amp; Terms — Applies to This Whole Batch")
                _ba1, _ba2 = st.columns(2)
                _batch_lpo_file = _ba1.file_uploader(
                    "Upload LPO (optional) — goes to MD/FM", type=["pdf", "jpg", "jpeg", "png"],
                    key="cart_lpo_upload")
                _batch_sample_file = _ba2.file_uploader(
                    "Upload Sample Photo (optional) — goes to the department", type=["pdf", "jpg", "jpeg", "png"],
                    key="cart_sample_upload")
                _sa1, _sa2 = st.columns(2)
                _batch_sample_attached = _sa1.selectbox("Sample Attached?", ["No", "Yes"], key="cart_sample_attached")
                _batch_sample_with = _sa2.text_input(
                    "Sample With (required if Yes)", key="cart_sample_with",
                    placeholder="e.g. Front Desk, With Client, Production")
                _pt1, _pt2 = st.columns(2)
                _batch_30day = _pt1.checkbox("30-Day Credit Terms job", key="cart_30day")
                _batch_sales_rep = _pt2.selectbox(
                    "Sales / Marketing Rep (who brought this job)",
                    ["— None / Walk-in —"] + list(SALES_REP_EMAILS.keys()), key="cart_sales_rep")
                _batch_terms_notes = ""
                if _cart_has_balance:
                    _batch_terms_notes = st.text_area(
                        "Payment Terms Notes — this batch isn't fully paid; explain the arrangement for MD/FM",
                        key="cart_terms_notes",
                        placeholder="e.g. Client to pay balance on collection; LPO attached; verbal agreement with MD on...")

                _sub_col, _clr_col = st.columns([3, 1])
                with _sub_col:
                    if st.button(f"SUBMIT {len(st.session_state.cart_items)} ITEM(S) FOR MANAGEMENT APPROVAL",
                                 type="primary", use_container_width=True):
                        if not st.session_state.cart_client_name or not st.session_state.cart_client_phone:
                            st.error("Client name and telephone must be set before submitting the batch.")
                        elif _batch_sample_attached == "Yes" and not _batch_sample_with.strip():
                            st.error("Sample is marked attached — enter who has it before submitting.")
                        else:
                            _pgid      = f"PG-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{random.randint(1000,9999)}"

                            def _upload_batch_file(_f, _label):
                                if _f is None:
                                    return None
                                try:
                                    _fb = _f.getvalue()
                                    _sp = f"{_pgid}/{_f.name}"
                                    supabase.storage.from_('job-attachments').upload(
                                        _sp, _fb, {"content-type": _f.type or "application/octet-stream"})
                                    return supabase.storage.from_('job-attachments').get_public_url(_sp)
                                except Exception as _ue:
                                    st.warning(f"{_label} upload failed (order will still submit without it): {_ue}")
                                    return None

                            _lpo_url    = _upload_batch_file(_batch_lpo_file, "LPO")
                            _sample_url = _upload_batch_file(_batch_sample_file, "Sample photo")
                            _terms_parts = []
                            if _batch_30day:
                                _terms_parts.append("30-Day Credit Terms")
                            if _cart_has_balance and _batch_terms_notes.strip():
                                _terms_parts.append(sanitize_string(_batch_terms_notes))
                            _final_payment_terms = " | ".join(_terms_parts) if _terms_parts else None
                            _submitted = []
                            _batch_err = False
                            for _b_item in st.session_state.cart_items:
                                _payload = {
                                    "customer_name":    sanitize_string(st.session_state.cart_client_name),
                                    "telephone_number": sanitize_string(st.session_state.cart_client_phone),
                                    "parent_group_id":  _pgid,
                                    "status":           "Pending Approval",
                                    "created_by":       st.session_state.user_email,
                                    "order_date":       datetime.now().strftime('%Y-%m-%d'),
                                    "sample_attached":  _batch_sample_attached,
                                    "sample_with":      sanitize_string(_batch_sample_with) if _batch_sample_attached == "Yes" else None,
                                    "lpo_file_url":     _lpo_url,
                                    "sample_file_url":  _sample_url,
                                    "payment_terms":    _final_payment_terms,
                                    "sales_rep":        _batch_sales_rep if _batch_sales_rep != "— None / Walk-in —" else None,
                                    **_b_item
                                }
                                try:
                                    _res    = supabase.table('job_orders').insert(_payload).execute()
                                    _gen_no = (
                                        _res.data[0].get("job_order_no", f"AT-{random.randint(10000,99999)}")
                                        if _res.data else f"AT-{random.randint(10000,99999)}"
                                    )
                                    _payload["job_order_no"] = _gen_no
                                    _submitted.append(_payload)
                                except Exception as _be:
                                    st.error(f"Failed to insert item: {str(_be)}")
                                    _batch_err = True
                                    break
                            if not _batch_err and _submitted:
                                st.session_state.last_raised_batch  = _submitted
                                st.session_state.last_raised_order  = None
                                st.session_state.cart_items         = []
                                st.session_state.cart_client_name   = ""
                                st.session_state.cart_client_phone  = ""
                                st.session_state.editing_cart_idx   = None
                                _notif = _submitted[0].copy()
                                _notif['total_amount'] = sum(o.get('total_amount', 0) for o in _submitted)
                                send_resend_notification(_notif)
                                st.toast(f"✅ Batch of {len(_submitted)} item(s) submitted to management authorization queue.", icon="✅")
                                st.rerun()
                with _clr_col:
                    if st.button("🗑 Clear Cart", use_container_width=True):
                        st.session_state.cart_items        = []
                        st.session_state.cart_client_name  = ""
                        st.session_state.cart_client_phone = ""
                        st.session_state.editing_cart_idx  = None
                        st.rerun()

            if st.session_state.last_raised_batch:
                st.markdown("<br>", unsafe_allow_html=True)
                _batch = st.session_state.last_raised_batch
                st.markdown(
                    f'<div style="background:linear-gradient(135deg,#f0fdf4,#dcfce7);'
                    f'border:1px solid #86efac;border-radius:12px;'
                    f'padding:1.25rem 1.5rem;margin-bottom:1.25rem;">'
                    f'<div style="font-size:0.75rem;font-weight:700;color:#166534;'
                    f'text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.35rem;">'
                    f'Batch Submission Confirmed</div>'
                    f'<div style="font-size:1.1rem;font-weight:800;color:#0f172a;">'
                    f'{len(_batch)} item(s) deposited in management authorization ledger</div>'
                    f'<div style="font-size:0.82rem;color:#15803d;margin-top:0.2rem;">'
                    f'Batch Ref: <strong>{_batch[0].get("parent_group_id","—")}</strong>'
                    f' &nbsp;·&nbsp; Client: <strong>{_batch[0].get("customer_name","—")}</strong>'
                    f'</div></div>', unsafe_allow_html=True)
                for _b_idx, _b_ticket in enumerate(_batch):
                    _b_preview = _b_ticket.get('job_description','')[:60] + ("…" if len(_b_ticket.get('job_description','')) > 60 else "")
                    st.markdown(
                        f'<div style="background:#ffffff;border:1px solid #e2e8f0;'
                        f'border-left:4px solid #10b981;border-radius:8px;'
                        f'padding:0.75rem 1rem;margin-bottom:0.5rem;'
                        f'display:flex;align-items:center;justify-content:space-between;">'
                        f'<div>'
                        f'<div style="font-weight:700;color:#0f172a;font-size:0.9rem;">Item {_b_idx+1}: {_b_preview}</div>'
                        f'<div style="font-size:0.78rem;color:#64748b;margin-top:0.15rem;">'
                        f'Ref: <strong style="color:#0369a1;">{_b_ticket.get("job_order_no","PENDING")}</strong>'
                        f' &nbsp;·&nbsp; {_b_ticket.get("qty_to_print",0):,} units'
                        f' &nbsp;·&nbsp; {_b_ticket.get("type_of_print","")}'
                        f' &nbsp;·&nbsp; {CURRENCY} {_b_ticket.get("total_amount",0):,.2f}'
                        f'</div></div></div>', unsafe_allow_html=True)
                    _b_pdf = dispatch_pdf_manifest(_b_ticket)
                    st.download_button(
                        label=f"📄 Export PDF — Item {_b_idx+1}: {_b_ticket.get('job_order_no','PENDING')}",
                        data=_b_pdf,
                        file_name=f"Manifest_{_b_ticket.get('job_order_no','PENDING')}.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                        key=f"dl_batch_{_b_idx}"
                    )

        # ════════════════════════════════════════════════════════════
        # GARMENT CART
        # ════════════════════════════════════════════════════════════
        else:
            if st.session_state.garment_cart_items:
                _gcc = len(st.session_state.garment_cart_items)
                _gcn = st.session_state.garment_cart_client_name or "—"
                st.markdown(
                    f'<div style="background:linear-gradient(135deg,#fffbeb,#fef3c7);'
                    f'border:1px solid #f59e0b;border-radius:10px;padding:0.85rem 1.25rem;'
                    f'margin-bottom:1.25rem;display:flex;align-items:center;justify-content:space-between;">'
                    f'<div style="font-size:0.875rem;font-weight:700;color:#92400e;">'
                    f'{_gcc} garment item(s) in cart for <strong>{_gcn}</strong></div>'
                    f'<div style="font-size:0.75rem;color:#b45309;">'
                    f'Add more items below, or scroll down to submit the batch</div></div>',
                    unsafe_allow_html=True)

            _g_editing_item = (
                st.session_state.garment_cart_items[st.session_state.editing_garment_cart_idx]
                if st.session_state.editing_garment_cart_idx is not None
                and 0 <= st.session_state.editing_garment_cart_idx < len(st.session_state.garment_cart_items)
                else {}
            )
            def _ged(key, default=""):
                v = _g_editing_item.get(key, default)
                return v if v not in (None,) else default
            def _gedf(key, default=0.0):
                v = _g_editing_item.get(key, default)
                try:
                    return float(v) if v not in (None, "") else default
                except (TypeError, ValueError):
                    return default
            def _gedi(key, default=0):
                v = _g_editing_item.get(key, default)
                try:
                    return int(v) if v not in (None, "") else default
                except (TypeError, ValueError):
                    return default
            def _gedd(key):
                v = _g_editing_item.get(key)
                if v:
                    try:
                        return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
                    except Exception:
                        pass
                return datetime.now().date()

            if _g_editing_item:
                _gec1, _gec2 = st.columns([5, 1])
                with _gec1:
                    st.info(f"✏️ Editing Item {st.session_state.editing_garment_cart_idx + 1} — correct the fields below and click Update.")
                with _gec2:
                    if st.button("Cancel Edit", key="cancel_garment_cart_edit", use_container_width=True):
                        st.session_state.editing_garment_cart_idx = None
                        st.rerun()

            _gv = st.session_state.garment_item_form_v
            with st.form("add_garment_cart_item_form", clear_on_submit=False):
                st.markdown('<div class="form-group-header">Client Identity — Shared Across All Garment Items</div>',
                            unsafe_allow_html=True)
                _gi1, _gi2 = st.columns(2)
                g_c_name  = _gi1.text_input("Customer Name ★", value=st.session_state.garment_cart_client_name, key=f"gi_cname_{_gv}")
                g_c_phone = _gi2.text_input("Telephone Number ★", value=st.session_state.garment_cart_client_phone, key=f"gi_cphone_{_gv}")
                st.markdown('<div class="form-group-header">Item Description & Financial</div>', unsafe_allow_html=True)
                g_desc = st.text_area("Item / Job Description ★", value=_ged("job_description"),
                                       placeholder="e.g. Custom T-Shirt DTF print, 50 pcs, White cotton...",
                                       key=f"gi_desc_{_gv}")
                _gf1, _gf2, _gf3, _gf4 = st.columns(4)
                g_t_amt  = _gf1.number_input("Total Item Amount (GHS) ★", min_value=0.0, step=100.0, value=_gedf("total_amount"), key=f"gi_tamt_{_gv}")
                g_d_amt  = _gf2.number_input("Deposit Paid (GHS)",          min_value=0.0, step=100.0, value=_gedf("deposit_amount"), key=f"gi_damt_{_gv}")
                g_b_due  = _gf3.date_input("Balance Deadline ★", value=_gedd("balance_due_date"), key=f"gi_bdue_{_gv}")
                g_c_date = _gf4.date_input("Collection Date ★",  value=_gedd("date_of_collection"), key=f"gi_cdate_{_gv}")
                g_receipt_no = st.text_input(
                    "Receipt Number (required if a deposit is entered)",
                    value=_ged("receipt_no"), placeholder="e.g. RCT-00123", key=f"gi_receipt_{_gv}")
                _gq1, _gq2 = st.columns(2)
                g_qty        = _gq1.number_input("Quantity to Print ★", min_value=0, step=10, value=_gedi("qty_to_print"), key=f"gi_qty_{_gv}")
                _gmat_opts   = ["", "Company Material", "Customer Material"]
                _gmat_exist  = _ged("material_source")
                g_mat_source = _gq2.selectbox("Material Source ★", _gmat_opts,
                                               index=_gmat_opts.index(_gmat_exist) if _gmat_exist in _gmat_opts else 0,
                                               key=f"gi_matsrc_{_gv}")
                st.markdown('<div class="form-group-header">Print Type & Dimensions</div>', unsafe_allow_html=True)
                _gpt1, _gpt2 = st.columns(2)
                _gprint_opts  = ["", "DTF", "Flexi Screen Print", "UV-DTF", "SAV", "Embroidery"]
                _gprint_exist = _ged("print_type") or _ged("type_of_print")
                g_print_type  = _gpt1.selectbox("Print Type ★", _gprint_opts,
                                                 index=_gprint_opts.index(_gprint_exist) if _gprint_exist in _gprint_opts else 0,
                                                 key=f"gi_ptype_{_gv}")
                _gdel_opts    = ["Company Delivery", "Customer Pick-up"]
                _gdel_exist   = _ged("delivery_mode")
                g_delivery    = _gpt2.selectbox("Delivery Mode ★", _gdel_opts,
                                                 index=_gdel_opts.index(_gdel_exist) if _gdel_exist in _gdel_opts else 0,
                                                 key=f"gi_delmode_{_gv}")
                _gps1, _gps2 = st.columns(2)
                _gpsz_opts   = ["", "A1", "A2", "A3", "A4", "A5", "A6"]
                _gpsz_exist  = _ged("print_size")
                g_print_size = _gps1.selectbox("Print Size", _gpsz_opts,
                                                index=_gpsz_opts.index(_gpsz_exist) if _gpsz_exist in _gpsz_opts else 0,
                                                key=f"gi_psize_{_gv}")
                _gfsz_opts   = ["", "A1", "A2", "A3", "A4", "A5", "A6",
                                "1YRD", "2YRDs", "3YRDs", "4YRDs", "5YRDs", "6YRDs",
                                "3FTx4FT", "4FTx8FT"]
                _gfsz_exist  = _ged("finished_print_size") or _ged("yardage")
                g_fin_size   = _gps2.selectbox("Finished Print Size / Yardage", _gfsz_opts,
                                                index=_gfsz_opts.index(_gfsz_exist) if _gfsz_exist in _gfsz_opts else 0,
                                                key=f"gi_fsize_{_gv}")
                st.markdown('<div class="form-group-header">Material Description</div>', unsafe_allow_html=True)
                g_mat_desc     = st.text_area("Material Description (fabric type, colour, etc.)",
                                               value=_ged("material_description"),
                                               placeholder="e.g. Cotton Jersey White, Polyester Red...",
                                               key=f"gi_matdesc_{_gv}")
                g_add_comments = st.text_area("Additional Comments / Specifications",
                                               value=_ged("additional_comments"),
                                               placeholder="Any other technical requirements...",
                                               key=f"gi_comments_{_gv}")
                st.markdown('<div class="form-group-header">Packaging & Delivery</div>', unsafe_allow_html=True)
                _gpkg1, _gpkg2, _gpkg3 = st.columns(3)
                _gpkgm_opts  = ["", "Box Packaging", "Bag Packaging", "None"]
                _gpkgm_exist = _ged("packaging_mode")
                g_pkg_mode  = _gpkg1.selectbox("Packaging Mode", _gpkgm_opts,
                                                index=_gpkgm_opts.index(_gpkgm_exist) if _gpkgm_exist in _gpkgm_opts else 0,
                                                key=f"gi_pkgmode_{_gv}")
                g_qty_pack  = _gpkg2.number_input("Qty to Pack", min_value=0, step=1, value=_gedi("qty_to_pack"), key=f"gi_qtypack_{_gv}")
                g_pkg_specs = _gpkg3.text_input("Packaging Specs", value=_ged("packaging_specs"), key=f"gi_pkgspecs_{_gv}")
                _gloc1, _gloc2 = st.columns(2)
                g_location = _gloc1.text_input("Delivery Location", value=_ged("delivery_location"), key=f"gi_location_{_gv}")
                g_contact  = _gloc2.text_input("Delivery Contact Person", value=_ged("delivery_contact"), key=f"gi_contact_{_gv}")
                st.markdown('<div class="form-group-header">Process / Technical Info</div>', unsafe_allow_html=True)
                g_process_info = st.text_area("Process / Technical Information",
                                               value=_ged("process_info"),
                                               placeholder="Stitching count, thread colour, press temperature...",
                                               key=f"gi_procinfo_{_gv}")
                st.info(f"Handled By: {st.session_state.user_email} | Date: {datetime.now().strftime('%Y-%m-%d')}")
                g_add_item_clicked = st.form_submit_button(
                    "💾 Update Item in Cart" if _g_editing_item else "Add Item to Cart",
                    use_container_width=True)
                if g_add_item_clicked:
                    _g_missing = []
                    if not g_c_name.strip():  _g_missing.append("Customer Name")
                    if not g_c_phone.strip(): _g_missing.append("Telephone Number")
                    if not g_desc.strip():    _g_missing.append("Item Description")
                    if g_t_amt <= 0.0:        _g_missing.append("Total Item Amount")
                    if g_qty <= 0:            _g_missing.append("Quantity")
                    if not g_print_type:      _g_missing.append("Print Type")
                    if not g_mat_source:      _g_missing.append("Material Source")
                    if g_d_amt > 0 and not g_receipt_no.strip():
                        _g_missing.append("Receipt Number (required since a deposit was entered)")
                    if not _g_missing:
                        st.session_state.garment_cart_client_name  = g_c_name.strip()
                        st.session_state.garment_cart_client_phone = g_c_phone.strip()
                        _mat_rows = []
                        for _ml in g_mat_desc.strip().splitlines():
                            if _ml.strip():
                                _mat_rows.append({"material": _ml.strip(), "sizes": g_fin_size, "colour": ""})
                        if not _mat_rows:
                            _mat_rows = [{"material": g_mat_desc, "sizes": g_fin_size, "colour": ""}]
                        _new_g_item = {
                            "department":               "GARMENT",
                            "job_description":          sanitize_string(g_desc),
                            "total_amount":             float(g_t_amt),
                            "deposit_amount":           float(g_d_amt),
                            "receipt_no":               sanitize_string(g_receipt_no) if g_d_amt > 0 else None,
                            "balance_due_date":         g_b_due.isoformat(),
                            "date_of_collection":       g_c_date.isoformat(),
                            "qty_to_print":             int(g_qty),
                            "print_type":               g_print_type,
                            "type_of_print":            g_print_type,
                            "material_source":          g_mat_source,
                            "delivery_mode":            g_delivery,
                            "print_size":               g_print_size,
                            "finished_print_size":      g_fin_size,
                            "yardage":                  g_fin_size,
                            "material_description":     sanitize_string(g_mat_desc),
                            "material_description_rows": _mat_rows,
                            "additional_comments":      sanitize_string(g_add_comments),
                            "packaging_mode":           g_pkg_mode,
                            "qty_to_pack":              int(g_qty_pack),
                            "packaging_specs":          sanitize_string(g_pkg_specs),
                            "delivery_location":        sanitize_string(g_location),
                            "delivery_contact":         sanitize_string(g_contact),
                            "process_info":             sanitize_string(g_process_info),
                            # Press-only fields explicitly null for schema safety
                            "paper_type": None, "gsm": None, "paper_size": None,
                            "paper_colour": None, "impressions_colour": None,
                            "binding_type": None, "laminating_type": None,
                        }
                        if (st.session_state.editing_garment_cart_idx is not None
                                and 0 <= st.session_state.editing_garment_cart_idx < len(st.session_state.garment_cart_items)):
                            st.session_state.garment_cart_items[st.session_state.editing_garment_cart_idx] = _new_g_item
                            st.session_state.editing_garment_cart_idx = None
                            st.toast("Garment item updated!", icon="✏️")
                        else:
                            st.session_state.garment_cart_items.append(_new_g_item)
                            st.toast(f"Garment item {len(st.session_state.garment_cart_items)} added to cart!", icon="🧵")
                        st.session_state.garment_item_form_v += 1
                        st.rerun()
                    else:
                        st.error(f"Cannot add item — missing required fields: {', '.join(_g_missing)}")

            if st.session_state.garment_cart_items:
                st.markdown("<br>", unsafe_allow_html=True)
                st.markdown(f"### 🧵 Garment Cart — {len(st.session_state.garment_cart_items)} Item(s) for {st.session_state.garment_cart_client_name}")
                for _gci_idx, _gci_item in enumerate(st.session_state.garment_cart_items):
                    _gci_preview = _gci_item['job_description'][:80] + ("…" if len(_gci_item['job_description']) > 80 else "")
                    _gcol_info, _gcol_edit, _gcol_rm = st.columns([6, 1, 1])
                    with _gcol_info:
                        st.markdown(
                            f'<div style="background:#fffbeb;border:1px solid #fde68a;'
                            f'border-left:4px solid #f59e0b;border-radius:8px;'
                            f'padding:0.75rem 1rem;margin-bottom:0.4rem;">'
                            f'<div style="font-weight:700;color:#0f172a;font-size:0.9rem;">'
                            f'Item {_gci_idx+1}: {_gci_preview}</div>'
                            f'<div style="color:#64748b;font-size:0.78rem;margin-top:0.25rem;">'
                            f'Qty: <strong>{_gci_item["qty_to_print"]:,}</strong> &nbsp;·&nbsp; '
                            f'Type: <strong>{_gci_item["print_type"]}</strong> &nbsp;·&nbsp; '
                            f'Amount: <strong>{CURRENCY} {_gci_item["total_amount"]:,.2f}</strong>'
                            f' &nbsp;·&nbsp; '
                            f'Deposit: <strong>{CURRENCY} {_gci_item["deposit_amount"]:,.2f}</strong>'
                            f' &nbsp;·&nbsp; '
                            f'Collection: <strong>{_gci_item["date_of_collection"]}</strong>'
                            f'</div></div>', unsafe_allow_html=True)
                    with _gcol_edit:
                        if st.button("✏️ Edit", key=f"gedit_cart_{_gci_idx}", use_container_width=True):
                            st.session_state.editing_garment_cart_idx = _gci_idx
                            st.rerun()
                    with _gcol_rm:
                        if st.button("✕ Remove", key=f"grm_cart_{_gci_idx}", use_container_width=True):
                            st.session_state.garment_cart_items.pop(_gci_idx)
                            if st.session_state.editing_garment_cart_idx == _gci_idx:
                                st.session_state.editing_garment_cart_idx = None
                            st.rerun()
                st.markdown("<br>", unsafe_allow_html=True)
                _g_cart_total   = sum(x.get('total_amount',   0) for x in st.session_state.garment_cart_items)
                _g_cart_deposit = sum(x.get('deposit_amount', 0) for x in st.session_state.garment_cart_items)
                _g_cart_has_balance = any(
                    float(x.get('total_amount', 0) or 0) != float(x.get('deposit_amount', 0) or 0)
                    for x in st.session_state.garment_cart_items
                )
                st.markdown(
                    f'<div style="background:linear-gradient(135deg,#78350f,#92400e);'
                    f'color:#ffffff;border-radius:10px;padding:1rem 1.5rem;margin-bottom:1.25rem;'
                    f'display:flex;gap:2.5rem;flex-wrap:wrap;align-items:center;">'
                    f'<div><div style="font-size:0.62rem;color:#fde68a;text-transform:uppercase;'
                    f'letter-spacing:0.06em;margin-bottom:0.15rem;">CLIENT</div>'
                    f'<div style="font-weight:700;font-size:0.95rem;">{st.session_state.garment_cart_client_name}</div></div>'
                    f'<div><div style="font-size:0.62rem;color:#fde68a;text-transform:uppercase;'
                    f'letter-spacing:0.06em;margin-bottom:0.15rem;">ITEMS</div>'
                    f'<div style="font-weight:700;font-size:0.95rem;">{len(st.session_state.garment_cart_items)}</div></div>'
                    f'<div><div style="font-size:0.62rem;color:#fde68a;text-transform:uppercase;'
                    f'letter-spacing:0.06em;margin-bottom:0.15rem;">COMBINED VALUE</div>'
                    f'<div style="font-weight:700;font-size:1rem;color:#fcd34d;">{CURRENCY} {_g_cart_total:,.2f}</div></div>'
                    f'<div><div style="font-size:0.62rem;color:#fde68a;text-transform:uppercase;'
                    f'letter-spacing:0.06em;margin-bottom:0.15rem;">DEPOSITS COLLECTED</div>'
                    f'<div style="font-weight:700;font-size:1rem;color:#fcd34d;">{CURRENCY} {_g_cart_deposit:,.2f}</div></div>'
                    f'</div>', unsafe_allow_html=True)

                st.markdown("### 📎 Attachments &amp; Terms — Applies to This Whole Batch")
                _gba1, _gba2 = st.columns(2)
                _g_batch_lpo_file = _gba1.file_uploader(
                    "Upload LPO (optional) — goes to MD/FM", type=["pdf", "jpg", "jpeg", "png"],
                    key="garment_cart_lpo_upload")
                _g_batch_sample_file = _gba2.file_uploader(
                    "Upload Sample Photo (optional) — goes to the department", type=["pdf", "jpg", "jpeg", "png"],
                    key="garment_cart_sample_upload")
                _gsa1, _gsa2 = st.columns(2)
                _g_batch_sample_attached = _gsa1.selectbox("Sample Attached?", ["No", "Yes"], key="garment_cart_sample_attached")
                _g_batch_sample_with = _gsa2.text_input(
                    "Sample With (required if Yes)", key="garment_cart_sample_with",
                    placeholder="e.g. Front Desk, With Client, Production")
                _gpt1, _gpt2 = st.columns(2)
                _g_batch_30day = _gpt1.checkbox("30-Day Credit Terms job", key="garment_cart_30day")
                _g_batch_sales_rep = _gpt2.selectbox(
                    "Sales / Marketing Rep (who brought this job)",
                    ["— None / Walk-in —"] + list(SALES_REP_EMAILS.keys()), key="garment_cart_sales_rep")
                _g_batch_terms_notes = ""
                if _g_cart_has_balance:
                    _g_batch_terms_notes = st.text_area(
                        "Payment Terms Notes — this batch isn't fully paid; explain the arrangement for MD/FM",
                        key="garment_cart_terms_notes",
                        placeholder="e.g. Client to pay balance on collection; LPO attached; verbal agreement with MD on...")

                _gsub_col, _gclr_col = st.columns([3, 1])
                with _gsub_col:
                    if st.button(
                        f"🚀 SUBMIT {len(st.session_state.garment_cart_items)} GARMENT ITEM(S) FOR MANAGEMENT APPROVAL",
                        type="primary", use_container_width=True, key="submit_garment_batch"
                    ):
                        if not st.session_state.garment_cart_client_name or not st.session_state.garment_cart_client_phone:
                            st.error("Client name and telephone must be set before submitting the batch.")
                        elif _g_batch_sample_attached == "Yes" and not _g_batch_sample_with.strip():
                            st.error("Sample is marked attached — enter who has it before submitting.")
                        else:
                            _g_pgid      = f"GPG-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{random.randint(1000,9999)}"

                            def _upload_g_batch_file(_f, _label):
                                if _f is None:
                                    return None
                                try:
                                    _fb = _f.getvalue()
                                    _sp = f"{_g_pgid}/{_f.name}"
                                    supabase.storage.from_('job-attachments').upload(
                                        _sp, _fb, {"content-type": _f.type or "application/octet-stream"})
                                    return supabase.storage.from_('job-attachments').get_public_url(_sp)
                                except Exception as _gue:
                                    st.warning(f"{_label} upload failed (order will still submit without it): {_gue}")
                                    return None

                            _g_lpo_url    = _upload_g_batch_file(_g_batch_lpo_file, "LPO")
                            _g_sample_url = _upload_g_batch_file(_g_batch_sample_file, "Sample photo")
                            _g_terms_parts = []
                            if _g_batch_30day:
                                _g_terms_parts.append("30-Day Credit Terms")
                            if _g_cart_has_balance and _g_batch_terms_notes.strip():
                                _g_terms_parts.append(sanitize_string(_g_batch_terms_notes))
                            _g_final_payment_terms = " | ".join(_g_terms_parts) if _g_terms_parts else None
                            _g_submitted = []
                            _g_batch_err = False
                            for _gb_item in st.session_state.garment_cart_items:
                                _g_payload = {
                                    "customer_name":    sanitize_string(st.session_state.garment_cart_client_name),
                                    "telephone_number": sanitize_string(st.session_state.garment_cart_client_phone),
                                    "parent_group_id":  _g_pgid,
                                    "status":           "Pending Approval",
                                    "created_by":       st.session_state.user_email,
                                    "order_date":       datetime.now().strftime('%Y-%m-%d'),
                                    "sample_attached":  _g_batch_sample_attached,
                                    "sample_with":      sanitize_string(_g_batch_sample_with) if _g_batch_sample_attached == "Yes" else None,
                                    "lpo_file_url":     _g_lpo_url,
                                    "sample_file_url":  _g_sample_url,
                                    "payment_terms":    _g_final_payment_terms,
                                    "sales_rep":        _g_batch_sales_rep if _g_batch_sales_rep != "— None / Walk-in —" else None,
                                    **_gb_item
                                }
                                # material_description_rows is Python-only; remove before Supabase insert
                                _rows_for_pdf = _g_payload.pop("material_description_rows", [])
                                try:
                                    _g_res    = supabase.table('job_orders').insert(_g_payload).execute()
                                    _g_gen_no = (
                                        _g_res.data[0].get("job_order_no", f"GT-{random.randint(10000,99999)}")
                                        if _g_res.data else f"GT-{random.randint(10000,99999)}"
                                    )
                                    _g_payload["job_order_no"]              = _g_gen_no
                                    _g_payload["material_description_rows"] = _rows_for_pdf
                                    _g_submitted.append(_g_payload)
                                except Exception as _gbe:
                                    st.error(f"Failed to insert garment item: {str(_gbe)}")
                                    _g_batch_err = True
                                    break
                            if not _g_batch_err and _g_submitted:
                                st.session_state.last_raised_garment_batch = _g_submitted
                                st.session_state.last_raised_batch          = []
                                st.session_state.garment_cart_items         = []
                                st.session_state.garment_cart_client_name   = ""
                                st.session_state.garment_cart_client_phone  = ""
                                st.session_state.editing_garment_cart_idx   = None
                                _g_notif = _g_submitted[0].copy()
                                _g_notif['total_amount'] = sum(o.get('total_amount', 0) for o in _g_submitted)
                                send_resend_notification(_g_notif)
                                st.toast(f"✅ Garment batch of {len(_g_submitted)} item(s) submitted to authorization queue.", icon="🧵")
                                st.rerun()
                with _gclr_col:
                    if st.button("🗑 Clear Cart", use_container_width=True, key="gclear_cart"):
                        st.session_state.garment_cart_items        = []
                        st.session_state.garment_cart_client_name  = ""
                        st.session_state.garment_cart_client_phone = ""
                        st.session_state.editing_garment_cart_idx  = None
                        st.rerun()

            if st.session_state.last_raised_garment_batch:
                st.markdown("<br>", unsafe_allow_html=True)
                _g_batch = st.session_state.last_raised_garment_batch
                st.markdown(
                    f'<div style="background:linear-gradient(135deg,#f0fdf4,#dcfce7);'
                    f'border:1px solid #86efac;border-radius:12px;'
                    f'padding:1.25rem 1.5rem;margin-bottom:1.25rem;">'
                    f'<div style="font-size:0.75rem;font-weight:700;color:#166534;'
                    f'text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.35rem;">'
                    f'Garment Batch Submission Confirmed</div>'
                    f'<div style="font-size:1.1rem;font-weight:800;color:#0f172a;">'
                    f'{len(_g_batch)} garment item(s) deposited in management authorization ledger</div>'
                    f'<div style="font-size:0.82rem;color:#15803d;margin-top:0.2rem;">'
                    f'Batch Ref: <strong>{_g_batch[0].get("parent_group_id","—")}</strong>'
                    f' &nbsp;·&nbsp; Client: <strong>{_g_batch[0].get("customer_name","—")}</strong>'
                    f'</div></div>', unsafe_allow_html=True)
                for _gb_idx, _gb_ticket in enumerate(_g_batch):
                    _gb_preview = _gb_ticket.get('job_description','')[:60] + ("…" if len(_gb_ticket.get('job_description','')) > 60 else "")
                    st.markdown(
                        f'<div style="background:#ffffff;border:1px solid #e2e8f0;'
                        f'border-left:4px solid #f59e0b;border-radius:8px;'
                        f'padding:0.75rem 1rem;margin-bottom:0.5rem;'
                        f'display:flex;align-items:center;justify-content:space-between;">'
                        f'<div>'
                        f'<div style="font-weight:700;color:#0f172a;font-size:0.9rem;">Item {_gb_idx+1}: {_gb_preview}</div>'
                        f'<div style="font-size:0.78rem;color:#64748b;margin-top:0.15rem;">'
                        f'Ref: <strong style="color:#d97706;">{_gb_ticket.get("job_order_no","PENDING")}</strong>'
                        f' &nbsp;·&nbsp; {_gb_ticket.get("qty_to_print",0):,} units'
                        f' &nbsp;·&nbsp; {_gb_ticket.get("print_type","")}'
                        f' &nbsp;·&nbsp; {CURRENCY} {_gb_ticket.get("total_amount",0):,.2f}'
                        f'</div></div></div>', unsafe_allow_html=True)
                    _gb_pdf = generate_garment_pdf_manifest(_gb_ticket)
                    st.download_button(
                        label=f"📄 Export Garment PDF — Item {_gb_idx+1}: {_gb_ticket.get('job_order_no','PENDING')}",
                        data=_gb_pdf,
                        file_name=f"GarmentManifest_{_gb_ticket.get('job_order_no','PENDING')}.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                        key=f"dl_garment_batch_{_gb_idx}"
                    )

# ═══════════════════════════════════════════════════════════════════
# ROUTE 3: AUTHORIZATION CENTER — GROUPED LINE-ITEM APPROVALS (dept-aware)
# ═══════════════════════════════════════════════════════════════════
elif app_mode == "Authorization Center" and is_admin:

    # ── Manager identity ──────────────────────────────────────────────────────
    _ac_prof = st.session_state.get('user_profile')
    _ac_fullname = (
        _ac_prof.get('full_name', st.session_state.get('user_email', 'Guest'))
        if _ac_prof else st.session_state.get('user_email', 'Guest')
    )

    st.markdown(
        '<div class="section-header">Executive Authorization Control Panel</div>',
        unsafe_allow_html=True,
    )

    # ── UPGRADE 4 — Cached Supabase fetch ─────────────────────────────────────
    # Authentication guard lives here, NOT inside the cached function.
    if supabase and st.session_state.get("authenticated"):
        pending_orders = fetch_pending_orders_cached()
    else:
        pending_orders = pd.DataFrame()

    if pending_orders.empty:
        st.info("No pending job contracts requiring authorization.")
    else:
        # ── Chip renderer (moved outside the loop — defined once) ─────────────
        def render_chips(value_str):
            if not value_str or str(value_str).strip().lower() in ('none', '-', ''):
                return (
                    '<span style="color:#94a3b8;font-size:0.8rem;'
                    'font-style:italic;">None selected</span>'
                )
            chips = ''
            for item in [v.strip() for v in str(value_str).split(',') if v.strip()]:
                chips += (
                    f'<span style="display:inline-block;background:#0f172a;'
                    f'color:#ffffff;font-size:0.72rem;font-weight:600;'
                    f'padding:0.2rem 0.55rem;border-radius:9999px;'
                    f'margin:0.15rem;">{item}</span>'
                )
            return chips

        # ── UPGRADE 3 — In-Memory Search & Filter bar ─────────────────────────
        # Zero Supabase round-trips: all filtering happens on the DataFrame
        # that is already in memory from the cached fetch above.
        _fi_c1, _fi_c2, _fi_c3 = st.columns([3, 2, 1])
        with _fi_c1:
            _search_text = st.text_input(
                "Search orders",
                placeholder="Customer Name · Order No · Batch Ref…",
                key="ac_search",
                label_visibility="collapsed",
            )
        with _fi_c2:
            st.markdown('<div style="font-size:0.7rem;color:#64748b;margin-bottom:0.15rem;">Filter by status</div>',
                        unsafe_allow_html=True)
            _sf1, _sf2 = st.columns(2)
            _show_pending  = _sf1.checkbox("Pending Approval", value=True, key="ac_status_pending")
            _show_revision = _sf2.checkbox("Pending Revision", value=True, key="ac_status_revision")
            _status_filter = []
            if _show_pending:  _status_filter.append("Pending Approval")
            if _show_revision: _status_filter.append("Pending Revision Approval")
        with _fi_c3:
            if st.button("🔄 Refresh", use_container_width=True, key="ac_cache_refresh"):
                # Manual cache bust — useful after an upstream data change
                # that occurred within the 20-second TTL window.
                fetch_pending_orders_cached.clear()
                st.rerun()

        # Apply status pill filter (O(n) Pandas mask, no network cost)
        if _status_filter:
            pending_orders = pending_orders[
                pending_orders['status'].isin(_status_filter)
            ].copy()

        # Apply free-text search across three columns (no ilike, pure Pandas)
        if _search_text.strip():
            _q = _search_text.strip().lower()
            _mask = (
                pending_orders['customer_name']
                    .fillna('').str.lower().str.contains(_q, regex=False)
                | pending_orders['job_order_no']
                    .fillna('').str.lower().str.contains(_q, regex=False)
                | pending_orders['parent_group_id']
                    .fillna('').str.lower().str.contains(_q, regex=False)
            )
            pending_orders = pending_orders[_mask].copy()

        if pending_orders.empty:
            st.info(
                "No orders match your search or filter. "
                "Clear the filters above to see all pending contracts."
            )
        else:
            # ── Build ordered group list (identical logic to original) ─────────
            pending_orders['_group_key'] = pending_orders.apply(
                lambda row: (
                    str(row.get('parent_group_id') or '').strip()
                    or f"SOLO_{row['id']}"
                ),
                axis=1,
            )
            if 'created_at' in pending_orders.columns:
                pending_orders = pending_orders.sort_values(
                    'created_at', ascending=True
                ).reset_index(drop=True)

            _seen_groups: list = []
            for _gk in pending_orders['_group_key']:
                if _gk not in _seen_groups:
                    _seen_groups.append(_gk)

            # ── UPGRADE 5 — Pagination by group (not by raw row) ──────────────
            # Hard ceiling: 40 groups per page.  At 10 line items per group
            # worst-case that is 400 cards — still never renders them because
            # they are collapsed inside expanders (Upgrade 2).
            AC_GROUPS_PER_PAGE = 40
            _total_groups = len(_seen_groups)
            _total_pages  = max(1, (_total_groups + AC_GROUPS_PER_PAGE - 1)
                                     // AC_GROUPS_PER_PAGE)

            # Clamp cursor — filters may shrink the group count mid-session
            if st.session_state.ac_page >= _total_pages:
                st.session_state.ac_page = 0

            # ── Pagination strip ───────────────────────────────────────────────
            _pc1, _pc2, _pc3, _pc4, _pc5 = st.columns([1.5, 1, 2, 1, 1.5])
            with _pc2:
                if st.button(
                    "◀ Prev",
                    key="ac_prev_btn",
                    disabled=(st.session_state.ac_page == 0),
                    use_container_width=True,
                ):
                    st.session_state.ac_page -= 1
                    st.rerun()
            with _pc3:
                st.markdown(
                    f'<div style="text-align:center;padding:0.4rem 0;'
                    f'font-size:0.82rem;color:#64748b;">'
                    f'Page&nbsp;<b>{st.session_state.ac_page + 1}</b>'
                    f'&nbsp;/&nbsp;{_total_pages}'
                    f'&nbsp;&nbsp;·&nbsp;&nbsp;'
                    f'<b>{_total_groups}</b>&nbsp;group(s)</div>',
                    unsafe_allow_html=True,
                )
            with _pc4:
                if st.button(
                    "Next ▶",
                    key="ac_next_btn",
                    disabled=(st.session_state.ac_page >= _total_pages - 1),
                    use_container_width=True,
                ):
                    st.session_state.ac_page += 1
                    st.rerun()

            st.markdown(
                "<div style='height:0.25rem;'></div>", unsafe_allow_html=True
            )

            # Slice to the groups that belong to the current page
            _page_start  = st.session_state.ac_page * AC_GROUPS_PER_PAGE
            _page_groups = _seen_groups[_page_start: _page_start + AC_GROUPS_PER_PAGE]

            # ══════════════════════════════════════════════════════════════════
            # PER-GROUP RENDER LOOP
            # ══════════════════════════════════════════════════════════════════
            for _group_key in _page_groups:
                _group_df      = pending_orders[
                    pending_orders['_group_key'] == _group_key
                ].copy()
                _first_row     = _group_df.iloc[0]
                _grp_customer  = str(_first_row.get('customer_name',    '—') or '—')
                _grp_telephone = str(_first_row.get('telephone_number', '—') or '—')
                _grp_is_multi  = (
                    len(_group_df) > 1 or not _group_key.startswith('SOLO_')
                )
                _grp_has_rev   = (
                    _group_df['status'].str.strip()
                    .eq('Pending Revision Approval').any()
                )
                _grp_is_solo   = _group_key.startswith('SOLO_')
                _grp_batch_ref = (
                    _group_key if not _grp_is_solo else 'Individual Submission'
                )
                _grp_total_val = (
                    _group_df['total_amount']
                    .fillna(0).apply(lambda x: float(x or 0)).sum()
                )
                _grp_has_garment = _group_df.apply(_is_garment, axis=1).any()
                _grp_all_garment = _group_df.apply(_is_garment, axis=1).all()
                _grp_dept_badge  = (
                    '🧵 GARMENT'      if _grp_has_garment and not _grp_all_garment
                    else '🧵 GARMENT DEPT' if _grp_has_garment
                    else '🖨 PRESS DEPT'
                )
                _item_count = len(_group_df)

                # ── UPGRADE 2 — Group header card (always visible, O(groups)) ──
                # This is the only thing rendered when the expander is closed.
                # DOM cost at closed state: O(groups) instead of
                # O(groups × line_items × card_weight).
                _badge = (
                    f"{_item_count} LINE ITEM(S)" if _grp_is_multi
                    else "INDIVIDUAL ORDER"
                )
                _rev_flag = (
                    ' &nbsp;⚠️ <span style="color:#fbbf24;font-size:0.72rem;'
                    'font-weight:700;">REVISED</span>'
                    if _grp_has_rev else ''
                )
                st.markdown(
                    f'<div style="background:#0f172a;color:#ffffff;'
                    f'border-radius:12px;padding:1.25rem 1.5rem;'
                    f'margin-bottom:0.4rem;margin-top:1rem;'
                    f'display:flex;justify-content:space-between;align-items:center;">'
                    f'<div>'
                    f'<div style="font-size:0.65rem;font-weight:700;color:#94a3b8;'
                    f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:0.2rem;">'
                    f'CLIENT SUBMISSION — {_badge} — {_grp_dept_badge}{_rev_flag}</div>'
                    f'<div style="font-size:1.35rem;font-weight:800;'
                    f'letter-spacing:-0.01em;">{_grp_customer}</div>'
                    f'<div style="font-size:0.82rem;color:#94a3b8;margin-top:0.2rem;">'
                    f'Tel: {_grp_telephone}&nbsp;·&nbsp;Batch Ref: '
                    f'<span style="color:#60a5fa;">{_grp_batch_ref}</span></div>'
                    f'</div>'
                    f'<div style="text-align:right;">'
                    f'<div style="font-size:0.62rem;color:#94a3b8;'
                    f'text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.2rem;">'
                    f'Combined Contract Value</div>'
                    f'<div style="font-size:1.35rem;font-weight:800;color:#34d399;">'
                    f'{CURRENCY} {_grp_total_val:,.2f}</div>'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )

                # Revision warning banner (still outside expander — managers must
                # see it before they even open the group)
                if _grp_has_rev:
                    st.markdown(
                        '<div style="background:linear-gradient(135deg,#fffbeb,#fef3c7);'
                        'border:2px solid #f59e0b;border-left:6px solid #d97706;'
                        'border-radius:10px;padding:0.85rem 1.25rem;'
                        'margin-bottom:0.4rem;'
                        'display:flex;align-items:flex-start;gap:0.85rem;">'
                        '<div style="font-size:1.6rem;flex-shrink:0;margin-top:-2px;">⚠️</div>'
                        '<div>'
                        '<div style="font-size:0.78rem;font-weight:700;color:#92400e;'
                        'text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.3rem;">'
                        'ATTENTION: REVISED CONTRACT</div>'
                        '<div style="font-size:0.875rem;color:#78350f;line-height:1.55;">'
                        'One or more line items in this submission were previously Approved '
                        'and have since been modified by an administrator. Original Job Order '
                        'references and Batch tracking IDs are preserved. Please review all '
                        'amended specifications carefully before re-authorizing.'
                        '</div></div></div>',
                        unsafe_allow_html=True,
                    )

                # ── UPGRADE 2 — Line items collapsed by default ────────────────
                _exp_label = (
                    f"📋 {_item_count} line item(s) — {_grp_customer}"
                    + (" · ⚠️ includes REVISED items" if _grp_has_rev else "")
                )
                with st.expander(_exp_label, expanded=False):

                    # ────────────────────────────────────────────────────────────
                    # PER-LINE-ITEM RENDER LOOP  (inside the expander)
                    # ────────────────────────────────────────────────────────────
                    for _item_pos, (_li_idx, _li_row) in enumerate(
                        _group_df.iterrows()
                    ):
                        _li_id          = _li_row['id']
                        _li_total       = float(_li_row.get('total_amount',    0) or 0)
                        _li_deposit     = float(_li_row.get('deposit_amount',  0) or 0)
                        _li_outstanding = _li_total - _li_deposit
                        _li_customer    = str(_li_row.get('customer_name',     '—') or '—')
                        _li_order_no    = str(_li_row.get('job_order_no',      'PENDING') or 'PENDING')
                        _li_description = str(_li_row.get('job_description',   '—') or '—')
                        _li_created_by  = str(_li_row.get('created_by',        '—') or '—')
                        _li_delivery    = str(_li_row.get('delivery_mode',     '—') or '—')
                        _li_collection  = str(_li_row.get('date_of_collection','—') or '—')
                        _li_type_print  = str(_li_row.get('type_of_print',     '—') or '—')
                        _li_mat_source  = str(_li_row.get('material_source',   '—') or '—')
                        _li_qty         = int(_li_row.get('qty_to_print',      0)   or 0)
                        _li_status      = str(_li_row.get('status',            '')   or '')
                        _li_is_revised  = _li_status.strip() == 'Pending Revision Approval'
                        _li_bal_color   = "#ef4444" if _li_outstanding > 0 else "#10b981"
                        _li_bal_label   = (
                            "Outstanding Debt Balance" if _li_outstanding > 0
                            else "Fully Settled"
                        )
                        _li_is_garment  = _is_garment(_li_row.to_dict())
                        _card_border    = (
                            "4px solid #f59e0b" if _li_is_revised
                            else "1px solid #e2e8f0"
                        )

                        # Line-item position label (multi-group only)
                        _li_item_label = ""
                        if _grp_is_multi:
                            _rev_badge = (
                                ' &nbsp;<span style="background:#fef3c7;color:#92400e;'
                                'font-size:0.6rem;font-weight:700;padding:0.1rem 0.4rem;'
                                'border-radius:4px;border:1px solid #f59e0b;">REVISED</span>'
                                if _li_is_revised else ''
                            )
                            _dept_chip = (
                                ' &nbsp;<span style="background:#fef3c7;color:#92400e;'
                                'font-size:0.6rem;font-weight:700;padding:0.1rem 0.4rem;'
                                'border-radius:4px;">🧵 GARMENT</span>'
                                if _li_is_garment else
                                ' &nbsp;<span style="background:#e0f2fe;color:#0369a1;'
                                'font-size:0.6rem;font-weight:700;padding:0.1rem 0.4rem;'
                                'border-radius:4px;">🖨 PRESS</span>'
                            )
                            _li_item_label = (
                                f'<div style="font-size:0.68rem;font-weight:700;'
                                f'color:#64748b;text-transform:uppercase;'
                                f'letter-spacing:0.06em;margin-bottom:0.6rem;">'
                                f'LINE ITEM {_item_pos + 1} OF {_item_count}'
                                f'{_rev_badge}{_dept_chip}</div>'
                            )

                        # Financial matrix HTML
                        _financial_html = (
                            f'<div style="font-size:0.7rem;font-weight:700;color:#64748b;'
                            f'text-transform:uppercase;letter-spacing:0.08em;'
                            f'margin-bottom:0.6rem;">Financial Matrix</div>'
                            f'<div style="display:grid;grid-template-columns:1fr 1fr 1fr;'
                            f'gap:0.75rem;margin-bottom:1.25rem;">'
                            # Contract value
                            f'<div style="background:linear-gradient(135deg,#eff6ff,#dbeafe);'
                            f'border:1px solid #bfdbfe;border-radius:8px;padding:0.85rem 1rem;">'
                            f'<div style="font-size:0.68rem;font-weight:700;color:#1d4ed8;'
                            f'text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.2rem;">'
                            f'Aggregate Contract Value</div>'
                            f'<div style="font-size:1.2rem;font-weight:800;color:#1e40af;">'
                            f'{CURRENCY} {_li_total:,.2f}</div></div>'
                            # Deposit
                            f'<div style="background:linear-gradient(135deg,#f0fdf4,#dcfce7);'
                            f'border:1px solid #bbf7d0;border-radius:8px;padding:0.85rem 1rem;">'
                            f'<div style="font-size:0.68rem;font-weight:700;color:#15803d;'
                            f'text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.2rem;">'
                            f'Cash Deposit Paid</div>'
                            f'<div style="font-size:1.2rem;font-weight:800;color:#166534;">'
                            f'{CURRENCY} {_li_deposit:,.2f}</div></div>'
                            # Balance
                            f'<div style="background:linear-gradient(135deg,#fff1f2,#ffe4e6);'
                            f'border:1px solid #fecdd3;border-radius:8px;padding:0.85rem 1rem;">'
                            f'<div style="font-size:0.68rem;font-weight:700;'
                            f'color:{_li_bal_color};text-transform:uppercase;'
                            f'letter-spacing:0.06em;margin-bottom:0.2rem;">{_li_bal_label}</div>'
                            f'<div style="font-size:1.2rem;font-weight:800;'
                            f'color:{_li_bal_color};">'
                            f'{CURRENCY} {_li_outstanding:,.2f}</div></div>'
                            f'</div>'
                        )

                        # Logistics row HTML
                        _logistics_html = (
                            f'<div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;'
                            f'gap:0.75rem;margin-bottom:1.25rem;">'
                            f'<div style="background:#f8fafc;border:1px solid #e2e8f0;'
                            f'border-radius:8px;padding:0.75rem 1rem;">'
                            f'<div style="font-size:0.65rem;font-weight:700;color:#94a3b8;'
                            f'text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.2rem;">'
                            f'Account Executive</div>'
                            f'<div style="font-size:0.85rem;font-weight:600;color:#1e293b;">'
                            f'{_li_created_by}</div></div>'
                            f'<div style="background:#f8fafc;border:1px solid #e2e8f0;'
                            f'border-radius:8px;padding:0.75rem 1rem;">'
                            f'<div style="font-size:0.65rem;font-weight:700;color:#94a3b8;'
                            f'text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.2rem;">'
                            f'Delivery Mode</div>'
                            f'<div style="font-size:0.85rem;font-weight:600;color:#1e293b;">'
                            f'{_li_delivery}</div></div>'
                            f'<div style="background:#f8fafc;border:1px solid #e2e8f0;'
                            f'border-radius:8px;padding:0.75rem 1rem;">'
                            f'<div style="font-size:0.65rem;font-weight:700;color:#94a3b8;'
                            f'text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.2rem;">'
                            f'Collection Date</div>'
                            f'<div style="font-size:0.85rem;font-weight:600;color:#0369a1;">'
                            f'{_li_collection}</div></div>'
                            f'<div style="background:#f8fafc;border:1px solid #e2e8f0;'
                            f'border-radius:8px;padding:0.75rem 1rem;">'
                            f'<div style="font-size:0.65rem;font-weight:700;color:#94a3b8;'
                            f'text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.2rem;">'
                            f'Print Qty / Source</div>'
                            f'<div style="font-size:0.85rem;font-weight:600;color:#1e293b;">'
                            f'{_li_qty:,} — {_li_mat_source}</div></div>'
                            f'</div>'
                        )

                        # Dept-specific spec section
                        if _li_is_garment:
                            _pt   = str(_li_row.get('print_type',         '—') or _li_type_print)
                            _ydg  = str(_li_row.get('yardage',            '—') or '—')
                            _psz  = str(_li_row.get('print_size',         '—') or '—')
                            _fsz  = str(_li_row.get('finished_print_size','—') or '—')
                            _proc = str(_li_row.get('process_info',       '—') or '—')
                            _pkgm = str(_li_row.get('packaging_mode',     '—') or '—')
                            _spec_section = (
                                f'<div style="font-size:0.7rem;font-weight:700;color:#64748b;'
                                f'text-transform:uppercase;letter-spacing:0.08em;'
                                f'margin-bottom:0.6rem;">🧵 Garment Specifications</div>'
                                f'<div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;'
                                f'gap:0.75rem;margin-bottom:1.25rem;">'
                                f'<div style="background:#fffbeb;border:1px solid #fde68a;'
                                f'border-radius:8px;padding:0.75rem 1rem;">'
                                f'<div style="font-size:0.65rem;font-weight:700;color:#92400e;'
                                f'text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.2rem;">'
                                f'Print Type</div>'
                                f'<div style="font-size:0.9rem;font-weight:600;color:#1e293b;">'
                                f'{_pt}</div></div>'
                                f'<div style="background:#fffbeb;border:1px solid #fde68a;'
                                f'border-radius:8px;padding:0.75rem 1rem;">'
                                f'<div style="font-size:0.65rem;font-weight:700;color:#92400e;'
                                f'text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.2rem;">'
                                f'Yardage / Fin. Size</div>'
                                f'<div style="font-size:0.9rem;font-weight:600;color:#1e293b;">'
                                f'{_ydg or _fsz}</div></div>'
                                f'<div style="background:#fffbeb;border:1px solid #fde68a;'
                                f'border-radius:8px;padding:0.75rem 1rem;">'
                                f'<div style="font-size:0.65rem;font-weight:700;color:#92400e;'
                                f'text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.2rem;">'
                                f'Print Size</div>'
                                f'<div style="font-size:0.9rem;font-weight:600;color:#1e293b;">'
                                f'{_psz}</div></div>'
                                f'<div style="background:#fffbeb;border:1px solid #fde68a;'
                                f'border-radius:8px;padding:0.75rem 1rem;">'
                                f'<div style="font-size:0.65rem;font-weight:700;color:#92400e;'
                                f'text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.2rem;">'
                                f'Packaging Mode</div>'
                                f'<div style="font-size:0.9rem;font-weight:600;color:#1e293b;">'
                                f'{_pkgm}</div></div>'
                                f'</div>'
                                f'<div style="font-size:0.7rem;font-weight:700;color:#64748b;'
                                f'text-transform:uppercase;letter-spacing:0.08em;'
                                f'margin-bottom:0.4rem;">Process / Technical Info</div>'
                                f'<div style="background:#fffbeb;border:1px solid #fde68a;'
                                f'border-radius:8px;padding:0.85rem 1rem;font-size:0.9rem;'
                                f'color:#1e293b;line-height:1.6;white-space:pre-wrap;'
                                f'margin-bottom:1.25rem;">{_proc}</div>'
                            )
                        else:
                            # PRESS spec section
                            _li_paper_type   = str(_li_row.get('paper_type',        '—') or '—')
                            _li_gsm          = str(_li_row.get('gsm',               '—') or '—')
                            _li_paper_size   = str(_li_row.get('paper_size',        '—') or '—')
                            _li_paper_colour = str(_li_row.get('paper_colour',      '—') or '—')
                            _li_impressions  = str(_li_row.get('impressions_colour','—') or '—')
                            _li_binding      = str(_li_row.get('binding_type',      'None') or 'None')
                            _li_laminating   = str(_li_row.get('laminating_type',   'None') or 'None')
                            _li_bind_chips   = render_chips(_li_binding)
                            _li_lam_chips    = render_chips(_li_laminating)
                            _spec_section = (
                                f'<div style="font-size:0.7rem;font-weight:700;color:#64748b;'
                                f'text-transform:uppercase;letter-spacing:0.08em;'
                                f'margin-bottom:0.6rem;">'
                                f'🖨 Material &amp; Substrate Properties</div>'
                                f'<div style="display:grid;'
                                f'grid-template-columns:2fr 1fr 1fr 1fr;'
                                f'gap:0.75rem;margin-bottom:1.25rem;">'
                                f'<div style="background:#f8fafc;border:1px solid #e2e8f0;'
                                f'border-radius:8px;padding:0.75rem 1rem;">'
                                f'<div style="font-size:0.65rem;font-weight:700;color:#94a3b8;'
                                f'text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.2rem;">'
                                f'Stock Paper Type</div>'
                                f'<div style="font-size:0.9rem;font-weight:600;color:#1e293b;">'
                                f'{_li_paper_type}</div></div>'
                                f'<div style="background:#f8fafc;border:1px solid #e2e8f0;'
                                f'border-radius:8px;padding:0.75rem 1rem;">'
                                f'<div style="font-size:0.65rem;font-weight:700;color:#94a3b8;'
                                f'text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.2rem;">'
                                f'GSM</div>'
                                f'<div style="font-size:0.9rem;font-weight:600;color:#1e293b;">'
                                f'{_li_gsm}</div></div>'
                                f'<div style="background:#f8fafc;border:1px solid #e2e8f0;'
                                f'border-radius:8px;padding:0.75rem 1rem;">'
                                f'<div style="font-size:0.65rem;font-weight:700;color:#94a3b8;'
                                f'text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.2rem;">'
                                f'Paper Size</div>'
                                f'<div style="font-size:0.9rem;font-weight:600;color:#1e293b;">'
                                f'{_li_paper_size}</div></div>'
                                f'<div style="background:#f8fafc;border:1px solid #e2e8f0;'
                                f'border-radius:8px;padding:0.75rem 1rem;">'
                                f'<div style="font-size:0.65rem;font-weight:700;color:#94a3b8;'
                                f'text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.2rem;">'
                                f'Colour / Impression</div>'
                                f'<div style="font-size:0.9rem;font-weight:600;color:#1e293b;">'
                                f'{_li_paper_colour} — {_li_impressions}</div></div>'
                                f'</div>'
                                f'<div style="font-size:0.7rem;font-weight:700;color:#64748b;'
                                f'text-transform:uppercase;letter-spacing:0.08em;'
                                f'margin-bottom:0.6rem;">Post-Press &amp; Finishing</div>'
                                f'<div style="display:grid;grid-template-columns:1fr 1fr;'
                                f'gap:0.75rem;margin-bottom:1.25rem;">'
                                f'<div style="background:#f8fafc;border:1px solid #e2e8f0;'
                                f'border-radius:8px;padding:0.75rem 1rem;">'
                                f'<div style="font-size:0.65rem;font-weight:700;color:#94a3b8;'
                                f'text-transform:uppercase;letter-spacing:0.06em;'
                                f'margin-bottom:0.4rem;">Binding</div>'
                                f'<div>{_li_bind_chips}</div></div>'
                                f'<div style="background:#f8fafc;border:1px solid #e2e8f0;'
                                f'border-radius:8px;padding:0.75rem 1rem;">'
                                f'<div style="font-size:0.65rem;font-weight:700;color:#94a3b8;'
                                f'text-transform:uppercase;letter-spacing:0.06em;'
                                f'margin-bottom:0.4rem;">Laminating</div>'
                                f'<div>{_li_lam_chips}</div></div>'
                                f'</div>'
                            )

                        # Dept badge for card header
                        _hdr_dept_badge = (
                            f'<div style="display:inline-block;background:#fef3c7;'
                            f'color:#92400e;font-size:0.72rem;font-weight:700;'
                            f'padding:0.25rem 0.7rem;border-radius:8px;'
                            f'border:1px solid #fde68a;margin-top:0.4rem;">🧵 GARMENT</div>'
                            if _li_is_garment else
                            f'<div style="display:inline-block;background:#e0f2fe;'
                            f'color:#0369a1;font-size:0.72rem;font-weight:700;'
                            f'padding:0.25rem 0.7rem;border-radius:8px;'
                            f'border:1px solid #bae6fd;margin-top:0.4rem;">🖨 PRESS</div>'
                        )

                        # ── Main line-item card (HTML — unchanged visually) ────
                        st.markdown(
                            f'<div style="background:#ffffff;border:1px solid #e2e8f0;'
                            f'border-left:{_card_border};border-radius:12px;padding:2rem;'
                            f'margin-bottom:1rem;'
                            f'box-shadow:0 4px 6px -1px rgba(15,23,42,0.05);">'
                            + _li_item_label
                            + f'<div style="display:flex;justify-content:space-between;'
                            f'align-items:flex-start;border-bottom:2px solid #0f172a;'
                            f'padding-bottom:1rem;margin-bottom:1.25rem;">'
                            f'<div>'
                            f'<div style="font-size:0.7rem;font-weight:700;color:#94a3b8;'
                            f'text-transform:uppercase;letter-spacing:0.08em;'
                            f'margin-bottom:0.25rem;">Pending Authorization</div>'
                            f'<div style="font-size:1.5rem;font-weight:800;color:#0f172a;'
                            f'letter-spacing:-0.02em;">{_li_customer}</div>'
                            f'<div style="font-size:0.85rem;font-weight:600;color:#64748b;'
                            f'margin-top:0.15rem;">Order Ref: '
                            f'<span style="color:#0369a1;">{_li_order_no}</span></div>'
                            f'</div>'
                            f'<div style="text-align:right;">'
                            f'<div style="font-size:0.7rem;font-weight:700;color:#94a3b8;'
                            f'text-transform:uppercase;letter-spacing:0.08em;'
                            f'margin-bottom:0.2rem;">Print Category</div>'
                            f'<div style="display:inline-block;background:#f1f5f9;'
                            f'color:#334155;font-size:0.8rem;font-weight:700;'
                            f'padding:0.3rem 0.8rem;border-radius:8px;'
                            f'border:1px solid #e2e8f0;">{_li_type_print}</div>'
                            f'{_hdr_dept_badge}'
                            f'</div></div>'
                            + _financial_html
                            + _spec_section
                            + _logistics_html
                            + f'<div style="font-size:0.7rem;font-weight:700;color:#64748b;'
                            f'text-transform:uppercase;letter-spacing:0.08em;'
                            f'margin-bottom:0.4rem;">Job Description</div>'
                            f'<div style="background:#f8fafc;border:1px solid #e2e8f0;'
                            f'border-radius:8px;padding:0.85rem 1rem;font-size:0.9rem;'
                            f'color:#1e293b;line-height:1.6;'
                            f'white-space:pre-wrap;">{_li_description}</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

                        # ── UPGRADE 1 — Form-wrapped action controls ───────────
                        # Wrapping in st.form means typing in the Notes field
                        # does NOT trigger a Streamlit rerun.  The app state only
                        # updates when the manager clicks a submit button.
                        #
                        # Two submit buttons in one form is valid Streamlit:
                        # only the clicked button returns True; the other is False.
                        with st.form(key=f"line_form_{_li_id}"):
                            _li_notes = st.text_input(
                                "Reason for Rejection (required to reject)",
                                key=f"ac_note_{_li_id}",
                                placeholder="Enter management rejection rationale…",
                            )
                            _fc1, _fc2 = st.columns([1, 3])
                            with _fc1:
                                _approve_submitted = st.form_submit_button(
                                    "✓ Approve Order",
                                    type="primary",
                                    use_container_width=True,
                                )
                                _reject_submitted = st.form_submit_button(
                                    "✗ Reject / Return",
                                    use_container_width=True,
                                )

                            # ── UPGRADE 4 — Cache invalidation on write ────────
                            # .clear() fires before st.rerun() so the very next
                            # render fetches a fresh DataFrame from Supabase,
                            # bypassing the 20-second TTL entirely.
                            if _approve_submitted:
                                try:
                                    from datetime import datetime as _dt, timezone as _tz
                                    _approval_ts = _dt.now(_tz.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
                                    _approval_payload = {
                                        "status":        "Approved",
                                        "approved_by":   _ac_fullname,
                                        "approval_date": _approval_ts,
                                    }
                                    try:
                                        supabase.table('job_orders').update(
                                            _approval_payload
                                        ).eq('id', _li_id).execute()
                                    except Exception:
                                        # approval_date column may not exist yet —
                                        # fall back to the two fields that always exist
                                        supabase.table('job_orders').update(
                                            {"status": "Approved", "approved_by": _ac_fullname}
                                        ).eq('id', _li_id).execute()
                                        _approval_ts = ''   # not persisted
                                    fetch_pending_orders_cached.clear()
                                    if hasattr(get_approved_orders_cached, 'clear'):
                                        get_approved_orders_cached.clear()
                                    if hasattr(get_archive_orders_cached, 'clear'):
                                        get_archive_orders_cached.clear()
                                    # ── Email notification to order creator ──
                                    try:
                                        _n_row = {}
                                        if not pending_orders.empty:
                                            _nm = pending_orders[pending_orders['id'] == _li_id]
                                            if not _nm.empty:
                                                _n_row = _nm.iloc[0].to_dict()
                                        _n_row['approved_by']   = _ac_fullname
                                        _n_row['approval_date'] = locals().get('_approval_ts', '')
                                        notify_order_approved(_n_row)
                                        notify_needs_scheduling(_n_row)
                                        send_departmental_alert(_n_row)
                                    except Exception:
                                        logger.exception(
                                            "notify_order_approved lookup/send failed for order id=%s.",
                                            _li_id,
                                        )
                                    st.success(
                                        f"Order {_li_order_no} approved and "
                                        f"released to production pipeline."
                                    )
                                    st.rerun()
                                except Exception as _ap_err:
                                    st.error(f"Approval failed: {str(_ap_err)}")

                            if _reject_submitted:
                                if not _li_notes.strip():
                                    st.error(
                                        "Please provide a rejection rationale "
                                        "before submitting."
                                    )
                                else:
                                    try:
                                        supabase.table('job_orders').update(
                                            {
                                                "status":         "Rejected",
                                                "rejection_note": _li_notes,
                                            }
                                        ).eq('id', _li_id).execute()
                                        fetch_pending_orders_cached.clear()
                                        # ── Email notification to order creator ──
                                        try:
                                            _rn_row = {}
                                            if not pending_orders.empty:
                                                _rm = pending_orders[pending_orders['id'] == _li_id]
                                                if not _rm.empty:
                                                    _rn_row = _rm.iloc[0].to_dict()
                                            _rn_row['rejection_note'] = _li_notes
                                            notify_order_rejected(_rn_row)
                                        except Exception:
                                            logger.exception(
                                                "notify_order_rejected lookup/send failed for order id=%s.",
                                                _li_id,
                                            )
                                        st.success(
                                            f"Order {_li_order_no} returned with "
                                            f"management notes appended."
                                        )
                                        st.rerun()
                                    except Exception as _rj_err:
                                        st.error(f"Rejection failed: {str(_rj_err)}")

                        st.markdown(
                            "<div style='height:0.5rem;'></div>",
                            unsafe_allow_html=True,
                        )
                    # ── end per-line-item loop ─────────────────────────────────
                # ── end expander ───────────────────────────────────────────────

                # Group divider (skip after the last group on the page)
                if _group_key != _page_groups[-1]:
                    st.markdown(
                        "<hr style='margin:1.75rem 0;border:none;"
                        "border-top:2px solid #f1f5f9;'>",
                        unsafe_allow_html=True,
                    )
            # ── end per-group loop ─────────────────────────────────────────────

            # Bottom pagination strip (mirrors the top one — saves scrolling)
            st.markdown(
                "<div style='height:0.75rem;'></div>", unsafe_allow_html=True
            )
            _bc1, _bc2, _bc3, _bc4, _bc5 = st.columns([1.5, 1, 2, 1, 1.5])
            with _bc2:
                if st.button(
                    "◀ Prev",
                    key="ac_prev_btn_bot",
                    disabled=(st.session_state.ac_page == 0),
                    use_container_width=True,
                ):
                    st.session_state.ac_page -= 1
                    st.rerun()
            with _bc3:
                st.markdown(
                    f'<div style="text-align:center;padding:0.4rem 0;'
                    f'font-size:0.82rem;color:#64748b;">'
                    f'Page&nbsp;<b>{st.session_state.ac_page + 1}</b>'
                    f'&nbsp;/&nbsp;{_total_pages}</div>',
                    unsafe_allow_html=True,
                )
            with _bc4:
                if st.button(
                    "Next ▶",
                    key="ac_next_btn_bot",
                    disabled=(st.session_state.ac_page >= _total_pages - 1),
                    use_container_width=True,
                ):
                    st.session_state.ac_page += 1
                    st.rerun()
        # ── end `if pending_orders.empty` branch ──────────────────────────────
    # ── end outer `if pending_orders.empty` branch ────────────────────────────

# ═══════════════════════════════════════════════════════════════════
# ROUTE 4: APPROVED ORDERS ARCHIVE — REVISION LIFECYCLE (dept-aware)
# ═══════════════════════════════════════════════════════════════════
elif app_mode == "Approved Orders Archive" and is_admin:
    st.markdown('<div class="section-header">Enterprise Ledger & Approved Orders Vault</div>',
                unsafe_allow_html=True)
    # ── Use cached multi-status fetch (30 s TTL) ─────────────────────────────
    approved_orders = (
        get_archive_orders_cached()
        if supabase and st.session_state.get("authenticated")
        else pd.DataFrame()
    )
    if approved_orders.empty:
        st.info("No approved job contracts currently sitting in archives.")
    else:
        # ── Lifecycle status tabs ─────────────────────────────────────────────
        _arch_by_status = {
            'Approved':             approved_orders[approved_orders['status'] == 'Approved'],
            'In Production':        approved_orders[approved_orders['status'] == 'In Production'],
            'Ready for Collection': approved_orders[approved_orders['status'] == 'Ready for Collection'],
            'Delivered':            approved_orders[approved_orders['status'] == 'Delivered'],
        }
        _atabs = st.tabs([
            f"Approved ({len(_arch_by_status['Approved'])})",
            f"In Production ({len(_arch_by_status['In Production'])})",
            f"Ready ({len(_arch_by_status['Ready for Collection'])})",
            f"Delivered ({len(_arch_by_status['Delivered'])})",
        ])

        def _render_archive_view(tab_df, status_label):
            if tab_df.empty:
                st.info(f"No orders with status '{status_label}'.")
                return
            _av = pd.DataFrame({
                "Order No":          tab_df["job_order_no"],
                "Customer":          tab_df["customer_name"],
                "Dept":              tab_df.apply(lambda r: 'GARMENT' if _is_garment(r) else 'PRESS', axis=1),
                f"Total ({CURRENCY})":   tab_df["total_amount"].fillna(0).apply(lambda x: float(x or 0)),
                f"Deposit ({CURRENCY})": tab_df["deposit_amount"].fillna(0).apply(lambda x: float(x or 0)),
                f"Balance ({CURRENCY})": (
                    tab_df["total_amount"].fillna(0).apply(lambda x: float(x or 0))
                    - tab_df["deposit_amount"].fillna(0).apply(lambda x: float(x or 0))
                ),
                "Collection":        tab_df["date_of_collection"],
                "Auth By":           tab_df["approved_by"],
            })
            st.dataframe(
                _av, use_container_width=True, hide_index=True,
                column_config={
                    f"Total ({CURRENCY})":   st.column_config.NumberColumn(format=f"{CURRENCY} %,.2f"),
                    f"Deposit ({CURRENCY})": st.column_config.NumberColumn(format=f"{CURRENCY} %,.2f"),
                    f"Balance ({CURRENCY})": st.column_config.NumberColumn(format=f"{CURRENCY} %,.2f"),
                })
            _csv_a = _av.to_csv(index=False).encode('utf-8')
            st.download_button(
                label=f"Export {status_label} CSV",
                data=_csv_a,
                file_name=f"ATP_{status_label.replace(' ','_')}_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv", key=f"arch_csv_{status_label}", use_container_width=False)

        with _atabs[0]: _render_archive_view(_arch_by_status['Approved'],             'Approved')
        with _atabs[1]: _render_archive_view(_arch_by_status['In Production'],        'In Production')
        with _atabs[2]: _render_archive_view(_arch_by_status['Ready for Collection'], 'Ready for Collection')
        with _atabs[3]: _render_archive_view(_arch_by_status['Delivered'],            'Delivered')

        st.markdown("<hr style='margin:2rem 0;'>", unsafe_allow_html=True)
        st.markdown("### Manage Archived Orders")
        _arch_search = st.text_input(
            "Search by order number or customer name",
            key="arch_manage_search",
            placeholder="e.g. P966102 or NUTRIFOODS — narrows the list below before you pick",
        )
        _arch_candidates = approved_orders
        if _arch_search.strip():
            _sq = _arch_search.strip().lower()
            _arch_candidates = approved_orders[
                approved_orders['job_order_no'].astype(str).str.lower().str.contains(_sq, na=False)
                | approved_orders['customer_name'].astype(str).str.lower().str.contains(_sq, na=False)
            ]
        elif len(approved_orders) >= ARCHIVE_ROW_CAP:
            st.caption(
                f"Showing the most recent {ARCHIVE_ROW_CAP:,} orders — this list is capped so the page stays "
                f"fast as history grows. If the order you need is older than that, search above, or use "
                f"Global Search in the sidebar, which searches the full history, not just this cap."
            )
        _arch_label_map = dict(zip(
            _arch_candidates['job_order_no'],
            _arch_candidates.apply(
                lambda r: f"{r.get('job_order_no','—')} — {r.get('customer_name','—')} · {r.get('status','—')}",
                axis=1
            )
        ))
        selected_order_no = st.selectbox(
            "Select Order Number to Modify, Export, or Delete:",
            [""] + _arch_candidates['job_order_no'].dropna().tolist(),
            format_func=lambda o: _arch_label_map.get(o, "—") if o else "— Select an order —",
        )
        if selected_order_no:
            target_row  = approved_orders[approved_orders['job_order_no'] == selected_order_no].iloc[0]
            _tr_status  = str(target_row.get('status', 'Approved') or 'Approved')
            _tr_total   = float(target_row.get('total_amount',  0) or 0)
            _tr_deposit = float(target_row.get('deposit_amount', 0) or 0)
            _tr_balance = _tr_total - _tr_deposit
            with st.expander(f"Order Operations: {selected_order_no}", expanded=True):

                # ── C12b-ii: Balance payment recording ───────────────────────
                if _tr_balance > 0:
                    st.markdown("<hr style='margin:1rem 0;border-top:1px solid #e2e8f0;'>",
                                unsafe_allow_html=True)
                    st.markdown("**💰 Record Balance Payment**")
                    st.markdown(
                        f'<div style="font-size:0.8rem;color:#64748b;">Outstanding Balance</div>'
                        f'<div style="font-size:1.25rem;font-weight:800;color:#ef4444;">'
                        f'{CURRENCY}{_tr_balance:,.2f}</div>',
                        unsafe_allow_html=True)
                    _bp1, _bp2 = st.columns([1, 1])
                    with _bp1:
                        _pay_amt = st.number_input(
                            "Payment Amount",
                            min_value=0.01, max_value=float(_tr_balance),
                            value=float(_tr_balance), step=100.0,
                            key=f"pay_amt_{selected_order_no}")
                    with _bp2:
                        _pay_receipt_no = st.text_input(
                            "Receipt Number",
                            key=f"pay_receipt_{selected_order_no}",
                            placeholder="e.g. RCT-00123 — optional, recommended for the audit trail")
                    if st.button("✓ Record Payment", key=f"pay_btn_{selected_order_no}",
                                 use_container_width=True, type="primary"):
                        _new_dep = _tr_deposit + _pay_amt
                        if record_balance_payment(str(target_row['id']), _new_dep, _pay_receipt_no):
                            st.success(
                                f"Payment of {CURRENCY}{_pay_amt:,.2f} recorded. "
                                f"New deposit total: {CURRENCY}{_new_dep:,.2f}")
                            st.rerun()
                        else:
                            st.error("Payment recording failed.")
                elif _tr_total > 0:
                    st.markdown(
                        f'<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:6px;'
                        f'padding:0.5rem 0.85rem;font-size:0.85rem;color:#15803d;font-weight:600;'
                        f'margin:0.5rem 0;">&#x2705; Fully Paid — {CURRENCY}{_tr_total:,.2f}</div>',
                        unsafe_allow_html=True)

                st.markdown("<hr style='margin:1rem 0;border-top:1px solid #e2e8f0;'>",
                            unsafe_allow_html=True)
                # Dept-aware PDF export
                _arch_pdf = dispatch_pdf_manifest(target_row.to_dict())
                _pdf_label = (
                    f"📄 EXPORT GARMENT PDF MANIFEST ({selected_order_no})"
                    if _is_garment(target_row.to_dict()) else
                    f"📄 EXPORT OFFICIAL PDF MANIFEST ({selected_order_no})"
                )
                st.download_button(
                    label=_pdf_label, data=_arch_pdf,
                    file_name=f"Manifest_{selected_order_no}.pdf",
                    mime="application/pdf", use_container_width=True, type="primary"
                )
                st.markdown("<br>", unsafe_allow_html=True)
                with st.form(key=f"edit_form_{target_row['id']}"):
                    st.markdown(
                        '<div style="font-size:1.1rem;font-weight:600;color:#0f172a;margin-bottom:1rem;">'
                        'Master Order Revision Interface</div>', unsafe_allow_html=True)
                    st.markdown(
                        '<div style="background:linear-gradient(135deg,#fffbeb,#fef3c7);'
                        'border:1px solid #fcd34d;border-left:4px solid #d97706;'
                        'border-radius:8px;padding:0.75rem 1rem;margin-bottom:1rem;">'
                        '<div style="font-size:0.72rem;font-weight:700;color:#92400e;'
                        'text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.2rem;">'
                        '⚠️ Revision Lifecycle Notice</div>'
                        '<div style="font-size:0.82rem;color:#78350f;">'
                        'Saving changes will move this order from <strong>Approved</strong> → '
                        '<strong>Pending Revision Approval</strong> and re-route it to the '
                        'Authorization Center for fresh management sign-off. The original '
                        'Job Order No. and Batch Reference are preserved for audit traceability.'
                        '</div></div>', unsafe_allow_html=True)
                    st.markdown("##### Commercial & Financial Data")
                    _e1, _e2 = st.columns(2)
                    e_amt = _e1.number_input(f"Total Contract Amount ({CURRENCY})",
                                             value=float(target_row['total_amount'] or 0), step=50.0)
                    e_dep = _e2.number_input(f"Deposit Received ({CURRENCY})",
                                             value=float(target_row['deposit_amount'] or 0), step=50.0)
                    st.markdown("##### Job Specifications")
                    _e3, _e4 = st.columns(2)
                    e_qty = _e3.number_input("Target Print Quantity",
                                             value=int(target_row['qty_to_print'] or 0), step=100)
                    _is_gmt_row = _is_garment(target_row.to_dict())
                    if _is_gmt_row:
                        _cat_list    = ["DTF", "Flexi Screen Print", "UV-DTF", "SAV", "Embroidery"]
                        _current_cat = str(target_row.get('type_of_print','') or target_row.get('print_type','') or '').strip()
                        if _current_cat not in _cat_list:
                            _cat_list.append(_current_cat)
                        e_cat = _e4.selectbox("Print Type",    _cat_list,
                                              index=_cat_list.index(_current_cat) if _current_cat in _cat_list else 0)
                    else:
                        _cat_list    = ["OFFSET", "DIGITAL PRESS", "PACKAGING"]
                        _current_cat = str(target_row.get('type_of_print','') or '').upper()
                        if _current_cat not in _cat_list:
                            _cat_list.append(_current_cat)
                        e_cat = _e4.selectbox("Category of Print", _cat_list,
                                              index=_cat_list.index(_current_cat) if _current_cat in _cat_list else 0)
                    st.markdown("<hr style='margin:1.5rem 0;border-top:1px solid #e2e8f0;'>", unsafe_allow_html=True)
                    _c_upd, _c_del = st.columns(2)
                    if _c_upd.form_submit_button("Save Changes", type="primary", use_container_width=True):
                        try:
                            supabase.table('job_orders').update({
                                "qty_to_print":  e_qty,
                                "total_amount":  e_amt,
                                "deposit_amount": e_dep,
                                "type_of_print": e_cat,
                                "status":        "Pending Revision Approval"
                            }).eq('id', target_row['id']).execute()
                            st.success(
                                f"✅ Order {selected_order_no} revised successfully. "
                                f"Status set to 'Pending Revision Approval' — removed from "
                                f"production archive and re-routed to Authorization Center "
                                f"for fresh management sign-off."
                            )
                            st.rerun()
                        except Exception as _upd_err:
                            st.error(f"Sync failed: {str(_upd_err)}")
                    if _c_del.form_submit_button("Delete Master Order", type="secondary", use_container_width=True):
                        try:
                            supabase.table('job_orders').delete().eq('id', target_row['id']).execute()
                            st.warning(f"Master Order {selected_order_no} permanently deleted from archive.")
                            st.rerun()
                        except Exception as _del_err:
                            st.error(f"Deletion failed: {str(_del_err)}")


# ═══════════════════════════════════════════════════════════════════
# ROUTE 4a: WAREHOUSE (receiving + finance handoff — see warehouse.py's
# module docstring for why this is separate from Dispatch)
# ═══════════════════════════════════════════════════════════════════
elif app_mode == "Warehouse":
    render_warehouse_module(
        get_db_job_orders_multi_status,
        notify_ready_for_finance,
        currency=CURRENCY,
    )

# ═══════════════════════════════════════════════════════════════════
# ROUTE 4a-b: DISPATCH (payment logging + finalize — runs alongside
# Approved Orders Archive's own lifecycle controls, same reasoning as
# Production Board above; see dispatch.py's module docstring)
# ═══════════════════════════════════════════════════════════════════
elif app_mode == "Dispatch":
    render_dispatch_module(
        get_db_job_orders_multi_status,
        update_order_lifecycle_status,
        record_balance_payment,
        currency=CURRENCY,
    )

# ═══════════════════════════════════════════════════════════════════
# ROUTE 4b: GLOBAL SEARCH RESULTS
# ═══════════════════════════════════════════════════════════════════
elif app_mode == "Search Results":
    _gsq = st.session_state.get("global_search_q", "").strip()
    st.markdown(
        f'<div class="section-header">&#x1F50D; Search Results'
        f'{"  —  " + _gsq if _gsq else ""}</div>',
        unsafe_allow_html=True)
    if not _gsq:
        st.info("Enter a search term in the sidebar search bar.")
    else:
        # PostgREST's .or_() takes a raw filter string, where comma and
        # parentheses are syntax, not literal characters — a search term
        # containing them would otherwise let a user reshape the filter's
        # logic (extra OR branches, malformed queries) rather than just
        # searching. Strip anything that isn't safe inside an ilike value.
        _gsq_safe = re.sub(r'[,()%]', ' ', _gsq).strip()
        _gs_df = pd.DataFrame()
        try:
            _gs_res = (
                supabase.table('job_orders')
                .select("*")
                .or_(f"job_order_no.ilike.%{_gsq_safe}%,customer_name.ilike.%{_gsq_safe}%,item_description.ilike.%{_gsq_safe}%")
                .order('created_at', desc=True)
                .limit(100)
                .execute()
            )
            if _gs_res.data:
                _gs_df = pd.DataFrame(_gs_res.data)
        except Exception:
            pass
        if _gs_df.empty:
            st.warning(f"No orders found matching **{_gsq}**.")
        else:
            st.markdown(f"**{len(_gs_df)} order(s) found.**")
            if len(_gs_df) >= 100:
                st.caption("Showing the top 100 matches, most recent first. Narrow your search (e.g. add more of the order number or customer name) to see others.")
            _GS_SC = {
                'Approved':'#10b981', 'Rejected':'#ef4444',
                'Pending Approval':'#f59e0b', 'Pending Revision Approval':'#f59e0b',
                'In Production':'#0369a1', 'Ready for Collection':'#7c3aed',
                'Delivered':'#64748b',
            }
            for _, _gr in _gs_df.iterrows():
                _gs_st  = str(_gr.get('status','') or '')
                _gs_col = _GS_SC.get(_gs_st, '#94a3b8')
                _gs_bal = (float(_gr.get('total_amount',0) or 0)
                           - float(_gr.get('deposit_amount',0) or 0))
                st.markdown(
                    f'<div style="background:#ffffff;border:1px solid #e2e8f0;'
                    f'border-left:5px solid {_gs_col};border-radius:10px;'
                    f'padding:1rem 1.25rem;margin-bottom:0.65rem;'
                    f'display:flex;justify-content:space-between;align-items:center;">'
                    f'<div>'
                    f'<div style="font-weight:800;color:#0f172a;font-size:1.05rem;">'
                    f'{_gr.get("job_order_no","—")}</div>'
                    f'<div style="color:#475569;font-size:0.875rem;margin-top:2px;">'
                    f'{_gr.get("customer_name","—")}</div>'
                    f'<div style="font-size:0.75rem;color:{_gs_col};font-weight:700;margin-top:4px;">'
                    f'{_gs_st}</div></div>'
                    f'<div style="text-align:right;">'
                    f'<div style="font-weight:700;color:#0f172a;">'
                    f'{CURRENCY}{float(_gr.get("total_amount",0) or 0):,.2f}</div>'
                    f'<div style="font-size:0.8rem;color:#ef4444;font-weight:600;">'
                    f'Bal: {CURRENCY}{_gs_bal:,.2f}</div>'
                    f'<div style="font-size:0.72rem;color:#94a3b8;">'
                    f'Collect: {str(_gr.get("date_of_collection","") or "—")}</div>'
                    f'</div></div>',
                    unsafe_allow_html=True)
    if st.button("&#x2190; Back to Command Center", key="gs_back_btn"):
        st.session_state.global_search_q = ""
        st.session_state.app_mode = "Command Center"
        st.rerun()

# ═══════════════════════════════════════════════════════════════════
# ROUTE 5: PRODUCTION LAYOUT BUILDER
# ═══════════════════════════════════════════════════════════════════
elif app_mode == "Production Layout Builder" and is_admin:
    st.markdown('<div class="section-header">Production Layout Builder — Machine Allocation Engine</div>',
                unsafe_allow_html=True)
    approved_pipeline_df = get_db_job_orders("Approved")
    if approved_pipeline_df.empty:
        st.info("No approved orders available for production scheduling. Authorize orders in the Authorization Center first.")
    else:
        # Labeled options, not bare order numbers — Streamlit's selectbox
        # filters against the displayed (formatted) string as you type, so
        # this also makes the dropdown searchable by customer name, not
        # just by an order number nobody has memorized.
        approved_pipeline_df = approved_pipeline_df.copy()
        approved_pipeline_df['_plb_label'] = approved_pipeline_df.apply(
            lambda r: f"{r.get('job_order_no','—')} — {r.get('customer_name','—')} "
                      f"({CURRENCY} {float(r.get('total_amount', 0) or 0):,.0f})",
            axis=1
        )
        _plb_label_map = dict(zip(approved_pipeline_df['job_order_no'], approved_pipeline_df['_plb_label']))
        select_for_layout = st.selectbox(
            "Select Approved Order to Schedule:",
            [""] + approved_pipeline_df['job_order_no'].dropna().tolist(),
            format_func=lambda o: _plb_label_map.get(o, "—") if o else "— Select an order —",
        )
        if select_for_layout:
            _plb_row = approved_pipeline_df[approved_pipeline_df['job_order_no'] == select_for_layout].iloc[0]
            st.markdown(
                f'<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;'
                f'padding:1rem 1.5rem;margin-bottom:1.5rem;display:flex;gap:3rem;flex-wrap:wrap;">'
                f'<div><div style="font-size:0.65rem;color:#94a3b8;text-transform:uppercase;'
                f'letter-spacing:0.06em;margin-bottom:0.15rem;">Customer</div>'
                f'<div style="font-weight:700;color:#0f172a;">{_plb_row.get("customer_name","—")}</div></div>'
                f'<div><div style="font-size:0.65rem;color:#94a3b8;text-transform:uppercase;'
                f'letter-spacing:0.06em;margin-bottom:0.15rem;">Quantity</div>'
                f'<div style="font-weight:700;color:#0f172a;">{int(_plb_row.get("qty_to_print",0)):,}</div></div>'
                f'<div><div style="font-size:0.65rem;color:#94a3b8;text-transform:uppercase;'
                f'letter-spacing:0.06em;margin-bottom:0.15rem;">Print Category</div>'
                f'<div style="font-weight:700;color:#0f172a;">{_plb_row.get("type_of_print","—")}</div></div>'
                f'<div><div style="font-size:0.65rem;color:#94a3b8;text-transform:uppercase;'
                f'letter-spacing:0.06em;margin-bottom:0.15rem;">Contract Value</div>'
                f'<div style="font-weight:700;color:#10b981;">{CURRENCY} {float(_plb_row.get("total_amount",0)):,.2f}</div></div>'
                f'</div>', unsafe_allow_html=True)
            with st.form(key=f"layout_form_{_plb_row['id']}"):
                st.markdown('<div class="form-group-header">Job Identification</div>', unsafe_allow_html=True)
                _lf1, _lf2, _lf3 = st.columns(3)
                lf_job_name   = _lf1.text_input("Job Name / Identifier ★", value=str(_plb_row.get('customer_name','')))
                lf_sales_rep  = _lf2.text_input("Sales Representative",    value=str(_plb_row.get('created_by','')))
                lf_start_date = _lf3.date_input("Job Start Date ★",        value=datetime.now().date())
                st.markdown('<div class="form-group-header">Production Dimensions</div>', unsafe_allow_html=True)
                _ld1, _ld2, _ld3 = st.columns(3)
                lf_total_qty = _ld1.number_input("Total Finished Quantity ★", min_value=1,
                                                  value=int(_plb_row.get('qty_to_print', 1000) or 1000))
                lf_type_id   = _ld2.number_input("Number of Ups / Type ID ★", min_value=1, max_value=64, value=1)
                lf_total_val = _ld3.number_input(f"Total Contract Value ({CURRENCY})", min_value=0.0,
                                                  value=float(_plb_row.get('total_amount', 0.0) or 0.0))
                st.markdown('<div class="form-group-header">Printing Presses — Components</div>', unsafe_allow_html=True)
                _press_opts = [m for m in MACHINE_DATA.keys() if any(k in m.upper() for k in ['SM', 'GTO', 'CANON'])]
                st.caption("Define one or more print components. Each component represents a distinct substrate run on a press.")
                _num_components = st.number_input("Number of Print Components", min_value=1, max_value=6, value=1)
                components = []
                for _ci in range(int(_num_components)):
                    _cc1, _cc2 = st.columns(2)
                    _comp_machine = _cc1.selectbox(f"Press Machine — Component {_ci+1}", _press_opts, key=f"comp_machine_{_ci}")
                    # Default assumes N-up printing: total_qty finished pieces need
                    # total_qty / ups actual press impressions, not total_qty itself
                    # (matches how Die Cutter's own quantity is already computed below).
                    # Still editable — this is a sane default, not a hard rule, since
                    # some components (e.g. a cover run) may not follow the job's ups.
                    _comp_default_imps = int(math.ceil(lf_total_qty / max(1, lf_type_id)))
                    _comp_imps    = _cc2.number_input(f"Press Impressions — Component {_ci+1}", min_value=1,
                                                       value=_comp_default_imps, key=f"comp_imps_{_ci}",
                                                       help=f"Defaults to {lf_total_qty:,} qty ÷ {lf_type_id} ups = {_comp_default_imps:,} press impressions.")
                    components.append({"machines": [_comp_machine], "impressions": _comp_imps})
                st.markdown('<div class="form-group-header">Post-Press & Finishing Machines</div>', unsafe_allow_html=True)
                _finishing_opts = [m for m in MACHINE_DATA.keys() if not any(k in m.upper() for k in ['SM', 'GTO', 'CANON'])]
                lf_finishing = checkbox_multiselect(
                    "Select Finishing Machines (applied in order: Die Cutter → Folder Gluer → Others)",
                    _finishing_opts, f"lf_finish_{_plb_row['id']}"
                )

                # ── Pre-flight sanity check — catches a fat-fingered quantity
                # (extra zero) before it silently jams a machine's schedule.
                _lf_flags = []
                for _ci, _c in enumerate(components):
                    _d = _estimate_working_days(_c['impressions'], _c['machines'][0])
                    if _d > STAGE_DAYS_WARNING_THRESHOLD:
                        _lf_flags.append(
                            f"Component {_ci+1} ({_c['machines'][0]}): "
                            f"~{_d:.0f} working days for {_c['impressions']:,} impressions"
                        )
                for _fm in lf_finishing:
                    _d = _estimate_working_days(lf_total_qty, _fm)
                    if _d > STAGE_DAYS_WARNING_THRESHOLD:
                        _lf_flags.append(f"{_fm}: ~{_d:.0f} working days for {lf_total_qty:,} units")

                _lf_override = False
                if _lf_flags:
                    st.markdown(
                        '<div style="background:#fef2f2;border:1px solid #fca5a5;border-left:4px solid #ef4444;'
                        'border-radius:8px;padding:0.75rem 1.1rem;margin:0.75rem 0;font-size:0.85rem;color:#991b1b;">'
                        '<strong>This schedule looks unusually long — double-check quantities before committing:</strong>'
                        '<ul style="margin:0.4rem 0 0 1.1rem;padding:0;">'
                        + "".join(f"<li>{f}</li>" for f in _lf_flags) +
                        '</ul></div>', unsafe_allow_html=True)
                    _lf_override = st.checkbox(
                        "I've double-checked these quantities and want to commit this schedule anyway")

                st.markdown("<br>", unsafe_allow_html=True)
                lf_submit = st.form_submit_button("CALCULATE SCHEDULE & COMMIT TO PRODUCTION PLAN",
                                                   use_container_width=True, type="primary")
                if lf_submit:
                    _lf_missing = []
                    if not lf_job_name.strip(): _lf_missing.append("Job Name")
                    if lf_total_qty < 1:        _lf_missing.append("Total Quantity")
                    if _lf_flags and not _lf_override:
                        _lf_missing.append("confirmation of the unusually long schedule flagged above")
                    if not _lf_missing:
                        with st.spinner("Calculating optimal schedule across machine availability windows..."):
                            add_multi_part_job({
                                "name":               sanitize_string(lf_job_name),
                                "job_order_no":       str(_plb_row.get('job_order_no', '')),
                                "sales_rep":          sanitize_string(lf_sales_rep),
                                "start_date":         lf_start_date,
                                "total_qty":          int(lf_total_qty),
                                "type_id":            int(lf_type_id),
                                "total_val":          float(lf_total_val),
                                "components":         components,
                                "finishing_machines": lf_finishing
                            })
                        update_order_lifecycle_status(str(_plb_row['id']), 'In Production')
                        st.success(f"Production plan committed for '{lf_job_name}'. Machine schedule written to Shop Floor Control.")
                        st.rerun()
                    else:
                        st.error(f"Cannot commit plan — missing required fields: {', '.join(_lf_missing)}")

# ═══════════════════════════════════════════════════════════════════
# ROUTE 5b: PRODUCTION BOARD (simplified, department-filterable — runs
# alongside Production Layout Builder rather than replacing it; see
# production.py's module docstring for the full scope note)
# ═══════════════════════════════════════════════════════════════════
elif app_mode == "Production Board":
    # No "and is_admin" here — unlike the routes above, access control for
    # this one lives inside render_production_board() via
    # rbac.check_access(), which is the "structured check using rbac.py"
    # this integration was asked to add. The five original admin routes
    # keep their existing router-level "and is_admin" pattern untouched;
    # this is a deliberate split between old and new style, not an
    # oversight — rewriting the original five to match was out of scope.
    render_production_board(
        get_db_job_orders_multi_status, update_order_lifecycle_status,
        generate_pdf_export=handle_production_pdf_export,
        currency=CURRENCY, send_departmental_alert=send_departmental_alert,
        notify_sent_to_warehouse=notify_sent_to_warehouse,
        user_department=st.session_state.get("user_profile", {}).get("department", "NONE")
    )

# ═══════════════════════════════════════════════════════════════════
# ROUTE 6: SHOP FLOOR CONTROL PANEL
# ═══════════════════════════════════════════════════════════════════
elif app_mode == "Shop Floor Control":
    st.markdown('<div class="section-header">Live Production Timeline</div>', unsafe_allow_html=True)
    now_utc = datetime.now(timezone.utc)

    # ── Tier 1: management summary — one bar per order, health-coloured ──
    st.markdown("**Production Pipeline — every order in flight**")
    _show_completed = st.checkbox("Show completed orders too", value=False)
    pipeline_df = get_job_pipeline_status(active_only=not _show_completed)

    _selected_order = None
    if pipeline_df.empty:
        st.info("No orders currently in production. Use the Production Layout Builder to schedule an approved order.")
    else:
        pipeline_df = pipeline_df.assign(
            _hover_current=pipeline_df['current_stage'].fillna('—'),
            _hover_next=pipeline_df['next_stage'].fillna('Final stage'),
            _hover_progress=pipeline_df.apply(
                lambda r: f"{int(r['stages_complete'])}/{int(r['stage_count'])} stages complete", axis=1),
            _hover_eta=pipeline_df['projected_completion'].dt.strftime('%d %b %Y'),
        )
        _pipe_fig = px.timeline(
            pipeline_df.sort_values('scheduled_start'),
            x_start="scheduled_start", x_end="projected_completion",
            y="label", color="health",
            color_discrete_map={"On Track": "#10b981", "At Risk": "#f59e0b", "Late": "#ef4444"},
            hover_data=["_hover_current", "_hover_next", "_hover_progress", "_hover_eta"],
        )
        _pipe_fig.update_traces(
            hovertemplate="<b>%{y}</b><br>"
                          "Currently: %{customdata[0]}<br>"
                          "Next: %{customdata[1]}<br>"
                          "%{customdata[2]} &middot; Est. completion %{customdata[3]}"
                          "<extra></extra>"
        )
        _pipe_fig.update_yaxes(autorange="reversed", title=None)
        _pipe_fig.add_vline(x=now_utc, line_dash="dash", line_color="#0f172a")
        _pipe_fig.update_layout(
            height=max(280, 46 * pipeline_df['label'].nunique()),
            font=dict(family="Segoe UI, sans-serif", color="#0f172a"),
            plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
            legend_title_text="Health",
            margin=dict(l=10, r=10, t=10, b=10),
        )
        st.plotly_chart(_pipe_fig, use_container_width=True, config={'displayModeBar': False})

        st.divider()
        st.markdown("**Drill Down — stage-by-stage detail for one order**")
        _order_opts = pipeline_df.sort_values('label')['job_order_no'].tolist()
        _selected_order = st.selectbox(
            "Order", _order_opts,
            format_func=lambda o: pipeline_df.loc[pipeline_df['job_order_no'] == o, 'label'].iloc[0],
        )

    # ── Tier 2: floor detail for exactly one order ──
    if _selected_order:
        floor_df = get_shop_floor_timeline()
        floor_df = floor_df[floor_df.get('job_order_no') == _selected_order] if not floor_df.empty else floor_df
        if floor_df.empty:
            st.info("No stage-level schedule found for this order yet.")
        else:
            floor_df = floor_df.assign(
                _hover_status=floor_df['stage_status'] if 'stage_status' in floor_df.columns else 'Scheduled',
                _hover_start=floor_df['start_time'].dt.strftime('%d %b, %I:%M %p'),
                _hover_finish=floor_df['effective_finish'].dt.strftime('%d %b, %I:%M %p'),
                _hover_qty=floor_df['quantity'].apply(lambda v: f"{int(v):,}" if pd.notna(v) else "—"),
                _hover_value=floor_df['contract_value'].apply(lambda v: f"{CURRENCY} {float(v):,.2f}" if pd.notna(v) else "—"),
            )
            _sort_col = 'sequence_no' if 'sequence_no' in floor_df.columns else 'start_time'
            _color_col = 'stage_status' if 'stage_status' in floor_df.columns else 'machine'
            _order_fig = px.timeline(
                floor_df.sort_values(_sort_col),
                x_start="start_time", x_end="effective_finish",
                y="machine", color=_color_col,
                color_discrete_map={"Scheduled": "#94a3b8", "In Progress": "#0369a1",
                                     "Delayed": "#ef4444", "Complete": "#10b981", "On Hold": "#f59e0b"},
                hover_data=["_hover_status", "_hover_start", "_hover_finish", "_hover_qty", "_hover_value"],
            )
            _order_fig.update_traces(
                hovertemplate="<b>%{y}</b><br>"
                              "%{customdata[0]}<br>"
                              "%{customdata[1]} → %{customdata[2]}<br>"
                              "Qty: %{customdata[3]} &middot; Value: %{customdata[4]}"
                              "<extra></extra>"
            )
            _order_fig.update_yaxes(autorange="reversed", title=None)
            _order_fig.add_vline(x=now_utc, line_dash="dash", line_color="#0f172a")
            _order_fig.update_layout(
                height=max(220, 46 * floor_df['machine'].nunique()),
                font=dict(family="Segoe UI, sans-serif", color="#0f172a"),
                plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
                legend_title_text="Stage Status",
                margin=dict(l=10, r=10, t=10, b=10),
            )
            st.plotly_chart(_order_fig, use_container_width=True, config={'displayModeBar': False})

            with st.expander("Operator Update"):
                _op_tids = floor_df['tracking_id'].dropna().unique().tolist()
                _op_tid = st.selectbox(
                    "Stage", _op_tids,
                    format_func=lambda t: floor_df.loc[floor_df['tracking_id'] == t, 'machine'].iloc[0]
                                if (floor_df['tracking_id'] == t).any() else t,
                )
                _op_status = st.selectbox("Status", ["In Progress", "Delayed", "On Hold", "Complete"])
                _op_new_eta = None
                if _op_status in ("Delayed", "Complete"):
                    _op_new_eta = st.date_input(
                        "New finish date" if _op_status == "Delayed" else "Actual finish date",
                        value=datetime.now().date())
                if st.button("Update Stage Status"):
                    _eta_dt = (datetime.combine(_op_new_eta, datetime.now().time()).replace(tzinfo=timezone.utc)
                               if _op_new_eta else None)
                    update_stage_status(_op_tid, _op_status, revised_finish=_eta_dt)
                    st.success("Updated — downstream stages recalculated if this pushed the schedule.")
                    st.rerun()

    # ── Whole-shop machine view — capacity planning, independent of any one order ──
    with st.expander("Machine Utilisation — whole shop", expanded=False):
        _all_floor_df = get_shop_floor_timeline()
        if _all_floor_df.empty:
            st.caption("Nothing scheduled.")
        else:
            _all_floor_df = _all_floor_df.assign(_run_status=_all_floor_df.apply(
                lambda r: "Completed" if r['finish_time'] < now_utc
                          else "Active" if r['start_time'] <= now_utc <= r['finish_time']
                          else "Queued", axis=1))
            _all_floor_df = _all_floor_df.assign(
                _hover_qty=_all_floor_df['quantity'].apply(lambda v: f"{int(v):,}" if pd.notna(v) else "—"),
            )
            _mach_fig = px.timeline(
                _all_floor_df.sort_values('start_time'),
                x_start="start_time", x_end="effective_finish",
                y="machine", color="_run_status",
                color_discrete_map={"Active": "#0369a1", "Queued": "#f59e0b", "Completed": "#94a3b8"},
                hover_data=["client_label", "_hover_qty"],
            )
            _mach_fig.update_traces(
                hovertemplate="<b>%{y}</b><br>"
                              "%{customdata[0]}<br>"
                              "Qty: %{customdata[1]}"
                              "<extra></extra>"
            )
            _mach_fig.update_yaxes(autorange="reversed", title=None)
            _mach_fig.add_vline(x=now_utc, line_dash="dash", line_color="#ef4444")
            _mach_fig.update_layout(
                height=max(280, 40 * _all_floor_df['machine'].nunique()),
                font=dict(family="Segoe UI, sans-serif", color="#0f172a"),
                plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
                legend_title_text="Run Status",
                margin=dict(l=10, r=10, t=10, b=10),
            )
            st.plotly_chart(_mach_fig, use_container_width=True, config={'displayModeBar': False})

# ═══════════════════════════════════════════════════════════════════
# ROUTE 7: MY ORDER TRACKER  (dept-aware PDF dispatch + tab isolation)
# ═══════════════════════════════════════════════════════════════════
elif app_mode == "My Order Tracker":
    _ot_user_email = st.session_state.get("user_email", "")
    st.markdown('<div class="section-header">My Order Tracker</div>', unsafe_allow_html=True)
    my_all_orders = get_all_db_job_orders_by_user(_ot_user_email)
    if my_all_orders.empty:
        st.info("No job orders found under your account. Use 'Raise Job Order' to submit your first contract.")
    else:
        _ot_prod_order_nos = my_all_orders.loc[
            my_all_orders['status'].isin(["In Production", "At Warehouse"]), 'job_order_no'
        ].dropna().tolist()
        _ot_jobs_df = get_jobs_by_order_numbers(_ot_prod_order_nos)

        _ot_total   = len(my_all_orders)
        _ot_pending = my_all_orders['status'].isin(["Pending Approval", "Pending Revision Approval"]).sum()
        _ot_approved = (my_all_orders['status'] == "Approved").sum()
        _ot_rejected = (my_all_orders['status'] == "Rejected").sum()
        _ot_value   = my_all_orders['total_amount'].fillna(0).apply(lambda x: float(x or 0)).sum()

        _kc1, _kc2, _kc3, _kc4, _kc5 = st.columns(5)
        with _kc1:
            st.markdown(f'<div class="metric-card"><div class="metric-label">Total Raised</div>'
                        f'<div class="metric-value">{_ot_total}</div></div>', unsafe_allow_html=True)
        with _kc2:
            st.markdown(f'<div class="metric-card" style="border-bottom-color:#f59e0b;">'
                        f'<div class="metric-label">Awaiting Decision</div>'
                        f'<div class="metric-value" style="color:#d97706;">{_ot_pending}</div></div>',
                        unsafe_allow_html=True)
        with _kc3:
            st.markdown(f'<div class="metric-card" style="border-bottom-color:#10b981;">'
                        f'<div class="metric-label">Approved</div>'
                        f'<div class="metric-value" style="color:#059669;">{_ot_approved}</div></div>',
                        unsafe_allow_html=True)
        with _kc4:
            st.markdown(f'<div class="metric-card" style="border-bottom-color:#ef4444;">'
                        f'<div class="metric-label">Rejected / Returned</div>'
                        f'<div class="metric-value" style="color:#dc2626;">{_ot_rejected}</div></div>',
                        unsafe_allow_html=True)
        with _kc5:
            st.markdown(f'<div class="metric-card" style="border-bottom-color:#0369a1;">'
                        f'<div class="metric-label">Total Contract Value</div>'
                        f'<div class="metric-value" style="font-size:1.35rem;">{CURRENCY}{_ot_value:,.2f}</div></div>',
                        unsafe_allow_html=True)
        st.markdown("<div style='height:1.75rem;'></div>", unsafe_allow_html=True)

        # ── In-memory search + filter bar (zero extra DB calls) ──────────
        _s1, _s3 = st.columns([5, 1])
        with _s1:
            _ot_search = st.text_input(
                "Search",
                placeholder="Customer · Order No · Description…",
                key="ot_search_q",
                label_visibility="collapsed",
            )
        with _s3:
            if st.button("⟳ Refresh", use_container_width=True, key="ot_refresh_btn"):
                st.rerun()
        _ot_status_filter = checkbox_multiselect(
            "Filter by status",
            ["Pending Approval", "Pending Revision Approval",
             "Approved", "In Production", "At Warehouse", "Delivered", "Rejected"],
            "ot_status",
        )

        # Apply filters to base DataFrame before tabs render
        _ot_filtered = my_all_orders.copy()
        if _ot_status_filter:
            _ot_filtered = _ot_filtered[_ot_filtered['status'].isin(_ot_status_filter)]
        if _ot_search.strip():
            _q = _ot_search.strip().lower()
            _mask = (
                _ot_filtered['customer_name'].fillna('').str.lower().str.contains(_q, regex=False)
                | _ot_filtered['job_order_no'].fillna('').str.lower().str.contains(_q, regex=False)
                | _ot_filtered['job_description'].fillna('').str.lower().str.contains(_q, regex=False)
            )
            _ot_filtered = _ot_filtered[_mask]

        if _ot_filtered.empty and (_ot_search.strip() or _ot_status_filter):
            st.info("No orders match your search or filter — clear the fields above to see all orders.")

        # Recount from the filtered view so tab labels stay accurate
        _ot_f_total    = len(_ot_filtered)
        _ot_f_pending  = _ot_filtered['status'].isin(
            ["Pending Approval", "Pending Revision Approval"]).sum()
        _ot_f_approved = (_ot_filtered['status'] == "Approved").sum()
        _ot_f_rejected = (_ot_filtered['status'] == "Rejected").sum()

        # ── C10: Personal analytics strip (computed from un-filtered base) ──
        if not my_all_orders.empty:
            _pa_tot    = len(my_all_orders)
            _pa_appr   = int((my_all_orders['status'] == 'Approved').sum())
            _pa_rate   = (_pa_appr / max(_pa_tot, 1)) * 100
            _pa_avgval = (my_all_orders['total_amount']
                              .fillna(0).apply(lambda x: float(x or 0)).mean())
            _pa_avgdays = None
            try:
                _pa_adf = my_all_orders[my_all_orders['status'] == 'Approved'].copy()
                if not _pa_adf.empty and 'created_at' in _pa_adf.columns:
                    _pa_adf['_c'] = pd.to_datetime(_pa_adf['created_at'], utc=True, errors='coerce')
                    _pa_adf['_u'] = pd.to_datetime(
                        _pa_adf.get('updated_at', _pa_adf['created_at']), utc=True, errors='coerce')
                    _pa_adf['_d'] = (_pa_adf['_u'] - _pa_adf['_c']).dt.total_seconds() / 86400
                    _pa_avgdays   = _pa_adf['_d'].mean()
            except Exception:
                pass
            _pa1, _pa2, _pa3 = st.columns(3)
            with _pa1:
                _parc = "#10b981" if _pa_rate >= 80 else ("#f59e0b" if _pa_rate >= 50 else "#ef4444")
                st.markdown(
                    f'<div class="metric-card" style="border-bottom-color:{_parc};">'
                    f'<div class="metric-label">My Approval Rate</div>'
                    f'<div class="metric-value" style="font-size:1.6rem;color:{_parc};">'
                    f'{_pa_rate:.0f}%</div></div>', unsafe_allow_html=True)
            with _pa2:
                st.markdown(
                    f'<div class="metric-card"><div class="metric-label">My Avg Order Value</div>'
                    f'<div class="metric-value" style="font-size:1.35rem;">'
                    f'{CURRENCY}{_pa_avgval:,.2f}</div></div>', unsafe_allow_html=True)
            with _pa3:
                _days_str = f"{_pa_avgdays:.1f} days" if _pa_avgdays is not None else "—"
                st.markdown(
                    f'<div class="metric-card"><div class="metric-label">Avg Days to Approval</div>'
                    f'<div class="metric-value" style="font-size:1.6rem;">'
                    f'{_days_str}</div></div>', unsafe_allow_html=True)
            st.markdown("<div style='height:0.6rem;'></div>", unsafe_allow_html=True)

        _ot_tab_all, _ot_tab_pending, _ot_tab_approved, _ot_tab_rejected = st.tabs([
            f"All Orders ({_ot_f_total})",
            f"Pending ({_ot_f_pending})",
            f"Approved ({_ot_f_approved})",
            f"Rejected ({_ot_f_rejected})",
        ])

        def _render_order_card(row, show_resubmit_button=False, tab_context="default"):
            _r_id          = row.get('id', '')
            _r_order_no    = str(row.get('job_order_no',     'PENDING') or 'PENDING')
            _r_customer    = str(row.get('customer_name',    '—')       or '—')
            _r_desc        = str(row.get('job_description',  '—')       or '—')
            _r_status      = str(row.get('status',           '—')       or '—')
            _r_total       = float(row.get('total_amount',    0)         or 0)
            _r_deposit     = float(row.get('deposit_amount',  0)         or 0)
            _r_balance     = _r_total - _r_deposit
            _r_qty         = int(row.get('qty_to_print',      0)         or 0)
            _r_type_print  = str(row.get('type_of_print',    '—')       or '—')
            _r_collection  = str(row.get('date_of_collection','—')      or '—')
            _r_approved_by = str(row.get('approved_by',      '—')       or '—')
            _r_rej_note    = str(row.get('rejection_note',   '')        or '')
            _r_pgid        = str(row.get('parent_group_id',  '')        or '')
            _r_delivery    = str(row.get('delivery_mode',    '—')       or '—')
            _r_bal_due     = str(row.get('balance_due_date', '—')       or '—')
            _r_is_revised  = _r_status.strip() == 'Pending Revision Approval'
            _r_is_garment  = _is_garment(row)

            _status_map = {
                'Approved':                  ('#10b981', '#d1fae5', '✓ APPROVED'),
                'Rejected':                  ('#ef4444', '#fee2e2', '✗ REJECTED'),
                'Pending Approval':          ('#f59e0b', '#fef3c7', '⏳ PENDING APPROVAL'),
                'Pending Revision Approval': ('#d97706', '#fffbeb', '⚠️ PENDING RE-APPROVAL'),
                'In Production':             ('#0369a1', '#e0f2fe', '🏭 IN PRODUCTION'),
                'At Warehouse':              ('#4f46e5', '#eef2ff', '📥 AT WAREHOUSE'),
                'Delivered':                 ('#059669', '#d1fae5', '🎯 DELIVERED'),
            }
            _s_color, _s_bg, _s_label = _status_map.get(_r_status.strip(), ('#64748b', '#f1f5f9', _r_status.upper()))
            _border_left = f"5px solid {_s_color}"
            _desc_short  = _r_desc[:90] + '…' if len(_r_desc) > 90 else _r_desc
            _batch_chip  = ''
            if _r_pgid:
                _batch_chip = (
                    f'&nbsp;<span style="display:inline-block;background:#e0f2fe;color:#0369a1;'
                    f'font-size:0.65rem;font-weight:700;padding:0.1rem 0.5rem;border-radius:9999px;'
                    f'border:1px solid #bae6fd;">BATCH</span>'
                )
            _dept_chip = (
                '&nbsp;<span style="display:inline-block;background:#fef3c7;color:#92400e;'
                'font-size:0.65rem;font-weight:700;padding:0.1rem 0.5rem;border-radius:9999px;'
                'border:1px solid #fde68a;">🧵 GARMENT</span>'
                if _r_is_garment else
                '&nbsp;<span style="display:inline-block;background:#e0f2fe;color:#0369a1;'
                'font-size:0.65rem;font-weight:700;padding:0.1rem 0.5rem;border-radius:9999px;'
                'border:1px solid #bae6fd;">🖨 PRESS</span>'
            )
            st.markdown(
                f'<div style="background:#ffffff;border:1px solid #e2e8f0;'
                f'border-left:{_border_left};border-radius:12px;'
                f'padding:1.5rem 1.75rem;margin-bottom:1.1rem;'
                f'box-shadow:0 4px 6px -1px rgba(15,23,42,0.04);">'
                f'<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:1rem;">'
                f'<div>'
                f'<div style="font-size:0.65rem;font-weight:700;color:#94a3b8;'
                f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:0.2rem;">'
                f'Job Order No{_batch_chip}{_dept_chip}</div>'
                f'<div style="font-size:1.35rem;font-weight:800;color:#0369a1;letter-spacing:-0.01em;">{_r_order_no}</div>'
                f'<div style="font-size:0.85rem;font-weight:600;color:#475569;margin-top:0.15rem;">{_r_customer}</div>'
                f'</div>'
                f'<div style="text-align:right;">'
                f'<div style="display:inline-block;background:{_s_bg};color:{_s_color};font-size:0.72rem;'
                f'font-weight:700;padding:0.35rem 0.9rem;border-radius:9999px;'
                f'border:1px solid {_s_color}20;letter-spacing:0.04em;">{_s_label}</div>'
                f'</div></div>'
                f'<div style="font-size:0.78rem;color:#64748b;font-weight:700;text-transform:uppercase;'
                f'letter-spacing:0.06em;margin-bottom:0.3rem;">Item Description</div>'
                f'<div style="font-size:0.9rem;color:#1e293b;line-height:1.55;margin-bottom:1rem;'
                f'white-space:pre-wrap;">{_desc_short}</div>'
                f'<div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:0.65rem;margin-bottom:1rem;">'
                f'<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:0.7rem 0.9rem;">'
                f'<div style="font-size:0.6rem;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.15rem;">Contract Value</div>'
                f'<div style="font-size:0.95rem;font-weight:800;color:#0f172a;">{CURRENCY} {_r_total:,.2f}</div></div>'
                f'<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:0.7rem 0.9rem;">'
                f'<div style="font-size:0.6rem;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.15rem;">Deposit Paid</div>'
                f'<div style="font-size:0.95rem;font-weight:800;color:#059669;">{CURRENCY} {_r_deposit:,.2f}</div></div>'
                f'<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:0.7rem 0.9rem;">'
                f'<div style="font-size:0.6rem;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.15rem;">Balance Outstanding</div>'
                f'<div style="font-size:0.95rem;font-weight:800;color:{"#ef4444" if _r_balance > 0 else "#10b981"};">{CURRENCY} {_r_balance:,.2f}</div></div>'
                f'<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:0.7rem 0.9rem;">'
                f'<div style="font-size:0.6rem;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.15rem;">Print Qty</div>'
                f'<div style="font-size:0.95rem;font-weight:800;color:#0f172a;">{_r_qty:,}</div></div>'
                f'</div>'
                f'<div style="display:flex;gap:1.5rem;flex-wrap:wrap;font-size:0.8rem;color:#64748b;margin-bottom:0.75rem;">'
                f'<span>📦 <strong>{_r_type_print}</strong></span>'
                f'<span>🚚 <strong>{_r_delivery}</strong></span>'
                f'<span>📅 Collection: <strong style="color:#0369a1;">{_r_collection}</strong></span>'
                f'<span>⏰ Balance Deadline: <strong>{_r_bal_due}</strong></span>'
                f'</div></div>', unsafe_allow_html=True)

            if _r_status.strip() == 'Approved' and _r_approved_by and _r_approved_by != '—':
                st.markdown(
                    f'<div class="fd-approved-card" style="margin-top:-0.6rem;margin-bottom:1.1rem;padding:0.8rem 1.1rem;">'
                    f'<span style="font-size:0.75rem;font-weight:700;color:#059669;text-transform:uppercase;letter-spacing:0.05em;">✓ Authorized By</span>'
                    f'<span style="font-size:0.9rem;font-weight:600;color:#064e3b;margin-left:0.75rem;">{_r_approved_by}</span>'
                    f'</div>', unsafe_allow_html=True)
            if _r_status.strip() == 'Rejected' and _r_rej_note:
                st.markdown(
                    f'<div class="fd-rejection-note-box" style="margin-top:-0.6rem;margin-bottom:1.1rem;">'
                    f'<div style="font-size:0.72rem;font-weight:700;color:#b91c1c;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.3rem;">Management Rejection Note</div>'
                    f'<div style="font-size:0.875rem;color:#7f1d1d;line-height:1.55;">{_r_rej_note}</div>'
                    f'</div>', unsafe_allow_html=True)
            if _r_is_revised:
                st.markdown(
                    f'<div style="background:linear-gradient(135deg,#fffbeb,#fef3c7);border:1px solid #fcd34d;'
                    f'border-left:4px solid #d97706;border-radius:8px;padding:0.65rem 1rem;'
                    f'margin-top:-0.6rem;margin-bottom:1.1rem;font-size:0.82rem;color:#78350f;">'
                    f'<strong>⚠️ Revised Contract:</strong> This order was edited after initial approval '
                    f'and is now awaiting fresh management sign-off. No action is required from you at this stage.'
                    f'</div>', unsafe_allow_html=True)

            if _r_status.strip() == "At Warehouse":
                st.markdown(
                    '<div style="background:#eef2ff;border:1px solid #c7d2fe;border-left:4px solid #4f46e5;'
                    'border-radius:8px;padding:0.75rem 1.1rem;margin-top:-0.6rem;margin-bottom:1.1rem;">'
                    '<div style="font-size:0.75rem;font-weight:700;color:#4338ca;text-transform:uppercase;'
                    'letter-spacing:0.05em;">📥 At Warehouse — Awaiting Dispatch</div></div>',
                    unsafe_allow_html=True)
            elif _r_status.strip() == "In Production":
                _pl = _pipeline_summary(_r_order_no, _ot_jobs_df)
                if _pl and not _pl["all_done"]:
                    _eta_str  = _pl["eta"].strftime("%d %b %Y") if pd.notna(_pl["eta"]) else "—"
                    _next_str = f' &nbsp;·&nbsp; Next: <strong>{_pl["next_machine"]}</strong>' if _pl["next_machine"] else ''
                    st.markdown(
                        f'<div style="background:#f0f9ff;border:1px solid #bae6fd;border-left:4px solid #0369a1;'
                        f'border-radius:8px;padding:0.75rem 1.1rem;margin-top:-0.6rem;margin-bottom:1.1rem;">'
                        f'<div style="font-size:0.75rem;font-weight:700;color:#0369a1;text-transform:uppercase;'
                        f'letter-spacing:0.05em;margin-bottom:0.2rem;">🏭 In Production</div>'
                        f'<div style="font-size:0.85rem;color:#0c4a6e;">'
                        f'Current stage: <strong>{_pl["current_machine"]}</strong>{_next_str}'
                        f' &nbsp;·&nbsp; Est. completion: <strong>{_eta_str}</strong></div></div>',
                        unsafe_allow_html=True)
                else:
                    st.markdown(
                        '<div style="background:#f0f9ff;border:1px solid #bae6fd;border-left:4px solid #0369a1;'
                        'border-radius:8px;padding:0.75rem 1.1rem;margin-top:-0.6rem;margin-bottom:1.1rem;">'
                        '<div style="font-size:0.85rem;color:#0c4a6e;">🏭 In production — detailed schedule '
                        'not available for this order yet.</div></div>',
                        unsafe_allow_html=True)

            # ── Dept-aware PDF download (LAZY / CACHED — 5-min TTL) ──────
            # _generate_pdf_cached only calls ReportLab on a cache miss.
            # Subsequent reruns return pre-built bytes at near-zero CPU cost.
            import json as _pjson
            try:
                _row_safe = {
                    k: (v if isinstance(v, (str, int, float, bool, type(None))) else str(v))
                    for k, v in row.items()
                }
                _pdf_data = _generate_pdf_cached(
                    str(_r_id), _r_status,
                    'garment' if _r_is_garment else 'press',
                    _pjson.dumps(_row_safe, default=str),
                )
            except Exception:
                _pdf_data = dispatch_pdf_manifest(row).getvalue()
            _pdf_label = (
                f"🧵 Export Garment PDF — {_r_order_no}"
                if _r_is_garment else
                f"📄 Export PDF Manifest — {_r_order_no}"
            )
            st.download_button(
                label=_pdf_label, data=_pdf_data,
                file_name=f"{'Garment' if _r_is_garment else ''}Manifest_{_r_order_no}.pdf",
                mime="application/pdf", use_container_width=True,
                key=f"dl_tracker_{_r_id}_{_r_order_no}_{tab_context}"
            )
            if show_resubmit_button and _r_status.strip() == 'Rejected':
                if st.button(f"🔄 Modify & Resubmit — {_r_order_no}",
                             key=f"resub_tracker_{_r_id}_{_r_order_no}_{tab_context}",
                             use_container_width=True):
                    st.session_state.resubmit_order_data = row
                    st.session_state.resubmit_active_dept = "GARMENT" if _r_is_garment else "PRESS"
                    st.session_state.app_mode = "Raise Job Order"
                    st.rerun()
            st.markdown("<div style='height:0.25rem;'></div>", unsafe_allow_html=True)

        def _render_order_tab(orders_df, show_resubmit=False, tab_context="default"):
            if orders_df.empty:
                st.info("No orders in this category.")
                return
            _df = orders_df.copy()
            def _safe_gk(r):
                """float NaN is truthy in Python — must be caught explicitly
                   before the or-fallback to avoid rendering 'nan' as the ref."""
                import math as _m
                _raw = r.get('parent_group_id')
                if _raw is None:
                    return f"SOLO_{r['id']}"
                try:
                    if isinstance(_raw, float) and _m.isnan(_raw):
                        return f"SOLO_{r['id']}"
                except Exception:
                    pass
                _pgid = str(_raw).strip()
                return _pgid if _pgid.lower() not in ('nan', 'none', '') else f"SOLO_{r['id']}"
            _df['_group_key'] = _df.apply(_safe_gk, axis=1)
            if 'created_at' in _df.columns:
                _df = _df.sort_values('created_at', ascending=False).reset_index(drop=True)
            _seen = []
            for _gk in _df['_group_key']:
                if _gk not in _seen:
                    _seen.append(_gk)
            for _gk in _seen:
                _gdf      = _df[_df['_group_key'] == _gk].copy()
                _is_multi = len(_gdf) > 1
                if _is_multi:
                    _g_first          = _gdf.iloc[0]
                    _g_total          = _gdf['total_amount'].fillna(0).apply(lambda x: float(x or 0)).sum()
                    _g_status_summary = ', '.join(sorted(set(s.strip() for s in _gdf['status'].unique().tolist())))
                    st.markdown(
                        f'<div style="background:linear-gradient(135deg,#f8fafc,#f1f5f9);border:1px solid #e2e8f0;'
                        f'border-radius:12px;padding:1rem 1.5rem;margin-bottom:0.75rem;margin-top:0.5rem;'
                        f'display:flex;justify-content:space-between;align-items:center;">'
                        f'<div>'
                        f'<div style="font-size:0.62rem;font-weight:700;color:#64748b;text-transform:uppercase;'
                        f'letter-spacing:0.08em;margin-bottom:0.2rem;">BATCH SUBMISSION — {len(_gdf)} LINE ITEMS</div>'
                        f'<div style="font-size:1.1rem;font-weight:800;color:#0f172a;">'
                        f'{str(_g_first.get("customer_name","—") or "—")}</div>'
                        f'<div style="font-size:0.78rem;color:#64748b;margin-top:0.15rem;">'
                        f'Ref: <span style="color:#0369a1;">'
                        f'{ "Individual Submission" if _gk.startswith("SOLO_") else _gk}</span>'
                        f' &nbsp;·&nbsp; Status: <strong>{_g_status_summary}</strong></div>'
                        f'</div>'
                        f'<div style="text-align:right;">'
                        f'<div style="font-size:0.62rem;color:#94a3b8;text-transform:uppercase;'
                        f'letter-spacing:0.06em;margin-bottom:0.15rem;">Batch Value</div>'
                        f'<div style="font-size:1.2rem;font-weight:800;color:#10b981;">{CURRENCY} {_g_total:,.2f}</div>'
                        f'</div></div>', unsafe_allow_html=True)
                for _item_pos, (_, _row) in enumerate(_gdf.iterrows()):
                    if _is_multi:
                        _rev_badge = ''
                        if str(_row.get('status', '')).strip() == 'Pending Revision Approval':
                            _rev_badge = (
                                ' &nbsp;<span style="background:#fef3c7;color:#92400e;font-size:0.6rem;'
                                'font-weight:700;padding:0.1rem 0.4rem;border-radius:4px;'
                                'border:1px solid #f59e0b;">REVISED</span>')
                        st.markdown(
                            f'<div style="font-size:0.68rem;font-weight:700;color:#94a3b8;'
                            f'text-transform:uppercase;letter-spacing:0.06em;'
                            f'margin-bottom:0.4rem;padding-left:0.25rem;">'
                            f'Line Item {_item_pos + 1} of {len(_gdf)}{_rev_badge}</div>',
                            unsafe_allow_html=True)
                    _render_order_card(_row.to_dict(), show_resubmit_button=show_resubmit, tab_context=tab_context)
                if _gk != _seen[-1]:
                    st.markdown("<hr style='margin:1.25rem 0;border:none;border-top:2px solid #f1f5f9;'>",
                                unsafe_allow_html=True)

        with _ot_tab_all:
            _render_order_tab(_ot_filtered, show_resubmit=True, tab_context="all")

        with _ot_tab_pending:
            _pending_df = _ot_filtered[_ot_filtered['status'].isin(
                ["Pending Approval", "Pending Revision Approval"])].copy()
            _render_order_tab(_pending_df, show_resubmit=False, tab_context="pending")
            if not _pending_df.empty:
                st.markdown(
                    '<div style="background:linear-gradient(135deg,#fffbeb,#fef3c7);border:1px solid #fcd34d;'
                    'border-radius:10px;padding:0.85rem 1.25rem;margin-top:0.5rem;">'
                    '<div style="font-size:0.72rem;font-weight:700;color:#92400e;text-transform:uppercase;'
                    'letter-spacing:0.05em;margin-bottom:0.2rem;">ℹ️ Awaiting Management Decision</div>'
                    '<div style="font-size:0.85rem;color:#78350f;">'
                    'These orders are currently in the authorization queue. '
                    'You will see them move to Approved or Rejected once management '
                    'reviews them in the Authorization Center.'
                    '</div></div>', unsafe_allow_html=True)

        with _ot_tab_approved:
            _approved_df = _ot_filtered[_ot_filtered['status'] == "Approved"].copy()
            _render_order_tab(_approved_df, show_resubmit=False, tab_context="approved")
            if not _approved_df.empty:
                _pipeline_total   = _approved_df['total_amount'].fillna(0).apply(lambda x: float(x or 0)).sum()
                _pipeline_deposit = _approved_df['deposit_amount'].fillna(0).apply(lambda x: float(x or 0)).sum()
                st.markdown(
                    f'<div style="background:linear-gradient(135deg,#0f172a,#1e293b);color:#ffffff;'
                    f'border-radius:10px;padding:1rem 1.5rem;margin-top:0.5rem;'
                    f'display:flex;gap:3rem;flex-wrap:wrap;">'
                    f'<div><div style="font-size:0.6rem;color:#94a3b8;text-transform:uppercase;'
                    f'letter-spacing:0.06em;margin-bottom:0.15rem;">Approved Orders</div>'
                    f'<div style="font-weight:800;font-size:1.1rem;">{len(_approved_df)}</div></div>'
                    f'<div><div style="font-size:0.6rem;color:#94a3b8;text-transform:uppercase;'
                    f'letter-spacing:0.06em;margin-bottom:0.15rem;">Total Contract Value</div>'
                    f'<div style="font-weight:800;font-size:1.1rem;color:#34d399;">{CURRENCY} {_pipeline_total:,.2f}</div></div>'
                    f'<div><div style="font-size:0.6rem;color:#94a3b8;text-transform:uppercase;'
                    f'letter-spacing:0.06em;margin-bottom:0.15rem;">Deposits Collected</div>'
                    f'<div style="font-weight:800;font-size:1.1rem;color:#7dd3fc;">{CURRENCY} {_pipeline_deposit:,.2f}</div></div>'
                    f'<div><div style="font-size:0.6rem;color:#94a3b8;text-transform:uppercase;'
                    f'letter-spacing:0.06em;margin-bottom:0.15rem;">Outstanding Balance</div>'
                    f'<div style="font-weight:800;font-size:1.1rem;color:#fca5a5;">'
                    f'{CURRENCY} {_pipeline_total - _pipeline_deposit:,.2f}</div></div>'
                    f'</div>', unsafe_allow_html=True)

        with _ot_tab_rejected:
            _rejected_df = _ot_filtered[_ot_filtered['status'] == "Rejected"].copy()
            _render_order_tab(_rejected_df, show_resubmit=True, tab_context="rejected")
            if not _rejected_df.empty:
                st.markdown(
                    '<div class="fd-rejection-note-box" style="margin-top:0.5rem;">'
                    '<div style="font-size:0.72rem;font-weight:700;color:#b91c1c;text-transform:uppercase;'
                    'letter-spacing:0.05em;margin-bottom:0.3rem;">Next Steps for Rejected Orders</div>'
                    '<div style="font-size:0.85rem;color:#7f1d1d;line-height:1.6;">'
                    'Click <strong>Modify &amp; Resubmit</strong> on any rejected order '
                    'to pre-load all its fields into the Raise Job Order form. '
                    'Make your corrections and resubmit — the revised order will '
                    're-enter the management authorization queue automatically.'
                    '</div></div>', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════
# ACCESS GUARDS — NON-ADMIN BLOCKS
# ═══════════════════════════════════════════════════════════════════
elif app_mode == "Authorization Center" and not is_admin:
    st.markdown(
        '<div style="margin-top:3rem;text-align:center;"><div style="font-size:3rem;margin-bottom:1rem;">🔒</div>'
        '<div style="font-size:1.5rem;font-weight:800;color:#0f172a;margin-bottom:0.5rem;">Restricted Access</div>'
        '<div style="font-size:1rem;color:#64748b;max-width:420px;margin:0 auto;line-height:1.6;">'
        'The Authorization Center is accessible only to authorized managers and administrators. '
        'Contact your system administrator if you require elevated access.'
        '</div></div>', unsafe_allow_html=True)

elif app_mode == "Approved Orders Archive" and not is_admin:
    st.markdown(
        '<div style="margin-top:3rem;text-align:center;"><div style="font-size:3rem;margin-bottom:1rem;">🔒</div>'
        '<div style="font-size:1.5rem;font-weight:800;color:#0f172a;margin-bottom:0.5rem;">Restricted Access</div>'
        '<div style="font-size:1rem;color:#64748b;max-width:420px;margin:0 auto;line-height:1.6;">'
        'The Approved Orders Archive is accessible only to authorized managers and administrators. '
        'Your submitted orders are visible in the My Order Tracker module.'
        '</div></div>', unsafe_allow_html=True)

elif app_mode == "Production Layout Builder" and not is_admin:
    st.markdown(
        '<div style="margin-top:3rem;text-align:center;"><div style="font-size:3rem;margin-bottom:1rem;">🔒</div>'
        '<div style="font-size:1.5rem;font-weight:800;color:#0f172a;margin-bottom:0.5rem;">Restricted Access</div>'
        '<div style="font-size:1rem;color:#64748b;max-width:420px;margin:0 auto;line-height:1.6;">'
        'The Production Layout Builder is reserved for plant administrators. '
        'Use the Raise Job Order module to submit orders for the production pipeline.'
        '</div></div>', unsafe_allow_html=True)