import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import math
from supabase import create_client, Client

# Page configuration
st.set_page_config(page_title="Appointed Time - Elite Planner", layout="wide")

# Custom UI Styling
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 1.8rem; font-weight: bold; }
    .status-card { background-color: #ffffff; border-radius: 10px; padding: 20px; border: 1px solid #e2e8f0; }
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

if 'jobs' not in st.session_state:
    st.session_state.jobs = pd.DataFrame()
if 'db_synced' not in st.session_state:
    st.session_state.db_synced = False

# --- Helper Logic ---

def format_human_time(dt_obj):
    """Simplifies timestamps for non-technical users."""
    now = datetime.now()
    if dt_obj.date() == now.date():
        return f"Today at {dt_obj.strftime('%I:%M %p')}"
    elif dt_obj.date() == (now + timedelta(days=1)).date():
        return f"Tomorrow at {dt_obj.strftime('%I:%M %p')}"
    else:
        return dt_obj.strftime('%a, %b %d at %I:%M %p')

def delete_job(job_name):
    """CRUD: Delete job from database."""
    try:
        supabase.table('jobs').delete().eq('job_name', job_name).execute()
        return True
    except:
        return False

def add_job(name, sales_rep, finished_qty, ups, impressions, processes, total_value, night_shift=False):
    current_time = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)
    rev_per_step = total_value / len(processes)
    
    for proc in processes:
        # Machine Queuing Logic
        if not st.session_state.jobs.empty:
            m_jobs = st.session_state.jobs[st.session_state.jobs['machine'] == proc]
            if not m_jobs.empty:
                last_f = pd.to_datetime(m_jobs['finish_time']).max().tz_localize(None)
                if last_f > current_time:
                    current_time = last_f

        duration = SETUP_HOURS + (impressions / MACHINE_DATA[proc]['rate'])
        
        # Staging rules
        if "DIE CUTTER" in proc: current_time += timedelta(hours=8)
        if "FOLDER GLUER" in proc: current_time += timedelta(hours=2)

        # Shift Logic (8am-5pm)
        if not night_shift:
            if current_time.hour >= 17:
                current_time = (current_time + timedelta(days=1)).replace(hour=8, minute=0)
            elif current_time.hour < 8:
                current_time = current_time.replace(hour=8, minute=0)
            
        finish_time = current_time + timedelta(hours=duration)
        
        # Split work if it crosses closing time
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

# Sync data from Supabase
if not st.session_state.db_synced:
    res = supabase.table('jobs').select("*").execute()
    st.session_state.jobs = pd.DataFrame(res.data)
    st.session_state.db_synced = True

# --- UI Layout ---

st.title("🏭 Appointed Time Printing - Elite Planner")

tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "📝 Plan Job", "📋 Production Control"])

with tab1:
    if not st.session_state.jobs.empty:
        df = st.session_state.jobs.copy()
        df['finish_dt'] = pd.to_datetime(df['finish_time'])
        total_rev = df['contract_value'].sum()
        target = 150000.00
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Revenue Achieved", f"{CURRENCY}{total_rev:,.2f}", f"{(total_rev/target)*100:.1f}%")
        m2.metric("Annual Target", f"{CURRENCY}{target:,.2f}")
        m3.metric("Gap", f"{CURRENCY}{max(0, target-total_rev):,.2f}", delta_color="inverse")
        
        st.divider()
        
        # Split view for better scannability
        left_col, right_col = st.columns([2, 1])
        
        with left_col:
            st.subheader("Current Job Queue")
            df_display = df.sort_values('finish_dt').copy()
            df_display['Ready For Next Step'] = df_display['finish_dt'].apply(format_human_time)
            # UPDATED: width='stretch' replaces use_container_width
            st.dataframe(df_display[['job_name', 'machine', 'Ready For Next Step']], width='stretch')
            
        with right_col:
            st.subheader("🛠️ Management")
            job_list = df['job_name'].unique()
            job_to_manage = st.selectbox("Select Job", job_list)
            
            if st.button(f"🗑️ Delete Entire Job: {job_to_manage}", type="primary"):
                if delete_job(job_to_manage):
                    st.success(f"{job_to_manage} removed.")
                    st.session_state.db_synced = False
                    st.rerun()
    else:
        st.info("The production floor is clear. Use 'Plan Job' to start.")

with tab2:
    st.header("New Job Entry")
    with st.form("job_form"):
        c1, c2 = st.columns(2)
        name = c1.text_input("Job Name")
        rep = c2.selectbox("Sales Rep", ["John Smith", "Sarah Johnson", "Mike Davis"])
        
        q, u, v = st.columns(3)
        qty = q.number_input("Finished Qty", value=5000)
        ups = u.number_input("Ups", value=1)
        val = v.number_input("Total Contract Value", value=1000.0)
        
        procs = st.multiselect("Production Steps", list(MACHINE_DATA.keys()))
        night = st.toggle("🌙 Enable Night Shift (Work past 5pm)")
        
        if st.form_submit_button("Confirm Schedule"):
            if add_job(name, rep, qty, ups, qty/ups, procs, val, night):
                st.session_state.db_synced = False
                st.rerun()

with tab3:
    st.header("📋 Production Control")
    if not st.session_state.jobs.empty:
        df_c = st.session_state.jobs.copy()
        df_c['finish_dt'] = pd.to_datetime(df_c['finish_time'])
        
        for date, group in df_c.sort_values('finish_dt').groupby(df_c['finish_dt'].dt.date):
            st.subheader(f"📅 {date.strftime('%A, %b %d')}")
            for _, job in group.iterrows():
                st.markdown(f"""
                    <div style="background-color: white; padding: 12px; border-radius: 8px; border-left: 10px solid #22c55e; margin-bottom: 8px; box-shadow: 2px 2px 5px rgba(0,0,0,0.05);">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div>
                                <b>{job['job_name']}</b><br>
                                <span style="font-size: 0.9em; color: #64748b;">Machine: {job['machine']}</span>
                            </div>
                            <div style="text-align: right;">
                                <span style="color: #1e293b; font-weight: 500;">{format_human_time(job['finish_dt'])}</span>
                            </div>
                        </div>
                    </div>
                """, unsafe_allow_html=True)