import os, subprocess
import threading
import time


class Plugins:
    def __init__(self, *plugin):
        self.cwd = "tools"
        self.exe = os.path.join(self.cwd, *plugin)

    def run(self, *args):
        stdout = subprocess.run(
            [self.exe, *args],
            creationflags=subprocess.CREATE_NO_WINDOW,
            check=False,
            capture_output=True,
            text=True,
        ).stdout
        return stdout

    def _read_output(self, pipe):
        for line in iter(pipe.readline, ""):
            print(line, end="")

    def write(self, proc, command):
        threading.Thread(
            target=self._read_output, args=(proc.stdout,), daemon=True
        ).start()
        threading.Thread(
            target=self._read_output, args=(proc.stderr,), daemon=True
        ).start()

        proc.stdin.write(command)
        proc.stdin.flush()


class Gr2ToJson(Plugins):
    def __init__(self):
        super().__init__("gr2tojson", "gr2tojson.exe")

    def run(self, *args):
        super().run(*args)


class Revorb(Plugins):
    def __init__(self):
        super().__init__("revorb", "revorb.exe")

    def run(self, *args):
        super().run(*args)


class NvttExport(Plugins):
    def __init__(self, proc):
        super().__init__("nvidia", "nvtt_export.exe")
        self.proc = proc

    def _read_output(self, pipe):
        for line in iter(pipe.readline, ""):
            print(line, end="")

    def run(self, *args):
        filename = os.path.splitext(args[0])[0]
        dir_path = os.path.dirname(args[0])
        out = os.path.join(dir_path, f"{filename}.png")

        self.write(self.proc, f'{self.exe} "{args[0]}" -o "{out}"\n')

        while not os.path.exists(out):
            time.sleep(0.01)

        os.remove(args[0])


class Ww2Ogg(Plugins):
    def __init__(self):
        super().__init__("ww2ogg", "ww2ogg.exe")

    def run(self, *args):
        filename = os.path.splitext(args[0])
        dest = os.path.dirname(args[0])
        old = os.path.join(dest, f"{filename[0]}{filename[1]}")
        new = os.path.join(dest, f"{filename[0]}.ogg")
        stdout = super().run(
            old,
            "-o",
            new,
            "--pcb",
            os.path.join(self.cwd, "ww2ogg", "packed_codebooks_aoTuV_603.bin"),
        )
        if "Parse error" in stdout:
            return stdout, new
        return None, new
