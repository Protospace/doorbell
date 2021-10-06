import time
import secrets
import pygame

CHIME = 'chime.ogg'
FRONTDOOR = 'frontdoor.ogg'
BACKDOOR = 'backdoor.ogg'


def play_sound(filename):
    pygame.mixer.music.load(filename)
    pygame.mixer.music.play()

    while pygame.mixer.music.get_busy():
        pygame.time.Clock().tick(10)

def backdoor():
    play_sound(CHIME)
    play_sound(BACKDOOR)

    time.sleep(1)

    play_sound(CHIME)
    play_sound(BACKDOOR)

pygame.init()
pygame.mixer.init()

backdoor()
