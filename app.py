import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import math
from supabase import create_client, Client

# Page configuration
st.set_page_config(
    page_title="Appointed Time Printing - Job Planning",
    layout="wide",
    initial_sidebar_state="expanded"
)

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
        url = st.secrets.get("SUPABASE_URL")
        key = st.secrets.get("SUPABASE_KEY")
        if not url or not key:
            st.warning("⚠️ Supabase credentials not found. Using session state only.")
            return None
        return create_client(url, key)
    except Exception as e:
        st.warning(f"⚠️ Supabase connection issue: {e}")
        return None

supabase: Client = init_supabase()

# Initialize session state
if 'jobs' not in st.session_state:
    st.session_state.jobs = []
if 'sales_reps' not in st.session_state:
    st.session_state.sales_reps = set()
if 'monthly_budget' not in st.session_state:
    st.session_state.monthly_budget = 100000
if 'machine_load' not in st.session_state:
    st.session_state.machine_load = {machine: [] for machine in MACHINE_DATA.keys()}
if 'db_synced' not in st.session_state:
    st.session_state.db_synced = False

# Helper functions
def calculate_impressions(finished_qty, ups, overs_pct):
    sheets = math.ceil(finished_qty / ups)
    impressions = sheets * (1 + overs_pct / 100)
    return int(impressions)

def calculate_processing_time(machine, impressions):
    rate = MACHINE_DATA[machine]['rate']
    return SETUP_HOURS + (impressions / rate)

def calculate_job_schedule(job_name, impressions, processes, start_time=None):
    schedule = []
    current_time = start_time or datetime.now().replace(minute=0, second=0, microsecond=0)
    for process in processes:
        duration = calculate_processing_time(process, impressions)
        end_time = current_time + timedelta(hours=duration)
        schedule.append({
            'process': process, 'start': current_time, 'end': end_time,
            'duration': duration, 'impressions': impressions,
            'run_time': (impressions / MACHINE_DATA[process]['rate']),
            'setup_time': SETUP_HOURS
        })
        current_time = end_time
    return schedule

def delete_job_from_db(job_name):
    if not supabase: return False
    try:
        supabase.table('jobs').delete().eq('name', job_name).execute()
        return True
    except Exception as e:
        st.error(f"Error deleting: {e}")
        return False

def save_job_to_db(job_data):
    if not supabase: return False
    try:
        supabase.table('jobs').insert(job_data).execute()
        return True
    except Exception as e:
        st.error(f"Error saving: {e}")
        return False

def load_jobs_from_db():
    if not supabase: return []
    try:
        response = supabase.table('jobs').select('*').execute()
        jobs = []
        for record in response.data:
            schedule = []
            if 'schedule' in record and record['schedule']:
                for task in record['schedule']:
                    schedule.append({
                        'process': task['process'],
                        'start': datetime.fromisoformat(task['start']),
                        'end': datetime.fromisoformat(task['end']),
                        'duration': task['duration'],
                        'impressions': task['impressions'],
                        'run_time': task.get('run_time', 0),
                        'setup_time': task.get('setup_time', 0)
                    })
            jobs.append({
                'id': record.get('id'), 'name': record['name'], 'sales_rep': record['sales_rep'],
                'impressions': record['impressions'], 'processes': record.get('processes', []),
                'contract_value': record.get('contract_value', 0), 'schedule': schedule,
                'target_deadline': datetime.fromisoformat(record['target_deadline']) if record.get('target_deadline') else None,
                'created_at': datetime.fromisoformat(record['created_at']),
                'efficiency': sum(t.get('run_time', 0) for t in schedule) / sum(t['duration'] for t in schedule) * 100 if schedule else 0
            })
            st.session_state.sales_reps.add(record['sales_rep'])
        return jobs
    except Exception as e:
        st.warning(f"Error loading: {e}")
        return []

# Initial Load
if not st.session_state.db_synced and supabase:
    st.session_state.jobs = load_jobs_from_db()
    st.session_state.db_synced = True
    st.session_state.machine_load = {m: [] for m in MACHINE_DATA.keys()}
    for job in st.session_state.jobs:
        for task in job['schedule']:
            st.session_state.machine_load[task['process']].append({'job': job['name'], 'duration': task['duration']})

