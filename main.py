import os
import vdf
import winreg
import argparse
import aiohttp
import aiofiles
import traceback
import subprocess
import colorlog
import logging
import json
import time
import sys
import psutil
import asyncio
from pathlib import Path

# Initialize logger
# Sets up a logger with colored output for different log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
def init_log():
    logger = logging.getLogger('Onekey')
    logger.setLevel(logging.DEBUG)
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.DEBUG)
    fmt_string = '%(log_color)s[%(name)s][%(levelname)s]%(message)s'
    log_colors = {
        'DEBUG': 'cyan',
        'INFO': 'green',
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'purple'
    }
    fmt = colorlog.ColoredFormatter(fmt_string, log_colors=log_colors)
    stream_handler.setFormatter(fmt)
    logger.addHandler(stream_handler)
    return logger


# Generate configuration file
# Creates a default configuration file if it does not already exist, prompting the user to fill it in
def gen_config_file():
    default_config = {"Github_Personal_Token": "", "Custom_Steam_Path": ""}
    with open('./config.json', 'w', encoding='utf-8') as f:
        json.dump(default_config, f)
    log.info('The program may be starting for the first time, please fill in the configuration file and restart the program')


# Load configuration file
# Loads the configuration file; if it does not exist, it generates a new one and exits the program
def load_config():
    if not os.path.exists('./config.json'):
        gen_config_file()
        os.system('pause')
        sys.exit()
    else:
        with open('./config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
            return config


log = init_log()
config = load_config()
lock = asyncio.Lock()


print('\033[1;32;40m  _____   __   _   _____   _   _    _____  __    __ \033[0m')
print('\033[1;32;40m /  _  \ |  \ | | | ____| | | / /  | ____| \ \  / /\033[0m')
print('\033[1;32;40m | | | | |   \| | | |__   | |/ /   | |__    \ \/ /\033[0m')
print('\033[1;32;40m | | | | | |\   | |  __|  | |\ \   |  __|    \  /')
print('\033[1;32;40m | |_| | | | \  | | |___  | | \ \  | |___    / /\033[0m')
print('\033[1;32;40m \_____/ |_|  \_| |_____| |_|  \_\ |_____|  /_/\033[0m')
log.info('Author: ikun0014')
log.info('This project is based on wxy1343/ManifestAutoUpdate, licensed under GPL V3')
log.info('Version: 1.0.4')
log.info('Project repository: https://github.com/ikunshare/Onekey')
log.debug('Official website: ikunshare.com')
log.warning('Note: It is rumored that the new version of Steam has detection for some unlocking tools, but no issues have been found yet. If you get banned, please report it via issue.')
log.warning('This project is completely free. If you obtained it through purchase on Taobao or QQ groups, go back and scold the商家死全家 (merchant to death)\nDiscussion group:\nClick the link to join the group【ikun分享】 (ikun share): https://qm.qq.com/q/D9Uiva3RVS\nhttps://t.me/ikunshare_group')


# Get Steam installation path via registry
# Retrieves the Steam installation path from the Windows registry, or uses a custom path if specified in the config
def get_steam_path():
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam')
    steam_path = Path(winreg.QueryValueEx(key, 'SteamPath')[0])
    custom_steam_path = config.get("Custom_Steam_Path", "")
    if not custom_steam_path == '':
        return Path(custom_steam_path)
    else:
        return steam_path


steam_path = get_steam_path()
isGreenLuma = any((steam_path / dll).exists() for dll in ['GreenLuma_2024_x86.dll', 'GreenLuma_2024_x64.dll', 'User32.dll'])
isSteamTools = (steam_path / 'config' / 'stplug-in').is_dir()


# Error stack handling
# Formats and returns the stack trace for a given exception
def stack_error(exception):
    stack_trace = traceback.format_exception(type(exception), exception, exception.__traceback__)
    return ''.join(stack_trace)


# Download manifest
# Attempts to download a manifest file from multiple URLs with retries
async def get(sha, path):
    url_list = [
        f'https://gcore.jsdelivr.net/gh/{repo}@{sha}/{path}',
        f'https://fastly.jsdelivr.net/gh/{repo}@{sha}/{path}',
        f'https://cdn.jsdelivr.net/gh/{repo}@{sha}/{path}',
        f'https://github.moeyy.xyz/https://raw.githubusercontent.com/{repo}/{sha}/{path}',
        f'https://mirror.ghproxy.com/https://raw.githubusercontent.com/{repo}/{sha}/{path}',
        f'https://ghproxy.org/https://raw.githubusercontent.com/{repo}/{sha}/{path}',
        f'https://raw.githubusercontent.com/{repo}/{sha}/{path}'
    ]
    retry = 3
    async with aiohttp.ClientSession() as session:
        while retry:
            for url in url_list:
                try:
                    async with session.get(url, ssl=False) as r:
                        if r.status == 200:
                            return await r.read()
                        else:
                            log.error(f'Failed to fetch: {path} - Status code: {r.status}')
                except aiohttp.ClientError:
                    log.error(f'Failed to fetch: {path} - Connection error')
            retry -= 1
            log.warning(f'Retries remaining: {retry} - {path}')
    log.error(f'Exceeded maximum retries: {path}')
    raise Exception(f'Failed to download: {path}')


# Get manifest information
# Downloads and processes manifest files, handling both .manifest and Key.vdf files
async def get_manifest(sha, path, steam_path: Path):
    collected_depots = []
    try:
        if path.endswith('.manifest'):
            depot_cache_path = steam_path / 'depotcache'
            async with lock:
                if not depot_cache_path.exists():
                    depot_cache_path.mkdir(exist_ok=True)
            save_path = depot_cache_path / path
            if save_path.exists():
                async with lock:
                    log.warning(f'Manifest already exists: {path}')
                return collected_depots
            content = await get(sha, path)
            async with lock:
                log.info(f'Manifest downloaded successfully: {path}')
            async with aiofiles.open(save_path, 'wb') as f:
                await f.write(content)
        elif path == 'Key.vdf':
            content = await get(sha, path)
            async with lock:
                log.info(f'Key downloaded successfully: {path}')
            depots_config = vdf.loads(content.decode(encoding='utf-8'))
            for depot_id, depot_info in depots_config['depots'].items():
                collected_depots.append((depot_id, depot_info['DecryptionKey']))
    except KeyboardInterrupt:
        raise
    except Exception as e:
        log.error(f'Failed to process: {path} - {stack_error(e)}')
        traceback.print_exc()
        raise
    return collected_depots


# Merge DecryptionKey
# Merges decryption keys into the Steam configuration file
async def depotkey_merge(config_path, depots_config):
    if not config_path.exists():
        async with lock:
            log.error('Steam default configuration does not exist, possibly due to not logging in')
        return
    with open(config_path, encoding='utf-8') as f:
        config = vdf.load(f)
    software = config['InstallConfigStore']['Software']
    valve = software.get('Valve') or software.get('valve')
    steam = valve.get('Steam') or valve.get('steam')
    if 'depots' not in steam:
        steam['depots'] = {}
    steam['depots'].update(depots_config['depots'])
    with open(config_path, 'w', encoding='utf-8') as f:
        vdf.dump(config, f, pretty=True)
    return True


# Add SteamTools unlock related files
# Generates and processes unlock files for SteamTools
async def stool_add(depot_data, app_id):
    lua_filename = f"Onekey_unlock_{app_id}.lua"
    lua_filepath = steam_path / "config" / "stplug-in" / lua_filename

    async with lock:
        log.info(f'SteamTools unlock file generated: {lua_filepath}')
        with open(lua_filepath, "w", encoding="utf-8") as lua_file:
            lua_file.write(f'addappid({app_id}, 1, "None")\n')
            for depot_id, depot_key in depot_data:
                lua_file.write(f'addappid({depot_id}, 1, "{depot_key}")\n')

    luapacka_path = steam_path / "config" / "stplug-in" / "luapacka.exe"
    subprocess.run([str(luapacka_path), str(lua_filepath)])
    os.remove(lua_filepath)
    return True


# Add GreenLuma unlock related files
# Generates and processes unlock files for GreenLuma
async def greenluma_add(depot_id_list):
    app_list_path = steam_path / 'appcache' / 'appinfo.vdf'
    if app_list_path.exists() and app_list_path.is_file():
        app_list_path.unlink(missing_ok=True)
    if not app_list_path.is_dir():
        app_list_path.mkdir(parents=True, exist_ok=True)
    depot_dict = {}
    for i in app_list_path.iterdir():
        if i.stem.isdecimal() and i.suffix == '.txt':
            with i.open('r', encoding='utf-8') as f:
                app_id_ = f.read().strip()
                depot_dict[int(i.stem)] = None
                if app_id_.isdecimal():
                    depot_dict[int(i.stem)] = int(app_id_)
    for depot_id in depot_id_list:
        if int(depot_id) not in depot_dict.values():
            index = max(depot_dict.keys()) + 1 if depot_dict.keys() else 0
            if index != 0:
                for i in range(max(depot_dict.keys())):
                    if i not in depot_dict.keys():
                        index = i
                        break
            with (app_list_path / f'{index}.txt').open('w', encoding='utf-8') as f:
                f.write(str(depot_id))
            depot_dict[index] = int(depot_id)
    return True


# Check Github Api request limit
# Checks and logs the current rate limit status of the GitHub API
async def check_github_api_limit(headers):
    url = 'https://api.github.com/rate_limit'
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, ssl=False) as r:
            r_json = await r.json()
            remain_limit = r_json['rate']['remaining']
            use_limit = r_json['rate']['used']
            reset_time = r_json['rate']['reset']
            f_reset_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(reset_time))
            log.info(f'Used Github requests: {use_limit}')
            log.info(f'Remaining Github requests: {remain_limit}')
            if r.status == 429:
                log.info(f'Your Github Api requests have exceeded the limit, try adding a Personal Token')
                log.info(f'Requests reset time: {f_reset_time}')
    return True


