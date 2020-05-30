# coding=utf-8

import json
import kodiutils
import re
import subprocess
import xbmc

SW_HIDE = 0
STARTF_USESHOWWINDOW = 1

FFMPEG_PROGRESS_PATTERN = re.compile(
    r"frame=\s*(\d+)\s+fps=\s*([0-9\.]+)\s+q=([0-9\.-]+) [A-Z]?size=\s*([0-9]+[A-Za-z]+) time=([0-9:\.]+) bitrate=([^ ]+) speed=\s*([0-9\.]+)x")


class Progress:

    callback = None
    low = None
    high = None
    total = None

    def __init__(self, _callback, _low, _high, _total):
        self.callback = _callback
        self.low = _low
        self.high = _high
        self.total = float(_total)

    def update(self, current):

        level = int(self.low + current / self.total * (self.high - self.low))
        self.callback(level)


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

    def exec_ffmpeg(self, params, progress=None):

        call = [self._ffmpeg_executable, "-hide_banner", "-y"]
        call += params

        xbmc.log(" ".join(call), xbmc.LOGNOTICE)
        p = subprocess.Popen(call,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT,
                             universal_newlines=True,
                             startupinfo=self._si)

        prev_line = None
        for line in iter(p.stdout.readline, ""):
            if not line:
                break

            prev_line = line
            if progress != None:
                progress_secs = self._parse_time_to_secs(line)
                if progress_secs != None:
                    progress.update(progress_secs)

        return_code = p.poll()
        if (return_code != 0):
            xbmc.log(prev_line, xbmc.LOGERROR)
            return False

        return True

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
        if err != None and err != "":
            xbmc.log(err, xbmc.LOGERROR)
            raise OSError(err)

        return out.decode("utf-8")

    def inspect_media(self, filename):

        params = ["-print_format", "json",
                  "-show_format", "-show_streams", filename]
        out = self.exec_ffprobe(params)
        return json.loads(out)

    def _parse_time_to_secs(self, line):

        match = FFMPEG_PROGRESS_PATTERN.match(line)
        if not match:
            return None

        time_str = match.groups()[4]
        ms = sum([f * e for f, e in zip([3600, 60, 1],
                                        map(float, time_str.split(':')))])
        return ms
