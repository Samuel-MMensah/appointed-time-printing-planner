import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
import math
import random
from supabase import create_client, Client
import plotly.express as px

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Appointed Time | Enterprise Production Suite", 
    layout="wide", 
    page_icon="🏢",
    initial_sidebar_state="collapsed"
)

# --- 2. GLOBAL SETUP & MACHINE REGISTRY ---
CURRENCY = "GH₵"
SHIFT_START_HOUR = 8
SHIFT_END_HOUR = 17
DAILY_CAPACITY_HOURS = 8.0 

# Machine profiles cleanly mapped to shop documentation requirements
MACHINE_DATA = {
    'SM102-CX FOUR COLOUR': {'rate': 8000, 'setup_hours': 1.5},
    'SM102-P FIVE COLOUR': {'rate': 7500, 'setup_hours': 1.5},
    'SM 52': {'rate': 7000, 'setup_hours': 1.5},
    'GTO 52 SEMI-AUTO-2 COLOUR': {'rate': 4500, 'setup_hours': 1.5},
    'GTO 52 MANUAL-2 COLOUR': {'rate': 4000, 'setup_hours': 2.0},
    'FOLDING UNIT (CONTINUOUS)': {'rate': 8000, 'setup_hours': 1.5},
    'MBO-B30E (SINGLE FOLD)': {'rate': 16000, 'setup_hours': 1.5},
    'PERFECT BINDING': {'rate': 500, 'setup_hours': 1.5},
    'SADDLE STITCHER': {'rate': 1000, 'setup_hours': 1.5},
    'POLAR CUTTER (BOOKS)': {'rate': 2000, 'setup_hours': 1.0},
    'POLAR CUTTER (SHEETS)': {'rate': 50000, 'setup_hours': 1.0},
    '3 WAY TRIMMER': {'rate': 5000, 'setup_hours': 1.0},
    'LAMINATION UNIT': {'rate': 2500, 'setup_hours': 1.5},
    'DIE CUTTER': {'rate': 3000, 'setup_hours': 1.5},
    'FOLDER GLUER': {'rate': 12000, 'setup_hours': 1.5},
    'CANON DIGITAL C10000': {'rate': 6000, 'setup_hours': 0.5},
    'CANON DIGITAL C800': {'rate': 4000, 'setup_hours': 0.5},
}

