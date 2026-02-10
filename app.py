import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import json

# Page configuration
st.set_page_config(
    page_title="Appointed Time Printing - Job Planning",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Machine data with performance parameters and revenue
MACHINE_DATA = {
    'SM102-CX FOUR COLOUR': {'rate_per_hour': 8000, 'setup_hours': 1.5, 'rev_per_1k': 25},
    'SM102-P FIVE COLOUR': {'rate_per_hour': 7500, 'setup_hours': 1.5, 'rev_per_1k': 30},
    'SM 52': {'rate_per_hour': 7000, 'setup_hours': 1.5, 'rev_per_1k': 15},
    'GTO 52 SEMI-AUTO-2 COLOUR': {'rate_per_hour': 4500, 'setup_hours': 1.5, 'rev_per_1k': 12},
    'GTO 52 MANUAL-2 COLOUR': {'rate_per_hour': 4000, 'setup_hours': 2.0, 'rev_per_1k': 10},
    'FOLDING UNIT CONTINUOUS FOLD': {'rate_per_hour': 8000, 'setup_hours': 1.5, 'rev_per_1k': 5},
    'MBO-B30E SINGLE FOLD': {'rate_per_hour': 16000, 'setup_hours': 1.5, 'rev_per_1k': 4},
    'POLAR MACHINE FOR BOOKS': {'rate_per_hour': 2000, 'setup_hours': 1.0, 'rev_per_1k': 8},
    'POLAR MACHINE FOR SHEETS': {'rate_per_hour': 50000, 'setup_hours': 1.0, 'rev_per_1k': 2},
    '3 WAY TRIMMER': {'rate_per_hour': 5000, 'setup_hours': 1.0, 'rev_per_1k': 6},
    'PERFECT BINDING': {'rate_per_hour': 500, 'setup_hours': 1.5, 'rev_per_1k': 50},
    'LAMINATION UNIT': {'rate_per_hour': 2500, 'setup_hours': 1.5, 'rev_per_1k': 20},
    'PEDDLER SADDLE STITCH': {'rate_per_hour': 1000, 'setup_hours': 1.5, 'rev_per_1k': 35},
    'DIE CUTTER': {'rate_per_hour': 3000, 'setup_hours': 1.5, 'rev_per_1k': 22},
    'FOLDER GLUER': {'rate_per_hour': 12000, 'setup_hours': 1.5, 'rev_per_1k': 12},
}

# Financial settings
MONTHLY_BUDGET_TARGET = 150000

# Initialize session state
if 'jobs' not in st.session_state:
    st.session_state.jobs = []
if 'machine_load' not in st.session_state:
    st.session_state.machine_load = {machine: [] for machine in MACHINE_DATA.keys()}
if 'total_run_time' not in st.session_state:
    st.session_state.total_run_time = 0
if 'total_machine_time' not in st.session_state:
    st.session_state.total_machine_time = 0

# Helper functions
def calculate_impressions(finished_qty, ups_per_sheet, overs_pct):
    """Calculate total impressions from finished quantity, ups, and overs%
    Formula: Impressions = (Finished Qty / Ups) × (1 + Overs%)
    """
    impressions = (finished_qty / ups_per_sheet) * (1 + overs_pct / 100)
    return impressions

def calculate_packets(impressions, sheets_per_packet):
    """Calculate number of packets needed
    Formula: Packets = Impressions / Sheets-per-Packet
    """
    return impressions / sheets_per_packet

def calculate_setup_time(impressions):
    """Calculate setup time based on impressions
    Default: 1.5 hours, or 2 hours if impressions > 100,000
    """
    return 2.0 if impressions > 100000 else 1.5

def calculate_processing_time(machine, impressions, custom_setup=None):
    """Calculate total processing time in hours (setup + run time)"""
    if machine not in MACHINE_DATA:
        return 0
    data = MACHINE_DATA[machine]
    setup_time = custom_setup if custom_setup is not None else calculate_setup_time(impressions)
    run_time = impressions / data['rate_per_hour']
    return setup_time + run_time

def calculate_job_revenue(schedule):
    """Calculate total revenue for a job based on machine rates and impressions"""
    total_revenue = 0
    for task in schedule:
        process = task['process']
        impressions = task['impressions']
        if process in MACHINE_DATA:
            rev_per_1k = MACHINE_DATA[process]['rev_per_1k']
            total_revenue += (impressions / 1000) * rev_per_1k
    return total_revenue

def get_machine_status(machine, current_time):
    """Determine machine status: Green (Available), Yellow (<2 hours), Red (>24 hours)"""
    total_load = sum(MACHINE_DATA[machine]['setup_hours'] + 
                     job['impressions'] / MACHINE_DATA[machine]['rate_per_hour']
                     for job in st.session_state.machine_load[machine])
    
    if total_load == 0:
        return "🟢 Available", "green"
    elif total_load < 2:
        return "🟡 Finishing Soon (<2h)", "orange"
    else:
        return "🔴 Booked (>24h)", "red"

def calculate_job_schedule(job_name, sales_rep, impressions, processes, start_time=None, target_deadline=None):
    """Calculate the complete schedule for a job through all processes with ripple effect"""
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
            'job': job_name,
            'process': process,
            'start': current_time,
            'end': end_time,
            'duration': duration,
            'impressions': impressions
        })
        
        current_time = end_time
    
    return schedule

