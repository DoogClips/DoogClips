import os
import socket
import threading
import shutil
import http.server
import socketserver
import qrcode
import PIL.Image as PILImage
from PyQt6.QtWidgets import QVBoxLayout, QLabel, QPushButton, QComboBox, QHBoxLayout
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtCore import Qt
from doogclips.gui.plugin_base import DoogPlugin
from doogclips.utils.paths import resolve_path

class DoogSyncHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        if hasattr(self, "_content_disp"):
            self.send_header("Content-Disposition", self._content_disp)
        super().end_headers()

    def do_GET(self):
        if "?" not in self.path:
            filename = os.path.basename(self.path)
            if not filename or filename == "/":
                self.send_error(404, "Select a video on PC")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <title>DoogClips Download</title>
                <style>
                    body {{ background: #0f0f1e; color: #fff; font-family: sans-serif; text-align: center; padding: 40px 20px; }}
                    .card {{ background: #1a1a2e; border: 1px solid #3a3a5c; border-radius: 20px; padding: 30px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }}
                    h1 {{ font-size: 24px; font-weight: 900; margin-bottom: 15px; color: #c77dff; }}
                    p {{ color: #88a; font-size: 14px; margin-bottom: 30px; line-height: 1.4; }}
                    .btn {{ 
                        display: inline-block; background: linear-gradient(90deg, #8a2be2, #ff00ff);
                        color: #fff; text-decoration: none; padding: 18px 40px; border-radius: 50px;
                        font-weight: 800; font-size: 18px; box-shadow: 0 4px 15px rgba(255,0,255,0.3);
                    }}
                    .tip {{ margin-top: 40px; font-size: 14px; color: #556; line-height: 1.6; border-top: 1px solid #222; padding-top: 25px; font-weight: bold; }}
                    video {{ width: 100%; border-radius: 12px; margin-bottom: 25px; background: #000; }}
                </style>
            </head>
            <body>
                <div class="card">
                    <h1>Your Clip Is Ready</h1>
                    <p>{filename}</p>
                    <video autoplay muted playsinline loop><source src="/{filename}?view=1" type="video/mp4"></video>
                    <a href="/{filename}?dl=1" class="btn">DOWNLOAD VIDEO</a>
                    <div class="tip">
                        Tap the Download Button To Save The Video To Your Phone.
                    </div>
                </div>
            </body>
            </html>
            """
            self.wfile.write(html.encode('utf-8'))
            return
        if "dl=1" in self.path:
            filename = os.path.basename(self.path.split('?')[0])
            self._content_disp = f'attachment; filename="{filename}"'
        self.path = self.path.split('?')[0]
        super().do_GET()

class PhoneSyncPlugin(DoogPlugin):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.plugin_name = "Send to Phone"
        self.plugin_description = "Share exported videos to your phone over Wi-Fi."
        self.server_thread = None
        self.httpd = None
        self.port = 8000

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        title = QLabel("Send to Phone")
        title.setStyleSheet("font-size: 24px; font-weight: 900; color: #ffffff;")
        layout.addWidget(title)
        desc = QLabel("Scan the QR code to download vids directly to your phone.")
        desc.setStyleSheet("color: #88a; font-size: 14px;")
        layout.addWidget(desc)
        self.file_combo = QComboBox()
        self.file_combo.setObjectName("urlInput")
        self.file_combo.setFixedHeight(45)
        layout.addWidget(self.file_combo)
        refresh_btn = QPushButton("Refresh Video List")
        refresh_btn.setObjectName("secondaryBtn")
        refresh_btn.setFixedHeight(40)
        refresh_btn.clicked.connect(self.refresh_files)
        layout.addWidget(refresh_btn)
        self.qr_label = QLabel()
        self.qr_label.setFixedSize(330, 330)
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label.setStyleSheet("background: #fff; border: 1px solid #2a2a4a; border-radius: 12px;")
        layout.addWidget(self.qr_label, alignment=Qt.AlignmentFlag.AlignCenter)
        self.url_label = QLabel("Server: Stopped")
        self.url_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.url_label.setStyleSheet("color: #7b2fff; font-weight: bold;")
        layout.addWidget(self.url_label)
        sync_btn = QPushButton("Generate QR Code")
        sync_btn.setObjectName("analyzeBtn")
        sync_btn.setFixedHeight(50)
        sync_btn.clicked.connect(self.generate_qr)
        layout.addWidget(sync_btn)
        layout.addStretch()
        self.refresh_files()

    def refresh_files(self):
        self.file_combo.clear()
        path = resolve_path("exports")
        if not os.path.exists(path): os.makedirs(path)
        files = [f for f in os.listdir(path) if f.endswith(".mp4")]
        files.sort(key=lambda x: os.path.getmtime(os.path.join(path, x)), reverse=True)
        self.file_combo.addItems(files)

    def get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except: return "127.0.0.1"

    def start_server(self):
        if self.httpd: return
        path = resolve_path("exports")
        os.chdir(path)
        self.httpd = socketserver.TCPServer(("", self.port), DoogSyncHandler)
        self.server_thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.server_thread.start()

    def stop_server(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None

    def generate_qr(self):
        filename = self.file_combo.currentText()
        if not filename: return
        self.stop_server()
        self.start_server()
        ip = self.get_local_ip()
        url = f"http://{ip}:{self.port}/{filename}"
        qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img = img.convert("RGB")
        data = img.tobytes("raw", "RGB")
        qimg = QImage(data, img.size[0], img.size[1], img.size[0] * 3, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg)
        self.qr_label.setPixmap(pixmap.scaled(280, 280, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.url_label.setText(f"Live at: {url}")

    def on_load(self):
        pass

    def on_unload(self):
        self.stop_server()
