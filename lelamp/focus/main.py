import datetime
import sys
import os
import threading
import time

# Add the project root to the python path to allow imports from other services
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lelamp.service.rgb import RGBService
from lelamp.focus.focus_service import FocusService


def get_user_input():
    """Get task parameters from user input in the terminal."""
    print("Please provide the details for your focus session.")

    # Task Duration
    while True:
        try:
            duration_str = input("- Enter total task duration in minutes: ")
            duration = int(duration_str)
            if duration > 0:
                break
            else:
                print("  Invalid input. Duration must be a positive integer.")
        except ValueError:
            print("  Invalid input. Please enter a whole number.")

    # Fatigue Level
    while True:
        try:
            fatigue_str = input("- Enter user fatigue level (1-5): ")
            fatigue = int(fatigue_str)
            if 1 <= fatigue <= 5:
                break
            else:
                print("  Invalid input. Please enter a number between 1 and 5.")
        except ValueError:
            print("  Invalid input. Please enter a whole number.")

    # Focus Mode
    while True:
        try:
            mode_str = input("- Enter focus mode (1 for 'focus', -1 for 'divergent'): ")
            mode = int(mode_str)
            if mode in [-1, 1]:
                break
            else:
                print("  Invalid input. Please enter 1 or -1.")
        except ValueError:
            print("  Invalid input. Please enter a whole number.")

    # Start time
    hour, minute = get_start_time()

    return {
        "start_hour": hour,
        "start_minute": minute,
        "total_duration_min": duration,
        "fatigue_level": fatigue,
        "focus_mode_m": mode,
    }

def get_start_time():
    """Get the task start time from the user."""
    while True:
        use_current = input("- Use current time as start time? (Y/n): ").lower().strip()
        if use_current in ['y', 'yes', '']:
            now = datetime.datetime.now()
            return now.hour, now.minute
        elif use_current in ['n', 'no']:
            # Get hour
            while True:
                try:
                    hour_str = input("  - Enter task start hour (0-23): ")
                    hour = int(hour_str)
                    if 0 <= hour <= 23:
                        break
                    else:
                        print("    Invalid input. Please enter a number between 0 and 23.")
                except ValueError:
                    print("    Invalid input. Please enter a whole number.")
            # Get minute
            while True:
                try:
                    minute_str = input("  - Enter task start minute (0-59): ")
                    minute = int(minute_str)
                    if 0 <= minute <= 59:
                        break
                    else:
                        print("    Invalid input. Please enter a number between 0 and 59.")
                except ValueError:
                    print("    Invalid input. Please enter a whole number.")
            return hour, minute
        else:
            print("  Invalid choice. Please enter 'y' or 'n'.")


def main():
    # Get parameters from user
    params = get_user_input()

    print("\nInitializing services...")
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
