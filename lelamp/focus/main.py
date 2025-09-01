import datetime
import sys
import os
import threading
import time
import json

# Add the project root to the python path to allow imports from other services
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lelamp.service.rgb import RGBService
from lelamp.focus.focus_service import FocusService


def load_params_from_config():
    """Load task parameters from a JSON config file."""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'focus_config.json')
    print(f"Loading parameters from {config_path}")
    try:
        with open(config_path, 'r') as f:
            params = json.load(f)
        
        # Optional: Validate parameters if needed
        if not all(k in params for k in ["start_hour", "start_minute", "total_duration_min", "fatigue_level", "focus_mode_m"]):
            print("Config file is missing one or more required parameters.")
            return None
            
        return params
    except FileNotFoundError:
        print(f"Error: Configuration file not found at {config_path}")
        return None
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {config_path}")
        return None


def main():
    # Load parameters from config file
    params = load_params_from_config()
    if not params:
        print("Exiting due to configuration error.")
        return

    print("Initializing services...")
    # Directly initialize RGBService, same as in test_rgb.py
    rgb_service = RGBService()


    rgb_service.start()

    focus_service = FocusService(rgb_service)

    try:
        print(f"Calculating light schedule with parameters: {params}")
        schedule = focus_service.calculate_light_schedule(**params)

        if schedule:
            # Run the focus session in a separate thread to keep the main thread responsive
            session_thread = threading.Thread(target=focus_service.run_focus_session, args=(schedule,))
            session_thread.start()
            print("Focus session started in the background.")
            # Keep the main thread alive while the session is running
            session_thread.join()
        else:
            print("Failed to generate a valid schedule.")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        print("Shutting down services...")
        rgb_service.stop()
        print("Services stopped.")


if __name__ == "__main__":
    main()