def add_job(job_name, sales_rep, impressions, processes, target_deadline=None):
    """Add a new job to the system"""
    schedule = calculate_job_schedule(job_name, sales_rep, impressions, processes, target_deadline=target_deadline)
    
    job = {
        'name': job_name,
        'sales_rep': sales_rep,
        'impressions': impressions,
        'processes': processes,
        'schedule': schedule,
        'target_deadline': target_deadline,
        'created_at': datetime.now(),
        'on_time': True if target_deadline is None else schedule[-1]['end'] <= target_deadline,
        'revenue': calculate_job_revenue(schedule)
    }
    
    st.session_state.jobs.append(job)
    
    # Update machine load and efficiency metrics
    for task in schedule:
        process = task['process']
        st.session_state.machine_load[process].append({
            'job': job_name,
            'impressions': impressions,
            'start': task['start'],
            'end': task['end']
        })
        st.session_state.total_machine_time += task['duration']
    
    st.session_state.total_run_time += sum(task['duration'] for task in schedule)
    
    return job

# Sidebar navigation
st.sidebar.title("📋 Appointed Time Printing")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navigate",
    ["Dashboard", "Plan Job", "Gantt View"]
)

# Filter by sales rep in sidebar
if page in ["Dashboard", "Gantt View"]:
    sales_reps = list(set([job['sales_rep'] for job in st.session_state.jobs]))
    if sales_reps:
        selected_rep = st.sidebar.selectbox("Filter by Sales Rep", ["All"] + sales_reps)
    else:
        selected_rep = "All"
        st.sidebar.info("No jobs created yet.")
else:
    selected_rep = "All"

st.sidebar.markdown("---")

