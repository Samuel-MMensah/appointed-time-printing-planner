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

def add_job_to_queue(name, rep, qty, ups, impressions, processes, total_value, night_shift):
    now_base = datetime.now(timezone.utc).replace(microsecond=0)
    rev_per_step = total_value / len(processes) if processes else 0
    current_jobs = get_db_jobs()
    
    for proc in processes:
        current_start = now_base
        if not current_jobs.empty:
            # FIX: Use ISO8601 format for robust parsing
            current_jobs['finish_time'] = pd.to_datetime(current_jobs['finish_time'], format='ISO8601', utc=True)
            m_jobs = current_jobs[current_jobs['machine'] == proc]
            if not m_jobs.empty:
                current_start = max(now_base, m_jobs['finish_time'].max())

        duration = SETUP_HOURS + (impressions / MACHINE_DATA[proc]['rate'])
        
        actual_start = current_start 
        if not night_shift and (actual_start.hour >= 17 or actual_start.hour < 8):
             actual_start = (actual_start + timedelta(days=1)).replace(hour=8, minute=0)
        
        actual_finish = actual_start + timedelta(hours=duration)
        
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
        # FIX: Robust ISO parsing for the dashboard
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
        fig_load = px.bar(
            load_df, x='duration_hrs', y='machine', orientation='h',
            text='duration_hrs', color='duration_hrs', color_continuous_scale='Blues',
            template="plotly_white", title="Total Hours Queued per Machine"
        )
        fig_load.update_traces(texttemplate='%{text:.1f} hrs', textposition='outside')
        st.plotly_chart(fig_load, use_container_width=True)

        st.divider()
        st.subheader("📋 Active Project Overview")

        for job_name, group in jobs_df.groupby('job_name'):
            total_rev = group['contract_value'].sum()
            final_ready = group['finish_time'].max().strftime('%b %d, %I:%M %p')
            with st.expander(f"💼 {job_name.upper()} | Value: {CURRENCY}{total_rev:,.2f} | Final Ready: {final_ready}"):
                detail_df = group[['machine', 'sales_rep', 'duration_hrs', 'finish_time']].copy()
                detail_df['Allocated Time'] = detail_df['duration_hrs'].map('{:,.2f} Hours'.format)
                detail_df['Completion'] = detail_df['finish_time'].dt.strftime('%b %d, %I:%M %p')
                st.table(detail_df[['machine', 'sales_rep', 'Allocated Time', 'Completion']])
                
                if st.button(f"Cancel Project: {job_name}", key=f"del_{job_name}"):
                    if delete_job(job_name): st.rerun()
    else:
        st.info("No active projects.")

# 2. Plan Job
with tab_plan:
    with st.form("new_job"):
        c1, c2 = st.columns(2)
        name = c1.text_input("Job/Client Name")
        rep = c2.selectbox("Sales Rep", ["Mabel Ampofo", "Daphne Sarpong", "Elizabeth Akoto", "Charles Adoo", "Christian Mante", "Bertha Tackie"])
        q, u, v = st.columns(3)
        qty = q.number_input("Quantity", value=5000)
        ups_v = u.number_input("Ups", value=1)
        val = v.number_input("Total Value", value=1000.0)
        procs = st.multiselect("Machine Routing", list(MACHINE_DATA.keys()))
        night = st.toggle("🌙 Enable 24-Hour Production")
        if st.form_submit_button("Commit to Timeline"):
            if name and procs:
                add_job_to_queue(name, rep, qty, ups_v, math.ceil(qty/ups_v), procs, val, night)
                st.rerun()

# 3. Production Control
with tab_control:
    jobs_df = get_db_jobs()
    if not jobs_df.empty:
        # FIX: Unified robust date parsing
        jobs_df['start_time'] = pd.to_datetime(jobs_df['start_time'], format='ISO8601', utc=True)
        jobs_df['finish_time'] = pd.to_datetime(jobs_df['finish_time'], format='ISO8601', utc=True)
        
        fig = px.timeline(
            jobs_df, x_start="start_time", x_end="finish_time", y="machine",
            color="job_name", text="job_name", template="plotly_white"
        )
        fig.update_traces(textposition="inside", insidetextanchor="middle")
        fig.update_layout(height=400, showlegend=False, xaxis=dict(tickformat="%d %b\n%H:%M", dtick=3600000 * 12, title="", side="top"), yaxis=dict(title="", autorange="reversed"))
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("📅 Dispatch Schedule")
        jobs_df['job_final_finish'] = jobs_df.groupby('job_name')['finish_time'].transform('max')
        for job_name, stages in jobs_df.sort_values('job_final_finish').groupby('job_name', sort=False):
            ready_t = stages['finish_time'].max().strftime('%A, %b %d at %I:%M %p')
            with st.expander(f"📦 {job_name.upper()} — Final Completion: {ready_t}"):
                stages['duration_hrs'] = (stages['finish_time'] - stages['start_time']).dt.total_seconds() / 3600
                disp = stages[['machine', 'start_time', 'finish_time', 'duration_hrs']].copy()
                disp['Start'] = disp['start_time'].dt.strftime('%b %d, %I:%M %p')
                disp['Ready'] = disp['finish_time'].dt.strftime('%b %d, %I:%M %p')
                disp['Allocated Time'] = disp['duration_hrs'].map('{:,.2f} Hours'.format)
                st.table(disp[['machine', 'Start', 'Ready', 'Allocated Time']])
    else:
        st.info("No active production.")