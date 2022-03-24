import board
from adafruit_funhouse import FunHouse
import adafruit_dps310
import adafruit_ahtx0
import time
import adafruit_dotstar
import adafruit_minimqtt.adafruit_minimqtt as MQTT
import ipaddress
import ssl
import wifi
import socketpool
import adafruit_requests
from adafruit_display_text import label
from adafruit_bitmap_font import bitmap_font
import microcontroller

funhouse = FunHouse(
    default_bg=0x0F0F00,
    scale=2,
)

TEMPERATURE_OFFSET = (3)  # Degrees C to adjust  temp to compensate for board produced heat
# Turn things off
funhouse.peripherals.set_dotstars(0x800000, 0x808000, 0x008000, 0x000080, 0x800080)    ## fill rainbow to start during bootup
funhouse.peripherals.dotstars.brightness = 0.2
funhouse.peripherals.led = True

i2c = board.I2C()
dps310 = adafruit_dps310.DPS310(i2c)
aht20 = adafruit_ahtx0.AHTx0(i2c)

# Get wifi details and more from a secrets.py file
try:
    from secrets import secrets
except ImportError:
    print("WiFi secrets are kept in secrets.py, please add them there!")
    raise

# screen update and report timing-related variables
secsAtBoot = time.monotonic()
mqttReportFreq = 10
screenUpdateFreq= 3
lastMqttReportSecs = 0
lastScreenUpdate = 0
# watchdog-related variables
wdCounter = 1
wdInput = -99
commsOK = True
wdTimeoutLength = 30
lastWDUpdate = time.monotonic()

print("ESP32-S2 Web Client")
# print("My MAC addr:", [hex(i) for i in wifi.radio.mac_address])

# print("Available WiFi networks:")
# for network in wifi.radio.start_scanning_networks():
#     print("\t%s\t\tRSSI: %d\tChannel: %d" % (str(network.ssid, "utf-8"),network.rssi, network.channel))
wifi.radio.start_scanning_networks()
wifi.radio.stop_scanning_networks()

print("Connecting to %s" % secrets["ssid"])
wifi.radio.connect(secrets["ssid"], secrets["password"])
print("Connected to %s!" % secrets["ssid"])
print("IP address: ", wifi.radio.ipv4_address)

## begin time
initial = time.monotonic()


##funhouse.peripherals.set_dotstars(0x800000, 0x808000, 0x008000, 0x000080, 0x800080)

def set_label_color(conditional, index, on_color):
    if conditional:
        funhouse.set_text_color(on_color, index)
    else:
        funhouse.set_text_color(0x808000, index)

# Create the labels
funhouse.display.show(None)
# slider_label = funhouse.add_text(
#     text="Slider:", text_position=(50, 30), text_color=0x808000
# )
# capright_label = funhouse.add_text(
#     text="Touch", text_position=(85, 10), text_color=0x808000
# )
# onoff_label = funhouse.add_text(text="OFF", text_position=(10, 25), text_color=0x808000)
# up_label = funhouse.add_text(text="UP", text_position=(10, 10), text_color=0x808000)
# sel_label = funhouse.add_text(text="SEL", text_position=(10, 60), text_color=0x808000)
# down_label = funhouse.add_text(
#      text="DOWN", text_position=(10, 100), text_color=0x808000
# )
title_label = funhouse.add_text(text="Attic Sensor",
    text_position=(10, 7), text_color=0x808000, text_font="fonts/Arial-Bold-12.pcf"
)
errorCount_val = funhouse.add_text(text="XX",
    text_position=(110, 5), text_color=0xFF0000
)
temp_label = funhouse.add_text(text="Temp:",
    text_position=(8, 34), text_color=0x808000
)
pres_label = funhouse.add_text( text="Pres:",
    text_position=(8, 54), text_color=0x808000
)
hum_label = funhouse.add_text( text="Hum'y:",
    text_position=(2, 74), text_color=0x808000
)
comms_label = funhouse.add_text( text="COMMS",
    text_position=(1, 89), text_color=0x808000
)
ssid_label = funhouse.add_text( text="SSID:",
    text_position=(1, 103), text_color=0x808000
)
IP_label = funhouse.add_text( text="IP:",
    text_position=(7, 113), text_color=0x808000
)
temp_val = funhouse.add_text( text="xxxx",
    text_position=(42, 32), text_color=0x808000, text_font="fonts/Arial-Bold-12.pcf"
)
pres_val = funhouse.add_text( text="xxxx",
    text_position=(42, 52), text_color=0x808000, text_font="fonts/Arial-Bold-12.pcf"
)
hum_val = funhouse.add_text( text="xxxx",
    text_position=(42, 72), text_color=0x808000, text_font="fonts/Arial-Bold-12.pcf"
)
comms_val = funhouse.add_text( text="XXXX",
    text_position=(34, 89), text_color=0xFFFFFF
)
sincecommstime_val = funhouse.add_text( text="(XX)",
    text_position=(55, 89), text_color=0x808000
)
wd_out_val = funhouse.add_text( text="XX",
    text_position=(85, 89), text_color=0x808000
)
wd_in_val = funhouse.add_text( text="XX",
    text_position=(103, 89), text_color=0x808000
)
ssid_val = funhouse.add_text( text="networkName",
    text_position=(34, 103), text_color=0x808000
)
IP_val = funhouse.add_text( text="xxx.xxx.xxx.xxx",
    text_position=(34, 113), text_color=0x808000
)

