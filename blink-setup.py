import os
import sys
import json
import base64
import logging
import asyncio
from time import sleep
from types import SimpleNamespace
from aiohttp import ClientSession
from blinkpy.auth import Auth
from blinkpy.blinkpy import Blink
from blinkpy.helpers.util import json_load
from colorama.ansi import clear_screen
from colorama import init as colorama_init, Fore, Style, Back

MENU_PRE = f'{Fore.YELLOW}{Back.BLUE}{Style.BRIGHT}'
MENU_POST = f'{Style.NORMAL}{Back.RESET}'
MENU_EOL = f'{Fore.RESET}'

CREDS = 'blink_credentials'

import sys

log = []


class err_writer(object):
    """Class for creating context to capture stderr output from library python code"""
    def write(self, data):
        self.log.append(data)
    def flush(self):
        pass 
    def __init__(self):
        self.log = []
    def __enter__(self):
        self.save_stderr = sys.stderr
        sys.stderr = self
        return self
    def __exit__(self, exception_type, exception_value, exception_traceback):
        #if the old stderr is restored, aiohttp logs some nonsense
        #sys.stderr = self.save_stderr
        pass


class AIOSessionBuilder():
    def __enter__(self):
        self.session = ClientSession()
        return self.session
    def __exit__(self, exception_type, exception_value, exception_traceback):
        self.session.close()


def obfuscate_str(plain_text: str) -> str:
    return base64.b32encode(plain_text.encode()).decode()

def deobfuscate_str(obfuscated: str) -> str:
    return base64.b32decode(obfuscated).decode()

def decode_credentials(settings: object) -> object:
    if CREDS not in settings:
        return None

    credentials = settings[CREDS]
    if isinstance(credentials, str):
        json_str = deobfuscate_str(credentials)
        return json.loads(json_str)
    else:
        return credentials

def encode_credentials(settings: object, credentials: object, obfuscate=True) -> object:
    if obfuscate:
        json_str = json.dumps(credentials)
        settings[CREDS] = obfuscate_str(json_str)
    else:
        settings[CREDS] = credentials
    return settings

def prompt(user_prompt: str, default_value: str=None, prefix: str=Fore.CYAN, postfix: str=Fore.RESET) -> str:
    default_prompt = '' if default_value is None else f' (default: "{default_value}") '
    return input(f'{prefix}{user_prompt}{default_prompt}{postfix}') or default_value

def cinput(prompt: str, prefix: str=Fore.CYAN, postfix: str=Fore.RESET) -> str:
    return input(f'{prefix}{prompt}{postfix}')

def ask_yes_no(question: str, prefix: str=Fore.CYAN, postfix: str=Fore.RESET) -> bool:
    """returns True if the user answered yes, False otherwise"""

    while True:
        answer = cinput(f'{Fore.CYAN}{question} (y/n):{Fore.RESET} ', prefix=prefix, postfix=postfix).lower()
        if answer in ["y", "yes"]:
            return True
        elif answer in ["n", "no"]:
            return False
        else:
            print(f'{Fore.RED}please enter yes or no{Fore.RESET}')


def setup_settings_location(default_location: str=None) -> object:
    if default_location is None:
        path = os.path.realpath(os.path.expanduser('~/prusa-connect-upload.config'))
    else:
        path = os.path.realpath(os.path.expanduser(default_location))

    print('')
    path = prompt('Enter filepath location for settings?', path)
    return path

def save_settings(settings: object, settings_location: str) -> None | str:
    """save settings to location, return None or error explanation"""
    try:
        with open(settings_location, 'w') as file:
            json.dump(settings, file, indent=True)
    except IOError as e:
        return f'Error saving settings: {e}'
    except Exception as e:
        print(e)
        return f'Unknown error saving settings to "{settings_location}"'
    return None

def exit_program(exit_code=0, message: str='Program terminated'):
    if message:
        print('')
        print(message)
    sys.exit(exit_code)

def add_camera(settings: object, camera_list: object) -> None:
    print(f'\n\n{Style.BRIGHT}Add camera for upload{Style.NORMAL}\n')
    for n, camera in enumerate(camera_list, 1):
        print(f'    {MENU_PRE} {n} {MENU_POST} - ' + 
            f'{Fore.GREEN}{camera[0]}{Fore.RESET} sn={camera[1]}{MENU_EOL}')

    resp = cinput('\nEnter camera number to upload, Q if finished adding: ')

    if resp == '0' or resp == 0 or resp == 'q' or resp == 'Q':
        resp = 0
    else:
        num = int(resp)
        if num>0 and num<=len(camera_list):
            camera = camera_list[num-1]
            token = cinput(f'Enter the token for the "{camera[0]}" camera: ')
            settings['upload_list'] = settings['upload_list'] if 'upload_list' in settings else []
            settings['upload_list'].append([camera[0], camera[1], token])
    return