# PAGE 1: DASHBOARD - Global Production View
if page == "Dashboard":
    st.title("🏭 Global Production View - Stoplight System")
    st.markdown("Real-time machine status, financial metrics, and efficiency analytics")
    
    # Financial Metrics
    st.markdown("### 💰 Financial Metrics")
    total_revenue = sum(job.get('revenue', 0) for job in st.session_state.jobs)
    revenue_gap = MONTHLY_BUDGET_TARGET - total_revenue
    gap_color = "🟢" if revenue_gap <= 0 else "🟡" if revenue_gap < MONTHLY_BUDGET_TARGET * 0.2 else "🔴"
    
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        st.metric("Projected Monthly Revenue", f"${total_revenue:,.0f}")
    with col2:
        st.metric("Budgeted Target", f"${MONTHLY_BUDGET_TARGET:,.0f}")
    with col3:
        st.metric(f"{gap_color} Revenue Gap", f"${max(0, revenue_gap):,.0f}")
    
    # Efficiency Metrics
    st.markdown("### 📊 Efficiency Metrics")
    
    # Calculate efficiency: Run Time / Total Time (including setup)
    total_run_time = sum(job['impressions'] / MACHINE_DATA[process]['rate_per_hour'] 
                        for job in st.session_state.jobs 
                        for process in job['processes'] 
                        if process in MACHINE_DATA)
    total_setup_time = sum(calculate_setup_time(job['impressions']) * len(job['processes']) 
                          for job in st.session_state.jobs)
    total_time = total_run_time + total_setup_time
    efficiency = (total_run_time / total_time * 100) if total_time > 0 else 0
    
    # On-Time Delivery (OTD)
    on_time_jobs = sum(1 for job in st.session_state.jobs if job.get('on_time', True))
    total_jobs = len(st.session_state.jobs)
    otd = (on_time_jobs / total_jobs * 100) if total_jobs > 0 else 0
    
    col1, col2 = st.columns([1, 1])
    with col1:
        st.metric("Avg Machine Efficiency %", f"{efficiency:.1f}%")
    with col2:
        st.metric("On-Time Delivery (OTD) %", f"{otd:.1f}%")
    
    # Top level summary
    st.markdown("### 📈 Production Summary")
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        st.metric("Total Jobs", len(st.session_state.jobs))
    with col2:
        st.metric("Active Machines", len([m for m in MACHINE_DATA.keys() if any(st.session_state.machine_load[m])]))
    with col3:
        st.metric("Total Impressions", f"{sum(job['impressions'] for job in st.session_state.jobs):,.0f}")
    
    st.markdown("### Machine Status Overview (Stoplight System)")
    
    # Create dashboard data
    dashboard_data = []
    for machine in sorted(MACHINE_DATA.keys()):
        status, color = get_machine_status(machine, datetime.now())
        
        # Calculate total load hours
        total_load = 0
        for job in st.session_state.machine_load[machine]:
            total_load += MACHINE_DATA[machine]['setup_hours'] + job['impressions'] / MACHINE_DATA[machine]['rate_per_hour']
        
        dashboard_data.append({
            'Machine': machine,
            'Status': status,
            'Load (hours)': f"{total_load:.2f}",
            'Rate (imp/hr)': MACHINE_DATA[machine]['rate_per_hour']
        })
    
    df_dashboard = pd.DataFrame(dashboard_data)
    
    # Display with color coding
    st.dataframe(df_dashboard, use_container_width=True, hide_index=True)
    
    # Jobs filtered by sales rep
    if st.session_state.jobs:
        st.markdown("### Recent Jobs")
        
        jobs_to_display = st.session_state.jobs
        if selected_rep != "All":
            jobs_to_display = [job for job in st.session_state.jobs if job['sales_rep'] == selected_rep]
        
        if jobs_to_display:
            jobs_df_data = []
            for job in jobs_to_display:
                jobs_df_data.append({
                    'Job Name': job['name'],
                    'Sales Rep': job['sales_rep'],
                    'Impressions': job['impressions'],
                    'Processes': ', '.join(job['processes']),
                    'Start Time': job['schedule'][0]['start'].strftime('%Y-%m-%d %H:%M'),
                    'End Time': job['schedule'][-1]['end'].strftime('%Y-%m-%d %H:%M')
                })
            
            st.dataframe(pd.DataFrame(jobs_df_data), use_container_width=True, hide_index=True)
        else:
            st.info(f"No jobs for {selected_rep}")

