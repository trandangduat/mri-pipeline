import os
import json
import re
import pandas as pd
import numpy as np

base_dir = "outputs"

records = []
stage_order_dict = {}
current_order = 1

for batch_dir in sorted(os.listdir(base_dir)):
    benchmark_path = os.path.join(base_dir, batch_dir, "benchmark", "benchmark_steps.json")
    if not os.path.isfile(benchmark_path):
        continue
    batch_config_path = os.path.join(base_dir, batch_dir, "benchmark", "batch_config.json")
    host_info_path = os.path.join(base_dir, batch_dir, "benchmark", "host_info.json")
    batch_config = {}
    host_info = {}
    if os.path.isfile(batch_config_path):
        with open(batch_config_path, "r") as f:
            try:
                parsed = json.load(f)
                batch_config = parsed if isinstance(parsed, dict) else {}
            except:
                batch_config = {}
    if os.path.isfile(host_info_path):
        with open(host_info_path, "r") as f:
            try:
                parsed = json.load(f)
                host_info = parsed if isinstance(parsed, dict) else {}
            except:
                host_info = {}
    fallback_core = None
    match = re.search(r'_(\d+)core_', batch_dir)
    if match:
        fallback_core = int(match.group(1))
        
    with open(benchmark_path, "r") as f:
        try:
            data = json.load(f)
        except:
            continue
        
    for step in data:
        if not step.get("success"):
            continue
        core = step.get("threads") or batch_config.get("threads") or fallback_core
        if core is None:
            continue
        try:
            core = int(core)
        except (TypeError, ValueError):
            continue
             
        stage = step.get("stage_label")
        tool = step.get("tool_label")
        if not stage or not tool:
            continue
            
        peak_ram_mb = step.get("peak_ram_mb")
        avg_ram_mb = step.get("avg_ram_mb")
        p95_ram_mb = step.get("p95_ram_mb")
        peak_cpu_pct = step.get("peak_cpu_pct")
        avg_cpu_pct = step.get("avg_cpu_pct")
        p95_cpu_pct = step.get("p95_cpu_pct")
        time_sec = step.get("run_sec")
        
        # Convert values, use np.nan if None
        peak_ram_gb = (peak_ram_mb / 1024) if peak_ram_mb is not None else np.nan
        avg_ram_gb = (avg_ram_mb / 1024) if avg_ram_mb is not None else np.nan
        p95_ram_gb = (p95_ram_mb / 1024) if p95_ram_mb is not None else np.nan
        peak_cpu_dec = (peak_cpu_pct / 100) if peak_cpu_pct is not None else np.nan
        avg_cpu_dec = (avg_cpu_pct / 100) if avg_cpu_pct is not None else np.nan
        p95_cpu_dec = (p95_cpu_pct / 100) if p95_cpu_pct is not None else np.nan
        time_min = (time_sec / 60) if time_sec is not None else np.nan
        
        if stage not in stage_order_dict:
            stage_order_dict[stage] = current_order
            current_order += 1
            
        records.append({
            "stage_label": stage,
            "tool_label": tool,
            "core": core,
            "device": step.get("device") or batch_config.get("device") or "",
            "cpu_model": step.get("cpu_model") or host_info.get("cpu_model") or "",
            "logical_cores": step.get("logical_cores") or host_info.get("logical_cores") or "",
            "physical_cores": step.get("physical_cores") or host_info.get("physical_cores") or "",
            "peak_ram_gb": peak_ram_gb,
            "avg_ram_gb": avg_ram_gb,
            "p95_ram_gb": p95_ram_gb,
            "peak_cpu_decimal": peak_cpu_dec,
            "avg_cpu_decimal": avg_cpu_dec,
            "p95_cpu_decimal": p95_cpu_dec,
            "time_min": time_min
        })

if not records:
    print("No records found.")
    exit(0)

df = pd.DataFrame(records)

# Average across subject_ids for same stage, tool, core
# mean() will automatically ignore np.nan
grouped = df.groupby(["stage_label", "tool_label", "device", "cpu_model", "logical_cores", "physical_cores", "core"]).agg(
    RAM_peak_mean=("peak_ram_gb", "mean"),
    RAM_step_mean=("avg_ram_gb", "mean"),
    RAM_step_p95_mean=("p95_ram_gb", "mean"),
    CPU_peak_mean=("peak_cpu_decimal", "mean"),
    CPU_step_mean=("avg_cpu_decimal", "mean"),
    CPU_step_p95_mean=("p95_cpu_decimal", "mean"),
    Time=("time_min", "mean")
).reset_index()

# Add order to stage_label
grouped["Tên bước"] = grouped["stage_label"].apply(lambda x: f"{stage_order_dict[x]}. {x}")
grouped["Tên tools"] = grouped["tool_label"]

# Prepare CSV output
# We need columns: RAM_mean_Xcore (GB), CPU_mean_Xcore, Time_Xcore (phút)
all_cores = sorted(int(c) for c in df["core"].dropna().unique())

csv_rows = []
groups = grouped.groupby(["Tên bước", "Tên tools", "device", "cpu_model", "logical_cores", "physical_cores"])

# Sort groups by stage order
def get_stage_order(name):
    return int(name.split('.')[0])

