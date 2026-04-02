import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
import math
import random
from supabase import create_client, Client
import plotly.express as px

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(page_title="Appointed Time | Production Control", layout="wide", page_icon="🏢")

# --- 2. GLOBAL SETUP ---
CURRENCY = "GH₵"
SETUP_HOURS = 2.0  
DAILY_CAPACITY_HOURS = 9.0  

MACHINE_DATA = {
    'CANON DIGITAL C10000': {'rate': 6000},
    'CANON DIGITAL C800': {'rate': 4000},
    'SM102-CX FOUR COLOUR': {'rate': 8000}, 
    'SM102-P FIVE COLOUR': {'rate': 7500},
    'SM 52': {'rate': 7000}, 
    'GTO 52 SEMI-AUTO-2 COLOUR': {'rate': 4500},
    'GTO 52 MANUAL-2 COLOUR': {'rate': 4000}, 
    'FOLDING UNIT': {'rate': 8000},
    'POLAR CUTTER': {'rate': 20000}, 
    'PERFECT BINDING': {'rate': 500}, 
    'SADDLE STITCHER': {'rate': 1000}, 
    'LAMINATION UNIT': {'rate': 2500},
}

# --- 3. CSS & STYLING ---
st.markdown("""
    <style>
    .main { background-color: #f8fafc; }
    .component-card { background-color: #ffffff; padding: 20px; border-radius: 12px; border: 1px solid #e2e8f0; margin-bottom: 15px; }
    .status-done { color: #16a34a; font-weight: bold; }
    .status-pending { color: #2563eb; font-weight: bold; }
    div[data-testid="stMetric"] { background-color: white; border: 1px solid #e2e8f0; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_resource
def init_supabase():
    try: return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except: return None

supabase: Client = init_supabase()

# --- 4. CORE ENGINES ---
def is_working_time(dt, night, weekend):
    if not weekend and dt.weekday() >= 5: return False
    if not night and (dt.hour < 8 or dt.hour >= 17): return False
    return True

def calculate_finish(start_time, duration_hrs, night, weekend):
    curr = start_time
    rem = duration_hrs
    while rem > 0:
        if is_working_time(curr, night, weekend): rem -= 0.25
        curr += timedelta(minutes=15)
    return curr

# --- 5. DATABASE OPS ---
def get_db_jobs():
    if not supabase: return pd.DataFrame()
    res = supabase.table('jobs').select("*").execute()
    return pd.DataFrame(res.data)

def delete_job(job_name):
    try:
        supabase.table('jobs').delete().eq('job_name', job_name).execute()
        return True
    except: return False

def add_multi_part_job(job_data):
    # Generates a hidden ID for internal linking only
    tid = f"INT-{random.randint(1000, 9999)}"
    comp_finish_times = []
    
    total_stages = sum(len(c['machines']) for c in job_data['components']) + len(job_data['finishing_machines'])
    val_per_stage = job_data['total_val'] / total_stages if total_stages > 0 else 0

    for comp in job_data['components']:
        if not comp['machines']: continue
        comp_start = datetime.combine(job_data['start_date'], datetime.now().time()).replace(tzinfo=timezone.utc)
        
        for machine in comp['machines']:
            dur = SETUP_HOURS + (comp['impressions'] / MACHINE_DATA[machine]['rate'])
            finish = calculate_finish(comp_start, dur, job_data['night'], job_data['weekend'])
            
            supabase.table('jobs').insert({
                "job_name": job_data['name'], "tracking_id": tid, "machine": machine,
                "sales_rep": job_data['sales_rep'], "quantity": int(job_data['total_qty']),
                "ups": int(comp.get('ups', 1)), "impressions": int(comp['impressions']),
                "start_time": comp_start.isoformat(), "finish_time": finish.isoformat(),
                "contract_value": float(val_per_stage), "net_profit": 0, "material_costs": 0, "overhead_rate": 0
            }).execute()
            comp_start = finish
        comp_finish_times.append(comp_start)

    if job_data['finishing_machines']:
        finish_start = max(comp_finish_times) if comp_finish_times else datetime.combine(job_data['start_date'], datetime.now().time()).replace(tzinfo=timezone.utc)
        for f_mach in job_data['finishing_machines']:
            f_dur = SETUP_HOURS + (job_data['total_qty'] / MACHINE_DATA[f_mach]['rate'])
            f_finish = calculate_finish(finish_start, f_dur, job_data['night'], job_data['weekend'])
            supabase.table('jobs').insert({
                "job_name": job_data['name'], "tracking_id": tid, "machine": f_mach,
                "sales_rep": job_data['sales_rep'], "quantity": int(job_data['total_qty']), "ups": 1, 
                "impressions": int(job_data['total_qty']), "start_time": finish_start.isoformat(), 
                "finish_time": f_finish.isoformat(), "contract_value": float(val_per_stage), 
                "net_profit": 0, "material_costs": 0, "overhead_rate": 0
            }).execute()
            finish_start = f_finish
    return tid

# --- 6. UI TABS ---
tab_dash, tab_plan, tab_control = st.tabs(["📊 DASHBOARD", "📝 SIMULATION", "📅 PRODUCTION CONTROL"])

# --- DASHBOARD ---
with tab_dash:
    df = get_db_jobs()
    if not df.empty:
        df['start_time'] = pd.to_datetime(df['start_time'], format='ISO8601', utc=True)
        df['finish_time'] = pd.to_datetime(df['finish_time'], format='ISO8601', utc=True)
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Active Projects", df['job_name'].nunique())
        m2.metric("Projected Revenue", f"{CURRENCY}{df['contract_value'].sum():,.2f}")
        m3.metric("Total Impressions", f"{int(df['impressions'].sum()):,}")
        
        st.divider()
        st.markdown("### 🛠️ Machine Queue Length")
        q_view = df[df['finish_time'] > datetime.now(timezone.utc)].groupby('machine').size().reset_index(name='Jobs Waiting')
        st.bar_chart(q_view.set_index('machine'))
    else:
        st.info("No active production in system.")

# --- SIMULATION ---
with tab_plan:
    st.subheader("📝 New Job Entry")
    c1, c2, c3 = st.columns([2, 1, 1])
    job_name = c1.text_input("Job Name / Description")
    sales_rep = c2.selectbox("Sales Rep", ["Mabel Ampofo", "Daphne Sarpong", "Elizabeth Akoto", "Charles Adoo", "Christian Mante", "Bertha Tackie", "Reginald Aidam"])
    total_val = c3.number_input("Total Quote (GH₵)", min_value=0.0, value=1000.0)

    col_input, col_info = st.columns([2, 1])
    with col_input:
        # Part 1: Cover
        with st.container():
            st.markdown('<div class="component-card">', unsafe_allow_html=True)
            st.markdown("### 📔 Cover Component")
            cc1, cc2 = st.columns(2)
            cov_qty = cc1.number_input("Order Qty", value=1000)
            cov_ups = cc2.number_input("Ups", value=1)
            cov_route = st.multiselect("Routing: Cover", list(MACHINE_DATA.keys()))
            st.markdown('</div>', unsafe_allow_html=True)

        # Part 2: Inners
        with st.container():
            st.markdown('<div class="component-card">', unsafe_allow_html=True)
            st.markdown("### 📄 Text Component")
            tc1, tc2 = st.columns(2)
            pages = tc1.number_input("Total Pages", value=1)
            sig_size = tc2.selectbox("Pages per Plate", [1, 2, 4, 8, 16, 32], index=0)
            text_impressions = math.ceil(pages / sig_size) * cov_qty
            text_route = st.multiselect("Routing: Text", list(MACHINE_DATA.keys()))
            st.markdown('</div>', unsafe_allow_html=True)

        # Part 3: Finishing
        with st.container():
            st.markdown('<div class="component-card">', unsafe_allow_html=True)
            st.markdown("### 🛠️ Binding & Finishing")
            fin_route = st.multiselect("Routing: Finishing", list(MACHINE_DATA.keys()))
            st.markdown('</div>', unsafe_allow_html=True)

    with col_info:
        st.info("**Production Summary**\n\nEnsure all stages are selected for accurate scheduling.")
        s1, s2 = st.columns(2)
        night = s1.toggle("Night Shift")
        wknd = s2.toggle("Work Weekends")
        start_date = st.date_input("Scheduled Start Date")

    if st.button("🚀 Push to Production Line", use_container_width=True):
        if job_name:
            payload = {
                "name": job_name, "sales_rep": sales_rep, "total_qty": cov_qty, "total_val": total_val,
                "start_date": start_date, "night": night, "weekend": wknd, "net_profit": 0,
                "components": [
                    {"name": "Cover", "impressions": cov_qty/cov_ups, "ups": cov_ups, "machines": cov_route},
                    {"name": "Text", "impressions": text_impressions, "ups": 1, "machines": text_route}
                ],
                "finishing_machines": fin_route
            }
            add_multi_part_job(payload)
            st.success(f"Job '{job_name}' is now LIVE in Production Control.")
            st.rerun()

# --- PRODUCTION CONTROL ---
with tab_control:
    st.subheader("📅 Live Shop Floor Status")
    df = get_db_jobs()
    
    if not df.empty:
        df['start_time'] = pd.to_datetime(df['start_time'], format='ISO8601', utc=True)
        df['finish_time'] = pd.to_datetime(df['finish_time'], format='ISO8601', utc=True)
        now = datetime.now(timezone.utc)

        # 1. Gantt Chart Overview
        fig = px.timeline(df, x_start="start_time", x_end="finish_time", y="machine", color="job_name", 
                          title="Machine Schedule Overview", template="plotly_white")
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(fig, use_container_width=True)

        st.divider()
        st.markdown("### 📋 Production Details (Expand for Stages)")
        
        # 2. Tabular Job List with Expanders
        for job_name, group in df.groupby('job_name'):
            group = group.sort_values('finish_time')
            overall_finish = group['finish_time'].max()
            is_complete = overall_finish < now
            status_label = "✅ COMPLETED" if is_complete else "⏳ IN PROGRESS"
            
            with st.expander(f"{status_label} | {job_name.upper()} | Deadline: {overall_finish.strftime('%d %b, %H:%M')}"):
                # Sales/Header Info
                c1, c2, c3 = st.columns(3)
                c1.write(f"**Sales Rep:** {group['sales_rep'].iloc[0]}")
                c2.write(f"**Total Qty:** {int(group['quantity'].iloc[0]):,}")
                c3.write(f"**Total Value:** {CURRENCY}{group['contract_value'].sum():,.2f}")
                
                # Internal Process Table
                st.markdown("#### Process Roadmap")
                process_data = []
                for _, row in group.iterrows():
                    step_status = "Done" if row['finish_time'] < now else "Pending"
                    process_data.append({
                        "Machine": row['machine'],
                        "Impressions": f"{int(row['impressions']):,}",
                        "Start Time": row['start_time'].strftime('%d %b, %H:%M'),
                        "Finish Time": row['finish_time'].strftime('%d %b, %H:%M'),
                        "Status": step_status
                    })
                
                st.table(pd.DataFrame(process_data))
                
                if st.button(f"Terminate {job_name}", key=f"del_{job_name}"):
                    if delete_job(job_name): st.rerun()
    else:
        st.info("No active jobs in the production table.")
