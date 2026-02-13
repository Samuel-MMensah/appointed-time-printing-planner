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

# --- TIME ENGINE ---
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

def add_job_to_queue(name, rep, qty, ups, impressions, processes, total_value, night_shift, weekend_work, custom_start):
    # Base start is either 'Now' or the user's chosen future date
    now_base = datetime.now(timezone.utc).replace(microsecond=0)
    sim_start_base = max(now_base, custom_start)
    
    rev_per_step = total_value / len(processes) if processes else 0
    current_jobs = get_db_jobs()
    
    # Track sequence within this specific project
    job_sequence_tracker = sim_start_base

    for proc in processes:
        # Check when this specific machine is actually available
        machine_free_at = sim_start_base
        if not current_jobs.empty:
            current_jobs['finish_time'] = pd.to_datetime(current_jobs['finish_time'], format='ISO8601', utc=True)
            m_jobs = current_jobs[current_jobs['machine'] == proc]
            if not m_jobs.empty:
                machine_free_at = max(sim_start_base, m_jobs['finish_time'].max())

        # Logic: Start when BOTH machine is free AND previous step in THIS job is done
        actual_start = max(machine_free_at, job_sequence_tracker)
        
        # Snap to next available working window
        while not is_working_time(actual_start, night_shift, weekend_work):
            actual_start += timedelta(minutes=15)

        duration = SETUP_HOURS + (impressions / MACHINE_DATA[proc]['rate'])
        actual_finish = calculate_production_end(actual_start, duration, night_shift, weekend_work)
        
        job_sequence_tracker = actual_finish

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
status_html = '<p class="status-open">● SHOP OPEN</p>' if is_open else '<p class="status-closed">○ SHOP CLOSED</p>'
c_status.markdown(f"<div style='text-align: right; padding-top: 25px;'>{status_html}</div>", unsafe_allow_html=True)

tab_dash, tab_plan, tab_control = st.tabs(["📊 Executive Dashboard", "📝 New Simulation", "📅 Production Control"])

# --- 1. DASHBOARD ---
with tab_dash:
    jobs_df = get_db_jobs()
    if not jobs_df.empty:
        jobs_df['start_time'] = pd.to_datetime(jobs_df['start_time'], format='ISO8601', utc=True)
        jobs_df['finish_time'] = pd.to_datetime(jobs_df['finish_time'], format='ISO8601', utc=True)
        jobs_df['duration_hrs'] = (jobs_df['finish_time'] - jobs_df['start_time']).dt.total_seconds() / 3600

        c1, c2, c3 = st.columns(3)
        c1.metric("Projected Revenue", f"{CURRENCY}{jobs_df['contract_value'].sum():,.2f}")
        c2.metric("Active Jobs", jobs_df['job_name'].nunique())
        c3.metric("Machines Engaged", jobs_df['machine'].nunique())
        
        st.divider()
        load_df = jobs_df.groupby('machine')['duration_hrs'].sum().reset_index().sort_values('duration_hrs')
        fig_load = px.bar(load_df, x='duration_hrs', y='machine', orientation='h', template="plotly_white", color_continuous_scale='Blues', title="Total Machine Load (Hours)")
        st.plotly_chart(fig_load, use_container_width=True)
        
        st.subheader("📋 Active Project List")
        for job_name, group in jobs_df.groupby('job_name'):
            with st.expander(f"💼 {job_name.upper()} — Ready: {group['finish_time'].max().strftime('%b %d, %I:%M %p')}"):
                st.table(group[['machine', 'finish_time']].rename(columns={'finish_time': 'Ready At'}))
                if st.button("Delete Job", key=f"del_{job_name}"):
                    if delete_job(job_name): st.rerun()
    else: st.info("No active projects.")

# --- 2. PLANNING (FEATURING FUTURE START) ---
with tab_plan:
    with st.form("new_job_form"):
        st.subheader("📋 Job & Start Details")
        c1, c2, c3 = st.columns([2, 1, 1])
        name = c1.text_input("Job/Client Name")
        start_date = c2.date_input("Scheduled Start Date", value=datetime.now())
        start_time = c3.time_input("Start Time", value=time(8, 0))
        
        # Combine date and time into a UTC-aware datetime
        combined_start = datetime.combine(start_date, start_time).replace(tzinfo=timezone.utc)
        
        rep = st.selectbox("Sales Rep", ["Mabel Ampofo", "Daphne Sarpong", "Elizabeth Akoto", "Charles Adoo", "Christian Mante", "Bertha Tackie", "Reginald Aidam"])
        
        q, u, v = st.columns(3)
        qty = q.number_input("Quantity", min_value=1, value=5000)
        ups_v = u.number_input("Ups", min_value=1, value=1)
        val = v.number_input("Value (GH₵)", min_value=0.0, value=1000.0)
        
        procs = st.multiselect("Machine Routing", list(MACHINE_DATA.keys()))
        
        st.markdown("---")
        col_a, col_b = st.columns(2)
        night = col_a.toggle("🌙 Enable Night Shift")
        wknd = col_b.toggle("📅 Work Weekends")
        
        if st.form_submit_button("Commit to Timeline"):
            if name and procs:
                add_job_to_queue(name, rep, qty, ups_v, math.ceil(qty/ups_v), procs, val, night, wknd, combined_start)
                st.success(f"Successfully scheduled {name}")
                st.rerun()

# --- 3. CONTROL ---
with tab_control:
    jobs_df = get_db_jobs()
    if not jobs_df.empty:
        jobs_df['start_time'] = pd.to_datetime(jobs_df['start_time'], format='ISO8601', utc=True)
        jobs_df['finish_time'] = pd.to_datetime(jobs_df['finish_time'], format='ISO8601', utc=True)
        fig = px.timeline(jobs_df, x_start="start_time", x_end="finish_time", y="machine", color="job_name", template="plotly_white")
        fig.update_layout(height=400, yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, use_container_width=True)
    else: st.info("Production control is empty.")