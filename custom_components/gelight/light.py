"""
Async platform to control **SOME** GE light devices.
Supports color temperature and brightness. RGB color light is not tested.
This is based on some code of the tuya light and (python-laurel)[https://github.com/google/python-laurel].
Example configuration:
  - platform: gelight
    username: user_from_ge
    password: pass_from_ge
    lights:
      - id: 1_from_ge
        mac: mac_in_lowercase_from_ge
        name: name_in_hass
        type: typeid_from_ge
"""
import voluptuous as vol
from homeassistant.components.light import LightEntity, PLATFORM_SCHEMA, ATTR_BRIGHTNESS,ATTR_COLOR_TEMP,ATTR_HS_COLOR,SUPPORT_BRIGHTNESS,SUPPORT_COLOR,SUPPORT_COLOR_TEMP
from homeassistant.const import (CONF_USERNAME, CONF_PASSWORD,CONF_HOST, CONF_ID, CONF_LIGHTS, CONF_NAME,CONF_MAC,CONF_TYPE)
CONF_MAX_BRIGHT = 'max_brightness'
CONF_MIN_BRIGHT = 'min_brightness'
import homeassistant.helpers.config_validation as cv
from homeassistant.util import color as colorutil
from time import time
from time import sleep
import dimond
import threading
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.device_registry import format_mac
from datetime import timedelta
SCAN_INTERVAL = timedelta(seconds=240)
import logging
_LOGGER = logging.getLogger(__name__)


CIRCADIAN_BRIGHTNESS=True
try:
  from custom_components.circadian_lighting import DOMAIN, CIRCADIAN_LIGHTING_UPDATE_TOPIC, DATA_CIRCADIAN_LIGHTING
except:
  CIRCADIAN_BRIGHTNESS=False
#REQUIREMENTS = ['pytuya==7.0.2']


DEFAULT_ID = '1'

