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

def input_listener(motors_service: MotorsService, available_actions: list):
    """Waits for user input and dispatches events to the motors service"""
    while True:
        try:
            user_input = input(
                "Enter a number to play an action (1-5), or 'q' to quit: "
            )
            if user_input.lower() == "q":
                break

            action_index = int(user_input) - 1
            if 0 <= action_index < len(available_actions):
                action_name = available_actions[action_index]
                print(f"Playing action: {action_name}")
                motors_service.dispatch("play", action_name)
            else:
                print("Invalid number. Please try again.")

        except (ValueError, IndexError):
            print("Invalid input. Please enter a number from the list.")
        except Exception as e:
            print(f"An error occurred: {e}")


def main():
    """Main function"""
    logging.basicConfig(level=logging.INFO)
    lamp_id = "lelamp"
    motors_service = MotorsService(port="COM3", lamp_id=lamp_id)
    motors_service.start()

    # Go to home position at startup
    print("Initializing lamp to home position...")
    motors_service.dispatch("go_home")
    print("Initialization complete.")

    # Get available actions
    available_actions = motors_service.get_available_recordings()
    if not available_actions:
        print("No recordings found for this lamp.")
    else:
        print("Available actions:")
        for i, action in enumerate(available_actions):
            print(f"  {i+1}: {action}")

    # Start input listener thread
    listener_thread = threading.Thread(
        target=input_listener, args=(motors_service, available_actions)
    )
    listener_thread.daemon = True
    listener_thread.start()

    try:
        # Keep the main thread alive to allow services and listeners to run
        while listener_thread.is_alive():
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        motors_service.stop()
        print("Shutdown complete.")


if __name__ == "__main__":
    main()
