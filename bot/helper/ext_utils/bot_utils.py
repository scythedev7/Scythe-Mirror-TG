from re import match as re_match, findall as re_findall
from threading import Thread, Event
from time import time
from math import ceil
from html import escape
from psutil import virtual_memory, cpu_percent, disk_usage
from requests import head as rhead
from urllib.request import urlopen
from telegram import InlineKeyboardMarkup

from bot.helper.telegram_helper.bot_commands import BotCommands
from bot import download_dict, download_dict_lock, STATUS_LIMIT, botStartTime, DOWNLOAD_DIR
from bot.helper.telegram_helper.button_build import ButtonMaker

MAGNET_REGEX = r"magnet:\?xt=urn:btih:[a-zA-Z0-9]*"

URL_REGEX = r"(?:(?:https?|ftp):\/\/)?[\w/\-?=%.]+\.[\w/\-?=%.]+"

COUNT = 0
PAGE_NO = 1


class MirrorStatus:
    STATUS_UPLOADING = "ââ³ â­ âððððððððð.....ê....ð¤ â«"
    STATUS_DOWNLOADING = "ââ³ ð âð³ðð ðððððððð.....ê....ð¥ â¬"
    STATUS_CLONING = "ð¤¶ Cloning..!. â»ï¸ "
    STATUS_WAITING = "ð¡ ððððððð...ð "
    STATUS_FAILED = "ð§ Failed ð«.. Cleaning..ð"
    STATUS_PAUSE = "ð¤·ââï¸ Paused...â¸ "
    STATUS_ARCHIVING = "ð Archiving...ð "
    STATUS_EXTRACTING = "ð Extracting...ð"
    STATUS_SPLITTING = "ð Splitting...âï¸"
    STATUS_CHECKING = "CÊá´á´á´ÉªÉ´É¢á´á´...ð"
    STATUS_SEEDING = "Sá´á´á´ÉªÉ´É¢...ð§"

SIZE_UNITS = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']


class setInterval:
    def __init__(self, interval, action):
        self.interval = interval
        self.action = action
        self.stopEvent = Event()
        thread = Thread(target=self.__setInterval)
        thread.start()

    def __setInterval(self):
        nextTime = time() + self.interval
        while not self.stopEvent.wait(nextTime - time()):
            nextTime += self.interval
            self.action()

    def cancel(self):
        self.stopEvent.set()

def get_readable_file_size(size_in_bytes) -> str:
    if size_in_bytes is None:
        return '0B'
    index = 0
    while size_in_bytes >= 1024:
        size_in_bytes /= 1024
        index += 1
    try:
        return f'{round(size_in_bytes, 2)}{SIZE_UNITS[index]}'
    except IndexError:
        return 'File too large'

def getDownloadByGid(gid):
    with download_dict_lock:
        for dl in list(download_dict.values()):
            status = dl.status()
            if (
                status
                not in [
                    MirrorStatus.STATUS_ARCHIVING,
                    MirrorStatus.STATUS_EXTRACTING,
                    MirrorStatus.STATUS_SPLITTING,
                ]
                and dl.gid() == gid
            ):
                return dl
    return None

def getAllDownload(req_status: str):
    with download_dict_lock:
        for dl in list(download_dict.values()):
            status = dl.status()
            if status not in [MirrorStatus.STATUS_ARCHIVING, MirrorStatus.STATUS_EXTRACTING, MirrorStatus.STATUS_SPLITTING] and dl:
                if req_status == 'down' and (status not in [MirrorStatus.STATUS_SEEDING,
                                                            MirrorStatus.STATUS_UPLOADING,
                                                            MirrorStatus.STATUS_CLONING]):
                    return dl
                elif req_status == 'up' and status == MirrorStatus.STATUS_UPLOADING:
                    return dl
                elif req_status == 'clone' and status == MirrorStatus.STATUS_CLONING:
                    return dl
                elif req_status == 'seed' and status == MirrorStatus.STATUS_SEEDING:
                    return dl
                elif req_status == 'all':
                    return dl
    return None

def get_progress_bar_string(status):
    completed = status.processed_bytes() / 8
    total = status.size_raw() / 8
    p = 0 if total == 0 else round(completed * 100 / total)
    p = min(max(p, 0), 100)
    cFull = p // 8
    p_str = 'â°' * cFull
    p_str += 'â±' * (12 - cFull)
    p_str = f"[{p_str}]"
    return p_str

