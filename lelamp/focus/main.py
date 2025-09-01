import datetime
import sys
import os
import threading
import time
import json
import csv

# Add the project root to the python path to allow imports from other services
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lelamp.service.rgb import RGBService
from lelamp.service.motors import MotorsService
from lelamp.focus.focus_service import FocusService
from lelamp.follower import LeLampFollower, LeLampFollowerConfig
from lerobot.utils.robot_utils import busy_wait

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

def input_listener(focus_service, motors_service):
    """Listens for user input to trigger actions."""
    while True:
        try:
            user_input = input("\nEnter '1' to play a recorded action, or 'q' to quit listener: ")
            if user_input == '1':
                focus_service.pause()
                print("\n--- Playing recorded action: curious_lelamp ---")
                motors_service.dispatch("play", 'curious_lelamp')
                motors_service.wait_until_idle(timeout=30) # Wait for action to complete
                print("--- Action replay finished ---")
                focus_service.resume()
            elif user_input.lower() == 'q':
                print("Stopping input listener.")
                break
        except (EOFError, KeyboardInterrupt):
            # This handles cases where the main program exits and closes stdin
            break

def main():
    # Load parameters from config file
    params = load_params_from_config()
    if not params:
        print("Exiting due to configuration error.")
        return

    print("\nInitializing services...")
    rgb_service = RGBService()
    motors_service = MotorsService(port=params['lamp_port'], lamp_id=params['lamp_id'])
    
    rgb_service.start()
    motors_service.start()

    focus_service = FocusService(rgb_service)

    try:
        print(f"Calculating light schedule with parameters: {params}")
        schedule = focus_service.calculate_light_schedule(**{k: v for k, v in params.items() if k not in ['lamp_port', 'lamp_id']})

        if schedule:
            # Run the focus session in a separate thread
            session_thread = threading.Thread(target=focus_service.run_focus_session, args=(schedule,))
            session_thread.start()
            print("Focus session started in the background.")

            # Start the input listener in a daemon thread
            listener_thread = threading.Thread(target=input_listener, args=(focus_service, motors_service), daemon=True)
            listener_thread.start()

            # Keep the main thread alive while the session is running
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
