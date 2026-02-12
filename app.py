import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time
import math
from supabase import create_client, Client
import plotly.express as px

# Page configuration
st.set_page_config(page_title="Appointed Time - Elite Planner", layout="wide")

# Custom CSS
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 1.6rem; font-weight: bold; }
    .stTabs [data-baseweb="tab"] { height: 50px; background-color: #f1f5f9; border-radius: 5px; }
    .stTabs [aria-selected="true"] { background-color: #1e3a8a !important; color: white !important; }
    .status-card { background-color: white; padding: 15px; border-radius: 8px; border-left: 5px solid #1e3a8a; box-shadow: 2px 2px 5px rgba(0,0,0,0.05); margin-bottom: 10px; }
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
    """Loads all jobs from Supabase."""
    if not supabase: return []
    try:
        res = supabase.table('jobs').select("*").execute()
        return res.data
    except Exception as e:
        st.error(f"DB Load Error: {e}")
        return []

def delete_job(job_name):
    """Deletes all machine steps associated with a specific job name."""
    try:
        supabase.table('jobs').delete().eq('job_name', job_name).execute()
        return True
    except Exception as e:
        st.error(f"Error deleting job: {e}")
        return False

def update_job_value(job_name, new_value):
    """Updates the contract value for an existing job."""
    try:
        res = supabase.table('jobs').select("id").eq('job_name', job_name).execute()
        steps = res.data
        if steps:
            val_per_step = new_value / len(steps)
            for step in steps:
                supabase.table('jobs').update({"contract_value": val_per_step}).eq('id', step['id']).execute()
        return True
    except Exception as e:
        st.error(f"Error updating job: {e}")
        return False

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

# --- State Management ---
if 'jobs' not in st.session_state:
    st.session_state.jobs = pd.DataFrame()
if 'db_synced' not in st.session_state:
    st.session_state.db_synced = False

if not st.session_state.db_synced:
    data = load_jobs_from_db()
    st.session_state.jobs = pd.DataFrame(data)
    st.session_state.db_synced = True

# --- UI Layout ---
st.title("🏭 Appointed Time Printing - Elite Planner")

t1, t2, t3 = st.tabs(["📊 Dashboard", "📝 Plan Job", "📋 Production Timeline"])

with t1:
    if not st.session_state.jobs.empty:
        df = st.session_state.jobs.copy()
        df['finish_dt'] = pd.to_datetime(df['finish_time'])
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Projected Revenue", f"{CURRENCY}{df['contract_value'].sum():,.2f}")
        c2.metric("Total Steps", len(df))
        c3.metric("Machine Utilization", f"{df['machine'].nunique()} Active")

        st.divider()
        st.subheader("🛠️ Manage Existing Jobs")
        unique_jobs = df['job_name'].unique()
        selected_job = st.selectbox("Select a job to Edit or Delete", unique_jobs)
        
        col_edit, col_del = st.columns(2)
        with col_edit:
            with st.expander(f"Edit Value for {selected_job}"):
                cur_val = df[df['job_name'] == selected_job]['contract_value'].sum()
                new_val = st.number_input("Update Total Contract Value", value=float(cur_val))
                if st.button("Save Changes"):
                    if update_job_value(selected_job, new_val):
                        st.success("Updated!")
                        st.session_state.db_synced = False
                        st.rerun()
        with col_del:
            with st.expander(f"⚠️ Delete {selected_job}"):
                if st.button(f"Confirm Delete {selected_job}", type="primary"):
                    if delete_job(selected_job):
                        st.session_state.db_synced = False
                        st.rerun()
    else:
        st.info("Floor is clear. Start by planning a job.")

with t2:
    st.header("New Job Entry Simulation")
    with st.form("job_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        name = col1.text_input("Job Name")
        rep = col2.selectbox("Sales Rep", ["Mabel Ampofo", "Daphne Sarpong", "Reginald Aidam", "Elizabeth Akoto", "Charles Adoo", "Mohammed Seidu Bunyamin", "Christian Mante", "Bertha Tackie"])
        
        q, u, v = st.columns(3)
        qty = q.number_input("Finished Quantity", value=10000)
        ups = u.number_input("Ups", value=1)
        val = v.number_input("Total Contract Value", value=1000.0)
        
        procs = st.multiselect("Workflow Steps", list(MACHINE_DATA.keys()))
        night = st.toggle("🌙 Continuous Night Shift (24h)")
        
        if st.form_submit_button("Confirm & Schedule Job"):
            if name and procs:
                if add_job(name, rep, qty, ups, math.ceil(qty/ups), procs, val, night):
                    st.session_state.db_synced = False
                    st.rerun()
            else:
                st.error("Missing Job Name or Production Steps")

with t3:
    st.header("📋 Interactive Production Simulation")
    if not st.session_state.jobs.empty:
        df_viz = st.session_state.jobs.copy()
        df_viz['start_time'] = pd.to_datetime(df_viz['start_time'])
        df_viz['finish_time'] = pd.to_datetime(df_viz['finish_time'])

        fig = px.timeline(
            df_viz, 
            x_start="start_time", 
            x_end="finish_time", 
            y="machine", 
            color="job_name",
            text="job_name",
            hover_data=["sales_rep", "quantity"],
            template="plotly_white"
        )
        fig.update_yaxes(autorange="reversed")
        fig.update_layout(height=600, xaxis_title="Simulation Timeline (Paused 5 PM - 8 AM)")
        st.plotly_chart(fig, use_container_width=True)
        
        st.divider()
        st.subheader("Collection Schedule")
        for date, group in df_viz.sort_values('finish_time').groupby(df_viz['finish_time'].dt.date):
            st.write(f"#### 🗓️ {date.strftime('%A, %b %d')}")
            for _, job in group.iterrows():
                st.markdown(f"""
                <div class="status-card">
                    <b>{job['job_name']}</b> | Rep: {job['sales_rep']} <br>
                    <small>Step: {job['machine']} — <b>Ready: {pd.to_datetime(job['finish_time']).strftime('%I:%M %p')}</b></small>
                </div>
                """, unsafe_allow_html=True)