# --- 3. PREMIUM EXECUTIVE UI STYLING (CSS) ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    /* Global Overrides */
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
        background-color: #f8fafc;
    }
    
    .main-title {
        font-size: 2.25rem;
        font-weight: 800;
        color: #0f172a;
        margin-bottom: 0.25rem;
        letter-spacing: -0.025em;
    }
    .main-subtitle {
        font-size: 0.95rem;
        color: #64748b;
        margin-bottom: 2rem;
    }
    
    /* Modern Section Headers */
    .section-header {
        font-size: 1.35rem;
        font-weight: 700;
        color: #1e293b;
        margin-top: 2rem;
        margin-bottom: 1rem;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }
    
    /* Card Layouts */
    .planner-card {
        background: #ffffff;
        padding: 2rem;
        border-radius: 16px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
        margin-bottom: 1rem;
    }
    
    .summary-box {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        color: #ffffff;
        padding: 2rem;
        border-radius: 16px;
        box-shadow: 0 10px 15px -3px rgba(15, 23, 42, 0.15);
    }
    
    /* Dashboard KPI Metrics */
    .metric-card {
        background: #ffffff;
        padding: 1.5rem;
        border-radius: 14px;
        border: 1px solid #e2e8f0;
        border-bottom: 4px solid #3b82f6;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.02);
        text-align: left;
        transition: transform 0.2s ease;
    }
    .metric-card:hover {
        transform: translateY(-2px);
    }
    .metric-label {
        font-size: 0.75rem;
        color: #64748b;
        text-transform: uppercase;
        font-weight: 700;
        letter-spacing: 0.05em;
    }
    .metric-value {
        font-size: 1.75rem;
        font-weight: 800;
        color: #0f172a;
        margin-top: 0.25rem;
    }
    
    /* Customizing Streamlit Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: #f1f5f9;
        padding: 6px;
        border-radius: 12px;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 8px 16px;
        border-radius: 8px;
        color: #64748b;
        font-weight: 600;
        transition: all 0.2s ease;
    }
    .stTabs [aria-selected="true"] {
        background-color: #ffffff !important;
        color: #0f172a !important;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1);
    }
    </style>
    """, unsafe_allow_html=True)

# --- 4. BACKEND INFRASTRUCTURE CORE ---

@st.cache_resource
def init_supabase():
    try: return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except: return None

supabase: Client = init_supabase()

def get_db_jobs():
    if not supabase: return pd.DataFrame()
    try:
        res = supabase.table('jobs').select("*").execute()
        return pd.DataFrame(res.data)
    except: return pd.DataFrame()

def apply_calendar_bounds(dt):
    """Schedules around fixed daily operational windows and removes weekend overlaps."""
    if dt.hour < SHIFT_START_HOUR:
        dt = dt.replace(hour=SHIFT_START_HOUR, minute=0, second=0, microsecond=0)
    elif dt.hour >= SHIFT_END_HOUR:
        dt = (dt + timedelta(days=1)).replace(hour=SHIFT_START_HOUR, minute=0, second=0, microsecond=0)
    while dt.weekday() in [5, 6]:
        dt = (dt + timedelta(days=1)).replace(hour=SHIFT_START_HOUR, minute=0, second=0, microsecond=0)
    return dt

def get_machine_next_available_time(machine_name, requested_start_dt):
    """Maintains proper asset availability timelines by querying previous job allocations."""
    df = get_db_jobs()
    if df.empty or 'machine' not in df.columns:
        return apply_calendar_bounds(requested_start_dt)
    
    m_df = df[df['machine'] == machine_name].copy()
    if m_df.empty:
        return apply_calendar_bounds(requested_start_dt)
    
    m_df['finish_time'] = pd.to_datetime(m_df['finish_time'], utc=True, format='mixed')
    max_finish = m_df['finish_time'].max().to_pydatetime()
    
    return apply_calendar_bounds(max_finish) if max_finish > requested_start_dt else apply_calendar_bounds(requested_start_dt)

def calculate_production_time(start_dt, impressions, machine_name, apply_setup=True):
    """Tracks chronological machine throughput output over multiple active shifts."""
    mach = MACHINE_DATA[machine_name]
    rate = mach['rate']
    setup = mach['setup_hours'] if apply_setup else 0.0
    
    current_time = apply_calendar_bounds(start_dt)
    if apply_setup:
        current_time += timedelta(hours=setup)
        current_time = apply_calendar_bounds(current_time)
        
    remaining_imps = impressions
    while remaining_imps > 0:
        current_time = apply_calendar_bounds(current_time)
        workday_end = current_time.replace(hour=SHIFT_END_HOUR, minute=0, second=0, microsecond=0)
        available_hours = (workday_end - current_time).total_seconds() / 3600.0
        
        if available_hours <= 0:
            current_time = (current_time + timedelta(days=1)).replace(hour=SHIFT_START_HOUR, minute=0)
            continue
            
        possible_today = available_hours * rate
        if remaining_imps <= possible_today:
            current_time += timedelta(hours=remaining_imps / rate)
            remaining_imps = 0
        else:
            remaining_imps -= possible_today
            current_time = (current_time + timedelta(days=1)).replace(hour=SHIFT_START_HOUR, minute=0)
            
    return apply_calendar_bounds(current_time)

def add_multi_part_job(job_data):
    """Calculates staging paths and handles interlocking flow structures for shop production."""
    tid = f"JOB-{random.randint(1000, 9999)}"
    total_stages = sum(len(c['machines']) for c in job_data['components']) + len(job_data['finishing_machines'])
    val_per_stage = job_data['total_val'] / total_stages if total_stages > 0 else 0

    anchor_start = datetime.combine(job_data['start_date'], datetime.now().time()).replace(tzinfo=timezone.utc)
    printing_finishes = []
    records = []

    # 1. PRINT PROCESSING
    for comp in job_data['components']:
        for machine in comp['machines']:
            allocated_start = get_machine_next_available_time(machine, anchor_start)
            finish = calculate_production_time(allocated_start, comp['impressions'], machine)
            printing_finishes.append(finish)
            
            records.append({
                "job_name": job_data['name'], "tracking_id": tid, "machine": machine,
                "sales_rep": job_data['sales_rep'], "quantity": int(job_data['total_qty']),
                "ups": int(job_data['type_id']), "impressions": int(comp['impressions']), 
                "start_time": allocated_start.isoformat(), "finish_time": finish.isoformat(), 
                "contract_value": float(val_per_stage)
            })

    earliest_finishing_base = max(printing_finishes) if printing_finishes else apply_calendar_bounds(anchor_start)

    # 2. STAGGERED FINISHING ROUTING (Die Cutter -> 2h buffer -> Folder Gluer)
    ordered_finishing = sorted(job_data['finishing_machines'], 
                               key=lambda x: 0 if "DIE" in x.upper() else (1 if "FOLDER" in x.upper() else 2))

    last_stage_finish = earliest_finishing_base
    die_cutter_start_time = None

    for machine_name in ordered_finishing:
        if "DIE CUTTER" in machine_name.upper():
            calculation_qty = job_data['total_qty'] / max(1, job_data['type_id'])
            f_start = get_machine_next_available_time(machine_name, anchor_start)
            f_finish = calculate_production_time(f_start, calculation_qty, machine_name)
            
            die_cutter_start_time = f_start
            last_stage_finish = f_finish

        elif "FOLDER GLUER" in machine_name.upper() and die_cutter_start_time is not None:
            calculation_qty = job_data['total_qty']
            stagger_offset_dt = calculate_production_time(die_cutter_start_time, MACHINE_DATA['DIE CUTTER']['rate'] * 2, 'DIE CUTTER')
            
            f_start = get_machine_next_available_time(machine_name, stagger_offset_dt)
            f_finish = calculate_production_time(f_start, calculation_qty, machine_name)
            last_stage_finish = f_finish
        else:
            calculation_qty = job_data['total_qty']
            f_start = get_machine_next_available_time(machine_name, last_stage_finish)
            f_finish = calculate_production_time(f_start, calculation_qty, machine_name)
            last_stage_finish = f_finish

        records.append({
            "job_name": job_data['name'], "tracking_id": tid, "machine": machine_name,
            "sales_rep": job_data['sales_rep'], "quantity": int(job_data['total_qty']),
            "ups": int(job_data['type_id']), "impressions": int(calculation_qty),
            "start_time": f_start.isoformat(), "finish_time": f_finish.isoformat(),
            "contract_value": float(val_per_stage)
        })

    if supabase and records:
        for r in records: supabase.table('jobs').insert(r).execute()

# --- 5. ENTERPRISE CONTROLS & MANAGEMENT INTERFACE ---
st.markdown('<div class="main-title">Appointed Time</div>', unsafe_allow_html=True)
st.markdown('<div class="main-subtitle">Commercial Print Scheduling Engine & Finite Capacity Queue Manager</div>', unsafe_allow_html=True)

tab_dash, tab_plan, tab_control = st.tabs(["🏛 COMMAND CENTER", "⚙ PRODUCTION PLANNER", "📅 SHOP FLOOR CONTROL"])

with tab_dash:
    df = get_db_jobs()
    if not df.empty:
        df['start_time'] = pd.to_datetime(df['start_time'], utc=True, format='mixed')
        
        # Grid layout for high-level KPIs
        c1, c2, c3, c4 = st.columns(4)
        with c1: st.markdown(f'<div class="metric-card"><div class="metric-label">Active Orders</div><div class="metric-value">{df["tracking_id"].nunique()}</div></div>', unsafe_allow_html=True)
        with c2: st.markdown(f'<div class="metric-card"><div class="metric-label">Pipeline Contract Value</div><div class="metric-value">{CURRENCY}{df["contract_value"].sum():,.2f}</div></div>', unsafe_allow_html=True)
        with c3:
            books = df[df['ups'] == 1]['tracking_id'].nunique()
            st.markdown(f'<div class="metric-card"><div class="metric-label">Book Runs Queue</div><div class="metric-value">{books}</div></div>', unsafe_allow_html=True)
        with c4:
            skillets = df[df['ups'] > 1]['tracking_id'].nunique()
            st.markdown(f'<div class="metric-card"><div class="metric-label">Packaging Skillets</div><div class="metric-value">{skillets}</div></div>', unsafe_allow_html=True)

        st.markdown('<div class="section-header">📊 Strategic Capacity Distribution & Revenue</div>', unsafe_allow_html=True)
        left, right = st.columns([2, 1])
        with left:
            load_df = df.groupby('machine').size().reset_index(name='Allocated Components')
            fig_load = px.bar(load_df, x='machine', y='Allocated Components', color='Allocated Components', color_continuous_scale='Blues', labels={'machine': 'Resource Profile'})
            fig_load.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', showlegend=False, margin=dict(t=10, b=10, l=10, r=10))
            st.plotly_chart(fig_load, use_container_width=True)
        with right:
            rev_df = df.groupby('job_name')['contract_value'].sum().reset_index()
            fig_rev = px.pie(rev_df, values='contract_value', names='job_name', hole=0.6, color_discrete_sequence=px.colors.qualitative.Pastel)
            fig_rev.update_layout(margin=dict(t=10, b=10, l=10, r=10), legend=dict(orientation="h", y=-0.1))
            st.plotly_chart(fig_rev, use_container_width=True)
    else:
        st.info("No active machine runs detected in the live database pipeline.")

with tab_plan:
    st.markdown('<div class="section-header">⚙ Architecture Layout Builder</div>', unsafe_allow_html=True)
    col_in, col_sum = st.columns([2, 1])
    
    with col_in:
        st.markdown('<div class="planner-card">', unsafe_allow_html=True)
        job_name = st.text_input("Project Description / Customer ID", placeholder="e.g. NUTRIFOODS Carton Run")
        sales_rep = st.selectbox("Sales Executive Lead", ["Isaac Kum","Mabel Ampofo", "Daphne Sarpong", "Elizabeth Akoto", "Charles Adoo", "Christian Mante", "Bertha Tackie", "Reginald Aidam", "Mohammed Seidu"])
        prod_cat = st.selectbox("Production Layout Category", ["📦 Skillet / Box Packing", "📚 Book / Magazine Brochure", "📄 Flat Sheet Flyer"])
        
        c1, c2, c3 = st.columns(3)
        order_qty = c1.number_input("Target Order Units", value=10000, step=1000)
        total_val = c2.number_input(f"Total Contract Value ({CURRENCY})", value=5000.0, step=500.0)
        ups = c3.number_input("Ups Per Print Sheet Layout", value=10, min_value=1)
        
        st.markdown("<br><p style='font-weight:600; font-size:0.95rem; margin-bottom:5px; color:#1e293b;'>Routing Chain Sequence Matrix</p>", unsafe_allow_html=True)
        if "Book" in prod_cat:
            type_id, pgs = 1, st.number_input("Total Page Count", value=64, min_value=1)
            sig = st.selectbox("Signature Form Factor", [8, 16, 32], index=1)
            text_imps = math.ceil(pgs/sig) * order_qty
            r1, r2, r3 = st.columns(3)
            comp = [
                {"name": "Cover", "impressions": max(1.0, order_qty/ups), "machines": r1.multiselect("Cover Asset Configuration", list(MACHINE_DATA.keys()))},
                {"name": "Text", "impressions": float(text_imps), "machines": r2.multiselect("Text Interior Asset Configuration", list(MACHINE_DATA.keys()))}
            ]
            fin_route = r3.multiselect("Finishing Layout Line", list(MACHINE_DATA.keys()))
        else:
            type_id = ups 
            r1, r2 = st.columns(2)
            comp = [{"name": "Body", "impressions": max(1.0, order_qty/ups), "machines": r1.multiselect("Primary Print Asset Configuration", list(MACHINE_DATA.keys()))}]
            fin_route = r2.multiselect("Finishing Component Line Sequence", list(MACHINE_DATA.keys()))
        st.markdown('</div>', unsafe_allow_html=True)
        
    with col_sum:
        st.markdown('<div class="summary-box">', unsafe_allow_html=True)
        st.markdown("<p style='font-size:1.25rem; font-weight:700; margin-top:0;'>🚀 Deployment Controls</p>", unsafe_allow_html=True)
        start_date = st.date_input("Target Production Start Date", min_value=datetime.today().date())
        
        st.markdown("<hr style='border-color: rgba(255,255,255,0.1); margin: 1.5rem 0;'>", unsafe_allow_html=True)
        st.markdown(f"**Target Units:** {order_qty:,}")
        st.markdown(f"**Combined Value:** {CURRENCY}{total_val:,.2f}")
        
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("DISPATCH TO FINITE QUEUES", use_container_width=True):
            if job_name and fin_route and any(c['machines'] for c in comp):
                add_multi_part_job({
                    "name": job_name, "sales_rep": sales_rep, "total_qty": order_qty, 
                    "total_val": total_val, "start_date": start_date, "type_id": type_id, 
                    "components": comp, "finishing_machines": fin_route
                })
                st.success("Successfully injected into floor scheduling buffers!")
                st.rerun()
            else: 
                st.error("Validation failed: Please ensure all layout routing paths are assigned.")
        st.markdown('</div>', unsafe_allow_html=True)

with tab_control:
    df = get_db_jobs()
    if not df.empty:
        df['start_time'] = pd.to_datetime(df['start_time'], utc=True, format='mixed')
        df['finish_time'] = pd.to_datetime(df['finish_time'], utc=True, format='mixed')
        
        st.markdown('<div class="section-header">⌛ Master Production Queue Flowchart (Gantt Chart)</div>', unsafe_allow_html=True)
        
        # Build premium high-contrast Gantt chart tracking the layout
        fig = px.timeline(
            df, x_start="start_time", x_end="finish_time", y="machine", color="job_name", 
            hover_data=["tracking_id", "impressions"], template="plotly_white", 
            color_discrete_sequence=px.colors.qualitative.Tealrose
        )
        fig.update_layout(
            height=480, 
            margin=dict(t=15, b=15, l=10, r=10), 
            yaxis={'categoryorder':'category ascending', 'title': None},
            xaxis={'title': 'Shift Operational Timeline Horizon', 'gridcolor': '#f1f5f9'},
            legend=dict(title="Active Production Projects", orientation="h", y=1.12)
        )
        st.plotly_chart(fig, use_container_width=True)
        
        st.markdown('<div class="section-header">📦 Isolated Project Component Dispatches</div>', unsafe_allow_html=True)
        for tid, group in df.groupby('tracking_id'):
            job_title = group['job_name'].iloc[0].upper()
            
            with st.expander(f"⚙️ {job_title} — Allocation ID: {tid}"):
                d_df = group[['machine', 'impressions', 'start_time', 'finish_time']].copy()
                
                d_df['Capacity Target (Full Shift)'] = d_df['machine'].apply(
                    lambda x: f"{int((DAILY_CAPACITY_HOURS - MACHINE_DATA[x]['setup_hours']) * MACHINE_DATA[x]['rate']):,}"
                )
                
                d_df['start_time'] = d_df['start_time'].dt.strftime('%a %d %b, %H:%M')
                d_df['finish_time'] = d_df['finish_time'].dt.strftime('%a %d %b, %H:%M')
                
                # Format clean modern columns
                d_df.columns = ['Allocated Machine Asset', 'Expected Impressions Count', 'Scheduled Operational Start', 'Target Processing Finish', 'Calculated Daily Performance Target']
                st.dataframe(d_df, use_container_width=True, hide_index=True)
                
                # Destructive clean action bar
                c_void, c_act = st.columns([5, 1])
                if c_act.button(f"Scrap Component Run {tid}", key=f"scrap_{tid}", use_container_width=True, type="secondary"):
                    supabase.table('jobs').delete().eq('tracking_id', tid).execute()
                    st.rerun()
    else:
        st.info("No scheduled manufacturing runs are running on the factory shop floor.")
