import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
import math
from supabase import create_client, Client
import plotly.express as px

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(page_title="Appointed Time - Elite Planner", layout="wide", page_icon="🏢")

# --- 2. GLOBAL SETUP & TARGETS ---
CURRENCY = "GH₵"
ANNUAL_REVENUE_TARGET = 2000000.00  # <--- ADJUST YOUR ANNUAL GOAL HERE
SETUP_HOURS = 2.0  

# Custom CSS & Header Rendering Fix
st.markdown("""
    <style>
    .main { background-color: #f8fafc; }
    [data-testid="stMetricValue"] { font-size: 1.8rem; font-weight: 800; color: #1e3a8a; }
    .stTabs [data-baseweb="tab"] { height: 50px; background-color: #ffffff; border-radius: 8px 8px 0 0; margin-right: 4px; border: 1px solid #e2e8f0; }
    .stTabs [aria-selected="true"] { background-color: #1e3a8a !important; color: white !important; }
    .header-style { font-size: 2.2rem; font-weight: 900; color: #1e3a8a; border-bottom: 3px solid #1e3a8a; margin-bottom: 20px; }
    .status-open { color: #16a34a; font-weight: bold; text-align: right; }
    .status-closed { color: #dc2626; font-weight: bold; text-align: right; }
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
    
    # Distribute revenue and material costs evenly across production steps
    rev_per_step = total_value / len(processes) if processes else 0
    mat_cost_per_step = material_costs / len(processes) if processes else 0
    
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

        # Calculate exact duration to find overhead cost
        duration = SETUP_HOURS + (impressions / MACHINE_DATA[proc]['rate'])
        actual_finish = calculate_production_end(actual_start, duration, night_shift, weekend_work)
        job_sequence_start = actual_finish
        
        # Calculate profitability for this step
        step_overhead = duration * overhead_rate
        step_net_profit = rev_per_step - mat_cost_per_step - step_overhead

        supabase.table('jobs').insert({
            "job_name": name, "sales_rep": rep, "quantity": qty,
            "ups": ups, "impressions": impressions,
            "contract_value": float(rev_per_step), "machine": proc,
            "start_time": actual_start.isoformat(), "finish_time": actual_finish.isoformat(),
            "material_costs": float(mat_cost_per_step),
            "overhead_rate": float(overhead_rate),
            "net_profit": float(step_net_profit)
        }).execute()

# --- 5. UI HEADER ---
c_head, c_status = st.columns([3, 1])
c_head.markdown('<div class="header-style">🏢 Appointed Time Production Intelligence</div>', unsafe_allow_html=True)

now_gmt = datetime.now(timezone.utc)
is_open = is_working_time(now_gmt, False, False)
status_label = '● SHOP OPEN' if is_open else '○ SHOP CLOSED (Standard Hours)'
status_class = 'status-open' if is_open else 'status-closed'
c_status.markdown(f"<div style='padding-top: 25px;' class='{status_class}'>{status_label}</div>", unsafe_allow_html=True)

tab_dash, tab_plan, tab_control = st.tabs(["📊 Executive Dashboard", "📝 New Simulation", "📅 Production Control"])

# --- 6. DASHBOARD TAB ---
with tab_dash:
    jobs_df = get_db_jobs()
    if not jobs_df.empty:
        jobs_df['start_time'] = pd.to_datetime(jobs_df['start_time'], format='ISO8601', utc=True)
        jobs_df['finish_time'] = pd.to_datetime(jobs_df['finish_time'], format='ISO8601', utc=True)
        jobs_df['duration_hrs'] = (jobs_df['finish_time'] - jobs_df['start_time']).dt.total_seconds() / 3600

        # Calculations for Revenue & Profitability
        projected_rev = jobs_df['contract_value'].sum()
        total_net_profit = jobs_df.get('net_profit', pd.Series([0])).sum(skipna=True) # Safely sum even if some old rows are missing data
        margin_pct = (total_net_profit / projected_rev * 100) if projected_rev > 0 else 0
        variance = projected_rev - ANNUAL_REVENUE_TARGET

        st.subheader("💰 Financial Performance vs. Annual Target")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Current Projected Revenue", f"{CURRENCY}{projected_rev:,.2f}")
        m2.metric("Estimated Net Profit", f"{CURRENCY}{total_net_profit:,.2f}")
        m3.metric("Overall Profit Margin", f"{margin_pct:.1f}%")
        m4.metric("Variance to Target", f"{CURRENCY}{variance:,.2f}", delta=f"{variance:,.2f}")

        st.divider()
        st.subheader("⚡ Operational Status")
        c1, c2 = st.columns(2)
        c1.metric("Active Jobs in Queue", jobs_df['job_name'].nunique())
        c2.metric("Machine Assets in Use", jobs_df['machine'].nunique())
        
        st.divider()
        st.subheader("⚙️ Capacity Load by Machine")
        load_df = jobs_df.groupby('machine')['duration_hrs'].sum().reset_index().sort_values('duration_hrs')
        fig_load = px.bar(load_df, x='duration_hrs', y='machine', orientation='h', template="plotly_white", 
                          color='duration_hrs', color_continuous_scale='Blues', labels={'duration_hrs': 'Booked Hours'})
        st.plotly_chart(fig_load, use_container_width=True)

        st.divider()
        st.subheader("📋 Client Project Status")
        for job_name, group in jobs_df.groupby('job_name'):
            total_rev = group['contract_value'].sum()
            job_profit = group.get('net_profit', pd.Series([0])).sum(skipna=True)
            final_ready = group['finish_time'].max().strftime('%A, %b %d at %I:%M %p')
            with st.expander(f"💼 {job_name.upper()} | Value: {CURRENCY}{total_rev:,.2f} | Est. Profit: {CURRENCY}{job_profit:,.2f} | Final Ready: {final_ready}"):
                detail_df = group[['machine', 'finish_time']].copy()
                detail_df['Completion'] = detail_df['finish_time'].dt.strftime('%b %d, %I:%M %p')
                st.table(detail_df[['machine', 'Completion']])
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
        
        # ADDED: Financial Costing Inputs
        st.markdown("---")
        st.subheader("💸 Financial Costing")
        cost1, cost2 = st.columns(2)
        mat_costs = cost1.number_input("Estimated Material Costs (Paper, Ink, Plates)", min_value=0.0, value=250.0)
        ovh_rate = cost2.number_input("Hourly Overhead Rate (Labor, Power)", min_value=0.0, value=50.0, help="The cost per hour to run this job on the floor.")

        st.markdown("---")
        c_date, c_procs = st.columns([1, 2])
        start_date = c_date.date_input("📅 Scheduled Start Date", value=datetime.now().date())
        procs = c_procs.multiselect("Machine Routing (In Production Order)", list(MACHINE_DATA.keys()))
        
        st.markdown("---")
        st.subheader("🕒 Operational Overrides")
        col_a, col_b = st.columns(2)
        night = col_a.toggle("🌙 Enable Night Shift (Run through the night)")
        wknd = col_b.toggle("📅 Include Weekends (Run Sat/Sun)")
        
        if st.form_submit_button("Commit to Live Schedule"):
            if name and procs:
                # Updated to pass mat_costs and ovh_rate to the database
                add_job_to_queue(name, rep, qty, ups_v, math.ceil(qty/ups_v), procs, val, night, wknd, start_date, mat_costs, ovh_rate)
                st.success(f"Job '{name}' has been added to the queue!")
                st.rerun()
            else: st.error("Please provide both a Client Name and at least one Machine Process.")

# --- 8. PRODUCTION CONTROL ---
with tab_control:
    jobs_df = get_db_jobs()
    if not jobs_df.empty:
        jobs_df['start_time'] = pd.to_datetime(jobs_df['start_time'], format='ISO8601', utc=True)
        jobs_df['finish_time'] = pd.to_datetime(jobs_df['finish_time'], format='ISO8601', utc=True)
        
        st.subheader("📊 GANTT Chart View")
        fig = px.timeline(jobs_df, x_start="start_time", x_end="finish_time", y="machine", color="job_name", 
                          template="plotly_white", hover_data=["sales_rep"])
        fig.update_layout(height=450, showlegend=True, xaxis=dict(title="Production Timeline", side="top"), yaxis=dict(title="", autorange="reversed"))
        st.plotly_chart(fig, use_container_width=True)

        st.divider()
        st.subheader("📅 Dispatch Manifest")
        for job_name, stages in jobs_df.sort_values('finish_time').groupby('job_name', sort=False):
            with st.expander(f"📦 {job_name.upper()} Delivery Schedule"):
                disp = stages[['machine', 'start_time', 'finish_time']].copy()
                disp['Machine Start'] = disp['start_time'].dt.strftime('%b %d, %H:%M')
                disp['Estimated Finish'] = disp['finish_time'].dt.strftime('%b %d, %H:%M')
                st.table(disp[['machine', 'Machine Start', 'Estimated Finish']])
    else: st.info("No production schedules to display.")