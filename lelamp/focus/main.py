import datetime
import sys
import os
import threading
import time
import json
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

def main():
    """Main function to initialize services and run the focus session."""
    logging.basicConfig(level=logging.INFO)
    
    params = load_params_from_config()
    if not params:
        print("Exiting due to configuration error.")
        return

    print("\n=== 启动Focus Lamp系统 ===")
    rgb_service = RGBService()
    motors_service = MotorsService(port=params['lamp_port'], lamp_id=params['lamp_id'])
    focus_service = FocusService(rgb_service)
    
    rgb_service.start()
    motors_service.start()

    # 步骤1: 执行nod动作并设定为home状态
    print("\n步骤1: 执行nod动作并设定home状态...")
    motors_service.dispatch("play", "nod")
    while motors_service.is_playing():
        time.sleep(0.1)
    
    # 记录当前位置为home状态（通过调用go_home来确保一致性）
    print("记录当前位置为home状态...")
    motors_service.dispatch("go_home", None)
    while motors_service.is_homing():
        time.sleep(0.1)
    print("Home状态设定完成。")

    # 步骤2: 启动RGB灯光系统
    print("\n步骤2: 启动RGB灯光系统...")
    schedule = focus_service.calculate_light_schedule(**{k: v for k, v in params.items() if k not in ['lamp_port', 'lamp_id']})
    
    if not schedule:
        print("无法生成有效的灯光计划，程序退出。")
        return

    # 步骤3: 获取可用动作列表
    available_actions = motors_service.get_available_recordings()
    if not available_actions:
        print("警告: 未找到可用的动作录制文件。")
        available_actions = []
    else:
        print("\n可用动作列表:")
        for i, action in enumerate(available_actions[:5]):  # 只显示前5个
            print(f"  {i+1}: {action}")

    # 步骤4: 主交互循环
    print("\n=== 系统就绪，等待用户输入 ===")
    print("输入数字1-5执行对应动作，输入'q'退出程序")
    
    session_thread = None
    try:
        # 在后台线程中运行灯光计划
        session_thread = threading.Thread(target=focus_service.run_focus_session, args=(schedule,))
        session_thread.start()
        print("灯光系统已启动。")
        
        while True:
            user_input = input("\n请输入指令 (1-5执行动作, q退出): ")
            if user_input.lower() == 'q':
                print("用户请求退出程序...")
                break

            try:
                action_index = int(user_input) - 1
                if available_actions and 0 <= action_index < min(5, len(available_actions)):
                    action_name = available_actions[action_index]
                    
                    print(f"\n--- 暂停灯光，执行动作: {action_name} ---")
                    focus_service.pause()
                    
                    # 执行动作
                    motors_service.dispatch("play", action_name)
                    while motors_service.is_playing():
                        time.sleep(0.1)
                    
                    # 返回home状态
                    print("动作完成，返回home状态...")
                    motors_service.dispatch("go_home", None)
                    while motors_service.is_homing():
                        time.sleep(0.1)

                    print("--- 恢复灯光系统 ---")
                    focus_service.resume()
                    
                elif user_input.isdigit() and 1 <= int(user_input) <= 5:
                    print(f"动作{user_input}不可用，请选择1-{min(5, len(available_actions))}范围内的数字。")
                else:
                    print("无效输入，请输入1-5的数字或'q'退出。")
                    
            except (ValueError, IndexError):
                print("输入格式错误，请输入1-5的数字或'q'退出。")

    except KeyboardInterrupt:
        print("\n检测到Ctrl+C，正在关闭系统...")
    except Exception as e:
        print(f"发生错误: {e}")
    finally:
        print("\n=== 关闭系统 ===")
        if focus_service:
            focus_service.stop()
        if session_thread and session_thread.is_alive():
            session_thread.join(timeout=2)
        motors_service.stop()
        rgb_service.stop()
        print("系统已安全关闭。")

if __name__ == "__main__":
    main()
