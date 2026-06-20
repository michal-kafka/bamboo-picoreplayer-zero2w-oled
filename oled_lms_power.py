#!/usr/bin/env python3
import fcntl
import os
import socket
import time
import unicodedata
import urllib.parse
from datetime import datetime

LMS_HOST = os.environ.get("LMS_HOST", "<LMS_HOST>")
LMS_PORT = int(os.environ.get("LMS_PORT", "9090"))
PLAYER_ID = os.environ.get("PLAYER_ID", "<PLAYER_ID>")
PLAYER_NAME = os.environ.get("PLAYER_NAME", "<PLAYER_NAME>")

I2C_SLAVE = 0x0703
ADDR = 0x3C
DEV = "/dev/i2c-1"

# piCorePlayer/TinyCore sysfs GPIO base may vary. On this build it is 512:
# GPIO23 -> 535, GPIO24 -> 536.
BUTTON_OLED_GPIO = os.environ.get("BUTTON_OLED_GPIO", "535")
BUTTON_POWER_GPIO = os.environ.get("BUTTON_POWER_GPIO", "536")

FONT = {
    " ": [0, 0, 0, 0, 0], ":": [0, 0x36, 0x36, 0, 0], "-": [0x08, 0x08, 0x08, 0x08, 0x08],
    ".": [0, 0x60, 0x60, 0, 0], "/": [0x20, 0x10, 0x08, 0x04, 0x02],
    "(": [0, 0x1c, 0x22, 0x41, 0], ")": [0, 0x41, 0x22, 0x1c, 0],
    "0": [0x3e, 0x51, 0x49, 0x45, 0x3e], "1": [0, 0x42, 0x7f, 0x40, 0],
    "2": [0x42, 0x61, 0x51, 0x49, 0x46], "3": [0x21, 0x41, 0x45, 0x4b, 0x31],
    "4": [0x18, 0x14, 0x12, 0x7f, 0x10], "5": [0x27, 0x45, 0x45, 0x45, 0x39],
    "6": [0x3c, 0x4a, 0x49, 0x49, 0x30], "7": [0x01, 0x71, 0x09, 0x05, 0x03],
    "8": [0x36, 0x49, 0x49, 0x49, 0x36], "9": [0x06, 0x49, 0x49, 0x29, 0x1e],
    "A": [0x7e, 0x11, 0x11, 0x11, 0x7e], "B": [0x7f, 0x49, 0x49, 0x49, 0x36],
    "C": [0x3e, 0x41, 0x41, 0x41, 0x22], "D": [0x7f, 0x41, 0x41, 0x22, 0x1c],
    "E": [0x7f, 0x49, 0x49, 0x49, 0x41], "F": [0x7f, 0x09, 0x09, 0x09, 0x01],
    "G": [0x3e, 0x41, 0x49, 0x49, 0x7a], "H": [0x7f, 0x08, 0x08, 0x08, 0x7f],
    "I": [0, 0x41, 0x7f, 0x41, 0], "J": [0x20, 0x40, 0x41, 0x3f, 0x01],
    "K": [0x7f, 0x08, 0x14, 0x22, 0x41], "L": [0x7f, 0x40, 0x40, 0x40, 0x40],
    "M": [0x7f, 0x02, 0x0c, 0x02, 0x7f], "N": [0x7f, 0x04, 0x08, 0x10, 0x7f],
    "O": [0x3e, 0x41, 0x41, 0x41, 0x3e], "P": [0x7f, 0x09, 0x09, 0x09, 0x06],
    "Q": [0x3e, 0x41, 0x51, 0x21, 0x5e], "R": [0x7f, 0x09, 0x19, 0x29, 0x46],
    "S": [0x46, 0x49, 0x49, 0x49, 0x31], "T": [0x01, 0x01, 0x7f, 0x01, 0x01],
    "U": [0x3f, 0x40, 0x40, 0x40, 0x3f], "V": [0x1f, 0x20, 0x40, 0x20, 0x1f],
    "W": [0x7f, 0x20, 0x18, 0x20, 0x7f], "X": [0x63, 0x14, 0x08, 0x14, 0x63],
    "Y": [0x07, 0x08, 0x70, 0x08, 0x07], "Z": [0x61, 0x51, 0x49, 0x45, 0x43],
}


def clean(s):
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).upper()


def is_bad(s):
    s = (s or "").strip()
    return s == "" or s.upper() in ["UNKNOWN", "NULL", "NONE", "PLAYING"]


def split_lines(s, width=21, max_lines=2):
    s = clean(s).strip()
    lines = []

    while s and len(lines) < max_lines:
        if len(s) <= width:
            lines.append(s)
            break

        cut = s.rfind(" ", 0, width + 1)
        if cut <= 0:
            cut = width

        lines.append(s[:cut].strip())
        s = s[cut:].strip()

    while len(lines) < max_lines:
        lines.append("")

    return lines


def setup_button(gpio):
    gpio_path = "/sys/class/gpio/gpio" + gpio

    if not os.path.exists(gpio_path):
        try:
            with open("/sys/class/gpio/export", "w") as f:
                f.write(gpio)
            time.sleep(0.2)
        except Exception:
            pass

    try:
        with open(gpio_path + "/direction", "w") as f:
            f.write("in")
    except Exception:
        pass


def button_pressed(gpio):
    try:
        with open("/sys/class/gpio/gpio" + gpio + "/value") as f:
            return f.read().strip() == "0"
    except Exception:
        return False