sorted_keys = sorted(groups.groups.keys(), key=lambda x: (get_stage_order(x[0]), x[1], str(x[3]), str(x[2])))

csv_columns = ["Tên bước", "Tên tools", "Device", "CPU model", "Logical cores", "Physical cores"]
for c in all_cores:
    csv_columns.extend([
        f"RAM_mean_{c}core (GB)",
        f"RAM_step_mean_{c}core (GB)",
        f"RAM_step_p95_mean_{c}core (GB)",
        f"CPU_mean_{c}core",
        f"CPU_step_mean_{c}core",
        f"CPU_step_p95_mean_{c}core",
        f"Time_{c}core (phút)",
    ])

for (stage, tool, device, cpu_model, logical_cores, physical_cores) in sorted_keys:
    group_df = groups.get_group((stage, tool, device, cpu_model, logical_cores, physical_cores))
    
    row_dict = {
        "Tên bước": stage,
        "Tên tools": tool,
        "Device": device,
        "CPU model": cpu_model,
        "Logical cores": logical_cores,
        "Physical cores": physical_cores,
    }
    for c in all_cores:
        core_data = group_df[group_df["core"] == c]
        if not core_data.empty:
            ram_peak_mean = core_data.iloc[0]["RAM_peak_mean"]
            ram_step_mean = core_data.iloc[0]["RAM_step_mean"]
            ram_step_p95_mean = core_data.iloc[0]["RAM_step_p95_mean"]
            cpu_peak_mean = core_data.iloc[0]["CPU_peak_mean"]
            cpu_step_mean = core_data.iloc[0]["CPU_step_mean"]
            cpu_step_p95_mean = core_data.iloc[0]["CPU_step_p95_mean"]
            tmean = core_data.iloc[0]["Time"]
            
            row_dict[f"RAM_mean_{c}core (GB)"] = "" if pd.isna(ram_peak_mean) else ram_peak_mean
            row_dict[f"RAM_step_mean_{c}core (GB)"] = "" if pd.isna(ram_step_mean) else ram_step_mean
            row_dict[f"RAM_step_p95_mean_{c}core (GB)"] = "" if pd.isna(ram_step_p95_mean) else ram_step_p95_mean
            row_dict[f"CPU_mean_{c}core"] = "" if pd.isna(cpu_peak_mean) else cpu_peak_mean
            row_dict[f"CPU_step_mean_{c}core"] = "" if pd.isna(cpu_step_mean) else cpu_step_mean
            row_dict[f"CPU_step_p95_mean_{c}core"] = "" if pd.isna(cpu_step_p95_mean) else cpu_step_p95_mean
            row_dict[f"Time_{c}core (phút)"] = "" if pd.isna(tmean) else tmean
        else:
            row_dict[f"RAM_mean_{c}core (GB)"] = ""
            row_dict[f"RAM_step_mean_{c}core (GB)"] = ""
            row_dict[f"RAM_step_p95_mean_{c}core (GB)"] = ""
            row_dict[f"CPU_mean_{c}core"] = ""
            row_dict[f"CPU_step_mean_{c}core"] = ""
            row_dict[f"CPU_step_p95_mean_{c}core"] = ""
            row_dict[f"Time_{c}core (phút)"] = ""
            
    csv_rows.append(row_dict)

csv_df = pd.DataFrame(csv_rows, columns=csv_columns)
csv_df.to_csv("benchmark_summary.csv", index=False, na_rep="")

# Prepare Excel output with MultiIndex columns
arrays = [
    ["Thông tin", "Thông tin", "Thông tin", "Thông tin", "Thông tin", "Thông tin"],
    ["Tên bước", "Tên tools", "Device", "CPU model", "Logical cores", "Physical cores"]
]
for c in all_cores:
    arrays[0].extend([f"{c} core"] * 7)
    arrays[1].extend(["CPU_mean", "CPU_step_mean", "CPU_step_p95_mean", "RAM_mean (GB)", "RAM_step_mean (GB)", "RAM_step_p95_mean (GB)", "Time (phút)"])

tuples = list(zip(*arrays))
index = pd.MultiIndex.from_tuples(tuples)

excel_data = []
for row in csv_rows:
    excel_row = [row["Tên bước"], row["Tên tools"], row["Device"], row["CPU model"], row["Logical cores"], row["Physical cores"]]
    for c in all_cores:
        excel_row.extend([
            row[f"CPU_mean_{c}core"],
            row[f"CPU_step_mean_{c}core"],
            row[f"CPU_step_p95_mean_{c}core"],
            row[f"RAM_mean_{c}core (GB)"],
            row[f"RAM_step_mean_{c}core (GB)"],
            row[f"RAM_step_p95_mean_{c}core (GB)"],
            row[f"Time_{c}core (phút)"]
        ])
    excel_data.append(excel_row)

excel_df = pd.DataFrame(excel_data, columns=index)
excel_df = excel_df.set_index([("Thông tin", "Tên bước"), ("Thông tin", "Tên tools"), ("Thông tin", "Device"), ("Thông tin", "CPU model"), ("Thông tin", "Logical cores"), ("Thông tin", "Physical cores")])

with pd.ExcelWriter("benchmark_summary.xlsx") as writer:
    excel_df.to_excel(writer, index=True)

print("Created benchmark_summary.csv and benchmark_summary.xlsx successfully.")
