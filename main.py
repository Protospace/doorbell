import os, sys
import logging
logging.basicConfig(stream=sys.stdout,
    format='[%(asctime)s] %(levelname)s %(module)s/%(funcName)s - %(message)s',
    level=logging.DEBUG if os.environ.get('DEBUG') else logging.INFO)

import time
import json

import pygame

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

if __name__ == '__main__':
    logging.info('')
    logging.info('==========================')
    logging.info('Booting up...')
    pygame.init()
    pygame.mixer.pre_init(buffer=4096)
    pygame.mixer.init(buffer=4096)

    backdoor()

