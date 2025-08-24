# SPDX-License-Identifier: MulanPSL-2.0
# Copyright (c) 2025, wheatfox <wheatfox17@icloud.com>

import threading
import time

try:
    from uapi.log import logger
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)

from car_controller import CarController
from camera_manager import CameraManager


class MainControlLoop:
    def __init__(self, car, keyboard_device, scene_lock, camera_manager=None):
        self.car = car
        self.keyboard_device = keyboard_device
        self.scene_lock = scene_lock
        self.camera_manager = camera_manager
        
        # Control parameters
        self.dt = 1.0 / 60.0  # 60 FPS
        self.speed = 1.5  # Translation speed
        self.rot_speed = 2.5  # Rotation speed
        
        # Create car controller
        self.car_controller = CarController(
            car, keyboard_device, self.dt, self.speed, self.rot_speed
        )
        
    def start_camera(self):
        """Start camera manager"""
        if self.camera_manager is not None:
            self.camera_manager.start_camera_thread()
            
    def stop_camera(self):
        """Stop camera manager"""
        if self.camera_manager is not None:
            self.camera_manager.stop_camera_thread()
            
    def run(self, scene_step_func):
        """Run main control loop"""
        logger.info("\nKeyboard Controls:")
        logger.info("Arrow Up/Down: Forward/Backward")
        logger.info("Arrow Left/Right: Left/Right")
        logger.info("[: Rotate left")
        logger.info("]: Rotate right")
        logger.info("ESC: Quit")
        
        try:
            while True:
                # Execute car control step
                if not self.car_controller.step():
                    logger.info("exiting simulation.")
                    break
                    
                # Scene step
                with self.scene_lock:
                    try:
                        scene_step_func()
                    except Exception as e:
                        logger.info(f"viewer closed or scene step failed: {e}")
                        break
                        
                # Control loop frequency
                time.sleep(self.dt)
                
        except KeyboardInterrupt:
            logger.info("interrupted by user")
        except Exception as e:
            logger.error(f"unexpected error: {e}")
        finally:
            # Stop camera
            self.stop_camera()
            logger.info("main control loop stopped")
