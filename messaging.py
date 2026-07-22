"""
messaging.py — Departmental email alerts for the Appointed Time Enterprise Hub.

Self-contained on purpose: app.py will import FROM this module, so this
module cannot import back from app.py without a circular import. Its HTML
shell duplicates the shape of app.py's existing _email_shell() rather than
importing it. If you want a single shared template, the actual fix is
moving app.py's send_resend_notification / notify_order_approved /
notify_order_rejected / notify_collection_due into THIS file too, so
everything email-related lives in one place and app.py only ever imports
from messaging.py, never the other way. That's a real, separate cleanup
task, not required for send_departmental_alert() to work correctly today.
"""
from __future__ import annotations

import logging
import os
import threading

import requests
import streamlit as st

logger = logging.getLogger("appointed_time.messaging")

CURRENCY = "GH₵"  # matches the module-level constant already in app.py


def _config(key: str, default: str = "") -> str:
    """
    st.secrets first, os.environ second.

    Every other config value in app.py (RESEND_API_KEY, SUPABASE_URL,
    NOTIFY_EMAIL_1/2, APPROVAL_NOTIFY_EMAILS) is read via st.secrets, not
    os.environ — Streamlit Cloud's Secrets editor writes to st.secrets;
    there's no separate "environment variables" panel there, so st.secrets
    is the front door for that deployment target. os.environ is checked
    second so this still works verbatim as asked if you're running
    somewhere that actually does set real process env vars (e.g. Docker,
    a systemd unit). Using one function with a defined priority beats
    guessing which one to hardcode.
    """
    val = st.secrets.get(key)
    if val:
        return val
    return os.environ.get(key, default)


APP_URL = _config("APP_URL", "")

# Department -> comma-separated recipient list, e.g. in secrets.toml:
#   DEPT_EMAILS_PRESS = "press.lead@appointedtime.com.gh,md@appointedtime.com.gh"
#   DEPT_EMAILS_GARMENT = "garment.lead@appointedtime.com.gh"
# or as real env vars of the same name if not on Streamlit Cloud.
def _department_recipients(department: str) -> list[str]:
    key = f"DEPT_EMAILS_{department.strip().upper()}"
    raw = _config(key, "")
    return [e.strip() for e in raw.split(",") if e.strip()]


def _send_resend_email(recipients, subject, html_body, log_context):
    """Same pattern as app.py's version: secrets are read by the caller on
    the main thread; the worker thread only does the HTTP call, making no
    Streamlit API calls itself."""
    api_key      = _config("RESEND_API_KEY")
    sender_email = _config("RESEND_SENDER_EMAIL", "onboarding@resend.dev")

    def worker():
        if not api_key or not recipients:
            return
        try:
            requests.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"from": f"Appointed Time Hub <{sender_email}>",
                      "to": recipients, "subject": subject, "html": html_body},
                timeout=10,
            )
        except Exception:
            logger.exception("Resend email failed (%s): subject=%r", log_context, subject)
    threading.Thread(target=worker, daemon=True).start()


def _alert_shell(accent_bg, heading, subheading, intro, rows, footer_note=""):
    """Plain, professional HTML template. No emoji, no decorative glyphs —
    every element here does one job: identify sender, state the fact,
    show the data, link back to the app."""
    row_html = "".join(
        f'<tr style="background:{"#f8fafc" if i % 2 == 0 else "#ffffff"};">'
        f'<td style="padding:9px 10px;font-weight:600;color:#64748b;'
        f'border-bottom:1px solid #e2e8f0;">{label}</td>'
        f'<td style="padding:9px 10px;font-weight:700;border-bottom:1px solid #e2e8f0;'
        f'color:#0f172a;">{value}</td></tr>'
        for i, (label, value) in enumerate(rows)
    )
    link_html = (
        f'<p style="text-align:center;margin-top:18px;">'
        f'<a href="{APP_URL}" style="display:inline-block;background:#0f172a;color:#ffffff;'
        f'text-decoration:none;font-weight:600;font-size:13px;padding:0.6rem 1.4rem;'
        f'border-radius:6px;">Open Appointed Time Hub</a></p>'
        if APP_URL else ""
    )
    return f"""<div style="font-family:'Segoe UI',Tahoma,sans-serif;color:#0f172a;max-width:600px;
        margin:0 auto;border:1px solid #e2e8f0;border-radius:12px;overflow:hidden;">
      <div style="background:{accent_bg};color:#ffffff;padding:24px;text-align:center;">
        <h2 style="margin:0;font-size:18px;letter-spacing:0.02em;">{heading}</h2>
        <p style="margin:4px 0 0 0;color:#cbd5e1;font-size:13px;">{subheading}</p>
      </div>
      <div style="padding:24px;background:#ffffff;">
        <p style="font-size:14px;line-height:1.6;">{intro}</p>
        <table style="width:100%;border-collapse:collapse;margin:16px 0;font-size:14px;">
          {row_html}
        </table>
        {link_html}
        <p style="font-size:12px;color:#94a3b8;text-align:center;margin-top:16px;">{footer_note}</p>
      </div>
    </div>"""


def send_departmental_alert(order_data: dict) -> bool:
    """
    Route an alert to whoever is configured for order_data['department'].

    Returns False (and logs why) without sending anything if department is
    missing/unmapped or no recipients are configured for it — a silent
    "sent to nobody" is worse than a visible False the caller can surface.
    Returns True once the send is queued (fire-and-forget on a background
    thread, same as the rest of this app's notifications — a slow or down
    Resend API never blocks the Streamlit UI).
    """
    department = str(order_data.get("department", "")).strip()
    if not department:
        logger.warning("send_departmental_alert: order_data has no department; nothing sent.")
        return False
    recipients = _department_recipients(department)
    if not recipients:
        logger.warning(
            "send_departmental_alert: no recipients configured for department=%r "
            "(expected secret/env DEPT_EMAILS_%s).",
            department, department.strip().upper(),
        )
        return False

    order_no = str(order_data.get("job_order_no", "—"))
    _dept_upper = department.strip().upper()
    if _dept_upper == "GARMENT":
        _intro = (
            "An order assigned to your department has been approved. Garment orders are "
            "not scheduled in Production Layout Builder — <strong>you can begin production "
            "immediately</strong>, no need to wait on the scheduler."
        )
    elif _dept_upper == "PRESS":
        _intro = (
            "An order assigned to your department has been approved and sent to the "
            "scheduler for machine/stage scheduling. <strong>Wait for the schedule before "
            "starting production</strong> — unless this is a low-quantity job that your team "
            "has agreed doesn't need scheduling, in which case you can begin immediately."
        )
    else:
        _intro = "An order assigned to your department requires attention."
    html = _alert_shell(
        accent_bg="#0f172a",
        heading=f"{department.upper()} DEPARTMENT ALERT",
        subheading="Appointed Time Printing Enterprise Hub",
        intro=_intro,
        rows=[
            ("Order No", order_no),
            ("Customer", str(order_data.get("customer_name", "—"))),
            ("Status", str(order_data.get("status", "—"))),
            ("Contract Value",
             f"{CURRENCY} {float(order_data.get('total_amount', 0) or 0):,.2f}"),
        ],
        footer_note="This is an automated notification from the Appointed Time Enterprise Hub.",
    )
    _send_resend_email(
        recipients, subject=f"{department.upper()} Alert: Order {order_no}",
        html_body=html, log_context=f"departmental-alert-{department.lower()}",
    )
    return True