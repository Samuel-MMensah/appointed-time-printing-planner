import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
import math
import random
from supabase import create_client, Client
import plotly.express as px

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(page_title="Appointed Time | Elite", layout="wide", page_icon="🏢")

# --- 2. GLOBAL SETUP & TARGETS ---
CURRENCY = "GH₵"
ANNUAL_REVENUE_TARGET = 105000000.00
SETUP_HOURS = 2.0  
DAILY_CAPACITY_HOURS = 9.0  

# Custom CSS for Professional UI
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
    
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    
    .main { background-color: #f1f5f9; }
    
    /* Metric Card Styling */
    div[data-testid="stMetric"] {
        background-color: #ffffff;
        padding: 20px;
        border-radius: 12px;
        box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
        border: 1px solid #e2e8f0;
    }
    
    [data-testid="stMetricValue"] { font-size: 2rem; color: #0f172a; }

    /* Tab Styling */
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] {
        height: 45px;
        white-space: pre;
        background-color: #f8fafc;
        border-radius: 8px;
        color: #64748b;
        border: 1px solid #e2e8f0;
        transition: all 0.3s;
    }
    .stTabs [aria-selected="true"] {
        background-color: #1e40af !important;
        color: white !important;
        box-shadow: 0 4px 12px rgba(30, 64, 175, 0.2);
    }

    /* Cards & Containers */
    .health-card {
        padding: 20px;
        border-radius: 12px;
        background: white;
        border-left: 6px solid #e2e8f0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        margin-bottom: 15px;
    }
    
    .profit-panel {
        background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
        padding: 25px;
        border-radius: 15px;
        border: 1px solid #bae6fd;
        margin-bottom: 25px;
    }

    .header-container {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 1rem 0;
        margin-bottom: 2rem;
        border-bottom: 2px solid #e2e8f0;
    }
    
    .status-badge {
        padding: 6px 12px;
        border-radius: 20px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    </style>
    """, unsafe_allow_html=True)

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

@st.cache_resource
def init_supabase():
    try: return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except: return None

supabase: Client = init_supabase()

# --- 3. CORE ENGINES ---
def is_working_time(dt, night_shift, weekend_work):
    if not weekend_work and dt.weekday() >= 5: return False
    if not night_shift:
        if dt.hour < 8 or dt.hour >= 17: return False
    return True

def calculate_production_end(start_time, duration_hours, night_shift, weekend_work):
    current_time = start_time
    remaining_hours = duration_hours
    while remaining_hours > 0:
        if is_working_time(current_time, night_shift, weekend_work):
            remaining_hours -= (15 / 60)
        current_time += timedelta(minutes=15)
        if (current_time - start_time).days > 365: break 
    return current_time

# --- 4. DATABASE OPERATIONS ---
def get_db_jobs():
    if not supabase: return pd.DataFrame()
    res = supabase.table('jobs').select("*").execute()
    return pd.DataFrame(res.data)

def delete_job(job_name):
    try:
        supabase.table('jobs').delete().eq('job_name', job_name).execute()
        return True
    except: return False

def add_job_to_queue(name, rep, qty, ups, impressions, processes, total_value, night_shift, weekend_work, start_date, mat_costs, ovh_rate):
    now_base = datetime.combine(start_date, datetime.now().time()).replace(tzinfo=timezone.utc, microsecond=0)
    rev_per_step = total_value / len(processes) if processes else 0
    mat_per_step = mat_costs / len(processes) if processes else 0
    tid = f"AT-{random.randint(1000, 9999)}"
    df = get_db_jobs()
    job_seq_start = now_base

    for proc in processes:
        m_free = now_base
        if not df.empty:
            df['finish_time'] = pd.to_datetime(df['finish_time'], utc=True)
            m_jobs = df[df['machine'] == proc]
            if not m_jobs.empty: m_free = max(now_base, m_jobs['finish_time'].max())

        start = max(m_free, job_seq_start)
        while not is_working_time(start, night_shift, weekend_work): start += timedelta(minutes=15)
        
        dur = SETUP_HOURS + (impressions / MACHINE_DATA[proc]['rate'])
        finish = calculate_production_end(start, dur, night_shift, weekend_work)
        job_seq_start = finish
        
        supabase.table('jobs').insert({
            "job_name": name, "sales_rep": rep, "quantity": qty, "ups": ups,
            "impressions": impressions, "contract_value": float(rev_per_step),
            "machine": proc, "start_time": start.isoformat(), "finish_time": finish.isoformat(),
            "material_costs": float(mat_per_step), "overhead_rate": float(ovh_rate),
            "net_profit": float(rev_per_step - mat_per_step - (dur * ovh_rate)),
            "tracking_id": tid
        }).execute()
    return tid

# --- 5. SIDEBAR & HEADER ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2761/2761008.png", width=80)
    st.title("System Status")
    now_gmt = datetime.now(timezone.utc)
    open_status = is_working_time(now_gmt, False, False)
    
    if open_status:
        st.success("● SHOP ONLINE")
    else:
        st.error("○ SHOP CLOSED")
    
    st.divider()
    st.info("System v2.4 Elite\nProduction Intelligence")

st.markdown('<div class="header-container"><div><h1 style="margin:0; color:#1e3a8a;">🏢 Appointed Time</h1><p style="color:#64748b; margin:0;">Operational Excellence & Financial Intelligence</p></div></div>', unsafe_allow_html=True)

tab_dash, tab_plan, tab_control, tab_track = st.tabs(["📊 DASHBOARD", "📝 SIMULATION", "📅 CONTROL", "🚛 TRACKING"])

# --- 6. DASHBOARD TAB ---
with tab_dash:
    df = get_db_jobs()
    if not df.empty:
        df['start_time'] = pd.to_datetime(df['start_time'], utc=True)
        df['finish_time'] = pd.to_datetime(df['finish_time'], utc=True)
        df['duration_hrs'] = (df['finish_time'] - df['start_time']).dt.total_seconds() / 3600

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Projected Revenue", f"{CURRENCY}{df['contract_value'].sum():,.2f}")
        m2.metric("Net Profit", f"{CURRENCY}{df['net_profit'].sum():,.2f}")
        m3.metric("Avg Margin", f"{(df['net_profit'].sum()/df['contract_value'].sum()*100):.1f}%")
        m4.metric("Live Queue", df['job_name'].nunique())

        st.markdown("### 📉 Machine Efficiency (OEE)")
        oee = df.groupby('machine').agg({'duration_hrs': 'sum', 'overhead_rate': 'mean'}).reset_index()
        cols = st.columns(3)
        for i, row in oee.iterrows():
            util = (row['duration_hrs'] / DAILY_CAPACITY_HOURS) * 100
            color = "#16a34a" if util > 70 else ("#f59e0b" if util > 40 else "#dc2626")
            with cols[i % 3]:
                st.markdown(f'<div class="health-card" style="border-left-color: {color};"><strong>{row["machine"]}</strong><br><span style="color:{color}; font-size:1.2rem; font-weight:800;">{util:.1f}%</span> Utilization</div>', unsafe_allow_html=True)

        st.markdown("### 📋 Active Project Details")
        for job, group in df.groupby('job_name'):
            with st.expander(f"💼 {job.upper()} | ID: {group['tracking_id'].iloc[0]}"):
                st.write(f"**Value:** {CURRENCY}{group['contract_value'].sum():,.2f}")
                if st.button(f"Terminate Job", key=f"del_{job}"):
                    if delete_job(job): st.rerun()
    else: st.info("No active production found.")

# --- 7. SIMULATION TAB ---
with tab_plan:
    st.markdown("### 📝 Financial & Production Simulation")
    col1, col2 = st.columns([2,1])
    
    with col1:
        with st.container():
            c1, c2 = st.columns(2)
            name = c1.text_input("Client Name")
            rep = c2.selectbox("Sales Representative", ["Mabel Ampofo", "Daphne Sarpong", "Elizabeth Akoto", "Charles Adoo", "Christian Mante", "Bertha Tackie", "Reginald Aidam"])
            
            q1, q2, q3 = st.columns(3)
            qty = q1.number_input("Quantity", min_value=1, value=1000)
            ups = q2.number_input("Ups", min_value=1, value=1)
            val = q3.number_input("Total Contract (GH₵)", min_value=0.0, value=2000.0)
            
            p1, p2 = st.columns(2)
            mat = p1.number_input("Material Cost (GH₵)", min_value=0.0, value=500.0)
            ovh = p2.number_input("Overhead (GH₵/hr)", min_value=0.0, value=50.0)
            
            procs = st.multiselect("Select Machine Routing", list(MACHINE_DATA.keys()))

    with col2:
        if procs:
            total_h = sum([(SETUP_HOURS + (math.ceil(qty/ups)/MACHINE_DATA[p]['rate'])) for p in procs])
            profit = val - mat - (total_h * ovh)
            y_hr = profit / total_h if total_h > 0 else 0
            
            st.markdown(f"""
            <div class="profit-panel">
                <h5 style='margin:0; color:#1e40af'>WHAT-IF ANALYSIS</h5>
                <hr style='margin:10px 0; border:0; border-top:1px solid #bae6fd'>
                <p style='margin:0; font-size:0.8rem; color:#64748b'>EST. NET PROFIT</p>
                <h2 style='margin:0; color:#0f172a'>{CURRENCY}{profit:,.2f}</h2>
                <br>
                <p style='margin:0; font-size:0.8rem; color:#64748b'>HOURLY YIELD</p>
                <h3 style='margin:0; color:#1e40af'>{CURRENCY}{y_hr:,.2f}/hr</h3>
            </div>
            """, unsafe_allow_html=True)

    st.divider()
    s1, s2, s3 = st.columns(3)
    date = s1.date_input("Start Date")
    night = s2.toggle("Night Shift")
    wknd = s3.toggle("Weekends")

    if st.button("🚀 Push to Production Line", use_container_width=True):
        if name and procs:
            tid = add_job_to_queue(name, rep, qty, ups, math.ceil(qty/ups), procs, val, night, wknd, date, mat, ovh)
            st.success(f"Job Logged. Tracking ID: {tid}")
            st.rerun()

# --- 8. CONTROL & 9. TRACKING ---
with tab_control:
    df = get_db_jobs()
    if not df.empty:
        df['start_time'] = pd.to_datetime(df['start_time'], utc=True)
        df['finish_time'] = pd.to_datetime(df['finish_time'], utc=True)
        fig = px.timeline(df, x_start="start_time", x_end="finish_time", y="machine", color="job_name", template="plotly_white", color_discrete_sequence=px.colors.qualitative.Prism)
        fig.update_layout(showlegend=False, height=400)
        st.plotly_chart(fig, use_container_width=True)

with tab_track:
    st.markdown("### 🚛 Order Tracking")
    sid = st.text_input("Enter Tracking ID (e.g., AT-1416)").upper().strip()
    
    if sid:
        all_j = get_db_jobs()
        if not all_j.empty:
            # Filter for all stages of this specific tracking ID
            match = all_j[all_j['tracking_id'] == sid].copy()
            
            if not match.empty:
                # Ensure finish_time is a datetime object for sorting
                match['finish_time'] = pd.to_datetime(match['finish_time'], utc=True)
                match = match.sort_values('finish_time')
                
                # Calculate overall job status
                final_deadline = match['finish_time'].max()
                total_stages = len(match)
                completed_stages = len(match[match['finish_time'] < datetime.now(timezone.utc)])
                progress = completed_stages / total_stages
                
                # Professional Status Header
                c1, c2 = st.columns([2, 1])
                with c1:
                    st.success(f"**Project Identified:** {match['job_name'].iloc[0]}")
                    st.write(f"📅 **Estimated Completion:** {final_deadline.strftime('%A, %b %d at %I:%M %p')}")
                with c2:
                    st.metric("Overall Progress", f"{int(progress * 100)}%")

                st.progress(progress)
                
                st.markdown("#### ⚙️ Production Roadmap")
                # Create a visual step-by-step list
                for i, row in match.iterrows():
                    is_done = row['finish_time'] < datetime.now(timezone.utc)
                    status_icon = "✅" if is_done else "⏳"
                    status_text = "Completed" if is_done else "In Progress / Pending"
                    
                    st.markdown(f"""
                    <div style="padding:10px; border-radius:8px; background-color:#f8fafc; border:1px solid #e2e8f0; margin-bottom:5px;">
                        <span style="font-size:1.2rem;">{status_icon}</span> 
                        <strong>Stage {match.index.get_loc(i) + 1}: {row['machine']}</strong><br>
                        <small style="color:#64748b;">Status: {status_text} | Ready by: {row['finish_time'].strftime('%b %d, %H:%M')}</small>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.warning("Tracking ID not found. Please verify the ID and try again.")
        else:
            st.error("No production data available in the system.")
