import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
import math
from supabase import create_client, Client
import plotly.express as px

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Appointed Time - Elite Planner", layout="wide")

# Custom CSS for a high-end ERP feel
st.markdown("""
    <style>
    .main { background-color: #f8fafc; }
    [data-testid="stMetricValue"] { font-size: 2rem; font-weight: 800; color: #1e3a8a; }
    .stTabs [data-baseweb="tab"] { height: 50px; background-color: #ffffff; border-radius: 8px 8px 0 0; margin-right: 4px; border: 1px solid #e2e8f0; }
    .stTabs [aria-selected="true"] { background-color: #1e3a8a !important; color: white !important; }
    .header-style { font-size: 2.2rem; font-weight: 900; color: #1e3a8a; border-bottom: 3px solid #1e3a8a; margin-bottom: 20px; }
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
    # Weekday check (0=Monday, 6=Sunday)
    if not weekend_work and dt.weekday() >= 5:
        return False
    # Hours check (8am to 5pm)
    if not night_shift:
        if dt.hour < 8 or dt.hour >= 17:
            return False
    return True

def calculate_production_end(start_time, duration_hours, night_shift, weekend_work):
    current_time = start_time
    remaining_hours = duration_hours
    
    # Step through time in 15-minute increments for precision
    step_minutes = 15
    while remaining_hours > 0:
        if is_working_time(current_time, night_shift, weekend_work):
            remaining_hours -= (step_minutes / 60)
        current_time += timedelta(minutes=step_minutes)
        
        # Safety break for logic errors
        if (current_time - start_time).days > 365: break 
        
    return current_time

# --- BACKEND LOGIC ---
def get_db_jobs():
    if not supabase: return pd.DataFrame()
    res = supabase.table('jobs').select("*").execute()
    return pd.DataFrame(res.data)

def delete_job(job_name):
    try:
        supabase.table('jobs').delete().eq('job_name', job_name).execute()
        return True
    except: return False

def add_job_to_queue(name, rep, qty, ups, impressions, processes, total_value, night_shift, weekend_work):
    # Start simulation from "Now"
    now_base = datetime.now(timezone.utc).replace(microsecond=0)
    rev_per_step = total_value / len(processes) if processes else 0
    current_jobs = get_db_jobs()
    
    # Track the finish time of the previous process to start the next one
    job_sequence_start = now_base

    for proc in processes:
        # Determine the earliest this machine is free
        machine_free_at = now_base
        if not current_jobs.empty:
            current_jobs['finish_time'] = pd.to_datetime(current_jobs['finish_time'], format='ISO8601', utc=True)
            m_jobs = current_jobs[current_jobs['machine'] == proc]
            if not m_jobs.empty:
                machine_free_at = max(now_base, m_jobs['finish_time'].max())

        # Start process when BOTH machine is free AND previous stage is done
        actual_start = max(machine_free_at, job_sequence_start)
        
        # Ensure start time is actually a working minute
        while not is_working_time(actual_start, night_shift, weekend_work):
            actual_start += timedelta(minutes=15)

        duration = SETUP_HOURS + (impressions / MACHINE_DATA[proc]['rate'])
        actual_finish = calculate_production_end(actual_start, duration, night_shift, weekend_work)
        
        # Update sequence start for the NEXT process in this job
        job_sequence_start = actual_finish

        supabase.table('jobs').insert({
            "job_name": name, "sales_rep": rep, "quantity": qty,
            "ups": ups, "impressions": impressions,
            "contract_value": float(rev_per_step), "machine": proc,
            "start_time": actual_start.isoformat(), "finish_time": actual_finish.isoformat()
        }).execute()

# --- INTERFACE ---
st.markdown('<div class="header-style">🏢 Appointed Time Production Intelligence</div>', unsafe_allow_html=True)
tab_dash, tab_plan, tab_control = st.tabs(["📊 Executive Dashboard", "📝 New Simulation", "📅 Production Control"])

# 1. Executive Dashboard
with tab_dash:
    jobs_df = get_db_jobs()
    if not jobs_df.empty:
        jobs_df['start_time'] = pd.to_datetime(jobs_df['start_time'], format='ISO8601', utc=True)
        jobs_df['finish_time'] = pd.to_datetime(jobs_df['finish_time'], format='ISO8601', utc=True)
        jobs_df['duration_hrs'] = (jobs_df['finish_time'] - jobs_df['start_time']).dt.total_seconds() / 3600

        c1, c2, c3 = st.columns(3)
        c1.metric("Projected Revenue", f"{CURRENCY}{jobs_df['contract_value'].sum():,.2f}")
        c2.metric("Active Workflows", jobs_df['job_name'].nunique())
        c3.metric("Machine Asset Load", f"{jobs_df['machine'].nunique()} Machines")
        
        st.divider()
        st.subheader("⚙️ Machine Load Factor")
        load_df = jobs_df.groupby('machine')['duration_hrs'].sum().reset_index().sort_values('duration_hrs')
        fig_load = px.bar(load_df, x='duration_hrs', y='machine', orientation='h', template="plotly_white", color='duration_hrs', color_continuous_scale='Blues')
        st.plotly_chart(fig_load, use_container_width=True)

        st.divider()
        st.subheader("📋 Active Project Overview")
        for job_name, group in jobs_df.groupby('job_name'):
            total_rev = group['contract_value'].sum()
            final_ready = group['finish_time'].max().strftime('%b %d, %I:%M %p')
            with st.expander(f"💼 {job_name.upper()} | Value: {CURRENCY}{total_rev:,.2f} | Final Ready: {final_ready}"):
                detail_df = group[['machine', 'duration_hrs', 'finish_time']].copy()
                detail_df['Completion'] = detail_df['finish_time'].dt.strftime('%b %d, %I:%M %p')
                st.table(detail_df[['machine', 'Completion']])
                if st.button(f"Cancel Project: {job_name}", key=f"del_{job_name}"):
                    if delete_job(job_name): st.rerun()
    else: st.info("No active projects.")

# 2. Plan Job
with tab_plan:
    with st.form("new_job"):
        c1, c2 = st.columns(2)
        name = c1.text_input("Job/Client Name")
        rep = c2.selectbox("Sales Rep", ["Mabel Ampofo", "Daphne Sarpong", "Elizabeth Akoto", "Charles Adoo", "Christian Mante", "Bertha Tackie", "Reginald Aidam"])
        q, u, v = st.columns(3)
        qty = q.number_input("Quantity", value=5000)
        ups_v = u.number_input("Ups", value=1)
        val = v.number_input("Total Value", value=1000.0)
        procs = st.multiselect("Machine Routing", list(MACHINE_DATA.keys()))
        
        st.markdown("### 🕒 Shift Preferences")
        col_a, col_b = st.columns(2)
        night = col_a.toggle("🌙 Enable Night Shift (24hr)")
        wknd = col_b.toggle("📅 Include Weekends")
        
        if st.form_submit_button("Commit to Timeline"):
            if name and procs:
                add_job_to_queue(name, rep, qty, ups_v, math.ceil(qty/ups_v), procs, val, night, wknd)
                st.rerun()

# 3. Production Control
with tab_control:
    jobs_df = get_db_jobs()
    if not jobs_df.empty:
        jobs_df['start_time'] = pd.to_datetime(jobs_df['start_time'], format='ISO8601', utc=True)
        jobs_df['finish_time'] = pd.to_datetime(jobs_df['finish_time'], format='ISO8601', utc=True)
        fig = px.timeline(jobs_df, x_start="start_time", x_end="finish_time", y="machine", color="job_name", template="plotly_white")
        fig.update_layout(height=400, showlegend=False, xaxis=dict(title="", side="top"), yaxis=dict(title="", autorange="reversed"))
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("📅 Dispatch Schedule")
        for job_name, stages in jobs_df.groupby('job_name'):
            with st.expander(f"📦 {job_name.upper()}"):
                disp = stages[['machine', 'start_time', 'finish_time']].copy()
                disp['Start'] = disp['start_time'].dt.strftime('%b %d, %I:%M %p')
                disp['Ready'] = disp['finish_time'].dt.strftime('%b %d, %I:%M %p')
                st.table(disp[['machine', 'Start', 'Ready']])
    else: st.info("No active production.")