# Check if process is running
# Checks if a specific process is currently running on the system
def check_process_running(process_name):
    for process in psutil.process_iter(['name']):
        if process.info['name'] == process_name:
            return True
    return False


# Main function
# Orchestrates the main workflow of the program, including fetching and processing manifests, and handling unlock files
async def main(app_id):
    app_id_list = list(filter(str.isdecimal, app_id.strip().split('-')))
    app_id = app_id_list[0]
    github_token = config.get("Github_Personal_Token", "")
    headers = {'Authorization': f'Bearer {github_token}'} if github_token else None

    await check_github_api_limit(headers)

    url = f'https://api.github.com/repos/{repo}/branches/{app_id}'
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, ssl=False) as r:
            r_json = await r.json()
            if 'commit' in r_json:
                sha = r_json['commit']['sha']
                url = r_json['commit']['commit']['tree']['url']
                date = r_json['commit']['commit']['author']['date']
                async with session.get(url, headers=headers, ssl=False) as r2:
                    r2_json = await r2.json()
                    if 'tree' in r2_json:
                        collected_depots = []
                        for i in r2_json['tree']:
                            result = await get_manifest(sha, i['path'], steam_path)
                            collected_depots.extend(result)
                        if collected_depots:
                            if isSteamTools:
                                await stool_add(collected_depots, app_id)
                                log.info('Found SteamTools, added unlock files')
                            if isGreenLuma:
                                await greenluma_add([app_id])
                                depot_config = {'depots': {depot_id: {'DecryptionKey': depot_key} for depot_id, depot_key in collected_depots}}
                                depotkey_merge(steam_path / 'config' / 'config.vdf', depot_config)
                                if await greenluma_add([int(i) for i in depot_config['depots'] if i.isdecimal()]):
                                    log.info('Found GreenLuma, added unlock files')
                            log.info(f'Manifest last updated: {date}')
                            log.info(f'Successfully added: {app_id}')
                            return True
    log.error(f'Failed to download or generate .st for: {app_id}')
    return False


parser = argparse.ArgumentParser()
parser.add_argument('-a', '--app-id')
args = parser.parse_args()
repo = 'ManifestHub/ManifestHub'
if __name__ == '__main__':
    try:
        log.debug('App ID can be found on SteamDB or the Steam store page')
        asyncio.run(main(args.app_id or input('App ID to add: ')))
    except KeyboardInterrupt:
        exit()
    except Exception as e:
        log.error(f'An error occurred: {stack_error(e)}')
        traceback.print_exc()
    if not args.app_id:
        os.system('pause')
