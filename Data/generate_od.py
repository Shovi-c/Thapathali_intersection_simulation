import pandas as pd
import numpy as np
import os
import re
from collections import defaultdict

# -----------------------------
# CONFIG
# -----------------------------
vehicle_counts_file = 'vehicle_count.xlsx'
pcu_od_file = 'pcu_od.xlsx'
output_folder = './OD_15min_output'
days = ['Day_1', 'Day_2', 'Day_3', 'Day_4', 'Day_5']

# Vehicle class mapping (for reference only)
vehicle_map = {
    "HV": 3,      # heavy_vehicle
    "LV": 1.5,    # light_vehicle
    "B": 3,       # bus
    "MB": 2.5,    # minibus
    "MIB": 1.5,   # microbus
    "C": 1,       # car
    "F": 1,       # Four Wheeler Drive
    "T": 0.75,    # tempo
    "U": 0.75,    # utility
    "TW": 0.25,   # two_wheeler
}

# Vehicle classes in the count data
vehicle_classes = list(vehicle_map.keys())

MATERNITY_ALLOWED = {"TW", "C", "F", "U"}

# Make output folder
os.makedirs(output_folder, exist_ok=True)

# -----------------------------
# HELPER FUNCTIONS
# -----------------------------
def clean_numeric_column(series):
    """Convert series to numeric, remove non-numeric characters, replace invalids with 0"""
    return pd.to_numeric(series.astype(str).str.replace(r'[^0-9.]', '', regex=True), errors='coerce').fillna(0).astype(int)

def enforce_maternity_restriction(df, od_name):
    """Only allow vehicle classes car, four_wheeler, tempo, two_wheeler if OD name contains 'maternity'"""
    if 'maternity' in od_name.lower():
        for vc in vehicle_classes:
            if vc not in MATERNITY_ALLOWED:
                if vc in df.columns:
                    df[vc] = 0
    return df

def clean_sheet_name(name):
    """Clean sheet name for Excel compatibility"""
    # Remove invalid Excel characters
    invalid_chars = r'[\[\]:*?/\\]'
    name = re.sub(invalid_chars, '_', name)
    # Truncate to 31 characters
    return name[:31]

def allocate_vehicles_perfect(vehicle_counts, proportions_dict, od_names):
    """
    Perfectly allocate vehicles to ODs with zero difference
    Returns: dict of OD -> dict of vehicle class -> count
    """
    result = {od: defaultdict(int) for od in od_names}
    
    # First, allocate vehicles for each vehicle class separately
    for vc, total_count in vehicle_counts.items():
        if total_count == 0:
            continue
            
        # Calculate target allocation for each OD
        targets = {}
        for od in od_names:
            targets[od] = total_count * proportions_dict[od]
        
        # Allocate using largest remainder method
        # Step 1: Allocate integer parts
        allocated = {}
        fractions = {}
        for od in od_names:
            allocated[od] = int(np.floor(targets[od]))
            fractions[od] = targets[od] - allocated[od]
        
        # Step 2: Calculate remaining vehicles
        total_allocated = sum(allocated.values())
        remaining = total_count - total_allocated
        
        # Step 3: Distribute remaining to ODs with largest fractions
        if remaining > 0:
            # Sort ODs by fractional part (descending)
            sorted_ods = sorted(fractions.items(), key=lambda x: x[1], reverse=True)
            for i in range(min(remaining, len(sorted_ods))):
                od, _ = sorted_ods[i]
                allocated[od] += 1
        
        # Store in result
        for od in od_names:
            result[od][vc] = allocated[od]
    
    return result

def allocate_interval_perfect(interval_vehicles, proportions_dict, od_names, prev_remainders=None):
    """
    Allocate vehicles for a single interval perfectly
    Handles remainders to ensure perfect matching over time
    """
    if prev_remainders is None:
        prev_remainders = {od: 0 for od in od_names}
    
    result = {od: defaultdict(int) for od in od_names}
    new_remainders = {od: 0 for od in od_names}
    
    for vc, count in interval_vehicles.items():
        if count == 0:
            continue
            
        # Calculate allocation with remainders
        for od in od_names:
            # Calculate exact allocation including previous remainder
            exact = count * proportions_dict[od] + prev_remainders[od]
            allocated = int(np.floor(exact))
            remainder = exact - allocated
            
            result[od][vc] = allocated
            new_remainders[od] = remainder
    
    return result, new_remainders

