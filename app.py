import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
import math
import random
from supabase import create_client, Client
import plotly.express as px

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(page_title="Appointed Time - Elite Planner", layout="wide", page_icon="🏢")

# --- 2. GLOBAL SETUP & TARGETS ---
CURRENCY = "GH₵"
ANNUAL_REVENUE_TARGET = 2000000.00
SETUP_HOURS = 2.0  

# Custom CSS
st.markdown("""
    <style>
    .main { background-color: #f8fafc; }
    [data-testid="stMetricValue"] { font-size: 1.8rem; font-weight: 800; color: #1e3a8a; }
    .stTabs [data-baseweb="tab"] { height: 50px; background-color: #ffffff; border-radius: 8px 8px 0 0; margin-right: 4px; border: 1px solid #e2e8f0; }
    .stTabs [aria-selected="true"] { background-color: #1e3a8a !important; color: white !important; }
    .header-style { font-size: 2.2rem; font-weight: 900; color: #1e3a8a; border-bottom: 3px solid #1e3a8a; margin-bottom: 20px; }
    .status-open { color: #16a34a; font-weight: bold; text-align: right; }
    .status-closed { color: #dc2626; font-weight: bold; text-align: right; }
    .tracking-card { padding: 20px; border-radius: 10px; border: 1px solid #e2e8f0; background: white; margin-bottom: 10px; }
    </style>
    """, unsafe_allow_html=True)

MACHINE_DATA = {
    'SM102-CX FOUR COLOUR': {'rate': 8000}, 'SM102-P FIVE COLOUR': {'rate': 7500},
    'SM 52': {'rate': 7000}, 'GTO 52 SEMI-AUTO-2 COLOUR': {'rate': 4500},
    'GTO 52 MANUAL-2 COLOUR': {'rate': 4000}, 'FOLDING UNIT CONTINUOUS FOLD': {'rate': 8000},
    'MBO-B30E SINGLE FOLD': {'rate': 16000}, 'POLAR MACHINE FOR BOOKS': {'rate': 2000},
    'POLAR MACHINE FOR SHEETS': {'rate': 50000}, '3 WAY TRIMMER': {'rate': 5000},
    'PERFECT BINDING': {'rate': 500}, 'LAMINATION UNIT': {'rate': 2500},
    'PEDDLER SADDLE STITCH': {'rate': 1000}, 'DIE CUTTER': {'rate': 3000},
    'FOLDER GLUER': {'rate': 12000},
}

@st.cache_resource
def init_supabase():
    try:
        return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except: return None

supabase: Client = init_supabase()

# --- 3. CORE ENGINES ---
def is_working_time(dt, night_shift, weekend_work):
    if not weekend_work and dt.weekday() >= 5: return False
    if not night_shift:
        if dt.hour < 8 or dt.hour >= 17: return False
    return True

def calculate_production_end(start_time, duration_hours, night_shift, weekend_work):
    current_time = start_time
    remaining_hours = duration_hours
    step_minutes = 15
    while remaining_hours > 0:
        if is_working_time(current_time, night_shift, weekend_work):
            remaining_hours -= (step_minutes / 60)
        current_time += timedelta(minutes=step_minutes)
        if (current_time - start_time).days > 365: break 
    return current_time

# --- 4. DATABASE OPERATIONS ---
def get_db_jobs():
    if not supabase: return pd.DataFrame()
    res = supabase.table('jobs').select("*").execute()
    return pd.DataFrame(res.data)

def delete_job(job_name):
    try:
        supabase.table('jobs').delete().eq('job_name', job_name).execute()
        return True
    except: return False

