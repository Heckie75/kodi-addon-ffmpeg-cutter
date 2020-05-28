# coding=utf-8

import json
import kodiutils
import subprocess
import xbmc

SW_HIDE = 0
STARTF_USESHOWWINDOW = 1

PROGRESS_REGEXP = r"frame= *(\d+) +fps= *([0-9\.]+) +q=([0-9\.-]+) [A-Z]*size= *([ 0-9]+[A-Za-z]+) time=([0-9:\.]+) bitrate=([^ ]+) speed= *([0-9\.]+)x"

class FFMpegUtils:

    X264_PRESETS = ["ultrafast", "superfast", "veryfast", "faster",
                    "fast", "medium", "slow", "slower", "veryslow", "placebo"]
    X264_TUNES = ["film", "animation", "grain", "stillimage",
                  "psnr", "ssim", "fastdecode", "zerolatency"]

    _ffmpeg_executable = None
    _ffprobe_executable = None

    _si = None

    def __init__(self, ffmpeg_executable="ffmpeg", ffprobe_executable="ffprobe"):

        _os = kodiutils.getOS()
        if (_os == kodiutils.OS_WINDOWS or _os == kodiutils.OS_XBOX):
            self._si = subprocess.STARTUPINFO()
            self._si.dwFlags = STARTF_USESHOWWINDOW
            self._si.wShowWindow = SW_HIDE

            if ffmpeg_executable == "ffmpeg":
                ffmpeg_executable = "%s.exe" % ffmpeg_executable
            if ffprobe_executable == "ffprobe":
                ffprobe_executable = "%s.exe" % ffprobe_executable

        self._ffmpeg_executable = ffmpeg_executable
        self._ffprobe_executable = ffprobe_executable

    def exec_ffmpeg(self, params):

        call = [self._ffmpeg_executable, "-hide_banner", "-y"]
        call += params

        xbmc.log(" ".join(call), xbmc.LOGNOTICE)
        p = subprocess.Popen(call,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE,
                             universal_newlines=True,
                             startupinfo=self._si)

        out, err = p.communicate()
        xbmc.log(out, xbmc.LOGNOTICE)
        xbmc.log(err, xbmc.LOGNOTICE)
        return out.decode("utf-8")

    def exec_ffprobe(self, params):

        call = [self._ffprobe_executable, "-v", "quiet"]
        call += params

        xbmc.log(" ".join(call), xbmc.LOGNOTICE)
        p = subprocess.Popen(call,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE,
                             universal_newlines=True,
                             startupinfo=self._si)

        out, err = p.communicate()
        xbmc.log(out, xbmc.LOGNOTICE)
        xbmc.log(err, xbmc.LOGNOTICE)
        return out.decode("utf-8")

    def inspect_media(self, filename):

        params = ["-print_format", "json",
                  "-show_format", "-show_streams", filename]
        out = self.exec_ffprobe(params)
        return json.loads(out)