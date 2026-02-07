#!/usr/bin/env python3
"""
MINIMAL TRAFFIC LIGHT CONTROL FOR SUMO
Fixed version with static logic override
"""

import traci
import sys

# Configuration
SUMO_CONFIG = "simulation.sumocfg"
USE_GUI = True
SIMULATION_TIME = 58500

# Traffic light configurations
TRAFFIC_LIGHTS = {
    "T1": 3,
    "T2": 2,
    "T3": 3,
    "T4": 2,
    "T5": 1
}

# Phase definitions
PHASE_1 = {
    "T1": [("rrr", 15), ("ggg", 40), ("yyy", 5)],  # 45 total: 40 green + 5 yellow
    "T2": [("rr", 60)],
    "T3": [("rrr", 60)],
    "T4": [("gg", 55), ("yy", 5)],  # 60 total: 55 green + 5 yellow
    "T5": [("g", 10), ("r", 15), ("g", 25), ("y", 5)]  # 55 total: 35 green + 5 yellow
}

PHASE_2 = {
    "T1": [("rrr", 15), ("ggg", 40), ("yyy", 5)],  # 45 green becomes 40 + 5 yellow
    "T2": [("gg", 55), ("yy", 5)],  # 60 total: 55 green + 5 yellow
    "T3": [("rrr", 60)],
    "T4": [("rr", 60)],
    "T5": [("g", 10), ("r", 15), ("g", 25), ("y", 5)]  # 55 total: 35 green + 5 yellow
}

PHASE_3 = {
    "T1": [("rrr", 30), ("ggg", 10), ("yyy", 5), ("rrr", 15)],  # 15 green becomes 10 + 5 yellow
    "T2": [("rr", 60)],
    "T3": [("ggg", 55), ("yyy", 5)],  # 60 total: 55 green + 5 yellow
    "T4": [("rr", 60)],
    "T5": [("g", 10), ("r", 15), ("g", 25), ("y", 5)]  # 55 total: 35 green + 5 yellow
}

PHASES = [
    {"duration": 60, "patterns": PHASE_1, "name": "Phase 1"},
    {"duration": 60, "patterns": PHASE_2, "name": "Phase 2"},
    {"duration": 60, "patterns": PHASE_3, "name": "Phase 3"}
]

def validate_state(tl_id, state):
    """Validate traffic light state matches expected length"""
    expected_len = TRAFFIC_LIGHTS.get(tl_id, 0)
    if len(state) != expected_len:
        print(f"ERROR: {tl_id} expects {expected_len} signals, got '{state}' (len={len(state)})")
        if expected_len == 3:
            return "rrr"
        elif expected_len == 2:
            return "rr"
        else:
            return "r"
    return state

def run_simulation():
    """Main simulation loop"""
    
    print("Starting SUMO with traffic light control...")
    
    # Start SUMO - REMOVE --quit-on-end flag
    sumo_binary = "sumo-gui" if USE_GUI else "sumo"
    sumo_cmd = [sumo_binary, "-c", SUMO_CONFIG]  # Removed --start and --quit-on-end
    
    try:
        traci.start(sumo_cmd)
        print("SUMO started successfully")
        
        # Check which traffic lights exist
        existing_tls = []
        all_tls = traci.trafficlight.getIDList()
        
        print(f"\nAvailable traffic lights in network: {all_tls}")
        
        for tl_id in TRAFFIC_LIGHTS.keys():
            if tl_id in all_tls:
                existing_tls.append(tl_id)
                # TAKE CONTROL FROM STATIC LOGIC - ADD THIS LINE
                traci.trafficlight.setProgram(tl_id, "0")  # Offline mode
                print(f"✓ {tl_id}: Took control from static logic")
            else:
                print(f"✗ {tl_id}: Not found in network")
        
        if not existing_tls:
            print("\nERROR: No traffic lights found!")
            traci.close()
            return
        
        print(f"\nControlling traffic lights: {existing_tls}")
        
        # Initialize
        current_phase = 0
        phase_start_time = 0
        step = 0
        
        # Run one simulation step before setting states
        traci.simulationStep()
        
        # Set initial states
        print("\nSetting initial states for Phase 1...")
        current_phase_data = PHASES[current_phase]
        for tl_id in existing_tls:
            if tl_id in current_phase_data["patterns"]:
                pattern = current_phase_data["patterns"][tl_id]
                if pattern:
                    state = pattern[0][0]
                    valid_state = validate_state(tl_id, state)
                    traci.trafficlight.setRedYellowGreenState(tl_id, valid_state)
                    print(f"  {tl_id} → {valid_state}")
        
        # Main simulation loop
        while step < SIMULATION_TIME and traci.simulation.getMinExpectedNumber() > 0:
            traci.simulationStep()
            
            time_in_phase = step - phase_start_time
            current_phase_data = PHASES[current_phase]
            
            # Check for phase change
            if time_in_phase >= current_phase_data["duration"]:
                current_phase = (current_phase + 1) % len(PHASES)
                phase_start_time = step
                current_phase_data = PHASES[current_phase]
                
                print(f"\n[Step {step}] Switching to {current_phase_data['name']}")
                
                # Apply new phase
                for tl_id in existing_tls:
                    if tl_id in current_phase_data["patterns"]:
                        pattern = current_phase_data["patterns"][tl_id]
                        if pattern:
                            state = pattern[0][0]
                            valid_state = validate_state(tl_id, state)
                            traci.trafficlight.setRedYellowGreenState(tl_id, valid_state)
                            print(f"  {tl_id} → {valid_state}")
            
            # Update each traffic light based on pattern
            for tl_id in existing_tls:
                if tl_id in current_phase_data["patterns"]:
                    pattern = current_phase_data["patterns"][tl_id]
                    
                    # Find current state based on elapsed time
                    elapsed = time_in_phase
                    for state, duration in pattern:
                        if elapsed < duration:
                            valid_state = validate_state(tl_id, state)
                            current_state = traci.trafficlight.getRedYellowGreenState(tl_id)
                            if current_state != valid_state:
                                traci.trafficlight.setRedYellowGreenState(tl_id, valid_state)
                            break
                        elapsed -= duration
            
            # Status update
            if step % 30 == 0:
                states = []
                for tl_id in sorted(existing_tls):
                    try:
                        state = traci.trafficlight.getRedYellowGreenState(tl_id)
                        states.append(f"{tl_id}:{state}")
                    except:
                        states.append(f"{tl_id}:ERROR")
                
                phase_info = f"{current_phase_data['name']} ({time_in_phase}/{current_phase_data['duration']}s)"
                print(f"[Step {step}] {phase_info}: {' | '.join(states)}")
            
            step += 1
        
        print(f"\nSimulation completed after {step} steps!")
        
    except traci.exceptions.FatalTraCIError as e:
        print(f"\nSUMO Error: {e}")
        print("\nThis usually means:")
        print("1. Invalid traffic light state (wrong length or characters)")
        print("2. SUMO crashed due to network issues")
        print("\nCheck that your traffic light states match the number of signals.")
    
    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}")
    
    finally:
        try:
            traci.close()
            print("SUMO closed")
        except:
            pass

if __name__ == "__main__":
    run_simulation()