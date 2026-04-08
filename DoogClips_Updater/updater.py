import os
import requests
from PyQt6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar, QMessageBox, QListWidget, QListWidgetItem
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from doogclips.gui.plugin_base import DoogPlugin
from doogclips.utils.paths import resolve_path

REPO_API = "https://api.github.com/repos/DoogClips/DoogClips/contents/"

class SyncWorker(QThread):
    progress = pyqtSignal(str, int)
    finished = pyqtSignal(bool, str)

    def __init__(self, items):
        super().__init__()
        self.items = items

    def run(self):
        try:
            total = len(self.items)
            for i, item in enumerate(self.items):
                name = item['name']
                url = item['download_url']
                path = item['path']
                self.progress.emit(f"Downloading {name}...", int((i / total) * 100))
                res = requests.get(url)
                if res.status_code == 200:
                    local_path = resolve_path(path)
                    os.makedirs(os.path.dirname(local_path), exist_ok=True)
                    with open(local_path, 'wb') as f: f.write(res.content)
                else:
                    self.finished.emit(False, f"Failed to download {name}")
                    return
            self.progress.emit("Update Complete!", 100)
            self.finished.emit(True, "Selected files updated successfully.")
        except Exception as e: self.finished.emit(False, str(e))

class FastUpdater(DoogPlugin):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.plugin_name = "Updater"
        self.plugin_description = "Navigate and download files from GitHub."
        self.repo_data = []
        self.current_path = ""

    def _init_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(30, 30, 30, 30)
        self.layout.setSpacing(15)

        title = QLabel("Cloud File Manager")
        title.setStyleSheet("font-size: 20px; font-weight: 800; color: #ffffff;")
        self.layout.addWidget(title)

        self.info = QLabel("Double-click a folder to enter.")
        self.info.setStyleSheet("color: #8888aa; font-size: 13px;")
        self.layout.addWidget(self.info)

        self.list_widget = QListWidget()
        self.list_widget.setObjectName("urlInput")
        self.list_widget.setFixedHeight(280)
        self.list_widget.setStyleSheet("QListWidget::item { border-bottom: 1px solid #1a1a24; padding: 8px; }")
        self.list_widget.itemDoubleClicked.connect(self.on_item_dc)
        self.layout.addWidget(self.list_widget)

        nav_row = QHBoxLayout()
        self.back_btn = QPushButton("⬅ Back")
        self.back_btn.setObjectName("secondaryBtn")
        self.back_btn.setFixedWidth(100)
        self.back_btn.clicked.connect(self.go_back)
        nav_row.addWidget(self.back_btn)

        self.refresh_btn = QPushButton("🔄 Refresh List")
        self.refresh_btn.setObjectName("secondaryBtn")
        self.refresh_btn.clicked.connect(self.fetch_files)
        nav_row.addWidget(self.refresh_btn)
        self.layout.addLayout(nav_row)

        self.pbar = QProgressBar()
        self.pbar.setFixedHeight(12)
        self.pbar.setValue(0)
        self.pbar.setTextVisible(False)
        self.layout.addWidget(self.pbar)

        self.sync_btn = QPushButton("Download selected files")
        self.sync_btn.setObjectName("primaryBtn")
        self.sync_btn.setFixedHeight(50)
        self.sync_btn.setEnabled(False)
        self.sync_btn.clicked.connect(self.start_sync)
        self.layout.addWidget(self.sync_btn)

        self.layout.addStretch()

    def fetch_files(self):
        self.refresh_btn.setEnabled(False)
        self.list_widget.clear()
        url = REPO_API + self.current_path
        try:
            res = requests.get(url)
            if res.status_code == 200:
                self.repo_data = res.json()
                for item in self.repo_data:
                    display_name = item['name']
                    if item['type'] == 'dir':
                        list_item = QListWidgetItem(f"📁 {display_name}")
                        list_item.setData(Qt.ItemDataRole.UserRole, item)
                    else:
                        size = round(item['size'] / 1024, 1)
                        list_item = QListWidgetItem(f"{display_name} ({size} KB)")
                        list_item.setFlags(list_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                        list_item.setCheckState(Qt.CheckState.Unchecked)
                        list_item.setData(Qt.ItemDataRole.UserRole, item)
                    self.list_widget.addItem(list_item)
                self.info.setText(f"Location: /{self.current_path}")
                self.sync_btn.setEnabled(True)
            else:
                self.info.setText(f"Failed to load: {res.status_code}")
        except Exception as e:
            self.info.setText(f"Error: {str(e)}")
        self.refresh_btn.setEnabled(True)

    def on_item_dc(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
        if data['type'] == 'dir':
            self.current_path = data['path']
            self.fetch_files()

    def go_back(self):
        if self.current_path:
            parts = self.current_path.rstrip('/').split('/')
            self.current_path = '/'.join(parts[:-1])
            self.fetch_files()

    def start_sync(self):
        selected = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(item.data(Qt.ItemDataRole.UserRole))
        if not selected:
            QMessageBox.warning(self, "Selection Required", "Please check at least one file to download.")
            return
        self.sync_btn.setEnabled(False)
        self.worker = SyncWorker(selected)
        self.worker.progress.connect(self.update_status)
        self.worker.finished.connect(self.sync_done)
        self.worker.start()

    def update_status(self, m, v):
        self.info.setText(m)
        self.pbar.setValue(v)

    def sync_done(self, ok, m):
        self.sync_btn.setEnabled(True)
        if ok:
            QMessageBox.information(self, "Success", m)
        else:
            QMessageBox.critical(self, "Sync Issue", m)
