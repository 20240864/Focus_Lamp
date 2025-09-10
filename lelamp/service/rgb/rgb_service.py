from typing import Any, List, Union
try:
    from rpi_ws281x import PixelStrip, Color
except (ImportError, ModuleNotFoundError):
    # Mock implementation for non-Raspberry Pi environments
    class Color:
        def __init__(self, r, g, b):
            pass

    class PixelStrip:
        def __init__(self, num, pin, freq_hz=800000, dma=10, invert=False, brightness=255, channel=0):
            self._led_data = [0] * num

        def begin(self):
            pass
        def setPixelColor(self, n, color):
            if n < len(self._led_data):
                self._led_data[n] = color
        def show(self):
            pass
        def numPixels(self):
            return len(self._led_data)

from ..base import ServiceBase


class RGBService(ServiceBase):
    def __init__(self, 
                 led_count: int = 64,
                 led_pin: int = 12,
                 led_freq_hz: int = 800000,
                 led_dma: int = 10,
                 led_brightness: int = 255,
                 led_invert: bool = False,
                 led_channel: int = 0):
        super().__init__("rgb")
        self.logger.info(f"Initializing RGBService with led_count={led_count}, led_pin={led_pin}")
        
        self.led_count = led_count
        self.strip = PixelStrip(
            led_count, led_pin, led_freq_hz, led_dma, 
            led_invert, led_brightness, led_channel
        )
        self.strip.begin()
        self.logger.info("PixelStrip.begin() called.")
        
    def handle_event(self, event_type: str, payload: Any):
        if event_type == "solid":
            self._handle_solid(payload)
        elif event_type == "paint":
            self._handle_paint(payload)
        else:
            self.logger.warning(f"Unknown event type: {event_type}")
    
    def _handle_solid(self, color_code: Union[int, tuple]):
        """Fill entire strip with single color"""
        if isinstance(color_code, tuple) and len(color_code) == 3:
            color = Color(color_code[0], color_code[1], color_code[2])
        elif isinstance(color_code, int):
            color = color_code
        else:
            self.logger.error(f"Invalid color format: {color_code}")
            return
            
        self.logger.info(f"Setting solid color: {color_code}")
        for i in range(self.led_count):
            self.strip.setPixelColor(i, color)
        self.strip.show()
        self.logger.info("PixelStrip.show() called to update LEDs.")
    
    def _handle_paint(self, colors: List[Union[int, tuple]]):
        """Set individual pixel colors from array"""
        if not isinstance(colors, list):
            self.logger.error(f"Paint payload must be a list, got: {type(colors)}")
            return
            
        max_pixels = min(len(colors), self.led_count)
        
        for i in range(max_pixels):
            color_code = colors[i]
            if isinstance(color_code, tuple) and len(color_code) == 3:
                color = Color(color_code[0], color_code[1], color_code[2])
            elif isinstance(color_code, int):
                color = color_code
            else:
                self.logger.warning(f"Invalid color at index {i}: {color_code}")
                continue
                
            self.strip.setPixelColor(i, color)
        
        self.strip.show()
        self.logger.debug(f"Applied paint pattern with {max_pixels} colors")
    
    def clear(self):
        """Turn off all LEDs"""
        self.logger.info("Clearing all LEDs.")
        for i in range(self.led_count):
            self.strip.setPixelColor(i, Color(0, 0, 0))
        self.strip.show()
        self.logger.info("PixelStrip.show() called to clear LEDs.")
    
    def stop(self, timeout: float = 5.0):
        """Override stop to clear LEDs before stopping"""
        self.clear()
        super().stop(timeout)