# PAGE 2: PLAN JOB - Job Routing Engine
elif page == "Plan Job":
    st.title("📝 Plan New Job - Advanced Routing Engine")
    st.markdown("Configure job parameters with advanced calculation logic for production scheduling")
    
    with st.form("job_form", clear_on_submit=True):
        st.markdown("### Job Information")
        col1, col2 = st.columns(2)
        
        with col1:
            job_name = st.text_input("Job Name", placeholder="e.g., Client A - Brochure Run 2025")
            sales_rep = st.selectbox("Sales Rep Name", 
                                     ["John Smith", "Sarah Johnson", "Mike Davis", "Emma Wilson", "Other"],
                                     key="sales_rep_select")
            if sales_rep == "Other":
                sales_rep = st.text_input("Enter Sales Rep Name")
        
        with col2:
            target_deadline = st.date_input("Target Delivery Date (Optional)")
            target_time = st.time_input("Target Delivery Time", value=datetime.min.time())
        
        st.markdown("### Job Specifications (Calculate Impressions)")
        st.markdown("**Formula:** Impressions = (Finished Qty ÷ Ups-per-Sheet) × (1 + Overs%)")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            finished_qty = st.number_input("Finished Quantity", min_value=100, value=100000, step=100,
                                          help="e.g., 2,000,000 units")
        
        with col2:
            ups_per_sheet = st.number_input("Ups-per-Sheet", min_value=1, value=12, step=1,
                                           help="How many copies per sheet")
        
        with col3:
            sheets_per_packet = st.number_input("Sheets-per-Packet", min_value=1, value=100, step=1)
        
        with col4:
            overs_pct = st.number_input("Overs %", min_value=0.0, value=5.0, step=0.1,
                                       help="Additional % for waste/damage")
        
        # Calculate impressions
        impressions = calculate_impressions(finished_qty, ups_per_sheet, overs_pct)
        packets = calculate_packets(impressions, sheets_per_packet)
        setup_time = calculate_setup_time(impressions)
        
        st.info(f"**Calculated Impressions:** {impressions:,.0f} | **Packets:** {packets:,.0f} | **Setup Time:** {setup_time} hours")
        
        st.markdown("### Production Sequence")
        st.markdown("Select the sequence of processes this job will go through (Print → Fold → Trim):")
        
        available_processes = list(MACHINE_DATA.keys())
        selected_processes = []
        
        # Create columns for process selection
        cols = st.columns(3)
        for idx, process in enumerate(sorted(available_processes)):
            col = cols[idx % 3]
            if col.checkbox(process):
                selected_processes.append(process)
        
        submitted = st.form_submit_button("✅ Create Job & Schedule", use_container_width=True)
        
        if submitted:
            if not job_name or not sales_rep or not selected_processes:
                st.error("Please fill in all required fields and select at least one process")
            else:
                target_datetime = None
                if target_deadline:
                    target_datetime = datetime.combine(target_deadline, target_time)
                
                job = add_job(job_name, sales_rep, impressions, selected_processes, target_deadline=target_datetime)
                st.success(f"✅ Job '{job_name}' created successfully!")
                
                # Display comprehensive job schedule
                st.markdown("### 📅 Job Schedule & Processing Details")
                schedule_data = []
                total_time = 0
                
                for idx, task in enumerate(job['schedule']):
                    duration = task['duration']
                    total_time += duration
                    machine = task['process']
                    rate = MACHINE_DATA[machine]['rate_per_hour']
                    
                    schedule_data.append({
                        'Stage': idx + 1,
                        'Process': task['process'],
                        'Rate (imp/hr)': f"{rate:,}",
                        'Start': task['start'].strftime('%Y-%m-%d %H:%M'),
                        'End': task['end'].strftime('%Y-%m-%d %H:%M'),
                        'Duration (hrs)': f"{duration:.2f}"
                    })
                
                st.dataframe(pd.DataFrame(schedule_data), use_container_width=True, hide_index=True)
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total Processing Time", f"{total_time:.2f}h")
                with col2:
                    st.metric("Expected Finish", job['schedule'][-1]['end'].strftime('%m/%d %H:%M'))
                with col3:
                    st.metric("Job Revenue", f"${job['revenue']:,.0f}")
                with col4:
                    if job['target_deadline']:
                        on_time = "✅ On-Time" if job['on_time'] else "❌ Late"
                        st.metric("Deadline Status", on_time)
                    else:
                        st.metric("Deadline Status", "No target set")

