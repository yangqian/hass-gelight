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
import getpass
import json
import random
API_TIMEOUT = 20
# https://github.com/unixpickle/cbyge/blob/main/login.go
# https://github.com/juanboro/cync2mqtt/blob/main/src/acync/__init__.py

def randomLoginResource():
    return ''.join([chr(ord('a')+random.randint(0,26)) for i in range(0,16)])

def authenticate():
    """Authenticate with the API and get a token."""
    global debug_output
    API_AUTH = "https://api.gelighting.com/v2/two_factor/email/verifycode"
    auth_data = {
        'corp_id':    "1007d2ad150c4000",
        'email':      username,
        "local_lang": "en-us"
    }
    r = requests.post(API_AUTH, json=auth_data, timeout=API_TIMEOUT)
    
    code = input("Enter emailed code: ")
    
    API_AUTH = "https://api.gelighting.com/v2/user_auth/two_factor"
    auth_data = {
        'corp_id':    "1007d2ad150c4000",
        'email':      username,
        'password':   password,
        "two_factor": code,
        "resource":   randomLoginResource()
    }
    r = requests.post(API_AUTH, json=auth_data, timeout=API_TIMEOUT)
    debug_output += "\"authenticate()\":" + r.text + ","
    try:
        return (
            r.json()['access_token'],
            r.json()['refresh_token'],
            r.json()['user_id']
        )
    except KeyError:
        raise(LaurelException('API authentication failed'))

def get_access_token (refresh_token):
    """Get new access_token for subsequent request"""
    global debug_output
    API_AUTH = "https://api.gelighting.com/v2/user/token/refresh"
    auth_data = {"refresh_token": refresh_token}
    r = requests.post(API_AUTH, json=auth_data, timeout=API_TIMEOUT)
    debug_output += "\"get_access_token()\":" + r.text + ","
    return r.json()['access_token']

def get_devices(auth_token, user):
    """Get a list of devices for a particular user."""
    global debug_output
    API_DEVICES = "https://api2.xlink.cn/v2/user/{user}/subscribe/devices"
    headers = {'Access-Token': auth_token}
    r = requests.get(API_DEVICES.format(user=user), headers=headers,
                     timeout=API_TIMEOUT)
    debug_output += "\"get_devices()\":" + r.text
    return r.json()

def get_properties(auth_token, product_id, device_id):
    """Get properties for a single device."""
    global debug_output
    API_DEVICE_INFO = "https://api2.xlink.cn/v2/product/{product_id}/device/{device_id}/property"
    headers = {'Access-Token': auth_token}
    r = requests.get(
        API_DEVICE_INFO.format(product_id=product_id, device_id=device_id),
        headers=headers,
        timeout=API_TIMEOUT
    )
    debug_output +=  "," + "\"get_properties()\":" + r.text
    return r.json()

errormsg = ""
debug_output = "{"

# have a refresh token and user_id already?
refresh_token = getpass.getpass("Refresh token (if available): ")
user_id       = getpass.getpass("`user_id` (if available): ")
is_debug      = getpass.getpass("Enable debug output? (y/N): ").lower() == "y"

# otherwise, get authenticate
if not (refresh_token and user_id):
    username = input("Cync Username/Email: ")
    password = getpass.getpass()
    access_token, refresh_token, user_id = authenticate()

print("light:")
devices = get_devices(get_access_token(refresh_token), user_id)
for device in devices:
    product_id = device['product_id']
    device_id  = device['id']
    username   = device['mac']
    access_key = device['access_key']
    print("  - platform: gelight")
    print("    password: {}".format(access_key))
    print("    username: {}".format(username))
    print("    lights:")
    device_info = get_properties(get_access_token(refresh_token), product_id, device_id)
    try:
        for bulb in device_info['bulbsArray']:
            id          = int(bulb['deviceID']) % 1000
            mac         = [bulb['mac'][i:i+2] for i in range(0, 12, 2)]
            mac         = "%s:%s:%s:%s:%s:%s" % (mac[0], mac[1], mac[2], mac[3], mac[4], mac[5])
            name        = bulb['displayName']
            device_type = bulb['deviceType']
            print("      - id: {}".format(id))
            print("        mac: {}".format(mac.lower()))
            print("        name: {}".format(name))
            print("        type: {}".format(device_type))
    except KeyError:
        errormsg+="Warning: Missing bulb info.\n"

print(errormsg)

if (is_debug):
    import json
    debug_json = debug_output + "}"
    print("=================== debug output ===================")
    print(debug_json)
    print("========== debug output (pretty printed)  ==========")
    print(json.dumps(json.loads(debug_json), indent = 2))
