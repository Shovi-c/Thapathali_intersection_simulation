import pandas as pd
import os
import re
from collections import defaultdict

def generate_flows_sorted_by_time():
    """Process ALL sheets and sort flows by start time"""
    
    print("="*70)
    print("MATSim Flow Generator - Sorted by Time")
    print("Simulation Time: 0 seconds start")
    print("="*70)
    
    # Process all 5 days
    for day in range(1, 6):
        print(f"\n{'='*60}")
        print(f"PROCESSING DAY {day}")
        print(f"{'='*60}")
        
        # File name
        file_name = f"OD_15min_Day_{day}.xlsx"
        
        if not os.path.exists(file_name):
            print(f" File not found: {file_name}")
            continue
        
        print(f"Processing: {file_name}")
        
        try:
            # Read the Excel file
            xls = pd.ExcelFile(file_name)
            
            # Get all sheet names and filter out Verification and Summary
            all_sheets = xls.sheet_names
            route_sheets = [sheet for sheet in all_sheets 
                          if sheet.lower() not in ['verification', 'summary']]
            
            if not route_sheets:
                print(f"    No valid routes found")
                continue
            
            print(f"   Found {len(route_sheets)} routes: {', '.join(route_sheets)}")
            
            # Store all flows temporarily so we can sort them
            all_flows = []  # List of (start_time, flow_xml_line)
            flow_id_counter = 0
            total_vehicles = 0
            route_stats = {}
            
            # Process EACH route (sheet)
            for route_name in route_sheets:
                try:
                    # Read this route's sheet
                    df = pd.read_excel(file_name, sheet_name=route_name)
                    
                    if df.empty:
                        print(f"   Route '{route_name}' is empty")
                        continue
                    
                    route_vehicle_count = 0
                    route_flow_count = 0
                    
                    # Process each time interval (row) in this route
                    for idx, row in df.iterrows():
                        # Skip rows with missing time data
                        if pd.isna(row.get('Start Time')) or pd.isna(row.get('End Time')):
                            continue
                        
                        # Calculate simulation time
                        start_sec = idx * 900        # 0, 900, 1800, ...
                        end_sec = (idx + 1) * 900    # 900, 1800, 2700, ...
                        
                        # Process each vehicle type
                        for vtype in ['HV', 'LV', 'B', 'MB', 'MIB', 'C', 'U', 'F', 'T', 'TW']:
                            if vtype in row and not pd.isna(row[vtype]) and row[vtype] > 0:
                                count = int(row[vtype])
                                
                                # Create flow ID
                                route_clean = re.sub(r'[^a-zA-Z0-9_]', '_', route_name).lower()
                                flow_id = f"flow_{route_clean}_{vtype.lower()}_{flow_id_counter}"
                                
                                # Create flow XML line
                                flow_line = f'    <flow id="{flow_id}" type="{vtype}" route="{route_name}" '
                                flow_line += f'begin="{start_sec}" end="{end_sec}" '
                                flow_line += f'number="{count}"/>'
                                
                                # Store with start time for sorting
                                all_flows.append((start_sec, flow_line, count, route_name, vtype))
                                
                                flow_id_counter += 1
                                route_flow_count += 1
                                route_vehicle_count += count
                                total_vehicles += count
                    
                    # Record stats
                    if route_flow_count > 0:
                        route_stats[route_name] = {
                            'flows': route_flow_count,
                            'vehicles': route_vehicle_count,
                            'intervals': len(df)
                        }
                        print(f"    Route '{route_name}': {route_flow_count} flows, {route_vehicle_count} vehicles")
                    
                except Exception as e:
                    print(f"   Error processing route '{route_name}': {str(e)}")
                    continue
            
            # Sort flows by start time (ascending)
            print(f"\n   Sorting {len(all_flows)} flows by start time...")
            all_flows.sort(key=lambda x: (x[0], x[3], x[4]))  # Sort by start_time, then route, then vtype
            
            # Start building XML with sorted flows
            xml_lines = [
                '<routes>'
            ]
            
            # Add sorted flows to XML
            for start_time, flow_line, count, route_name, vtype in all_flows:
                xml_lines.append(flow_line)
            
            # Close XML
            xml_lines.append('</routes>')
            
            # Save file if we have any flows
            if flow_id_counter > 0:
                os.makedirs("flows_output_sorted", exist_ok=True)
                output_file = f"flows_output_sorted/flows_day_{day}_sorted.xml"
                
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(xml_lines))
                
                # Group flows by time interval for statistics
                time_groups = defaultdict(list)
                for start_time, flow_line, count, route_name, vtype in all_flows:
                    time_groups[start_time].append((route_name, vtype, count))
                
                print(f"\n    SUMMARY for Day {day}:")
                print(f"      • Total routes: {len(route_stats)}")
                print(f"      • Total flows: {flow_id_counter}")
                print(f"      • Total vehicles: {total_vehicles}")
                
                # Show time grouping
                print(f"\n   Flow Distribution by Time Interval:")
                for time in sorted(time_groups.keys()):
                    flows_in_interval = time_groups[time]
                    total_vehicles_in_interval = sum(f[2] for f in flows_in_interval)
                    print(f"      • {time}-{time+900}s: {len(flows_in_interval)} flows, {total_vehicles_in_interval} vehicles")
                
                print(f"\n   File saved: {output_file}")
                
                # Create detailed summary
                create_detailed_summary(all_flows, day)
            else:
                print(f"    No flows generated for Day {day}")
                
        except Exception as e:
            print(f"    Error processing {file_name}: {str(e)}")
    
    print(f"\n{'='*70}")
    print("✅ PROCESSING COMPLETE - FLOWS SORTED BY TIME!")
    print("="*70)

def create_detailed_summary(all_flows, day_number):
    """Create a detailed summary CSV showing flows by time interval"""
    summary_dir = "flow_summaries_detailed"
    os.makedirs(summary_dir, exist_ok=True)
    
    # Organize data by time interval
    time_intervals = {}
    for start_time, flow_line, count, route_name, vtype in all_flows:
        interval_key = f"{start_time}-{start_time+900}"
        
        if interval_key not in time_intervals:
            time_intervals[interval_key] = []
        
        time_intervals[interval_key].append({
            'Day': day_number,
            'Time_Interval': interval_key,
            'Route': route_name,
            'Vehicle_Type': vtype,
            'Vehicles': count,
            'Start_Time': start_time
        })
    
def main_sorted():
    """Main function for sorted flows"""
    print("\n" + "="*70)
    print("MATSim Flow Generator - Time-Sorted Flows")
    print("="*70)
    print("\nThis version will:")
    print("1. Process ALL routes from Excel sheets")
    print("2. Sort flows by START TIME (ascending)")
    print("3. Group flows from same time intervals together")
    print("4. Generate properly ordered SUMO XML")
    
    # Verify files
    found_files = []
    for day in range(1, 6):
        patterns = [
            f"OD_15min_Day_{day}.xlsx",
            f"Day_{day}.xlsx",
            f"Day{day}.xlsx"
        ]
        for pattern in patterns:
            if os.path.exists(pattern):
                found_files.append((day, pattern))
                print(f"\n Found: {pattern}")
                break
    
    if not found_files:
        print("\n No Excel files found!")
        return
    
    print(f"\n Found {len(found_files)} day(s) of data")
    print("\nStarting processing with time sorting...")
    
    # Generate sorted flows
    generate_flows_sorted_by_time()
    
    print(f"\n{'='*70}")
    print(" ALL DONE - FLOWS ARE TIME-SORTED!")
  
# Run the sorted version
if __name__ == "__main__":
    main_sorted()