# PAGE 3: GANTT VIEW - Sequential Gantt Chart with Target Deadline
elif page == "Gantt View":
    st.title("📊 Gantt Chart - Sequential Job Flow & Target Deadlines")
    st.markdown("Interactive timeline visualization with Expected Finish vs Target Deadline comparison")
    
    if not st.session_state.jobs:
        st.warning("No jobs created yet. Go to 'Plan Job' to create a job.")
    else:
        # Filter jobs by sales rep
        jobs_to_display = st.session_state.jobs
        if selected_rep != "All":
            jobs_to_display = [job for job in st.session_state.jobs if job['sales_rep'] == selected_rep]
        
        if not jobs_to_display:
            st.info(f"No jobs for {selected_rep}")
        else:
            # Job selection
            job_names = [job['name'] for job in jobs_to_display]
            selected_job_name = st.selectbox("Select Job to Visualize", job_names)
            
            # Find selected job
            selected_job = next((job for job in jobs_to_display if job['name'] == selected_job_name), None)
            
            if selected_job:
                # Display editable schedule table with ripple effect
                st.markdown("### 📅 Job Schedule (Edit to Apply Ripple Effect)")
                
                schedule_data = []
                for idx, task in enumerate(selected_job['schedule']):
                    schedule_data.append({
                        'Process': task['process'],
                        'Start': task['start'],
                        'Duration (hours)': task['duration']
                    })
                
                df_schedule = pd.DataFrame(schedule_data)
                edited_df = st.data_editor(
                    df_schedule,
                    use_container_width=True,
                    hide_index=True,
                    key="schedule_editor"
                )
                
                # Recalculate schedule if start times changed (ripple effect)
                if st.button("🔄 Update Schedule with Ripple Effect"):
                    updated_schedule = []
                    
                    for idx, row in edited_df.iterrows():
                        if idx == 0:
                            current_time = row['Start']
                        else:
                            current_time = updated_schedule[idx-1]['end']
                        
                        duration = row['Duration (hours)']
                        end_time = current_time + timedelta(hours=duration)
                        
                        updated_schedule.append({
                            'job': selected_job['name'],
                            'process': row['Process'],
                            'start': current_time,
                            'end': end_time,
                            'duration': duration,
                            'impressions': selected_job['impressions']
                        })
                    
                    selected_job['schedule'] = updated_schedule
                    if selected_job['target_deadline']:
                        selected_job['on_time'] = updated_schedule[-1]['end'] <= selected_job['target_deadline']
                    st.success("✅ Schedule updated with ripple effect applied!")
                    st.rerun()
                
                # Create enhanced Gantt chart with target deadline
                st.markdown("### 📈 Timeline Visualization")
                
                fig = go.Figure()
                
                colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f']
                
                # Add task bars
                for idx, task in enumerate(selected_job['schedule']):
                    color = colors[idx % len(colors)]
                    fig.add_trace(go.Bar(
                        x=[task['duration']],
                        y=[task['process']],
                        orientation='h',
                        name=task['process'],
                        marker=dict(color=color),
                        base=task['start'],
                        hovertemplate=f"<b>{task['process']}</b><br>" +
                                      f"Start: {task['start'].strftime('%Y-%m-%d %H:%M')}<br>" +
                                      f"End: {task['end'].strftime('%Y-%m-%d %H:%M')}<br>" +
                                      f"Duration: {task['duration']:.2f}h<extra></extra>"
                    ))
                
                # Add target deadline line if present
                if selected_job['target_deadline']:
                    fig.add_vline(
                        x=selected_job['target_deadline'],
                        line_dash="dash",
                        line_color="red",
                        annotation_text="Target Deadline",
                        annotation_position="top right"
                    )
                
                fig.update_layout(
                    title=f"Sequential Flow: {selected_job['name']}<br>Expected: {selected_job['schedule'][-1]['end'].strftime('%Y-%m-%d %H:%M')} | Target: {selected_job['target_deadline'].strftime('%Y-%m-%d %H:%M') if selected_job['target_deadline'] else 'None'}",
                    xaxis_title="Timeline",
                    yaxis_title="Process/Machine",
                    barmode='overlay',
                    hovermode='closest',
                    height=500,
                    xaxis=dict(type='date'),
                    showlegend=False
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
                # Summary statistics with deadline comparison
                col1, col2, col3, col4 = st.columns(4)
                
                total_time = selected_job['schedule'][-1]['end'] - selected_job['schedule'][0]['start']
                total_hours = total_time.total_seconds() / 3600
                
                with col1:
                    st.metric("Total Duration", f"{total_hours:.2f}h")
                with col2:
                    expected_finish = selected_job['schedule'][-1]['end']
                    st.metric("Expected Finish", expected_finish.strftime('%m/%d %H:%M'))
                with col3:
                    if selected_job['target_deadline']:
                        days_diff = (selected_job['target_deadline'] - expected_finish).days
                        if days_diff >= 0:
                            st.metric("Buffer Days", f"+{days_diff} days")
                        else:
                            st.metric("Days Late", f"{abs(days_diff)} days")
                    else:
                        st.metric("Target Deadline", "Not set")
                with col4:
                    on_time_status = "✅ On-Time" if selected_job['on_time'] else "❌ Late"
                    st.metric("Deadline Status", on_time_status)
                
                # Detailed metrics
                st.markdown("### 📊 Job Details")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Stages", len(selected_job['schedule']))
                with col2:
                    st.metric("Sales Rep", selected_job['sales_rep'])
                with col3:
                    st.metric("Job Revenue", f"${selected_job.get('revenue', 0):,.0f}")

# Footer
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: #888;'>"
    "Appointed Time Printing - Job Planning & Simulation System<br>"
    "Production Ready | Data-Driven Scheduling"
    "</div>",
    unsafe_allow_html=True
)
