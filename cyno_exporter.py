from datetime import datetime
from pathlib import Path
import sys, os, time, shutil, json, concurrent.futures, argparse
import requests
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QTreeWidget,
    QTreeWidgetItem,
    QMenu,
    QFileDialog,
    QProgressDialog,
    QProgressBar,
    QWidget,
    QDialog,
    QVBoxLayout,
    QTextEdit,
    QHeaderView,
    QLabel,
    QMenuBar,
    QHBoxLayout,
    QSizePolicy,
    QMessageBox,
    QPushButton,
    QTabWidget,
)
from PyQt6.QtGui import QIcon, QPixmap, QAction
from PyQt6.QtCore import Qt, QObject, pyqtSignal
from utils.obj import Wavefront
from utils.plugins import Revorb, Ww2Ogg, Texconv, ImageMagick

CONFIG_FILE = "./config.json"
VERSION = "v1.0.1"
WINDOW_TITLE = f"Cyno Exporter {VERSION}"
CLIENTS = {
    "tq": {"name": "Tranquility", "id": "TQ"},
    "sisi": {"name": "Singularity", "id": "SISI"},
    "serenity": {"name": "Serenity", "id": "SERENITY"},
    "duality": {"name": "Duality", "id": "DUALITY"},
    "infinity": {"name": "Infinity", "id": "INFINITY"},
    "sharedCache": {"name": "Local", "id": None},
}
STYLE_SHEET = open(
    os.path.join(Path(__file__).parent, "style.qss"), "r", encoding="utf-8"
).read()


class EVEDirectory(QTreeWidgetItem):
    def __init__(self, parent, text="", icon=None):
        super().__init__(parent)
        self.setText(0, text)
        self.setIcon(0, icon)
        self.items = []
        self.size = int()

    def add(self, item):
        self.items.append(item)


class EVEFile(QTreeWidgetItem):
    def __init__(
        self,
        parent,
        text="",
        filename="",
        respath="",
        resfile_hash="",
        size=0,
        icon=QIcon(),
    ):
        super().__init__(parent)
        self.setText(0, text)
        self.setIcon(0, icon)
        self.filename = filename
        self.size = int(size)
        self.respath = respath
        self.resfile_hash = resfile_hash


class ResIndex:
    def __init__(self, chinese_client=False, event_logger=None):
        self.chinese_client = chinese_client
        self.event_logger = event_logger
        if not chinese_client:
            self.binaries_url = "https://binaries.eveonline.com"
            self.resources_url = "https://resources.eveonline.com"
        else:
            self.chinese_url = (
                "https://eve-china-version-files.oss-cn-hangzhou.aliyuncs.com"
            )
            self.binaries_url = "https://ma79.gdl.netease.com/eve/binaries"
            self.resources_url = "https://ma79.gdl.netease.com/eve/resources"

    def fetch_client(self, client, timeout=10):
        if not self.chinese_client:
            response = requests.get(f"{self.binaries_url}/{client}", timeout=timeout)
        else:
            response = requests.get(f"{self.chinese_url}/{client}", timeout=timeout)
        try:
            if response.status_code == 200:
                client = response.json()
                self.event_logger.add(f"Requesting client: {response.url}")
                if not self.is_protected(client):
                    return self.get_build(client)
                else:
                    return None
        except Exception:
            self.event_logger.add(f"Connection failed to: {response.url}")

    @staticmethod
    def resindexfile_object(content):
        resfile_list = []
        for line in sorted(filter(bool, content.lstrip().splitlines())):
            data = line.lower().split(",")
            resfile_list.append(
                {
                    "res_path": data[0].split(":/")[1],
                    "resfile_hash": data[1],
                    "size": data[3],
                }
            )

        return resfile_list

    @staticmethod
    def get_soundbankinfo(content):
        return next(
            (
                bnk["resfile_hash"]
                for bnk in content
                if "soundbanksinfo.json" in bnk["res_path"]
            ),
            None,
        )

    def fetch_resindexfile(self, build):
        base_url = self.chinese_url if self.chinese_client else self.binaries_url
        response = requests.get(f"{base_url}/eveonline_{build}.txt")
        self.event_logger.add(f"Requesting resindex: {base_url}/eveonline_{build}.txt")
        if response.status_code == 200:
            resfileindex = next(
                (
                    resfile
                    for resfile in ResIndex.resindexfile_object(response.text)
                    if resfile["res_path"].startswith("resfileindex.txt")
                ),
                None,
            )

            resfileindex_file = f"{build}_resfileindex.txt"

            os.makedirs("resindex", exist_ok=True)
            resfileindex_file_path = os.path.join("resindex", resfileindex_file)
            with open(resfileindex_file_path, "wb") as f:
                content = requests.get(
                    f"{self.binaries_url}/{resfileindex['resfile_hash']}"
                ).content
                f.write(content)

            return resfileindex_file
        return None

    def is_protected(self, client):
        return bool(client["protected"])

    def get_build(self, client):
        return int(client["build"])