def oled_write(control, data):
    with open(DEV, "wb", buffering=0) as f:
        fcntl.ioctl(f, I2C_SLAVE, ADDR)
        f.write(bytes([control]) + bytes(data))


def cmd(*d):
    oled_write(0x00, d)


def dat(d):
    oled_write(0x40, d)


def init():
    for c in [
        (0xAE,), (0xD5, 0x80), (0xA8, 0x3F), (0xD3, 0x00), (0x40,),
        (0x8D, 0x14), (0x20, 0x00), (0xA1,), (0xC8,), (0xDA, 0x12),
        (0x81, 0xCF), (0xD9, 0xF1), (0xDB, 0x40), (0xA4,), (0xA6,), (0xAF,)
    ]:
        cmd(*c)


def display_off():
    cmd(0xAE)


def clear():
    cmd(0x21, 0, 127)
    cmd(0x22, 0, 7)
    dat([0] * 1024)


def text(line, page):
    line = clean(line)[:21]

    cmd(0x21, 0, 127)
    cmd(0x22, page, 7)

    out = []
    for ch in line:
        out += FONT.get(ch, FONT[" "]) + [0]

    out += [0] * (128 - len(out))
    dat(out[:128])


def render_screen(row1, row2, row3):
    artist_station = split_lines(row2, 21, 2)
    title_info = split_lines(row3, 21, 2)

    text(row1, 0)
    text(artist_station[0], 2)
    text(artist_station[1], 3)
    text(title_info[0], 5)
    text(title_info[1], 6)


def lms(cmdline):
    with socket.create_connection((LMS_HOST, LMS_PORT), timeout=3) as s:
        s.sendall((cmdline + "\n").encode())
        return s.recv(8192).decode(errors="ignore").strip()


def lms_player(cmdline):
    pid = urllib.parse.quote(PLAYER_ID, safe="")
    return lms(pid + " " + cmdline)


def parse_lms(resp):
    out = {}
    for token in resp.split():
        if "%3A" in token:
            k, v = token.split("%3A", 1)
            out[urllib.parse.unquote(k)] = urllib.parse.unquote(v)
    return out


def get_status():
    return parse_lms(lms_player("status - 1 tags:altK"))


def handle_power_button(info):
    power = info.get("power", "1")
    mode = info.get("mode", "")

    if power == "0":
        lms_player("power 1")
        time.sleep(0.5)
        lms_player("play")
        return

    if mode != "play":
        lms_player("play")
        return

    lms_player("power 0")


def display_lines(info, last_row2, last_row3):
    mode = info.get("mode", "")
    power = info.get("power", "1")
    volume = info.get("mixer volume", info.get("volume", "--"))
    row1 = datetime.now().strftime("%Y-%m-%d %H:%M") + " V" + str(volume)

    if power == "0":
        return row1, "PLAYER OFF", "PRESS TO PLAY"

    if mode != "play":
        return row1, "NOT PLAYING", PLAYER_NAME

    artist = info.get("artist", "")
    title = info.get("title", "")
    album = info.get("album", "")
    remote_title = info.get("remote_title", "") or info.get("current_title", "")
    playlist = info.get("playlist name", "")

    if not is_bad(artist) and not is_bad(title):
        return row1, artist, title

    station = title or playlist or last_row2 or "RADIO"
    stream = remote_title or last_row3 or album or ""

    if is_bad(station):
        station = last_row2 or "RADIO"

    if is_bad(stream):
        stream = last_row3 or station

    if stream == station and last_row3 and last_row3 != station:
        stream = last_row3

    return row1, station, stream


def main():
    setup_button(BUTTON_OLED_GPIO)
    setup_button(BUTTON_POWER_GPIO)

    init()
    clear()

    last_row2 = ""
    last_row3 = ""
    last_track_id = ""
    screen_on = True
    last_oled_button_state = False
    last_power_button_state = False
    last_update = 0

    while True:
        oled_pressed = button_pressed(BUTTON_OLED_GPIO)
        power_pressed = button_pressed(BUTTON_POWER_GPIO)

        if oled_pressed and not last_oled_button_state:
            screen_on = not screen_on

            if screen_on:
                init()
                clear()
                last_row2 = ""
                last_row3 = ""
                last_track_id = ""
                last_update = 0
            else:
                display_off()

            time.sleep(0.3)

        if power_pressed and not last_power_button_state:
            try:
                info = get_status()
                handle_power_button(info)
                last_row2 = ""
                last_row3 = ""
                last_track_id = ""
                last_update = 0
            except Exception:
                pass

            time.sleep(0.3)

        last_oled_button_state = oled_pressed
        last_power_button_state = power_pressed

        if screen_on and time.time() - last_update >= 3:
            try:
                info = get_status()
                track_id = info.get("id", "") + ":" + info.get("title", "")

                if track_id != last_track_id:
                    last_row2 = ""
                    last_row3 = ""
                    last_track_id = track_id

                row1, row2, row3 = display_lines(info, last_row2, last_row3)

                if not is_bad(row2):
                    last_row2 = row2
                if not is_bad(row3):
                    last_row3 = row3

                render_screen(row1, row2, row3)
            except Exception:
                render_screen(
                    datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "LMS ERROR",
                    "RETRYING"
                )

            last_update = time.time()

        time.sleep(0.05)


if __name__ == "__main__":
    main()
