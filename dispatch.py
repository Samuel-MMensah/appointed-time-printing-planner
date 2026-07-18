"""
dispatch.py — Payment logging and dispatch finalization.

outstanding_balance is not a column (confirmed: zero hits anywhere in
app.py's Supabase calls) — every existing balance calculation in the app
is total_amount - deposit_amount, computed inline. This module does the
same, not because the request was wrong to think it might be a column
(the archive view even labels it "Outstanding Balance" in the UI, which
is almost certainly where that name came from) — just that the underlying
data is derived, not stored.

"Finalize Dispatch" writes update_order_lifecycle_status(id, 'Delivered')
— 'Delivered' is the only terminal status the existing lifecycle function
accepts (Approved -> In Production -> Ready for Collection -> Delivered).
Inventing a new "Dispatched" status string instead would silently drop
those orders out of get_archive_orders_cached's status filter, which only
matches ['Approved','In Production','Ready for Collection','Delivered'] —
so this reuses the real terminal status rather than adding a fifth one
the rest of the app doesn't know about.

Payment logging reuses record_balance_payment(id, new_deposit_total) —
note NEW TOTAL, not the incremental payment amount; app.py's own existing
call site computes this as (current_deposit + payment_amount) before
calling it, and this module replicates that exactly. Passing the raw
payment amount instead would silently overwrite the deposit total instead
of adding to it — for a module about money, worth stating outright rather
than leaving as something to notice from the diff.

Dependency-injection style and CSS-token requirement: same as
production.py — see that module's docstring for the reasoning.
"""
from __future__ import annotations

import logging

import streamlit as st

import rbac

logger = logging.getLogger("appointed_time.dispatch")


def render_dispatch_module(
    get_db_job_orders_multi_status,
    update_order_lifecycle_status,
    record_balance_payment,
    currency: str = "GH₵",
) -> None:
    """
    get_db_job_orders_multi_status: app.py's existing function, called
        with ['In Production', 'Ready for Collection'].
    update_order_lifecycle_status / record_balance_payment: app.py's
        existing functions — both already clear the approved/archive
        caches internally on success, so this module doesn't manage
        cache invalidation itself.
    currency: pass app.py's CURRENCY constant.
    """
    if not rbac.check_access(rbac.ADMIN_ROLES | rbac.FINANCE_ROLES):
        st.markdown(
            '<div style="margin-top:3rem;text-align:center;">'
            '<div style="font-size:1.5rem;font-weight:800;color:var(--at-navy,#0f172a);'
            'margin-bottom:0.5rem;">Restricted Access</div>'
            '<div style="font-size:1rem;color:var(--at-slate,#64748b);max-width:420px;'
            'margin:0 auto;line-height:1.6;">Dispatch is reserved for managers and '
            'administrators.</div></div>',
            unsafe_allow_html=True,
        )
        return

    st.markdown('<div class="section-header">Dispatch</div>', unsafe_allow_html=True)

    orders = get_db_job_orders_multi_status(["In Production", "At Warehouse"])
    if orders.empty:
        st.info("No orders currently in production or awaiting collection.")
        return
    if "created_at" in orders.columns:
        orders = orders.sort_values("created_at", ascending=True)

    for _, row in orders.iterrows():
        row_id     = str(row.get("id"))
        order_no   = str(row.get("job_order_no", "—"))
        customer   = str(row.get("customer_name", "—"))
        status     = str(row.get("status", "—"))
        total_amt  = float(row.get("total_amount", 0) or 0)
        deposit    = float(row.get("deposit_amount", 0) or 0)
        balance    = max(0.0, total_amt - deposit)
        _not_ready = status.strip() != "At Warehouse"

        with st.container():
            st.markdown(
                f'<div style="background:var(--at-white,#ffffff);border:1px solid '
                f'var(--at-border,#e2e8f0);border-radius:var(--at-radius-lg,12px);'
                f'padding:1.25rem 1.5rem;margin-bottom:0.4rem;'
                f'box-shadow:var(--at-shadow-sm,0 4px 6px -1px rgba(15,23,42,0.04));">'
                f'<div style="display:flex;justify-content:space-between;align-items:flex-start;">'
                f'<div>'
                f'<div style="font-size:0.65rem;font-weight:700;color:var(--at-slate,#64748b);'
                f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:0.2rem;">'
                f'{order_no} &middot; {status}</div>'
                f'<div style="font-size:1.15rem;font-weight:800;color:var(--at-navy,#0f172a);">'
                f'{customer}</div></div>'
                f'<div style="text-align:right;">'
                f'<div style="font-size:0.65rem;color:var(--at-slate,#64748b);'
                f'text-transform:uppercase;letter-spacing:0.06em;">Balance</div>'
                f'<div style="font-size:1.1rem;font-weight:800;'
                f'color:{"var(--at-danger,#ef4444)" if balance > 0 else "var(--at-success,#10b981)"};">'
                f'{currency} {balance:,.2f}</div></div>'
                f'</div></div>',
                unsafe_allow_html=True,
            )

            if balance > 0:
                pay_col1, pay_col2 = st.columns([3, 1])
                with pay_col1:
                    pay_amt = st.number_input(
                        "Payment amount", min_value=0.01, max_value=float(balance),
                        value=float(balance), step=50.0,
                        key=f"disp_pay_amt_{row_id}", label_visibility="collapsed",
                    )
                with pay_col2:
                    if st.button("Record Payment", key=f"disp_pay_btn_{row_id}", use_container_width=True):
                        new_deposit_total = deposit + pay_amt  # cumulative — see module docstring
                        if record_balance_payment(row_id, new_deposit_total):
                            st.success(f"Payment of {currency} {pay_amt:,.2f} recorded for {order_no}.")
                            st.rerun()
                        else:
                            logger.error("record_balance_payment failed for order id=%s.", row_id)
                            st.error("Payment recording failed. Check logs for details.")

                # Professional CSS warning block — replaces an emoji-based alert.
                st.markdown(
                    f'<div style="background:#fef2f2;border:1px solid var(--at-danger-soft,#fca5a5);'
                    f'border-left:4px solid var(--at-danger,#ef4444);border-radius:8px;'
                    f'padding:0.65rem 1rem;margin:0.5rem 0 1rem 0;font-size:0.82rem;'
                    f'color:#991b1b;font-weight:600;">'
                    f'Finalize Dispatch is locked until the outstanding balance of '
                    f'{currency} {balance:,.2f} is fully recorded.</div>',
                    unsafe_allow_html=True,
                )

            if _not_ready:
                st.markdown(
                    '<div style="background:#fffbeb;border:1px solid #fde68a;border-left:4px solid #f59e0b;'
                    'border-radius:8px;padding:0.65rem 1rem;margin:0.5rem 0 1rem 0;font-size:0.82rem;'
                    'color:#92400e;font-weight:600;">'
                    'Still in production — Finalize Dispatch unlocks once the production team '
                    'marks this order sent to the warehouse.</div>',
                    unsafe_allow_html=True,
                )

            if st.button(
                "Finalize Dispatch", key=f"finalize_{row_id}",
                disabled=(balance > 0 or _not_ready), use_container_width=True,
                type="primary",
            ):
                if update_order_lifecycle_status(row_id, "Delivered"):
                    st.success(f"{order_no} finalized and marked Delivered.")
                    st.rerun()
                else:
                    logger.error("Finalize Dispatch failed for order id=%s.", row_id)
                    st.error("Finalization failed. Check logs for details.")

            st.markdown("<hr style='margin:0.5rem 0 1.25rem 0;border-top:1px solid #e2e8f0;'>",
                        unsafe_allow_html=True)