class ResTree(QTreeWidget):
    def __init__(
        self,
        parent=None,
        client=None,
        chinese_client=False,
        is_shared_cache=False,
        event_logger=None,
        shared_cache=None,
    ):
        super().__init__(parent)

        self.setHeaderLabel("res: ► ")
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        self.itemSelectionChanged.connect(self.show_selected_item)
        self.setHeaderLabels(["", "Size"])

        self.setColumnWidth(0, 775)
        self.setColumnWidth(1, 50)
        self.header().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)

        self.chinese_client = chinese_client
        self.client = client

        self.is_shared_cache = is_shared_cache
        self.shared_cache = shared_cache
        self.are_resfiles_loaded = False
        self.event_logger = event_logger

        self.protected_label = None

        self.icon_atlas = QPixmap("./icons/icons.png")

        try:
            self.config = json.loads(open(CONFIG_FILE, "r", encoding="utf-8").read())
        except:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                f.write(json.dumps({"SharedCacheLocation": ""}, indent=4))

            self.config = json.loads(open(CONFIG_FILE, "r", encoding="utf-8").read())

        self.show()

    def show_selected_item(self):
        try:
            self.setHeaderLabel(
                "res: ► "
                + self.get_path_segments(self.selectedItems()[0]).replace("\\", " ► ")
            )
        except:
            pass

    def get_path_segments(self, item):
        path_segments = []
        try:
            while item and item.text(0) != "res:":
                path_segments.insert(
                    0, item.text(0) if isinstance(item, EVEDirectory) else item.filename
                )
                item = item.parent()
            return os.path.join(*path_segments)
        except:
            return ""

    def get_directory_size(self, directory):
        total = 0
        for child in directory.items:
            if isinstance(child, EVEFile):
                total += int(child.size)
            elif isinstance(child, EVEDirectory):
                total += int(self.get_directory_size(child))
        directory.size = total
        return total

    def copy_folder_files(self, folder_item, base_path):
        files = []
        for i in range(folder_item.childCount()):
            child = folder_item.child(i)
            child_name = child.text(0)
            child_path = os.path.join(base_path, child_name)

            if child.childCount() > 0:
                files.extend(self.copy_folder_files(child, child_path))
            else:
                files.append(child)

        return files

    def download_file_itemless(self, resfile_hash, dest_path):
        resindex = ResIndex(
            chinese_client=self.chinese_client, event_logger=self.event_logger
        )
        try:
            url = f"{resindex.resources_url}/{resfile_hash}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                with open(dest_path, "wb") as f:
                    f.write(response.content)
            elif response.status_code == 404:
                return "404 error: download_file_itemless"
        except:
            self.event_logger.add(f"Request failed: {url}")

    def download_file(self, item, dest_path):
        resindex = ResIndex(
            chinese_client=self.chinese_client, event_logger=self.event_logger
        )
        try:
            url = f"{resindex.resources_url}/{item.resfile_hash}"
            response = requests.get(url)
            if response.status_code == 200:
                with open(dest_path, "wb") as f:
                    f.write(response.content)
            elif response.status_code == 404:
                return f"404 error: {item.filename}"

            return item.filename
        except:
            self.event_logger.add(f"Request failed: {url}")

    def save_as_obj_command(self, item):
        out_file = self.save_file_command(item)
        if not out_file:
            return
        Wavefront().to_obj(out_file)
        self.event_logger.add(f"Obj exported: {out_file}")

    def save_as_png_command(self, out_file_path):
        is_normal_map = out_file_path.lower().endswith("_n.dds")
        out_png = Texconv(is_normal_map=is_normal_map).run(out_file_path)
        # remove the alpha channel from the normal map
        if is_normal_map:
            ImageMagick().run(out_png)
        os.remove(out_file_path)

    def save_as_ogg_command(self, out_file_path):
        stdout, wem = Ww2Ogg().run(out_file_path)
        temp = os.path.join(
            os.path.dirname(out_file_path), f"{out_file_path.split('.')[0]}.temp"
        )

        if stdout is not None:
            self.event_logger.add(
                f"Could not convert: {out_file_path}\n\n{str(stdout)}"
            )
            return

        os.remove(out_file_path)
        Revorb().run(wem, temp)
        os.remove(wem)
        os.rename(
            temp,
            os.path.join(
                os.path.dirname(out_file_path), f"{out_file_path.split('.')[0]}.ogg"
            ),
        )

    def save_file_command(self, item, multiple=False, multiple_destination=None):
        if not multiple:
            dest_folder = QFileDialog.getExistingDirectory(None, "Save Destination")
            if not dest_folder:
                return
            out_file_path = os.path.join(dest_folder, item.filename)
        else:
            out_file_path = multiple_destination

        if self.is_shared_cache:
            folder, resfile_hash = item.resfile_hash.split("/", 1)
            shutil.copy(
                os.path.join(
                    self.config["SharedCacheLocation"], "ResFiles", folder, resfile_hash
                ),
                out_file_path,
            )
        else:
            self.download_file(
                item=item,
                dest_path=out_file_path,
            )

        if out_file_path.lower().endswith(".dds"):
            self.save_as_png_command(out_file_path)
        elif out_file_path.lower().endswith(".wem"):
            self.save_as_ogg_command(out_file_path)
        if not multiple:
            self.event_logger.add(f"Exported resfile to: {out_file_path}")
        return out_file_path if not multiple else item.filename

    def save_folder_command(self, item):
        dest_folder = QFileDialog.getExistingDirectory(None, "Select Destination")
        if not dest_folder:
            return

        path_segments = self.get_path_segments(item)
        files = self.copy_folder_files(item, path_segments)

        loading = LoadingScreenWindow(files, True)

        with concurrent.futures.ThreadPoolExecutor(max_workers=15) as worker:
            futures = []

            for i, file in enumerate(files):
                if isinstance(file, EVEFile):
                    file_path = os.path.normpath(
                        os.path.join(dest_folder, file.respath)
                    )
                    os.makedirs(os.path.dirname(file_path), exist_ok=True)
                    futures.append(
                        worker.submit(self.save_file_command, file, True, file_path)
                    )

            for future in concurrent.futures.as_completed(futures):
                loading.label.setText(future.result())
                loading.setValue(loading.value() + 1)
                QApplication.processEvents()

        self.event_logger.add(f"Exported {len(files)} resfiles to {dest_folder}")
        loading.close()

    def load_resfiles(self, parent, client=None):
        self.shared_cache.setEnabled(False)
        if self.are_resfiles_loaded:
            return
        parent.clear()
        root = EVEDirectory(parent, "res:", QIcon("./icons/res.png"))
        root.setExpanded(True)

        if self.protected_label is not None:
            self.protected_label.close()

        self.protected_label = QLabel("Client is protected", self)

        os.makedirs("resindex", exist_ok=True)
        if self.is_shared_cache:
            self.config = json.loads(open(CONFIG_FILE, "r").read())
            try:
                with open(
                    os.path.join(
                        self.config["SharedCacheLocation"], "tq", "resfileindex.txt"
                    ),
                    "r",
                ) as f:
                    resfileindex = ResIndex.resindexfile_object(f.read())

                bnk_hash = ResIndex.get_soundbankinfo(resfileindex)
                self.download_file_itemless(
                    bnk_hash,
                    f"./resindex/soundbanksinfo.json",
                )
                bnk = json.loads(open("./resindex/soundbanksinfo.json", "r").read())
                self.event_logger.add("Loading resfiles...")
                start = time.time()
                self.load(root=root, resfiles=resfileindex, bankfileinfo=bnk)
                self.event_logger.add(
                    f"Took {time.time() - start:.2f}s to load resfiles"
                )
            except OSError:
                QMessageBox.warning(
                    self, "Error", f"Invalid Shared Cache location. Check config.json"
                )
        else:
            resindex = ResIndex(
                chinese_client=self.chinese_client, event_logger=self.event_logger
            )
            build = resindex.fetch_client(client)
            if build is not None:
                resfileindex_file = resindex.fetch_resindexfile(build=build)

                with open(
                    os.path.join("resindex", resfileindex_file), "r", encoding="utf-8"
                ) as f:
                    resfileindex = ResIndex.resindexfile_object(f.read())

                bnk_hash = ResIndex.get_soundbankinfo(resfileindex)
                self.download_file_itemless(
                    bnk_hash,
                    f"./resindex/{build}_soundbanksinfo.json",
                )
                bnk = json.loads(
                    open(f"./resindex/{build}_soundbanksinfo.json", "r").read()
                )
                self.event_logger.add("Loading resfiles...")
                start = time.time()
                self.load(root=root, resfiles=resfileindex, bankfileinfo=bnk)
                self.event_logger.add(
                    f"Took {time.time() - start:.2f}s to load resfiles"
                )
            else:
                root.setHidden(True)
                self.protected_label.setGeometry(25, 25, 300, 50)
                self.protected_label.show()
                self.event_logger.add(
                    "Could not load resfiles due to client protection"
                )

        self.shared_cache.setEnabled(True)

    def add_directory(self, part, parent, path, dir_map):
        if path not in dir_map:
            dir_item = EVEDirectory(
                parent, text=part, icon=QIcon(self.icon_atlas.copy(16, 0, 15, 16))
            )
            dir_map[path] = dir_item
            parent.add(dir_item)
            parent.setText(1, self.format_filesize(self.get_directory_size(parent)))
        return dir_map[path]

    def add_resfile_filter(self, i, name):
        if "_lowdetail" in name or "_mediumdetail" in name:
            i += 1
            return True
        return False

    def load(self, root, resfiles, bankfileinfo):
        dir_map = {}

        loading = ProgressBar(resfiles, self)
        loading_label = QLabel("Building tree...", self)
        loading_label.setGeometry(5, 795, 900, 15)
        loading_label.setStyleSheet("font-weight: bold;")
        loading_label.show()
        for i, resfile in enumerate(resfiles):
            if ".wem" in resfile["res_path"]:
                name = os.path.basename(resfile["res_path"]).split(".")[0]
                resfiles[i]["res_path"] = next(
                    (
                        bank["Path"].replace("\\", "/").lower()
                        for bank in bankfileinfo["SoundBanksInfo"]["StreamedFiles"]
                        if name == bank["Id"]
                    ),
                    resfile["res_path"],
                )

            path_segments = resfile["res_path"].split("/")
            parent = root

            full_path = ""

            for segment in path_segments[:-1]:
                full_path = os.path.join(full_path, segment)
                parent = self.add_directory(segment, parent, full_path, dir_map)

            name = path_segments[-1]
            ext = os.path.splitext(name)

            # filter junk
            if self.add_resfile_filter(i, name):
                continue

            icon = self.set_icon_from_extension(ext[1])

            if resfile["res_path"].lower().startswith("sfx"):
                full_path = ""
                for segment in path_segments[:-1]:
                    full_path = os.path.join(full_path, segment)
                    parent = self.add_directory(segment, parent, full_path, dir_map)

                file_item = EVEFile(
                    parent,
                    text=name,
                    filename=name,
                    size=resfile["size"],
                    respath=resfile["res_path"],
                    resfile_hash=resfile["resfile_hash"],
                    icon=icon,
                )
                file_item.setText(1, self.format_filesize(int(resfile["size"])))
                parent.add(file_item)
                parent.setText(1, self.format_filesize(self.get_directory_size(parent)))
            else:
                file_item = EVEFile(
                    parent,
                    text=name,
                    filename=name,
                    size=resfile["size"],
                    respath=resfile["res_path"],
                    resfile_hash=resfile["resfile_hash"],
                    icon=icon,
                )
                file_item.setText(1, self.format_filesize(int(resfile["size"])))
                parent.add(file_item)
                parent.setText(1, self.format_filesize(self.get_directory_size(parent)))

            loading.setValue(i + 1)
            QApplication.processEvents()

        loading.close()
        loading_label.close()
        self.are_resfiles_loaded = True

    def set_icon_from_extension(self, ext):
        if ext == ".png":
            return QIcon(self.icon_atlas.copy(97, 0, 15, 16))
        elif ext == ".dds":
            return QIcon(self.icon_atlas.copy(33, 0, 15, 16))
        elif ext == ".jpg":
            return QIcon(self.icon_atlas.copy(81, 0, 15, 16))
        elif ext == ".gr2":
            return QIcon(self.icon_atlas.copy(177, 0, 15, 16))
        elif ext in (".txt", ".yaml", ".xml", ".json"):
            return QIcon(self.icon_atlas.copy(130, 0, 15, 16))
        elif ext in (".wem", ".webm"):
            return QIcon(self.icon_atlas.copy(65, 0, 15, 16))
        else:
            return QIcon(self.icon_atlas.copy(161, 0, 15, 16))

    def format_filesize(self, size):
        size = float(size)
        for unit in ["KB", "MB", "GB"]:
            size /= 1024
            if size <= 1024:
                return f"{size:.2f} {unit}"

    def show_context_menu(self, point):
        item = self.itemAt(point)
        if item:
            menu = QMenu(self)

            (
                save_folder_action,
                save_file_action,
                export_obj_action,
                export_png_action,
                export_ogg_action,
            ) = (None, None, None, None, None)

            if isinstance(item, EVEDirectory) and item.text(0) != "res:":
                save_folder_action = menu.addAction("Save folder")
            elif isinstance(item, EVEFile):
                save_file_action = menu.addAction("Save file")
                if item.filename.endswith(".gr2"):
                    menu.addSeparator()
                    export_obj_action = menu.addAction("Export as .obj")

            menu.installEventFilter(ContextMenuFilter(menu))
            action = menu.exec(self.mapToGlobal(point))

            if action is None:
                return

            if action == save_folder_action:
                self.save_folder_command(item)
            elif action == save_file_action:
                self.save_file_command(item)
            elif action == export_obj_action:
                self.save_as_obj_command(item)


