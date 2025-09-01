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
from lelamp.follower.lelamp_follower import LeLampFollower
from lelamp.follower.config_lelamp_follower import LeLampFollowerConfig

# 直接读取home.json文件中的homing_offset数据并控制舵机
def go_home_direct(port, lamp_id):
    """直接读取home.json文件中的homing_offset数据作为home状态"""
    try:
        # 读取home.json文件
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        home_config_path = os.path.join(project_root, 'lelamp', 'follower', 'home.json')
        
        print(f"读取home配置文件: {home_config_path}")
        with open(home_config_path, 'r') as f:
            home_config = json.load(f)
        
        if 'homing_offset' not in home_config:
            print("错误: home.json中未找到homing_offset数据")
            return False
        
        homing_offset = home_config['homing_offset']
        print("读取到的homing_offset:")
        for motor_name, position in homing_offset.items():
            print(f"  {motor_name}: {position:.3f}")
        
        # 初始化机械臂连接
        robot_config = LeLampFollowerConfig(port=port, id=lamp_id)
        robot = LeLampFollower(robot_config)
        
        print("正在连接机械臂...")
        robot.connect(calibrate=False)  # 不使用自动校准，直接控制
        print("连接成功！")
        
        # 启用扭矩
        robot.bus.enable_torque()
        
        # 直接将homing_offset中的位置值发送给舵机
        print("正在移动到home位置...")
        
        # 构建目标位置字典，直接使用homing_offset中的值
        target_positions = {}
        for motor_name in robot.bus.motors.keys():
            if motor_name in homing_offset:
                target_positions[motor_name] = homing_offset[motor_name]
            else:
                print(f"警告: 在homing_offset中未找到电机 {motor_name}")
                target_positions[motor_name] = 0.0
        
        print("发送的目标位置:")
        for motor_name, position in target_positions.items():
            print(f"  {motor_name}: {position:.3f}")
        
        # 直接使用bus.sync_write发送位置命令
        robot.bus.sync_write("Goal_Position", target_positions)
        
        # 等待运动完成
        print("等待运动完成...")
        time.sleep(2)
        
        # 检查当前位置
        current_positions = robot.bus.sync_read("Present_Position")
        print("当前位置:")
        for motor_name, current_pos in current_positions.items():
            print(f"  {motor_name}: {current_pos:.3f}")
        
        # 断开连接
        robot.disconnect()
        print("✅ 已到达home位置！")
        return True
        
    except Exception as e:
        print(f"go_home_direct执行失败: {e}")
        return False

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
    
    # 使用直接读取home.json的方式设定home状态
    print("使用home.json数据设定home状态...")
    if go_home_direct(params['lamp_port'], params['lamp_id']):
        print("Home状态设定完成。")
    else:
        print("Home状态设定失败，请检查配置文件。")

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
                        time.sleep(5)
                    
                    print("动作完成，正在返回home状态...")
                    # 返回home状态
                    if go_home_direct(params['lamp_port'], params['lamp_id']):
                        print("已返回home状态")
                    else:
                        print("返回home状态失败")

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