def add_job_to_queue(name, rep, qty, ups, impressions, processes, total_value, night_shift, weekend_work, start_date, material_costs, overhead_rate):
    now_base = datetime.combine(start_date, datetime.now().time()).replace(tzinfo=timezone.utc, microsecond=0)
    rev_per_step = total_value / len(processes) if processes else 0
    mat_cost_per_step = material_costs / len(processes) if processes else 0
    
    # Generate Unique Tracking ID (Amazon Style)
    tracking_id = f"AT-{random.randint(1000, 9999)}"
    
    current_jobs = get_db_jobs()
    job_sequence_start = now_base

    for proc in processes:
        machine_free_at = now_base
        if not current_jobs.empty:
            current_jobs['finish_time'] = pd.to_datetime(current_jobs['finish_time'], format='ISO8601', utc=True)
            m_jobs = current_jobs[current_jobs['machine'] == proc]
            if not m_jobs.empty:
                machine_free_at = max(now_base, m_jobs['finish_time'].max())

        actual_start = max(machine_free_at, job_sequence_start)
        while not is_working_time(actual_start, night_shift, weekend_work):
            actual_start += timedelta(minutes=15)

        duration = SETUP_HOURS + (impressions / MACHINE_DATA[proc]['rate'])
        actual_finish = calculate_production_end(actual_start, duration, night_shift, weekend_work)
        job_sequence_start = actual_finish
        
        step_overhead = duration * overhead_rate
        step_net_profit = rev_per_step - mat_cost_per_step - step_overhead

        supabase.table('jobs').insert({
            "job_name": name, "sales_rep": rep, "quantity": qty,
            "ups": ups, "impressions": impressions,
            "contract_value": float(rev_per_step), "machine": proc,
            "start_time": actual_start.isoformat(), "finish_time": actual_finish.isoformat(),
            "material_costs": float(mat_cost_per_step),
            "overhead_rate": float(overhead_rate),
            "net_profit": float(step_net_profit),
            "tracking_id": tracking_id
        }).execute()
    return tracking_id

# --- 5. UI HEADER ---
c_head, c_status = st.columns([3, 1])
c_head.markdown('<div class="header-style">🏢 Appointed Time Production Intelligence</div>', unsafe_allow_html=True)

now_gmt = datetime.now(timezone.utc)
is_open = is_working_time(now_gmt, False, False)
status_label = '● SHOP OPEN' if is_open else '○ SHOP CLOSED (Standard Hours)'
status_class = 'status-open' if is_open else 'status-closed'
c_status.markdown(f"<div style='padding-top: 25px;' class='{status_class}'>{status_label}</div>", unsafe_allow_html=True)

tab_dash, tab_plan, tab_control, tab_track = st.tabs(["📊 Executive Dashboard", "📝 New Simulation", "📅 Production Control", "🚛 Track & Trace"])

# --- 6. DASHBOARD TAB ---
with tab_dash:
    jobs_df = get_db_jobs()
    if not jobs_df.empty:
        jobs_df['start_time'] = pd.to_datetime(jobs_df['start_time'], format='ISO8601', utc=True)
        jobs_df['finish_time'] = pd.to_datetime(jobs_df['finish_time'], format='ISO8601', utc=True)
        jobs_df['duration_hrs'] = (jobs_df['finish_time'] - jobs_df['start_time']).dt.total_seconds() / 3600

        projected_rev = jobs_df['contract_value'].sum()
        total_net_profit = jobs_df.get('net_profit', pd.Series([0])).sum(skipna=True)
        margin_pct = (total_net_profit / projected_rev * 100) if projected_rev > 0 else 0
        variance = projected_rev - ANNUAL_REVENUE_TARGET

        st.subheader("💰 Financial Performance vs. Annual Target")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Current Projected Revenue", f"{CURRENCY}{projected_rev:,.2f}")
        m2.metric("Estimated Net Profit", f"{CURRENCY}{total_net_profit:,.2f}")
        m3.metric("Overall Profit Margin", f"{margin_pct:.1f}%")
        m4.metric("Variance to Target", f"{CURRENCY}{variance:,.2f}", delta=f"{variance:,.2f}")

        st.divider()
        st.subheader("📋 Client Project Status")
        for job_name, group in jobs_df.groupby('job_name'):
            total_rev = group['contract_value'].sum()
            t_id = group['tracking_id'].iloc[0] if 'tracking_id' in group.columns else "N/A"
            final_ready = group['finish_time'].max().strftime('%b %d at %I:%M %p')
            with st.expander(f"💼 {job_name.upper()} | ID: {t_id} | Value: {CURRENCY}{total_rev:,.2f} | Ready: {final_ready}"):
                st.write(f"**Unique Tracking ID:** `{t_id}`")
                if st.button(f"Cancel Job", key=f"del_{job_name}"):
                    if delete_job(job_name): st.rerun()
    else: st.info("The production queue is currently empty.")