class ContextMenuFilter(QObject):
    def eventFilter(self, context_menu, event):
        if isinstance(context_menu, QMenu):
            if event.type() == event.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.RightButton:
                    context_menu.close()
                    return True
        return False


class CynoExporterWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setFixedSize(900, 900)
        self.setWindowTitle(WINDOW_TITLE)
        self.setWindowIcon(QIcon("icon.ico"))
        self.init()

    def init(self):

        self.move(
            QApplication.primaryScreen().geometry().center() - self.rect().center()
        )

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        self.tab_widget = QTabWidget()

        self.setStyleSheet(STYLE_SHEET)

        self.event_logger = EventLogger()

        self.set_shared_cache_action = QAction("&Set Shared Cache", self)
        self.set_shared_cache_action.triggered.connect(self.set_shared_cache)
        self.set_shared_cache_action.setEnabled(False)

        self.shared_cache_tq = ResTree(
            self,
            is_shared_cache=True,
            event_logger=self.event_logger,
            shared_cache=self.set_shared_cache_action,
        )
        self.tranquility = ResTree(
            self,
            f"eveclient_{CLIENTS['tq']['id']}.json",
            event_logger=self.event_logger,
            shared_cache=self.set_shared_cache_action,
        )
        self.singularity = ResTree(
            self,
            f"eveclient_{CLIENTS['sisi']['id']}.json",
            event_logger=self.event_logger,
            shared_cache=self.set_shared_cache_action,
        )
        self.serenity = ResTree(
            self,
            f"eveclient_{CLIENTS['serenity']['id']}.json",
            chinese_client=True,
            event_logger=self.event_logger,
            shared_cache=self.set_shared_cache_action,
        )
        self.infinity = ResTree(
            self,
            f"eveclient_{CLIENTS['infinity']['id']}.json",
            chinese_client=True,
            event_logger=self.event_logger,
            shared_cache=self.set_shared_cache_action,
        )

        self.tab_widget.addTab(self.shared_cache_tq, CLIENTS["sharedCache"]["name"])
        self.tab_widget.addTab(self.tranquility, CLIENTS["tq"]["name"])
        self.tab_widget.addTab(self.singularity, CLIENTS["sisi"]["name"])
        self.tab_widget.addTab(self.serenity, CLIENTS["serenity"]["name"])
        self.tab_widget.addTab(self.infinity, CLIENTS["infinity"]["name"])

        self.menu_bar = QMenuBar()
        self.setMenuBar(self.menu_bar)

        self.help_menu = QMenu("&Help", self)
        self.menu_bar.addMenu(self.help_menu)

        help_action = QAction("&About", self)
        help_action.triggered.connect(lambda: AboutDialogPanel(self))
        logs_action = QAction("&Logs", self)
        logs_action.triggered.connect(lambda: LogsDialogPanel(self, self.event_logger))

        self.help_menu.addAction(self.set_shared_cache_action)
        self.help_menu.addSeparator()
        self.help_menu.addAction(help_action)
        self.help_menu.addAction(logs_action)

        self.tab_widget.currentChanged.connect(self.on_tab_change)

        main_layout.addWidget(self.tab_widget)

    def set_shared_cache(self):
        folder = QFileDialog.getExistingDirectory(
            None, "Path to EVE's SharedCache folder"
        )
        if not folder:
            return
        with open("./config.json", "w", encoding="utf-8") as f:
            json.dump({"SharedCacheLocation": folder}, f, indent=4)

        self.tab_widget.tabBar().setEnabled(False)
        self.shared_cache_tq.are_resfiles_loaded = False
        self.shared_cache_tq.load_resfiles(
            self.shared_cache_tq, self.shared_cache_tq.client
        )
        self.tab_widget.tabBar().setEnabled(True)

    def closeEvent(self, event):
        os.system('taskkill /F /IM "Cyno Exporter.exe"')

    def on_tab_change(self, i):
        self.tab_widget.tabBar().setEnabled(False)
        self.event_logger.add(f"Switching server to: {self.tab_widget.tabText(i)}")

        if i == 1 and not self.tranquility.are_resfiles_loaded:
            self.tranquility.load_resfiles(self.tranquility, self.tranquility.client)
        elif i == 2 and not self.singularity.are_resfiles_loaded:
            self.singularity.load_resfiles(self.singularity, self.singularity.client)
        elif i == 3 and not self.serenity.are_resfiles_loaded:
            self.serenity.load_resfiles(self.serenity, self.serenity.client)
        elif i == 4 and not self.infinity.are_resfiles_loaded:
            self.infinity.load_resfiles(self.infinity, self.infinity.client)

        self.tab_widget.tabBar().setEnabled(True)


