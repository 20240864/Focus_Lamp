import datetime
import sys
import os
import threading
import time
import json
import csv
import logging

# Add the project root to the python path to allow imports from other services
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lelamp.service.rgb import RGBService
from lelamp.service.motors import MotorsService
from lelamp.focus.focus_service import FocusService

# 从JSON文件加载参数
def load_params_from_config():
    """Load task parameters from a JSON config file."""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'focus_config.json')
    print(f"Loading parameters from {config_path}")
    try:
        with open(config_path, 'r') as f:
            params = json.load(f)
        
        # Validate parameters
        required_keys = ["start_hour", "start_minute", "total_duration_min", "fatigue_level", "focus_mode_m", "lamp_port", "lamp_id"]
        if not all(k in params for k in required_keys):
            print("Config file is missing one or more required parameters.")
            return None
            
        return params
    except FileNotFoundError:
        print(f"Error: Configuration file not found at {config_path}")
        return None
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {config_path}")
        return None

def input_listener(focus_service: FocusService, motors_service: MotorsService, available_actions: list):
    """Waits for user input, pauses focus service, and plays actions."""
    while True:
        try:
            user_input = input(
                "Enter a number to play an action, or 'q' to quit: "
            )
            if user_input.lower() == "q":
                break

            action_index = int(user_input) - 1
            if 0 <= action_index < len(available_actions):
                action_name = available_actions[action_index]
                
                print(f"--- Pausing light sequence to play action: {action_name} ---")
                focus_service.pause()
                
                motors_service.dispatch("play", action_name)
                # Wait for the action to complete
                while motors_service.is_playing():
                    time.sleep(0.1)
                
                print("--- Action finished, returning to home position ---")
                motors_service.dispatch("go_home", None)
                while motors_service.is_homing():
                    time.sleep(0.1)

                print("--- Resuming light sequence ---")
                focus_service.resume()
            else:
                print("Invalid number. Please try again.")

        except (ValueError, IndexError):
            print("Invalid input. Please enter a number from the list.")
        except Exception as e:
            print(f"An error occurred during input handling: {e}")

def main():
    """Main function to initialize services and run the focus session."""
    logging.basicConfig(level=logging.INFO)
    
    params = load_params_from_config()
    if not params:
        print("Exiting due to configuration error.")
        return

    print("\nInitializing services...")
    rgb_service = RGBService()
    motors_service = MotorsService(port=params['lamp_port'], lamp_id=params['lamp_id'])
    
    rgb_service.start()
    motors_service.start()

    # Initialize lamp to home position first
    print("Initializing lamp to home position...")
    motors_service.dispatch("go_home", None)
    # Wait for homing to complete
    while motors_service.is_homing():
        time.sleep(0.1)
    print("Initialization complete.")

    focus_service = FocusService(rgb_service)

    try:
        print(f"Calculating light schedule with parameters: {params}")
        schedule = focus_service.calculate_light_schedule(**{k: v for k, v in params.items() if k not in ['lamp_port', 'lamp_id']})

        if schedule:
            session_thread = threading.Thread(target=focus_service.run_focus_session, args=(schedule,))
            session_thread.start()
            print("Focus session started in the background.")

            available_actions = motors_service.get_available_recordings()
            if available_actions:
                print("\nAvailable actions:")
                for i, action in enumerate(available_actions):
                    print(f"  {i+1}: {action}")
                
                listener_thread = threading.Thread(target=input_listener, args=(focus_service, motors_service, available_actions), daemon=True)
                listener_thread.start()
            else:
                print("No recordings found for this lamp.")

            session_thread.join()
        else:
            print("Failed to generate a valid schedule.")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        print("\nShutting down services...")
        motors_service.stop()
        rgb_service.stop()
        print("Services stopped.")

if __name__ == "__main__":
    main()
