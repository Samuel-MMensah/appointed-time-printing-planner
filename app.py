import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone, time
import math
import random
import re
from supabase import create_client, Client
import plotly.express as px

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Appointed Time | Secured Enterprise Suite",
    layout="wide",
    page_icon="🏢",
    initial_sidebar_state="expanded"
)

# --- 2. GLOBAL SETUP & MACHINE REGISTRY ---
CURRENCY = "GH₵"
SHIFT_START_HOUR = 8
SHIFT_END_HOUR = 17
DAILY_CAPACITY_HOURS = 8.0
MACHINE_DATA = {
    'SM102-CX FOUR COLOUR': {'rate': 8000, 'setup_hours': 1.5},
    'SM102-P FIVE COLOUR': {'rate': 7500, 'setup_hours': 1.5},
    'SM 52': {'rate': 7000, 'setup_hours': 1.5},
    'GTO 52 SEMI-AUTO-2 COLOUR': {'rate': 4500, 'setup_hours': 1.5},
    'GTO 52 MANUAL-2 COLOUR': {'rate': 4000, 'setup_hours': 2.0},
    'FOLDING UNIT (CONTINUOUS)': {'rate': 8000, 'setup_hours': 1.5},
    'MBO-B30E (SINGLE FOLD)': {'rate': 16000, 'setup_hours': 1.5},
    'PERFECT BINDING': {'rate': 500, 'setup_hours': 1.5},
    'SADDLE STITCHER': {'rate': 1000, 'setup_hours': 1.5},
    'POLAR CUTTER (BOOKS)': {'rate': 2000, 'setup_hours': 1.0},
    'POLAR CUTTER (SHEETS)': {'rate': 50000, 'setup_hours': 1.0},
    '3 WAY TRIMMER': {'rate': 500, 'setup_hours': 1.0},
    'LAMINATION UNIT': {'rate': 2500, 'setup_hours': 1.5},
    'DIE CUTTER': {'rate': 3000, 'setup_hours': 1.5},
    'FOLDER GLUER': {'rate': 12000, 'setup_hours': 1.5},
    'CANON DIGITAL C10000': {'rate': 6000, 'setup_hours': 0.5},
    'CANON DIGITAL C800': {'rate': 4000, 'setup_hours': 0.5},
}

# --- 3. PREMIUM "CLEAN INDUSTRIAL LIGHT" CSS TYPOGRAPHY & STYLING ---
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght=300;400;500;600;700;800&display=swap');
html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    background-color: #f8fafc;
    color: #0f172a;
}
.main-title {
    font-size: 2.5rem;
    font-weight: 800;
    color: #0f172a;
    margin-bottom: 0.25rem;
    letter-spacing: -0.03em;
}
.main-subtitle {
    font-size: 1rem;
    color: #64748b;
    margin-bottom: 2rem;
    font-weight: 400;
}
.section-header {
    font-size: 1.4rem;
    font-weight: 700;
    color: #1e293b;
    margin-top: 2.25rem;
    margin-bottom: 1.25rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    letter-spacing: -0.01em;
}
.planner-card {
    background: #ffffff;
    padding: 2rem;
    border-radius: 16px;
    border: 1px solid #e2e8f0;
    box-shadow: 0 4px 6px -1px rgba(15, 23, 42, 0.03), 0 2px 4px -2px rgba(15, 23, 42, 0.03);
    margin-bottom: 1rem;
}
.summary-box {
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
    color: #ffffff;
    padding: 2rem;
    border-radius: 16px;
    box-shadow: 0 10px 15px -3px rgba(15, 23, 42, 0.1);
}
.metric-card {
    background: #ffffff;
    padding: 1.5rem;
    border-radius: 14px;
    border: 1px solid #e2e8f0;
    border-bottom: 4px solid #0f172a;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.01);
    text-align: left;
}
.metric-label {
    font-size: 0.75rem;
    color: #64748b;
    text-transform: uppercase;
    font-weight: 700;
    letter-spacing: 0.06em;
}
.metric-value {
    font-size: 1.85rem;
    font-weight: 800;
    color: #0f172a;
    margin-top: 0.25rem;
    letter-spacing: -0.02em;
}
.ticket-container {
    background-color: #f8fafc;
    border: 1px solid #cbd5e1;
    border-radius: 12px;
    padding: 1.25rem;
    margin-bottom: 1.5rem;
}
.ticket-title {
    font-size: 0.85rem;
    font-weight: 700;
    color: #0f172a;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.75rem;
    display: flex;
    align-items: center;
    gap: 0.25rem;
}
.ticket-field {
    font-size: 0.85rem;
    color: #334155;
    margin-bottom: 0.35rem;
}
.ticket-label {
    font-weight: 600;
    color: #64748b;
}
.job-rollup-card {
    background: #ffffff;
    padding: 1.25rem;
    border-radius: 10px;
    border: 1px solid #e2e8f0;
    border-left: 5px solid #0f172a;
    margin-bottom: 0.75rem;
}
.stream-row-item {
    padding: 0.65rem 0;
    border-bottom: 1px solid #f1f5f9;
    display: flex;
    justify-content: space-between;
    font-size: 0.875rem;
}
.stream-row-item:last-child {
    border-bottom: none;
}
.stRadio > label {
    font-weight: 600 !important;
    color: #1e293b !important;
}

