import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import math

# Page configuration
st.set_page_config(
    page_title="Appointed Time Printing - Job Planning",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Machine data with impressions per hour (rate)
# All machines have fixed 2-hour setup time
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

SETUP_HOURS = 2.0  # Fixed setup time for all machines

# Initialize session state
if 'jobs' not in st.session_state:
    st.session_state.jobs = []
if 'monthly_budget' not in st.session_state:
    st.session_state.monthly_budget = 150000
if 'machine_load' not in st.session_state:
    st.session_state.machine_load = {machine: [] for machine in MACHINE_DATA.keys()}

# Helper functions
def calculate_impressions(finished_qty, ups, overs_pct):
    """Calculate total impressions using formula: ceil(Qty/Ups) × (1 + Overs%)"""
    base_impressions = math.ceil(finished_qty / ups)
    total_impressions = base_impressions * (1 + overs_pct / 100)
    return total_impressions

def calculate_processing_time(machine, impressions):
    """Calculate total time = setup (2h) + run time"""
    if machine not in MACHINE_DATA:
        return 0
    rate = MACHINE_DATA[machine]['rate']
    run_time = impressions / rate
    return SETUP_HOURS + run_time

def calculate_job_schedule(job_name, impressions, processes, start_time=None):
    """Calculate sequential schedule: each step starts when previous finishes"""
    if start_time is None:
        start_time = datetime.now()
    
    schedule = []
    current_time = start_time
    
    for process in processes:
        if process not in MACHINE_DATA:
            continue
        
        duration = calculate_processing_time(process, impressions)
        end_time = current_time + timedelta(hours=duration)
        
        schedule.append({
            'process': process,
            'start': current_time,
            'end': end_time,
            'duration': duration,
            'impressions': impressions
        })
        
        current_time = end_time
    
    return schedule

def add_job(job_name, sales_rep, impressions, processes, contract_value, target_deadline=None):
    """Add a new job to the system"""
    schedule = calculate_job_schedule(job_name, impressions, processes)
    
    calculated_finish = schedule[-1]['end'] if schedule else datetime.now()
    on_time = True if target_deadline is None else calculated_finish <= target_deadline
    
    job = {
        'name': job_name,
        'sales_rep': sales_rep,
        'impressions': impressions,
        'processes': processes,
        'contract_value': contract_value,
        'schedule': schedule,
        'target_deadline': target_deadline,
        'calculated_finish': calculated_finish,
        'on_time': on_time,
        'created_at': datetime.now()
    }
    
    st.session_state.jobs.append(job)
    
    # Update machine load
    for task in schedule:
        process = task['process']
        st.session_state.machine_load[process].append({
            'job': job_name,
            'impressions': impressions,
            'start': task['start'],
            'end': task['end'],
            'duration': task['duration']
        })
    
    return job

def get_machine_status_color(machine):
    """Determine stoplight color based on machine load:
    Green: 0 hours
    Yellow: 0 < load < 2 hours
    Red: load >= 24 hours
    """
    total_load = 0
    for job_load in st.session_state.machine_load[machine]:
        total_load += job_load['duration']
    
    if total_load == 0:
        return "Green", "🟢"
    elif total_load < 2:
        return "Yellow", "🟡"
    else:
        return "Red", "🔴"

# Sidebar navigation
st.sidebar.title("Appointed Time Printing")
st.sidebar.markdown("---")

page = st.sidebar.radio("Navigate", ["Dashboard", "Plan Job", "Gantt View"])

# Dynamic sales rep filter
sales_reps = sorted(list(set([job['sales_rep'] for job in st.session_state.jobs])))
if page in ["Dashboard", "Gantt View"]:
    selected_rep = st.sidebar.selectbox(
        "Filter by Sales Rep",
        ["All"] + sales_reps if sales_reps else ["All"]
    )
else:
    selected_rep = "All"

st.sidebar.markdown("---")

# Monthly budget configuration
st.sidebar.markdown("### Financial Setup")
monthly_budget = st.sidebar.number_input(
    "Monthly Budget Target ($)",
    value=st.session_state.monthly_budget,
    min_value=10000,
    step=10000
)
st.session_state.monthly_budget = monthly_budget

# PAGE 1: DASHBOARD
if page == "Dashboard":
    st.title("Global Production View")
    st.markdown("Real-time machine status and production analytics")
    
    # Financial summary
    total_revenue = sum(job['contract_value'] for job in st.session_state.jobs)
    revenue_gap = st.session_state.monthly_budget - total_revenue
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            "Projected Revenue",
            f"${total_revenue:,.0f}",
            delta=f"${revenue_gap:,.0f} gap",
            delta_color="inverse"
        )
    with col2:
        st.metric("Budget Target", f"${st.session_state.monthly_budget:,.0f}")
    with col3:
        pct_of_budget = (total_revenue / st.session_state.monthly_budget * 100) if st.session_state.monthly_budget > 0 else 0
        st.metric("Budget %", f"{pct_of_budget:.1f}%")
    
    st.markdown("---")
    
    # On-Time Delivery %
    if st.session_state.jobs:
        on_time_jobs = sum(1 for job in st.session_state.jobs if job['on_time'])
        total_jobs = len(st.session_state.jobs)
        otd = (on_time_jobs / total_jobs * 100)
        
        st.metric("On-Time Delivery %", f"{otd:.1f}%")
    
    st.markdown("---")
    
    # Stoplight System - Machine Status Table
    st.markdown("### Stoplight System - Machine Status")
    
    stoplight_data = []
    for machine in sorted(MACHINE_DATA.keys()):
        status_color, symbol = get_machine_status_color(machine)
        
        total_load = sum(job['duration'] for job in st.session_state.machine_load[machine])
        job_count = len(st.session_state.machine_load[machine])
        
        stoplight_data.append({
            'Status': f"{symbol} {status_color}",
            'Machine': machine,
            'Rate (imp/hr)': MACHINE_DATA[machine]['rate'],
            'Load (hours)': f"{total_load:.1f}",
            'Jobs': job_count
        })
    
    df_stoplight = pd.DataFrame(stoplight_data)
    st.dataframe(df_stoplight, use_container_width=True, hide_index=True)
    
    st.markdown("---")
    
    # Production table
    if st.session_state.jobs:
        st.markdown("### Production Schedule")
        
        jobs_to_display = st.session_state.jobs
        if selected_rep != "All":
            jobs_to_display = [job for job in st.session_state.jobs if job['sales_rep'] == selected_rep]
        
        if jobs_to_display:
            production_data = []
            for job in jobs_to_display:
                status = "✅ On-Time" if job['on_time'] else "❌ Late"
                production_data.append({
                    'Job Name': job['name'],
                    'Sales Rep': job['sales_rep'],
                    'Start': job['schedule'][0]['start'].strftime('%m/%d %H:%M') if job['schedule'] else 'N/A',
                    'Realistic Finish': job['calculated_finish'].strftime('%m/%d %H:%M'),
                    'Status': status,
                    'Revenue': f"${job['contract_value']:,.0f}"
                })
            
            st.dataframe(pd.DataFrame(production_data), use_container_width=True, hide_index=True)

