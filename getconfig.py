#!/usr/bin/env python3
# Adoptd from https://github.com/google/python-laurel/blob/master/laurel/__init__.py
# Copyright 2018 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import requests
API_TIMEOUT = 10
def authenticate(username, password):
    """Authenticate with the API and get a token."""
    API_AUTH = "https://api2.xlink.cn/v2/user_auth"
    auth_data = {'corp_id': "1007d2ad150c4000", 'email': username,
                 'password': password}
    r = requests.post(API_AUTH, json=auth_data, timeout=API_TIMEOUT)
    try:
        return (r.json()['access_token'], r.json()['user_id'])
    except KeyError:
        raise(LaurelException('API authentication failed'))
def get_devices(auth_token, user):
    """Get a list of devices for a particular user."""
    API_DEVICES = "https://api2.xlink.cn/v2/user/{user}/subscribe/devices"
    headers = {'Access-Token': auth_token}
    r = requests.get(API_DEVICES.format(user=user), headers=headers,
                     timeout=API_TIMEOUT)
    return r.json()
def get_properties(auth_token, product_id, device_id):
    """Get properties for a single device."""
    API_DEVICE_INFO = "https://api2.xlink.cn/v2/product/{product_id}/device/{device_id}/property"
    headers = {'Access-Token': auth_token}
    r = requests.get(API_DEVICE_INFO.format(product_id=product_id, device_id=device_id), headers=headers, timeout=API_TIMEOUT)
    return r.json()

username = input("username:")
password = input("password:")
access_token, user_id = authenticate(username, password)
print("light:")
devices = get_devices(access_token, user_id)
errormsg = ""
for device in devices:
    product_id = device['product_id']
    device_id = device['id']
    username = device['mac']
    access_key = device['access_key']
    print("  - platform: gelight")
    print("    password: {}".format(access_key))
    print("    username: {}".format(username))
    print("    lights:")
    device_info = get_properties(access_token, product_id, device_id)
    try:
        for bulb in device_info['bulbsArray']:
            id = bulb['deviceID']%1000
            mac = [bulb['mac'][i:i+2] for i in range(0, 12, 2)]
            mac = "%s:%s:%s:%s:%s:%s" % (mac[5], mac[4], mac[3], mac[2], mac[1], mac[0])
            name = bulb['displayName']
            device_type = bulb['deviceType']
            print("      - id: {}".format(id))
            print("        mac: {}".format(mac))
            print("        name: {}".format(name))
            print("        type: {}".format(device_type))
    except KeyError:
        errormsg+="Warning: Missing bulb info.\n"
print(errormsg)