def get_readable_message():
    with download_dict_lock:
        msg = ""
        if STATUS_LIMIT is not None:
            tasks = len(download_dict)
            global pages
            pages = ceil(tasks/STATUS_LIMIT)
            if PAGE_NO > pages and pages != 0:
                globals()['COUNT'] -= STATUS_LIMIT
                globals()['PAGE_NO'] -= 1
        for index, download in enumerate(list(download_dict.values())[COUNT:], start=1):
            msg += f"<b>ââ³ ð ðµð¸ð»ð´ð½ð°ð¼ð´ ð âª¡ã:</b> <code>{escape(str(download.name()))}</code>"
            msg += f"\n<b>ââ³ ð¥â ðð¿ð³ð°ðð´ ð¸ð½ðµð¾ ð§ âª¡ã:ââ¬:</b> <i>{download.status()}</i>"
            if download.status() not in [
                MirrorStatus.STATUS_ARCHIVING,
                MirrorStatus.STATUS_EXTRACTING,
                MirrorStatus.STATUS_SPLITTING,
                MirrorStatus.STATUS_SEEDING,
            ]:
                msg += f"\n{get_progress_bar_string(download)} {download.progress()}"
                if download.status() == MirrorStatus.STATUS_CLONING:
                    msg += f"\n<b>ð¦CÊá´É´á´á´ :</b> {get_readable_file_size(download.processed_bytes())} of {download.size()}"
                elif download.status() == MirrorStatus.STATUS_UPLOADING:
                    msg += f"\n<b>ââ³ ð° ðððððððð... ð=> :</b> {get_readable_file_size(download.processed_bytes())} of {download.size()}"
                else:
                    msg += f"\n<b>ââ³ ð° ð³ð¾ðð½ð»ð¾ð°ð³ ð |:</b> {get_readable_file_size(download.processed_bytes())} of {download.size()}"
                msg += f"\n<b>ââ³ ð¯ ðð¿ð´ð´ð³ â¡ âª¡ã:</b> {download.speed()} | <b>ETA:</b> {download.eta()}"
                
                msg += f"\n<b>ââ³ ð° ð´ððð¸ð¼ð°ðð´ð³ ðð¸ð¼ð´ â³ : </b> <code>{download.eta()}â</code>"
                msg += f"\n<b>ââ³ ð ð³ðð ððððððð | </b> <b>{download.message.from_user.first_name}</b>\n<b>ââ³ â ï¸ USER - ID âª¡ãð </b><code>/warn {download.message.from_user.id}</code>"

                try:
                    msg += f"\n<b>ââ³ð¡ ðð¾ððð´ð½ð ð¸ð½ðµð¾ âï¸ â\nââ³ ðð´ð´ð³ð´ðð ð¹: </b> <code>{download.aria_download().num_seeders}</code>" \
                           f" | <b> ð¿ð´ð´ðð ð¥ : </b> <code>{download.aria_download().connections}</code>\n<b>ââ³ ð ð¼ð¸ððð¾ð ð²ð»ð¸ð´ð½ð |</b> aria2c â·"           
                except:
                    pass
                try:
                    msg += f"\n<b>ââ³ ð¤ ðð´ð´ð³ð´ðð :</b> {download.torrent_info().num_seeds}" \
                           f" | <b>ð§² ð»ð´ð´ð²ð·ð´ðð:</b> {download.torrent_info().num_leechs}"
                except:
                    pass
                msg += f"\n<b>ââ³ ð¤·ââï¸ ðð¾ ð²ð°ð½ð²ð´ð» ð³ð¾ðð½ð»ð¾ð°ð³ ð¤¦ââï¸ |</b> \n<b>=> ðð¾ðºð´ð½ </b> <code>/{BotCommands.CancelMirror} {download.gid()}</code>"
                msg += f"\n<b> ââââââââââââââââââââââââââ </b>"
            elif download.status() == MirrorStatus.STATUS_SEEDING:
                msg += f"\n<b>ð¦ SÉªá´¢á´ : </b>{download.size()}"
                msg += f"\n<b>ââ³ ð¯ ðð¿ð´ð´ð³ â¡ âª¡ã: </b>{get_readable_file_size(download.torrent_info().upspeed)}/s"
                msg += f" | <b>ââ³ ð° ðððððððð... ð=> : </b>{get_readable_file_size(download.torrent_info().uploaded)}"
                msg += f"\n<b>Ratio: </b>{round(download.torrent_info().ratio, 3)}"
                msg += f" | <b>â²ï¸ Eá´á´ : </b>{get_readable_time(download.torrent_info().seeding_time)}"
                msg += f"\n<b>ââ³ ð¤·ââï¸ ðð¾ ð²ð°ð½ð²ð´ð» ð³ð¾ðð½ð»ð¾ð°ð³ ð¤¦ââï¸ |</b> \n<b>=> ðð¾ðºð´ð½ </b> <code>/{BotCommands.CancelMirror} {download.gid()}</code>"
                msg += f"\n<b> ââââââââââââââââââââââââââ </b>"
            else:
                msg += f"\n<b>ð¦ SÉªá´¢á´ : </b>{download.size()}"
            msg += "\n\n"
            if STATUS_LIMIT is not None and index == STATUS_LIMIT:
                break
        bmsg = f"<b>ð¥ï¸ Cá´á´ :</b> {cpu_percent()}% | <b>FÊá´á´:</b> {get_readable_file_size(disk_usage(DOWNLOAD_DIR).free)}"
        bmsg += f"\n<b>ð® Rá´á´ :</b> {virtual_memory().percent}% | <b>Uá´á´Éªá´á´:</b> {get_readable_time(time() - botStartTime)}"
        dlspeed_bytes = 0
        upspeed_bytes = 0
        for download in list(download_dict.values()):
            spd = download.speed()
            if download.status() == MirrorStatus.STATUS_DOWNLOADING:
                if 'K' in spd:
                    dlspeed_bytes += float(spd.split('K')[0]) * 1024
                elif 'M' in spd:
                    dlspeed_bytes += float(spd.split('M')[0]) * 1048576
            elif download.status() == MirrorStatus.STATUS_UPLOADING:
                if 'KB/s' in spd:
                    upspeed_bytes += float(spd.split('K')[0]) * 1024
                elif 'MB/s' in spd:
                    upspeed_bytes += float(spd.split('M')[0]) * 1048576
        bmsg += f"\n<b>DL:</b> {get_readable_file_size(dlspeed_bytes)}/s | <b>UL:</b> {get_readable_file_size(upspeed_bytes)}/s"
        if STATUS_LIMIT is not None and tasks > STATUS_LIMIT:
            msg += f"<b>Page:</b> {PAGE_NO}/{pages} | <b>Tasks:</b> {tasks}\n"
            buttons = ButtonMaker()
            buttons.sbutton("Previous", "status pre")
            buttons.sbutton("Next", "status nex")
            button = InlineKeyboardMarkup(buttons.build_menu(2))
            return msg + bmsg, button
        return msg + bmsg, ""