class DialogPanel(QDialog):
    def __init__(self, parent, title):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        self.setWindowModality(Qt.WindowModality.ApplicationModal)


class EventLogger(QObject):
    on_update = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.log_items = []

    def add(self, message):
        self.log_items.append(
            {"time": datetime.now().strftime("%H:%M:%S"), "message": message}
        )
        self.on_update.emit()


class LogsDialogPanel(DialogPanel):
    def __init__(self, parent, event_logger):
        super().__init__(parent, "Logs")

        self.logs_widget = QTreeWidget(self)
        self.logs_widget.setHeaderLabels(["Time", "Event"])
        self.logs_widget.header().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)

        self.setMinimumWidth(400)
        self.logs_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        layout = QVBoxLayout(self)
        layout.addWidget(self.logs_widget, stretch=1)

        self.event_logger = event_logger
        self.event_logger.on_update.connect(self._update)
        self._update()

        self.setWindowModality(Qt.WindowModality.NonModal)
        self.show()

    def _update(self):
        self.logs_widget.clear()
        for log in self.event_logger.log_items:
            item = QTreeWidgetItem(self.logs_widget)
            item.setText(0, log["time"])
            item.setText(1, log["message"])


class LicenseAgreementDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        from utils.license_agreement import LICENSE_TEXT

        self.setWindowTitle("License Agreement")
        self.setFixedSize(900, 525)

        legal_disclaimer = QTextEdit(self)
        legal_disclaimer.setPlainText(LICENSE_TEXT)
        legal_disclaimer.setStyleSheet("font-size: 11px;")
        legal_disclaimer.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        accept_button = QPushButton("I accept", self)
        accept_button.clicked.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(legal_disclaimer, stretch=1)
        layout.addWidget(accept_button)