# Sidebar
st.sidebar.markdown("### ⚙️ Configuration")
sales_rep_list = sorted(list(st.session_state.sales_reps)) if st.session_state.sales_reps else []
selected_rep = st.sidebar.selectbox("Filter by Sales Rep", ["All"] + sales_rep_list)
st.session_state.monthly_budget = st.sidebar.number_input(f"Budget Target ({CURRENCY})", value=st.session_state.monthly_budget)

tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "📝 Plan Job", "📈 Gantt View"])

# --- TAB 1: DASHBOARD ---
with tab1:
    f_jobs = [j for j in st.session_state.jobs if selected_rep == "All" or j['sales_rep'] == selected_rep]
    total_rev = sum(j['contract_value'] for j in f_jobs)
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Projected Revenue", f"{CURRENCY}{total_rev:,.0f}")
    col2.metric("Budgeted Target", f"{CURRENCY}{st.session_state.monthly_budget:,.0f}")
    col3.metric("Gap", f"{CURRENCY}{max(0, st.session_state.monthly_budget - total_rev):,.0f}")

    st.subheader("Machine Status")
    stoplight = []
    for m in sorted(MACHINE_DATA.keys()):
        load = sum(task['duration'] for task in st.session_state.machine_load.get(m, []))
        status = "🟢 Available" if load == 0 else "🔴 Heavy" if load > 5 else "🟡 Active"
        stoplight.append({'Machine': m, 'Status': status, 'Load (hrs)': f"{load:.1f}"})
    
    st.dataframe(pd.DataFrame(stoplight), width="stretch", hide_index=True)

    if f_jobs:
        st.subheader("Production Summary")
        summary = pd.DataFrame([{
            'Job Name': j['name'], 'Sales Rep': j['sales_rep'], 
            'Finish': j['schedule'][-1]['end'].strftime('%Y-%m-%d %H:%M'),
            'Revenue': f"{j['contract_value']:,.0f}"
        } for j in f_jobs])
        st.dataframe(summary, width="stretch", hide_index=True)

        with st.expander("⚙️ Management Actions"):
            job_to_del = st.selectbox("Select job to remove", [j['name'] for j in f_jobs])
            if st.button("🗑️ Delete Selected Job", type="primary"):
                if delete_job_from_db(job_to_del):
                    st.session_state.db_synced = False
                    st.rerun()

# --- TAB 2: PLAN JOB ---
with tab2:
    with st.form("job_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        j_name = c1.text_input("Job Name")
        s_rep = c2.selectbox("Sales Rep", ["John Smith", "Sarah Johnson", "Mike Davis", "Other"])
        
        c1, c2, c3 = st.columns(3)
        f_qty = c1.number_input("Finished Qty", value=10000)
        u_sheet = c2.number_input("Ups", value=1)
        c_val = c3.number_input("Contract Value", value=500.0)
        
        selected_procs = [m for m in sorted(MACHINE_DATA.keys()) if st.checkbox(m)]
        
        if st.form_submit_button("✅ Create Job", width="stretch"):
            if j_name and selected_procs:
                imps = calculate_impressions(f_qty, u_sheet, 5.0)
                sched = calculate_job_schedule(j_name, imps, selected_procs)
                db_data = {
                    'name': j_name, 'sales_rep': s_rep, 'impressions': imps,
                    'contract_value': float(c_val), 'processes': selected_procs,
                    'created_at': datetime.now().isoformat(),
                    'schedule': [{'process': t['process'], 'start': t['start'].isoformat(), 'end': t['end'].isoformat(), 'duration': t['duration'], 'impressions': t['impressions'], 'run_time': t['run_time'], 'setup_time': t['setup_time']} for t in sched]
                }
                if save_job_to_db(db_data):
                    st.session_state.db_synced = False
                    st.rerun()

# --- TAB 3: GANTT VIEW ---
with tab3:
    if f_jobs:
        sel_j = st.selectbox("View Timeline for:", [j['name'] for j in f_jobs])
        job = next(j for j in f_jobs if j['name'] == sel_j)
        
        fig = go.Figure()
        for t in job['schedule']:
            fig.add_trace(go.Bar(
                x=[t['duration']], y=[t['process']], orientation='h',
                base=t['start'], name=t['process'],
                text=f"{t['duration']:.1f}h", textposition='inside'
            ))
        fig.update_layout(height=400, width=1000, title=f"Timeline: {sel_j}", xaxis_type='date')
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("No jobs to display.")