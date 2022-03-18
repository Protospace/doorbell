import os, sys
import logging
logging.basicConfig(stream=sys.stdout,
    format='[%(asctime)s] %(levelname)s %(module)s/%(funcName)s - %(message)s',
    level=logging.DEBUG if os.environ.get('DEBUG') else logging.INFO)

os.environ['SDL_AUDIODRIVER'] = 'alsa'

import time
import json

import asyncio
from asyncio_mqtt import Client
import pygame

import secrets

COOLDOWN = time.time()

CHIME = 'chime.ogg'

DOORBELLS = {
    '647166': {
        'name': 'Front Door',
        'sound': 'frontdoor.ogg',
    },
    '549660': {
        'name': 'Back Door',
        'sound': 'backdoor.ogg',
    },
    '56504': {
        'name': 'Test Door',
        'sound': 'testing.ogg',
    },
}

async def play_sound(filename):
    pygame.mixer.music.load(filename)
    pygame.mixer.music.play()

    logging.info('Playing sound %s', filename)

    while pygame.mixer.music.get_busy():
        #pygame.time.Clock().tick(10)
        await asyncio.sleep(0.1)


async def ring_bell(sound):
    global COOLDOWN
    if time.time() - COOLDOWN < 5.0:
        logging.info('Cooldown skipping.')
        return
    COOLDOWN = time.time()

    await asyncio.sleep(0.1)

    if sound != 'testing.ogg':
        await play_sound(CHIME)
    await play_sound(sound)

    await asyncio.sleep(0.75)

    if sound != 'testing.ogg':
        await play_sound(CHIME)
    await play_sound(sound)

    logging.info('Done ringing.')

async def process_mqtt(message):
    text = message.payload.decode()
    topic = message.topic
    logging.info('MQTT topic: %s, message: %s', topic, text)

    if not topic.startswith('rtl_433'):
        logging.info('Invalid topic, returning')
        return

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logging.info('Invalid json, returning')
        return

    id_ = str(data.get('id', ''))

    if id_ not in DOORBELLS:
        logging.info('Invalid id, returning')
        return

    doorbell = DOORBELLS[id_]

    logging.info('Ringing %s...', doorbell['name'])

    await ring_bell(doorbell['sound'])


async def fetch_mqtt():
    await asyncio.sleep(3)
    async with Client('localhost') as client:
        async with client.filtered_messages('#') as messages:
            await client.subscribe('#')
            async for message in messages:
                loop = asyncio.get_event_loop()
                loop.create_task(process_mqtt(message))


if __name__ == '__main__':
    logging.info('')
    logging.info('==========================')
    logging.info('Booting up...')

    pygame.mixer.pre_init(buffer=4096)
    pygame.mixer.init(buffer=4096)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(fetch_mqtt())
