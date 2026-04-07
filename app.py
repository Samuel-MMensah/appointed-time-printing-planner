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

# --- 3. ENHANCED ELITE CSS STYLING ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    
    .stApp { background-color: #f8fafc; }
    
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

    /* Production Planner Glassmorphism */
    .planner-card {
        background: white;
        padding: 2rem;
        border-radius: 20px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1);
        margin-bottom: 20px;
    }

    /* Shop Floor Status Badges */
    .badge {
        padding: 4px 12px;
        border-radius: 50px;
        font-size: 12px;
        font-weight: 600;
        text-transform: uppercase;
    }
    .badge-running { background-color: #dcfce7; color: #166534; border: 1px solid #bbf7d0; }
    .badge-waiting { background-color: #fef9c3; color: #854d0e; border: 1px solid #fef08a; }

    /* Custom Headers */
    .section-header {
        font-size: 22px;
        font-weight: 800;
        color: #0f172a;
        margin: 25px 0 15px 0;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    
    /* Summary Panel */
    .summary-box {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        color: white;
        padding: 25px;
        border-radius: 20px;
        position: sticky;
        top: 20px;
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
            finish = comp_start + timedelta(hours=dur)
            
            supabase.table('jobs').insert({
                "job_name": job_data['name'], "tracking_id": tid, "machine": machine,
                "sales_rep": job_data['sales_rep'], "quantity": int(job_data['total_qty']),
                "ups": int(job_data['type_id']), 
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

# --- TAB 1: COMMAND CENTER ---
with tab_dash:
    df = get_db_jobs()
    if not df.empty:
        df['start_time'] = pd.to_datetime(df['start_time'], format='ISO8601', utc=True)
        df['finish_time'] = pd.to_datetime(df['finish_time'], format='ISO8601', utc=True)
        
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
        col_left, col_right = st.columns([1.5, 1])
        
        with col_left:
            st.markdown('<p class="section-header">🥇 Top 5 Jobs by Revenue</p>', unsafe_allow_html=True)
            top_jobs = df.groupby('job_name')['contract_value'].sum().sort_values(ascending=True).tail(5).reset_index()
            fig_top = px.bar(top_jobs, y='job_name', x='contract_value', orientation='h', 
                             text_auto='.2s', color='contract_value', color_continuous_scale='Blues')
            fig_top.update_layout(showlegend=False, height=400, margin=dict(t=10, b=10, l=10, r=10), 
                                 xaxis_title="Revenue (GH₵)", yaxis_title=None,
                                 paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_top, use_container_width=True)

        with col_right:
            st.markdown('<p class="section-header">🍕 Revenue by Category</p>', unsafe_allow_html=True)
            cat_data = df.groupby('ups')['contract_value'].sum().reset_index()
            cat_data['Category'] = cat_data['ups'].map({1: 'Books/Manuals', 2: 'Skillets/Boxes'})
            fig_pie = px.pie(cat_data, values='contract_value', names='Category', hole=.5,
                             color_discrete_sequence=['#2563eb', '#93c5fd'])
            fig_pie.update_traces(textposition='outside', textinfo='percent+label')
            fig_pie.update_layout(height=400, margin=dict(t=30, b=30, l=30, r=30), 
                                 showlegend=False, paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_pie, use_container_width=True)

# --- TAB 2: PRODUCTION PLANNER ---
with tab_plan:
    st.markdown('<p class="section-header">🛠️ Project Specification Architecture</p>', unsafe_allow_html=True)
    col_input, col_summ = st.columns([2.2, 1])
    
    with col_input:
        st.markdown('<div class="planner-card">', unsafe_allow_html=True)
        st.markdown("##### 🟢 Step 1: Identity & Classification")
        c1, c2, c3 = st.columns([2, 1, 1])
        job_name = c1.text_input("Project Description", placeholder="Enter unique job name...")
        sales_rep = c2.selectbox("Account Manager", ["Mabel Ampofo", "Daphne Sarpong", "Elizabeth Akoto", "Charles Adoo", "Christian Mante", "Bertha Tackie", "Reginald Aidam"])
        prod_cat = c3.selectbox("Work Type", ["📚 Book / Brochure", "📦 Skillet / Box", "📄 Flyer / Leaflet"])
        
        st.divider()
        st.markdown("##### 🔵 Step 2: Dimensional Specs")
        cc1, cc2, cc3 = st.columns(3)
        order_qty = cc1.number_input("Total Units", value=1000, step=500)
        total_val = cc2.number_input("Project Value (GH₵)", value=5000.0)
        
        if "Book" in prod_cat:
            type_id = 1
            ups = cc3.number_input("Cover Ups", value=2)
            p1, p2 = st.columns(2)
            pages = p1.number_input("Page Count", value=64)
            sig_size = p2.selectbox("Signature Breakdown", [8, 16, 32], index=1)
            text_impressions = math.ceil(pages / sig_size) * order_qty
        else:
            type_id = 2
            ups = cc3.number_input("Items Per Sheet", value=12)
            text_impressions = 0

        st.divider()
        st.markdown("##### 🟣 Step 3: Workflow Routing")
        if "Book" in prod_cat:
            r1, r2, r3 = st.columns(3)
            cov_route = r1.multiselect("Press: Cover", list(MACHINE_DATA.keys()))
            txt_route = r2.multiselect("Press: Text", list(MACHINE_DATA.keys()))
            fin_route = r3.multiselect("Binding Line", list(MACHINE_DATA.keys()))
            components = [
                {"name": "Cover", "impressions": order_qty/ups, "machines": cov_route},
                {"name": "Text", "impressions": text_impressions, "machines": txt_route}
            ]
        else:
            r1, r2 = st.columns(2)
            print_route = r1.multiselect("Printing Line", list(MACHINE_DATA.keys()))
            fin_route = r2.multiselect("Finishing Line", list(MACHINE_DATA.keys()))
            components = [{"name": "Body", "impressions": order_qty/ups, "machines": print_route}]
        st.markdown('</div>', unsafe_allow_html=True)

    with col_summ:
        st.markdown('<div class="summary-box">', unsafe_allow_html=True)
        st.markdown("### 📋 Run Estimate")
        st.markdown(f"**Target Start:** {datetime.now().strftime('%Y-%m-%d')}")
        st.markdown(f"**Est. Impressions:** {int(order_qty/ups + (text_impressions if 'Book' in prod_cat else 0)):,}")
        st.markdown(f"**Stages:** {len(fin_route) + (len(cov_route)+len(txt_route) if 'Book' in prod_cat else len(print_route))}")
        st.divider()
        start_date = st.date_input("Deployment Date")
        if st.button("🚀 Push to Production", use_container_width=True):
            if job_name:
                payload = {"name": job_name, "sales_rep": sales_rep, "total_qty": order_qty, "total_val": total_val, "start_date": start_date, "type_id": type_id, "components": components, "finishing_machines": fin_route}
                add_multi_part_job(payload)
                st.toast("Job Dispatched Successfully!", icon="🏭")
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

# --- TAB 3: SHOP FLOOR CONTROL (Updated with Collapse/Expand) ---
with tab_control:
    df = get_db_jobs()
    if not df.empty:
        df['start_time'] = pd.to_datetime(df['start_time'], format='ISO8601', utc=True)
        df['finish_time'] = pd.to_datetime(df['finish_time'], format='ISO8601', utc=True)
        
        st.markdown('<p class="section-header">⌛ Real-Time Timeline</p>', unsafe_allow_html=True)
        fig = px.timeline(df, x_start="start_time", x_end="finish_time", y="machine", color="job_name", 
                          template="plotly_white", color_discrete_sequence=px.colors.qualitative.Bold)
        fig.update_layout(height=400, margin=dict(t=0, b=0), paper_bgcolor='rgba(0,0,0,0)', showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
        
        st.markdown('<p class="section-header">📋 Detailed Production Queue</p>', unsafe_allow_html=True)
        
        for job_name, group in df.groupby('job_name'):
            # Using st.expander to provide collapse/expand functionality
            with st.expander(f"📦 {job_name.upper()} | Status: IN PRODUCTION", expanded=False):
                display_df = group[['machine', 'impressions', 'start_time', 'finish_time']].copy()
                display_df['start_time'] = display_df['start_time'].dt.strftime('%d %b, %H:%M')
                display_df['finish_time'] = display_df['finish_time'].dt.strftime('%d %b, %H:%M')
                
                st.dataframe(display_df, use_container_width=True, hide_index=True)
                
                col_actions = st.columns([6, 1])
                if col_actions[1].button("🗑️ Scrap Job", key=f"del_{job_name}", use_container_width=True):
                    supabase.table('jobs').delete().eq('job_name', job_name).execute()
                    st.rerun()