def turn(data):
    try:
        with download_dict_lock:
            global COUNT, PAGE_NO
            if data[1] == "nex":
                if PAGE_NO == pages:
                    COUNT = 0
                    PAGE_NO = 1
                else:
                    COUNT += STATUS_LIMIT
                    PAGE_NO += 1
            elif data[1] == "pre":
                if PAGE_NO == 1:
                    COUNT = STATUS_LIMIT * (pages - 1)
                    PAGE_NO = pages
                else:
                    COUNT -= STATUS_LIMIT
                    PAGE_NO -= 1
        return True
    except:
        return False

def get_readable_time(seconds: int) -> str:
    result = ''
    (days, remainder) = divmod(seconds, 86400)
    days = int(days)
    if days != 0:
        result += f'{days}d'
    (hours, remainder) = divmod(remainder, 3600)
    hours = int(hours)
    if hours != 0:
        result += f'{hours}h'
    (minutes, seconds) = divmod(remainder, 60)
    minutes = int(minutes)
    if minutes != 0:
        result += f'{minutes}m'
    seconds = int(seconds)
    result += f'{seconds}s'
    return result

def is_url(url: str):
    url = re_findall(URL_REGEX, url)
    return bool(url)

def is_gdrive_link(url: str):
    return "drive.google.com" in url

def is_gdtot_link(url: str):
    url = re_match(r'https?://.+\.gdtot\.\S+', url)
    return bool(url)

def is_mega_link(url: str):
    return "mega.nz" in url or "mega.co.nz" in url

def get_mega_link_type(url: str):
    if "folder" in url:
        return "folder"
    elif "file" in url:
        return "file"
    elif "/#F!" in url:
        return "folder"
    return "file"

def is_magnet(url: str):
    magnet = re_findall(MAGNET_REGEX, url)
    return bool(magnet)

def new_thread(fn):
    """To use as decorator to make a function call threaded.
    Needs import
    from threading import Thread"""

    def wrapper(*args, **kwargs):
        thread = Thread(target=fn, args=args, kwargs=kwargs)
        thread.start()
        return thread

    return wrapper

def get_content_type(link: str) -> str:
    try:
        res = rhead(link, allow_redirects=True, timeout=5, headers = {'user-agent': 'Wget/1.12'})
        content_type = res.headers.get('content-type')
    except:
        try:
            res = urlopen(link, timeout=5)
            info = res.info()
            content_type = info.get_content_type()
        except:
            content_type = None
    return content_type