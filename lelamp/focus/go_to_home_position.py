#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直接让舵机运动到标定位姿脚本

使用方法：
1. 确保机械臂已连接
2. 运行此脚本
3. 机械臂将自动运动到lelamp.json中标定的home位置
"""

import sys
import os
import json
import time

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from lelamp.follower import LeLampFollowerConfig, LeLampFollower

def load_lamp_config():
    """从focus_config.json加载灯具配置"""
    config_path = os.path.join(os.path.dirname(__file__), 'focus_config.json')
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        return config['lamp_port'], config['lamp_id']
    except Exception as e:
        print(f"无法加载配置文件: {e}")
        return None, None

def check_home_calibration(lamp_id):
    """检查home位置是否已标定"""
    # 从当前文件位置 (lelamp/focus) 向上两级到项目根目录，然后到 lelamp/follower
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    config_file = os.path.join(project_root, 'lelamp', 'follower', 'home.json')
    
    try:
        with open(config_file, 'r') as f:
            config_data = json.load(f)
        
        if 'homing_offset' not in config_data:
            print(f"错误: {config_file} 中未找到 homing_offset 数据")
            return False
            
        print(f"找到home标定数据: {config_file}")
        print("标定的homing_offset:")
        for motor_name, position in config_data['homing_offset'].items():
            print(f"  {motor_name}: {position:.3f}")
        return True
    except FileNotFoundError:
        print(f"错误: 未找到配置文件 {config_file}")
        print("请先运行 set_home_position.py 来标定home位置")
        return False
    except Exception as e:
        print(f"读取配置文件时出错: {e}")
        return False

def move_to_home_position(robot):
    """让机械臂运动到home位置"""
    try:
        print("正在移动到home位置...")
        print("使用与motors_service相同的方法: 发送0.0位置，让lerobot框架自动应用homing_offset")
        
        # 使用与motors_service._go_home()相同的方法
        # 发送0.0位置，lerobot框架会自动应用homing_offset校准
        home_action = {f"{joint}.pos": 0.0 for joint in robot.bus.motors}
        
        print("发送的action:")
        for key, value in home_action.items():
            print(f"  {key}: {value}")
        
        # 使用robot.send_action()而不是直接使用bus.sync_write()
        # 这样会通过lerobot框架的校准系统
        robot.send_action(home_action)
        
        # 等待运动完成
        print("\n等待运动完成...")
        time.sleep(2)  # 给足够时间让电机运动
        
        # 检查当前位置
        current_positions = robot.bus.sync_read("Present_Position")
        print("\n当前位置:")
        for motor_name, current_pos in current_positions.items():
            print(f"  {motor_name}: {current_pos:.3f}")
        
        print("\n✅ 已到达home位置！")
        return True
        
    except Exception as e:
        print(f"移动到home位置时出错: {e}")
        return False

def main():
    print("=== 机械臂Home位置运动脚本 ===")
    print("此脚本将让机械臂运动到标定的home位置")
    print()
    
    # 加载配置
    port, lamp_id = load_lamp_config()
    if not port or not lamp_id:
        print("无法加载灯具配置，请检查focus_config.json文件")
        return
    
    # 检查home位置是否已标定
    if not check_home_calibration(lamp_id):
        return
    
    print(f"连接到设备: {lamp_id} (端口: {port})")
    
    try:
        # 初始化机械臂连接
        robot_config = LeLampFollowerConfig(port=port, id=lamp_id)
        robot = LeLampFollower(robot_config)
        
        print("正在连接机械臂...")
        robot.connect(calibrate=True)  # 启用自动校准，加载homing_offset
        print("连接成功！")
        
        # 确保扭矩已启用
        print("正在启用扭矩...")
        robot.bus.enable_torque()
        
        # 移动到home位置
        success = move_to_home_position(robot)
        
        if success:
            print("\n机械臂已成功移动到home位置！")
        else:
            print("\n移动失败，请检查机械臂连接和配置")
            
    except Exception as e:
        print(f"发生错误: {e}")
    finally:
        try:
            robot.disconnect()
            print("\n连接已断开")
        except:
            pass

if __name__ == "__main__":
    main()