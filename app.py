import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
import math
import random
from supabase import create_client, Client
import plotly.express as px

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(page_title="Appointed Time | Elite Planner", layout="wide", page_icon="🏢")

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
    .main { background-color: #f1f5f9; }
    .component-card { background-color: #ffffff; padding: 20px; border-radius: 12px; border: 1px solid #e2e8f0; margin-bottom: 15px; }
    .profit-panel { background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); color: white; padding: 25px; border-radius: 15px; position: sticky; top: 20px; }
    div[data-testid="stMetric"] { background-color: white; padding: 15px; border-radius: 10px; border: 1px solid #e2e8f0; }
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

def add_multi_part_job(job_data):
    tid = f"AT-{random.randint(1000, 9999)}"
    comp_finish_times = []
    
    # Calculate total steps for financial distribution
    total_stages = sum(len(c['machines']) for c in job_data['components']) + len(job_data['finishing_machines'])
    val_per_stage = job_data['total_val'] / total_stages if total_stages > 0 else 0
    profit_per_stage = job_data['net_profit'] / total_stages if total_stages > 0 else 0
    mat_per_stage = job_data['total_mat'] / total_stages if total_stages > 0 else 0

    for comp in job_data['components']:
        if not comp['machines']: continue
        comp_start = datetime.combine(job_data['start_date'], datetime.now().time()).replace(tzinfo=timezone.utc)
        
        for machine in comp['machines']:
            dur = SETUP_HOURS + (comp['impressions'] / MACHINE_DATA[machine]['rate'])
            finish = calculate_finish(comp_start, dur, job_data['night'], job_data['weekend'])
            
            # ALL database columns must be present to avoid 23502 error
            supabase.table('jobs').insert({
                "job_name": job_data['name'], 
                "tracking_id": tid, 
                "machine": machine,
                "sales_rep": job_data['sales_rep'],
                "quantity": int(job_data['total_qty']),
                "ups": int(comp.get('ups', 1)),
                "impressions": int(comp['impressions']),
                "start_time": comp_start.isoformat(), 
                "finish_time": finish.isoformat(),
                "net_profit": float(profit_per_stage), 
                "contract_value": float(val_per_stage),
                "material_costs": float(mat_per_stage),
                "overhead_rate": float(job_data['ovh_rate'])
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
                "sales_rep": job_data['sales_rep'],
                "quantity": int(job_data['total_qty']), "ups": 1, "impressions": int(job_data['total_qty']),
                "start_time": finish_start.isoformat(), "finish_time": f_finish.isoformat(),
                "net_profit": float(profit_per_stage), "contract_value": float(val_per_stage),
                "material_costs": 0.0, "overhead_rate": float(job_data['ovh_rate'])
            }).execute()
            finish_start = f_finish
    return tid

# --- 6. UI TABS ---
tab_dash, tab_plan, tab_control, tab_track = st.tabs(["📊 DASHBOARD", "📝 SIMULATION", "📅 CONTROL", "🚛 TRACKING"])

with tab_dash:
    df = get_db_jobs()
    if not df.empty:
        df['start_time'] = pd.to_datetime(df['start_time'], utc=True)
        df['finish_time'] = pd.to_datetime(df['finish_time'], utc=True)
        df['duration_hrs'] = (df['finish_time'] - df['start_time']).dt.total_seconds() / 3600

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Projected Revenue", f"{CURRENCY}{df['contract_value'].sum():,.2f}")
        m2.metric("Net Profit", f"{CURRENCY}{df['net_profit'].sum():,.2f}")
        m3.metric("Avg Margin", f"{(df['net_profit'].sum()/df['contract_value'].sum()*100 if df['contract_value'].sum()>0 else 0):.1f}%")
        m4.metric("Live Queue", df['job_name'].nunique())

        st.markdown("### 📉 Machine Utilization")
        oee = df.groupby('machine').agg({'duration_hrs': 'sum'}).reset_index()
        cols = st.columns(3)
        for i, row in oee.iterrows():
            util = (row['duration_hrs'] / DAILY_CAPACITY_HOURS) * 100
            with cols[i % 3]:
                st.write(f"**{row['machine']}**")
                st.progress(min(util/100, 1.0))

with tab_plan:
    st.subheader("📝 Multi-Component Production Planner")
    c1, c2, c3 = st.columns([2, 1, 1])
    job_name = c1.text_input("Project Name")
    sales_rep = c2.selectbox("Sales Representative", ["Mabel Ampofo", "Daphne Sarpong", "Elizabeth Akoto", "Charles Adoo", "Christian Mante", "Bertha Tackie", "Reginald Aidam"])
    total_val = c3.number_input("Total Contract Value", min_value=0.0, value=5000.0)

    col_input, col_viz = st.columns([2, 1])
    with col_input:
        with st.container():
            st.markdown('<div class="component-card">', unsafe_allow_html=True)
            st.markdown("### 📔 Part 1: Cover Specs")
            cc1, cc2, cc3 = st.columns(3)
            cov_qty = cc1.number_input("Qty", value=1000)
            cov_ups = cc2.number_input("Ups", value=2)
            cov_mat = cc3.number_input("Paper Cost", value=200.0)
            cov_route = st.multiselect("Manual Routing: Cover", list(MACHINE_DATA.keys()))
            st.markdown('</div>', unsafe_allow_html=True)

        with st.container():
            st.markdown('<div class="component-card">', unsafe_allow_html=True)
            st.markdown("### 📄 Part 2: Inner Text Specs")
            tc1, tc2, tc3 = st.columns(3)
            pages = tc1.number_input("Pages", value=64)
            sig_size = tc2.selectbox("Sig Size", [8, 16, 32], index=1)
            text_mat = tc3.number_input("Paper Cost ", value=800.0)
            text_impressions = math.ceil(pages / sig_size) * cov_qty
            text_route = st.multiselect("Manual Routing: Inners", list(MACHINE_DATA.keys()))
            st.markdown('</div>', unsafe_allow_html=True)

        with st.container():
            st.markdown('<div class="component-card">', unsafe_allow_html=True)
            st.markdown("### 🛠️ Part 3: Finishing")
            fin_route = st.multiselect("Manual Routing: Binding", list(MACHINE_DATA.keys()))
            st.markdown('</div>', unsafe_allow_html=True)

    with col_viz:
        ovh_rate = st.number_input("Overhead (GH₵/hr)", value=60.0)
        est_hrs = (len(cov_route + text_route + fin_route) * SETUP_HOURS) 
        net_profit = total_val - (cov_mat + text_mat) - (est_hrs * ovh_rate)
        
        st.markdown(f'<div class="profit-panel"><h3>{CURRENCY}{net_profit:,.2f}</h3><p>Est. Net Profit</p><hr><p>Margin: {(net_profit/total_val*100 if total_val>0 else 0):.1f}%</p></div>', unsafe_allow_html=True)

    s1, s2, s3 = st.columns(3)
    start_date = s1.date_input("Schedule Start")
    night = s2.toggle("🌙 Night Shift")
    wknd = s3.toggle("📅 Weekends")
    
    if st.button("🚀 Commit Full Project", width="stretch"):
        if job_name and sales_rep:
            payload = {
                "name": job_name, "sales_rep": sales_rep, "total_qty": cov_qty, "total_val": total_val,
                "start_date": start_date, "night": night, "weekend": wknd, "net_profit": net_profit,
                "total_mat": (cov_mat + text_mat), "ovh_rate": ovh_rate,
                "components": [
                    {"name": "Cover", "impressions": cov_qty/cov_ups, "ups": cov_ups, "machines": cov_route},
                    {"name": "Text", "impressions": text_impressions, "ups": 1, "machines": text_route}
                ],
                "finishing_machines": fin_route
            }
            tid = add_multi_part_job(payload)
            st.success(f"Project Queued! ID: {tid}")
            st.rerun()

with tab_control:
    df = get_db_jobs()
    if not df.empty:
        df['start_time'] = pd.to_datetime(df['start_time'], utc=True)
        df['finish_time'] = pd.to_datetime(df['finish_time'], utc=True)
        fig = px.timeline(df, x_start="start_time", x_end="finish_time", y="machine", color="job_name", template="plotly_white")
        st.plotly_chart(fig, width="stretch")

with tab_track:
    st.markdown("### 🚛 Order Tracking")
    sid = st.text_input("Enter Tracking ID").upper().strip()
    if sid:
        df = get_db_jobs()
        match = df[df['tracking_id'] == sid].sort_values('finish_time')
        if not match.empty:
            st.success(f"Project: {match['job_name'].iloc[0]}")
            st.write(f"Estimated Completion: {match['finish_time'].max()}")
            for _, row in match.iterrows():
                st.write(f"- {row['machine']}: Ready by {pd.to_datetime(row['finish_time']).strftime('%b %d, %H:%M')}")
