import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time
import math
from supabase import create_client, Client
import plotly.express as px
import plotly.graph_objects as go

# Page configuration
st.set_page_config(page_title="Appointed Time - Elite Planner", layout="wide")

# Custom CSS for modern UI
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 1.8rem; font-weight: bold; color: #1e3a8a; }
    .stTabs [data-baseweb="tab"] { height: 50px; background-color: #f8fafc; border-radius: 8px; margin-right: 5px; border: 1px solid #e2e8f0; }
    .stTabs [aria-selected="true"] { background-color: #1e3a8a !important; color: white !important; font-weight: bold; }
    .main-header { font-size: 2.2rem; font-weight: 800; color: #1e3a8a; margin-bottom: 1rem; }
    </style>
    """, unsafe_allow_html=True)

# Machine data
MACHINE_DATA = {
    'SM102-CX FOUR COLOUR': {'rate': 8000},
    'SM102-P FIVE COLOUR': {'rate': 7500},
    'SM 52': {'rate': 7000},
    'GTO 52 SEMI-AUTO-2 COLOUR': {'rate': 4500},
    'GTO 52 MANUAL-2 COLOUR': {'rate': 4000},
    'FOLDING UNIT CONTINUOUS FOLD': {'rate': 8000},
    'MBO-B30E SINGLE FOLD': {'rate': 16000},
    'POLAR MACHINE FOR BOOKS': {'rate': 2000},
    'POLAR MACHINE FOR SHEETS': {'rate': 50000},
    '3 WAY TRIMMER': {'rate': 5000},
    'PERFECT BINDING': {'rate': 500},
    'LAMINATION UNIT': {'rate': 2500},
    'PEDDLER SADDLE STITCH': {'rate': 1000},
    'DIE CUTTER': {'rate': 3000},
    'FOLDER GLUER': {'rate': 12000},
}

SETUP_HOURS = 2.0  
CURRENCY = "GH₵"

@st.cache_resource
def init_supabase():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"Supabase connection issue: {e}")
        return None

supabase: Client = init_supabase()

# --- Database Helper Functions ---

def load_jobs_from_db():
    if not supabase: return []
    try:
        res = supabase.table('jobs').select("*").execute()
        return res.data
    except Exception as e:
        st.error(f"DB Load Error: {e}")
        return []

def delete_job(job_name):
    try:
        supabase.table('jobs').delete().eq('job_name', job_name).execute()
        return True
    except Exception: return False

def update_job_value(job_name, new_value):
    try:
        res = supabase.table('jobs').select("id").eq('job_name', job_name).execute()
        steps = res.data
        if steps:
            val_per_step = new_value / len(steps)
            for step in steps:
                supabase.table('jobs').update({"contract_value": val_per_step}).eq('id', step['id']).execute()
        return True
    except Exception: return False

# --- Shift & Simulation Logic ---

def get_next_working_time(start_dt, night_shift):
    if night_shift: return start_dt
    if start_dt.hour >= 17:
        start_dt = (start_dt + timedelta(days=1)).replace(hour=8, minute=0, second=0)
    elif start_dt.hour < 8:
        start_dt = start_dt.replace(hour=8, minute=0, second=0)
    return start_dt

def calculate_finish_with_shifts(start_dt, total_hours, night_shift):
    if night_shift: return start_dt + timedelta(hours=total_hours)
    current_time, remaining_hours = start_dt, total_hours
    while remaining_hours > 0:
        current_time = get_next_working_time(current_time, False)
        end_of_day = current_time.replace(hour=17, minute=0, second=0)
        available_today = (end_of_day - current_time).total_seconds() / 3600
        if remaining_hours <= available_today:
            current_time += timedelta(hours=remaining_hours)
            remaining_hours = 0
        else:
            remaining_hours -= available_today
            current_time = (current_time + timedelta(days=1)).replace(hour=8, minute=0, second=0)
    return current_time

def add_job(name, sales_rep, finished_qty, ups, impressions, processes, total_value, night_shift=False):
    current_time = datetime.now().replace(hour=8, minute=0, second=0)
    rev_per_step = total_value / len(processes) if processes else 0
    for proc in processes:
        if not st.session_state.jobs.empty:
            m_jobs = st.session_state.jobs[st.session_state.jobs['machine'] == proc]
            if not m_jobs.empty:
                last_f = pd.to_datetime(m_jobs['finish_time']).max().tz_localize(None)
                if last_f > current_time: current_time = last_f
        duration = SETUP_HOURS + (impressions / MACHINE_DATA[proc]['rate'])
        if "DIE CUTTER" in proc: current_time += timedelta(hours=8)
        if "FOLDER GLUER" in proc: current_time += timedelta(hours=2)
        start_t = get_next_working_time(current_time, night_shift)
        finish_t = calculate_finish_with_shifts(start_t, duration, night_shift)
        supabase.table('jobs').insert({
            "job_name": name, "sales_rep": sales_rep, "quantity": finished_qty,
            "ups": ups, "impressions": impressions, "contract_value": float(rev_per_step),
            "machine": proc, "start_time": start_t.isoformat(), "finish_time": finish_t.isoformat()
        }).execute()
        current_time = finish_t 
    return True

# --- State Management ---
if 'jobs' not in st.session_state: st.session_state.jobs = pd.DataFrame()
if 'db_synced' not in st.session_state: st.session_state.db_synced = False
if not st.session_state.db_synced:
    st.session_state.jobs = pd.DataFrame(load_jobs_from_db())
    st.session_state.db_synced = True

# --- UI ---
st.markdown('<div class="main-header">🏭 Appointed Time Printing - Elite Planner</div>', unsafe_allow_html=True)
t1, t2, t3 = st.tabs(["📊 Dashboard", "📝 Plan Job", "📋 Production Timeline"])

with t1:
    if not st.session_state.jobs.empty:
        df = st.session_state.jobs.copy()
        c1, c2, c3 = st.columns(3)
        c1.metric("Projected Revenue", f"{CURRENCY}{df['contract_value'].sum():,.2f}")
        c2.metric("Workflow Operations", len(df))
        c3.metric("Machine Assets", f"{df['machine'].nunique()} Utilized")
        st.divider()
        unique_jobs = df['job_name'].unique()
        selected_job = st.selectbox("Quick Manage: Select Job", unique_jobs)
        col_edit, col_del = st.columns(2)
        with col_edit:
            with st.expander(f"Edit Value: {selected_job}"):
                new_val = st.number_input("Update Value", value=float(df[df['job_name'] == selected_job]['contract_value'].sum()))
                if st.button("Apply Updates"):
                    if update_job_value(selected_job, new_val):
                        st.session_state.db_synced = False
                        st.rerun()
        with col_del:
            with st.expander(f"Delete: {selected_job}"):
                if st.button("Permanently Delete", type="primary"):
                    if delete_job(selected_job):
                        st.session_state.db_synced = False
                        st.rerun()
    else: st.info("Planner database empty.")

with t2:
    st.header("Simulate New Workflow")
    with st.form("job_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        name = c1.text_input("Client/Job Name")
        rep = c2.selectbox("Sales Executive", ["Mabel Ampofo", "Daphne Sarpong", "Reginald Aidam", "Elizabeth Akoto", "Charles Adoo", "Mohammed Seidu Bunyamin", "Christian Mante", "Bertha Tackie"])
        q, u, v = st.columns(3)
        qty = q.number_input("Target Quantity", value=10000)
        ups = u.number_input("Ups per Sheet", value=1)
        val = v.number_input("Total Contract Value", value=1000.0)
        procs = st.multiselect("Machine Routing", list(MACHINE_DATA.keys()))
        night = st.toggle("🌙 Enable 24-Hour Production")
        if st.form_submit_button("Commit to Schedule"):
            if name and procs:
                if add_job(name, rep, qty, ups, math.ceil(qty/ups), procs, val, night):
                    st.session_state.db_synced = False
                    st.rerun()

with t3:
    st.header("Production Visualizer")
    if not st.session_state.jobs.empty:
        df_viz = st.session_state.jobs.copy()
        df_viz['start_time'] = pd.to_datetime(df_viz['start_time'])
        df_viz['finish_time'] = pd.to_datetime(df_viz['finish_time'])
        
        # Enhanced Plotly Gantt
        fig = px.timeline(
            df_viz, x_start="start_time", x_end="finish_time", y="machine", color="job_name",
            text="job_name", opacity=0.85, color_discrete_sequence=px.colors.qualitative.Prism,
            template="plotly_white", hover_data=["sales_rep", "quantity"]
        )
        fig.update_yaxes(autorange="reversed", title_text="", tickfont=dict(size=12, color="#1e3a8a", family="Arial Black"))
        fig.update_layout(height=500, xaxis_title="Simulation Timeline (Working Hours: 8 AM - 5 PM)", 
                          showlegend=False, font=dict(family="Arial", size=11))
        st.plotly_chart(fig, use_container_width=True)
        
        # Tabulated Collection Schedule
        st.subheader("📅 Collection Schedule (Tabulated)")
        table_df = df_viz[['job_name', 'machine', 'sales_rep', 'finish_time']].copy()
        table_df['Date'] = table_df['finish_time'].dt.strftime('%A, %b %d')
        table_df['Time'] = table_df['finish_time'].dt.strftime('%I:%M %p')
        table_df = table_df.sort_values('finish_time').rename(columns={
            'job_name': 'Job Name', 'machine': 'Final Machine Step', 'sales_rep': 'Rep'
        })
        
        st.dataframe(
            table_df[['Date', 'Time', 'Job Name', 'Final Machine Step', 'Rep']],
            use_container_width=True,
            hide_index=True
        )