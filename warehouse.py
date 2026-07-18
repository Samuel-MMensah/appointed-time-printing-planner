"""
warehouse.py — Warehouse receiving and finance handoff.

Separate from dispatch.py by design: Warehouse and Finance are different
people, not the same role wearing two hats. Warehouse sees order identity
and quantity — nothing about money. Balance and payment collection stay in
dispatch.py, gated to FINANCE_ROLES, not WAREHOUSE_ROLES.

Warehouse's one action is "Notify Finance This Is Ready" — it does NOT
change job_orders.status. The order stays "At Warehouse" through this
whole module; status only advances to "Delivered" from dispatch.py, once
finance has actually collected payment. Two roles reading the same
"At Warehouse" queue through two different modules is the intended
design, not two systems that need to be kept in sync.
"""
from __future__ import annotations

import logging

import streamlit as st

import rbac

logger = logging.getLogger("appointed_time.warehouse")


def render_warehouse_module(
    get_db_job_orders_multi_status,
    notify_ready_for_finance,
    currency: str = "GH₵",
) -> None:
    if not rbac.check_access(rbac.ADMIN_ROLES | rbac.WAREHOUSE_ROLES):
        st.markdown(
            '<div style="margin-top:3rem;text-align:center;">'
            '<div style="font-size:1.5rem;font-weight:800;color:var(--at-navy,#0f172a);'
            'margin-bottom:0.5rem;">Restricted Access</div>'
            '<div style="font-size:1rem;color:var(--at-slate,#64748b);max-width:420px;'
            'margin:0 auto;line-height:1.6;">Warehouse is reserved for warehouse staff and '
            'administrators.</div></div>',
            unsafe_allow_html=True,
        )
        return

    st.markdown('<div class="section-header">Warehouse Receiving</div>', unsafe_allow_html=True)

    orders = get_db_job_orders_multi_status(["At Warehouse"])
    if orders.empty:
        st.info("Nothing waiting at the warehouse right now.")
        return
    if "created_at" in orders.columns:
        orders = orders.sort_values("created_at", ascending=True)

    for _, row in orders.iterrows():
        row_id   = str(row.get("id"))
        order_no = str(row.get("job_order_no", "—"))
        customer = str(row.get("customer_name", "—"))
        qty      = row.get("print_qty", row.get("qty_to_print", "—"))
        already_notified = bool(row.get("warehouse_notified_finance", False))

        with st.container():
            st.markdown(
                f'<div style="background:var(--at-white,#ffffff);border:1px solid '
                f'var(--at-border,#e2e8f0);border-radius:var(--at-radius-lg,12px);'
                f'padding:1.25rem 1.5rem;margin-bottom:0.4rem;">'
                f'<div style="font-size:0.65rem;font-weight:700;color:var(--at-slate,#64748b);'
                f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:0.2rem;">'
                f'{order_no} &middot; At Warehouse</div>'
                f'<div style="font-size:1.15rem;font-weight:800;color:var(--at-navy,#0f172a);">'
                f'{customer}</div>'
                f'<div style="font-size:0.85rem;color:var(--at-slate,#64748b);margin-top:0.3rem;">'
                f'Quantity: {qty}</div></div>',
                unsafe_allow_html=True,
            )
            if already_notified:
                st.success("Finance already notified — awaiting dispatch finalization.")
            else:
                if st.button("Notify Finance This Is Ready", key=f"wh_notify_{row_id}",
                              use_container_width=True, type="primary"):
                    if notify_ready_for_finance(row.to_dict()):
                        st.success(f"Finance notified for {order_no}.")
                        st.rerun()
                    else:
                        st.error("Could not send the notification. Check logs for details.")
            st.markdown("<hr style='margin:0.5rem 0 1.25rem 0;border-top:1px solid #e2e8f0;'>",
                        unsafe_allow_html=True)