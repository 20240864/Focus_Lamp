import time
try:
    from rpi_ws281x import PixelStrip, Color
except (ImportError, ModuleNotFoundError):
    print("rpi_ws281x library not found. Please install it.")
    print("On a Raspberry Pi, you can usually install it with:")
    print("sudo pip3 install rpi_ws281x")
    exit()

# LED strip configuration:
LED_COUNT = 40      # Number of LED pixels.
LED_PIN = 12        # GPIO pin connected to the pixels (must support PWM!).
LED_FREQ_HZ = 800000  # LED signal frequency in hertz (usually 800khz)
LED_DMA = 10        # DMA channel to use for generating signal (try 10)
LED_BRIGHTNESS = 255 # Set to 0 for darkest and 255 for brightest
LED_INVERT = False  # True to invert the signal (when using NPN transistor level shift)
LED_CHANNEL = 0       # set to '1' for GPIOs 13, 19, 41, 45 or 53

def simple_red_test():
    """
    A simple test to light up the RGB strip with a solid red color
    using the rpi_ws281x library directly.
    """
    print("--- Simple RGB Red Light Test (Direct) ---")
    
    # Create PixelStrip object with appropriate configuration.
    strip = PixelStrip(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL)
    # Intialize the library (must be called once before other functions).
    strip.begin()

    try:
        print("Setting color to RED...")
        # Set all pixels to red.
        for i in range(strip.numPixels()):
            strip.setPixelColor(i, Color(255, 0, 0))
        strip.show() # Update the strip to show the new colors

        print("Light will stay on for 5 seconds...")
        time.sleep(5)
        
        print("Test finished.")

    except Exception as e:
        print(f"An error occurred: {e}")

    finally:
        # Turn off all pixels.
        print("Turning off light.")
        for i in range(strip.numPixels()):
            strip.setPixelColor(i, Color(0, 0, 0))
        strip.show()

if __name__ == "__main__":
    simple_red_test()