from datetime import datetime
from pathlib import Path
import sys, os, time, shutil, json, concurrent.futures, argparse
import requests
from dotenv import load_dotenv
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
    QLineEdit,
    QVBoxLayout,
    QTextEdit,
    QHeaderView,
    QLabel,
    QMenuBar,
    QSizePolicy,
    QMessageBox,
    QPushButton,
    QTabWidget,
)
from PyQt6.QtGui import QIcon, QPixmap, QAction, QKeySequence, QShortcut
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QSettings, QTimer
from utils.plugins import Revorb, Ww2Ogg, NvttExport, BlackReader
from utils.obj import Wavefront
import subprocess
from typing import Any, List, Optional, Union, Dict, cast


class ConvertTypes:
    GENERIC = "generic"
    PNG = "png"
    OBJ = "obj"
    OGG = "ogg"
    BLACK = "black"


load_dotenv()

CONFIG_FILE = "./config.json"
VERSION = "v2.0.0"
WINDOW_TITLE = f"Cyno Exporter {VERSION}"
CLIENTS: Dict[str, Dict[str, Any]] = {
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
DB = json.loads(open("./db.json", "r").read())

try:
    PROC: Any = subprocess.Popen(
        ["cmd.exe"],
        creationflags=subprocess.CREATE_NO_WINDOW,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
except FileNotFoundError:
    print("could not find cmd.exe")
except Exception as e:
    print(f"could not open cmd.exe: {e}")


class EVEDirectory(QTreeWidgetItem):
    def __init__(
        self,
        parent: Optional[Union[QTreeWidget, QTreeWidgetItem]],
        icon: QIcon,
        text: str = "",
        filename: str = "",
    ) -> None:
        super().__init__(parent)  # type: ignore
        self.setText(0, text)
        self.setIcon(0, icon)
        self.filename = filename
        self.items: List[Any] = []
        self.size = int()

    def add(self, item: QTreeWidgetItem):
        self.items.append(item)


class EVEFile(QTreeWidgetItem):
    def __init__(
        self,
        parent: QTreeWidgetItem,
        text: str = "",
        filename: str = "",
        description: str = "",
        respath: str = "",
        resfile_hash: str = "",
        size: int = 0,
        icon: QIcon = QIcon(),
    ):
        super().__init__(parent)  # type: ignore
        self.setText(0, text)
        self.setIcon(0, icon)
        self.filename = filename
        self.description = description
        self.size = int(size)
        self.respath = respath
        self.resfile_hash = resfile_hash
        self.setToolTip(0, description)


class ResFileIndex:
    def __init__(self, chinese_client: bool = False, event_logger: Any = None):
        self.chinese_client = chinese_client
        self.event_logger = event_logger

        if not chinese_client:
            self.binaries_url = "https://binaries.eveonline.com"
            self.resources_url = "https://resources.eveonline.com"
        else:
            self.chinese_url = os.environ.get("CHINESE_RESINDEX_CDN")
            self.binaries_url = f"{os.environ.get('CHINESE_CDN')}/binaries"
            self.resources_url = f"{os.environ.get('CHINESE_CDN')}/resources"

    def fetch_client(self, client: Dict[str, Any], timeout: int = 10):
        base_url = self.chinese_url if self.chinese_client else self.binaries_url
        response: Any = None
        try:
            response = requests.get(f"{base_url}/{client}", timeout=timeout)
            if response.status_code == 200:
                client = response.json()
                self.event_logger.add(f"Requesting client: {response.url}")
                if not self._is_protected(client):
                    return self._get_build(client)
                else:
                    return None
        except requests.exceptions.MissingSchema:
            self.event_logger.add(f"Connection failed.")
        except Exception:
            self.event_logger.add(f"Connection failed to: {response.url}")

    @staticmethod
    def resindexfile_object(content: str):
        resfile_list: List[Dict[str, Any]] = []
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
    def get_soundbankinfo(content: Any) -> Union[str, None]:
        return next(
            (
                bnk["resfile_hash"]
                for bnk in content
                if "soundbanksinfo.json" in bnk["res_path"]
            ),
            None,
        )

    def fetch_resindexfile(self, build: int) -> str:
        base_url = self.chinese_url if self.chinese_client else self.binaries_url
        response = requests.get(f"{base_url}/eveonline_{build}.txt")
        self.event_logger.add(f"Requesting resindex: {base_url}/eveonline_{build}.txt")
        if response.status_code == 200:
            resfileindex: Any = next(
                (
                    resfile
                    for resfile in ResFileIndex.resindexfile_object(response.text)
                    if resfile["res_path"].startswith("resfileindex.txt")
                ),
                None,
            )

            resfileindex_file = f"{build}_resfileindex.txt"

            os.makedirs("resindex", exist_ok=True)
            resfileindex_file_path = os.path.join("resindex", resfileindex_file)
            content = requests.get(
                f"{self.binaries_url}/{resfileindex['resfile_hash']}"
            ).content

            with open(resfileindex_file_path, "wb") as f:
                f.write(content)

            return resfileindex_file
        return ""

    def _is_protected(self, client: Any) -> bool:
        return bool(client["protected"])

    def _get_build(self, client: Any) -> int:
        return int(client["build"])


class ResTree(QTreeWidget):
    def __init__(
        self,
        parent: Any = None,
        client: Any = None,
        chinese_client: bool = False,
        event_logger: Any = None,
        shared_cache: Any = None,
    ):
        super().__init__(parent)

        self.setHeaderLabel("res: ► ")
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)  # type: ignore
        self.itemSelectionChanged.connect(self._show_selected_item)  # type: ignore
        self.setHeaderLabels(["", "Size"])  # type: ignore

        self.setColumnWidth(0, 775)
        self.setColumnWidth(1, 50)

        self._header = self.header()
        if self._header:
            self._header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)

        self.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)

        self.last_saved_dir: str = ""
        self.settings = QSettings("cynostudios", "Cyno Exporter")

        self.chinese_client: bool = chinese_client
        self.client: Any = client

        self.shared_cache: Any = shared_cache
        self.are_resfiles_loaded = False
        self.event_logger: Any = event_logger

        self.protected_label = None
        self.icon_atlas = QPixmap("./icons/icons.png")
        try:
            self.config = json.loads(open(CONFIG_FILE, "r", encoding="utf-8").read())
        except:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                f.write(json.dumps({"SharedCacheLocation": ""}, indent=4))

            self.config = json.loads(open(CONFIG_FILE, "r", encoding="utf-8").read())

        self.show()

    def mouseMoveEvent(self, e):  # type: ignore
        return

    def _show_selected_item(self) -> Any:
        try:
            print(f"Selected item: {cast(EVEFile, self.selectedItems()[0]).respath}")
            self.setHeaderLabel(
                "res: ► "
                + cast(EVEFile, self.selectedItems()[0]).respath.replace("/", " ► ")
            )
        except:
            pass

    def _get_path_segments(self, item: Any) -> str:
        path_segments: Any = []
        try:
            while item and item.text(0) != "res:":
                path_segments.insert(0, item.text(0))
                item = item.parent()

            return cast(str, os.path.join(*path_segments))
        except:
            return ""

    def _get_directory_size(self, directory: EVEDirectory) -> int:
        total = 0
        for child in directory.items:
            if isinstance(child, EVEFile):
                total += int(child.size)
            elif isinstance(child, EVEDirectory):
                total += int(self._get_directory_size(child))
        directory.size = total
        return total

    def copy_folder_files(
        self, folder_item: Any, base_path: str
    ) -> List[QTreeWidgetItem]:
        files: List[QTreeWidgetItem] = []
        for i in range(folder_item.childCount()):
            child = folder_item.child(i)
            child_name = child.text(0)
            child_path = os.path.join(base_path, child_name)

            if child.childCount() > 0:
                files.extend(self.copy_folder_files(child, child_path))
            else:
                files.append(child)

        return files

    def download_file_itemless(
        self, resfile_hash: Union[str, None], dest_path: str
    ) -> None:
        resindex = ResFileIndex(
            chinese_client=self.chinese_client, event_logger=self.event_logger
        )
        url = None
        try:
            url = f"{resindex.resources_url}/{resfile_hash}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                with open(dest_path, "wb") as f:
                    f.write(response.content)
            elif response.status_code == 404:
                self.event_logger.add(f"404 error: {url}")
                return
        except:
            self.event_logger.add(f"Request failed: {url}")

    def download_file(self, item: EVEFile, dest_path: str, retries: int = 0) -> Any:
        resindex = ResFileIndex(
            chinese_client=self.chinese_client, event_logger=self.event_logger
        )
        url = None
        try:
            url = f"{resindex.resources_url}/{item.resfile_hash}"
            response = requests.get(url)
            if response.status_code == 200:
                with open(dest_path, "wb") as f:
                    f.write(response.content)
                if os.path.getsize(dest_path) != item.size:
                    self.event_logger.add(
                        f"resfile size doesn't match: {dest_path}, re-trying..."
                    )
                    if retries < 3:
                        self.download_file(item, dest_path, retries + 1)
            elif response.status_code == 404:
                self.event_logger.add(f"404 error: {item.filename}")
                return
            return item.filename
        except:
            self.event_logger.add(f"Request failed: {url}")

    def _save_file_dialog(
        self,
        item: Union[Union[List[EVEFile], EVEFile], List[QTreeWidgetItem]],
        type: str,
        is_multi_select: bool = False,
    ):

        options = QFileDialog.Option.DontUseNativeDialog
        self.last_saved_dir = self.settings.value("last_dir", "")

        if is_multi_select:
            destination_path = QFileDialog.getExistingDirectory(
                self,
                "Select Destination",
                self.last_saved_dir,
                options=options | QFileDialog.Option.ShowDirsOnly,
            )

            if not destination_path:
                return

            item = cast(List[EVEFile], item)
            for file in item:
                out_path = os.path.join(destination_path, file.text(0))
                self._save_file(file, out_path, type)
            return

        item = cast(EVEFile, item)
        destination_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save File",
            os.path.join(self.last_saved_dir, item.text(0)),
            "All Files(*.)",
            options=options,
        )
        if not destination_path:
            return

        self.settings.setValue("last_dir", os.path.dirname(destination_path))

        self._save_file(item, destination_path, type)

    def _save_file(self, item: QTreeWidgetItem, out_path: str, type: Any):
        if not isinstance(item, EVEFile):
            return

        if self.client is None:
            folder, resfile_hash = item.resfile_hash.split("/", 1)
            shutil.copy(
                os.path.join(
                    self.config["SharedCacheLocation"], "ResFiles", folder, resfile_hash
                ),
                out_path,
            )
        else:
            self.download_file(item, out_path)

        if type == ConvertTypes.OBJ:
            Wavefront.to_obj(out_path)
            self.event_logger.add(f"OBJ exported: {out_path}")
        elif type == ConvertTypes.PNG:
            NvttExport(PROC).run(out_path)
            self.event_logger.add(f"DDS exported: {out_path}")
        elif type == ConvertTypes.OGG:
            stdout, wem = Ww2Ogg().run(out_path)
            temp = os.path.join(
                os.path.dirname(out_path), f"{out_path.split('.')[0]}.temp"
            )

            if stdout is not None:
                self.event_logger.add(f"Could not convert: {out_path}\n\n{str(stdout)}")
                return

            os.remove(out_path)
            Revorb().run(wem, temp)
            os.remove(wem)
            os.rename(
                temp,
                os.path.join(
                    os.path.dirname(out_path), f"{out_path.split('.')[0]}.ogg"
                ),
            )
            self.event_logger.add(f"WEM exported: {out_path}")
        elif type == ConvertTypes.BLACK:
            stdout: Any = BlackReader().run(out_path)

            if stdout:
                QMessageBox.warning(self, "Error", stdout)
            else:
                os.remove(out_path)

        return item.text(0)

    def _save_folder_command(self, item: EVEDirectory):
        options = (
            QFileDialog.Option.DontUseNativeDialog | QFileDialog.Option.ShowDirsOnly
        )
        dest_folder = QFileDialog.getExistingDirectory(
            self, "Select Destination", self.last_saved_dir, options=options
        )
        if not dest_folder:
            return

        path_segments: str = self._get_path_segments(item)
        files = self.copy_folder_files(item, path_segments)

        loading = LoadingScreenWindow(files, stay_on_top=True)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as worker:
            futures: List[Any] = []

            for file in files:
                if isinstance(file, EVEFile):
                    file_path = os.path.normpath(
                        os.path.join(dest_folder, file.respath)
                    )
                    os.makedirs(os.path.dirname(file_path), exist_ok=True)
                    futures.append(
                        worker.submit(
                            self._save_file, file, file_path, ConvertTypes.GENERIC
                        )
                    )

            for future in concurrent.futures.as_completed(futures):
                loading.label.setText(future.result())
                loading.setValue(loading.value() + 1)
                QApplication.processEvents()

        self.event_logger.add(f"Exported {len(files)} resfiles to {dest_folder}")
        loading.close()

    def _start_loading(self, root: Any, resfileindex_path: str, bnk_path: str):
        with open(resfileindex_path, "r", encoding="utf-8") as f:
            resfileindex: List[Dict[str, Any]] = ResFileIndex.resindexfile_object(
                f.read()
            )

        bnk_hash: Union[str, None] = ResFileIndex.get_soundbankinfo(resfileindex)
        self.download_file_itemless(bnk_hash, bnk_path)

        with open(bnk_path, "r", encoding="utf-8") as f:
            bnk = json.load(f)

        start_time = time.time()

        self.event_logger.add("Loading resfiles...")
        self._load_file_tree(root, resfileindex, bnk)
        self.event_logger.add(f"Took {time.time() - start_time:.2f}s to load resfiles")

    def load_resfiles(self, parent: QTreeWidget, client: Any = None) -> None:
        self.shared_cache.setEnabled(False)
        if self.are_resfiles_loaded:
            return
        parent.clear()
        root = EVEDirectory(parent, text="res:", icon=QIcon("./icons/res.png"))
        root.setExpanded(True)

        if self.protected_label is not None:
            self.protected_label.close()

        self.protected_label = QLabel("Client is protected", self)

        os.makedirs("resindex", exist_ok=True)

        if self.client is None:
            self.config = json.loads(open(CONFIG_FILE, "r").read())
            try:
                shared_cache_path = os.path.join(
                    self.config["SharedCacheLocation"], "tq", "resfileindex.txt"
                )
                resfileindex_path = os.path.join(shared_cache_path, "resfileindex.txt")
                bnk_path = "./resindex/soundbanksinfo.json"
                self._start_loading(root, shared_cache_path, bnk_path)
            except OSError:
                QMessageBox.warning(
                    self, "Error", f"Invalid Shared Cache location. Check config.json"
                )
        else:
            resindex = ResFileIndex(
                chinese_client=self.chinese_client, event_logger=self.event_logger
            )
            build = resindex.fetch_client(client)
            if build is not None:
                resfileindex_file: str = resindex.fetch_resindexfile(build=build)
                resfileindex_path: str = os.path.join("resindex", resfileindex_file)

                bnk_path = f"./resindex/{build}_soundbanksinfo.json"

                self._start_loading(root, resfileindex_path, bnk_path)
            else:
                root.setHidden(True)
                self.protected_label.setGeometry(25, 25, 300, 50)
                self.protected_label.show()
                self.event_logger.add(
                    "Could not load resfiles due to client protection"
                )

        self.shared_cache.setEnabled(True)

    def add_directory(
        self, part: str, parent: EVEDirectory, path: str, dir_map: Dict[str, Any]
    ):
        if path not in dir_map:
            dir_item = EVEDirectory(
                parent,
                text=part,
                filename=part,
                icon=QIcon(self.icon_atlas.copy(16, 0, 15, 16)),
            )
            dir_map[path] = dir_item
            parent.add(dir_item)
            parent.setText(1, self._format_filesize(self._get_directory_size(parent)))
        return dir_map[path]

    def add_resfile_filter(self, i: int, name: str) -> bool:
        if "_lowdetail" in name or "_mediumdetail" in name:
            i += 1
            return True
        return False

    def _load_file_tree(
        self, root: Any, resfiles: List[Dict[str, Any]], bankfileinfo: Any
    ):
        dir_map: Dict[str, Any] = {}

        loading = ProgressBar(resfiles, self)
        # loading_label = QLabel("Building tree...", self)
        # loading_label.setGeometry(5, 770, 900, 15)
        # loading_label.setStyleSheet("font-weight: bold;")
        # loading_label.show()

        for i, resfile in enumerate(resfiles):
            soundbank_directory = ""
            if ".wem" in resfile["res_path"]:
                search_id = os.path.basename(resfile["res_path"]).split(".")[0]
                if "StreamedFiles" in bankfileinfo["SoundBanksInfo"]:
                    for bank in bankfileinfo["SoundBanksInfo"]["StreamedFiles"]:
                        if search_id == bank["Id"]:
                            resfiles[i]["res_path"] = (
                                bank["Path"].replace("\\", "/").lower()
                            )
                        else:
                            resfiles[i]["res_path"] = resfile["res_path"]
                else:
                    for bank in bankfileinfo["SoundBanksInfo"]["SoundBanks"]:
                        if "Media" in bank:
                            for mediaFile in bank["Media"]:
                                if search_id == mediaFile["Id"]:
                                    soundbank_directory = bank["ShortName"]
                                    resfiles[i]["res_path"] = mediaFile[
                                        "CachePath"
                                    ].lower()
                                else:
                                    resfiles[i]["res_path"] = resfile["res_path"]

            path_segments = resfile["res_path"].split("/")
            parent = root
            full_path = ""

            file_name = path_segments[-1]
            ext = os.path.splitext(file_name)
            icon = self.set_icon_from_extension(ext[1])

            # filter junk
            if self.add_resfile_filter(i, file_name):
                continue

            if soundbank_directory:
                parent = self.add_directory("soundbanks", root, full_path, dir_map)
            if resfile["res_path"].lower().startswith("sfx") and soundbank_directory:
                full_path = os.path.join(full_path, soundbank_directory)
                parent = self.add_directory(
                    soundbank_directory, parent, full_path, dir_map
                )

            for segment in path_segments[:-1]:
                full_path = os.path.join(full_path, segment)
                parent = self.add_directory(segment, parent, full_path, dir_map)

            if not file_name in DB:
                db = DB.setdefault(
                    file_name, {"description": "", "aliases": [file_name]}
                )
            else:
                db = DB[file_name]

            description = db.get("description", "")
            aliases = db.get("aliases", [])
            file_item = EVEFile(
                parent,
                text=file_name,
                filename=file_name,
                description=description,
                size=resfile["size"],
                respath=resfile["res_path"],
                resfile_hash=resfile["resfile_hash"],
                icon=icon,
            )
            file_item.setData(0, Qt.ItemDataRole.UserRole, aliases)
            file_size = int(resfile["size"])
            file_item.setText(1, self._format_filesize(file_size))
            parent.add(file_item)

            current = parent
            while current:
                current.size = int(current.size) + file_size
                current.setText(1, self._format_filesize(current.size))
                current = current.parent()

            loading.setValue(i + 1)
            QApplication.processEvents()

        loading.close()
        # loading_label.close()
        self.are_resfiles_loaded = True

    def set_icon_from_extension(self, ext: str) -> QIcon:
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

    def _format_filesize(self, size: Union[float, int]):
        size = float(size)
        for unit in ["KB", "MB", "GB"]:
            size /= 1024
            if size <= 1024:
                return f"{size:.2f} {unit}"

    def show_context_menu(self, point: Any) -> Any:
        item = self.itemAt(point)
        if item:
            menu: Any = QMenu(self)

            if isinstance(item, EVEDirectory) and item.text(0) != "res:":
                menu.addAction("Save folder").triggered.connect(
                    lambda: self._save_folder_command(item)
                )
                menu.addSeparator()
                # save_folder_and_convert_dds_action = menu.addAction(
                #     "Save folder | convert dds -> png"
                # )
                # save_folder_and_convert_dds_action.triggered.connect(
                #     lambda: self._save_folder_command(item)
                # )
            elif isinstance(item, EVEFile):
                sub_menu: Any = QMenu("Export...", menu)
                sub_menu.installEventFilter(ContextMenuFilter(sub_menu))
                menu.addMenu(sub_menu)
                if len(self.selectedItems()) > 1:
                    items: List[QTreeWidgetItem] = self.selectedItems()

                    def ctx() -> str:
                        ALL_DDS = all(f.text(0).lower().endswith(".dds") for f in items)
                        ALL_GR2 = all(f.text(0).lower().endswith(".gr2") for f in items)
                        ALL_WEM = all(f.text(0).lower().endswith(".wem") for f in items) 
                        ALL_BLACK = all(f.text(0).lower().endswith(".black") for f in items)

                        if ALL_DDS:
                            return ConvertTypes.PNG
                        elif ALL_GR2:
                            return ConvertTypes.OBJ
                        elif ALL_WEM: 
                            return ConvertTypes.OGG
                        elif ALL_BLACK:
                            return ConvertTypes.BLACK
                         
                        return ConvertTypes.GENERIC

                    _ctx: str = ctx()

                    sub_menu.addAction("Save selected files").triggered.connect(
                        lambda: self._save_file_dialog(
                            cast(List[EVEFile], items),
                            ConvertTypes.GENERIC,
                            is_multi_select=True,
                        )
                    )
                    if _ctx != ConvertTypes.GENERIC:
                        sub_menu.addSeparator()
                        sub_menu.addAction(
                            f"Save selected as .{_ctx}"
                        ).triggered.connect(
                            lambda: self._save_file_dialog(
                                items, _ctx, is_multi_select=True
                            )
                        )
                else:
                    sub_menu.addAction("Save file").triggered.connect(
                        lambda: self._save_file_dialog(item, ConvertTypes.GENERIC)
                    )
                    sub_menu.addSeparator()
                    if item.text(0).endswith(".gr2"):
                        sub_menu.addSeparator()
                        sub_menu.addAction("Save as .obj").triggered.connect(
                            lambda: self._save_file_dialog(item, ConvertTypes.OBJ)
                        )
                    elif item.text(0).endswith(".dds"):
                        sub_menu.addSeparator()
                        sub_menu.addAction("Save as .png").triggered.connect(
                            lambda: self._save_file_dialog(item, ConvertTypes.PNG)
                        )
                    elif item.text(0).endswith(".wem"):
                        sub_menu.addSeparator()
                        sub_menu.addAction("Save as .ogg").triggered.connect(
                            lambda: self._save_file_dialog(item, ConvertTypes.OGG)
                        )
                    elif item.text(0).endswith(".black"):
                        sub_menu.addSeparator()
                        sub_menu.addAction("Save as .json").triggered.connect(
                            lambda: self._save_file_dialog(item, ConvertTypes.BLACK)
                        )

                menu.addAction(f"{item.filename}").setEnabled(False)

            menu.installEventFilter(ContextMenuFilter(menu))

            vp = self.viewport()
            if vp:
                menu.popup(vp.mapToGlobal(point))


