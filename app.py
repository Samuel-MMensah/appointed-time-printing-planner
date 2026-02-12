import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import math
from supabase import create_client, Client

# Page configuration
st.set_page_config(page_title="Appointed Time - Elite Planner", layout="wide")

# Custom CSS for a better look
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 1.8rem; font-weight: bold; }
    .status-card { background-color: #f8fafc; border-radius: 10px; padding: 20px; border: 1px solid #e2e8f0; }
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

# Session State Handling
if 'jobs' not in st.session_state:
    st.session_state.jobs = pd.DataFrame()
if 'db_synced' not in st.session_state:
    st.session_state.db_synced = False

# --- Helper Logic ---

def format_human_time(dt_obj):
    """Simplifies technical timestamps for non-technical users."""
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
    except Exception as e:
        return []

def add_job(name, sales_rep, finished_qty, ups, impressions, processes, total_value, night_shift=False):
    current_time = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)
    rev_per_step = total_value / len(processes)
    
    for proc in processes:
        # Machine Queuing
        if not st.session_state.jobs.empty:
            m_jobs = st.session_state.jobs[st.session_state.jobs['machine'] == proc]
            if not m_jobs.empty:
                last_f = pd.to_datetime(m_jobs['finish_time']).max().tz_localize(None)
                if last_f > current_time:
                    current_time = last_f

        # Process logic
        duration = SETUP_HOURS + (impressions / MACHINE_DATA[proc]['rate'])
        if "DIE CUTTER" in proc: current_time += timedelta(hours=8)
        if "FOLDER GLUER" in proc: current_time += timedelta(hours=2)

        # Shift Logic (08:00 - 17:00)
        if not night_shift:
            if current_time.hour >= 17:
                current_time = (current_time + timedelta(days=1)).replace(hour=8, minute=0)
            elif current_time.hour < 8:
                current_time = current_time.replace(hour=8, minute=0)
            
        finish_time = current_time + timedelta(hours=duration)
        
        # Split across days if needed
        if not night_shift and (finish_time.hour >= 17 or finish_time.date() > current_time.date()):
            overtime = (finish_time - current_time.replace(hour=17, minute=0)).total_seconds() / 3600
            finish_time = (current_time + timedelta(days=1)).replace(hour=8, minute=0) + timedelta(hours=max(0, overtime))

        supabase.table('jobs').insert({
            "job_name": name, "sales_rep": sales_rep, "quantity": finished_qty,
            "ups": ups, "impressions": impressions, "contract_value": float(rev_per_step),
            "machine": proc, "start_time": current_time.isoformat(),
            "finish_time": finish_time.isoformat()
        }).execute()
        current_time = finish_time 
    return True

if not st.session_state.db_synced:
    st.session_state.jobs = pd.DataFrame(load_jobs_from_db())
    st.session_state.db_synced = True

# --- UI Layout ---
st.title("🏭 Appointed Time Printing - Elite Planner")

t1, t2, t3 = st.tabs(["📊 Dashboard", "📝 Plan Job", "📋 Production Control"])

with t1:
    if not st.session_state.jobs.empty:
        df = st.session_state.jobs.copy()
        df['finish_dt'] = pd.to_datetime(df['finish_time'])
        total_rev = df['contract_value'].sum()
        target = 150000.00
        
        # Dashboard Metrics (Stoplight System)
        m1, m2, m3 = st.columns(3)
        m1.metric("Projected Revenue", f"{CURRENCY}{total_rev:,.2f}", f"{(total_rev/target)*100:.1f}% of target")
        m2.metric("Annual Target", f"{CURRENCY}{target:,.2f}")
        gap_color = "normal" if total_rev >= target else "inverse"
        m3.metric("Revenue Gap", f"{CURRENCY}{max(0, target-total_rev):,.2f}", delta_color=gap_color)
        
        st.divider()
        st.subheader("Current Machine Load")
        
        # Clean Table for Non-Technical Users
        display_df = df.sort_values('finish_dt', ascending=True).tail(10).copy()
        display_df['Completion Status'] = display_df['finish_dt'].apply(format_human_time)
        
        st.table(display_df[['job_name', 'machine', 'Completion Status']])
    else:
        st.info("The production floor is currently clear. Add a job to get started!")

with t2:
    st.header("New Job Entry")
    with st.form("job_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        name = c1.text_input("Job Name (e.g., Nutrifoods)")
        rep = c2.selectbox("Sales Rep", ["Mabel Ampofo", "Daphne Sarpong", "Reginald Aidam", "Elizabeth Akoto", "Charles Adoo", "Mohammed Seidu Bunyamin", "Christian Mante", "Bertha Tackie"])
        
        q, u, o = st.columns(3)
        qty = q.number_input("Finished Quantity", value=100000)
        ups = u.number_input("Ups per Sheet", value=12)
        overs = o.slider("Overs % (Buffer)", 0, 10, 2)
        
        val = st.number_input("Total Contract Value", value=5000.0)
        procs = st.multiselect("Production Steps", list(MACHINE_DATA.keys()))
        night = st.toggle("🌙 Run Night Shift for this job")
        
        if st.form_submit_button("Confirm & Schedule Job"):
            if add_job(name, rep, qty, ups, calculate_impressions(qty, ups, overs), procs, val, night):
                st.success("Job added to production schedule!")
                st.session_state.db_synced = False
                st.rerun()

with t3:
    st.header("📋 Production Control")
    if not st.session_state.jobs.empty:
        df_control = st.session_state.jobs.copy()
        df_control['finish_dt'] = pd.to_datetime(df_control['finish_time'])
        
        for date, group in df_control.sort_values('finish_dt').groupby(df_control['finish_dt'].dt.date):
            st.subheader(f"🗓️ {date.strftime('%A, %b %d')}")
            for _, job in group.iterrows():
                # Visual block style
                st.markdown(f"""
                    <div style="background-color: white; padding: 15px; border-radius: 8px; border-left: 10px solid #22c55e; box-shadow: 0 2px 4px rgba(0,0,0,0.05); margin-bottom: 10px;">
                        <div style="display: flex; justify-content: space-between;">
                            <span style="font-weight: bold; font-size: 1.1em;">{job['job_name']}</span>
                            <span style="color: #64748b;">Ready: {format_human_time(job['finish_dt'])}</span>
                        </div>
                        <div style="margin-top: 5px; color: #475569;">
                            <b>Step:</b> {job['machine']} | <b>Rep:</b> {job['sales_rep']}
                        </div>
                    </div>
                """, unsafe_allow_html=True)