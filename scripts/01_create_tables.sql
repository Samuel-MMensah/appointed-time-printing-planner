-- Create jobs table
CREATE TABLE IF NOT EXISTS jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR NOT NULL,
  sales_rep VARCHAR NOT NULL,
  impressions INTEGER NOT NULL,
  finished_qty INTEGER NOT NULL,
  ups_per_sheet INTEGER NOT NULL,
  sheets_per_packet INTEGER NOT NULL,
  overs_pct DECIMAL(5, 2) DEFAULT 5.0,
  contract_value DECIMAL(12, 2) NOT NULL,
  target_deadline TIMESTAMP,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Create job_processes table (many-to-many for jobs and processes)
CREATE TABLE IF NOT EXISTS job_processes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  process_name VARCHAR NOT NULL,
  sequence_order INTEGER NOT NULL,
  start_time TIMESTAMP NOT NULL,
  end_time TIMESTAMP NOT NULL,
  duration_hours DECIMAL(10, 2) NOT NULL,
  created_at TIMESTAMP DEFAULT NOW()
);

-- Create machine_loads table for tracking machine utilization
CREATE TABLE IF NOT EXISTS machine_loads (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  machine_name VARCHAR NOT NULL,
  job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  start_time TIMESTAMP NOT NULL,
  end_time TIMESTAMP NOT NULL,
  duration_hours DECIMAL(10, 2) NOT NULL,
  created_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_jobs_sales_rep ON jobs(sales_rep);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at);
CREATE INDEX IF NOT EXISTS idx_job_processes_job_id ON job_processes(job_id);
CREATE INDEX IF NOT EXISTS idx_machine_loads_machine ON machine_loads(machine_name);
CREATE INDEX IF NOT EXISTS idx_machine_loads_time ON machine_loads(start_time, end_time);

-- Enable RLS (Row Level Security)
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_processes ENABLE ROW LEVEL SECURITY;
ALTER TABLE machine_loads ENABLE ROW LEVEL SECURITY;

-- Create RLS policies (allow all for now - adjust based on auth requirements)
CREATE POLICY "Allow all for jobs" ON jobs USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for job_processes" ON job_processes USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for machine_loads" ON machine_loads USING (true) WITH CHECK (true);