# Create a socket pool
pool = socketpool.SocketPool(wifi.radio)

MQTT_TEMP_TOPIC = "Liberty/Attic/Temperature"
MQTT_RH_TOPIC = "Liberty/Attic/RelativeHumidity"
MQTT_LIGHT_TOPIC = "Liberty/Attic/Light"

### Code ###
# Define callback methods which are called when events occur
# pylint: disable=unused-argument, redefined-outer-name
def connect(mqtt_client, userdata, flags, rc):
    # This function will be called when the mqtt_client is connected
    # successfully to the broker.
    print("Connected to MQTT Broker!")
    #print("Flags: {0}\n RC: {1}".format(flags, rc))

def disconnect(mqtt_client, userdata, rc):
    # This method is called when the mqtt_client disconnects
    # from the broker.
    print("Disconnected from MQTT Broker!")

def subscribe(mqtt_client, userdata, topic, granted_qos):
    # This method is called when the mqtt_client subscribes to a new feed.
    print("Subscribed to {0} with QOS level {1}".format(topic, granted_qos))

def unsubscribe(mqtt_client, userdata, topic, pid):
    # This method is called when the mqtt_client unsubscribes from a feed.
    print("Unsubscribed from {0} with PID {1}".format(topic, pid))

#def publish(mqtt_client, userdata, topic, pid):
#    # This method is called when the mqtt_client publishes data to a feed.
#    print("Published {0} with PID {1}".format(topic, pid))

def message(client, topic, message):
    # Method callled when a client's subscribed feed has a new value.
    print("New message on topic {0}: {1}".format(topic, message))
    if topic == 'Liberty/Attic/MQTT-ESP32-WDT':
        # this is a watchdog refresh message from openHAB
        #print("Refresh watchdog from openHAB/MQTT")
        global wdInput
        wdInput = float(message)
        global lastWDUpdate
        #print(lastWDUpdate)
        lastWDUpdate = time.monotonic() # update watchdog timer
        #print(lastWDUpdate)

# Initialize a new MQTT Client object
# Set up a MiniMQTT Client
mqtt_client = MQTT.MQTT(
    broker=secrets["mqtt_broker"],
    port=secrets["mqtt_port"],
    username=None,
    password=None,
    socket_pool=pool,
    ssl_context=ssl.create_default_context(),
)

# Connect callback handlers to mqtt_client
mqtt_client.on_connect = connect
mqtt_client.on_disconnect = disconnect
mqtt_client.on_subscribe = subscribe
mqtt_client.on_unsubscribe = unsubscribe
#mqtt_client.on_publish = publish
mqtt_client.on_message = message

print("Attempting to connect to %s" % mqtt_client.broker)
mqtt_client.connect()

print("Subscribing to watchdog topic..")
mqtt_client.subscribe("Liberty/Attic/MQTT-ESP32-WDT")

sensorwrite_timestamp = time.monotonic()
last_pir = None
firstRun = True
tempFiltConst = 0.25

countErrors = 0

funhouse.display.show(funhouse.splash)

brightSetTime = 0

## set lights back off
funhouse.peripherals.set_dotstars(0x000000, 0x000000, 0x000000, 0x000000, 0x000000)    ## fill black after startup

