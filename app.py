import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone, time
import math
from supabase import create_client, Client
import plotly.express as px

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Appointed Time - Elite Planner", layout="wide", page_icon="🏢")

# Custom CSS for high-end ERP aesthetics
st.markdown("""
    <style>
    .main { background-color: #f8fafc; }
    [data-testid="stMetricValue"] { font-size: 1.8rem; font-weight: 800; color: #1e3a8a; }
    .stTabs [data-baseweb="tab"] { height: 50px; background-color: #ffffff; border-radius: 8px 8px 0 0; margin-right: 4px; border: 1px solid #e2e8f0; }
    .stTabs [aria-selected="true"] { background-color: #1e3a8a !important; color: white !important; }
    .header-style { font-size: 2.2rem; font-weight: 900; color: #1e3a8a; border-bottom: 3px solid #1e3a8a; margin-bottom: 20px; }
    .status-open { color: #16a34a; font-weight: bold; }
    .status-closed { color: #dc2626; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# Machine Rates & Global Setup
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
SETUP_HOURS = 2.0  
CURRENCY = "GH₵"

@st.cache_resource
def init_supabase():
    try:
        return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except: return None

supabase: Client = init_supabase()

# --- TIME ENGINE: CALENDAR AWARENESS ---
def is_working_time(dt, night_shift, weekend_work):
    if not weekend_work and dt.weekday() >= 5:
        return False
    if not night_shift:
        if dt.hour < 8 or dt.hour >= 17:
            return False
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

# --- DATABASE OPERATIONS ---
def get_db_jobs():
    if not supabase: return pd.DataFrame()
    res = supabase.table('jobs').select("*").execute()
    return pd.DataFrame(res.data)

def delete_job(job_name):
    try:
        supabase.table('jobs').delete().eq('job_name', job_name).execute()
        return True
    except: return False

def add_job_to_queue(name, rep, qty, ups, impressions, processes, total_value, night_shift, weekend_work, custom_start_dt):
    # Use selected future date OR current time
    now_base = custom_start_dt if custom_start_dt else datetime.now(timezone.utc).replace(microsecond=0)
    rev_per_step = total_value / len(processes) if processes else 0
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

        supabase.table('jobs').insert({
            "job_name": name, "sales_rep": rep, "quantity": qty,
            "ups": ups, "impressions": impressions,
            "contract_value": float(rev_per_step), "machine": proc,
            "start_time": actual_start.isoformat(), "finish_time": actual_finish.isoformat()
        }).execute()

# --- HEADER SECTION ---
c_head, c_status = st.columns([3, 1])
c_head.markdown('<div class="header-style">🏢 Appointed Time Production Intelligence</div>', unsafe_allow_html=True)

now_gmt = datetime.now(timezone.utc)
is_open = is_working_time(now_gmt, False, False)
status_html = '<p class="status-open">● SHOP OPEN</p>' if is_open else '<p class="status-closed">○ SHOP CLOSED (Standard Hours)</p>'
c_status.markdown(f"<div style='text-align: right; padding-top: 25px;'>{status_html}</div>", unsafe_allow_html=True)

tab_dash, tab_plan, tab_control = st.tabs(["📊 Executive Dashboard", "📝 New Simulation", "📅 Production Control"])

# --- 1. EXECUTIVE DASHBOARD ---
with tab_dash:
    jobs_df = get_db_jobs()
    if not jobs_df.empty:
        jobs_df['start_time'] = pd.to_datetime(jobs_df['start_time'], format='ISO8601', utc=True)
        jobs_df['finish_time'] = pd.to_datetime(jobs_df['finish_time'], format='ISO8601', utc=True)
        jobs_df['duration_hrs'] = (jobs_df['finish_time'] - jobs_df['start_time']).dt.total_seconds() / 3600
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Projected Revenue", f"{CURRENCY}{jobs_df['contract_value'].sum():,.2f}")
        c2.metric("Active Jobs", jobs_df['job_name'].nunique())
        c3.metric("Machine Load", f"{jobs_df['machine'].nunique()} Assets")
        
        st.divider()
        st.subheader("📋 Client Project Status")
        for job_name, group in jobs_df.groupby('job_name'):
            total_rev = group['contract_value'].sum()
            final_ready = group['finish_time'].max().strftime('%A, %b %d at %I:%M %p')
            with st.expander(f"💼 {job_name.upper()} | Ready: {final_ready}"):
                detail_df = group[['machine', 'finish_time']].copy()
                detail_df['Completion'] = detail_df['finish_time'].dt.strftime('%b %d, %I:%M %p')
                st.table(detail_df[['machine', 'Completion']])
                if st.button(f"Cancel Job", key=f"del_{job_name}"):
                    if delete_job(job_name): st.rerun()
    else: st.info("The production queue is currently empty.")

# --- 2. PLAN NEW JOB (WITH FUTURE START) ---
with tab_plan:
    with st.form("new_job", clear_on_submit=True):
        st.subheader("📝 Job Details")
        c1, c2 = st.columns(2)
        name = c1.text_input("Client/Job Name")
        rep = c2.selectbox("Sales Rep", ["Mabel Ampofo", "Daphne Sarpong", "Elizabeth Akoto", "Charles Adoo", "Christian Mante", "Bertha Tackie", "Reginald Aidam"])
        
        q, u, v = st.columns(3)
        qty = q.number_input("Total Quantity", min_value=1, value=5000)
        ups_v = u.number_input("Ups per Sheet", min_value=1, value=1)
        val = v.number_input("Total Value", min_value=0.0, value=1000.0)
        
        procs = st.multiselect("Machine Routing", list(MACHINE_DATA.keys()))
        
        st.divider()
        st.subheader("📅 Production Start Timing")
        sc1, sc2 = st.columns(2)
        start_date = sc1.date_input("Scheduled Start Date", value=datetime.now(timezone.utc).date())
        start_time = sc2.time_input("Scheduled Start Time", value=time(8, 0)) # Default to 8am start
        
        # Merge date and time into a single UTC object
        combined_start_dt = datetime.combine(start_date, start_time).replace(tzinfo=timezone.utc)
        
        st.subheader("🕒 Operational Overrides")
        col_a, col_b = st.columns(2)
        night = col_a.toggle("🌙 Enable Night Shift")
        wknd = col_b.toggle("📅 Include Weekends")
        
        if st.form_submit_button("Commit to Live Schedule"):
            if name and procs:
                add_job_to_queue(name, rep, qty, ups_v, math.ceil(qty/ups_v), procs, val, night, wknd, combined_start_dt)
                st.success(f"Job '{name}' scheduled successfully!")
                st.rerun()
            else: st.error("Please fill in the Job Name and Machine Processes.")

# --- 3. PRODUCTION CONTROL ---
with tab_control:
    jobs_df = get_db_jobs()
    if not jobs_df.empty:
        jobs_df['start_time'] = pd.to_datetime(jobs_df['start_time'], format='ISO8601', utc=True)
        jobs_df['finish_time'] = pd.to_datetime(jobs_df['finish_time'], format='ISO8601', utc=True)
        st.subheader("GANTT Chart View")
        fig = px.timeline(jobs_df, x_start="start_time", x_end="finish_time", y="machine", color="job_name", template="plotly_white")
        fig.update_layout(height=450, xaxis=dict(title="Timeline", side="top"), yaxis=dict(title="", autorange="reversed"))
        st.plotly_chart(fig, use_container_width=True)
    else: st.info("No active production schedules.")