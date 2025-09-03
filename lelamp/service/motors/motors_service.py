import os
import csv
import time
import json
from typing import Any, List
from ..base import ServiceBase
from lelamp.follower import LeLampFollowerConfig, LeLampFollower


class MotorsService(ServiceBase):
    def __init__(self, port: str, lamp_id: str, fps: int = 30):
        super().__init__("motors")
        self.port = port
        self.lamp_id = lamp_id
        self.fps = fps
        self.robot_config = LeLampFollowerConfig(port=port, id=lamp_id)
        self.robot: LeLampFollower = None
        self.recordings_dir = os.path.join(os.path.dirname(__file__), "..", "..", "recordings")
        self.home_config_path = os.path.join(os.path.dirname(__file__), "..", "..", "follower", "home.json")
        self.playing = False
        self.homing = False

    # 启动电机服务
    def start(self):
        super().start() # 启动基础服务
        self.robot = LeLampFollower(self.robot_config) # 初始化机器人
        self.robot.connect(calibrate=True) # 连接机器人并校准
        self.logger.info(f"Motors service connected to {self.port}") # 

    def stop(self, timeout: float = 5.0):
        if self.robot:
            self.robot.disconnect()
            self.robot = None
        super().stop(timeout)

    def handle_event(self, event_type: str, payload: Any):
        if event_type == "play":
            self._handle_play(payload)
        elif event_type == "go_home":
            self._go_home()
        elif event_type == "go_home_from_json":
            self._go_home_from_json()
        else:
            self.logger.warning(f"Unknown event type: {event_type}")

    def _go_home_from_json(self):
        """Move the robot to the home position defined in home.json."""
        if not self.robot:
            self.logger.error("Robot not connected")
            return

        try:
            self.homing = True
            self.logger.info(f"Homing robot from {self.home_config_path}...")

            with open(self.home_config_path, 'r') as f:
                home_config = json.load(f)
            
            if 'homing_offset' not in home_config:
                self.logger.error(f"'homing_offset' not found in {self.home_config_path}")
                return

            # The send_action method expects a dictionary of {motor_name: position}
            home_action = home_config['homing_offset']
            self.robot.send_action(home_action)

            self.logger.info("Waiting for homing movement to complete...")
            time.sleep(2)  # Give it a moment to start moving

            self.logger.info("Homing complete.")

        except FileNotFoundError:
            self.logger.error(f"Home config file not found: {self.home_config_path}")
        except json.JSONDecodeError:
            self.logger.error(f"Error decoding JSON from {self.home_config_path}")
        except Exception as e:
            self.logger.error(f"Error during homing from JSON: {e}")
        finally:
            self.homing = False

    def _go_home(self):
        """Move the robot to its calibrated home position."""
        if not self.robot:
            self.logger.error("Robot not connected")
            return
        try:
            self.homing = True
            self.logger.info("Homing robot...")
            home_action = {f"{joint}.pos": 0.0 for joint in self.robot.bus.motors}
            self.robot.send_action(home_action)

            self.logger.info("Waiting for homing movement to complete by checking position stability...")

            last_positions = None
            stable_counter = 0
            # Threshold in degrees. If position changes less than this, it's considered stable.
            MOVEMENT_THRESHOLD = 0.5
            # How many consecutive stable reads we need to be sure it stopped.
            STABLE_READS_REQUIRED = 5  # e.g., 5 * 0.1s = 0.5 seconds of stability

            while stable_counter < STABLE_READS_REQUIRED:
                try:
                    current_positions = self.robot.bus.sync_read("Present_Position")

                    if last_positions is not None:
                        is_moving = False
                        for motor_name in current_positions:
                            if abs(current_positions[motor_name] - last_positions.get(motor_name, 0)) > MOVEMENT_THRESHOLD:
                                is_moving = True
                                break
                        
                        if is_moving:
                            stable_counter = 0
                        else:
                            stable_counter += 1
                    
                    last_positions = current_positions

                except Exception as read_exc:
                    self.logger.warning(f"Could not read 'Present_Position' for stability check: {read_exc}. Retrying...")
                    stable_counter = 0
                
                time.sleep(0.1)

            # Wait an additional second after motors have stopped
            time.sleep(1.0)

            self.logger.info("Homing complete.")
        except Exception as e:
            self.logger.error(f"Error during homing: {e}")
        finally:
            self.homing = False

    def _handle_play(self, recording_name: str):
        """Play a recording by name"""
        if not self.robot:
            self.logger.error("Robot not connected")
            return

        csv_filename = f"{recording_name}_{self.lamp_id}.csv"
        csv_path = os.path.join(self.recordings_dir, csv_filename)

        if not os.path.exists(csv_path):
            self.logger.error(f"Recording not found: {csv_path}")
            return

        try:
            self.playing = True
            with open(csv_path, 'r') as csvfile:
                csv_reader = csv.DictReader(csvfile)
                actions = list(csv_reader)

            self.logger.info(f"Playing {len(actions)} actions from {recording_name}")

            for row in actions:
                t0 = time.perf_counter()

                # Extract action data (exclude timestamp column)
                action = {key: float(value) for key, value in row.items() if key != 'timestamp'}
                self.robot.send_action(action)

                # Use time.sleep instead of busy_wait to avoid blocking other threads
                sleep_time = 1.0 / self.fps - (time.perf_counter() - t0)
                if sleep_time > 0:
                    time.sleep(sleep_time)

            self.logger.info(f"Finished playing recording: {recording_name}")

        except Exception as e:
            self.logger.error(f"Error playing recording {recording_name}: {e}")
        finally:
            self.playing = False

    # 获取可用的动作列表
    def get_available_recordings(self) -> List[str]:
        """Get list of recording names available for this lamp ID"""
        if not os.path.exists(self.recordings_dir):
            return []
        
        recordings = []
        suffix = f"_{self.lamp_id}.csv" # 动作文件名后缀
        
        for filename in sorted(os.listdir(self.recordings_dir)): # 遍历记录目录
            if filename.endswith(suffix): # 检查文件名是否以lamp_id后缀结尾
                # Remove the lamp_id suffix to get the recording name
                recording_name = filename[:-len(suffix)] # 去掉lamp_id后缀
                recordings.append(recording_name) # 去掉后缀后的文件名

        return recordings

    def is_playing(self) -> bool:
        """Check if a recording is currently playing."""
        return self.playing

    def is_homing(self) -> bool:
        """Check if the robot is currently homing."""
        return self.homing