while True:

    funhouse.peripherals.led = False

    ## handle errors on MQTT loop?
    try:
        # do the MQTT maintenance loop
        if mqtt_client.is_connected():      ## only if MQTT client is still connected, then do the maintenance loop
            mqtt_client.loop()
        else:
            mqtt_client.connect()
    except:
        print("Error in mqtt client loop.")
        countErrors = countErrors + 1       ## add to error accum variable

    if (time.monotonic() - lastMqttReportSecs > mqttReportFreq):

        # calc/apply temperature offset
        # currently-known offset is -12 degF -- maybe will get more precise/variable over time
        tempFahrRaw = (funhouse.peripherals.temperature*(9/5)+32) - 12
        # print("Raw temp with offset: %0.1f" % tempFahrRaw)
        if (firstRun):      ## if first run, just use the current value as last..
            tempFahrLast = tempFahrRaw

        # calculate filtered temperature value
        tempFahr = tempFiltConst*tempFahrRaw + (1-tempFiltConst)*tempFahrLast

        ## save last temp value
        tempFahrLast = tempFahr

        ## handle errors on getting light values?
        try:
            lightRaw = funhouse.peripherals.light
        except:
            print("Could not retrieve light value?")
            lightRaw = lightLast
            countErrors = countErrors + 1       ## add to error accum variable

        if (firstRun):      ## if first run, just use the current value as last..
            lightLast = lightRaw
        lightFilt = 0.25*lightRaw + 0.75*lightLast

        ## turn off firstRun; never need it again
        firstRun = False

        if mqtt_client.is_connected():      ## only if MQTT client is still connected, then publish

            ## handle errors on publish..
            try:
                print("Publishing to MQTT.")
                mqtt_client.publish(MQTT_TEMP_TOPIC, float(tempFahr))
                mqtt_client.publish(MQTT_RH_TOPIC, funhouse.peripherals.relative_humidity)
                mqtt_client.publish(MQTT_LIGHT_TOPIC, lightFilt)
                mqtt_client.publish("Liberty/Attic/ESP32-UptimeMins", round((time.monotonic()-secsAtBoot)/60,0))
                mqtt_client.publish("Liberty/Attic/ESP32-MQTT-WDT", wdCounter)
            except:
                print("Could not publish")
                countErrors = countErrors + 1       ## add to error accum variable

            lastMqttReportSecs = time.monotonic()
            wdCounter = wdCounter + 1
            if wdCounter > 99:
                wdCounter = 1

    ## update screen after delay time
    if time.monotonic() - lastScreenUpdate > screenUpdateFreq:
        funhouse.set_text("%0.1F°F" % float(tempFahr), temp_val)
        funhouse.set_text("%0.1F RH" % funhouse.peripherals.relative_humidity, hum_val)
        funhouse.set_text("%d mbar" % funhouse.peripherals.pressure, pres_val)
        funhouse.set_text("%s" % secrets["ssid"], ssid_val)
        funhouse.set_text("%s" % wifi.radio.ipv4_address, IP_val)
        if commsOK:
            funhouse.set_text("OK", comms_val)
            funhouse.set_text_color(0x00A300, comms_val)
        else:
            funhouse.set_text("FAIL", comms_val)
            funhouse.set_text_color(0xEE0000, comms_val)
        funhouse.set_text("(%d)" % round(time.monotonic() - lastWDUpdate,0), sincecommstime_val)
        funhouse.set_text("%d" % wdCounter, wd_out_val)
        funhouse.set_text("%d" % wdInput, wd_in_val)
        funhouse.set_text("%d" % countErrors, errorCount_val)
        lastScreenUpdate = time.monotonic()
        ##print("temperatures - DPS, AHT, processor, funhouse: ", dps310.temperature, aht20.temperature, microcontroller.cpu.temperature, funhouse.peripherals.temperature)

    ## light sleep for 3 seconds to keep heat down?
    #funhouse.enter_light_sleep(3)
    #funhouse.display.show(funhouse.splash)

    if time.monotonic() - lastWDUpdate > wdTimeoutLength:
        commsOK = False
    else:
        commsOK = True

    # print(lastWDUpdate)

    ## print(funhouse.peripherals.temperature, funhouse.peripherals.relative_humidity)

    # calc # of seconds since boot if needed for debugging
    now = time.monotonic()
    ##print(now-initial)

    #print("funhouse.display.brightness: ", funhouse.display.brightness)
    #print("funhouse.peripherals.dotstars.brightness: ", funhouse.peripherals.dotstars.brightness)

    ## handle errors on getting light values?
    try:
        slider = funhouse.peripherals.slider
    except:
        print("Could not retrieve slider value?")
        slider = 1.0
        countErrors = countErrors + 1       ## add to error accum variable

    if slider is not None:
        if slider < 0.05:   # don't let the screen go totally off
            slider = 0.05
        ##funhouse.peripherals.dotstars.brightness = slider
        funhouse.display.brightness = slider
        #print("slider: ", slider)
        brightSetTime = time.monotonic()
        #print("funhouse.display.brightness: ", funhouse.display.brightness)
        #print("funhouse.peripherals.dotstars.brightness: ", funhouse.peripherals.dotstars.brightness)

    ## set screen brightness back to low after some seconds..
    if (now - brightSetTime > 10) and (funhouse.display.brightness > 0.15):
        ##funhouse.peripherals.dotstars.brightness = 0.15
        funhouse.display.brightness = 0.15