class AboutDialogPanel(DialogPanel):
    def __init__(self, parent):
        super().__init__(parent, "About")

        app_label = QLabel(f"<img src='icon.ico', width='40'> {WINDOW_TITLE}", self)
        app_label.setStyleSheet("font-size: 24px;")

        self.setFixedSize(700, 525)

        author = QLabel("Author", self)
        author.setStyleSheet("font-size: 15px; font-weight: bold;")

        label = QLabel(
            'Tyloth: <a style="color:white;" href="https://github.com/largeBIGsnooze/cyno-exporter">https://github.com/largeBIGsnooze/cyno-exporter</a>',
            self,
        )
        label.setStyleSheet("font-size: 12px;")
        label.setOpenExternalLinks(True)

        credit = QLabel("Credits", self)
        credit.setStyleSheet("font-size: 15px; font-weight: bold;")

        credit_link = QLabel(
            'leixingyu, unrealStylesheet: <a style="color:white;" href="https://github.com/leixingyu/unrealStylesheet">https://github.com/leixingyu/unrealStylesheet</a>',
            self,
        )
        credit_text = QLabel(
            'Khossyy, ww2ogg: <a style="color: white;" href="https://github.com/khossyy/wem2ogg">https://github.com/khossyy/wem2ogg</a>',
            self,
        )
        credit_text_2 = QLabel(
            'Tamber, gr2tojson: <a style="color: white;" href="https://github.com/cppctamber/evegr2tojson">https://github.com/cppctamber/evegr2tojson</a>',
            self,
        )
        credit_text_3 = QLabel(
            'ItsBranK, ReVorb: <a style="color: white;" href="https://github.com/ItsBranK/ReVorb">https://github.com/ItsBranK/ReVorb</a>',
            self,
        )
        credit_link.setOpenExternalLinks(True)
        credit_text.setOpenExternalLinks(True)
        credit_text_2.setOpenExternalLinks(True)
        credit_text_3.setOpenExternalLinks(True)

        legal_disclaimner_header = QLabel("Legal Disclaimer", self)
        legal_disclaimner_header.setStyleSheet("font-size: 15px; font-weight: bold;")
        legal_disclaimer = QTextEdit(self)
        legal_disclaimer.setPlainText(
            "This tool provides access to materials used with limited permission of CCP Games.It is not endorsed by CCP Games and does not reflect the views or opinions of CCP Games or anyone officially involved in producing or managing EVE Online.\n\nAs such, it does not contribute to the official narrative of the fictional universe, if applicable.\n\nEVE Online © CCP Games.\n\nTHE SOFTWARE IS PROVIDED AS IS, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.\n\nIN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE."
        )
        legal_disclaimer.setStyleSheet("font-size: 11px;")

        legal_disclaimer.setReadOnly(True)
        legal_disclaimer.setFixedWidth(700)

        div = QWidget(self)
        div.setStyleSheet("margin: 5px;")
        div.setFixedWidth(700)

        layout = QVBoxLayout(div)
        layout.addWidget(app_label)
        layout.addWidget(author)
        layout.addWidget(label)
        layout.addWidget(credit)
        layout.addWidget(credit_link)
        layout.addWidget(credit_text)
        layout.addWidget(credit_text_2)
        layout.addWidget(credit_text_3)
        layout.addWidget(legal_disclaimner_header)
        layout.addWidget(legal_disclaimer)

        self.show()


