from __future__ import annotations
import logging
import streamlit as st
import rbac

logger = logging.getLogger("appointed_time.production")
_DEPT_OPTIONS = ["All Departments", "PRESS", "GARMENT"]

def _dept_of(row: dict) -> str:
    dept = str(row.get("department") or "").strip().upper()
    if dept:
        return dept
    pt = str(row.get("type_of_print") or row.get("print_type") or "").strip().upper()
    return "GARMENT" if pt in ("DTF", "UV-DTF", "SAV", "EMBROIDERY", "FLEXI SCREEN PRINT") else "PRESS"

def render_production_board(
    get_db_job_orders_multi_status,
    update_order_lifecycle_status, 
    generate_pdf_export=None,
    currency: str = "GH₵",
    send_departmental_alert=None,
    notify_sent_to_warehouse=None,
    user_department: str = "NONE"
) -> None:
    
    # Permission Logic
    allowed_roles = rbac.ADMIN_ROLES
    if not rbac.check_access(allowed_roles) and user_department not in ["PRESS", "GARMENT"]:
        st.markdown('<div style="text-align:center;padding:3rem;">Restricted Access</div>', unsafe_allow_html=True)
        return

    st.markdown('<div class="section-header">Production Board</div>', unsafe_allow_html=True)

    orders = get_db_job_orders_multi_status(["Approved", "In Production"])
    if orders.empty:
        st.info("No approved orders waiting to start production, and nothing currently in production.")
        return

    # Filtering
    if user_department in ["PRESS", "GARMENT"]:
        dept_choice = user_department
    else:
        dept_choice = st.radio("Department", _DEPT_OPTIONS, horizontal=True, key="prod_board_dept_filter", label_visibility="collapsed")

    orders = orders.copy()
    orders["_dept"] = orders.apply(lambda r: _dept_of(r.to_dict()), axis=1)
    if dept_choice != "All Departments":
        orders = orders[orders["_dept"] == dept_choice]

    if orders.empty:
        st.info(f"No approved {dept_choice.lower()} orders waiting.")
        return

    if "created_at" in orders.columns:
        orders = orders.sort_values("created_at", ascending=True)

    for _, row in orders.iterrows():
        row_id      = str(row.get("id"))
        order_no    = str(row.get("job_order_no", "—"))
        customer    = str(row.get("customer_name", "—"))
        description = str(row.get("item_description", row.get("description", "—")))
        dept_label  = str(row.get("_dept", "—"))
        total_val   = float(row.get("total_amount", 0) or 0)
        qty         = row.get("print_qty", "—")

        # Detailed UI Card
        st.markdown(f'''
        <div style="background:var(--at-white,#ffffff);border:1px solid var(--at-border,#e2e8f0);
                    border-radius:12px;padding:1.5rem;margin-bottom:1rem;box-shadow:0 2px 4px rgba(0,0,0,0.05);">
            <div style="font-size:0.7rem;font-weight:700;color:#64748b;text-transform:uppercase;">
                {order_no} &middot; {dept_label} &middot; {row.get('status','—')}
            </div>
            <div style="font-size:1.3rem;font-weight:800;color:#0f172a;margin-bottom:0.25rem;">
                {customer}
            </div>
            <div style="color:#475569;margin-bottom:1rem;">{description}</div>
            <div style="display:flex;gap:1rem;margin-bottom:1rem;">
                <div style="background:#f8fafc;padding:0.5rem 1rem;border-radius:6px;">
                    <small style="display:block;color:#64748b;font-size:0.65rem;">CONTRACT</small>
                    <strong>{currency} {total_val:,.2f}</strong>
                </div>
                <div style="background:#f8fafc;padding:0.5rem 1rem;border-radius:6px;">
                    <small style="display:block;color:#64748b;font-size:0.65rem;">QTY</small>
                    <strong>{qty}</strong>
                </div>
            </div>
        </div>
        ''', unsafe_allow_html=True)
        
        # Action Row
        col1, col2 = st.columns([1, 1])
        with col1:
            _row_status = str(row.get('status', '—'))
            if _row_status == "Approved":
                if st.button("Start Production", key=f"start_{row_id}", use_container_width=True):
                    if update_order_lifecycle_status(row_id, "In Production"):
                        st.success("Moved to In Production.")
                        st.rerun()
            elif _row_status == "In Production":
                if st.button("Send to Warehouse", key=f"warehouse_{row_id}",
                              use_container_width=True, type="primary"):
                    if update_order_lifecycle_status(row_id, "At Warehouse"):
                        if notify_sent_to_warehouse:
                            try:
                                notify_sent_to_warehouse(row.to_dict())
                            except Exception:
                                logger.exception("notify_sent_to_warehouse failed for order id=%s.", row_id)
                        st.success("Sent to warehouse.")
                        st.rerun()
        with col2:
            if generate_pdf_export and st.button("Export PDF", key=f"pdf_{row_id}", use_container_width=True):
                generate_pdf_export(row_id, row.to_dict())
        st.divider()