import os, subprocess


class Plugins:
    def __init__(self, *plugin):
        self.cwd = "./tools"
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


class Texconv(Plugins):
    def __init__(self):
        super().__init__("texconv", "texconv.exe")

    def run(self, *args):
        super().run(args[0], "-ft", "PNG", "-y", "-o", os.path.dirname(args[0]))


class Ww2Ogg(Plugins):
    def __init__(self):
        super().__init__("ww2ogg", "ww2ogg.exe")

    def run(self, *args):
        filename = os.path.splitext(args[1])
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