class ProgressBar(QProgressBar):
    def __init__(self, files, parent):
        super().__init__(parent)
        self.setGeometry(0, 815, 900, 15)
        self.setStyleSheet("border-top: 5px solid #242424;")
        self.setValue(0)
        self.setMaximum(len(files))
        self.show()


class LoadingScreenWindow(QProgressDialog):
    def __init__(self, files, stay_on_top=False):
        super().__init__()
        self.setLabelText("Loading...")
        self.setWindowTitle(WINDOW_TITLE)
        self.setCancelButton(None)
        self.setValue(0)

        self.label = QLabel("", self)
        self.label.setObjectName("loadingLabel")
        self.setLabel(self.label)

        self.setMaximum(len(files))
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(300, 60)
        self.move(
            QApplication.primaryScreen().geometry().center() - self.rect().center()
        )
        self.setStyleSheet(STYLE_SHEET)
        self.setWindowModality(
            Qt.WindowModality.WindowModal
            if not stay_on_top
            else Qt.WindowModality.ApplicationModal
        )
        self.show()
        self.raise_()


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("--dev", action="store_true")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon("icon.ico"))
    window = CynoExporterWindow()
    license_agreement = LicenseAgreementDialog()
    license_agreement.setStyleSheet(STYLE_SHEET)

    def show():
        window.show()
        window.tab_widget.tabBar().setEnabled(False)
        window.shared_cache_tq.load_resfiles(
            window.shared_cache_tq, window.shared_cache_tq.client
        )
        window.tab_widget.tabBar().setEnabled(True)
        sys.exit(app.exec())

    if not args.dev:
        if license_agreement.exec() == QDialog.DialogCode.Accepted:
            show()
    else:
        show()