def display_upload_list(upload_list: list, as_menu: bool=True) -> None:
    if upload_list is None or len(upload_list)==0:
        print(f'{Fore.RED}<NO CAMERAS CONFIGURED>{Fore.RESET}')
    elif as_menu:
        for n, entry in enumerate(upload_list, 1):
            print(f'    {MENU_PRE} {n} {MENU_POST} - "{Fore.GREEN}{entry[0]}{Fore.RESET}" with token {entry[2]}')
    else:
        for n, entry in enumerate(upload_list, 1):
            print(f'    {Style.BRIGHT}{n}{Style.NORMAL} - "{Fore.GREEN}{entry[0]}{Fore.RESET}" with token {entry[2]}')

def main_camera_menu(settings: object, camera_list: object) -> str:
    upload_list = settings['upload_list']
    empty_list = len(upload_list)==0
    while True:
        print(f'\n\n{Style.BRIGHT}List of cameras to be used for image upload{Style.NORMAL}\n')
        display_upload_list(upload_list, as_menu=False)

        MENUITEM = lambda key, description: f'    {MENU_PRE} {key.upper()} {MENU_POST} - {description}{MENU_EOL}'
        print(f'\n{Style.BRIGHT}Choose action:{Style.NORMAL}\n')
        print(MENUITEM('A', 'add camera'))
        if not empty_list:
            print(MENUITEM('R', 'remove camera'))
        print(MENUITEM('S', 'save and exit'))
        print(MENUITEM('X', 'exit without saving'))
        choice = prompt('\nChoice? ', 'S')
        choice = choice.upper() if hasattr(choice, 'upper') else choice

        if (choice == 'R' and not empty_list):
            print('\nCurrent camera upload list:\n')
            display_upload_list(upload_list, as_menu=True)
            remove_num = cinput('\nEnter number of camera to remove: ')
            num = int(remove_num)
            if num>0 and num<=len(upload_list):
                del upload_list[num-1]

        elif (choice == 'A' or 
          choice == 'S' or 
          choice == 'X'):
            break

    return choice

async def blink_camera_setup(err_log: object):
    colorama_init()
    clear_screen()

    settings_path = setup_settings_location(sys.argv[1] if len(sys.argv)>1 else None)

    with AIOSessionBuilder() as aiohttp_session:
        blink = Blink(session=aiohttp_session)
        settings = {}

        if (os.path.isfile(settings_path)):
            try:
                with open(settings_path, 'r') as file:
                    settings = json.load(file)
            except:
                settings = {}

            creds = decode_credentials(settings) if CREDS in settings else None
            username = creds['username'] if 'username' in creds else None
            if username is not None and creds is not None:
                resp = ask_yes_no(f'\nBlink app credentials exist for {username}, should they be used?')
                if resp:
                    auth = Auth(creds)
                    blink.auth = auth
                else:
                    print('\nEnter new Blink app credentials:\n')
            else:
                print('\nEnter Blink app credentials:\n')
        else:
            print('\nEnter Blink app credentials:\n')

        await blink.start()

        camera_list = list()

        if blink is not None and blink.cameras is not None and len(blink.cameras)>0:
            print('')
            for n, item in enumerate(blink.cameras.items(), 1):
                camera = SimpleNamespace(**item[1].attributes)
                camera_list.append((camera.name, camera.serial))
                print(f'    {n} - {Style.BRIGHT}{camera.name}{Style.NORMAL} sn={camera.serial}')

            go_on = ask_yes_no('\nDoes this list of cameras look correct?')
            if not go_on:
                exit_program(1)

        else:
            exit_program(1)

        settings = encode_credentials(settings, blink.auth.login_attributes)
        settings['blink_username'] = blink.auth.login_attributes['username']
        err = save_settings(settings, settings_path)

        if err is not None:
            print(f'SAVE ERROR: {err}')
            yes_no_resp = ask_yes_no('\nContinue?')
            if not yes_no_resp:
                exit_program(1)

        print('')
        print('To configure camera images to upload you must go to Prusa Connect and')
        print('and add one or more "other cameras" and be ready to copy and paste the')
        print('\'token\' for each camera for this setup. Use the camera tab at')
        print('https://connect.prusa3d.com/ and look for "Add new other camera" near')
        print('the bottom, ignore the "web camera" section that has QR codes')

        choice = '' if 'upload_list' in settings and len(settings['upload_list'])>0 else 'A'

        while True:
            if choice=='A':
                add_camera(settings, camera_list)

            choice = main_camera_menu(settings, camera_list)

            if choice=='S' or choice=='X':
                break

        if choice=='X':
            exit_program(1)

        if choice=='S':
            save_rc = save_settings(settings, settings_path)
            if save_rc:
                print(f'\n{Fore.RED}{save_rc}{Fore.RESET}\n')
            else:
                print(f'\n{Fore.GREEN}Settings saved{Fore.RESET}\n')

    sleep(1)
    return

with err_writer() as err_log:
    asyncio.run(blink_camera_setup(err_log))
    sleep(1)
