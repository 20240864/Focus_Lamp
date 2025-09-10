import time
import neopixel
import RPi.GPIO as GPIO

LED_PIN = 18        # ֱ���� BCM ���
NUM_LEDS = 8
pixels = neopixel.NeoPixel(LED_PIN, NUM_LEDS, auto_write=False)

# ѭ����ʾ��ɫ
while True:
    # ��ɫ
    pixels.fill((255, 0, 0))
    pixels.show()
    time.sleep(1)

    # ��ɫ
    pixels.fill((0, 255, 0))
    pixels.show()
    time.sleep(1)

    # ��ɫ
    pixels.fill((0, 0, 255))
    pixels.show()
    time.sleep(1)
