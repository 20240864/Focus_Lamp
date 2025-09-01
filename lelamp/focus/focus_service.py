import time
import sys
import os
import math
import threading

# Add the project root to the python path to allow imports from other services
# 允许从其他服务导入
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from lelamp.service.rgb import RGBService
from lelamp.service.base import Priority

# --- Color Temperature and Brightness Conversion Functions ---
# 色温与亮度转换函数
def kelvin_to_rgb(temp_kelvin):
    """
    Converts Kelvin temperature to an RGB color tuple.
    Algorithm by Tanner Helland.
    """
    temp = temp_kelvin / 100.0
    # 色温转换为RGB
    # 色温范围：1000K-6500K
    if temp <= 66:
        red = 255
        green = 99.4708025861 * math.log(temp) - 161.1195681661
    else:
        red = 329.698727446 * ((temp - 60) ** -0.1332047592)
        green = 288.1221695283 * ((temp - 60) ** -0.0755148492)
    
    # 色温转换为RGB
    # 色温范围：1000K-6500K
    if temp >= 66:
        blue = 255
    elif temp <= 19:
        blue = 0
    else:
        blue = 138.5177312231 * math.log(temp - 10) - 305.0447927307

    return (
        int(max(0, min(255, red))),
        int(max(0, min(255, green))),
        int(max(0, min(255, blue)))
    )

# 亮度与色温转换函数
def illuminance_to_brightness(illuminance_lx, max_illuminance=750):
    """
    Converts illuminance in Lux to a brightness factor (0.0 to 1.0).
    Assumes a linear relationship and a known maximum illuminance for the lamp.
    """
    return max(0.0, min(1.0, illuminance_lx / max_illuminance))

def apply_brightness(rgb_color, brightness_factor):
    """
    Applies a brightness factor to an RGB color.
    """
    r, g, b = rgb_color
    return (
        int(r * brightness_factor),
        int(g * brightness_factor),
        int(b * brightness_factor)
    )

# 焦点服务类
# 实现焦点照明计划的数学算法
class FocusService:
    """
    Implements the mathematical algorithm for determining focus lighting schedules.
    """
    def __init__(self, rgb_service: RGBService):
        self.rgb_service = rgb_service
        self._running_event = threading.Event()
        self._running_event.set()  # Set to running by default

    def calculate_light_schedule(self, start_hour, start_minute, total_duration_min, fatigue_level, focus_mode_m):
        """
        Calculates the duration and light parameters for each phase of the focus session.
        
        :param start_hour: Task start hour (0-23)
        :param start_minute: Task start minute (0-59)
        :param total_duration_min: Total task duration in minutes
        :param fatigue_level: Fatigue level (1-5)
        :param focus_mode_m: Focus mode (-1 for divergent, 1 for convergent)
        :return: A list of tuples, where each tuple is (duration_seconds, cct_k, illuminance_lx)
        """
        
        # 1. Intermediate variables
        c = start_hour * 60 + start_minute
        t = total_duration_min
        f = fatigue_level
        M = focus_mode_m
        
        t_before_17 = max(0, min(c + t, 1020) - c)

        # 2. Calculate T_wakeup
        T_wakeup = 0
        if start_hour >= 17:
            T_wakeup = 0
        elif 12 <= start_hour < 17:
            if f == 5:
                T_wakeup = 0.20 * t
            elif f == 4:
                T_wakeup = 0.15 * t
            else: # f in {1,2,3}
                T_wakeup = 0
        else: # start_hour < 12
            factor1 = 0.7 + 0.1 * f
            factor2 = 30 - 0.0833 * max(c - 480, 0)
            T_wakeup = t * (factor1 * factor2) / 100

        # 3. Calculate T_moderate
        P_moderate = 0.75 * M + 0.25 * (t_before_17 / t if t > 0 else 0)
        T_moderate = t * max(0, P_moderate)

        # 4. Calculate T_low
        T_low = t - T_wakeup - T_moderate
        
        # Ensure no negative durations
        T_wakeup = max(0, T_wakeup)
        T_moderate = max(0, T_moderate)
        T_low = max(0, T_low)

        # 5. Define light parameters for each phase
        schedule = []
        
        # Phase 1: Wakeup
        if T_wakeup > 0:
            schedule.append((T_wakeup * 60, 5800, 750))
            
        # Phase 2: Moderate
        if T_moderate > 0:
            if t > 90:
                schedule.append((T_moderate * 60, 3000, 750))
            else:
                schedule.append((T_moderate * 60, 4500, 450))
                
        # Phase 3: Low
        if T_low > 0:
            schedule.append((T_low * 60, 3000, 250))
            
        return schedule

    def run_focus_session(self, schedule):
        """
        Executes a focus session based on a calculated schedule.
        """
        if not self.rgb_service.is_running:
            print("Error: RGBService is not running. Please start it first.")
            return
            
        print("Starting focus session...")
        total_duration = sum(item[0] for item in schedule)
        print(f"Total estimated duration: {total_duration / 60:.2f} minutes.")

        for i, (duration_sec, cct, lux) in enumerate(schedule):
            print(f"--- Phase {i+1}/{len(schedule)} ---")
            print(f"Duration: {duration_sec / 60:.2f} minutes")
            print(f"Color Temperature: {cct}K")
            print(f"Illuminance: {lux} lx")

            # Convert CCT and Lux to RGB color
            base_rgb = kelvin_to_rgb(cct)
            brightness = illuminance_to_brightness(lux)
            final_rgb = apply_brightness(base_rgb, brightness)
            
            print(f"Calculated Brightness: {brightness:.2f}")
            print(f"Calculated RGB: {final_rgb}")

            # Dispatch to RGB service
            self.rgb_service.dispatch("solid", final_rgb, Priority.NORMAL)
            
            # Wait for the duration of the phase, checking for pause events
            start_time = time.time()
            while time.time() - start_time < duration_sec:
                self._running_event.wait()  # Blocks if paused
                time.sleep(0.1)  # Check every 100ms
            
        print("--- Focus session completed! ---")

    def pause(self):
        """Pauses the focus session."""
        self._running_event.clear()
        print("Focus session paused.")

    def resume(self):
        """Resumes the focus session."""
        self._running_event.set()
        print("Focus session resumed.")


def run_example_scenario():
    """
    An example scenario demonstrating the FocusService.
    """
    print("Initializing services...")
    rgb_service = RGBService()
    rgb_service.start()
    
    focus_service = FocusService(rgb_service)

    try:
        # --- Scenario Parameters ---
        # As per the logic file:
        # start_hour, start_minute, total_duration_min, fatigue_level, focus_mode_m
        params = {
            "start_hour": 14,
            "start_minute": 0,
            "total_duration_min": 120,
            "fatigue_level": 4,
            "focus_mode_m": 1 # Convergent thinking
        }
        
        print(f"\nCalculating schedule with parameters: {params}")
        schedule = focus_service.calculate_light_schedule(**params)
        
        if not schedule:
            print("No valid schedule generated for the given parameters.")
        else:
            focus_service.run_focus_session(schedule)

    finally:
        print("\nCleaning up and stopping services...")
        rgb_service.stop()
        print("Services stopped.")


if __name__ == "__main__":
    # This will run the example scenario.
    # In a real application, you would integrate this with a UI or other triggers.
    run_example_scenario()