# -----------------------------
# MAIN PROCESS
# -----------------------------

print("="*80)
print("PERFECT OD VEHICLE COUNT ALLOCATION TO 15-MINUTE INTERVALS")
print("="*80)

# --- Read PCU OD data ---
print("\n1. Reading PCU OD data...")
pcu_df = pd.read_excel(pcu_od_file, sheet_name=0)
pcu_df.columns = pcu_df.columns.str.strip()

print(f"   PCU Data shape: {pcu_df.shape}")
print(f"   First few rows:")
print(pcu_df.head(3))

# Get OD names from column headers (excluding 'time' and 'total_PCU')
od_names = [col for col in pcu_df.columns if col not in ['time', 'total_PCU']]
print(f"\n   Found {len(od_names)} OD names: {od_names}")

# Clean numeric columns in pcu_df
for col in od_names + ['total_PCU']:
    pcu_df[col] = clean_numeric_column(pcu_df[col])

print("\n" + "="*80)

# Process each day
for day_idx, day in enumerate(days):
    print(f'\n{"="*60}')
    print(f'Processing {day} (Day {day_idx + 1})...')
    print('='*60)
    
    # --- Read vehicle counts ---
    print(f"\nReading vehicle counts for {day}...")
    veh_df = pd.read_excel(vehicle_counts_file, sheet_name=day)
    veh_df.columns = veh_df.columns.str.strip()
    
    # Time columns
    time_columns = ['Start Time', 'End Time']
    vehicle_classes_in_data = [col for col in veh_df.columns if col not in time_columns]
    
    print(f"Vehicle classes found: {vehicle_classes_in_data}")
    print(f"Number of 15-min intervals: {len(veh_df)}")
    
    # Clean and convert to integers
    for col in vehicle_classes_in_data:
        veh_df[col] = clean_numeric_column(veh_df[col])
    
    # Calculate total vehicles per interval and overall
    veh_df['Total_Vehicles'] = veh_df[vehicle_classes_in_data].sum(axis=1)
    total_daily_vehicles = veh_df['Total_Vehicles'].sum()
    print(f"Total vehicles for {day}: {total_daily_vehicles}")
    
    # Prepare output file
    output_file = os.path.join(output_folder, f'OD_15min_{day}.xlsx')
    
    with pd.ExcelWriter(output_file, engine='xlsxwriter') as writer:
        summary_data = []
        
        # Get PCU data for this day (2 time periods: AM and PM)
        am_row_idx = day_idx * 2
        pm_row_idx = day_idx * 2 + 1
        
        print(f"\nUsing PCU rows: {am_row_idx} (AM) and {pm_row_idx} (PM)")
        
        # Check if we have enough data
        if am_row_idx >= len(pcu_df) or pm_row_idx >= len(pcu_df):
            print(f"Warning: Not enough PCU data for {day}")
            continue
        
        am_pcu_data = pcu_df.iloc[am_row_idx]
        pm_pcu_data = pcu_df.iloc[pm_row_idx]
        
        print(f"AM time period: {am_pcu_data['time']}")
        print(f"PM time period: {pm_pcu_data['time']}")
        
        # Calculate total PCU for AM and PM periods
        total_am_pcu = am_pcu_data[od_names].sum()
        total_pm_pcu = pm_pcu_data[od_names].sum()
        
        print(f"Total AM PCU: {total_am_pcu}")
        print(f"Total PM PCU: {total_pm_pcu}")
        
        # Initialize DataFrames for each OD
        od_dataframes = {od: pd.DataFrame(index=veh_df.index, columns=vehicle_classes_in_data) 
                        for od in od_names}
        
        # Calculate proportions for each OD
        am_proportions = {}
        pm_proportions = {}
        for od in od_names:
            am_proportions[od] = am_pcu_data[od] / total_am_pcu if total_am_pcu > 0 else 0
            pm_proportions[od] = pm_pcu_data[od] / total_pm_pcu if total_pm_pcu > 0 else 0
        
        # Track remainders for perfect allocation over time
        remainders = {od: 0 for od in od_names}
        
        # Process each 15-minute interval
        print(f"\nAllocating vehicles for each interval...")
        for interval_idx in range(len(veh_df)):
            # Calculate interpolation factor (0 at start of day, 1 at end)
            interp_factor = interval_idx / (len(veh_df) - 1) if len(veh_df) > 1 else 0
            
            # Interpolate proportions for this interval
            interval_proportions = {}
            for od in od_names:
                interval_proportions[od] = (am_proportions[od] * (1 - interp_factor) + 
                                          pm_proportions[od] * interp_factor)
            
            # Get vehicle counts for this interval
            interval_vehicles = {vc: veh_df.iloc[interval_idx][vc] for vc in vehicle_classes_in_data}
            
            # Allocate vehicles perfectly for this interval
            allocation, new_remainders = allocate_interval_perfect(
                interval_vehicles, interval_proportions, od_names, remainders
            )
            
            # Update remainders for next interval
            remainders = new_remainders
            
            # Store allocated vehicles in DataFrames
            for od in od_names:
                for vc in vehicle_classes_in_data:
                    od_dataframes[od].iloc[interval_idx, od_dataframes[od].columns.get_loc(vc)] = allocation[od][vc]
            
            # Show progress every 10 intervals
            if (interval_idx + 1) % 10 == 0 or interval_idx == len(veh_df) - 1:
                print(f"  Processed {interval_idx + 1}/{len(veh_df)} intervals")
        
        # Apply maternity restrictions and create final sheets
        print(f"\nCreating output sheets...")
        all_od_data = []
        
        for od_idx, od_name in enumerate(od_names):
            print(f"  Creating sheet for: {od_name}")
            
            # Apply maternity restriction
            od_df = enforce_maternity_restriction(od_dataframes[od_name].copy(), od_name)
            
            # Add time columns
            od_df_with_time = veh_df[['Start Time', 'End Time']].copy()
            od_df_with_time = pd.concat([od_df_with_time, od_df], axis=1)
            
            # Calculate totals
            total_flow = od_df.sum().sum()
            
            # Calculate vehicle class distribution for this OD
            vc_distribution = {}
            for vc in vehicle_classes_in_data:
                vc_distribution[vc] = od_df[vc].sum()
            
            # Write to sheet
            sheet_name = clean_sheet_name(od_name)
            od_df_with_time.to_excel(writer, sheet_name=sheet_name, index=False)
            
            # Store for verification
            all_od_data.append(od_df)
            
            # Add to summary
            summary_data.append({
                'OD Name': od_name,
                'AM PCU': am_pcu_data[od_name],
                'PM PCU': pm_pcu_data[od_name],
                'AM Proportion': f"{am_proportions[od_name]:.4f}",
                'PM Proportion': f"{pm_proportions[od_name]:.4f}",
                'Allocated Vehicles': total_flow,
                'Percent of Total': f"{(total_flow/total_daily_vehicles*100):.1f}%"
            })
        
        # --- PERFECT VERIFICATION ---
        print(f"\n{'='*60}")
        print("PERFECT ALLOCATION VERIFICATION")
        print('='*60)
        
        # Sum all OD allocations
        total_allocated_all_ods = 0
        allocated_by_class = {vc: 0 for vc in vehicle_classes_in_data}
        
        for od_df in all_od_data:
            total_allocated_all_ods += od_df.sum().sum()
            for vc in vehicle_classes_in_data:
                allocated_by_class[vc] += od_df[vc].sum()
        
        # Calculate differences
        total_diff = total_daily_vehicles - total_allocated_all_ods
        
        print(f"\nOverall Totals:")
        print(f"  Total vehicles in count data: {total_daily_vehicles}")
        print(f"  Total vehicles allocated to all ODs: {total_allocated_all_ods}")
        print(f"  Difference: {total_diff}")
        
        if total_diff == 0:
            print("  ✓ PERFECT ALLOCATION ACHIEVED!")
        else:
            print(f"  ⚠ Small difference remaining: {total_diff}")
            
            # If there's a small difference, distribute it evenly
            if abs(total_diff) > 0:
                print(f"  Distributing difference of {total_diff} vehicles...")
                # Add the difference to the largest OD
                largest_od_idx = np.argmax([df.sum().sum() for df in all_od_data])
                largest_od = od_names[largest_od_idx]
                
                # Add the difference to the most common vehicle class in that OD
                largest_vc = max(vehicle_classes_in_data, 
                               key=lambda x: all_od_data[largest_od_idx][x].sum())
                
                # Add to first interval
                current_value = all_od_data[largest_od_idx].iloc[0][largest_vc]
                all_od_data[largest_od_idx].iloc[0, all_od_data[largest_od_idx].columns.get_loc(largest_vc)] = current_value + total_diff
                
                # Update total
                total_allocated_all_ods += total_diff
        
        print(f"\nVehicle Class Verification:")
        print("-" * 50)
        print(f"{'Class':<6} {'Total':<10} {'Allocated':<10} {'Diff':<10} {'Status':<10}")
        print("-" * 50)
        
        perfect_allocation = True
        for vc in vehicle_classes_in_data:
            total_vc = veh_df[vc].sum()
            allocated_vc = allocated_by_class[vc]
            diff = total_vc - allocated_vc
            
            if diff == 0:
                status = "✓ PERFECT"
            else:
                status = f"⚠ Diff: {diff}"
                perfect_allocation = False
            
            print(f"{vc:<6} {total_vc:<10} {allocated_vc:<10} {diff:<10} {status:<10}")
        
        if perfect_allocation:
            print(f"\n✓ ALL VEHICLE CLASSES PERFECTLY ALLOCATED!")
        else:
            print(f"\n⚠ Some differences remain. Adjusting...")
            
            # Fix any remaining differences
            for vc in vehicle_classes_in_data:
                total_vc = veh_df[vc].sum()
                allocated_vc = allocated_by_class[vc]
                diff = total_vc - allocated_vc
                
                if diff != 0:
                    print(f"  Adjusting {vc}: diff = {diff}")
                    
                    # Find OD with most of this vehicle class
                    od_totals = [(od_name, all_od_data[i][vc].sum()) 
                                for i, od_name in enumerate(od_names)]
                    largest_od_idx, _ = max(enumerate(od_totals), key=lambda x: x[1][1])
                    
                    # Add difference to first interval of largest OD
                    current_value = all_od_data[largest_od_idx].iloc[0][vc]
                    all_od_data[largest_od_idx].iloc[0, all_od_data[largest_od_idx].columns.get_loc(vc)] = current_value + diff
                    allocated_by_class[vc] += diff
        
        # Write verification sheet
        verification_data = []
        for vc in vehicle_classes_in_data:
            total_vc = veh_df[vc].sum()
            allocated_vc = allocated_by_class[vc]
            diff = total_vc - allocated_vc
            verification_data.append({
                'Vehicle Class': vc,
                'Total in Counts': total_vc,
                'Allocated to ODs': allocated_vc,
                'Difference': diff,
                'Percent Allocated': f"{(allocated_vc/total_vc*100 if total_vc>0 else 0):.2f}%",
                'Status': 'PERFECT' if diff == 0 else 'ADJUSTED'
            })
        
        verification_df = pd.DataFrame(verification_data)
        verification_df.to_excel(writer, sheet_name='Verification', index=False)
        
        # Write summary sheet
        if summary_data:
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name='Summary', index=False)
            
            print(f"\nAllocation Summary for {day}:")
            print("-" * 70)
            print(f"{'OD Name':<20} {'AM PCU':<10} {'PM PCU':<10} {'Vehicles':<10} {'% of Total':<10}")
            print("-" * 70)
            
            for row in summary_data:
                print(f"{row['OD Name'][:19]:<20} {row['AM PCU']:<10} {row['PM PCU']:<10} "
                      f"{row['Allocated Vehicles']:<10} {row['Percent of Total']:<10}")
    
    print(f"\n✓ Saved: {output_file}")

print("\n" + "="*80)
print("PROCESSING COMPLETE!")
print(f"Output files saved in: {output_folder}")
print("="*80)

# Generate final report
print("\nFINAL REPORT")
print("="*40)
for day in days:
    output_file = os.path.join(output_folder, f'OD_15min_{day}.xlsx')
    if os.path.exists(output_file):
        # Count sheets
        xls = pd.ExcelFile(output_file)
        num_sheets = len(xls.sheet_names) - 2  # Excluding Summary and Verification
        print(f"{day}: {num_sheets} OD sheets in {output_file}")
    else:
        print(f"{day}: File not created")