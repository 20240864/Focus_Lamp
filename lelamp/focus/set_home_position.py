#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
手动设置机械臂Home位置脚本

使用方法：
1. 运行此脚本
2. 手动将机械臂摆放到您希望的home位置
3. 按Enter键记录当前位置
4. 脚本会将当前关节角度保存为home姿态
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

def get_current_joint_positions(robot):
    """获取当前关节位置"""
    try:
        # 获取当前电机位置
        positions = robot.bus.sync_read("Present_Position")
        print("当前关节位置:")
        for motor_name, current_pos in positions.items():
            print(f"{motor_name}: {current_pos:.3f}")
        return positions
    except Exception as e:
        print(f"读取关节位置时出错: {e}")
        return None

def save_home_position(positions, lamp_id):
    """保存home位置到配置文件"""
    # 创建homing_offset格式的数据
    homing_offset = {}
    for motor_name, position in positions.items():
        homing_offset[motor_name] = position
    
    # 保存到JSON文件
    # 从当前文件位置 (lelamp/focus) 向上两级到项目根目录，然后到 lelamp/follower
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    config_dir = os.path.join(project_root, 'lelamp', 'follower')
    config_file = os.path.join(config_dir, 'home.json')
    
    # 读取现有配置或创建新配置
    if os.path.exists(config_file):
        with open(config_file, 'r') as f:
            config_data = json.load(f)
    else:
        config_data = {
            "id": lamp_id,
            "motors": {
                "base_yaw": {"id": 1, "model": "xl330-m077"},
                "base_pitch": {"id": 2, "model": "xl330-m077"},
                "elbow_pitch": {"id": 3, "model": "xl330-m077"},
                "wrist_pitch": {"id": 4, "model": "xl330-m077"},
                "wrist_roll": {"id": 5, "model": "xl330-m077"}
            }
        }
    
    # 更新homing_offset
    config_data["homing_offset"] = homing_offset
    
    # 保存配置文件
    with open(config_file, 'w') as f:
        json.dump(config_data, f, indent=4)
    
    print(f"\nHome位置已保存到: {config_file}")
    print("保存的homing_offset:")
    for motor_name, position in homing_offset.items():
        print(f"  {motor_name}: {position:.3f}")

def main():
    print("=== 机械臂Home位置设置工具 ===")
    print("此工具将帮助您设置机械臂的初始home位置")
    print()
    
    # 加载配置
    port, lamp_id = load_lamp_config()
    if not port or not lamp_id:
        print("无法加载灯具配置，请检查focus_config.json文件")
        return
    
    print(f"连接到设备: {lamp_id} (端口: {port})")
    
    try:
        # 初始化机械臂连接
        robot_config = LeLampFollowerConfig(port=port, id=lamp_id)
        robot = LeLampFollower(robot_config)
        
        print("正在连接机械臂...")
        robot.connect(calibrate=False)  # 不进行自动校准
        print("连接成功！")
        
        # 禁用扭矩，允许手动摆动
        print("正在禁用扭矩，现在您可以手动摆动机械臂...")
        robot.bus.disable_torque()
        print("扭矩已禁用，机械臂现在可以手动摆动")
        print()
        
        print("请手动将机械臂摆放到您希望的home位置")
        print("摆放完成后，按Enter键记录当前位置...")
        input()
        
        # 重新启用扭矩以读取位置
        print("正在启用扭矩以读取位置...")
        robot.bus.enable_torque()
        
        print("\n正在读取当前关节位置...")
        time.sleep(0.5)  # 等待扭矩稳定
        positions = get_current_joint_positions(robot)
        
        if positions:
            print("\n当前关节位置:")
            for motor_name, position in positions.items():
                print(f"  {motor_name}: {position:.3f}")
            
            print("\n确认将此位置设置为home位置吗? (y/N): ", end="")
            confirm = input().strip().lower()
            
            if confirm == 'y' or confirm == 'yes':
                save_home_position(positions, lamp_id)
                print("\n✅ Home位置设置完成！")
                print("现在您可以在main.py中使用go_home命令让机械臂回到此位置")
            else:
                print("操作已取消")
        else:
            print("无法读取关节位置")
            
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