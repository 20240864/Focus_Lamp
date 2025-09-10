import argparse
import time
import csv
import os
import sys

# Add the project root to the python path to allow imports from other services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lelamp.service.rgb import RGBService
from lelamp.follower import LeLampFollowerConfig, LeLampFollower
# 注意：这些函数现在已经整合到 test/main.py 中
# 如果需要使用这些函数，请从 main.py 导入或复制函数定义
# from lelamp.test.main import kelvin_to_rgb, illuminance_to_brightness, apply_brightness

# 临时解决方案：在此文件中重新定义这些函数
import math

def kelvin_to_rgb(temp_kelvin):
    """将开尔文色温转换为RGB颜色元组"""
    temp = temp_kelvin / 100.0
    
    if temp <= 66:
        red = 255
        green = 99.4708025861 * math.log(temp) - 161.1195681661
    else:
        red = 329.698727446 * ((temp - 60) ** -0.1332047592)
        green = 288.1221695283 * ((temp - 60) ** -0.0755148492)
    
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

def illuminance_to_brightness(illuminance_lx, max_illuminance=750):
    """将照度（勒克斯）转换为亮度因子（0.0到1.0）"""
    return min(1.0, max(0.0, illuminance_lx / max_illuminance))

def apply_brightness(rgb_color, brightness_factor):
    """将亮度因子应用到RGB颜色"""
    r, g, b = rgb_color
    return (int(r * brightness_factor), int(g * brightness_factor), int(b * brightness_factor))
from lerobot.utils.robot_utils import busy_wait

def execute_teachers_day_action(robot, lamp_id, fps=30):
    """Execute the teachers_day action using CSV replay method"""
    print("\n=== Executing Teachers Day Action ===")
    
    # Build CSV filename for teachers_day action
    recordings_dir = os.path.join(os.path.dirname(__file__), "recordings")
    csv_filename = f"teachers_day_{lamp_id}.csv"
    csv_path = os.path.join(recordings_dir, csv_filename)
    
    try:
        # Read CSV file and replay actions
        with open(csv_path, 'r') as csvfile:
            csv_reader = csv.DictReader(csvfile)
            actions = list(csv_reader)
        
        print(f"Replaying {len(actions)} actions from {csv_path}")
        
        for row in actions:
            t0 = time.perf_counter()
            
            # Extract action data (exclude timestamp column)
            action = {key: float(value) for key, value in row.items() if key != 'timestamp'}
            robot.send_action(action)
            
            busy_wait(1.0 / fps - (time.perf_counter() - t0))
        
        print("Teachers Day action completed!")
        return True
        
    except FileNotFoundError:
        print(f"Error: Action file not found: {csv_path}")
        print(f"Please make sure the file 'teachers_day_{lamp_id}.csv' exists in the recordings directory.")
        return False
    except Exception as e:
        print(f"Error executing teachers_day action: {e}")
        return False

def maintain_servo_stability(robot, duration_seconds=30):
    """Maintain servo stability by sending the current position repeatedly"""
    print(f"\n=== Maintaining servo stability for {duration_seconds} seconds ===")
    
    try:
        # Get current position
        current_action = robot.get_action()
        print(f"Current servo positions: {current_action}")
        
        start_time = time.time()
        while time.time() - start_time < duration_seconds:
            # Send current position to maintain stability
            robot.send_action(current_action)
            time.sleep(0.1)  # Send position updates every 100ms
        
        print("Servo stability maintenance completed.")
        
    except Exception as e:
        print(f"Error maintaining servo stability: {e}")

def set_white_light(rgb_service):
    """Set bright white light at the beginning"""
    print("\n=== Setting initial white light ===")
    
    try:
        # Set bright white light (6500K color temperature, high brightness)
        white_cct_k = 6500  # Cool white color temperature
        white_lux = 800     # High brightness
        
        # Convert to RGB values
        base_rgb = kelvin_to_rgb(white_cct_k)
        brightness = illuminance_to_brightness(white_lux)
        white_rgb = apply_brightness(base_rgb, brightness)
        
        print(f"Setting white light: CCT={white_cct_k}K, Lux={white_lux}, RGB={white_rgb}")
        
        # Apply white light
        rgb_service.dispatch("solid", white_rgb)
        
        print("White light set successfully.")
        
    except Exception as e:
        print(f"Error setting white light: {e}")

