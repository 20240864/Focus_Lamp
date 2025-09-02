import datetime
import sys
import os
import threading
import time
import json
import logging
import re
from datetime import datetime as dt

# Add the project root to the python path to allow imports from other services
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lelamp.service.rgb import RGBService
from lelamp.service.motors import MotorsService
from lelamp.focus.focus_service import FocusService

# 解析detection_log.txt获取最新的专注状态评级
def get_latest_concentration_rating(log_file_path):
    """从detection_log.txt中获取最新的专注状态评级"""
    try:
        if not os.path.exists(log_file_path):
            print(f"警告: 检测日志文件不存在: {log_file_path}")
            return None
            
        with open(log_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 查找所有的专注状态评级
        pattern = r'专注状态评级: (\d+)'
        matches = re.findall(pattern, content)
        
        if matches:
            latest_rating = int(matches[-1])  # 获取最后一个匹配的评级
            return latest_rating
        else:
            print("未找到专注状态评级数据")
            return None
            
    except Exception as e:
        print(f"读取检测日志文件时出错: {e}")
        return None

# 根据专注状态评级获取对应的动作
def get_action_by_rating(rating, available_actions):
    """根据专注状态评级返回对应的动作名称"""
    # 定义评级到动作的映射关系
    rating_to_action_map = {
        10: 0,  # 对应available_actions[0]
        11: 1,  # 对应available_actions[1]
        20: 2,  # 对应available_actions[2]
        21: 3,  # 对应available_actions[3]
        30: 4,  # 对应available_actions[4]
        31: 5,  # 对应available_actions[5]
        40: 6,  # 对应available_actions[6]
        41: 7,  # 对应available_actions[7]
        50: 8,  # 对应available_actions[8]
        51: 9   # 对应available_actions[9]
    }
    
    if rating in rating_to_action_map:
        action_index = rating_to_action_map[rating]
        if action_index < len(available_actions):
            return available_actions[action_index]
        else:
            print(f"警告: 评级{rating}对应的动作索引{action_index}超出可用动作范围")
            return None
    else:
        print(f"未知的专注状态评级: {rating}")
        return None

# 执行动作的函数
def execute_action(action_name, motors_service, focus_service):
    """执行指定的动作"""
    print(f"\n--- 暂停灯光，执行动作: {action_name} ---")
    focus_service.pause()
    
    # 执行动作
    motors_service.dispatch("play", action_name)
    while motors_service.is_playing():
        time.sleep(0.1)

    print("动作完成，等待5秒...")
    time.sleep(5)
    
    print("正在返回home状态...")
    motors_service.dispatch("go_home_from_json", None)
    while motors_service.is_homing():
        time.sleep(0.1)
    print("已返回home状态")

    print("--- 恢复灯光系统 ---")
    focus_service.resume()

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

    time.sleep(1)
    # 使用MotorService设定home状态
    print("使用MotorService设定home状态...")
    motors_service.dispatch("go_home_from_json", None)
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
        for i, action in enumerate(available_actions[:10]):  # 显示前10个动作
            print(f"  {i+1}: {action}")
    
    # 检查是否有足够的动作文件
    if len(available_actions) < 10:
        print(f"警告: 需要至少10个动作文件，当前只有{len(available_actions)}个")
        print("系统将使用现有动作文件，缺失的评级将被忽略")
    
    # 设置detection_log.txt的路径
    log_file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), 'yolo_test', 'detection_log.txt')
    print(f"\n检测日志文件路径: {log_file_path}")

    # 步骤4: 自动监控循环
    print("\n=== 系统就绪，开始自动监控专注状态 ===")
    print("系统将每30秒检查一次专注状态评级并执行相应动作")
    print("按Ctrl+C退出程序")
    
    session_thread = None
    last_rating = None
    try:
        # 在后台线程中运行灯光计划
        session_thread = threading.Thread(target=focus_service.run_focus_session, args=(schedule,))
        session_thread.start()
        print("灯光系统已启动。")
        
        while True:
            try:
                # 获取最新的专注状态评级
                current_rating = get_latest_concentration_rating(log_file_path)
                
                if current_rating is not None:
                    print(f"\n当前专注状态评级: {current_rating}")
                    
                    # 检查是否为状态0，如果是则保持原状不变
                    if current_rating == 0:
                        print("检测到状态0，保持原状不变")
                    else:
                        # 每次检测到非0状态都执行动作，即使和上次相同
                        action_name = get_action_by_rating(current_rating, available_actions)
                        
                        if action_name:
                            if current_rating == last_rating:
                                print(f"评级保持为 {current_rating}，重复执行动作: {action_name}")
                            else:
                                print(f"评级从 {last_rating} 变更为 {current_rating}，执行动作: {action_name}")
                            execute_action(action_name, motors_service, focus_service)
                        else:
                            print(f"评级 {current_rating} 没有对应的动作")
                    
                    last_rating = current_rating
                else:
                    print("无法获取专注状态评级")
                
                # 等待30秒后再次检查
                print(f"等待30秒后进行下次检查... (当前时间: {dt.now().strftime('%H:%M:%S')})")
                time.sleep(30)
                
            except Exception as e:
                print(f"监控循环中发生错误: {e}")
                time.sleep(30)  # 出错后也等待30秒再重试

    except KeyboardInterrupt:
        print("\n用户中断程序...")
    except Exception as e:
        print(f"程序运行出错: {e}")
    finally:
        # 步骤5: 清理资源
        print("\n=== 开始清理资源 ===")
        
        # 停止灯光服务
        if session_thread and session_thread.is_alive():
            focus_service.stop()
            session_thread.join(timeout=5)
            if session_thread.is_alive():
                print("警告: 灯光服务线程未能正常结束")
            else:
                print("灯光服务已停止")
        
        # 停止电机服务
        try:
            motors_service.stop()
            print("电机服务已停止")
        except Exception as e:
            print(f"停止电机服务时出错: {e}")
        
        # 停止RGB服务
        try:
            rgb_service.stop()
            print("RGB服务已停止")
        except Exception as e:
            print(f"停止RGB服务时出错: {e}")
        
        print("=== 程序已退出 ===")

if __name__ == "__main__":
    main()
