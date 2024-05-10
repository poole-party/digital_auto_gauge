import busio
import board
import displayio
import math
import supervisor
from adafruit_bitmap_font import  bitmap_font
from adafruit_display_text import label
from adafruit_st7735r import ST7735R
from analogio import AnalogIn
from fourwire import FourWire

def getTempFromADC(thermistor):
    VIN = 3.3
    R0 = 10000
    rT = R0 * (65535 / thermistor - 1)
    logRT = math.log(rT)

    # steinhart constants
    A = 0.0009086268490
    B = 0.0002045041393
    C = 0.0000001912131738

    kelvin = 1 / (A + (B * logRT) + C * math.pow(logRT, 3))
    celsius = kelvin - 273.15
    fahrenheit = celsius * 9 / 5 + 32

    return fahrenheit

# Release any resources currently in use for the displays
displayio.release_displays()

# init the spi bus and allocate the requisite pins
spi = busio.SPI(clock=board.GP10, MOSI=board.GP11)
tft_cs = board.GP13
tft_dc = board.GP12
tft_reset = board.GP9
display_bus = FourWire(spi, command=tft_dc, chip_select=tft_cs, reset=tft_reset)

# set colors and load custom fonts to make it look pretty
saira = bitmap_font.load_font("fonts/saira-bold-italic-28pt.bdf")
sairaSmall = bitmap_font.load_font("fonts/saira-semibold-10pt.bdf")
label_color = 0xff0303

# init the measurement vars
boost_raw = AnalogIn(board.A0)
boost_pressure = boost_raw.value / 1000 - 13.043
thermistor = AnalogIn(board.A2)
oil_temp = getTempFromADC(thermistor.value)
temp_samples_index = 0
sample_size = 50
oil_temp_samples = [oil_temp] * sample_size
start_boost_loop = 0
start_oil_loop = 0
last_loop = 101

# init the display and define the display context
display_height = 128
display_width = 128
screen = displayio.Group()
display = ST7735R(display_bus, width=display_width, height=display_height, colstart=2, rowstart=3)
display.root_group = screen

color_bitmap = displayio.Bitmap(display_width, display_height, 1)
color_palette = displayio.Palette(1)
color_palette[0] = 0x000000

grid = displayio.TileGrid(color_bitmap, pixel_shader=color_palette, x=0, y=0)
display.rotation = 180
screen.append(grid)

# common vars shared by both gauges
labels_x_pos = 1
units_x_pos = display_width - 7


# === build boost gauge ===
boost_label = label.Label(sairaSmall, text="BOOST", color=label_color)
boost_label.anchor_point = (0.0, 0.0)
boost_label.anchored_position = (labels_x_pos, 5)

boost_units = label.Label(sairaSmall, text="psi", color=0xffffff)
boost_units.anchor_point = (1.0, 1.0)
boost_units.anchored_position = (units_x_pos, display_height / 2 - 7)

boost_readout = label.Label(
    saira,
    text=str(f'{boost_pressure:5.1f}'),
    color=0xffffff
)
boost_readout.anchor_point = (1.0, 1.0)
boost_readout.anchored_position = (display_width - 32, display_height / 2 - 10)


# === build oil temp gauge ===
oil_temp_label = label.Label(sairaSmall, text="OIL TEMP", color=label_color)
oil_temp_label.anchor_point = (0.0, 0.0)
oil_temp_label.anchored_position = (labels_x_pos, display_height / 2 + 5)

# since the startup temp is unknown, hide these units and the associated readout 
# on initial render by setting their color to 0x000000
# the actual display color will be determined in the first iteration of the update loop below
oil_temp_units = label.Label(sairaSmall, text="°F", color=0x000000)
oil_temp_units.anchor_point = (1.0, 1.0)
oil_temp_units.anchored_position = (units_x_pos, display_height - 10)

oil_temp_readout = label.Label(
    saira, 
    text=str(int(oil_temp)), 
    color=0x000000
)
oil_temp_readout.anchor_point = (1.0, 1.0)
oil_temp_readout.anchored_position = (display_width - 27, display_height - 10)


# render gauges on display
screen.append(boost_label)
screen.append(oil_temp_label)
screen.append(boost_units)
screen.append(oil_temp_units)
screen.append(boost_readout)
screen.append(oil_temp_readout)

while True:
    # update boost readout value every 100ms
    if (last_loop - start_boost_loop > 100):
        boost_pressure = boost_raw.value / 1000 - 13.05
        boost_readout.text = str(f'{boost_pressure:5.1f}')
        start_boost_loop = supervisor.ticks_ms()

    # update temp readout value every 200ms
    if (last_loop - start_oil_loop > 200):
        oil_temp = getTempFromADC(thermistor.value)
        oil_temp_damped = '- - '
        oil_temp_samples[temp_samples_index] = int(oil_temp)
        temp_samples_index = (temp_samples_index + 1) % sample_size

        if (oil_temp < 0):
            update_color = 0xffffff
        else:
            oil_temp_damped = sum(oil_temp_samples) / len(oil_temp_samples)
            oil_temp_damped = str(int(oil_temp_damped))
            if (oil_temp < 200):
                # blue
                update_color = 0x3040ff
            elif (oil_temp < 270):
                # white
                update_color = 0xffffff
            else:
                # red
                update_color = 0xff2020

        oil_temp_units.color = update_color
        oil_temp_readout.color = update_color
        oil_temp_readout.text = oil_temp_damped
        start_oil_loop = supervisor.ticks_ms()

    last_loop = supervisor.ticks_ms()

    # if supervisor.ticks rolls over, reset all of the counters so the gauge doesn't freeze
    if (start_boost_loop > last_loop or start_oil_loop > last_loop):
        start_boost_loop = 0
        start_oil_loop = 0
        last_loop = 101
