#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速设置Home位置脚本
简化版本，用于快速记录当前机械臂位置作为home姿态
"""

import sys
import os
import json

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from lelamp.follower import LeLampFollowerConfig, LeLampFollower

def main():
    print("快速设置Home位置")
    print("==================")
    
    # 从focus_config.json读取配置
    config_path = os.path.join(os.path.dirname(__file__), 'focus_config.json')
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    port = config['lamp_port']
    lamp_id = config['lamp_id']
    
    print(f"设备: {lamp_id}")
    print(f"端口: {port}")
    print()
    
    # 连接机械臂
    robot_config = LeLampFollowerConfig(port=port, id=lamp_id)
    robot = LeLampFollower(robot_config)
    robot.connect(calibrate=False)
    
    # 禁用扭矩，允许手动摆动
    print("正在禁用扭矩，现在可以手动摆动机械臂...")
    robot.bus.disable_torque()
    print("扭矩已禁用")
    
    print("请手动摆放机械臂到目标位置，然后按Enter...")
    input()
    
    # 重新启用扭矩以读取位置
    print("正在启用扭矩以读取位置...")
    robot.bus.enable_torque()
    
    # 读取当前位置
    import time
    time.sleep(0.5)  # 等待扭矩稳定
    positions = robot.bus.sync_read("Present_Position")
    print("\n当前关节位置:")
    for motor_name, pos in positions.items():
        print(f"  {motor_name}: {pos:.3f}")
    
    # 保存到配置文件
    # 从当前文件位置 (lelamp/focus) 向上两级到项目根目录，然后到 lelamp/follower
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    config_dir = os.path.join(project_root, 'lelamp', 'follower')
    config_file = os.path.join(config_dir, f'{lamp_id}.json')
    
    # 确保配置目录存在
    os.makedirs(config_dir, exist_ok=True)
    
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
    
    config_data["homing_offset"] = positions
    
    with open(config_file, 'w') as f:
        json.dump(config_data, f, indent=4)
    
    print(f"\n✅ Home位置已保存到: {config_file}")
    
    robot.disconnect()
    print("完成！")

if __name__ == "__main__":
    main()