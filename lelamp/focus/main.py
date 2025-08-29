import argparse
import datetime
from lelamp.service.rgb.rgb_service import RGBService
from lelamp.focus.focus_service import FocusService
import threading
import time

def main():
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="Run a focus lamp session.")
    # 任务开始时间
    # 任务开始时间，默认当前时间
    parser.add_argument("--hour", type=int, default=datetime.datetime.now().hour, help="Task start hour (0-23). Default is current hour.")
    # 任务开始分钟
    parser.add_argument("--minute", type=int, default=datetime.datetime.now().minute, help="Task start minute (0-59). Default is current minute.")
    # 任务持续时间
    parser.add_argument("--duration", type=int, required=True, help="Total task duration in minutes.")
    # 任务疲劳等级
    parser.add_argument("--fatigue", type=int, required=True, choices=range(1, 6), help="User fatigue level (1-5).")
    # 任务模式
    # 1 专注模式
    # -1 发散模式
    parser.add_argument("--mode", type=int, required=True, choices=[-1, 1], help="Focus mode: 1 for 'focus', -1 for 'divergent'.")
    
    # 解析参数
    args = parser.parse_args()

    print("Initializing services...")
    # We need a mock RGBService if we are not on a Raspberry Pi
    try:
        rgb_service = RGBService()
    except (ImportError, RuntimeError):
        print("Could not initialize RPi.GPIO. Using a mock RGBService.")
        class MockRGBService:
            def dispatch(self, event_type, payload):
                print(f"MockRGBService: Dispatched event '{event_type}' with payload {payload}")
            def start(self):
                print("MockRGBService: Started.")
            # 模拟停止方法
            def stop(self):
                print("MockRGBService: Stopped.")
        rgb_service = MockRGBService()


    rgb_service.start()

    focus_service = FocusService(rgb_service)

    params = {
        "start_hour": args.hour,
        "start_minute": args.minute,
        "total_duration_min": args.duration,
        "fatigue_level": args.fatigue,
        "focus_mode_m": args.mode,
    }

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
