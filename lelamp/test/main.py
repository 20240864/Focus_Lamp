#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Focus Lamp 主控制程序
整合了专注会话管理、WebSocket通信、灯光控制和动作执行等功能

主要功能模块：
1. 色温与亮度转换工具函数
2. FocusService 专注会话管理类
3. WebSocket 通信服务
4. 灯光控制线程
5. 动作执行与机器人控制
6. 配置管理
"""

# ============================================================================
# 标准库导入
# ============================================================================
import datetime
import sys
import os
import threading
import time
import json
import logging
import re
import csv
import math
from datetime import datetime as dt

# ============================================================================
# 第三方库导入
# ============================================================================
# 异步与 WebSocket 支持
import asyncio
import websockets

# ============================================================================
# 项目内部导入
# ============================================================================
# Add the project root to the python path to allow imports from other services
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lelamp.service.rgb import RGBService
from lelamp.service.base import Priority
from lelamp.follower import LeLampFollowerConfig, LeLampFollower
from lerobot.utils.robot_utils import busy_wait

# ============================================================================
# 配置和常量
# ============================================================================

# 配置文件路径
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'focus_config.json')

# ============================================================================
# 工具函数模块
# ============================================================================

# --- 色温与亮度转换函数 ---

def kelvin_to_rgb(temp_kelvin):
    """
    将开尔文色温转换为RGB颜色元组
    使用Tanner Helland算法
    """
    temp = temp_kelvin / 100.0
    
    # 色温转换为RGB (色温范围：1000K-6500K)
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
    """
    将照度(Lux)转换为亮度因子(0.0到1.0)
    假设线性关系和已知的灯具最大照度
    """
    return max(0.0, min(1.0, illuminance_lx / max_illuminance))

def apply_brightness(rgb_color, brightness_factor):
    """
    将亮度因子应用到RGB颜色
    """
    r, g, b = rgb_color
    return (
        int(r * brightness_factor),
        int(g * brightness_factor),
        int(b * brightness_factor)
    )

# ============================================================================
# 专注会话管理模块
# ============================================================================

class FocusService:
    """
    实现专注照明计划数学算法的焦点服务类
    """
    
    def __init__(self, rgb_service: RGBService):
        self.rgb_service = rgb_service
        self._running_event = threading.Event()
        self._running_event.set()  # 默认设置为运行状态
        self._stop_event = threading.Event()
        self._session_complete_callback = None

    def calculate_light_schedule(self, start_hour, start_minute, total_duration_min, fatigue_level, focus_mode_m):
        """
        计算专注会话每个阶段的持续时间和灯光参数
        
        :param start_hour: 任务开始小时 (0-23)
        :param start_minute: 任务开始分钟 (0-59)
        :param total_duration_min: 总任务持续时间(分钟)
        :param fatigue_level: 疲劳等级 (1-5)
        :param focus_mode_m: 专注模式 (-1为发散思维, 1为聚合思维)
        :return: 元组列表，每个元组为 (duration_seconds, cct_k, illuminance_lx)
        """
        
        # 1. 中间变量
        c = start_hour * 60 + start_minute
        t = total_duration_min
        f = fatigue_level
        M = focus_mode_m
        
        t_before_17 = max(0, min(c + t, 1020) - c)

        # 2. 计算 T_wakeup
        T_wakeup = 0
        if start_hour >= 17:
            T_wakeup = 0
        elif 12 <= start_hour < 17:
            if f == 5:
                T_wakeup = 0.20 * t
            elif f == 4:
                T_wakeup = 0.15 * t
            else:  # f in {1,2,3}
                T_wakeup = 0
        else:  # start_hour < 12
            factor1 = 0.7 + 0.1 * f
            factor2 = 30 - 0.0833 * max(c - 480, 0)
            T_wakeup = t * (factor1 * factor2) / 100

        # 3. 计算 T_moderate
        P_moderate = 0.75 * M + 0.25 * (t_before_17 / t if t > 0 else 0)
        T_moderate = t * max(0, P_moderate)

        # 4. 计算 T_low
        T_low = t - T_wakeup - T_moderate
        
        # 确保没有负持续时间
        T_wakeup = max(0, T_wakeup)
        T_moderate = max(0, T_moderate)
        T_low = max(0, T_low)

        # 5. 定义每个阶段的灯光参数
        schedule = []
        
        # 阶段1: 唤醒
        if T_wakeup > 0:
            schedule.append((T_wakeup * 60, 5800, 750))
            
        # 阶段2: 中等
        if T_moderate > 0:
            if t > 90:
                schedule.append((T_moderate * 60, 3000, 750))
            else:
                schedule.append((T_moderate * 60, 4500, 450))
                
        # 阶段3: 低强度
        if T_low > 0:
            schedule.append((T_low * 60, 3000, 250))
            
        return schedule

    def run_focus_session(self, schedule):
        """
        基于计算的调度执行专注会话
        """
        if not self.rgb_service.is_running:
            print("错误: RGB服务未运行，请先启动服务。")
            return
            
        print("开始专注会话...")
        total_duration = sum(item[0] for item in schedule)
        print(f"预计总持续时间: {total_duration / 60:.2f} 分钟。")
        
        session_completed_normally = True

        for i, (duration_sec, cct, lux) in enumerate(schedule):
            if self._stop_event.is_set():
                session_completed_normally = False
                break
            print(f"--- 阶段 {i+1}/{len(schedule)} ---")
            print(f"持续时间: {duration_sec / 60:.2f} 分钟")
            print(f"色温: {cct}K")
            print(f"照度: {lux} lx")

            # 将色温和照度转换为RGB颜色
            base_rgb = kelvin_to_rgb(cct)
            brightness = illuminance_to_brightness(lux)
            final_rgb = apply_brightness(base_rgb, brightness)
            
            print(f"计算亮度: {brightness:.2f}")
            print(f"计算RGB: {final_rgb}")

            # 发送到RGB服务
            self.rgb_service.dispatch("solid", final_rgb, Priority.NORMAL)
            
            # 等待阶段持续时间，检查暂停/停止事件
            start_time = time.time()
            while time.time() - start_time < duration_sec:
                if self._stop_event.is_set():
                    session_completed_normally = False
                    break
                self._running_event.wait(timeout=0.1)  # 如果暂停则阻塞，检查停止事件
            
            if self._stop_event.is_set():
                session_completed_normally = False
                break
        
        if session_completed_normally:
            print("--- 专注会话正常完成！所有阶段已完成。 ---")
            # 通知监控循环会话已完成
            if self._session_complete_callback:
                self._session_complete_callback()
        else:
            print("--- 专注会话手动停止！ ---")

    def pause(self):
        """暂停专注会话"""
        self._running_event.clear()
        print("专注会话已暂停。")

    def resume(self):
        """恢复专注会话"""
        self._running_event.set()
        print("专注会话已恢复。")

    def stop(self):
        """停止专注会话"""
        self._stop_event.set()
        self._running_event.set()  # 确保wait()循环解除阻塞以看到停止信号
        print("专注会话正在停止。")
    
    def set_session_complete_callback(self, callback):
        """设置会话完成时的回调函数"""
        self._session_complete_callback = callback
    
    def reset(self):
        """重置FocusService状态，准备新的会话"""
        self._stop_event.clear()
        self._running_event.set()

# ============================================================================
# 全局状态管理模块
# ============================================================================

# --- 专注会话状态 ---
start_focus_state = {"value": False}
state_lock = threading.Lock()

# --- 灯光控制线程状态 ---
light_control_state = {"running": False, "cct_k": 4500, "lux": 300}
light_control_lock = threading.Lock()

# --- 全局变量存储专注会话相关对象 ---
focus_session_globals = {
    'focus_service': None,
    'robot': None,
    'available_actions': [],
    'log_file_path': None,
    'params': None
}


# ============================================================================
# WebSocket 通信模块
# ============================================================================

# --- WebSocket 消息处理器 ---
async def ws_handler(websocket):
    """WebSocket消息处理器"""
    async for message in websocket:
        try:
            # 打印接收到的原始数据
            print(f"[WebSocket] 接收到数据: {message}")
            
            new_val = None
            cfg_updates_ack = []
            
            # 优先解析 JSON 格式：{"start_focus": true/false, 以及配置相关字段}
            try:
                data = json.loads(message)
                if isinstance(data, dict):
                    # 读取并更新 start_focus
                    if "start_focus" in data:
                        new_val = bool(data["start_focus"])
                    # 解析并覆盖配置（如果有提供字段）
                    updated_keys = update_config_from_ws(data)
                    if updated_keys:
                        cfg_updates_ack = updated_keys
            except Exception:
                pass
                
            # 兼容纯文本仅用于 start_focus
            if new_val is None:
                m = str(message).strip().lower()
                if "true" in m:
                    new_val = True
                elif "false" in m:
                    new_val = False
                    
            # 应用 start_focus 变更
            if new_val is None and not cfg_updates_ack:
                print("WebSocket 收到无法解析的消息：", message)
                await websocket.send("invalid message: " + str(message))
                continue
                
            if new_val is not None:
                with state_lock:
                    old_val = start_focus_state["value"]
                    start_focus_state["value"] = new_val
                    
                if new_val != old_val:
                    print(f"start_focus 变更：{old_val} -> {new_val}")
                    # 当start_focus变为True时，启动专注会话
                    if new_val:
                        print("=== 开始专注会话，启用实时detection_log.txt监控 ===")
                        asyncio.create_task(start_focus_session())
                    else:
                        print("=== 专注会话停止，仅继续灯光控制 ===")
                        
            # 如果更新了色温或亮度，立即触发灯光控制线程更新
            if cfg_updates_ack and ('IDLE_CCT_K' in cfg_updates_ack or 'IDLE_LUX' in cfg_updates_ack):
                print(f"[WebSocket] 灯光参数已更新: {cfg_updates_ack}")
            
            # 回执
            ack = {"ack": True}
            if new_val is not None:
                ack["start_focus"] = new_val
            if cfg_updates_ack:
                ack["updated"] = cfg_updates_ack
            await websocket.send(json.dumps(ack, ensure_ascii=False))
            
        except Exception as e:
            print("WebSocket 处理消息出错：", e)

async def ws_main():
    """WebSocket服务器主函数"""
    async with websockets.serve(ws_handler, "192.168.137.104", 5173):
        print("WebSocket服务器已启动，监听端口5173")
        await asyncio.Future()

def start_websocket_server():
    """启动WebSocket服务器"""
    asyncio.run(ws_main())


# ============================================================================
# 专注会话控制模块
# ============================================================================

# --- 专注会话启动函数 ---
async def start_focus_session():
    """启动专注会话，计算灯光调度并开始监控"""
    try:
        # 重新加载配置参数
        params = load_params_from_config()
        if not params:
            print("加载专注会话配置失败")
            return
        
        focus_service = focus_session_globals['focus_service']
        if not focus_service:
            print("专注服务未初始化")
            return
        
        # 重置FocusService状态
        focus_service.reset()
        
        # 设置会话完成回调
        def on_session_complete():
            print("[回调] 专注会话完成，设置start_focus为False")
            with state_lock:
                start_focus_state["value"] = False
        
        focus_service.set_session_complete_callback(on_session_complete)
        
        # 准备传递给calculate_light_schedule的参数
        schedule_params = {k: v for k, v in params.items() 
                          if k not in ['lamp_port', 'lamp_id', 'IDLE_CCT_K', 'IDLE_LUX']}
        print(f"专注会话调度参数: {schedule_params}")
        
        schedule = focus_service.calculate_light_schedule(**schedule_params)
        
        if not schedule:
            print("无法为专注会话生成有效的灯光调度")
            return
        
        print(f"专注会话已启动，调度包含: {len(schedule)} 个阶段")
        
        # 在后台线程中启动专注会话的灯光调度，避免阻塞
        def run_focus_in_thread():
            print("[阶段线程] 在后台开始阶段执行...")
            focus_service.run_focus_session(schedule)
            print("[阶段线程] 所有阶段完成或停止。")
        
        focus_thread = threading.Thread(target=run_focus_in_thread, daemon=True)
        focus_thread.start()
        print("[主线程] 阶段执行线程启动成功")
        
        # 开始监控循环（在后台运行），实现实时读取detection_log.txt
        print("[主线程] 开始实时detection_log.txt监控...")
        asyncio.create_task(focus_monitoring_loop())
        print("[主线程] 专注会话初始化完成 - 阶段和监控现在并行运行")
        
    except Exception as e:
        print(f"启动专注会话时出错: {e}")

# --- 专注会话监控循环 ---
async def focus_monitoring_loop():
    """专注监控循环 - 实时读取detection_log.txt并响应专注状态变化"""
    try:
        robot = focus_session_globals['robot']
        focus_service = focus_session_globals['focus_service']
        available_actions = focus_session_globals['available_actions']
        log_file_path = focus_session_globals['log_file_path']
        params = focus_session_globals['params']
        
        if not all([robot, focus_service, available_actions, log_file_path, params]):
            print("专注监控: 缺少必需的对象")
            return
        
        print("开始实时专注监控循环...")
        print(f"监控检测日志: {log_file_path}")
        print(f"会话持续时间限制: {params.get('total_duration_min', 0)} 分钟")
        
        # 记录会话开始时间
        session_start_time = time.time()
        session_duration_seconds = params.get('total_duration_min', 0) * 60
        
        last_rating = None
        consecutive_same_rating = 0
        
        while True:
            # 检查是否还在专注状态
            with state_lock:
                if not start_focus_state["value"]:
                    print("专注会话被外部信号结束，停止监控")
                    focus_service.stop()  # 使用stop而不是pause，完全停止Phase执行
                    break
            
            # 检查是否超过设定的duration_min
            elapsed_time = time.time() - session_start_time
            if session_duration_seconds > 0 and elapsed_time >= session_duration_seconds:
                print(f"专注会话达到时间限制 ({params.get('total_duration_min', 0)} 分钟)，自动停止")
                with state_lock:
                    start_focus_state["value"] = False
                focus_service.stop()
                break
            
            # 实时获取最新的专注评级
            rating = get_latest_concentration_rating(log_file_path)
            
            if rating is not None:
                # 检查评级是否发生变化
                if rating != last_rating:
                    print(f"[实时] 专注评级变化: {last_rating} -> {rating}")
                    last_rating = rating
                    consecutive_same_rating = 1
                else:
                    consecutive_same_rating += 1
                
                # 根据评级获取对应的动作
                action_name = get_action_by_rating(rating, available_actions)
                
                if action_name:
                    # 只要识别到数字就执行相应的动作
                    print(f"[实时] 为评级 {rating} 执行动作: {action_name}")
                    # 在新线程中执行动作，避免阻塞异步循环和Phase执行
                    def execute_in_thread():
                        execute_action(action_name, robot, focus_service, params['lamp_id'])
                    
                    action_thread = threading.Thread(target=execute_in_thread, daemon=True)
                    action_thread.start()
                else:
                    print(f"[实时] 未找到评级 {rating} 对应的动作")
            else:
                print("[实时] 检测日志中没有可用的专注评级")
            
            # 显示剩余时间
            if session_duration_seconds > 0:
                remaining_time = session_duration_seconds - elapsed_time
                if remaining_time > 0:
                    print(f"[实时] 会话剩余时间: {remaining_time/60:.1f} 分钟")
            
            # 实时监控：每10秒检查一次，确保及时响应
            await asyncio.sleep(10)
            
    except Exception as e:
        print(f"实时专注监控循环出错: {e}")
    finally:
        print("[监控] 专注监控循环结束，清理中...")
        # 确保停止detection_log.txt监控
        with state_lock:
            if start_focus_state["value"]:
                start_focus_state["value"] = False
                print("[监控] 清理期间设置start_focus为False")

# ============================================================================
# 灯光控制模块
# ============================================================================

# --- 灯光控制线程 ---
def light_control_thread(rgb_service):
    """独立的灯光控制线程，根据WebSocket参数实时调整灯光"""
    print("灯光控制线程已启动")
    last_cct_k = None
    last_lux = None
    
    while True:
        try:
            # 检查是否应该运行灯光控制
            with light_control_lock:
                should_run = light_control_state["running"]
                current_cct_k = light_control_state["cct_k"]
                current_lux = light_control_state["lux"]
            
            if should_run:
                # 只有当参数发生变化时才更新灯光，避免频繁调用
                if last_cct_k != current_cct_k or last_lux != current_lux:
                    # 计算并应用灯光
                    base_rgb = kelvin_to_rgb(current_cct_k)
                    brightness = illuminance_to_brightness(current_lux)
                    final_rgb = apply_brightness(base_rgb, brightness * 0.5)  # 温和亮度，减半
                    
                    rgb_service.dispatch("solid", final_rgb)
                    print(f"[灯光控制] 已更新: CCT={current_cct_k}K, Lux={current_lux}, RGB={final_rgb}")
                    
                    last_cct_k = current_cct_k
                    last_lux = current_lux
                
                # 每0.5秒检查一次参数变化
                time.sleep(0.5)
            else:
                # 未运行时重置记录的参数，等待更长时间
                last_cct_k = None
                last_lux = None
                time.sleep(1)
                
        except Exception as e:
            print(f"灯光控制线程错误: {e}")
            time.sleep(1)

# ============================================================================
# 数据处理和动作执行模块
# ============================================================================

# --- 专注度数据读取 ---
def get_latest_concentration_rating(log_file_path):
    """从detection_log.txt获取最新的专注评级"""
    try:
        if not os.path.exists(log_file_path):
            print(f"警告: 检测日志文件未找到: {log_file_path}")
            return None
            
        with open(log_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 查找所有专注状态评级
        pattern = r'专注状态评级: (\d+)'
        matches = re.findall(pattern, content)
        
        if matches:
            latest_rating = int(matches[-1])  # 获取最后匹配的评级
            return latest_rating
        else:
            print("未找到专注评级数据")
            return None
            
    except Exception as e:
        print(f"读取检测日志文件出错: {e}")
        return None

# --- 动作映射 ---
def get_action_by_rating(rating, available_actions):
    """根据专注评级返回对应的动作名称"""
    # 定义评级到动作文件名的直接映射
    rating_to_action_map = {
        10: "10_shake",
        11: "11_angry", 
        20: "curious",
        21: "21_standup",
        30: "30_nod1",
        31: "31_wiggle",
        40: "excited",
        41: "41_courage",
        50: "happy_wiggle",
        51: "51_scanning"
    }
    
    if rating in rating_to_action_map:
        action_name = rating_to_action_map[rating]
        # 检查动作文件是否存在于available_actions中
        if action_name in available_actions:
            return action_name
        else:
            print(f"警告: 动作文件 {action_name} 在可用动作中未找到")
            return None
    else:
        print(f"未知的专注评级: {rating}")
        return None

# ============================================================================
# 动作执行
# ============================================================================

# --- 机器人控制 ---
def go_home(motors_service):
    """将灯具返回到初始家位置"""
    print("返回家位置...")
    motors_service.dispatch("go_home_from_json", None)
    while motors_service.is_homing():
        time.sleep(0.1)
    print("已返回家位置。")

def execute_action(action_name, robot, focus_service, lamp_id, fps=30, use_id_suffix=True):
    """执行指定动作并等待完成，使用CSV重放方法"""
    print(f"\n--- 临时暂停阶段灯光，执行动作: {action_name} ---")
    
    # 暂停当前Phase的灯光，但不停止整个focus session
    focus_service.pause()
    
    # 从名称和灯具ID构建CSV文件名
    recordings_dir = os.path.join(os.path.dirname(__file__), "..", "recordings")
    if use_id_suffix:
        csv_filename = f"{action_name}_{lamp_id}.csv"
    else:
        csv_filename = f"{action_name}.csv"
    csv_path = os.path.join(recordings_dir, csv_filename)
    
    try:
        # 读取CSV文件并重放动作
        with open(csv_path, 'r') as csvfile:
            csv_reader = csv.DictReader(csvfile)
            actions = list(csv_reader)
        
        print(f"从 {csv_path} 重放 {len(actions)} 个动作")
        
        for row in actions:
            t0 = time.perf_counter()
            
            # 提取动作数据（排除时间戳列）
            action = {key: float(value) for key, value in row.items() if key != 'timestamp'}
            robot.send_action(action)
            
            busy_wait(1.0 / fps - (time.perf_counter() - t0))
        
        print(f"动作 {action_name} 完成！恢复阶段灯光...")
        
    except FileNotFoundError:
        print(f"错误: 动作文件未找到: {csv_path}")
    except Exception as e:
        print(f"执行动作 {action_name} 时出错: {e}")
    finally:
        # 无论动作是否成功执行，都要恢复Phase灯光
        focus_service.resume()
        print("阶段灯光已恢复，继续专注会话...")

# ============================================================================
# 配置管理模块
# ============================================================================

# --- 配置文件加载 ---
def load_params_from_config():
    """从JSON配置文件加载任务参数"""
    config_path = CONFIG_PATH
    print(f"从 {config_path} 加载参数")
    try:
        with open(config_path, 'r') as f:
            params = json.load(f)
        
        # 验证参数
        required_keys = ["start_hour", "start_minute", "total_duration_min", 
                        "fatigue_level", "focus_mode_m", "lamp_port", "lamp_id"]
        missing_keys = [k for k in required_keys if k not in params]
        if missing_keys:
            print(f"配置文件缺少必需参数: {missing_keys}")
            return None
            
        return params
    except FileNotFoundError:
        print(f"错误: 在 {config_path} 未找到配置文件")
        return None
    except json.JSONDecodeError:
        print(f"错误: 无法从 {config_path} 解码JSON")
        return None

# --- 空闲状态RGB计算 ---
def compute_idle_rgb_from_config():
    """根据配置计算空闲（设定值）RGB"""
    try:
        with open(CONFIG_PATH, 'r') as f:
            params = json.load(f)
    except Exception:
        params = {}
    idle_cct_k = params.get('IDLE_CCT_K', 4500)
    idle_lux = params.get('IDLE_LUX', 300)
    base = kelvin_to_rgb(int(idle_cct_k))
    bright = illuminance_to_brightness(int(idle_lux))
    return apply_brightness(base, bright), int(idle_cct_k), int(idle_lux)

# --- WebSocket配置更新 ---
def update_config_from_ws(data: dict):
    """
    将WebSocket的部分字段写回配置文件
    支持字段：start_hour, start_min, focus_hour, focus_min, exhaustion_level(0..5), 
             focus_pattern(0/1), cct_k, lux
    对应映射：start_hour->start_hour, start_min->start_minute, 
             focus_hour/min->total_duration_min, exhaustion_level->fatigue_level, 
             focus_pattern->focus_mode_m(0->-1,1->1), cct_k->IDLE_CCT_K, lux->IDLE_LUX
    """
    try:
        with state_lock:
            # 读取现有配置
            try:
                with open(CONFIG_PATH, 'r') as f:
                    cfg = json.load(f)
            except Exception:
                cfg = {}
            updated = []
            
            # start_hour
            if 'start_hour' in data and data['start_hour'] is not None:
                try:
                    val = int(data['start_hour'])
                    val = max(0, min(23, val))
                    cfg['start_hour'] = val
                    updated.append('start_hour')
                except Exception:
                    pass
                    
            # start_min -> start_minute
            if 'start_min' in data and data['start_min'] is not None:
                try:
                    val = int(data['start_min'])
                    val = max(0, min(59, val))
                    cfg['start_minute'] = val
                    updated.append('start_minute')
                except Exception:
                    pass
                    
            # focus_hour + focus_min -> total_duration_min
            hours_present = 'focus_hour' in data and data['focus_hour'] is not None
            mins_present = 'focus_min' in data and data['focus_min'] is not None
            if hours_present or mins_present:
                try:
                    cur_total = int(cfg.get('total_duration_min', 0))
                    cur_h = cur_total // 60
                    cur_m = cur_total % 60
                    h = int(data['focus_hour']) if hours_present else cur_h
                    m = int(data['focus_min']) if mins_present else cur_m
                    h = max(0, h)
                    m = max(0, min(59, m))
                    cfg['total_duration_min'] = h * 60 + m
                    updated.append('total_duration_min')
                except Exception:
                    pass
                    
            # exhaustion_level -> fatigue_level
            if 'exhaustion_level' in data and data['exhaustion_level'] is not None:
                try:
                    val = int(data['exhaustion_level'])
                    val = max(1, min(5, val))
                    cfg['fatigue_level'] = val
                    updated.append('fatigue_level')
                except Exception:
                    pass
                    
            # focus_pattern -> focus_mode_m (0->-1, 1->1)
            if 'focus_pattern' in data and data['focus_pattern'] is not None:
                try:
                    val = int(data['focus_pattern'])
                    if val == 0:
                        cfg['focus_mode_m'] = -1
                    elif val == 1:
                        cfg['focus_mode_m'] = 1
                    updated.append('focus_mode_m')
                except Exception:
                    pass
                    
            # cct_k -> IDLE_CCT_K
            if 'cct_k' in data and data['cct_k'] is not None:
                try:
                    val = int(data['cct_k'])
                    val = max(1000, min(6500, val))
                    cfg['IDLE_CCT_K'] = val
                    updated.append('IDLE_CCT_K')
                    # 同时更新灯光控制状态
                    with light_control_lock:
                        light_control_state['cct_k'] = val
                except Exception:
                    pass
                    
            # lux -> IDLE_LUX
            if 'lux' in data and data['lux'] is not None:
                try:
                    val = int(data['lux'])
                    val = max(0, min(1000, val))
                    cfg['IDLE_LUX'] = val
                    updated.append('IDLE_LUX')
                    # 同时更新灯光控制状态
                    with light_control_lock:
                        light_control_state['lux'] = val
                except Exception:
                    pass
            
            # 写回配置文件
            if updated:
                try:
                    with open(CONFIG_PATH, 'w') as f:
                        json.dump(cfg, f, indent=2, ensure_ascii=False)
                    print(f"配置已更新: {updated}")
                except Exception as e:
                    print(f"写入配置文件失败: {e}")
            
            return updated
    except Exception as e:
        print(f"更新配置时出错: {e}")
        return []

# ============================================================================
# 主程序入口
# ============================================================================

def main():
    """主程序入口"""
    print("=== Focus Lamp 主控制程序启动 ===")
    
    # 加载配置参数
    params = load_params_from_config()
    if not params:
        print("无法加载配置，程序退出")
        return
    
    print(f"已加载配置参数: {params}")
    
    # 初始化RGB服务
    print("初始化RGB服务...")
    rgb_service = RGBService()
    rgb_service.start()
    
    # 初始化专注服务
    print("初始化专注服务...")
    focus_service = FocusService(rgb_service)
    
    # 初始化机器人
    print("初始化机器人...")
    config = LeLampFollowerConfig(port=params['lamp_port'])
    robot = LeLampFollower(config)
    robot.connect()
    
    # 获取可用动作列表
    recordings_dir = os.path.join(os.path.dirname(__file__), "..", "recordings")
    available_actions = []
    if os.path.exists(recordings_dir):
        for file in os.listdir(recordings_dir):
            if file.endswith(f"_{params['lamp_id']}.csv"):
                action_name = file.replace(f"_{params['lamp_id']}.csv", "")
                available_actions.append(action_name)
    
    print(f"可用动作: {available_actions}")
    
    # 设置检测日志路径
    log_file_path = os.path.join(os.path.dirname(__file__), "detection_log.txt")
    
    # 更新全局变量
    focus_session_globals.update({
        'focus_service': focus_service,
        'robot': robot,
        'available_actions': available_actions,
        'log_file_path': log_file_path,
        'params': params
    })
    
    # 设置空闲灯光
    print("设置空闲灯光...")
    idle_rgb, idle_cct_k, idle_lux = compute_idle_rgb_from_config()
    rgb_service.dispatch("solid", idle_rgb)
    print(f"空闲灯光设置: CCT={idle_cct_k}K, Lux={idle_lux}, RGB={idle_rgb}")
    
    # 更新灯光控制状态
    with light_control_lock:
        light_control_state["running"] = True
        light_control_state["cct_k"] = idle_cct_k
        light_control_state["lux"] = idle_lux
    
    # 执行启动动作
    print("执行启动动作...")
    if "0_beginning" in available_actions:
        execute_action("0_beginning", robot, focus_service, params['lamp_id'])
    
    # 启动WebSocket服务器线程
    print("启动WebSocket服务器...")
    ws_thread = threading.Thread(target=start_websocket_server, daemon=True)
    ws_thread.start()
    
    # 启动灯光控制线程
    print("启动灯光控制线程...")
    light_thread = threading.Thread(target=light_control_thread, args=(rgb_service,), daemon=True)
    light_thread.start()
    
    # 打印可用动作
    print("\n=== 可用动作列表 ===")
    for action in available_actions:
        print(f"  - {action}")
    
    # 设置日志文件路径
    log_file_path = os.path.join(os.path.dirname(__file__), "detection_log.txt")
    print(f"\n检测日志文件路径: {log_file_path}")
    
    # 全局变量初始化完成
    print("\n=== 系统初始化完成 ===")
    print("WebSocket服务器监听: ws://192.168.137.104:5173")
    print("发送 {\"start_focus\": true} 开始专注会话")
    print("发送 {\"start_focus\": false} 停止专注会话")
    
    try:
        # 保持程序运行
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n收到中断信号，正在关闭...")
    finally:
        # 清理资源
        print("清理资源...")
        if "0_ending" in available_actions:
            execute_action("0_ending", robot, focus_service, params['lamp_id'])
        
        rgb_service.stop()
        robot.disconnect()
        print("程序已退出。")

if __name__ == "__main__":
    main()