class ContextMenuFilter(QObject):
    def eventFilter(self, context_menu, event):  # type: ignore
        if isinstance(context_menu, QMenu):
            if event.type() == event.Type.MouseButtonPress:  # type: ignore
                if event.button() == Qt.MouseButton.RightButton:  # type: ignore
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
            QApplication.primaryScreen().geometry().center() - self.rect().center()  # type: ignore
        )

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        self.tab_widget: QTabWidget = QTabWidget()

        self.setStyleSheet(STYLE_SHEET)
        self.event_logger = EventLogger()

        self.set_shared_cache_action = QAction("&Set Shared Cache", self)
        self.set_shared_cache_action.triggered.connect(self.set_shared_cache)  # type: ignore
        self.set_shared_cache_action.setEnabled(False)

        self.shared_cache_tq = ResTree(
            self,
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

        self.text_box = QLineEdit()
        self.text_box.setPlaceholderText("Search... ex: af3_t1.gr2, Punisher")
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._search)

        self.pending_query = ""
        self.text_box.textChanged.connect(self._debounce_search)
        self.text_box.returnPressed.connect(self._next_search_item)
        self.search_results = []
        self.search_index = -1

        self.search_label = QLabel("")
        self.search_label.setStyleSheet("font-weight: bold;")

        search_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        search_shortcut.activated.connect(self._search_shortcut)

        main_layout.addWidget(self.tab_widget)
        main_layout.addWidget(self.text_box)
        main_layout.addWidget(self.search_label)

    def _debounce_search(self, search_str: str) -> None:
        self.pending_query = search_str
        self.timer.stop()
        self.timer.start(400)

    def _show_all_items(self, item: Any) -> None:
        item.setHidden(False)
        for i in range(item.childCount()):
            if item:
                self._show_all_items(item.child(i))

    def _filter_items(self, item: EVEFile, search_str: str) -> Union[bool, str]:
        text_lower = item.text(0).lower()
        filename_lower = item.filename.lower()

        aliases: List[Any] = item.data(0, Qt.ItemDataRole.UserRole) or []
        found_alias = next(
            (x for x in aliases if isinstance(x, str) and search_str in x.lower()), None
        )

        found = search_str in text_lower or search_str in filename_lower or found_alias
        found_child = False
        for i in range(item.childCount()):
            found_child = self._filter_items(item.child(i), search_str) or found_child  # type: ignore
        if item.text(0) != "res:":
            item.setHidden(not (found or found_child))
        return found or found_child

    def _search_shortcut(self):
        self.text_box.setFocus()

    def _get_searches(self, item: QTreeWidgetItem, search_str: str) -> List[Any]:
        results: List[QTreeWidgetItem] = []
        aliases: List[Any] = item.data(0, Qt.ItemDataRole.UserRole) or []
        found_alias = next(
            (x for x in aliases if isinstance(x, str) and search_str in x.lower()), None
        )
        if isinstance(item, EVEFile) and (
            found_alias or search_str in item.text(0).lower()
        ):
            results.append(item)

        for i in range(item.childCount()):
            results.extend(self._get_searches(item.child(i), search_str))  # type: ignore

        return list(sorted(results, key=lambda x: len(x.text(0))))

    def _search(self):

        search_str = self.pending_query

        tree = self.tab_widget.currentWidget()
        self.search_label.setText("")
        if not isinstance(tree, ResTree):
            return

        self.search_results.clear()
        self.search_index = -1

        root: Optional[EVEFile] = cast(EVEFile, tree.topLevelItem(0))
        if not root:
            return

        if not search_str:
            self._show_all_items(root)
            tree.collapseAll()
            root.setExpanded(True)
            return

        search_str = search_str.lower()

        self._filter_items(root, search_str)
        self.search_results = self._get_searches(root, search_str)

        if self.search_results:
            self.search_index = 0
            self._select_search_item(tree)
        else:
            tree.clearSelection()
            self.search_index = -1
            self.search_label.setText("")

    def _next_search_item(self):
        tree: QTreeWidget = cast(QTreeWidget, self.tab_widget.currentWidget())
        if not self.search_results:
            self._search()
            return
        self.search_index = (self.search_index + 1) % len(self.search_results)
        self._select_search_item(tree)

    def _select_search_item(self, tree: QTreeWidget):
        item = self.search_results[self.search_index]
        parent = item.parent()
        while parent:
            tree.expandItem(parent)
            parent = parent.parent()
        tree.setCurrentItem(item)
        tree.scrollToItem(item, QTreeWidget.ScrollHint.PositionAtCenter)
        self.search_label.setText(
            f"{self.search_index + 1} of {len(self.search_results)}"
        )

    def set_shared_cache(self) -> Any:
        folder = QFileDialog.getExistingDirectory(
            self, "Path to EVE's SharedCache folder"
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
        # i do this because if you exit while its still loading resfiles
        # the app will persist due to how the loading widget operates
        PROC.stdin.write("\nexit\n")
        PROC.terminate()
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
    def __init__(self, parent: Any):
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
    def __init__(self, files: List[Any], parent: Any):
        super().__init__(parent)
        self.setGeometry(0, 770, 900, 15)
        self.setStyleSheet("border-top: 5px solid #242424;")
        self.setValue(0)
        self.setMaximum(len(files))
        self.show()


class LoadingScreenWindow(QProgressDialog):
    def __init__(self, files: List[Any], stay_on_top: bool = False):
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
        screen = QApplication.primaryScreen()
        if screen:
            self.move(screen.geometry().center() - self.rect().center())
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
        tab_bar = window.tab_widget.tabBar()
        if tab_bar:
            tab_bar.setEnabled(False)
        window.shared_cache_tq.load_resfiles(
            window.shared_cache_tq, window.shared_cache_tq.client
        )
        if tab_bar:
            tab_bar.setEnabled(True)
        sys.exit(app.exec())

    if not args.dev:
        if license_agreement.exec() == QDialog.DialogCode.Accepted:
            show()
    else:
        show()