# --- 7. PLAN NEW JOB ---
with tab_plan:
    with st.form("new_job", clear_on_submit=True):
        st.subheader("📝 Simulation Parameters")
        c1, c2 = st.columns(2)
        name = c1.text_input("Client/Job Name", placeholder="e.g., ABC Magazine")
        rep = c2.selectbox("Assigned Sales Rep", ["Mabel Ampofo", "Daphne Sarpong", "Elizabeth Akoto", "Charles Adoo", "Christian Mante", "Bertha Tackie", "Reginald Aidam"])
        
        q, u, v = st.columns(3)
        qty = q.number_input("Total Quantity", min_value=1, value=5000)
        ups_v = u.number_input("Ups per Sheet", min_value=1, value=1)
        val = v.number_input("Total Contract Value", min_value=0.0, value=1000.0)
        
        st.markdown("---")
        st.subheader("💸 Financial Costing")
        cost1, cost2 = st.columns(2)
        mat_costs = cost1.number_input("Estimated Material Costs (Paper, Ink, Plates)", min_value=0.0, value=250.0)
        ovh_rate = cost2.number_input("Hourly Overhead Rate", min_value=0.0, value=50.0)

        st.markdown("---")
        c_date, c_procs = st.columns([1, 2])
        start_date = c_date.date_input("📅 Scheduled Start Date", value=datetime.now().date())
        procs = c_procs.multiselect("Machine Routing", list(MACHINE_DATA.keys()))
        
        night = st.toggle("🌙 Enable Night Shift")
        wknd = st.toggle("📅 Include Weekends")
        
        if st.form_submit_button("Commit to Live Schedule"):
            if name and procs:
                tid = add_job_to_queue(name, rep, qty, ups_v, math.ceil(qty/ups_v), procs, val, night, wknd, start_date, mat_costs, ovh_rate)
                st.success(f"Job '{name}' added! **Tracking ID: {tid}**")
                st.info(f"Give this ID to the client for the Track & Trace portal.")
                st.rerun()
            else: st.error("Please provide both a Client Name and at least one Machine Process.")

# --- 8. PRODUCTION CONTROL ---
with tab_control:
    jobs_df = get_db_jobs()
    if not jobs_df.empty:
        jobs_df['start_time'] = pd.to_datetime(jobs_df['start_time'], format='ISO8601', utc=True)
        jobs_df['finish_time'] = pd.to_datetime(jobs_df['finish_time'], format='ISO8601', utc=True)
        st.subheader("📊 GANTT Chart View")
        fig = px.timeline(jobs_df, x_start="start_time", x_end="finish_time", y="machine", color="job_name", template="plotly_white")
        st.plotly_chart(fig, use_container_width=True)
    else: st.info("No production schedules to display.")

# --- 9. NEW: TRACK & TRACE PORTAL ---
with tab_track:
    st.subheader("🚛 Automated Client Order Tracking")
    search_id = st.text_input("Enter your Unique Tracking ID (e.g., AT-1234)", placeholder="AT-XXXX").strip().upper()
    
    if search_id:
        all_jobs = get_db_jobs()
        if not all_jobs.empty and 'tracking_id' in all_jobs.columns:
            client_job = all_jobs[all_jobs['tracking_id'] == search_id].copy()
            
            if not client_job.empty:
                client_job['finish_time'] = pd.to_datetime(client_job['finish_time'], format='ISO8601', utc=True)
                client_job = client_job.sort_values('finish_time')
                
                # Calculate Progress
                total_steps = len(client_job)
                completed_steps = len(client_job[client_job['finish_time'] < datetime.now(timezone.utc)])
                progress = completed_steps / total_steps
                
                st.markdown(f"### Order Status for: **{client_job['job_name'].iloc[0]}**")
                st.progress(progress)
                st.write(f"**Overall Completion: {int(progress * 100)}%**")
                
                for idx, row in client_job.iterrows():
                    is_done = row['finish_time'] < datetime.now(timezone.utc)
                    status_icon = "✅ COMPLETE" if is_done else "⏳ SCHEDULED / IN PROGRESS"
                    st.markdown(f"""
                    <div class="tracking-card">
                        <strong>Stage: {row['machine']}</strong><br>
                        Status: {status_icon}<br>
                        <small>Estimated Finish: {row['finish_time'].strftime('%b %d, %I:%M %p')}</small>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.error("Tracking ID not found. Please check with your Sales Representative.")
        else:
            st.info("No jobs found in the system.")