# PAGE 2: PLAN JOB
elif page == "Plan Job":
    st.title("Plan New Job")
    st.markdown("Create a job with skillet math and scheduling")
    
    with st.form("job_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            job_name = st.text_input("Job Name", placeholder="e.g., Acme Corp Brochures")
            sales_rep = st.selectbox(
                "Sales Rep",
                ["John Smith", "Sarah Johnson", "Mike Davis", "Emma Wilson", "Other"]
            )
            if sales_rep == "Other":
                sales_rep = st.text_input("Enter Sales Rep Name")
        
        with col2:
            contract_value = st.number_input("Contract Value ($)", min_value=100, value=5000, step=100)
            target_deadline = st.date_input("Target Delivery Date (Optional)", value=None)
        
        st.markdown("---")
        st.markdown("### Skillet Math Calculation")
        st.markdown("**Formula:** Impressions = ⌈Quantity ÷ Ups⌉ × (1 + Overs%)")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            finished_qty = st.number_input("Finished Quantity", min_value=100, value=100000, step=1000)
        with col2:
            ups = st.number_input("Ups-per-Sheet", min_value=1, value=12, step=1)
        with col3:
            overs_pct = st.number_input("Overs %", min_value=0.0, value=5.0, step=0.5)
        with col4:
            st.write("")  # Spacer
        
        # Calculate impressions
        impressions = calculate_impressions(finished_qty, ups, overs_pct)
        st.info(f"**Calculated Impressions:** {impressions:,.0f}")
        
        st.markdown("---")
        st.markdown("### Production Sequence")
        
        available_processes = sorted(list(MACHINE_DATA.keys()))
        selected_processes = []
        
        cols = st.columns(3)
        for idx, process in enumerate(available_processes):
            col = cols[idx % 3]
            if col.checkbox(process):
                selected_processes.append(process)
        
        submitted = st.form_submit_button("Create Job & Schedule", use_container_width=True)
        
        if submitted:
            if not job_name or not sales_rep or not selected_processes:
                st.error("Please fill in all fields and select at least one process")
            else:
                target_dt = None
                if target_deadline:
                    target_dt = datetime.combine(target_deadline, datetime.min.time())
                
                job = add_job(job_name, sales_rep, impressions, selected_processes, contract_value, target_dt)
                st.success(f"Job '{job_name}' created!")
                
                # Display schedule
                st.markdown("### Job Schedule")
                schedule_data = []
                for idx, task in enumerate(job['schedule']):
                    schedule_data.append({
                        'Step': idx + 1,
                        'Process': task['process'],
                        'Start': task['start'].strftime('%Y-%m-%d %H:%M'),
                        'Finish': task['end'].strftime('%Y-%m-%d %H:%M'),
                        'Duration (hours)': f"{task['duration']:.2f}"
                    })
                
                st.dataframe(pd.DataFrame(schedule_data), use_container_width=True, hide_index=True)
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    total_time = sum(t['duration'] for t in job['schedule'])
                    st.metric("Total Time", f"{total_time:.2f}h")
                with col2:
                    st.metric("Calculated Finish", job['calculated_finish'].strftime('%m/%d %H:%M'))
                with col3:
                    st.metric("Contract Value", f"${job['contract_value']:,.0f}")
                with col4:
                    status = "✅ On-Time" if job['on_time'] else "❌ Late"
                    st.metric("Deadline Status", status)

# PAGE 3: GANTT VIEW
elif page == "Gantt View":
    st.title("Gantt Chart - Job Visualization")
    st.markdown("Interactive timeline of job flow through machines")
    
    if not st.session_state.jobs:
        st.warning("No jobs created yet. Go to 'Plan Job' to create a job.")
    else:
        jobs_to_display = st.session_state.jobs
        if selected_rep != "All":
            jobs_to_display = [job for job in st.session_state.jobs if job['sales_rep'] == selected_rep]
        
        if not jobs_to_display:
            st.info(f"No jobs for {selected_rep}")
        else:
            job_names = [job['name'] for job in jobs_to_display]
            selected_job_name = st.selectbox("Select Job", job_names)
            
            selected_job = next((job for job in jobs_to_display if job['name'] == selected_job_name), None)
            
            if selected_job:
                # Gantt chart
                fig = go.Figure()
                
                colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
                
                for idx, task in enumerate(selected_job['schedule']):
                    color = colors[idx % len(colors)]
                    fig.add_trace(go.Bar(
                        x=[task['duration']],
                        y=[task['process']],
                        orientation='h',
                        name=task['process'],
                        marker=dict(color=color),
                        base=task['start'],
                        hovertemplate=f"<b>{task['process']}</b><br>Start: %{{base|%Y-%m-%d %H:%M}}<br>Duration: {task['duration']:.2f}h<extra></extra>"
                    ))
                
                # Add target deadline line if present
                if selected_job['target_deadline']:
                    fig.add_vline(
                        x=selected_job['target_deadline'],
                        line_dash="dash",
                        line_color="red",
                        annotation_text="Target",
                        annotation_position="top right"
                    )
                
                fig.update_layout(
                    title=f"{selected_job['name']} - Finish: {selected_job['calculated_finish'].strftime('%Y-%m-%d %H:%M')}",
                    xaxis_title="Timeline",
                    yaxis_title="Process",
                    barmode='overlay',
                    height=500,
                    showlegend=False,
                    hovermode='closest'
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
                # Job details
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Job Name", selected_job['name'][:20])
                with col2:
                    st.metric("Sales Rep", selected_job['sales_rep'])
                with col3:
                    st.metric("Impressions", f"{selected_job['impressions']:,.0f}")
                with col4:
                    st.metric("Revenue", f"${selected_job['contract_value']:,.0f}")
