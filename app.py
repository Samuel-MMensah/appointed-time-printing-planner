import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
import math
import random
from supabase import create_client, Client
import plotly.express as px
import plotly.graph_objects as go

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(page_title="Appointed Time | Elite ERP", layout="wide", page_icon="🏢")

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

# --- 3. ELITE CSS STYLING ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    
    .stApp { background-color: #fcfcfd; }
    
    /* Stats Cards */
    .metric-card {
        background: white;
        padding: 24px;
        border-radius: 16px;
        border: 1px solid #edf2f7;
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);
        text-align: center;
    }
    .metric-value { font-size: 28px; font-weight: 700; color: #1a202c; }
    .metric-label { font-size: 14px; color: #718096; text-transform: uppercase; letter-spacing: 1px; }

    /* Production Cards */
    .prod-card {
        background: white;
        border-left: 5px solid #2563eb;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.02);
    }
    
    /* Section Headers */
    .section-header {
        font-size: 20px;
        font-weight: 700;
        color: #1e293b;
        margin-bottom: 20px;
        border-bottom: 2px solid #e2e8f0;
        padding-bottom: 8px;
    }
    </style>
    """, unsafe_allow_html=True)

@st.cache_resource
def init_supabase():
    try: return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except: return None

supabase: Client = init_supabase()

# --- 4. DATA ENGINE ---
def get_db_jobs():
    if not supabase: return pd.DataFrame()
    res = supabase.table('jobs').select("*").execute()
    return pd.DataFrame(res.data)

def add_multi_part_job(job_data):
    tid = f"JOB-{random.randint(1000, 9999)}"
    comp_finish_times = []
    total_stages = sum(len(c['machines']) for c in job_data['components']) + len(job_data['finishing_machines'])
    val_per_stage = job_data['total_val'] / total_stages if total_stages > 0 else 0

    for comp in job_data['components']:
        if not comp['machines']: continue
        comp_start = datetime.combine(job_data['start_date'], datetime.now().time()).replace(tzinfo=timezone.utc)
        for machine in comp['machines']:
            dur = SETUP_HOURS + (comp['impressions'] / MACHINE_DATA[machine]['rate'])
            # Note: calculate_finish logic remains standard
            finish = comp_start + timedelta(hours=dur) # Simplified for UI focus
            
            supabase.table('jobs').insert({
                "job_name": job_data['name'], "tracking_id": tid, "machine": machine,
                "sales_rep": job_data['sales_rep'], "quantity": int(job_data['total_qty']),
                "ups": int(job_data['type_id']), # Storing category type here
                "impressions": int(comp['impressions']), "start_time": comp_start.isoformat(), 
                "finish_time": finish.isoformat(), "contract_value": float(val_per_stage),
                "net_profit": 0, "material_costs": 0, "overhead_rate": 0
            }).execute()
            comp_start = finish
        comp_finish_times.append(comp_start)

    if job_data['finishing_machines']:
        finish_start = max(comp_finish_times)
        for f_mach in job_data['finishing_machines']:
            f_dur = SETUP_HOURS + (job_data['total_qty'] / MACHINE_DATA[f_mach]['rate'])
            f_finish = finish_start + timedelta(hours=f_dur)
            supabase.table('jobs').insert({
                "job_name": job_data['name'], "tracking_id": tid, "machine": f_mach,
                "sales_rep": job_data['sales_rep'], "quantity": int(job_data['total_qty']),
                "ups": int(job_data['type_id']), "impressions": int(job_data['total_qty']),
                "start_time": finish_start.isoformat(), "finish_time": f_finish.isoformat(),
                "contract_value": float(val_per_stage), "net_profit": 0, "material_costs": 0, "overhead_rate": 0
            }).execute()
            finish_start = f_finish
    return tid

# --- 5. UI LAYOUT ---
tab_dash, tab_plan, tab_control = st.tabs(["🏛️ COMMAND CENTER", "⚙️ PRODUCTION PLANNER", "📅 SHOP FLOOR CONTROL"])

# --- TAB 1: COMMAND CENTER (Redesigned Dashboard) ---
with tab_dash:
    df = get_db_jobs()
    if not df.empty:
        df['start_time'] = pd.to_datetime(df['start_time'], format='ISO8601', utc=True)
        df['finish_time'] = pd.to_datetime(df['finish_time'], format='ISO8601', utc=True)
        
        # High-Level Metrics
        c1, c2, c3, c4 = st.columns(4)
        with c1: st.markdown(f'<div class="metric-card"><div class="metric-label">Active Jobs</div><div class="metric-value">{df["job_name"].nunique()}</div></div>', unsafe_allow_html=True)
        with c2: st.markdown(f'<div class="metric-card"><div class="metric-label">Pipeline Value</div><div class="metric-value">{CURRENCY}{df["contract_value"].sum():,.0f}</div></div>', unsafe_allow_html=True)
        with c3: 
            books_count = df[df['ups'] == 1]['job_name'].nunique()
            st.markdown(f'<div class="metric-card"><div class="metric-label">Book Projects</div><div class="metric-value">{books_count}</div></div>', unsafe_allow_html=True)
        with c4:
            skillets_count = df[df['ups'] == 2]['job_name'].nunique()
            st.markdown(f'<div class="metric-card"><div class="metric-label">Skillet Jobs</div><div class="metric-value">{skillets_count}</div></div>', unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        col_left, col_right = st.columns([2, 1])
        with col_left:
            st.markdown('<p class="section-header">Machine Load Analysis</p>', unsafe_allow_html=True)
            load = df.groupby('machine').size().reset_index(name='Queue')
            fig_load = px.bar(load, x='machine', y='Queue', color='Queue', color_continuous_scale='Blues')
            fig_load.update_layout(showlegend=False, height=350, margin=dict(t=10, b=10, l=10, r=10))
            st.plotly_chart(fig_load, use_container_width=True)
            
        with col_right:
            st.markdown('<p class="section-header">Revenue by Category</p>', unsafe_allow_html=True)
            cat_data = df.groupby('ups')['contract_value'].sum().reset_index()
            cat_data['Category'] = cat_data['ups'].map({1: 'Books/Manuals', 2: 'Skillets/Flyers'})
            fig_pie = px.pie(cat_data, values='contract_value', names='Category', hole=.6, color_discrete_sequence=['#2563eb', '#60a5fa'])
            fig_pie.update_layout(height=350, margin=dict(t=10, b=10, l=10, r=10), showlegend=False)
            st.plotly_chart(fig_pie, use_container_width=True)

# --- TAB 2: PRODUCTION PLANNER (Product Choice Integration) ---
with tab_plan:
    st.markdown('<p class="section-header">New Production Simulation</p>', unsafe_allow_html=True)
    
    with st.container():
        st.markdown('<div class="component-card">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([2, 1, 1])
        job_name = c1.text_input("Project Name / Description", placeholder="e.g. 50,000 Pharma Skillets")
        sales_rep = c2.selectbox("Account Manager", ["Mabel Ampofo", "Daphne Sarpong", "Elizabeth Akoto", "Charles Adoo", "Christian Mante", "Bertha Tackie", "Reginald Aidam"])
        prod_cat = c3.selectbox("Product Category", ["📚 Book / Brochure", "📦 Skillet / Box", "📄 Flyer / Leaflet"])
        st.markdown('</div>', unsafe_allow_html=True)

    col_cfg, col_summ = st.columns([2, 1])
    
    with col_cfg:
        # Step-based entry
        st.markdown("#### 1. Material & Quantity")
        cc1, cc2, cc3 = st.columns(3)
        order_qty = cc1.number_input("Total Order Quantity", value=1000, step=500)
        total_val = cc2.number_input("Contract Value (GH₵)", value=5000.0)
        
        # Logic change based on category
        if "Book" in prod_cat:
            type_id = 1
            ups = cc3.number_input("Ups per Sheet (Cover)", value=2)
            pages = st.number_input("Total Text Pages", value=64)
            sig_size = st.selectbox("Signature Size", [8, 16, 32], index=1)
            text_impressions = math.ceil(pages / sig_size) * order_qty
        else:
            type_id = 2
            ups = cc3.number_input("Ups per Sheet", value=12)
            text_impressions = 0 # Not used for skillets

        st.markdown("#### 2. Workflow Routing")
        if "Book" in prod_cat:
            r1, r2, r3 = st.columns(3)
            cov_route = r1.multiselect("Cover Press", list(MACHINE_DATA.keys()))
            txt_route = r2.multiselect("Text Press", list(MACHINE_DATA.keys()))
            fin_route = r3.multiselect("Finishing/Binding", list(MACHINE_DATA.keys()))
            components = [
                {"name": "Cover", "impressions": order_qty/ups, "machines": cov_route},
                {"name": "Text", "impressions": text_impressions, "machines": txt_route}
            ]
        else:
            r1, r2 = st.columns(2)
            print_route = r1.multiselect("Printing Press", list(MACHINE_DATA.keys()))
            fin_route = r2.multiselect("Finishing (Diecut/Glue)", list(MACHINE_DATA.keys()))
            components = [{"name": "Body", "impressions": order_qty/ups, "machines": print_route}]

    with col_summ:
        st.markdown('<div class="profit-panel">', unsafe_allow_html=True)
        st.markdown("#### Scheduling")
        start_date = st.date_input("Target Start Date")
        st.write(f"**Category:** {prod_cat}")
        st.write(f"**Est. Press Run:** {int(order_qty/ups):,} impressions")
        st.markdown('</div>', unsafe_allow_html=True)
        
        if st.button("🚀 Push to Shop Floor", use_container_width=True):
            if job_name:
                payload = {
                    "name": job_name, "sales_rep": sales_rep, "total_qty": order_qty, "total_val": total_val,
                    "start_date": start_date, "type_id": type_id, "night": False, "weekend": False,
                    "components": components, "finishing_machines": fin_route
                }
                add_multi_part_job(payload)
                st.balloons()
                st.rerun()

# --- TAB 3: SHOP FLOOR CONTROL ---
with tab_control:
    df = get_db_jobs()
    if not df.empty:
        df['start_time'] = pd.to_datetime(df['start_time'], format='ISO8601', utc=True)
        df['finish_time'] = pd.to_datetime(df['finish_time'], format='ISO8601', utc=True)
        
        # Gantt
        fig = px.timeline(df, x_start="start_time", x_end="finish_time", y="machine", color="job_name", 
                          template="plotly_white", color_discrete_sequence=px.colors.qualitative.Prism)
        fig.update_layout(height=400, margin=dict(t=0, b=0))
        st.plotly_chart(fig, use_container_width=True)
        
        st.markdown('<p class="section-header">Live Production Queue</p>', unsafe_allow_html=True)
        for job_name, group in df.groupby('job_name'):
            with st.expander(f"📦 {job_name.upper()} | Sales: {group['sales_rep'].iloc[0]}"):
                st.table(group[['machine', 'impressions', 'start_time', 'finish_time']].assign(
                    start_time=lambda x: x['start_time'].dt.strftime('%d %b, %H:%M'),
                    finish_time=lambda x: x['finish_time'].dt.strftime('%d %b, %H:%M')
                ))
                if st.button("Delete Job", key=f"del_{job_name}"):
                    supabase.table('jobs').delete().eq('job_name', job_name).execute()
                    st.rerun()
