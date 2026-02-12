import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
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
    # Standardize current time to UTC for DB compatibility
    current_time = datetime.now(timezone.utc).replace(hour=8, minute=0, second=0, microsecond=0)
    rev_per_step = total_value / len(processes) if processes else 0
    for proc in processes:
        if not st.session_state.jobs.empty:
            m_jobs = st.session_state.jobs[st.session_state.jobs['machine'] == proc]
            if not m_jobs.empty:
                last_f = pd.to_datetime(m_jobs['finish_time']).max()
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
t1, t2, t3 = st.tabs(["📊 Dashboard", "📝 Plan Job", "📋 Production Control"])

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
    st.markdown("### 📋 Production Control Center")
    if not st.session_state.jobs.empty:
        # 1. Search and Filter Bar (Inspired by image_1871e5.jpg)
        search_col, filter_col = st.columns([2, 1])
        search_query = search_col.text_input("🔍 Search Client or Machine", placeholder="Enter name...")
        status_filter = filter_col.multiselect("Filter Status", ["Pending", "In Production", "Completed"], default=["Pending", "In Production"])

        df_viz = st.session_state.jobs.copy()
        df_viz['start_time'] = pd.to_datetime(df_viz['start_time'])
        df_viz['finish_time'] = pd.to_datetime(df_viz['finish_time'])
        now = datetime.now(timezone.utc)
        
        def get_status(row):
            if row['finish_time'] < now: return "Completed"
            if row['start_time'] <= now <= row['finish_time']: return "In Production"
            return "Pending"
        
        df_viz['Status'] = df_viz.apply(get_status, axis=1)

        # Apply Filters
        if search_query:
            df_viz = df_viz[df_viz['job_name'].str.contains(search_query, case=False) | 
                            df_viz['machine'].str.contains(search_query, case=False)]
        if status_filter:
            df_viz = df_viz[df_viz['Status'].isin(status_filter)]

        # 2. Timeline Visualizer (Updated with fixed axis)
        fig = px.timeline(
            df_viz, x_start="start_time", x_end="finish_time", y="machine", 
            color="job_name", text="job_name", template="plotly_white",
            hover_data={"Status": True, "sales_rep": True},
            color_discrete_sequence=px.colors.qualitative.Prism
        )
        fig.update_layout(
            height=400, showlegend=False, margin=dict(l=10, r=10, t=50, b=10),
            xaxis=dict(side="top", tickformat="%d\n%b", dtick=86400000.0)
        )
        fig.add_vline(x=now.timestamp() * 1000, line_width=2, line_dash="dash", line_color="#ef4444")
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

        # 3. Grouped Dispatch Queue (Matching image_0d895a.png and image_17fda3.png)
        st.markdown("---")
        st.subheader("📅 Dispatch Queue")
        
        # Grouping logic for Date Headers
        df_viz['finish_date'] = df_viz['finish_time'].dt.strftime('%A, %b %d')
        grouped = df_viz.sort_values('finish_time').groupby('finish_date', sort=False)

        for date_str, group in grouped:
            st.markdown(f"#### 🗓️ {date_str}") # Date Header as seen in image_0d895a.png
            
            for _, row in group.iterrows():
                # Dynamic Styling based on Status
                status_color = "#10b981" if row['Status'] == "Completed" else "#3b82f6"
                if row['Status'] == "Pending": status_color = "#f59e0b"

                st.markdown(f"""
                <div style="border-left: 5px solid {status_color}; background-color: white; 
                            padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); 
                            margin-bottom: 12px; border: 1px solid #f1f5f9;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <span style="font-weight: 800; color: #1e3a8a; font-size: 1.1rem;">{row['job_name']}</span>
                            <span style="color: #64748b; margin-left: 10px; font-size: 0.9rem;">| Rep: {row['sales_rep']}</span>
                            <div style="color: #475569; font-size: 0.85rem; margin-top: 4px;">
                                <b>Step:</b> {row['machine']}
                            </div>
                        </div>
                        <div style="text-align: right;">
                            <div style="background: {status_color}22; color: {status_color}; 
                                         padding: 2px 10px; border-radius: 20px; font-weight: bold; 
                                         font-size: 0.75rem; display: inline-block; margin-bottom: 5px;">
                                {row['Status'].upper()}
                            </div>
                            <div style="font-size: 0.85rem; color: #1e3a8a;">
                                <b>Ready:</b> {row['finish_time'].strftime('%I:%M %p')}
                            </div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.info("No active production jobs found.")