LIGHT_SCHEMA = vol.Schema({
    vol.Optional(CONF_ID, default=DEFAULT_ID): cv.string,
    vol.Optional(CONF_NAME): cv.string,
    vol.Optional(CONF_MAC): cv.string,
    vol.Optional(CONF_TYPE): cv.string,
    vol.Optional(CONF_MIN_BRIGHT, default=1):
        vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
    vol.Optional(CONF_MAX_BRIGHT, default=100):
        vol.All(vol.Coerce(int), vol.Range(min=1, max=100))
})

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_USERNAME): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
    vol.Optional(CONF_ID, default=DEFAULT_ID): cv.string,
    vol.Optional(CONF_LIGHTS, default=[]):
        vol.All(cv.ensure_list, [LIGHT_SCHEMA])
})
#The callback is buggy and not used here.
#Instead I assume the state is correct which is reasonably reliable and fast
#is you always use hass to control the device.
#Only one device is allowed to connect to the mesh through bluetooth anyway.
#The light status is unknown when hass reboots.
def callback(mesh, data):
    if data[7] != 0xdc:
        return
    responses = data[10:]
    for i in range(len(responses),4):
        response = responses[i:i+4]
        devid=response[0];
        if devid==0:
          break
        device=mesh.devices[devid]
        brightness = response[2]
        if brightness >= 128:
          brightness = brightness - 128
          device.red = int(((response[3] & 0xe0) >> 5) * 255 / 7)
          device.green = int(((response[3] & 0x1c) >> 2) * 255 / 7)
          device.blue = int((response[3] & 0x3) * 255 / 3)
          device.rgb = True
        else:
          device.temperature = response[3]
          device.rgb = False
        device._brightness=(255*brightness//100)


async def async_setup_platform(hass, config, async_add_devices, discovery_info=None):
    """Set up of the GE light."""
    devices = config.get(CONF_LIGHTS)
    lights = []

    mesh= laurel_mesh(
            config.get(CONF_USERNAME),
            config.get(CONF_PASSWORD)
    )
    for  device_config in devices:
        mac=device_config.get(CONF_MAC)
        min_brightness = device_config.get(CONF_MIN_BRIGHT)
        max_brightness = device_config.get(CONF_MAX_BRIGHT)
        lights.append(GEDevice(hass,mesh,mac,device_config.get(CONF_ID),device_config.get(CONF_NAME),device_config.get(CONF_TYPE),max_brightness,min_brightness))
    async_add_devices(lights)
    mesh.devices={}
    for light in lights:
      mesh.devices[light.id]=light
    #retry 3 times
    await hass.async_add_executor_job(mesh.connect)
    async def async_update(now=None):
        await hass.async_add_executor_job(mesh.update_status)
    async_track_time_interval(hass, async_update, SCAN_INTERVAL)

class GEDevice(LightEntity):
    """Representation of a GE light."""

    def __init__(self, hass,network,mac,
        lightid,name,type,max_brightness,min_brightness,icon=None):
        """Initialize the GE light."""
        self.hass = hass
        self.id = int(lightid)
        self.mac = mac
        self.type = int(type)
        self.network = network
        self.power = None
        self._unique_id = format_mac(mac)
        self._name = name
        self._icon = icon
        self._lightid = lightid
        self._cl = None
        self._brightness = 0
        self._max_brightness = int (255* max_brightness/100.)
        self._min_brightness = int (255* min_brightness/100.)
        self._min_mireds = colorutil.color_temperature_kelvin_to_mired(7000)
        self._max_mireds = colorutil.color_temperature_kelvin_to_mired(2000)
        self._temperature = self.max_mireds
        self.ratio = -100./(self.max_mireds-self.min_mireds)
        self._color = (0, 0)
        self.red = 0
        self.green = 0
        self.blue = 0

    @property
    def unique_id(self):
        """Return the entity unique ID."""
        return self._unique_id

    @property
    def name(self):
        """Get name of light."""
        return self._name
    @property
    def icon(self):
        """Return the icon."""
        return self._icon
    @property
    def min_mireds(self):
        """Return color temperature min mireds."""
        return self._min_mireds

    @property
    def max_mireds(self):
        """Return color temperature max mireds."""
        return self._max_mireds
    @property
    def hs_color(self):
        """Return the hs_color of the light."""
        return self._color

    #autobrightness from circadian_lighting if enabled
    def calc_brightness(self):
        if self._cl==None:
          self._cl = self.hass.data.get(DATA_CIRCADIAN_LIGHTING)
          if self._cl==None:
            return self.brightness
        if self._cl.data['percent'] > 0:
            return self._max_brightness
        else:
            return int(((self._max_brightness - self._min_brightness) * ((100+self._cl.data['percent']) / 100)) + self._min_brightness)
    async def async_turn_on(self, **kwargs):
        """Turn light on."""
        await self.hass.async_add_executor_job(self.set_power,True)
        brightness = kwargs.get(ATTR_BRIGHTNESS, None)
        _LOGGER.debug("%s: request brightness %s", self.entity_id, str(brightness))
        #manual brightness
        if brightness:
          #self._brightness = brightness
          await self.hass.async_add_executor_job(self.set_brightness,brightness)
        else:
          #autobrightness if brightness is not set
          if CIRCADIAN_BRIGHTNESS:
            brightness = self.calc_brightness()
            _LOGGER.debug("%s: calculated brightness %s", self.entity_id, str(brightness))
            await self.hass.async_add_executor_job(self.set_brightness,brightness)
        if self.support_temp:
          color_temp = kwargs.get(ATTR_COLOR_TEMP, None)
          if color_temp:
            await self.hass.async_add_executor_job(self.set_color_temp,color_temp)
          else:
            #autocolortemp when brightness and color temp is not set
            if CIRCADIAN_BRIGHTNESS and not brightness:
              kelvin=self._cl.data['colortemp']
              temperature = colorutil.color_temperature_kelvin_to_mired(kelvin)
              if self._temperature != temperature:
                self._temperature = temperature
                await self.hass.async_add_executor_job(self.set_color_temp, self._temperature)

        if ATTR_HS_COLOR in kwargs:
          await self.hass.async_add_executor_job(self.set_hs, kwargs[ATTR_HS_COLOR])
        _LOGGER.debug("%s: adjusted brightness %s", self.entity_id, str(brightness))
        #self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        """Turn light off."""
        await self.hass.async_add_executor_job(self.set_power,False)
    @property
    def is_on(self):
        """Return true if light is on."""
        return self.power

    @property
    def brightness(self):
        """Return the brightness of the light."""
        return int(self._brightness)
    @property
    def color_temp(self):
        """Return the temperature of the light."""
        return int(self._temperature)
    @property
    def supported_features(self):
        """Flag supported features."""
        supports = SUPPORT_BRIGHTNESS
        if self.support_rgb():
            supports = supports | SUPPORT_COLOR
        if self.support_color_temp():
            supports = supports | SUPPORT_COLOR_TEMP
        return supports
    def support_rgb(self):
        if self.type == 6 or \
           self.type == 7 or \
           self.type == 8 or \
           self.type == 21 or \
           self.type == 22 or \
           self.type == 23:
            return True
        return False
    def support_color_temp(self):
        if self.support_rgb() or \
           self.type == 5 or \
           self.type == 19 or \
           self.type == 20 or \
           self.type == 80 or \
           self.type == 83 or \
           self.type == 85:
            self.support_temp=True
            return True
        self.support_temp=False
        return False
    def set_color_temp(self, temperature):
        self.network.send_packet(self.id, 0xe2, [0x05, int(self.ratio*(temperature-self.max_mireds))])
        self._temperature = temperature
    def set_brightness(self, brightness):
        self.network.send_packet(self.id, 0xd2, [(100*brightness//255)])
        self._brightness = brightness
    def set_hs(self, hs_color):
        self._color = hs_color
        hue, saturation = hs_color
        red, green, blue = colorutil.color_hsv_to_RGB(hue, saturation, self._brightness*100/255)
        self.network.send_packet(self.id, 0xe2, [0x04, red, green, blue])
        self.red = red
        self.green = green
        self.blue = blue

    def set_power(self, power):
        self.network.send_packet(self.id, 0xd0, [int(power)])
        self.power=power

    def update(self):
        self.network.send_packet(self.id, 0xda, [])
    async def async_update(self):
      if self.id==0:
        await self.hass.async_add_executor_job(self.update)
    @property
    def assumed_state(self):
        return True
class laurel_mesh:
    def __init__(self, address, password):
        self.address = str(address)
        self.password = str(password)
        self.devices = {}
        self.link = None
        self.lock=threading.Lock()
    def __del__(self):
        if self.link:
            if self.link.device:
                 self.link.device.disconnect()

    def connect(self):
        if self.link != None:
            return

        for device in self.devices.values():
            # Try each device in turn - we only need to connect to one to be
            # on the mesh
            try:
                self.link = dimond.dimond(0x0211, device.mac, self.address, self.password)#,self,callback)
                self.link.connect()
                break
            except Exception as e:
                _LOGGER.debug("Failed to connect to %s", device.mac)
                self.link = None
                pass
        if self.link is None:
            raise Exception("Unable to connect to mesh %s" % self.address)

    def send_packet(self, id, command, params):
        # the lock mechanism is to prevent the simutaneous packets if
        # you control two devices at the same time though a group.
        self.lock.acquire()
        try:
          self.link.send_packet(id, command, params)
        except:
          self.link=None
          try:
            self.connect()
            self.link.send_packet(id, command, params)
          except:
            pass
        sleep(0.05)
        self.lock.release()

    def update_status(self):
        self.send_packet(0xffff, 0xda, [])

