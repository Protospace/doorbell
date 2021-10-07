import os
import logging
logging.basicConfig(
    format='[%(asctime)s] %(levelname)s %(module)s/%(funcName)s - %(message)s',
    level=logging.DEBUG if os.environ.get('DEBUG') else logging.INFO)

import time
import json

import pygame
from pyezviz import EzvizClient, MQTTClient

import secrets

CHIME = 'chime.ogg'
FRONTDOOR = 'frontdoor.ogg'
BACKDOOR = 'backdoor.ogg'

def play_sound(filename):
    pygame.mixer.music.load(filename)
    pygame.mixer.music.play()

    logging.info('Playing sound %s', filename)

    while pygame.mixer.music.get_busy():
        pygame.time.Clock().tick(10)

def backdoor():
    play_sound(CHIME)
    play_sound(BACKDOOR)

    time.sleep(0.75)

    play_sound(CHIME)
    play_sound(BACKDOOR)

def on_message(client, userdata, mqtt_message):
    message = json.loads(mqtt_message.payload)
    #print(json.dumps(mqtt_message, indent=4))

    if message['alert'] == 'somebody there ring the door':  # lmao
        logging.info('Received door bell press alert')
        if 'E80451501' in message['ext']:
            logging.info('Backdoor pressed')
            backdoor()

if __name__ == '__main__':
    logging.info('')
    logging.info('==========================')
    logging.info('Booting up...')
    pygame.init()
    pygame.mixer.init(buffer=1024)

    client = EzvizClient(secrets.EZVIZ_EMAIL, secrets.EZVIZ_PASS, 'apiius.ezvizlife.com')
    try:
        logging.info('Logging into EZVIZ client...')
        token = client.login()
        mqtt = MQTTClient(token, on_message)
        logging.info('Starting MQTT...')
        mqtt.start()
    except Exception as exp:
        logging.exception(str(exp))
    finally:
        client.close_session()