/* --- REFINED SIDEBAR CONTAINER CARDS & INTERACTION LAYERS --- */
.sidebar-card {
    background: #ffffff;
    padding: 1.25rem;
    border-radius: 12px;
    border: 1px solid #e2e8f0;
    margin-bottom: 1.25rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.02);
}
.sidebar-header-text {
    font-size: 0.75rem;
    font-weight: 700;
    color: #475569;
    margin-bottom: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    border-bottom: 1px solid #f1f5f9;
    padding-bottom: 0.5rem;
}
.sidebar-btn-active {
    display: flex;
    align-items: center;
    width: 100%;
    padding: 0.65rem 0.85rem;
    background-color: #0f172a;
    color: #ffffff !important;
    border-radius: 8px;
    font-size: 0.875rem;
    font-weight: 600;
    margin-bottom: 0.35rem;
    border: none;
    text-align: left;
}
.sidebar-btn-inactive {
    display: flex;
    align-items: center;
    width: 100%;
    padding: 0.65rem 0.85rem;
    background-color: transparent;
    color: #334155 !important;
    border-radius: 8px;
    font-size: 0.875rem;
    font-weight: 500;
    margin-bottom: 0.35rem;
    border: none;
    text-align: left;
    transition: all 0.2s ease;
    cursor: pointer;
}
.sidebar-btn-inactive:hover {
    background-color: #f1f5f9;
    color: #0f172a !important;
    padding-left: 1.05rem;
}
.sidebar-icon {
    margin-right: 0.65rem;
    font-size: 1rem;
    display: inline-block;
    width: 1.25rem;
    text-align: center;
}
</style>
""", unsafe_allow_html=True)

# --- 4. SECURED BACKEND SYSTEM CORNERSTONE ---
@st.cache_resource
def init_supabase():
    try:
        url = st.secrets.get("SUPABASE_URL")
        key = st.secrets.get("SUPABASE_KEY")
        if not url or not key:
            st.error("Security Key Initialization Failure: Missing API secrets.")
            return None
        return create_client(url, key)
    except Exception:
        return None

supabase: Client = init_supabase()

def sanitize_string(input_str):
    return re.sub(r'[^\w\s\-\(\)\.\,\/]', '', input_str).strip()

def get_db_jobs():
    if not supabase or not st.session_state.get("authenticated"):
        return pd.DataFrame()
    try:
        res = supabase.table('jobs').select("*").execute()
        return pd.DataFrame(res.data)
    except Exception:
        return pd.DataFrame()

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
        return pd.DataFrame()

def apply_calendar_bounds(dt):
    dt = dt.replace(tzinfo=None)
    if dt.hour < SHIFT_START_HOUR:
        dt = dt.replace(hour=SHIFT_START_HOUR, minute=0, second=0, microsecond=0)
    elif dt.hour >= SHIFT_END_HOUR:
        dt = (dt + timedelta(days=1)).replace(hour=SHIFT_START_HOUR, minute=0, second=0, microsecond=0)
    while dt.weekday() in [5, 6]:
        dt = (dt + timedelta(days=1)).replace(hour=SHIFT_START_HOUR, minute=0, second=0, microsecond=0)
    return dt

def get_machine_next_available_time(machine_name, requested_start_dt):
    df = get_db_jobs()
    if df.empty or 'machine' not in df.columns:
        return apply_calendar_bounds(requested_start_dt)
    m_df = df[df['machine'] == machine_name].copy()
    if m_df.empty:
        return apply_calendar_bounds(requested_start_dt)
    m_df['finish_time'] = pd.to_datetime(m_df['finish_time'], utc=True, format='mixed')
    max_finish = m_df['finish_time'].max().to_pydatetime()
    return apply_calendar_bounds(max_finish) if max_finish > requested_start_dt.replace(tzinfo=None) else apply_calendar_bounds(requested_start_dt)

def calculate_production_time(start_dt, impressions, machine_name, apply_setup=True):
    mach = MACHINE_DATA[machine_name]
    rate = mach['rate']
    setup = mach['setup_hours'] if apply_setup else 0.0
    current_time = apply_calendar_bounds(start_dt)
    if apply_setup:
        current_time += timedelta(hours=setup)
    current_time = apply_calendar_bounds(current_time)
    remaining_imps = impressions
    while remaining_imps > 0:
        current_time = apply_calendar_bounds(current_time)
        workday_end = current_time.replace(hour=SHIFT_END_HOUR, minute=0, second=0, microsecond=0)
        available_hours = (workday_end - current_time).total_seconds() / 3600.0
        if available_hours <= 0:
            current_time = (current_time + timedelta(days=1)).replace(hour=SHIFT_START_HOUR, minute=0)
            continue
        possible_today = available_hours * rate
        if remaining_imps <= possible_today:
            current_time += timedelta(hours=remaining_imps / rate)
            remaining_imps = 0
        else:
            remaining_imps -= possible_today
            current_time = (current_time + timedelta(days=1)).replace(hour=SHIFT_START_HOUR, minute=0)
    return apply_calendar_bounds(current_time)

def add_multi_part_job(job_data):
    if not supabase: return
    tid = f"JOB-{random.randint(1000, 9999)}"
    total_stages = sum(len(c['machines']) for c in job_data['components']) + len(job_data['finishing_machines'])
    val_per_stage = job_data['total_val'] / total_stages if total_stages > 0 else 0
    anchor_start = datetime.combine(job_data['start_date'], datetime.now().time()).replace(tzinfo=timezone.utc)
    printing_finishes = []
    records = []
    for comp in job_data['components']:
        for machine in comp['machines']:
            allocated_start = get_machine_next_available_time(machine, anchor_start)
            finish = calculate_production_time(allocated_start, comp['impressions'], machine)
            printing_finishes.append(finish)
            records.append({
                "job_name": job_data['name'], "tracking_id": tid, "machine": machine,
                "sales_rep": job_data['sales_rep'], "quantity": int(job_data['total_qty']),
                "ups": int(job_data['type_id']), "impressions": int(comp['impressions']),
                "start_time": allocated_start.isoformat(), "finish_time": finish.isoformat(),
                "contract_value": float(val_per_stage)
            })
    earliest_finishing_base = max(printing_finishes) if printing_finishes else apply_calendar_bounds(anchor_start)
    ordered_finishing = sorted(job_data['finishing_machines'], key=lambda x: 0 if "DIE" in x.upper() else (1 if "FOLDER" in x.upper() else 2))
    last_stage_finish = earliest_finishing_base
    die_cutter_start_time = None
    for machine_name in ordered_finishing:
        if "DIE CUTTER" in machine_name.upper():
            calculation_qty = job_data['total_qty'] / max(1, job_data['type_id'])
            f_start = get_machine_next_available_time(machine_name, anchor_start)
            f_finish = calculate_production_time(f_start, calculation_qty, machine_name)
            die_cutter_start_time = f_start
            last_stage_finish = f_finish
        elif "FOLDER GLUER" in machine_name.upper() and die_cutter_start_time is not None:
            calculation_qty = job_data['total_qty']
            stagger_offset_dt = calculate_production_time(die_cutter_start_time, MACHINE_DATA['DIE CUTTER']['rate'] * 2, 'DIE CUTTER')
            f_start = get_machine_next_available_time(machine_name, stagger_offset_dt)
            f_finish = calculate_production_time(f_start, calculation_qty, machine_name)
            last_stage_finish = f_finish
        else:
            calculation_qty = job_data['total_qty']
            f_start = get_machine_next_available_time(machine_name, last_stage_finish)
            f_finish = calculate_production_time(f_start, calculation_qty, machine_name)
            last_stage_finish = f_finish
        records.append({
            "job_name": job_data['name'], "tracking_id": tid, "machine": machine_name,
            "sales_rep": job_data['sales_rep'], "quantity": int(job_data['total_qty']),
            "ups": int(job_data['type_id']), "impressions": int(calculation_qty),
            "start_time": f_start.isoformat(), "finish_time": f_finish.isoformat(),
            "contract_value": float(val_per_stage)
        })
    try:
        for r in records: supabase.table('jobs').insert(r).execute()
    except Exception as e:
        st.error(f"Database insertion unauthorized or broken: {str(e)}")

# --- 5. AUTHENTICATION & MULTI-PAGE ROUTING LAYER ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if "app_mode" not in st.session_state:
    st.session_state.app_mode = "Command Center"

# Corporate Unified Aesthetic Icons Registry
MODULE_ICONS = {
    "Command Center": "⊙",
    "Shop Floor Control": "☵",
    "Production Layout Builder": "⎋",
    "Raise Job Order": "📋",
    "Authorization Center": "✓",
    "Approved Orders Archive": "📁"
}

with st.sidebar:
    st.markdown("### 🔒 Secure Access Portal")
    if not st.session_state.authenticated:
        with st.form("auth_form"):
            email = st.text_input("Corporate Email")
            password = st.text_input("Password", type="password")
            login_btn = st.form_submit_button("Authenticate", use_container_width=True)
            if login_btn and supabase:
                try:
                    auth_res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                    if auth_res.user:
                        st.session_state.authenticated = True
                        st.session_state.user_email = auth_res.user.email
                        st.rerun()
                except Exception:
                    st.error("Authentication Denied: Invalid credentials.")
    else:
        st.write(f"Logged in as: `{st.session_state.user_email}`")
        st.markdown("<br><hr style='margin:0.5rem 0;'>", unsafe_allow_html=True)
        
        user_email = st.session_state.user_email.lower() if st.session_state.authenticated else ""
        is_admin = any(x in user_email for x in ["md", "fm", "admin", "manager"]) if st.session_state.authenticated else False
        is_frontdesk = "frontdesk" in user_email if st.session_state.authenticated else False
        
        st.markdown("### 🛠️ ERP WORKSPACE MODULES")
        
        ops_modules = ["Command Center", "Shop Floor Control"]
        if is_admin:
            ops_modules.insert(1, "Production Layout Builder")
            
        admin_modules = ["Raise Job Order"]
        if is_admin:
            admin_modules += ["Authorization Center", "Approved Orders Archive"]

        # --- 5A. PLANT OPERATIONS SECTION CARD ---
        st.markdown(f"""
        <div class="sidebar-card">
            <div class="sidebar-header-text">📈 Plant Operations</div>
        </div>
        """, unsafe_allow_html=True)
        
        for mod in ops_modules:
            ico = MODULE_ICONS.get(mod, "▪")
            btn_style = "sidebar-btn-active" if st.session_state.app_mode == mod else "sidebar-btn-inactive"
            if st.button(f"{ico} {mod}", key=f"btn_ops_{mod}", use_container_width=True):
                st.session_state.app_mode = mod
                st.rerun()
                
        st.markdown("<div style='margin-bottom:1rem;'></div>", unsafe_allow_html=True)

        # --- 5B. ADMINISTRATION PANEL SECTION CARD ---
        st.markdown(f"""
        <div class="sidebar-card">
            <div class="sidebar-header-text">💼 Administration Panel</div>
        </div>
        """, unsafe_allow_html=True)
        
        for mod in admin_modules:
            ico = MODULE_ICONS.get(mod, "▪")
            btn_style = "sidebar-btn-active" if st.session_state.app_mode == mod else "sidebar-btn-inactive"
            if st.button(f"{ico} {mod}", key=f"btn_admin_{mod}", use_container_width=True):
                st.session_state.app_mode = mod
                st.rerun()

        app_mode = st.session_state.app_mode
        st.markdown("<hr style='margin:1rem 0;'>", unsafe_allow_html=True)
        if st.button("Terminate Session", use_container_width=True, type="secondary"):
            st.session_state.authenticated = False
            st.rerun()

# --- 6. CORE APP ROUTING CONTROLLER ---
if not st.session_state.authenticated:
    st.warning("Please sign in from the sidebar panel to view live shop queues.")
else:
    st.markdown('<div class="main-title">Appointed Time Printing Ltd.</div>', unsafe_allow_html=True)
    st.markdown('<div class="main-subtitle">Secured Capacity Planning Engine</div>', unsafe_allow_html=True)
    
    # --- ROUTE 1: COMMAND CENTER ---
    if app_mode == "Command Center":
        df = get_db_jobs()
        if not df.empty:
            df['start_time'] = pd.to_datetime(df['start_time'], utc=True, format='mixed')
            c1, c2, c3, c4 = st.columns(4)
            with c1: st.markdown(f'<div class="metric-card"><div class="metric-label">Active Orders</div><div class="metric-value">{df["tracking_id"].nunique()}</div></div>', unsafe_allow_html=True)
            with c2: st.markdown(f'<div class="metric-card"><div class="metric-label">Pipeline Contract Value</div><div class="metric-value">{CURRENCY}{df["contract_value"].sum():,.2f}</div></div>', unsafe_allow_html=True)
            with c3:
                books = df[df['ups'] == 1]['tracking_id'].nunique()
                st.markdown(f'<div class="metric-card"><div class="metric-label">Book Runs Queue</div><div class="metric-value">{books}</div></div>', unsafe_allow_html=True)
            with c4:
                skillets = df[df['ups'] > 1]['tracking_id'].nunique()
                st.markdown(f'<div class="metric-card"><div class="metric-label">Packaging Skillets</div><div class="metric-value">{skillets}</div></div>', unsafe_allow_html=True)
            
            st.markdown('<div class="section-header">Strategic Capacity Distribution & Revenue</div>', unsafe_allow_html=True)
            left, right = st.columns([2, 1])
            with left:
                load_df = df.groupby('machine').size().reset_index(name='Allocated Components')
                fig_load = px.bar(load_df, x='machine', y='Allocated Components', color='Allocated Components', color_continuous_scale='Blues')
                fig_load.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', showlegend=False, margin=dict(t=10, b=10, l=10, r=10))
                st.plotly_chart(fig_load, use_container_width=True)
            with right:
                rev_df = df.groupby('job_name')['contract_value'].sum().reset_index()
                fig_rev = px.pie(rev_df, values='contract_value', names='job_name', hole=0.6, color_discrete_sequence=px.colors.qualitative.Pastel)
                fig_rev.update_layout(margin=dict(t=10, b=10, l=10, r=10), legend=dict(orientation="h", y=-0.1))
                st.plotly_chart(fig_rev, use_container_width=True)
        else:
            st.info("No active machine runs detected in the live database pipeline.")
            
    # --- ROUTE 2: RAISE JOB ORDER ---
    elif app_mode == "Raise Job Order":
        st.markdown('<div class="section-header">Press Job Order Entry Form</div>', unsafe_allow_html=True)
        with st.form("raise_order_form"):
            c1, c2 = st.columns(2)
            c_name = c1.text_input("Customer Name *")
            c_phone = c2.text_input("Telephone Number")
            j_desc = st.text_area("Job Description")
            f1, f2, f3 = st.columns(3)
            t_amt = f1.number_input(f"Total Amount ({CURRENCY})", min_value=0.0, step=100.0)
            d_amt = f2.number_input(f"Deposit Amount ({CURRENCY})", min_value=0.0, step=100.0)
            b_due = f3.date_input("Balance Due Date")
            p1, p2, p3 = st.columns(3)
            q_print = p1.number_input("Quantity to Print *", min_value=1, value=1000, step=500)
            t_print = p2.selectbox("Type of Print", ["OFFSET", "DIGITAL PRESS", "PACKAGING"])
            m_source = p3.selectbox("Material Source", ["COMPANY MATERIAL", "CUSTOMER MATERIAL"])
            
            st.markdown("#### Technical Parameters & Spec Sheets")
            s1, s2, s3, s4 = st.columns(4)
            p_size = s1.text_input("Print Size (e.g. A1, A3)", value="A3")
            f_size = s2.text_input("Finished Print Size", value="A4")
            pap_type = s3.text_input("Paper Type", value="Bond")
            pap_gsm = s4.text_input("GSM (Weight)", value="150gsm")
            
            o1, o2, o3, o4 = st.columns(4)
            pap_size = o1.text_input("Paper Size stock", value="24x36")
            pap_col = o2.text_input("Paper Colour", value="White")
            imp_col = o3.selectbox("Impressions Ink Colour", ["1 colour", "2 colour", "3 colour", "4 colour"])
            d_mode = o4.selectbox("Delivery Mode", ["COMPANY DELIVERY", "CUSTOMER PICK-UP"])
            
            st.markdown("#### Finishing & Enhancements Processing")
            b_type = st.multiselect("Binding Selection", ["Perfect Binding", "Spiral Binding", "Saddle Stitching", "Comb Binding"])
            l_type = st.multiselect("Laminating Selection", ["Gloss Laminating", "Matt Laminating", "Soft Touch", "UV-Varnish"])
            c_date = st.date_input("Target Date of Collection")
            
            st.markdown("<br>", unsafe_allow_html=True)
            st.info(f"Job Order Handled By: {st.session_state.user_email} | Filling Date: {datetime.now().strftime('%Y-%m-%d')}")
            submit_order = st.form_submit_button("SUBMIT FOR MANAGEMENT APPROVAL", use_container_width=True)
            
            if submit_order:
                if c_name and q_print:
                    order_payload = {
                        "customer_name": sanitize_string(c_name),
                        "telephone_number": sanitize_string(c_phone),
                        "job_description": sanitize_string(j_desc),
                        "total_amount": float(t_amt),
                        "deposit_amount": float(d_amt),
                        "balance_due_date": b_due.isoformat(),
                        "date_of_collection": c_date.isoformat(),
                        "qty_to_print": int(q_print),
                        "type_of_print": t_print,
                        "material_source": m_source,
                        "print_size": sanitize_string(p_size),
                        "finished_print_size": sanitize_string(f_size),
                        "paper_type": sanitize_string(pap_type),
                        "gsm": sanitize_string(pap_gsm),
                        "paper_size": sanitize_string(pap_size),
                        "paper_colour": sanitize_string(pap_col),
                        "impressions_colour": imp_col,
                        "delivery_mode": d_mode,
                        "binding_type": ", ".join(b_type) if b_type else "None",
                        "laminating_type": ", ".join(l_type) if l_type else "None",
                        "status": "Pending Approval",
                        "created_by": st.session_state.user_email
                    }
                    try:
                        supabase.table('job_orders').insert(order_payload).execute()
                        st.success("Job Entry securely deposited inside management ledger pool successfully.")
                    except Exception as e:
                        st.error(f"Failed to process order sequence entry: {str(e)}")
                else:
                    st.error("Submission blocked. Customer Name and Print Quantity require clear declarations.")

    # --- ROUTE 3: AUTHORIZATION CENTER ---
    elif app_mode == "Authorization Center" and is_admin:
        st.markdown('<div class="section-header">Executive Authorization Control Panel</div>', unsafe_allow_html=True)
        orders_df = get_db_job_orders("Pending Approval")
        if orders_df.empty:
            st.success("All clear! No pending jobs require executive sign-off.")
        else:
            PAGE_SIZE_AUTH = 15
            total_orders = len(orders_df)
            total_pages_auth = math.ceil(total_orders / PAGE_SIZE_AUTH)
            if "auth_page" not in st.session_state:
                st.session_state.auth_page = 1
                
            col_p1, col_p2, col_p3 = st.columns([1, 4, 1])
            with col_p1:
                if st.button(" ⬅️ Previous", key="auth_prev_btn", disabled=(st.session_state.auth_page <= 1), use_container_width=True):
                    st.session_state.auth_page -= 1
                    st.rerun()
            with col_p2:
                st.markdown(f"<p style='text-align: center; color: #64748b; font-weight: 600;'>Showing records {((st.session_state.auth_page - 1) * PAGE_SIZE_AUTH) + 1} - {min(st.session_state.auth_page * PAGE_SIZE_AUTH, total_orders)} of {total_orders} (Page {st.session_state.auth_page} of {total_pages_auth})</p>", unsafe_allow_html=True)
            with col_p3:
                if st.button("Next ➡️ ", key="auth_next_btn", disabled=(st.session_state.auth_page >= total_pages_auth), use_container_width=True):
                    st.session_state.auth_page += 1
                    st.rerun()
                    
            start_idx = (st.session_state.auth_page - 1) * PAGE_SIZE_AUTH
            end_idx = start_idx + PAGE_SIZE_AUTH
            paginated_orders = orders_df.iloc[start_idx:end_idx]
            
            for _, row in paginated_orders.iterrows():
                with st.expander(f"Order No: {row['job_order_no']} — Client: {row['customer_name']} ({row['type_of_print']})"):
                    col1, col2, col3 = st.columns(3)
                    col1.markdown(f"**Target Qty:** {row['qty_to_print']:,}")
                    col2.markdown(f"**Total Value:** {CURRENCY}{row['total_amount']:,.2f}")
                    col3.markdown(f"**Deposit Paid:** {CURRENCY}{row['deposit_amount']:,.2f}")
                    st.text(f"Specs: {row['paper_type']} {row['gsm']} | Binding: {row['binding_type']}")
                    st.markdown(f"_Submitted by front desk agent:_ `{row['created_by']}`")
                    btn_approve, btn_reject = st.columns(2)
                    if btn_approve.button("APPROVE & ACTIVATE", key=f"app_{row['id']}", use_container_width=True):
                        try:
                            supabase.table('job_orders').update({
                                "status": "Approved",
                                "approved_by": st.session_state.user_email,
                                "approved_at": datetime.now(timezone.utc).isoformat()
                            }).eq('id', row['id']).execute()
                            st.success("Job order released to active plant production queues!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed status transition: {str(e)}")
                    if btn_reject.button("REJECT / DISCARD", key=f"rej_{row['id']}", use_container_width=True, type="secondary"):
                        try:
                            supabase.table('job_orders').delete().eq('id', row['id']).execute()
                            st.warning("Order discarded.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed deletion request: {str(e)}")

    # --- ROUTE 4: APPROVED ORDERS ARCHIVE ---
    elif app_mode == "Approved Orders Archive" and is_admin:
        st.markdown('<div class="section-header">Enterprise Ledger & Approved Orders Vault</div>', unsafe_allow_html=True)
        approved_orders = get_db_job_orders("Approved")
        if approved_orders.empty:
            st.info("No approved job contracts are currently sitting in archives.")
        else:
            view_matrix = pd.DataFrame({
                "Order No": approved_orders["job_order_no"],
                "Customer Name": approved_orders["customer_name"],
                "Print Qty": approved_orders["qty_to_print"],
                "Category": approved_orders["type_of_print"],
                "total_amount": approved_orders["total_amount"],
                "deposit_amount": approved_orders["deposit_amount"],
                "Authorized Manager": approved_orders["approved_by"]
            })
            st.dataframe(
                view_matrix,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Order No": st.column_config.TextColumn("Order No", help="Unique sequential system layout job number", width="medium"),
                    "Customer Name": st.column_config.TextColumn("Customer Name", width="large"),
                    "Print Qty": st.column_config.NumberColumn("Print Qty", format="%d", width="small"),
                    "Category": st.column_config.SelectboxColumn("Category", options=["OFFSET", "DIGITAL PRESS", "PACKAGING"], width="medium"),
                    "total_amount": st.column_config.NumberColumn(f"Total Amount ({CURRENCY})", format=f"{CURRENCY} %,.2f", width="medium"),
                    "deposit_amount": st.column_config.NumberColumn(f"Deposit Paid ({CURRENCY})", format=f"{CURRENCY} %,.2f", width="medium"),
                    "Authorized Manager": st.column_config.TextColumn("Authorized Manager", width="medium")
                }
            )
            st.markdown("<hr style='margin: 2rem 0;'>", unsafe_allow_html=True)
            st.markdown("### Manage Archived Orders")
            selected_order_no = st.selectbox("Select Order Number to Modify or Delete:", [""] + view_matrix['Order No'].tolist())
            if selected_order_no:
                target_row = approved_orders[approved_orders['job_order_no'] == selected_order_no].iloc[0]
                with st.expander(f"Edit or Delete Job Order: {selected_order_no}"):
                    with st.form(key=f"edit_form_{target_row['id']}"):
                        e_qty = st.number_input("Print Quantity", value=int(target_row['qty_to_print']), step=100)
                        e_amt = st.number_input("Total Amount", value=float(target_row['total_amount']), step=50.0)
                        c_upd, c_del = st.columns(2)
                        if c_upd.form_submit_button(" 💾 Save Changes", use_container_width=True):
                            try:
                                supabase.table('job_orders').update({"qty_to_print": int(e_qty), "total_amount": float(e_amt)}).eq('id', target_row['id']).execute()
                                st.success(f"Order {selected_order_no} updated.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Update failed: {str(e)}")
                        if c_del.form_submit_button(" 🗑️ Delete Order", type="secondary", use_container_width=True):
                            try:
                                supabase.table('job_orders').delete().eq('id', target_row['id']).execute()
                                st.warning(f"Order {selected_order_no} permanently deleted.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Deletion failed: {str(e)}")

    # --- ROUTE 5: PRODUCTION LAYOUT BUILDER ---
    elif app_mode == "Production Layout Builder" and is_admin:
        st.markdown('<div class="section-header">Finite Capacity Layout Blueprint Engine</div>', unsafe_allow_html=True)
        approved_orders = get_db_job_orders("Approved")
        if approved_orders.empty:
            st.info("No approved job contracts are currently waiting for plant capacity injection mapping.")
        else:
            col_in, col_sum = st.columns([2, 1])
            with col_in:
                st.markdown('<div class="planner-card">', unsafe_allow_html=True)
                st.markdown("#### Active Deployment Focus Target")
                order_options = approved_orders.apply(lambda r: f"{r['job_order_no']} | {r['customer_name']} ({r['qty_to_print']:,} units)", axis=1).tolist()
                selected_option = st.selectbox("Assign floor queue properties to contract target:", order_options)
                matched_order = approved_orders.iloc[order_options.index(selected_option)]
                job_name = f"{matched_order['job_order_no']} - {matched_order['customer_name']}"
                st.text_input("Project Label ID (Locked Key Sync)", value=job_name, disabled=True)
                
                sales_rep = st.selectbox("Sales Executive Lead", ["Mabel Ampofo", "Isaac Kum", "Daphne Sarpong", "Elizabeth Akoto", "Charles Adoo", "Christian Mante", "Bertha Tackie", "Reginald Aidam", "Mohammed Seidu"])
                prod_cat = st.selectbox("Production Layout Category", ["Skillet / Box Packing", "Book / Magazine Brochure", "Flat Sheet Flyer"])
                
                c1, c2, c3 = st.columns(3)
                order_qty = c1.number_input("Target Order Units", value=int(matched_order['qty_to_print']), min_value=1)
                ups = c2.number_input("Number of Ups (Layout density logic)", value=1, min_value=1, step=1)
                total_val = c3.number_input("Assigned Contract Evaluation Value (GH₵)", value=float(matched_order['total_amount']), min_value=0.0)
                
                st.markdown("#### Sequential Floor Run Mappings")
                if prod_cat == "Book / Magazine Brochure":
                    type_id = 1
                    text_pages = st.number_input("Total Inner Text Pages", value=16, min_value=4, step=4)
                    text_ups = st.number_input("Text Page Layout Signatures (Ups)", value=8, min_value=1)
                    text_imps = (order_qty * text_pages) / text_ups
                    st.caption(f"Calculated Text Run Load: **{int(text_imps):,} impressions** needed.")
                    
                    r1, r2, r3 = st.columns(3)
                    comp = [
                        {"name": "Cover", "impressions": max(1.0, order_qty/ups), "machines": r1.multiselect("Cover Asset Configuration", list(MACHINE_DATA.keys()))},
                        {"name": "Text", "impressions": float(text_imps), "machines": r2.multiselect("Text Interior Asset Configuration", list(MACHINE_DATA.keys()))}
                    ]
                    fin_route = r3.multiselect("Finishing Layout Line", list(MACHINE_DATA.keys()))
                else:
                    type_id = ups
                    r1, r2 = st.columns(2)
                    comp = [{"name": "Body", "impressions": max(1.0, order_qty/ups), "machines": r1.multiselect("Primary Print Asset Configuration", list(MACHINE_DATA.keys()))}]
                    fin_route = r2.multiselect("Finishing Component Line Sequence", list(MACHINE_DATA.keys()))
                st.markdown('</div>', unsafe_allow_html=True)
                
            with col_sum:
                st.markdown(f"""
                <div class="ticket-container">
                    <div class="ticket-title">Production Work Ticket Blueprint</div>
                    <div class="ticket-field"><span class="ticket-label">Job Num:</span> {matched_order['job_order_no']}</div>
                    <div class="ticket-field"><span class="ticket-label">Format:</span> {matched_order['type_of_print']} | {matched_order['material_source']}</div>
                    <div class="ticket-field"><span class="ticket-label">Description:</span> {matched_order['job_description'] if matched_order['job_description'] else 'No special description.'}</div>
                    <div class="ticket-field"><span class="ticket-label">Print Size:</span> {matched_order['print_size']} (Trimmed: {matched_order['finished_print_size']})</div>
                    <div class="ticket-field"><span class="ticket-label">Stock Required:</span> {matched_order['paper_type']} | {matched_order['gsm']} | Size: {matched_order['paper_size']}</div>
                    <div class="ticket-field"><span class="ticket-label">Colors:</span> {matched_order['paper_colour']} — {matched_order['impressions_colour']}</div>
                    <div class="ticket-field"><span class="ticket-label">Finishing Bind:</span> {matched_order['binding_type'] if matched_order['binding_type'] else 'None'}</div>
                    <div class="ticket-field"><span class="ticket-label">Lamination:</span> {matched_order['laminating_type'] if matched_order['laminating_type'] else 'None'}</div>
                    <div class="ticket-field"><span class="ticket-label">Delivery Target:</span> {matched_order['delivery_mode']} by {matched_order['date_of_collection']}</div>
                </div>
                """, unsafe_allow_html=True)
                
                st.markdown('<div class="summary-box">', unsafe_allow_html=True)
                st.markdown("<p style='font-size:1.25rem; font-weight:700; margin-top:0;'>Deployment Controls</p>", unsafe_allow_html=True)
                start_date = st.date_input("Target Production Start Date", min_value=datetime.today().date())
                st.markdown("<hr style='border-color: rgba(255,255,255,0.1); margin: 1.5rem 0;'>", unsafe_allow_html=True)
                st.markdown(f"**Target Units:** {order_qty:,}")
                st.markdown(f"**Combined Value:** {CURRENCY}{total_val:,.2f}")
                st.markdown(f"**Authorized By:** `{matched_order['approved_by']}`")
                st.markdown("<br>", unsafe_allow_html=True)
                
                if st.button("INJECT INTO ACTIVE CAPACITY PIPELINE", use_container_width=True):
                    has_press = any(len(c['machines']) > 0 for c in comp)
                    if not has_press and not fin_route:
                        st.error("Injection denied: Ensure at least one print element configuration matrix or finishing row contains an assigned target machine module.")
                    else:
                        payload_job = {
                            "name": job_name,
                            "sales_rep": sales_rep,
                            "total_qty": order_qty,
                            "type_id": type_id,
                            "total_val": total_val,
                            "start_date": start_date,
                            "components": comp,
                            "finishing_machines": fin_route
                        }
                        add_multi_part_job(payload_job)
                        st.success("Finite schedule lines sequenced and committed successfully.")
                st.markdown('</div>', unsafe_allow_html=True)

    # --- ROUTE 6: SHOP FLOOR CONTROL ---
    elif app_mode == "Shop Floor Control":
        st.markdown('<div class="section-header">Live Floor Machine Sequencing Streams</div>', unsafe_allow_html=True)
        jobs_df = get_db_jobs()
        if jobs_df.empty:
            st.info("All floor boards are currently idle. No tasks discovered in tracking rows.")
        else:
            jobs_df['start_time'] = pd.to_datetime(jobs_df['start_time'], format='mixed', errors='coerce')
            jobs_df['finish_time'] = pd.to_datetime(jobs_df['finish_time'], format='mixed', errors='coerce')
            jobs_df = jobs_df.dropna(subset=['start_time', 'finish_time'])
            
            m_filter = st.multiselect("Filter View Board by Stationary Assets:", sorted(list(MACHINE_DATA.keys())))
            if m_filter:
                jobs_df = jobs_df[jobs_df['machine'].isin(m_filter)]
                
            unique_tracking_ids = jobs_df['tracking_id'].unique() if not jobs_df.empty else []
            
            if len(unique_tracking_ids) == 0:
                st.info("No matching schedule items discovered for chosen stationary filters.")
            else:
                PAGE_SIZE_SF = 10
                total_jobs = len(unique_tracking_ids)
                total_pages_sf = math.ceil(total_jobs / PAGE_SIZE_SF)
                if "sf_page" not in st.session_state:
                    st.session_state.sf_page = 1
                    
                col_p1, col_p2, col_p3 = st.columns([1, 4, 1])
                with col_p1:
                    if st.button(" ⬅️ Previous", key="sf_prev_btn", disabled=(st.session_state.sf_page <= 1), use_container_width=True):
                        st.session_state.sf_page -= 1
                        st.rerun()
                with col_p2:
                    st.markdown(f"<p style='text-align: center; color: #64748b; font-weight: 600;'>Showing records {((st.session_state.sf_page - 1) * PAGE_SIZE_SF) + 1} - {min(st.session_state.sf_page * PAGE_SIZE_SF, total_jobs)} of {total_jobs} (Page {st.session_state.sf_page} of {total_pages_sf})</p>", unsafe_allow_html=True)
                with col_p3:
                    if st.button("Next ➡️ ", key="sf_next_btn", disabled=(st.session_state.sf_page >= total_pages_sf), use_container_width=True):
                        st.session_state.sf_page += 1
                        st.rerun()
                        
                start_idx = (st.session_state.sf_page - 1) * PAGE_SIZE_SF
                end_idx = start_idx + PAGE_SIZE_SF
                paginated_tids = unique_tracking_ids[start_idx:end_idx]
                
                # --- RENDER TIMELINE CHART ---
                st.markdown("### 📊 Shop Floor Timeline Plot")
                timeline_data = jobs_df[jobs_df['tracking_id'].isin(paginated_tids)].copy()
                
                if not timeline_data.empty:
                    timeline_data['Start Time'] = timeline_data['start_time'].dt.strftime('%Y-%m-%d %H:%M:%S')
                    timeline_data['Finish Time'] = timeline_data['finish_time'].dt.strftime('%Y-%m-%d %H:%M:%S')
                    timeline_data['Machine Asset'] = timeline_data['machine']
                    timeline_data['Job Label'] = timeline_data['job_name']
                    
                    try:
                        fig_timeline = px.timeline(
                            timeline_data,
                            x_start="Start Time",
                            x_end="Finish Time",
                            y="Machine Asset",
                            color="Job Label",
                            hover_data=["tracking_id", "impressions", "quantity"],
                            color_discrete_sequence=px.colors.qualitative.Prism
                        )
                        
                        if fig_timeline is not None:
                            fig_timeline.update_yaxis(autorange="reversed")
                            fig_timeline.update_layout(
                                plot_bgcolor='#ffffff',
                                paper_bgcolor='rgba(0,0,0,0)',
                                margin=dict(t=20, b=20, l=10, r=10),
                                xaxis=dict(gridcolor='#f1f5f9', title="Timeline Run Bounds"),
                                yaxis=dict(gridcolor='#f1f5f9')
                            )
                            st.plotly_chart(fig_timeline, use_container_width=True)
                        else:
                            st.error("Failed to construct layout: Timeline model generated an empty projection matrix.")
                    except Exception as ex:
                        st.warning("Timeline display skipped: Data coordinates are currently reorganizing or out of viewing ranges.")
                else:
                    st.info("No active production items mapped to the timeline chart layer.")
                
                st.markdown("<br>", unsafe_allow_html=True)
                # --- RENDER CARDS ---
                for tid in paginated_tids:
                    flow_rows = jobs_df[jobs_df['tracking_id'] == tid].sort_values('start_time')
                    if flow_rows.empty: continue
                    first_row = flow_rows.iloc[0]
                    total_flow_value = flow_rows['contract_value'].sum()
                    
                    st.markdown(f"""
                    <div class="job-rollup-card">
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.5rem;">
                            <span style="font-size:1.15rem; font-weight:700; color:#0f172a;">{first_row['job_name']}</span>
                            <span style="background-color:#e2e8f0; color:#334155; font-size:0.75rem; font-weight:700; padding:0.25rem 0.6rem; border-radius:20px;">{tid}</span>
                        </div>
                        <div style="font-size:0.85rem; color:#64748b; margin-bottom:0.75rem;">
                            Lead Sales Rep: <strong>{first_row['sales_rep']}</strong> &nbsp;|&nbsp; Target Production Yield: <strong>{int(first_row['quantity']):,} items</strong> &nbsp;|&nbsp; Unified Flow Value: <strong>{CURRENCY}{total_flow_value:,.2f}</strong>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    for _, run_row in flow_rows.iterrows():
                        s_str = run_row['start_time'].strftime('%b %d, %H:%M') if pd.notnull(run_row['start_time']) else "N/A"
                        f_str = run_row['finish_time'].strftime('%b %d, %H:%M') if pd.notnull(run_row['finish_time']) else "N/A"
                        st.markdown(f"""
                        <div class="stream-row-item">
                            <div>
                                <strong>Station Alloc:</strong> {run_row['machine']} <br>
                                <span style="color:#64748b;">Target Volume Run: {int(run_row['impressions']):,} impressions</span>
                            </div>
                            <div style="text-align:right;">
                                <strong>Timeline Boundary:</strong> {s_str} to {f_str} <br>
                                <span style="color:#059669; font-weight:600;\">Stage Value allocation: {CURRENCY}{run_row['contract_value']:,.2f}</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    if is_admin:
                        if st.button("🗑️ Delete Scheduled Job Flow", key=f"del_sched_{tid}", use_container_width=True, type="secondary"):
                            try:
                                supabase.table('jobs').delete().eq('tracking_id', tid).execute()
                                st.success(f"Production schedule {tid} successfully removed.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed to clear job sequence: {str(e)}")
