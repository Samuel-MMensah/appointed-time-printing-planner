import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time
import math
from supabase import create_client, Client
import plotly.express as px

# Page configuration
st.set_page_config(page_title="Appointed Time - Elite Planner", layout="wide")

# Custom CSS for a professional look
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 1.8rem; font-weight: bold; }
    .stTabs [data-baseweb="tab-list"] { gap: 24px; }
    .stTabs [data-baseweb="tab"] { height: 50px; white-space: pre-wrap; background-color: #f1f5f9; border-radius: 5px; padding: 10px; }
    .stTabs [aria-selected="true"] { background-color: #1e3a8a !important; color: white !important; }
    </style>
    """, unsafe_allow_html=True)

# Machine data constants
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

if 'jobs' not in st.session_state:
    st.session_state.jobs = pd.DataFrame()
if 'db_synced' not in st.session_state:
    st.session_state.db_synced = False

# --- Shift & Time Simulation Logic ---

def get_next_working_time(start_dt, night_shift):
    """Ensures start time respects the 8 AM - 5 PM shift."""
    if night_shift:
        return start_dt
    
    if start_dt.hour >= 17:
        start_dt = (start_dt + timedelta(days=1)).replace(hour=8, minute=0, second=0)
    elif start_dt.hour < 8:
        start_dt = start_dt.replace(hour=8, minute=0, second=0)
    return start_dt

def calculate_finish_with_shifts(start_dt, total_hours, night_shift):
    """Simulates job progress, pausing at 5 PM daily."""
    if night_shift:
        return start_dt + timedelta(hours=total_hours)

    current_time = start_dt
    remaining_hours = total_hours

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

def format_human_time(dt_obj):
    now = datetime.now()
    if dt_obj.date() == now.date():
        return f"Today at {dt_obj.strftime('%I:%M %p')}"
    elif dt_obj.date() == (now + timedelta(days=1)).date():
        return f"Tomorrow at {dt_obj.strftime('%I:%M %p')}"
    else:
        return dt_obj.strftime('%a, %b %d at %I:%M %p')

def calculate_impressions(finished_qty, ups, overs_pct):
    sheets = math.ceil(finished_qty / ups)
    return int(sheets * (1 + overs_pct / 100))

def load_jobs_from_db():
    if not supabase: return []
    try:
        res = supabase.table('jobs').select("*").execute()
        return res.data
    except Exception:
        return []

def add_job(name, sales_rep, finished_qty, ups, impressions, processes, total_value, night_shift=False):
    current_time = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)
    rev_per_step = total_value / len(processes) if processes else 0
    
    for proc in processes:
        if not st.session_state.jobs.empty:
            m_jobs = st.session_state.jobs[st.session_state.jobs['machine'] == proc]
            if not m_jobs.empty:
                last_f = pd.to_datetime(m_jobs['finish_time']).max().tz_localize(None)
                if last_f > current_time:
                    current_time = last_f

        duration = SETUP_HOURS + (impressions / MACHINE_DATA[proc]['rate'])
        if "DIE CUTTER" in proc: current_time += timedelta(hours=8)
        if "FOLDER GLUER" in proc: current_time += timedelta(hours=2)

        start_time = get_next_working_time(current_time, night_shift)
        finish_time = calculate_finish_with_shifts(start_time, duration, night_shift)

        supabase.table('jobs').insert({
            "job_name": name, "sales_rep": sales_rep, "quantity": finished_qty,
            "ups": ups, "impressions": impressions, "contract_value": float(rev_per_step),
            "machine": proc, "start_time": start_time.isoformat(),
            "finish_time": finish_time.isoformat()
        }).execute()
        
        current_time = finish_time 
    return True

# Data Synchronization
if not st.session_state.db_synced:
    st.session_state.jobs = pd.DataFrame(load_jobs_from_db())
    st.session_state.db_synced = True

# --- UI Layout ---
st.title("🏭 Appointed Time Printing - Elite Planner")

t1, t2, t3 = st.tabs(["📊 Revenue Dashboard", "📝 Schedule Simulation", "📋 Visual Production Control"])

with t1:
    if not st.session_state.jobs.empty:
        df = st.session_state.jobs.copy()
        df['finish_dt'] = pd.to_datetime(df['finish_time'])
        total_rev = df['contract_value'].sum()
        target = 150000.00
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Projected Revenue", f"{CURRENCY}{total_rev:,.2f}")
        m2.metric("Annual Target", f"{CURRENCY}{target:,.2f}")
        m3.metric("Revenue Gap", f"{CURRENCY}{max(0, target-total_rev):,.2f}")
        
        st.divider()
        st.subheader("Current Machine Load Summary")
        display_df = df.sort_values('finish_dt', ascending=True).copy()
        display_df['finish_time'] = display_df['finish_dt'].dt.strftime('%Y-%m-%d %H:%M')
        st.dataframe(display_df[['machine', 'job_name', 'finish_time']], use_container_width=True)
    else:
        st.info("Floor clear. Add a job to see revenue projections.")

with t2:
    st.header("Schedule a New Job Simulation")
    st.info("Entering a job here will simulate its path through the factory, accounting for existing backlogs and 5 PM closures.")
    with st.form("job_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        name = c1.text_input("Job Name (Client/Project)")
        rep = c2.selectbox("Assigned Sales Rep", ["Mabel Ampofo", "Daphne Sarpong", "Reginald Aidam", "Elizabeth Akoto", "Charles Adoo", "Mohammed Seidu Bunyamin", "Christian Mante", "Bertha Tackie"])
        
        q, u, o = st.columns(3)
        qty = q.number_input("Finished Quantity", value=100000)
        ups = u.number_input("Ups per Sheet", value=12)
        overs = o.slider("Overs % (Buffer)", 0, 10, 2)
        
        val = st.number_input("Total Contract Value (GH₵)", value=5000.0)
        procs = st.multiselect("Production Workflow", list(MACHINE_DATA.keys()))
        night = st.toggle("🌙 Run as 24h Night Shift (No 5 PM Pause)")
        
        if st.form_submit_button("Confirm & Simulate Schedule"):
            if not procs or not name:
                st.error("Please provide a job name and at least one production step.")
            else:
                if add_job(name, rep, qty, ups, calculate_impressions(qty, ups, overs), procs, val, night):
                    st.success(f"Job '{name}' successfully simulated and added to the timeline!")
                    st.session_state.db_synced = False
                    st.rerun()

with t3:
    st.header("📋 Interactive Production Timeline")
    if not st.session_state.jobs.empty:
        df_viz = st.session_state.jobs.copy()
        df_viz['start_time'] = pd.to_datetime(df_viz['start_time'])
        df_viz['finish_time'] = pd.to_datetime(df_viz['finish_time'])

        # Visual Gantt Chart Simulation
        fig = px.timeline(
            df_viz, 
            start="start_time", 
            end="finish_time", 
            y="machine", 
            color="job_name",
            text="job_name",
            hover_data={"sales_rep": True, "quantity": True, "start_time": "|%b %d, %H:%M", "finish_time": "|%b %d, %H:%M"},
            labels={"machine": "Production Line", "job_name": "Job Name"},
            template="plotly_white"
        )
        
        fig.update_yaxes(autorange="reversed")
        fig.update_layout(
            xaxis_title="Timeline (Simulation includes 5 PM Pauses)",
            height=500,
            showlegend=True,
            font=dict(size=12)
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        st.divider()
        st.subheader("Daily Ready-for-Collection List")
        for date, group in df_viz.sort_values('finish_time').groupby(df_viz['finish_time'].dt.date):
            st.write(f"### 🗓️ {date.strftime('%A, %b %d')}")
            for _, job in group.iterrows():
                st.markdown(f"""
                    <div style="background-color: #1e3a8a; color: white; padding: 15px; border-radius: 8px; margin-bottom: 10px; border-left: 8px solid #22c55e;">
                        <div style="display: flex; justify-content: space-between;">
                            <span style="font-weight: bold; font-size: 1.1em;">{job['job_name']}</span>
                            <span>Ready: {format_human_time(job['finish_time'])}</span>
                        </div>
                        <div style="margin-top: 5px; opacity: 0.9; font-size: 0.9em;">
                            <b>Current Line:</b> {job['machine']} | <b>Sales Rep:</b> {job['sales_rep']} | <b>Qty:</b> {job['quantity']:,}
                        </div>
                    </div>
                """, unsafe_allow_html=True)
    else:
        st.info("No active jobs in the simulation. Use the 'Schedule Simulation' tab to add one.")