def set_rainbow_light(rgb_service, duration_seconds=30):
    """Set rainbow color cycling effect for specified duration"""
    print(f"\n=== Setting rainbow light for {duration_seconds} seconds ===")
    
    try:
        import math
        
        start_time = time.time()
        while time.time() - start_time < duration_seconds:
            # Calculate current time position in the cycle (0 to 1)
            elapsed = time.time() - start_time
            cycle_position = (elapsed * 0.5) % 1.0  # Complete cycle every 2 seconds
            
            # Convert to HSV and then RGB for smooth rainbow transition
            hue = cycle_position * 360  # 0 to 360 degrees
            
            # Simple HSV to RGB conversion for rainbow effect
            def hsv_to_rgb(h, s, v):
                h = h / 60.0
                c = v * s
                x = c * (1 - abs((h % 2) - 1))
                m = v - c
                
                if 0 <= h < 1:
                    r, g, b = c, x, 0
                elif 1 <= h < 2:
                    r, g, b = x, c, 0
                elif 2 <= h < 3:
                    r, g, b = 0, c, x
                elif 3 <= h < 4:
                    r, g, b = 0, x, c
                elif 4 <= h < 5:
                    r, g, b = x, 0, c
                else:
                    r, g, b = c, 0, x
                
                return (int((r + m) * 255), int((g + m) * 255), int((b + m) * 255))
            
            # Generate rainbow RGB with full saturation and brightness
            rainbow_rgb = hsv_to_rgb(hue, 1.0, 1.0)
            
            # Apply rainbow color
            rgb_service.dispatch("solid", rainbow_rgb)
            
            # Update every 50ms for smooth transition
            time.sleep(0.05)
        
        print("Rainbow light period completed.")
        
    except Exception as e:
        print(f"Error setting rainbow light: {e}")

def main():
    """Main function to execute teachers_day action with servo stability and warm light"""
    parser = argparse.ArgumentParser(description="Execute Teachers Day action with servo stability and warm light")
    parser.add_argument('--id', type=str, required=True, help='ID of the lamp')
    parser.add_argument('--port', type=str, required=True, help='Serial port for the lamp')
    parser.add_argument('--fps', type=int, default=30, help='Frames per second for action replay (default: 30)')
    parser.add_argument('--servo-time', type=int, default=30, help='Servo stability duration in seconds (default: 30)')
    parser.add_argument('--light-time', type=int, default=30, help='Rainbow light duration in seconds (default: 30)')
    args = parser.parse_args()

    print("\n=== Teachers Day Script Started ===")
    print(f"Lamp ID: {args.id}")
    print(f"Port: {args.port}")
    print(f"Action FPS: {args.fps}")
    print(f"Servo stability time: {args.servo_time} seconds")
    print(f"Rainbow light time: {args.light_time} seconds")
    
    # Initialize RGB service
    print("\nInitializing RGB service...")
    rgb_service = RGBService()
    rgb_service.start()
    
    # Set initial white light
    set_white_light(rgb_service)
    
    # Initialize robot
    print("Initializing robot connection...")
    robot_config = LeLampFollowerConfig(port=args.port, id=args.id)
    robot = LeLampFollower(robot_config)
    robot.connect(calibrate=False)
    
    try:
        # Step 1: Execute teachers_day action
        success = execute_teachers_day_action(robot, args.id, args.fps)
        
        if success:
            # Step 2: Maintain servo stability for specified duration
            maintain_servo_stability(robot, args.servo_time)
            
            # Step 3: Set rainbow light for specified duration
            set_rainbow_light(rgb_service, args.light_time)
        else:
            print("Skipping servo stability and warm light due to action execution failure.")
        
        print("\n=== Teachers Day Script Completed Successfully ===")
        
    except KeyboardInterrupt:
        print("\n=== Script interrupted by user ===")
    except Exception as e:
        print(f"\n=== Script error: {e} ===")
    finally:
        # Cleanup
        print("\nCleaning up...")
        try:
            robot.disconnect()
            print("Robot disconnected.")
        except Exception as e:
            print(f"Error disconnecting robot: {e}")
        
        try:
            rgb_service.stop()
            print("RGB service stopped.")
        except Exception as e:
            print(f"Error stopping RGB service: {e}")
        
        print("=== Cleanup completed ===")

if __name__ == "__main__":
    main()