import os
import sys
import subprocess
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QProgressBar,
    QScrollArea, QFrame, QSplitter, QSizePolicy,
    QMessageBox, QStackedWidget, QComboBox, QSpinBox, QCheckBox, QFileDialog,
    QTabWidget, QTextEdit, QPlainTextEdit, QApplication, QDialog, QSlider,
    QInputDialog
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl, QTimer, QPropertyAnimation, QEasingCurve, QPoint
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
try:
    from PyQt6.QtMultimediaWidgets import QVideoWidget
except ImportError:
    QVideoWidget = None
from .styles import STYLESHEET
from .clip_card import ClipCard
from ..utils.paths import resolve_path
try:
    from ..utils.uploader_utils import YouTubeUploader
    HAS_YT = True
except ImportError:
    HAS_YT = False

from dataclasses import dataclass
import time
import random
import json

try:
    import sounddevice as sd
    import soundfile as sf
    from scipy.io.wavfile import write as wav_write
    import numpy as np
    HAS_AUDIO_LIBS = True
except ImportError:
    HAS_AUDIO_LIBS = False

try:
    from ..utils.qwen_tts import QwenTTSManager
    HAS_QWEN = True
except ImportError:
    HAS_QWEN = False

from .plugin_base import DoogPlugin
import importlib.util
import inspect

CLONE_DIR = resolve_path("assets/clones")
PLUGINS_DIR = resolve_path("plugins")
os.makedirs(CLONE_DIR, exist_ok=True)
os.makedirs(PLUGINS_DIR, exist_ok=True)

class RecordingThread(QThread):
    finished = pyqtSignal(str)
    progress = pyqtSignal(int)
    error = pyqtSignal(str)

    def __init__(self, filename, duration=10, fs=44100):
        super().__init__()
        self.filename = filename
        self.duration = duration
        self.fs = fs

    def run(self):
        try:
                                                        
            recording = []
            chunk_size = 1
            for i in range(self.duration):
                chunk = sd.rec(int(chunk_size * self.fs), samplerate=self.fs, channels=1)
                sd.wait()
                recording.append(chunk)
                self.progress.emit(int((i+1) * 100 / self.duration))
            
            audio_data = np.concatenate(recording, axis=0)
            wav_write(self.filename, self.fs, audio_data)
            self.finished.emit(self.filename)
        except Exception as e:
            self.error.emit(str(e))

class DownloadModelThread(QThread):
    progress = pyqtSignal(str, int)
    finished = pyqtSignal(bool)

    def run(self):
        manager = QwenTTSManager.get_instance()
        success = manager.download_model(progress_callback=self.progress.emit)
        
        if success:
            try:
                self.progress.emit("NUCLEAR RESET: Purging broken libraries...", 80)
                import shutil
                                                                          
                try:
                    base_env = os.path.dirname(os.path.dirname(sys.executable))
                    sp_path = os.path.join(base_env, "Lib", "site-packages")
                    
                                                                                 
                                                                                                       
                    for folder in ["torch", "torchvision", "torchaudio", "qwen_tts", "onnxruntime"]:
                        p = os.path.join(sp_path, folder)
                        if os.path.exists(p):
                            shutil.rmtree(p, ignore_errors=True)
                except Exception as wipe_err:
                    print(f"Purge warning: {wipe_err}")

                self.progress.emit("Restoring Stable Torch (2.5.1+cu121)...", 85)
                                                              
                subprocess.check_call([sys.executable, "-m", "pip", "install", "-U", 
                                      "torch==2.5.1+cu121", "torchvision==0.20.1+cu121", "torchaudio==2.5.1+cu121", 
                                      "--index-url", "https://download.pytorch.org/whl/cu121"])
                
                self.progress.emit("Finalizing Studio Safe-Install...", 95)
                subprocess.check_call([sys.executable, "-m", "pip", "install", "-U", "qwen-tts", "--no-deps", "--force-reinstall"])
                
                                                                           
                                                                                         
                subprocess.check_call([sys.executable, "-m", "pip", "install", "-U", "onnxruntime==1.16.3", "static-sox", "numpy<2"])
                
                self.progress.emit("All engines restored!", 100)
            except Exception as e:
                print(f"Library install failed: {e}")
                                                                 
                                                             
        
        self.finished.emit(success)

class CloningThread(QThread):
    finished = pyqtSignal(str)
    progress = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, text, ref_wav, out_wav):
        super().__init__()
        self.text = text
        self.ref_wav = ref_wav
        self.out_wav = out_wav

    def run(self):
        manager = QwenTTSManager.get_instance()
        if not manager.is_model_downloaded():
            self.error.emit("qwen engine missing download it first")
            return
        
        try:
            self.progress.emit("preparing qwen3 studio")
            print("[qwen3] loading weights")
            if not manager.load_model(progress_callback=self.progress.emit):
                self.error.emit("failed to load model weights check console")
                return
            
            self.progress.emit("synthesizing your voice")
            print(f"[qwen3] starting synthesis")
            success = manager.generate_audio(
                text=self.text,
                ref_wav_path=self.ref_wav,
                output_path=self.out_wav
            )
            print(f"[qwen3] synthesis complete")
            if success:
                self.finished.emit(self.out_wav)
            else:
                self.error.emit("synthesis failed check logs")
        except Exception as e:
            self.error.emit(str(e))

class VoiceCard(QFrame):
    delete_requested = pyqtSignal(str)
    play_requested = pyqtSignal(str)
    selected = pyqtSignal(str)

    def __init__(self, name, path, parent=None):
        super().__init__(parent)
        self.name = name
        self.path = path
        self.setObjectName("voiceCard")                         
        self.setFixedHeight(100)                              
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 10)
        
        info_layout = QVBoxLayout()
        name_lbl = QLabel(name)
        name_lbl.setStyleSheet("font-weight: bold; font-size: 15px; color: #ffffff;")
        info_layout.addWidget(name_lbl)
        
        type_lbl = QLabel("Local Clone")
        type_lbl.setStyleSheet("color: #8888aa; font-size: 12px;")
        info_layout.addWidget(type_lbl)
        layout.addLayout(info_layout, 1)
        
        self.play_btn = QPushButton("▶️")
        self.play_btn.setFixedSize(56, 56)
        self.play_btn.setObjectName("openFolderBtn")
        self.play_btn.setStyleSheet("font-size: 20px;")
        self.play_btn.clicked.connect(lambda: self.play_requested.emit(self.path))
        layout.addWidget(self.play_btn)
        
        self.del_btn = QPushButton("❌")
        self.del_btn.setFixedSize(56, 56)
        self.del_btn.setObjectName("openFolderBtn")
        self.del_btn.setStyleSheet("background: #331111; color: #ff6666; font-size: 20px;")
        self.del_btn.clicked.connect(lambda: self.delete_requested.emit(self.path))
        layout.addWidget(self.del_btn)
        
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        self.selected.emit(self.path)
        super().mousePressEvent(event)

class VoiceCloningTab(QWidget):
    cloned_ready = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_win = parent
        self.setAcceptDrops(True)
        
        if hasattr(parent, 'register_voice_tab'):
            parent.register_voice_tab(self)
        
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.audio_output.setVolume(1.0)
        self.player.setAudioOutput(self.audio_output)
        
        self.rec_thread = None
        self.clone_thread = None
        self.dl_thread = None
        self.zip_thread = None                     
        self.ref_path = ""                             
        self.test_path = os.path.join(CLONE_DIR, "test_voice.wav")

        self._init_ui()
        self._refresh_gallery()

        if not HAS_AUDIO_LIBS:
            self._disable_for_missing_libs()

    def _disable_for_missing_libs(self):
        self.rec_btn.setEnabled(False)
        self.rec_btn.setText("❌ Audio Libraries Missing")
        self.test_btn.setEnabled(False)
        self.status_lbl.setText("Error: Run 'pip install sounddevice soundfile scipy' to enable voice cloning.")

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(25)

                                      
        header_row = QHBoxLayout()
        header_title = QLabel("Voice Cloning Studio")
        header_title.setObjectName("titleLabel")
        header_row.addWidget(header_title)
        header_row.addStretch()
        
        self.cleanup_btn = QPushButton("🧹 Prepare for Zip")
        self.cleanup_btn.setObjectName("openFolderBtn")
        self.cleanup_btn.setFixedWidth(140)
        self.cleanup_btn.setFixedHeight(34)
        self.cleanup_btn.clicked.connect(self._prep_dist_for_zip)
        header_row.addWidget(self.cleanup_btn)
        layout.addLayout(header_row)

                          
        dl_box = QFrame()
        dl_box.setObjectName("clipCard")
        dl_box.setFixedHeight(120)
        dl_layout = QVBoxLayout(dl_box)
        
        dl_top = QHBoxLayout()
        dl_info = QLabel("Qwen3-TTS Engine (3.5GB)")
        dl_info.setStyleSheet("font-weight: bold; font-size: 14px;")
        dl_top.addWidget(dl_info)
        dl_top.addStretch()
        
        self.dl_btn = QPushButton("Download Qwen Engine")
        self.dl_btn.setFixedWidth(250)
        self.dl_btn.setFixedHeight(40)
        self.dl_btn.setObjectName("exportBtn")
        self.dl_btn.clicked.connect(self._start_download)
        dl_top.addWidget(self.dl_btn)
        dl_layout.addLayout(dl_top)
        
        self.dl_prog = QProgressBar()
        self.dl_prog.setFixedHeight(8)
        self.dl_prog.setValue(0)
        self.dl_prog.setTextVisible(False)
        dl_layout.addWidget(self.dl_prog)
        
        self.dl_status = QLabel("Engine not installed. High-quality cloning requires this download.")
        self.dl_status.setStyleSheet("color: #8888aa; font-size: 12px;")
        dl_layout.addWidget(self.dl_status)
        layout.addWidget(dl_box)

                               
        layout.addWidget(QLabel("YOUR VOICES (Drag & Drop .wav/.mp3 here):"))
        
        self.gallery_scroll = QScrollArea()
        self.gallery_scroll.setWidgetResizable(True)
        self.gallery_scroll.setFixedHeight(300)
        self.gallery_scroll.setObjectName("urlInput")                       
        self.gallery_container = QWidget()
        self.gallery_layout = QVBoxLayout(self.gallery_container)
        self.gallery_layout.setContentsMargins(10, 10, 10, 10)
        self.gallery_layout.setSpacing(10)
        self.gallery_layout.addStretch()
        self.gallery_scroll.setWidget(self.gallery_container)
        layout.addWidget(self.gallery_scroll)

                           
        test_section = QVBoxLayout()
        test_section.setSpacing(15)
        test_section.addWidget(QLabel("TEST SELECTED VOICE:"))
        
        test_row = QHBoxLayout()
        self.test_text = QLineEdit("Hello, I am testing my new Qwen3 cloned voice.")
        self.test_text.setObjectName("urlInput")
        self.test_text.setFixedHeight(44)
        
        self.test_btn = QPushButton("Generate Test")
        self.test_btn.setObjectName("exportBtn")
        self.test_btn.setFixedHeight(44)
        self.test_btn.setFixedWidth(150)
        self.test_btn.clicked.connect(self._start_test_cloning)
        
        test_row.addWidget(self.test_text, 1)
        test_row.addWidget(self.test_btn)
        test_section.addLayout(test_row)
        
        self.play_test_btn = QPushButton("Play Test Result")
        self.play_test_btn.setObjectName("openFolderBtn")
        self.play_test_btn.setFixedHeight(44)
        self.play_test_btn.setEnabled(False)
        self.play_test_btn.clicked.connect(lambda: self._play_audio(self.test_path))
        test_section.addWidget(self.play_test_btn)
        
        self.status_lbl = QLabel("Ready")
        self.status_lbl.setObjectName("statusLabel")
        test_section.addWidget(self.status_lbl)
        
        layout.addLayout(test_section)
        layout.addStretch()
        
        scroll.setWidget(container)
        main_layout.addWidget(scroll)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if file_path.lower().endswith(('.wav', '.mp3')):
                self._on_voice_dropped(file_path)
                break

    def _on_voice_dropped(self, file_path):
        name, ok = QInputDialog.getText(self, "New Voice", "Enter a name for this voice:")
        if ok and name.strip():
            safe_name = "".join(c for c in name if c.isalnum() or c in " _-").strip()
            dest = os.path.join(CLONE_DIR, f"{safe_name}.wav")
            try:
                import shutil
                shutil.copy(file_path, dest)
                self._refresh_gallery()
                if hasattr(self.parent_win, '_update_voice_dropdowns'):
                    self.parent_win._update_voice_dropdowns()
                QMessageBox.information(self, "Success", f"Voice '{name}' created!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save voice: {e}")

    def _refresh_gallery(self):
                        
        for i in reversed(range(self.gallery_layout.count())):
            item = self.gallery_layout.itemAt(i)
            if item.widget():
                item.widget().deleteLater()
        
                               
        has_voices = False
        for f in os.listdir(CLONE_DIR):
            if f.endswith(".wav") and f != "test_voice.wav":
                has_voices = True
                path = os.path.join(CLONE_DIR, f)
                name = os.path.splitext(f)[0].replace("_", " ").title()
                card = VoiceCard(name, path)
                card.selected.connect(self._select_voice)
                card.play_requested.connect(self._play_audio)
                card.delete_requested.connect(self._delete_voice)
                self.gallery_layout.insertWidget(0, card)
        
        if not has_voices:
            empty = QLabel("No voices yet. Drag & Drop an audio file here.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("color: #6666aa; margin-top: 40px;")
            self.gallery_layout.insertWidget(0, empty)
            
        self.gallery_layout.addStretch()

    def _select_voice(self, path):
        self.ref_path = path
        self.status_lbl.setText(f"Active: {os.path.basename(path)}")
                                                 
        for i in range(self.gallery_layout.count()):
            w = self.gallery_layout.itemAt(i).widget()
            if isinstance(w, VoiceCard):
                if w.path == path:
                    w.setProperty("selected", "true")
                else:
                    w.setProperty("selected", "false")
                w.style().unpolish(w)
                w.style().polish(w)

    def _delete_voice(self, path):
        if os.path.exists(path):
            reply = QMessageBox.question(self, "Delete", f"Delete voice {os.path.basename(path)}?", 
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                os.remove(path)
                if self.ref_path == path: self.ref_path = ""
                self._refresh_gallery()
                if hasattr(self.parent_win, '_update_voice_dropdowns'):
                    self.parent_win._update_voice_dropdowns()

    def _start_download(self):
        self.dl_btn.setEnabled(False)
        self.dl_status.setText("Starting Qwen3 download...")
        self.dl_thread = DownloadModelThread()
        self.dl_thread.progress.connect(self._on_download_prog)
        self.dl_thread.finished.connect(self._on_download_finished)
        self.dl_thread.start()

    def _on_download_prog(self, msg, pct):
        self.dl_status.setText(msg)
        self.dl_prog.setValue(pct)

    def _on_download_finished(self, success):
        self.dl_btn.setEnabled(True)
        if success:
            self.dl_status.setText("Qwen3 Engine ready!")
            self.dl_prog.setValue(100)
            QMessageBox.information(self, "Success", "Qwen3 Engine has been downloaded and installed!")
        else:
            self.dl_status.setText("Download failed. Check connection.")
            QMessageBox.critical(self, "Error", "Failed to download model files.")

    def _start_recording(self):
        self.rec_btn.setEnabled(False)
        self.rec_btn.setText("⏺ Recording...")
        self.rec_thread = RecordingThread(self.ref_path)
        self.rec_thread.finished.connect(self._on_rec_finished)
        self.rec_thread.start()

    def _on_rec_finished(self, path):
        self.rec_btn.setEnabled(True)
        self.rec_btn.setText("🔴 Re-Record Voice")
        self.play_ref_btn.setEnabled(True)
        QMessageBox.information(self, "Success", "Recording complete!")

    def _upload_reference(self):
        file, _ = QFileDialog.getOpenFileName(self, "Select Voice Sample", os.path.expanduser("~/Downloads"), "Audio Files (*.wav *.mp3)")
        if file:
            try:
                import shutil
                shutil.copy(file, self.ref_path)
                QMessageBox.information(self, "Success", f"Voice reference updated with: {os.path.basename(file)}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to copy file: {e}")

    def _prep_dist_for_zip(self):
        msg = "Cleaning all private files, press ok to proceed. (This deletes everything, dont touch unless youre aware)"
        reply = QMessageBox.warning(self, "build master zip", msg,
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                import shutil
                                                   
                root_nuke = [
                    "license.key", "setup_piper.py", "pv.mp3", "test_whisper.py",
                    "gen_key.py", "installer.py", "client_secrets.json", "token.pickle", 
                    "GEN_HUMANIZER_SAMPLES.bat", "gen_samples.py", "humanizer_debug.txt",
                    "Update", "Update.zip", "dev_test.py", "build_log.txt", "DoogClips_v7_Portable.zip",
                    "repair_exports.py", "import_history.py", "tests", ".pytest_cache", ".git"
                ]
                for f in root_nuke:
                    p = resolve_path(f)
                    if os.path.exists(p):
                        try: 
                            if os.path.isdir(p): shutil.rmtree(p, ignore_errors=True)
                            else: os.remove(p)
                        except: pass
                
                                                   
                                          
                                                   
                for folder in ["models", "assets/clones", "assets/bgm", "downloads", "exports", "temp", "piper"]:
                    pdir = resolve_path(folder)
                    if os.path.exists(pdir):
                        if folder in ["piper", "temp", "models"]:
                                                     
                            shutil.rmtree(pdir, ignore_errors=True)
                        else:
                                                                
                            for f in os.listdir(pdir):
                                fp = os.path.join(pdir, f)
                                try:
                                    if os.path.isfile(fp): os.remove(fp)
                                    elif os.path.isdir(fp): shutil.rmtree(fp, ignore_errors=True)
                                except: pass

                                       
                h_path = resolve_path("doogclips/data/history.json")
                if os.path.exists(h_path):
                    try:
                        with open(h_path, 'w') as f: f.write("{}")
                    except: pass

                                              
                root_dir = resolve_path(".")
                for root, dirs, files in os.walk(root_dir):
                    if "__pycache__" in dirs:
                        shutil.rmtree(os.path.join(root, "__pycache__"), ignore_errors=True)
                    for f in files:
                        if f.endswith((".bak", ".log", ".tmp", ".pyc")):
                            try: os.remove(os.path.join(root, f))
                            except: pass
                
                             
                self.status_lbl.setText("status: ready to zip")
                QMessageBox.information(self, "success", "Ready to zip")
                
            except Exception as e:
                QMessageBox.critical(self, "error", f"cleanup failed {e}")

    def _start_test_cloning(self):
        text = self.test_text.text().strip()
        if not text: return
        self.test_btn.setEnabled(False)
        self.status_lbl.setText("status: synthesizing...")
        self.clone_thread = CloningThread(text, self.ref_path, self.test_path)
        self.clone_thread.finished.connect(self._on_clone_finished)
        self.clone_thread.error.connect(self._on_clone_error)
        self.clone_thread.start()

    def _on_clone_finished(self, path):
        self.test_btn.setEnabled(True)
        self.play_test_btn.setEnabled(True)
        self.status_lbl.setText("status: success")
        self._play_audio(path)

    def _on_clone_error(self, err_msg):
        self.test_btn.setEnabled(True)
        self.status_lbl.setText(f"error: {err_msg}")
        QMessageBox.critical(self, "synthesis error", f"failed to synthesize voice clone\n\n{err_msg}")

    def _play_audio(self, path):
        if not os.path.exists(path): return
        self.player.setSource(QUrl.fromLocalFile(os.path.abspath(path)))
        self.player.play()

class AnalysisThread(QThread):
    progress = pyqtSignal(str, int)
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, url, mc, min_d, max_d, color, gp, bg, bgc, bgm, bgmc, fsz, max_w, style, color2, font_fam, stroke_w, glow, use_slide, emoji, pbar, bgm_volume=0.15, speaker_colors=None, track_strength=100, use_facecam=False, custom_title="", use_gpu=True):
        super().__init__()
        self.url = url
        self.mc = mc
        self.min_d = min_d
        self.max_d = max_d
        self.color = color
        self.gp = gp
        self.bg = bg
        self.bgc = bgc
        self.bgm = bgm
        self.bgmc = bgmc
        self.fsz = fsz
        self.max_w = max_w
        self.style = style
        self.color2 = color2
        self.font_fam = font_fam
        self.stroke_w = stroke_w
        self.glow = glow
        self.use_slide = use_slide
        self.emoji = emoji
        self.pbar = pbar
        self.bgm_volume = bgm_volume
        self.speaker_colors = speaker_colors
        self.track_strength = track_strength
        self.use_facecam = use_facecam
        self.custom_title = custom_title
        self.use_gpu = use_gpu

    def run(self):
        try:
            from doogclips.pipeline import run_pipeline
            res = run_pipeline(
                self.url,
                progress_cb=lambda msg, pct: self.progress.emit(msg, pct),
                max_clips=self.mc,
                min_duration=self.min_d,
                max_duration=self.max_d,
                subtitle_color=self.color,
                use_gameplay=self.gp,
                bg_type=self.bg,
                bg_custom=self.bgc,
                bgm_type=self.bgm,
                bgm_custom=self.bgmc,
                font_size=self.fsz,
                max_words=self.max_w,
                style=self.style,
                secondary_color=self.color2,
                font_family=self.font_fam,
                stroke_width=self.stroke_w,
                use_glow=self.glow,
                use_slide=self.use_slide,
                enable_emojis=self.emoji,
                show_progress_bar=self.pbar,
                bgm_volume=self.bgm_volume,
                speaker_colors=self.speaker_colors,
                track_strength=self.track_strength,
                use_facecam=self.use_facecam,
                custom_hook_title=self.custom_title,
                use_gpu=self.use_gpu
            )
            self.finished.emit(res)
        except Exception as e:
            import traceback
            self.error.emit(str(e) + "\n\n" + traceback.format_exc())

class RedditThread(QThread):
    progress = pyqtSignal(str, int)
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, title, story, bg_type, bg_custom, bgm_type, bgm_custom, color, fsz, max_w, sub, vid, cust_aud, style, color2, font_fam, stroke_w, glow, use_slide, emoji, pbar, voice_rate="+0%", out_path=None, use_dropdown=False, use_dropdown_comment=False, use_top_comment=True, post_meta=None, comment_data=None, subreddit_icon_url=None, post_id=None, whisper_engine="Quality (Large-v3)", bgm_volume=0.15, fast_mode=False, use_gpu=True):
        super().__init__()
        self.title = title
        self.story = story
        self.bg_type = bg_type
        self.bg_custom = bg_custom
        self.bgm_type = bgm_type
        self.bgm_custom = bgm_custom
        self.color = color
        self.font_sz = fsz
        self.mw = max_w
        self.sub = sub
        self.vid = vid
        self.cust_aud = cust_aud
        self.style = style
        self.color2 = color2
        self.font_fam = font_fam
        self.stroke_w = stroke_w
        self.glow = glow
        self.use_slide = use_slide
        self.emoji = emoji
        self.pbar = pbar
        self.voice_rate = voice_rate
        self.out_path = out_path
        self.use_dropdown = use_dropdown
        self.use_dropdown_comment = use_dropdown_comment
        self.use_top_comment = use_top_comment
        self.post_meta = post_meta
        self.comment_data = comment_data
        self.subreddit_icon_url = subreddit_icon_url
        self.post_id = post_id
        self.whisper_engine = whisper_engine
        self.bgm_volume = bgm_volume
        self.fast_mode = fast_mode
        self.use_gpu = use_gpu
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            from doogclips.reddit_pipeline import create_reddit_clip
            from doogclips.pipeline import EXPORTS_DIR
            import time
            final_out = self.out_path
            if not final_out:
                safe_name = "".join(c for c in self.title[:100] if c.isalnum() or c in " _-").strip().replace(" ", "_")
                if not safe_name: safe_name = "reddit_clip"
                final_out = os.path.join(EXPORTS_DIR, f"{safe_name}_{int(time.time())}.mp4")

            res = create_reddit_clip(
                self.title, self.story, final_out,
                subreddit=self.sub,
                progress_cb=lambda msg, pct: self.progress.emit(msg, pct),
                bg_type=self.bg_type,
                bg_custom=self.bg_custom,
                bgm_type=self.bgm_type,
                bgm_custom=self.bgm_custom,
                subtitle_color=self.color,
                font_size=self.font_sz,
                max_words=self.mw,
                voice_id=self.vid,
                custom_audio_path=self.cust_aud,
                style=self.style,
                secondary_color=self.color2,
                font_family=self.font_fam,
                stroke_width=self.stroke_w,
                use_glow=self.glow,
                use_slide=self.use_slide,
                enable_emojis=self.emoji,
                show_progress_bar=self.pbar,
                voice_rate=self.voice_rate,
                use_dropdown=self.use_dropdown,
                use_dropdown_comment=self.use_dropdown_comment,
                use_top_comment=self.use_top_comment,
                post_meta=self.post_meta,
                comment_data=self.comment_data,
                subreddit_icon_url=self.subreddit_icon_url,
                post_id=self.post_id,
                whisper_engine=self.whisper_engine,
                bgm_volume=self.bgm_volume,
                fast_mode=self.fast_mode
            )
            
            if res:
                self.finished.emit([res] if isinstance(res, str) else res)
            else:
                self.error.emit("Cancelled")
        except Exception as e:
            import traceback
            self.error.emit(str(e) + "\n\n" + traceback.format_exc())

class CaptioningThread(QThread):
    progress = pyqtSignal(str, int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, video_path, color, fsz, max_w, style, color2, font_fam, stroke_w, glow, use_slide, emoji, pbar, out_path, script=""):
        super().__init__()
        self.video_path = video_path
        self.color = color
        self.font_sz = fsz
        self.mw = max_w
        self.style = style
        self.color2 = color2
        self.font_fam = font_fam
        self.stroke_w = stroke_w
        self.glow = glow
        self.use_slide = use_slide
        self.emoji = emoji
        self.pbar = pbar
        self.out_path = out_path
        self.script = script
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            from doogclips.pipeline import create_standalone_captioned_video
            res = create_standalone_captioned_video(
                self.video_path, self.out_path,
                progress_cb=lambda msg, pct: self.progress.emit(msg, pct),
                subtitle_color=self.color, font_size=self.font_sz, max_words=self.mw,
                style=self.style, secondary_color=self.color2,
                font_family=self.font_fam, stroke_width=self.stroke_w,
                use_glow=self.glow, use_slide=self.use_slide,
                enable_emojis=self.emoji, show_progress_bar=self.pbar,
                cancel_cb=lambda: self._is_cancelled,
                script=self.script
            )
            if res:
                self.finished.emit(res)
            else:
                self.error.emit("Cancelled")
        except Exception as e:
            import traceback
            self.error.emit(str(e) + "\n\n" + traceback.format_exc())


class CaptioningTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_win = parent
        self.cap_thread = None
        
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        
        self._init_ui()
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)
        
        title = QLabel("Add Captions to Premade Video")
        title.setObjectName("titleLabel")
        layout.addWidget(title)
        
        info = QLabel("Select a video from your PC and press the Add captions button when youre ready.")
        info.setStyleSheet("color: #6666aa; font-size: 14px;")
        layout.addWidget(info)
        
                      
        self.script_input = QPlainTextEdit()
        self.script_input.setPlaceholderText("Paste your script here (helps with transcription accuracy)...")
        self.script_input.setMaximumHeight(100)
        self.script_input.setObjectName("urlInput")
        layout.addWidget(self.script_input)
        
                        
        file_row = QHBoxLayout()
        self.video_input = QLineEdit()
        self.video_input.setObjectName("urlInput")
        self.video_input.setPlaceholderText("Paste video path or click Browse...")
        self.video_input.setFixedHeight(44)
        self.browse_btn = QPushButton("Browse")
        self.browse_btn.setObjectName("openFolderBtn")
        self.browse_btn.setFixedHeight(44)
        self.browse_btn.clicked.connect(self._browse_video)
        file_row.addWidget(self.video_input, 1)
        file_row.addWidget(self.browse_btn)
        layout.addLayout(file_row)
        
                             
        self.status = QLabel("Ready")
        self.status.setObjectName("statusLabel")
        layout.addWidget(self.status)
        
        self.prog = QProgressBar()
        self.prog.setFixedHeight(12)
        self.prog.setValue(0)
        layout.addWidget(self.prog)
        
                         
        btn_row = QHBoxLayout()
        self.start_btn = QPushButton("Add Captions")
        self.start_btn.setObjectName("analyzeBtn")
        self.start_btn.setFixedHeight(50)
        self.start_btn.clicked.connect(self._start_captioning)
        
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setObjectName("openFolderBtn")
        self.stop_btn.setFixedHeight(50)
        self.stop_btn.setFixedWidth(100)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_captioning)
        
        btn_row.addWidget(self.start_btn, 1)
        btn_row.addWidget(self.stop_btn)
        layout.addLayout(btn_row)
        
                       
        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumHeight(350)
        self.video_widget.setStyleSheet("background: black; border-radius: 10px;")
        layout.addWidget(self.video_widget, 1)
        self.player.setVideoOutput(self.video_widget)
        
        layout.addStretch()

    def _browse_video(self):
        file, _ = QFileDialog.getOpenFileName(self, "Select Video", "", "Video Files (*.mp4 *.mov *.avi *.mkv)")
        if file:
            self.video_input.setText(file)

    def _start_captioning(self):
        v_path = self.video_input.text().strip()
        if not v_path or not os.path.exists(v_path):
            QMessageBox.warning(self, "Error", "Please select a valid video file!")
            return
            
                                     
        mw = self.parent_win
        color = mw.COLORS.get(mw.color_combo.currentText(), (255, 220, 0))
        color2 = mw.COLORS.get(mw.color2_combo.currentText(), (255, 255, 255))
        style = mw.style_combo.currentText()
        font_fam = mw._resolve_font_path()
        fsz = mw.font_spin.value()
        stroke_w = mw.stroke_spin.value()
        glow = mw.glow_chk.isChecked()
        use_slide = mw.slide_chk.isChecked()
        emoji = mw.emoji_chk.isChecked()
        pbar = mw.pbar_chk.isChecked()
        
        mwords = mw.words_combo.currentText()
        if mwords == "Automax": max_w = 4
        else: max_w = int(mwords.split(" ")[0])
        
                            
        import time
        base = os.path.basename(v_path).rsplit(".", 1)[0]
        out_path = resolve_path(f"exports/{base}_captioned_{int(time.time())}.mp4")
        
        script_text = self.script_input.toPlainText().strip()
        
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.prog.setValue(0)
        self.status.setText("Initializing...")
        
                                           
        try:
            import json
            from doogclips.utils.ollama_helper import generate_viral_title, is_ollama_running
            from doogclips.utils.reddit_utils import format_title_for_display
            
            final_title = format_title_for_display(script_text[:100])
            if is_ollama_running():
                ai_title = generate_viral_title(final_title, script_text)
                if ai_title: final_title = ai_title
                
            meta_path = out_path.replace(".mp4", ".json")
            with open(meta_path, "w") as f:
                json.dump({"title": final_title}, f)
        except: pass
        
        self.cap_thread = CaptioningThread(v_path, color, fsz, max_w, style, color2, font_fam, stroke_w, glow, use_slide, emoji, pbar, out_path, script=script_text)
        self.cap_thread.progress.connect(self._on_prog)
        self.cap_thread.finished.connect(self._on_done)
        self.cap_thread.error.connect(self._on_err)
        self.cap_thread.start()

    def _stop_captioning(self):
        if self.cap_thread and self.cap_thread.isRunning():
            self.cap_thread.cancel()
            self.status.setText("Stopping...")
            self.stop_btn.setEnabled(False)

    def _on_prog(self, msg, pct):
        self.status.setText(msg)
        self.prog.setValue(pct)

    def _on_done(self, out):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.prog.setValue(100)
        self.status.setText("Done!")
        if os.path.exists(out):
            self.player.setSource(QUrl.fromLocalFile(os.path.abspath(out)))
            self.player.play()

    def _on_err(self, err):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.prog.setValue(0)
        if err == "Cancelled":
            self.status.setText("Cancelled")
        else:
            self.status.setText("Error!")
            QMessageBox.critical(self, "Error", err)


class BulkRedditThread(QThread):
    progress = pyqtSignal(str, int)                                         
    batch_progress = pyqtSignal(int, int)                   
    log = pyqtSignal(str)
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, urls, bg_settings, font_settings, voice_settings, use_dropdown=False, use_dropdown_comment=False, use_top_comment=True, whisper_engine="Base", voice_rate="+0%"):
        super().__init__()
        self.urls = urls
        self.bg_settings = bg_settings
        self.font_settings = font_settings
        self.voice_settings = voice_settings
        self.use_dropdown = use_dropdown
        self.use_dropdown_comment = use_dropdown_comment
        self.use_top_comment = use_top_comment
        self.whisper_engine = whisper_engine
        self.voice_rate = voice_rate
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        from doogclips.reddit_pipeline import create_reddit_clip, scrape_reddit_post
        import time
        
        results = []
        total = len(self.urls)
        
        for i, url in enumerate(self.urls):
            if self._is_cancelled:
                self.log.emit("Batch cancelled by user.")
                break
                
            url = url.strip()
            if not url: continue
            
            self.batch_progress.emit(i, total)
            self.log.emit(f"[{i+1}/{total}] Processing: {url}")
            
            try:
                        
                post = scrape_reddit_post(url)
                title = post["title"]
                story = post["story"]
                sub = post["subreddit"]
                post_id = post.get("id")
                post_meta = {
                    "author": post.get("author"),
                    "created_utc": post.get("created_utc"),
                    "score": post.get("score"),
                    "num_comments": post.get("num_comments")
                }
                comment_data = post.get("comment")
                sub_icon = post.get("sub_icon")
                
                            
                safe_name = "".join(c for c in title[:100] if c.isalnum() or c in " _-").strip().replace(" ", "_")
                if not safe_name: safe_name = "bulk_clip"
                out_path = resolve_path(f"exports/{safe_name}_{int(time.time())}.mp4")
                
                                                                  
                try:
                    import json
                    from doogclips.utils.ollama_helper import generate_viral_title, is_ollama_running
                    from doogclips.utils.reddit_utils import format_title_for_display
                    
                    final_title = format_title_for_display(title)
                    if is_ollama_running():
                        ai_title = generate_viral_title(title, story)
                        if ai_title: final_title = ai_title
                        
                    meta_path = out_path.replace(".mp4", ".json")
                    with open(meta_path, "w") as f:
                        json.dump({"title": final_title}, f)
                except: pass
                
                          
                res = create_reddit_clip(
                    title, story, out_path,
                    subreddit=sub,
                    progress_cb=lambda msg, pct: self.progress.emit(f"Clip {i+1}: {msg}", pct),
                    bg_type=self.bg_settings['type'],
                    bg_custom=self.bg_settings['custom'],
                    bgm_type=self.bg_settings['bgm_type'],
                    bgm_custom=self.bg_settings['bgm_custom'],
                    subtitle_color=self.font_settings['color1'],
                    font_size=self.font_settings['size'],
                    max_words=self.font_settings['mw'],
                    voice_id=self.voice_settings['id'],
                    custom_audio_path=self.voice_settings['custom_path'],
                    style=self.font_settings['style'],
                    secondary_color=self.font_settings['color2'],
                    font_family=self.font_settings['family'],
                    stroke_width=self.font_settings['stroke'],
                    use_glow=self.font_settings['glow'], use_slide=self.font_settings['use_slide'],
                    enable_emojis=self.font_settings.get('emoji', False),
                    show_progress_bar=self.font_settings.get('pbar', False),
                    voice_rate=self.voice_rate,
                    use_dropdown=self.use_dropdown,
                    use_dropdown_comment=self.use_dropdown_comment,
                    use_top_comment=self.use_top_comment,
                    post_meta=post_meta,
                    comment_data=comment_data,
                    subreddit_icon_url=sub_icon,
                    post_id=post_id,
                    whisper_engine=self.whisper_engine,
                    bgm_volume=self.bg_settings.get('bgm_volume', 0.15)
                )
                
                if isinstance(res, list):
                    results.extend(res)
                else:
                    results.append(out_path)
                self.log.emit(f"SUCCESS: Created {len(res) if isinstance(res, list) else 1} file(s).")
                
            except Exception as e:
                self.log.emit(f"ERROR on {url}: {str(e)}")
                continue
                
        self.batch_progress.emit(total, total)
        self.finished.emit(results)


class YoutubePosterThread(QThread):
    progress = pyqtSignal(str, int)
    log = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, folder_path, interval_mins, template_title, template_desc):
        super().__init__()
        self.folder_path = folder_path
        self.interval = interval_mins * 60
        self.template_title = template_title
        self.template_desc = template_desc
        self._is_cancelled = False
        if HAS_YT:
            self.uploader = YouTubeUploader("client_secrets.json")
        else:
            self.uploader = None

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        if not HAS_YT:
            self.error.emit("YouTube libraries are not installed. Please run pip install -r requirements.txt")
            return
        try:
            self.uploader.authenticate()
            self.log.emit("[YouTube] Authentication successful.")
        except Exception as e:
            self.error.emit(f"Auth failed: {str(e)}")
            return

        while not self._is_cancelled:
                                 
            files = [f for f in os.listdir(self.folder_path) if f.lower().endswith(('.mp4', '.mov', '.mkv'))]
            if not files:
                self.log.emit("[YouTube] No videos left in folder. Stopping...")
                break

            target_file = os.path.join(self.folder_path, files[0])
            meta_file = target_file.replace(".mp4", ".json")
            
            base_name = None
            if os.path.exists(meta_file):
                try:
                    import json
                    with open(meta_file, "r") as f:
                        meta = json.load(f)
                        base_name = meta.get("title")
                        self.log.emit(f"[YouTube] Found metadata for {files[0]}.")
                except: pass
            
            if not base_name:
                def clean_title(name):
                    import re
                                                               
                    name = os.path.splitext(name)[0]
                    
                                                                     
                    name = re.sub(r'_\d{5,}$', '', name)
                    
                                                                                
                    def format_money(match):
                        val = match.group(0)
                                                             
                        if len(val) >= 4 and val not in ["2022", "2023", "2024", "2025"]:
                            try:
                                num = int(val.replace("$", "").replace(",", ""))                     
                                return f"${num:,}"
                            except: return val
                        return val
                    
                                                                                       
                    name = re.sub(r'(?<=_|^)\d{3,}(?=_|$)', format_money, name)

                                                     
                    replacements = {
                        "_as_long_as_you_": ", But You Need to ",
                        "_if_": ", If ",
                        "_but_": ", But ",
                        "_or_": ", Or ",
                    }
                    for old, new in replacements.items():
                        if old in name:
                            name = name.replace(old, new)
                    
                    parts = name.split("_")
                    formatted = []
                    short_words = ["a", "an", "the", "and", "but", "or", "for", "nor", "on", "at", "to", "from", "by", "with", "in", "of"]
                    for i, p in enumerate(parts):
                        if not p: continue
                                                                                  
                        if p.startswith("$"):
                            formatted.append(p)
                            continue
                            
                        if i == 0 or p.lower() not in short_words or (formatted and formatted[-1].endswith(",")):
                            formatted.append(p.capitalize())
                        else:
                            formatted.append(p.lower())
                    
                    res = " ".join(formatted).replace(" ,", ",").strip()
                                            
                    for suffix in [" One Item", " Life"]:
                        if res.endswith(suffix):
                            res = res[:-(len(suffix))]
                    return res[:100]

                base_name = clean_title(files[0])
            
                              
            if self.template_title.strip():
                title = self.template_title.replace("{filename}", base_name)
            else:
                title = base_name
                
            if self.template_desc.strip():
                desc = self.template_desc.replace("{filename}", base_name)
            else:
                desc = base_name
            
            self.log.emit(f"[YouTube] Uploading: {files[0]}...")
            
            try:
                def prog_cb(pct):
                    self.progress.emit(f"Uploading {files[0]} ({pct}%)", pct)
                
                success = self.uploader.upload_video(
                    target_file, title, desc,
                    progress_callback=prog_cb
                )
                
                if success:
                    self.log.emit(f"[SUCCESS] Posted: {title}")
                                              
                    try:
                        os.remove(target_file)
                        if os.path.exists(meta_file): os.remove(meta_file)
                        self.log.emit(f"[YouTube] Deleted local file: {files[0]}")
                    except: pass
                else:
                    self.log.emit(f"[YouTube] Upload failed for {files[0]}")
            except Exception as e:
                self.log.emit(f"[ERROR] {str(e)}")

            if self._is_cancelled: break
            
                               
            self.log.emit(f"[YouTube] Waiting {self.interval // 60} minutes for next post...")
            for _ in range(self.interval):
                if self._is_cancelled: break
                time.sleep(1)

        self.finished.emit()


class YoutubePosterTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_win = parent
        self.poster_thread = None
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(25)

        hdr = QLabel("YouTube Shorts Poster")
        hdr.setObjectName("titleLabel")
        layout.addWidget(hdr)

        desc = QLabel("Pick a folder full of videos. Set a schedule. We'll post them one by one and delete them once finished.")
        desc.setObjectName("subtitleLabel")
        layout.addWidget(desc)

                       
        folder_box = QWidget()
        fl = QHBoxLayout(folder_box)
        fl.addWidget(QLabel("Source Folder:"))
        self.folder_input = QLineEdit()
        self.folder_input.setObjectName("urlInput")
        self.folder_input.setPlaceholderText("Folder containing your exports...")
        self.folder_input.setFixedHeight(44)
        
        btn_browse = QPushButton("Browse")
        btn_browse.setObjectName("openFolderBtn")
        btn_browse.setFixedHeight(44)
        btn_browse.setFixedWidth(120)
        btn_browse.clicked.connect(self._browse_folder)
        
        fl.addWidget(self.folder_input, 1)
        fl.addWidget(btn_browse)
        layout.addWidget(folder_box)

                  
        settings_box = QWidget()
        sl = QGridLayout(settings_box)
        sl.setSpacing(15)

        sl.addWidget(QLabel("Post Frequency (mins):"), 0, 0)
        self.freq_spin = QSpinBox()
        self.freq_spin.setRange(1, 1440)
        self.freq_spin.setValue(60)
        self.freq_spin.setObjectName("urlInput")
        self.freq_spin.setFixedHeight(40)
        sl.addWidget(self.freq_spin, 0, 1)

        sl.addWidget(QLabel("Title:"), 1, 0)
        self.title_tmpl = QLineEdit("{filename} #shorts #reddit")
        self.title_tmpl.setObjectName("urlInput")
        self.title_tmpl.setFixedHeight(40)
        sl.addWidget(self.title_tmpl, 1, 1)

        sl.addWidget(QLabel("Description:"), 2, 0)
        self.desc_tmpl = QTextEdit("Automated Reddit Story Post. #reddit #stories")
        self.desc_tmpl.setObjectName("urlInput")
        self.desc_tmpl.setMaximumHeight(80)
        sl.addWidget(self.desc_tmpl, 2, 1)

        layout.addWidget(settings_box)

                  
        ctrl_h = QHBoxLayout()
        self.start_btn = QPushButton("🚀 Start Posting")
        self.start_btn.setObjectName("analyzeBtn")
        self.start_btn.setFixedHeight(55)
        self.start_btn.clicked.connect(self._start_automation)
        
        self.stop_btn = QPushButton("🛑 Stop Posting")
        self.stop_btn.setObjectName("openFolderBtn")
        self.stop_btn.setFixedHeight(55)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_automation)
        
        self.logout_btn = QPushButton("🔓 Logout / Switch Account")
        self.logout_btn.setObjectName("openFolderBtn")
        self.logout_btn.setFixedHeight(55)
        self.logout_btn.clicked.connect(self._logout_channel)
        
        self.guide_btn = QPushButton("📖 View YouTube Setup Guide")
        self.guide_btn.setObjectName("openFolderBtn")
        self.guide_btn.setFixedHeight(55)
        self.guide_btn.clicked.connect(self._show_guide)
        
        ctrl_h.addWidget(self.start_btn, 2)
        ctrl_h.addWidget(self.stop_btn, 1)
        ctrl_h.addWidget(self.logout_btn, 1)
        ctrl_h.addWidget(self.guide_btn, 1)
        layout.addLayout(ctrl_h)

                       
        self.status_lbl = QLabel("Status: Idle")
        self.status_lbl.setObjectName("statusLabel")
        layout.addWidget(self.status_lbl)

        self.prog = QProgressBar()
        self.prog.setObjectName("progressBar")
        self.prog.setFixedHeight(22)
        self.prog.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.prog.setValue(0)
        layout.addWidget(self.prog)

             
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setObjectName("urlInput")
        self.log.setStyleSheet("background: #050510; color: #00eeff; font-family: 'Consolas'; font-size: 11px;")
        layout.addWidget(self.log, 1)

        layout.addStretch()
        scroll.setWidget(container)
        main_layout.addWidget(scroll)

    def _browse_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Select Video Folder")
        if d: self.folder_input.setText(d)

    def _start_automation(self):
        path = self.folder_input.text().strip()
        if not path or not os.path.exists(path):
            QMessageBox.warning(self, "Error", "Select a valid folder full of videos first.")
            return

        if not os.path.exists("client_secrets.json"):
            QMessageBox.critical(self, "API Error", "client_secrets.json not found! You must provide one from Google Cloud Console to use the uploader.")
            return

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.log.append(">>> Starting YouTube shorts pipeline...")
        
        self.poster_thread = YoutubePosterThread(
            path, self.freq_spin.value(),
            self.title_tmpl.text(),
            self.desc_tmpl.toPlainText()
        )
        self.poster_thread.progress.connect(self._on_prog)
        self.poster_thread.log.connect(self.log.append)
        self.poster_thread.error.connect(lambda e: QMessageBox.critical(self, "Poster Error", e))
        self.poster_thread.finished.connect(self._on_finished)
        self.poster_thread.start()

    def _stop_automation(self):
        if self.poster_thread:
            self.poster_thread.cancel()
            self.log.append("!!! Manual stop requested...")
            self.stop_btn.setEnabled(False)

    def _on_prog(self, msg, pct):
        self.status_lbl.setText(msg)
        self.prog.setValue(pct)

    def _on_finished(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_lbl.setText("Status: Finished / Stopped")
        self.log.append(">>> Pipeline stopped.")

    def _logout_channel(self):
        if os.path.exists("token.pickle"):
            try:
                os.remove("token.pickle")
                QMessageBox.information(self, "Logged Out", "Successfully logged out. You will be asked to log in again on your next upload.")
                self.log.append(">>> Logged out of YouTube.")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to delete token: {e}")
        else:
            QMessageBox.information(self, "No Account", "You are not currently logged in.")

    def _show_guide(self):
        guide_text = """
        HOW TO SETUP YOUTUBE SHORTS POSTER:
        
        1. Go to Google Cloud Console (console.cloud.google.com).
        2. Create a Project named 'DoogClips'.
        3. Search for 'YouTube Data API v3' and ENABLE it.
        4. Go to 'Credentials' > 'Create Credentials' > 'OAuth client ID'.
        5. Select 'Desktop App'.
        6. Download the JSON and rename it to 'client_secrets.json'.
        7. Place it in this folder.
        
        Full guide is also in README_YOUTUBE.txt!
        """
        QMessageBox.information(self, "YouTube Setup Guide", guide_text.strip())


class PluginsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_win = parent
        self.loaded_plugins = {}
        self._init_ui()
        self.refresh_plugins()

    def _init_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

                                    
        hdr_widget = QWidget()
        hdr_widget.setObjectName("urlPanel")
        hl = QHBoxLayout(hdr_widget)
        hl.setContentsMargins(20, 10, 20, 10)

        title = QLabel("MODULAR PLUGINS")
        title.setObjectName("titleLabel")
        hl.addWidget(title)
        hl.addStretch()

        self.guide_btn = QPushButton("📖 Developer Guide")
        self.guide_btn.setObjectName("openFolderBtn")
        self.guide_btn.setFixedWidth(180)
        self.guide_btn.setFixedHeight(40)
        self.guide_btn.clicked.connect(self.show_guide)
        hl.addWidget(self.guide_btn)

        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.setObjectName("openFolderBtn")
        self.refresh_btn.setFixedWidth(120)
        self.refresh_btn.setFixedHeight(40)
        self.refresh_btn.clicked.connect(self.refresh_plugins)
        hl.addWidget(self.refresh_btn)
        
        self.layout.addWidget(hdr_widget)

                                                 
        self.plugin_tabs = QTabWidget()
        self.plugin_tabs.setObjectName("mainTabs")
        self.plugin_tabs.setTabPosition(QTabWidget.TabPosition.West)
        self.layout.addWidget(self.plugin_tabs, 1)

    def refresh_plugins(self):
                            
        for name, instance in self.loaded_plugins.items():
            try: instance.on_unload()
            except: pass
        
        self.plugin_tabs.clear()
        self.loaded_plugins = {}

        if not os.path.exists(PLUGINS_DIR):
            os.makedirs(PLUGINS_DIR, exist_ok=True)
            return

                          
        for filename in os.listdir(PLUGINS_DIR):
            if filename.endswith(".py") and not filename.startswith("__"):
                path = os.path.join(PLUGINS_DIR, filename)
                plugin_instance = self._load_plugin_file(path)
                if plugin_instance:
                    name = getattr(plugin_instance, "plugin_name", filename)
                    self.plugin_tabs.addTab(plugin_instance, name)
                    self.loaded_plugins[name] = plugin_instance
                    try: plugin_instance.on_load()
                    except: pass

        if self.plugin_tabs.count() == 0:
            empty = QWidget()
            el = QVBoxLayout(empty)
            txt = QLabel("No plugins found in /plugins folder.\nDrop .py files there and Refresh!")
            txt.setAlignment(Qt.AlignmentFlag.AlignCenter)
            txt.setStyleSheet("color: #445; font-size: 14px; font-weight: bold;")
            el.addWidget(txt)
            self.plugin_tabs.addTab(empty, "Empty")

    def show_guide(self):
        guide = """
# DoogClips Plugin Dev Guide

## 📂 1. The Directory
Place all your `.py` files in the **`plugins/`** folder. The app scans this folder every time you click "Refresh".

## 🏗️ 2. The Plugin Class
Your plugin file must contain a class that inherits from `DoogPlugin`.

```python
from doogclips.gui.plugin_base import DoogPlugin
from PyQt6.QtWidgets import QVBoxLayout, QLabel

class MyCoolPlugin(DoogPlugin):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.plugin_name = "My Cool Plugin"
        self.plugin_description = "A short description."

    def _init_ui(self):
        # This is where u build your GUI
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Success!"))
```

## 🧠 3. Accessing the App (parent_win)
Your plugin has access to `self.parent_win`. This allows you to interact with the whole app.
- **Get Reddit Title**: `self.parent_win.red_title_input.text()`
- **Get Export Dir**: `from doogclips.pipeline import EXPORTS_DIR`

## 🧩 4. Lifecycles
- `on_load(self)`: Triggered when the user switches TO your plugin tab.
- `on_unload(self)`: Triggered when the user switches AWAY from your tab (use this to stop background threads).

## 🛠️ 5. Helpful Utilities
- **Paths**: Use `from doogclips.utils.paths import resolve_path` to ensure your plugin works in the portable version!
        """
        dialog = QDialog(self)
        dialog.setWindowTitle("DoogClips Plugin Developer Guide")
        dialog.setMinimumSize(700, 600)
        dl = QVBoxLayout(dialog)
        
        from PyQt6.QtWidgets import QTextEdit
        text = QTextEdit()
        text.setReadOnly(True)
        text.setMarkdown(guide.strip())
        text.setStyleSheet("background: #0d0d15; color: #ccc; border: none; padding: 20px; font-size: 14px;")
        dl.addWidget(text)
        
        close_btn = QPushButton("Got it!")
        close_btn.setObjectName("analyzeBtn")
        close_btn.setFixedHeight(45)
        close_btn.clicked.connect(dialog.accept)
        dl.addWidget(close_btn)
        
        dialog.exec()

    def _load_plugin_file(self, path):
        try:
            module_name = os.path.basename(path).replace(".py", "")
            spec = importlib.util.spec_from_file_location(module_name, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            for name, obj in inspect.getmembers(module):
                if inspect.isclass(obj) and issubclass(obj, DoogPlugin) and obj is not DoogPlugin:
                    return obj(self.parent_win)
        except Exception as e:
            print(f"Failed to load plugin {path}: {e}")
        return None


class SlidingStackedWidget(QStackedWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.m_duration = 380
        self.m_animation_type = QEasingCurve.Type.OutExpo
        self.m_active = False

    def slideInIdx(self, idx):
        if self.m_active: return
        self.m_active = True
        now = self.currentIndex()
        next_w = self.widget(idx)
        if now == idx:
            self.m_active = False
            return
        offsetx = self.width()
        if now < idx: offsetx = -offsetx
        next_w.setGeometry(0, 0, self.width(), self.height())
        next_w.move(QPoint(-offsetx, 0))
        next_w.show()
        next_w.raise_()
        self.anim_now = QPropertyAnimation(self.widget(now), b"pos")
        self.anim_now.setDuration(self.m_duration)
        self.anim_now.setEasingCurve(self.m_animation_type)
        self.anim_now.setStartValue(QPoint(0, 0))
        self.anim_now.setEndValue(QPoint(offsetx, 0))
        self.anim_next = QPropertyAnimation(next_w, b"pos")
        self.anim_next.setDuration(self.m_duration)
        self.anim_next.setEasingCurve(self.m_animation_type)
        self.anim_next.setStartValue(QPoint(-offsetx, 0))
        self.anim_next.setEndValue(QPoint(0, 0))
        self.anim_next.finished.connect(lambda: self._on_anim_finished(idx))
        self.anim_now.start()
        self.anim_next.start()

    def _on_anim_finished(self, idx):
        self.setCurrentIndex(idx)
        self.m_active = False

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DoogClips")
        self.setMinimumSize(1200, 750)
        self.resize(1400, 830)
        self.setStyleSheet(STYLESHEET)
        
        self.clips = []
        self.selected_clip = None
        self.clip_cards = []
        self.custom_font_path = ""
        
        self.player = None
        self.audio_output = None
        self.analysis_thread = None
        self.reddit_thread = None
        self.red_player = None
        self.red_audio_out = None
        
        self.COLORS = {
            "Yellow": (255, 220, 0), "Red": (255, 60, 60), "Green": (50, 255, 50),
            "White": (255, 255, 255), "Blue": (50, 150, 255), "Purple": (200, 50, 255)
        }
        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

                 
        self.sidebar = QWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(240)
        sl = QVBoxLayout(self.sidebar)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)
        
        hdr = QWidget()
        hdr.setObjectName("sidebarHeader")
        hl = QVBoxLayout(hdr)
        hl.setContentsMargins(20, 30, 20, 30)
        logo = QLabel("DOOGCLIPS")
        logo.setObjectName("logoLabel")
        logo.setStyleSheet("font-size: 32px; font-weight: 900; color: #ffffff;")
        sub = QLabel("AN ALL IN ONE CREATOR TOOL")
        sub.setObjectName("logoSubLabel")
        sub.setStyleSheet("font-size: 11px; font-weight: 800; color: #7b2fff; margin-top: -5px;")
        hl.addWidget(logo)
        hl.addWidget(sub)
        sl.addWidget(hdr)

        self.nav_btns = []
        tabs = [
            ("🎬 AI Viral Clipper", 0),
            ("💬 Reddit Creator", 1),
            ("🔡 Add Captions", 2),
            ("🎤 Voice Cloning", 3),
            ("📦 Bulk Reddit", 4),
            ("📺 YouTube Poster", 5),
            ("🔌 Plugins", 6),
            ("⚙️ Fonts Settings", 7)
        ]

        for text, idx in tabs:
            btn = QPushButton(text)
            btn.setObjectName("navBtn")
            btn.setProperty("active", "false")
            btn.clicked.connect(lambda checked, i=idx: self._switch_tab(i))
            sl.addWidget(btn)
            self.nav_btns.append(btn)
            
        sl.addStretch()
        root.addWidget(self.sidebar)

                            
        self.stack = SlidingStackedWidget()
        root.addWidget(self.stack, 1)

        tab_clipper = QWidget()
        self._build_clipper_tab(tab_clipper)
        self.stack.addWidget(tab_clipper)
        
        tab_reddit = QWidget()
        self._build_reddit_tab(tab_reddit)
        self.stack.addWidget(tab_reddit)
        
        self.stack.addWidget(CaptioningTab(self))
        
        self.voice_tab = VoiceCloningTab(self)
        self.stack.addWidget(self.voice_tab)
        
        tab_bulk = QWidget()
        self._build_bulk_reddit_tab(tab_bulk)
        self.stack.addWidget(tab_bulk)

        self.stack.addWidget(YoutubePosterTab(self))

        self.plugins_tab = PluginsTab(self)
        self.stack.addWidget(self.plugins_tab)

        tab_fonts = QWidget()
        self._build_fonts_tab(tab_fonts)
        self.stack.addWidget(tab_fonts)

        QTimer.singleShot(500, self._update_voice_dropdowns)
        self._init_player()
        self._trigger_preview_update(True)
        self._switch_tab(0)

    def _switch_tab(self, idx):
        for i, btn in enumerate(self.nav_btns):
            btn.setProperty("active", "true" if i == idx else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self.stack.slideInIdx(idx)

    def register_voice_tab(self, tab):
        self.voice_tab = tab

    def _on_red_preview_status(self, status):
                            
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            try:
                self.red_player.setSource(QUrl())
                if os.path.exists("pv.mp3"): os.remove("pv.mp3")
            except: pass

    def _build_clipper_tab(self, parent):
        main_layout = QVBoxLayout(parent)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        cl_layout = QVBoxLayout(container)
        cl_layout.setContentsMargins(0, 0, 0, 0)

        url_panel = QWidget()
        url_panel.setObjectName("urlPanel")
        up_master = QVBoxLayout(url_panel)
        up_master.setContentsMargins(20, 20, 20, 20)
        up_master.setSpacing(15)

        title_row = QHBoxLayout()
        title = QLabel("DOOGCLIPS")
        title.setObjectName("titleLabel")
        sub = QLabel("An OpusClips Alternative")
        sub.setObjectName("subtitleLabel")
        title_row.addWidget(title)
        title_row.addWidget(sub)
        title_row.addStretch()
        up_master.addLayout(title_row)

                           
        input_group = QWidget()
        grid = QGridLayout(input_group)
        grid.setSpacing(14)
        
                    
        grid.addWidget(QLabel("Video URL:"), 0, 0)
        self.url_input = QLineEdit()
        self.url_input.setObjectName("urlInput")
        self.url_input.setPlaceholderText("Paste YouTube URL here...")
        self.url_input.setFixedHeight(44)
        self.url_input.returnPressed.connect(self._start_analysis)
        grid.addWidget(self.url_input, 0, 1, 1, 2)
        
        self.analyze_btn = QPushButton("Analyze Video")
        self.analyze_btn.setObjectName("analyzeBtn")
        self.analyze_btn.setFixedHeight(44)
        self.analyze_btn.setFixedWidth(160)
        self.analyze_btn.clicked.connect(self._start_analysis)
        grid.addWidget(self.analyze_btn, 0, 3)

                             
        grid.addWidget(QLabel("Custom Title:"), 1, 0)
        self.custom_title_input = QLineEdit()
        self.custom_title_input.setObjectName("urlInput")
        self.custom_title_input.setPlaceholderText("Optional")
        self.custom_title_input.setFixedHeight(44)
        grid.addWidget(self.custom_title_input, 1, 1, 1, 3)
        
                    
        grid.addWidget(QLabel("BGM:"), 2, 0)
        self.bgm_clip_combo = QComboBox()
        self.bgm_clip_combo.setObjectName("urlInput")
        self.bgm_clip_combo.addItems(["None", "Lofi Chill", "Spooky Ambient", "Custom File (.mp3/.wav)"])
        self.bgm_clip_combo.setFixedHeight(44)
        self.bgm_clip_combo.currentTextChanged.connect(self._on_clip_bgm_changed)
        grid.addWidget(self.bgm_clip_combo, 2, 1, 1, 2)
        
        grid.addWidget(QLabel("BGM Volume:"), 3, 0)
        self.clip_bgm_vol = QSlider(Qt.Orientation.Horizontal)
        self.clip_bgm_vol.setRange(0, 100)
        self.clip_bgm_vol.setValue(15)
        self.clip_bgm_vol.setToolTip("BGM Volume")
        self.clip_bgm_vol.setFixedHeight(44)
        grid.addWidget(self.clip_bgm_vol, 3, 1, 1, 3)
        
        self.bgm_clip_custom = QLineEdit()
        self.bgm_clip_custom.setObjectName("urlInput")
        self.bgm_clip_custom.setPlaceholderText("Paste absolute path to custom BGM .mp3/.wav")
        self.bgm_clip_custom.setFixedHeight(44)
        self.bgm_clip_custom.setVisible(False)
        grid.addWidget(self.bgm_clip_custom, 4, 1, 1, 3)

                                 
        grid.addWidget(QLabel("Durations:"), 5, 0)
        self.min_dur_sp = QSpinBox()
        self.min_dur_sp.setRange(10, 180)
        self.min_dur_sp.setValue(30)
        self.min_dur_sp.setObjectName("urlInput")
        self.min_dur_sp.setFixedHeight(44)
        
        self.max_dur_sp = QSpinBox()
        self.max_dur_sp.setRange(10, 180)
        self.max_dur_sp.setValue(90)
        self.max_dur_sp.setObjectName("urlInput")
        self.max_dur_sp.setFixedHeight(44)
        
        dur_h = QHBoxLayout()
        dur_h.addWidget(self.min_dur_sp)
        l = QLabel("to")
        l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dur_h.addWidget(l)
        dur_h.addWidget(self.max_dur_sp)
        grid.addLayout(dur_h, 5, 1)

        grid.addWidget(QLabel("Whisper:"), 5, 2)
        self.whisper_model_combo = QComboBox()
        self.whisper_model_combo.setObjectName("urlInput")
        self.whisper_model_combo.addItems(["Faster (Tiny)", "Base (Standard)", "Quality (Large-v3)"])
        self.whisper_model_combo.setCurrentText("Quality (Large-v3)")
        self.whisper_model_combo.setFixedHeight(44)
        grid.addWidget(self.whisper_model_combo, 5, 3)
        
                             
        grid.addWidget(QLabel("Clips:"), 6, 0)
        self.max_clips_sp = QSpinBox()
        self.max_clips_sp.setRange(1, 25)
        self.max_clips_sp.setValue(8)
        self.max_clips_sp.setObjectName("urlInput")
        self.max_clips_sp.setFixedHeight(44)
        grid.addWidget(self.max_clips_sp, 6, 1)

        self.gameplay_chk = QCheckBox("Game Split")
        self.gameplay_chk.setChecked(True)
        
        self.facecam_chk = QCheckBox("Facecam Mode")
        self.facecam_chk.setChecked(False)
        self.facecam_chk.setToolTip("Put Streamer on top, Game on bottom")
        
        self.track_strength_sp = QSpinBox()
        self.track_strength_sp.setRange(0, 100)
        self.track_strength_sp.setValue(100)
        self.track_strength_sp.setSuffix("%")
        self.track_strength_sp.setToolTip("Face Tracking Strength (0% = center crop)")
        self.track_strength_sp.setFixedHeight(44)
        
        self.gpu_chk = QCheckBox("GPU Mode")
        self.gpu_chk.setChecked(True)
        self.gpu_chk.setToolTip("Uses High Speed GPU Encoding (Nvidia/AMD)")
        
        hbox = QHBoxLayout()
        hbox.addWidget(self.gameplay_chk)
        hbox.addWidget(self.facecam_chk)
        hbox.addWidget(self.gpu_chk)
        hbox.addWidget(QLabel("Face Track:"))
        hbox.addWidget(self.track_strength_sp)
        grid.addLayout(hbox, 6, 2, 1, 2)
        
                           
        grid.addWidget(QLabel("Background:"), 7, 0)
        self.bg_clip_combo = QComboBox()
        self.bg_clip_combo.setObjectName("urlInput")
        self.bg_clip_combo.addItems(["Random Preset", "GTA V Racing", "Minecraft Parkour", "Subway Surfers", "Custom URL"])
        self.bg_clip_combo.setFixedHeight(44)
        self.bg_clip_combo.currentTextChanged.connect(self._on_clip_bg_changed)
        grid.addWidget(self.bg_clip_combo, 7, 1, 1, 3)

        self.bg_clip_custom = QLineEdit()
        self.bg_clip_custom.setObjectName("urlInput")
        self.bg_clip_custom.setPlaceholderText("Paste Custom Video URL here")
        self.bg_clip_custom.setFixedHeight(44)
        self.bg_clip_custom.setVisible(False)
        grid.addWidget(self.bg_clip_custom, 8, 1, 1, 3)
        
        up_master.addWidget(input_group)

                          
        prog_row = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("progressBar")
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.status_label = QLabel("Ready  |  Configure settings and Analyze")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        prog_row.addWidget(self.progress_bar, 3)
        prog_row.addWidget(self.status_label, 2)
        up_master.addLayout(prog_row)

        cl_layout.addWidget(url_panel)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("QSplitter::handle { background: #1e1e30; }")

        clips_panel = QWidget()
        clips_panel.setObjectName("clipsPanel")
        clips_panel.setMinimumWidth(320)
        clips_panel.setMaximumWidth(420)
        cl = QVBoxLayout(clips_panel)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)

        hdr = QLabel("VIRAL CLIPS")
        hdr.setObjectName("clipsPanelHeader")
        cl.addWidget(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #1e1e30;")
        cl.addWidget(sep)

        self.scroll_area_clips = QScrollArea()
        self.scroll_area_clips.setWidgetResizable(True)
        self.scroll_area_clips.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 8, 0, 8)
        self.cards_layout.setSpacing(6)
        self.cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.empty_label = QLabel("No clips yet.\nAnalyze a YouTube\nvideo to get started.")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: #3a3a5c; font-size: 13px; padding: 40px;")
        self.cards_layout.addWidget(self.empty_label)
        self.scroll_area_clips.setWidget(self.cards_container)
        cl.addWidget(self.scroll_area_clips)

        export_all_btn = QPushButton("Export All Clips")
        export_all_btn.setObjectName("exportAllBtn")
        export_all_btn.setFixedHeight(42)
        export_all_btn.clicked.connect(self._export_all)
        cl.addWidget(export_all_btn)
        splitter.addWidget(clips_panel)

        preview_panel = QWidget()
        preview_panel.setObjectName("previewPanel")
        pl = QVBoxLayout(preview_panel)
        pl.setContentsMargins(20, 20, 20, 20)
        pl.setSpacing(16)

        video_container = QWidget()
        video_container.setObjectName("previewContainer")
        video_container.setStyleSheet("background: #000; border-radius: 16px;")
        vcl = QVBoxLayout(video_container)
        vcl.setContentsMargins(0, 0, 0, 0)

        self.preview_stack = QStackedWidget()
        placeholder = QLabel("Select a clip to preview")
        placeholder.setObjectName("previewLabel")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setStyleSheet("color: #3a3a5c; font-size: 16px; background: #000; border-radius: 16px;")
        self.preview_stack.addWidget(placeholder)

        self.video_widget = QVideoWidget()
        self.video_widget.setStyleSheet("background: #000; border-radius: 16px;")
        self.preview_stack.addWidget(self.video_widget)
        vcl.addWidget(self.preview_stack)
        pl.addWidget(video_container, 1)

        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(10)
        self.play_btn = QPushButton("Play")
        self.play_btn.setObjectName("exportBtn")
        self.play_btn.setFixedHeight(40)
        self.play_btn.clicked.connect(self._toggle_play)
        self.export_btn = QPushButton("Export Clip")
        self.export_btn.setObjectName("exportBtn")
        self.export_btn.setFixedHeight(40)
        self.export_btn.clicked.connect(self._export_selected)
        self.open_folder_btn = QPushButton("Open Exports Folder")
        self.open_folder_btn.setObjectName("openFolderBtn")
        self.open_folder_btn.setFixedHeight(40)
        self.open_folder_btn.clicked.connect(self._open_exports)
        ctrl_row.addWidget(self.play_btn)
        ctrl_row.addWidget(self.export_btn)
        ctrl_row.addStretch()
        ctrl_row.addWidget(self.open_folder_btn)
        pl.addLayout(ctrl_row)

        self.clip_details = QLabel("")
        self.clip_details.setStyleSheet("color: #6666aa; font-size: 12px;")
        self.clip_details.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.clip_details.setWordWrap(True)
        pl.addWidget(self.clip_details)

        splitter.addWidget(preview_panel)
        splitter.setSizes([360, 1040])
        cl_layout.addWidget(splitter, 1)
        
        scroll.setWidget(container)
        main_layout.addWidget(scroll)
        
        self.preview_time = 0.0
        self.preview_timer = QTimer()
        self.preview_timer.timeout.connect(self._tick_preview)
        self.preview_timer.start(100)


    def _browse_custom_font(self):
        file, _ = QFileDialog.getOpenFileName(self, "Select Font File", os.path.expanduser("~/Downloads"), "Font Files (*.ttf *.otf)")
        if file:
            self.custom_font_path = file
            self.status_label.setText(f"Loaded Custom Font: {os.path.basename(file)}")
            self._trigger_preview_update(False)

    def _on_font_family_changed(self, text):
        if text == "Mr Beast Font":
            self.custom_font_path = resolve_path("assets/fonts/MrBeast.ttf")
            self.font_browse_btn.setVisible(False)
        else:
            is_custom = (text == "Custom...")
            self.font_browse_btn.setVisible(is_custom)
            if is_custom and not self.custom_font_path:
                self._browse_custom_font()
        self._trigger_preview_update(False)

    def _build_bulk_reddit_tab(self, parent):
        main_layout = QVBoxLayout(parent)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        bk_layout = QVBoxLayout(container)
        bk_layout.setContentsMargins(40, 40, 40, 40)
        bk_layout.setSpacing(20)

        hdr = QLabel("BULK REDDIT CREATOR")
        hdr.setObjectName("titleLabel")
        bk_layout.addWidget(hdr)
        
        desc = QLabel("Enter Reddit URLs manually, or target a specific subreddit below.")
        desc.setObjectName("subtitleLabel")
        bk_layout.addWidget(desc)

                                   
        auto_box = QWidget()
        al = QGridLayout(auto_box)
        al.setSpacing(25)                                   
        al.setContentsMargins(10, 15, 10, 15)
        
                                                        
        al.setColumnStretch(1, 3)
        al.setColumnStretch(3, 1)
        al.setColumnStretch(5, 1)
        
                                      
        al.addWidget(QLabel("Target Subreddit:"), 0, 0)
        self.bulk_sub_name = QLineEdit()
        self.bulk_sub_name.setObjectName("urlInput")
        self.bulk_sub_name.setPlaceholderText("e.g. r/AskReddit")
        self.bulk_sub_name.setFixedHeight(50)
        al.addWidget(self.bulk_sub_name, 0, 1)
        
        al.addWidget(QLabel("Limit:"), 0, 2)
        self.bulk_sub_count = QSpinBox()
        self.bulk_sub_count.setObjectName("urlInput")
        self.bulk_sub_count.setRange(1, 100)
        self.bulk_sub_count.setValue(10)
        self.bulk_sub_count.setFixedHeight(50)
        self.bulk_sub_count.setFixedWidth(200)
        al.addWidget(self.bulk_sub_count, 0, 3)

        al.addWidget(QLabel("Time:"), 0, 4)
        self.bulk_sub_time = QComboBox()
        self.bulk_sub_time.setObjectName("urlInput")
        self.bulk_sub_time.addItems(["day", "week", "month", "year", "all"])
        self.bulk_sub_time.setFixedHeight(50)
        self.bulk_sub_time.setMinimumWidth(200)
        al.addWidget(self.bulk_sub_time, 0, 5)
        
                                        
        al.addWidget(QLabel("Min Dur (s):"), 1, 0)
        self.bulk_sub_min = QSpinBox()
        self.bulk_sub_min.setObjectName("urlInput")
        self.bulk_sub_min.setRange(5, 300)
        self.bulk_sub_min.setValue(20)
        self.bulk_sub_min.setFixedHeight(50)
        self.bulk_sub_min.setFixedWidth(200)
        al.addWidget(self.bulk_sub_min, 1, 1)
        
        al.addWidget(QLabel("Max Dur (s):"), 1, 2)
        self.bulk_sub_max = QSpinBox()
        self.bulk_sub_max.setObjectName("urlInput")
        self.bulk_sub_max.setRange(10, 600)
        self.bulk_sub_max.setValue(60)
        self.bulk_sub_max.setFixedHeight(50)
        self.bulk_sub_max.setFixedWidth(200)
        al.addWidget(self.bulk_sub_max, 1, 3)

        self.bulk_scrape_btn = QPushButton("Scrape Subreddit")
        self.bulk_scrape_btn.setObjectName("analyzeBtn")
        self.bulk_scrape_btn.setFixedHeight(36)
        self.bulk_scrape_btn.clicked.connect(self._scrape_subreddit_auto)
        al.addWidget(self.bulk_scrape_btn, 1, 4, 1, 2)
        
        bk_layout.addSpacing(10)
        bk_layout.addWidget(auto_box)
        bk_layout.addSpacing(15)
        
        bk_layout.addWidget(QLabel("Manual URLs / Scraped Queue:"))
        
        self.bulk_urls_input = QTextEdit()
        self.bulk_urls_input.setObjectName("urlInput")
        self.bulk_urls_input.setPlaceholderText("https://reddit.com/r/AskReddit/comments/...\nhttps://reddit.com/r/Stories/comments/...")
        bk_layout.addWidget(self.bulk_urls_input, 1)
        
        self.bulk_dropdown_chk = QCheckBox("Use Dropdown Style (Scrolling text)")
        self.bulk_dropdown_chk.setStyleSheet("color: #e8e8f0; font-weight: bold; margin-bottom: 5px;")
        bk_layout.addWidget(self.bulk_dropdown_chk)

        self.bulk_dropdown_comment_chk = QCheckBox("Dropdown + Comment")
        self.bulk_dropdown_comment_chk.setStyleSheet("color: #e8e8f0; font-weight: bold; margin-bottom: 5px;")
        bk_layout.addWidget(self.bulk_dropdown_comment_chk)

        self.bulk_top_comment_chk = QCheckBox("Include Top Comment")
        self.bulk_top_comment_chk.setChecked(True)
        self.bulk_top_comment_chk.setStyleSheet("color: #e8e8f0; font-weight: bold; margin-bottom: 5px;")
        bk_layout.addWidget(self.bulk_top_comment_chk)
        
        ctrl_h = QHBoxLayout()
        self.bulk_start_btn = QPushButton("Start Batch Processing")
        self.bulk_start_btn.setObjectName("analyzeBtn")
        self.bulk_start_btn.setFixedHeight(50)
        self.bulk_start_btn.clicked.connect(self._start_bulk_reddit)
        
        self.bulk_stop_btn = QPushButton("Cancel Batch")
        self.bulk_stop_btn.setObjectName("openFolderBtn")
        self.bulk_stop_btn.setFixedHeight(50)
        self.bulk_stop_btn.setEnabled(False)
        self.bulk_stop_btn.clicked.connect(self._cancel_bulk_reddit)
        
        ctrl_h.addWidget(self.bulk_start_btn, 2)
        ctrl_h.addWidget(self.bulk_stop_btn, 1)
        bk_layout.addLayout(ctrl_h)
        
                           
        self.bulk_log = QTextEdit()
        self.bulk_log.setReadOnly(True)
        self.bulk_log.setObjectName("urlInput")
        self.bulk_log.setStyleSheet("background: #0a0a15; color: #00ff00; font-family: 'Consolas', monospace; font-size: 11px;")
        self.bulk_log.setPlaceholderText("Automation Log Console...")
        bk_layout.addWidget(self.bulk_log, 1)
        
        self.bulk_prog_clip = QProgressBar()
        self.bulk_prog_clip.setObjectName("progressBar")
        self.bulk_prog_clip.setFixedHeight(8)
        self.bulk_prog_clip.setTextVisible(False)
        bk_layout.addWidget(QLabel("Current Clip Progress:"))
        bk_layout.addWidget(self.bulk_prog_clip)
        
        self.bulk_prog_batch = QProgressBar()
        self.bulk_prog_batch.setObjectName("progressBar")
        self.bulk_prog_batch.setFixedHeight(12)
        self.bulk_prog_batch.setStyleSheet("QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ff00ff, stop:1 #00ffff); }")
        bk_layout.addWidget(QLabel("Overall Batch Progress:"))
        bk_layout.addWidget(self.bulk_prog_batch)
        
        self.bulk_status = QLabel("Ready")
        self.bulk_status.setObjectName("statusLabel")
        bk_layout.addWidget(self.bulk_status)

        scroll.setWidget(container)
        main_layout.addWidget(scroll)


    def _build_fonts_tab(self, parent=None):
        if parent is None:
            parent = QWidget()
        main_layout = QVBoxLayout(parent)
        main_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        
        left_panel = QWidget()
        left_panel.setObjectName("urlPanel")
        ll = QVBoxLayout(left_panel)
        ll.setSpacing(15)
        
        hdr = QLabel("Global Fonts & Styles")
        hdr.setObjectName("titleLabel")
        ll.addWidget(hdr)
        
                                
        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setSpacing(10)

                           
        grid.addWidget(QLabel("QUICK PRESETS:"), 0, 0)
        presets_h = QHBoxLayout()
        self.btn_mb = QPushButton("MrBeast Style")
        self.btn_mb.setObjectName("analyzeBtn")
        self.btn_mb.setFixedHeight(40)
        self.btn_mb.clicked.connect(self._apply_mrbeast_preset)
        presets_h.addWidget(self.btn_mb)
        
        self.btn_hr = QPushButton("Hormozi style")
        self.btn_hr.setObjectName("exportBtn")
        self.btn_hr.setFixedHeight(40)
        self.btn_hr.clicked.connect(self._apply_hormozi_preset)
        presets_h.addWidget(self.btn_hr)
        
        grid.addLayout(presets_h, 0, 1, 1, 3)
        
                                     
        grid.addWidget(QLabel("Font Family:"), 1, 0)
        self.font_family_combo = QComboBox()
        self.font_family_combo.setObjectName("urlInput")
        self.font_family_combo.addItems(["Impact", "Mr Beast Font", "Arial Bold", "Arial Black", "Calibri Bold", "Comic Sans", "Verdana Bold", "Tahoma Bold", "Custom..."])
        self.font_family_combo.setFixedHeight(40)
        self.font_family_combo.currentTextChanged.connect(self._on_font_family_changed)
        grid.addWidget(self.font_family_combo, 1, 1, 1, 2)
        
        self.font_browse_btn = QPushButton("Browse...")
        self.font_browse_btn.setFixedWidth(80)
        self.font_browse_btn.setVisible(False)
        self.font_browse_btn.clicked.connect(self._browse_custom_font)
        grid.addWidget(self.font_browse_btn, 1, 3)
        
                              
        grid.addWidget(QLabel("Animation Style:"), 2, 0)
        self.style_combo = QComboBox()
        self.style_combo.setObjectName("urlInput")
        self.style_combo.addItems(["Regular", "Bouncy", "Hormozi", "Pop", "Pulse"])
        self.style_combo.setFixedHeight(40)
        self.style_combo.currentTextChanged.connect(self._on_style_changed)
        grid.addWidget(self.style_combo, 2, 1, 1, 1)
        
        self.slide_chk = QCheckBox("Slide In")
        self.slide_chk.stateChanged.connect(lambda: self._trigger_preview_update(False))
        grid.addWidget(self.slide_chk, 2, 2)
        
                       
        grid.addWidget(QLabel("Primary Color:"), 3, 0)
        self.color_combo = QComboBox()
        self.color_combo.setObjectName("urlInput")
        self.color_combo.addItems(["Yellow", "Red", "Green", "White", "Blue", "Purple"])
        self.color_combo.setFixedHeight(40)
        self.color_combo.currentTextChanged.connect(lambda: self._trigger_preview_update(True))
        grid.addWidget(self.color_combo, 3, 1)
        
        self.color2_lbl = QLabel("Secondary:")
        self.color2_lbl.setVisible(False)
        grid.addWidget(self.color2_lbl, 3, 2)
        
        self.color2_combo = QComboBox()
        self.color2_combo.setObjectName("urlInput")
        self.color2_combo.addItems(["White", "Yellow", "Red", "Green", "Blue", "Purple"])
        self.color2_combo.setFixedHeight(40)
        self.color2_combo.setVisible(False)
        self.color2_combo.currentTextChanged.connect(lambda: self._trigger_preview_update(True))
        grid.addWidget(self.color2_combo, 3, 3)

                                             
        grid.addWidget(QLabel("Spk 1 / 3 Color:"), 6, 0)
        spk_h1 = QHBoxLayout()
        self.spk1_combo = QComboBox()
        self.spk1_combo.addItems(["Yellow", "Red", "Green", "White", "Blue", "Purple"])
        self.spk1_combo.setCurrentText("Yellow")
        self.spk3_combo = QComboBox()
        self.spk3_combo.addItems(["Yellow", "Red", "Green", "White", "Blue", "Purple"])
        self.spk3_combo.setCurrentText("Green")
        spk_h1.addWidget(self.spk1_combo)
        spk_h1.addWidget(self.spk3_combo)
        grid.addLayout(spk_h1, 6, 1)

        grid.addWidget(QLabel("Spk 2 / 4 Color:"), 6, 2)
        spk_h2 = QHBoxLayout()
        self.spk2_combo = QComboBox()
        self.spk2_combo.addItems(["White", "Yellow", "Red", "Green", "Blue", "Purple"])
        self.spk2_combo.setCurrentText("White")
        self.spk4_combo = QComboBox()
        self.spk4_combo.addItems(["Blue", "Yellow", "Red", "Green", "White", "Purple"])
        self.spk4_combo.setCurrentText("Blue")
        spk_h2.addWidget(self.spk2_combo)
        spk_h2.addWidget(self.spk4_combo)
        grid.addLayout(spk_h2, 6, 3)
        
                              
        grid.addWidget(QLabel("Font Size:"), 4, 0)
        self.font_spin = QSpinBox()
        self.font_spin.setObjectName("urlInput")
        self.font_spin.setRange(40, 140)
        self.font_spin.setValue(86)
        self.font_spin.setFixedHeight(40)
        self.font_spin.valueChanged.connect(lambda: self._trigger_preview_update(False))
        grid.addWidget(self.font_spin, 4, 1)
        
        grid.addWidget(QLabel("Outline:"), 4, 2)
        self.stroke_spin = QSpinBox()
        self.stroke_spin.setObjectName("urlInput")
        self.stroke_spin.setRange(0, 15)
        self.stroke_spin.setValue(4)
        self.stroke_spin.setFixedHeight(40)
        self.stroke_spin.valueChanged.connect(lambda: self._trigger_preview_update(False))
        grid.addWidget(self.stroke_spin, 4, 3)
        
                     
        grid.addWidget(QLabel("Pace:"), 5, 0)
        self.words_combo = QComboBox()
        self.words_combo.setObjectName("urlInput")
        self.words_combo.addItems(["1 Word", "2 Words", "3 Words", "4 Words", "Automax"])
        self.words_combo.setCurrentText("3 Words")
        self.words_combo.setFixedHeight(40)
        self.words_combo.currentTextChanged.connect(lambda: self._trigger_preview_update(True))
        grid.addWidget(self.words_combo, 5, 1, 1, 3)
        
        ll.addWidget(grid_widget)
        
                                     
        ll.addWidget(QLabel("Enhancements:"))
        extras_h = QHBoxLayout()
        self.glow_chk = QCheckBox("Glow Effect")
        self.glow_chk.stateChanged.connect(lambda: self._trigger_preview_update(False))
        
        self.emoji_chk = QCheckBox("Auto-Emojis")
        self.emoji_chk.stateChanged.connect(lambda: self._trigger_preview_update(False))
        
        self.pbar_chk = QCheckBox("Progress Bar")
        self.pbar_chk.stateChanged.connect(lambda: self._trigger_preview_update(False))
        
        extras_h.addWidget(self.glow_chk)
        extras_h.addWidget(self.emoji_chk)
        extras_h.addWidget(self.pbar_chk)
        ll.addLayout(extras_h)
        
        ll.addStretch()
        layout.addWidget(left_panel, 2)
        
                                   
        right_panel = QWidget()
        rightl = QVBoxLayout(right_panel)
        rightl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        lbl = QLabel("True 9:16 Preview Render")
        lbl.setStyleSheet("color: #6666aa; font-weight: bold;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rightl.addWidget(lbl)
        
        self.preview_label = QLabel()
        self.preview_label.setFixedSize(270, 480)                        
        self.preview_label.setStyleSheet("background: #000; border: 4px solid #2a2a4a; border-radius: 12px;")
        rightl.addWidget(self.preview_label)
        
        layout.addWidget(right_panel, 1)
        
        scroll.setWidget(container)
        main_layout.addWidget(scroll)
        return parent


    def _on_clip_bg_changed(self, text):
        self.bg_clip_custom.setVisible(text == "Custom URL")
        
    def _on_clip_bgm_changed(self, text):
        self.bgm_clip_custom.setVisible("Custom" in text)
        
    def _on_style_changed(self, text):
        is_bouncy = (text == "Bouncy")
        self.color2_combo.setVisible(is_bouncy)
        if hasattr(self, 'color2_lbl'):
            self.color2_lbl.setVisible(is_bouncy)
        self._trigger_preview_update(True)

    def _build_reddit_tab(self, parent=None):
        if parent is None:
            parent = QWidget()
        main_layout = QVBoxLayout(parent)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        rd_layout = QHBoxLayout(container)
        rd_layout.setContentsMargins(20, 20, 20, 20)
        rd_layout.setSpacing(20)
        
        left_panel = QWidget()
        left_panel.setObjectName("urlPanel")
        ll = QVBoxLayout(left_panel)
        ll.setSpacing(15)
        
        hdr_lbl = QLabel("Create Reddit Stories")
        hdr_lbl.setObjectName("titleLabel")
        ll.addWidget(hdr_lbl)

                           
        scrape_widget = QWidget()
        sg = QGridLayout(scrape_widget)
        sg.setSpacing(10)
        
        sg.addWidget(QLabel("Reddit URL:"), 0, 0)
        self.red_scrape = QLineEdit()
        self.red_scrape.setObjectName("urlInput")
        self.red_scrape.setPlaceholderText("Paste Reddit post URL here...")
        self.red_scrape.setFixedHeight(44)
        sg.addWidget(self.red_scrape, 0, 1)
        
        btn_scrape = QPushButton("Scrape Content")
        btn_scrape.setObjectName("exportBtn")
        btn_scrape.setFixedWidth(140)
        btn_scrape.setFixedHeight(44)
        btn_scrape.clicked.connect(self._scrape_reddit)
        sg.addWidget(btn_scrape, 0, 2)
        
        ll.addWidget(scrape_widget)
        
        desc = QLabel("Turn text into shorts using Edge-TTS or your cloned voice.")
        desc.setStyleSheet("color: #6666aa; font-size: 13px;")
        desc.setWordWrap(True)
        ll.addWidget(desc)

                                       
        settings_widget = QWidget()
        stg = QGridLayout(settings_widget)
        stg.setSpacing(12)
        
        stg.addWidget(QLabel("Voice:"), 0, 0)
        self.red_voice = QComboBox()
        self.red_voice.setObjectName("urlInput")
        self.red_voice.setMinimumWidth(340)
        self.red_voice.addItems([
            "Christopher (Male)", "Guy (Male)", "Brian (Male)", "Andrew (Male)", "Ryan (Male - UK)",
            "Aria (Female)", "Jenny (Female)", "Emma (Female)", "Sonia (Female - UK)", 
            "Natasha (Female - AU)", "William (Male - AU)",
            "Custom Audio File (.mp3/.wav)"
        ])
        self.red_voice.setFixedHeight(44)
        self.red_voice.currentTextChanged.connect(self._on_red_voice_changed)
        stg.addWidget(self.red_voice, 0, 1)
        self.red_voice_preview_btn = QPushButton("▶️ Preview")
        self.red_voice_preview_btn.setObjectName("exportBtn")
        self.red_voice_preview_btn.setFixedWidth(130)
        self.red_voice_preview_btn.setFixedHeight(44)
        self.red_voice_preview_btn.clicked.connect(self._preview_reddit_voice)
        stg.addWidget(self.red_voice_preview_btn, 0, 2)
        
        self.red_audio_input = QLineEdit()
        self.red_audio_input.setObjectName("urlInput")
        self.red_audio_input.setPlaceholderText("Custom .mp3 path...")
        self.red_audio_input.setFixedHeight(44)
        self.red_audio_input.setVisible(False)
        stg.addWidget(self.red_audio_input, 1, 1, 1, 2)
        
        stg.addWidget(QLabel("Whisper Model:"), 2, 0)
        self.red_whisper_model = QComboBox()
        self.red_whisper_model.setObjectName("urlInput")
        self.red_whisper_model.addItems(["Faster (Tiny)", "Base (Standard)", "Quality (Large-v3)"])
        self.red_whisper_model.setCurrentText("Quality (Large-v3)")
        self.red_whisper_model.setFixedHeight(46)
        stg.addWidget(self.red_whisper_model, 2, 1, 1, 2)
        
        stg.addWidget(QLabel("Background:"), 3, 0)
        self.red_bg_combo = QComboBox()
        self.red_bg_combo.setObjectName("urlInput")
        self.red_bg_combo.addItems(["Random Preset", "GTA V Racing", "Minecraft Parkour", "Subway Surfers", "Custom URL"])
        self.red_bg_combo.setFixedHeight(44)
        self.red_bg_combo.currentTextChanged.connect(self._on_red_bg_changed)
        stg.addWidget(self.red_bg_combo, 3, 1)

        self.red_bgm_combo = QComboBox()
        self.red_bgm_combo.setObjectName("urlInput")
        self.red_bgm_combo.addItems(["None", "Lofi Chill", "Spooky Ambient", "Custom File (.mp3/.wav)"])
        self.red_bgm_combo.setFixedHeight(44)
        self.red_bgm_combo.currentTextChanged.connect(self._on_red_bgm_changed)
        stg.addWidget(self.red_bgm_combo, 3, 2)

        stg.addWidget(QLabel("Background Music Volume:"), 4, 0)
        self.red_bgm_vol = QSlider(Qt.Orientation.Horizontal)
        self.red_bgm_vol.setRange(0, 100)
        self.red_bgm_vol.setValue(15)
        self.red_bgm_vol.setToolTip("BGM Volume")
        self.red_bgm_vol.setFixedHeight(44)
        stg.addWidget(self.red_bgm_vol, 4, 1, 1, 2)
        
        self.red_bg_custom = QLineEdit()
        self.red_bg_custom.setObjectName("urlInput")
        self.red_bg_custom.setPlaceholderText("Custom Background URL...")
        self.red_bg_custom.setFixedHeight(44)
        self.red_bg_custom.setVisible(False)
        stg.addWidget(self.red_bg_custom, 5, 1, 1, 2)
        
        self.red_bgm_custom = QLineEdit()
        self.red_bgm_custom.setObjectName("urlInput")
        self.red_bgm_custom.setPlaceholderText("Custom BGM Path...")
        self.red_bgm_custom.setFixedHeight(44)
        self.red_bgm_custom.setVisible(False)
        stg.addWidget(self.red_bgm_custom, 5, 1, 1, 2)
        
        stg.addWidget(QLabel("Subreddit:"), 6, 0)
        self.red_sub = QLineEdit()
        self.red_sub.setObjectName("urlInput")
        self.red_sub.setFixedHeight(44)
        stg.addWidget(self.red_sub, 6, 1, 1, 2)
        
        stg.addWidget(QLabel("Title:"), 7, 0)
        self.red_title = QLineEdit()
        self.red_title.setObjectName("urlInput")
        self.red_title.setFixedHeight(44)
        stg.addWidget(self.red_title, 7, 1, 1, 2)
        
        stg.addWidget(QLabel("Voice Speed:"), 8, 0)
        self.red_speed = QComboBox()
        self.red_speed.setObjectName("urlInput")
        self.red_speed.addItems(["0.8x", "0.9x", "1.0x (Default)", "1.1x", "1.2x", "1.3x", "1.5x"])
        self.red_speed.setCurrentText("1.0x (Default)")
        self.red_speed.setFixedHeight(44)
        self.red_speed.currentTextChanged.connect(self._update_length_estimate)
        stg.addWidget(self.red_speed, 8, 1, 1, 2)
        
        ll.addWidget(settings_widget)
        
        ll.addWidget(QLabel("Story Script:"))
        self.red_story = QTextEdit()
        self.red_story.setObjectName("urlInput")
        self.red_story.setMinimumHeight(120)
        self.red_story.textChanged.connect(self._update_length_estimate)
        ll.addWidget(self.red_story, 1)
        
        self.red_estimator = QLabel("Estimated Length: ~0 seconds")
        self.red_estimator.setStyleSheet("color: #88a; font-size: 11px;")
        ll.addWidget(self.red_estimator)
        
        self.red_prog = QProgressBar()
        self.red_prog.setObjectName("progressBar")
        self.red_prog.setFixedHeight(6)
        self.red_prog.setRange(0, 100)
        self.red_prog.setValue(0)
        self.red_prog.setTextVisible(False)
        ll.addWidget(self.red_prog)
        
        self.red_status = QLabel("Ready")
        self.red_status.setObjectName("statusLabel")
        ll.addWidget(self.red_status)
        
        self.red_dropdown_chk = QCheckBox("Dropdown Story (Scrolling text)")
        self.red_dropdown_chk.setStyleSheet("color: #e8e8f0; font-weight: bold; margin-bottom: 5px; padding: 5px;")
        ll.addWidget(self.red_dropdown_chk)

        self.red_dropdown_comment_chk = QCheckBox("Dropdown + Comment")
        self.red_dropdown_comment_chk.setStyleSheet("color: #e8e8f0; font-weight: bold; margin-bottom: 5px; padding: 5px;")
        ll.addWidget(self.red_dropdown_comment_chk)

        self.red_top_comment_chk = QCheckBox("Include Top Comment")
        self.red_top_comment_chk.setChecked(True)
        self.red_top_comment_chk.setStyleSheet("color: #e8e8f0; font-weight: bold; margin-bottom: 5px; padding: 5px;")
        ll.addWidget(self.red_top_comment_chk)
        
        self.red_fast_mode_chk = QCheckBox("Fast Mode (Faster Rendering, Linear Interpolation)")
        self.red_fast_mode_chk.setStyleSheet("color: #e8e8f0; font-weight: bold; margin-bottom: 5px; padding: 5px;")
        ll.addWidget(self.red_fast_mode_chk)
        
        self.red_gpu_chk = QCheckBox("GPU Acceleration Mode (NVENC/AMF)")
        self.red_gpu_chk.setChecked(True)
        self.red_gpu_chk.setStyleSheet("color: #e8e8f0; font-weight: bold; margin-bottom: 20px; padding: 5px;")
        ll.addWidget(self.red_gpu_chk)
        
        red_btn_row = QHBoxLayout()
        self.red_btn = QPushButton("Generate Reddit Clip")
        self.red_btn.setObjectName("analyzeBtn")
        self.red_btn.setFixedHeight(50)
        self.red_btn.clicked.connect(self._start_reddit)
        
        self.red_stop_btn = QPushButton("Stop")
        self.red_stop_btn.setObjectName("openFolderBtn")
        self.red_stop_btn.setFixedHeight(50)
        self.red_stop_btn.setFixedWidth(100)
        self.red_stop_btn.setEnabled(False)
        self.red_stop_btn.clicked.connect(self._stop_reddit)
        
        red_btn_row.addWidget(self.red_btn, 1)
        red_btn_row.addWidget(self.red_stop_btn)
        ll.addLayout(red_btn_row)
        
        rd_layout.addWidget(left_panel, 2)

        right_panel = QWidget()
        rl = QVBoxLayout(right_panel)
        rl.setContentsMargins(10, 10, 10, 10)
        
        self.red_vp = QVideoWidget()
        self.red_vp.setStyleSheet("background: #000; border-radius: 16px;")
        rl.addWidget(self.red_vp, 1)
        
        self.red_player = QMediaPlayer()
        if self.audio_output:
            self.red_player.setAudioOutput(self.audio_output)
        self.red_player.setVideoOutput(self.red_vp)
        
        ctrl = QHBoxLayout()
        self.rplay_btn = QPushButton("Play")
        self.rplay_btn.setObjectName("exportBtn")
        self.rplay_btn.setFixedHeight(40)
        self.rplay_btn.clicked.connect(lambda: self.red_player.pause() if self.red_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState else self.red_player.play())
        self.ropen_btn = QPushButton("Open Folder")
        self.ropen_btn.setObjectName("openFolderBtn")
        self.ropen_btn.setFixedHeight(40)
        self.ropen_btn.clicked.connect(self._open_exports)
        ctrl.addWidget(self.rplay_btn)
        ctrl.addWidget(self.ropen_btn)
        rl.addLayout(ctrl)
        
                                   
        export_row = QHBoxLayout()
        self.red_export_path = QLineEdit()
        self.red_export_path.setObjectName("urlInput")
        self.red_export_path.setPlaceholderText("Default export folder...")
        self.red_export_path.setFixedHeight(44)
        
        self.red_browse_btn = QPushButton("Change Export Folder")
        self.red_browse_btn.setObjectName("openFolderBtn")
        self.red_browse_btn.setFixedHeight(44)
        self.red_browse_btn.clicked.connect(self._browse_reddit_export)
        
        export_row.addWidget(self.red_export_path, 1)
        export_row.addWidget(self.red_browse_btn)
        rl.addLayout(export_row)
        
        rd_layout.addWidget(right_panel, 1)
        
        scroll.setWidget(container)
        main_layout.addWidget(scroll)
        return parent

    def _scrape_reddit(self):
        url = self.red_scrape.text().strip()
        if not url: return
        try:
            from doogclips.reddit_pipeline import scrape_reddit_post
            btn = self.sender()
            old_txt = btn.text()
            btn.setText("Scraping...")
            btn.setEnabled(False)
            
            post = scrape_reddit_post(url)
            
            self.red_title.setText(post["title"])
            self.red_story.setPlainText(post["story"])
            self.red_sub.setText(post["subreddit"])
            self.red_post_id = post.get("id")                              
            self.red_post_meta = {
                "author": post.get("author"),
                "created_utc": post.get("created_utc"),
                "score": post.get("score"),
                "num_comments": post.get("num_comments")
            }
            self.red_comment_data = post.get("comment")
            self.red_sub_icon_url = post.get("sub_icon")
            
            btn.setText(old_txt)
            btn.setEnabled(True)
        except Exception as e:
            QMessageBox.warning(self, "Error Scraping", f"Failed: {str(e)}")
            self.sender().setText("Scrape UI")
            self.sender().setEnabled(True)


    def _scrape_subreddit_auto(self):
        sub = self.bulk_sub_name.text().strip()
        if not sub:
            QMessageBox.warning(self, "Input Error", "Please enter a subreddit name.")
            return
            
        limit = self.bulk_sub_count.value()
        time_filter = self.bulk_sub_time.currentText()
        min_d = self.bulk_sub_min.value()
        max_d = self.bulk_sub_max.value()
        
        try:
            from doogclips.reddit_pipeline import scrape_subreddit, estimate_duration, load_history
            
            btn = self.sender()
            btn.setText("Scraping...")
            btn.setEnabled(False)
            
            posts = scrape_subreddit(sub, limit, time_filter)
            history = load_history()
            
            valid_urls = []
            skipped_history = 0
            skipped_duration = 0
            
            for p in posts:
                if p['id'] in history:
                    skipped_history += 1
                    continue
                
                dur = estimate_duration(p['title'], p['story'])
                if dur < min_d or dur > max_d:
                    skipped_duration += 1
                    continue
                    
                valid_urls.append(p['url'])
                if len(valid_urls) >= limit:
                    break
            
            if valid_urls:
                current = self.bulk_urls_input.toPlainText().strip()
                if current:
                    new_text = current + "\n" + "\n".join(valid_urls)
                else:
                    new_text = "\n".join(valid_urls)
                self.bulk_urls_input.setPlainText(new_text)
                
                self.bulk_log.append(f"[Scraper] Added {len(valid_urls)} stories from r/{sub}.")
                if skipped_history or skipped_duration:
                    self.bulk_log.append(f"[Scraper] Filtered out {skipped_history} dupes and {skipped_duration} off-length stories.")
            else:
                QMessageBox.information(self, "No Results", "No new stories found matching your filters.")
                
            btn.setText("Scrape Stories")
            btn.setEnabled(True)
            
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed: {str(e)}")
            self.sender().setText("Scrape Stories")
            self.sender().setEnabled(True)

    def _update_length_estimate(self):
        text = self.red_story.toPlainText()
        words = len(text.split())
        
                           
        spd_txt = self.red_speed.currentText().split("x")[0]
        try:
            pace = float(spd_txt)
        except:
            pace = 1.0
            
        est_secs = int((words / 2.5) / pace) if words > 0 else 0
        self.red_estimator.setText(f"Estimated Length: ~{est_secs} seconds")

    def _update_voice_dropdowns(self):
                                              
        clones = []
        if os.path.exists(CLONE_DIR):
            for f in os.listdir(CLONE_DIR):
                if f.endswith(".wav") and f != "test_voice.wav":
                    clones.append(f"Clone: {os.path.splitext(f)[0].replace('_', ' ').title()}")
        
                                    
        current = self.red_voice.currentText()
                           
        for i in reversed(range(self.red_voice.count())):
            txt = self.red_voice.itemText(i)
            if txt.startswith("Clone:"):
                self.red_voice.removeItem(i)
        
                                                            
        idx = self.red_voice.count() - 1
        for c in clones:
            self.red_voice.insertItem(idx, c)
            idx += 1
            
        if current in [self.red_voice.itemText(i) for i in range(self.red_voice.count())]:
            self.red_voice.setCurrentText(current)
            
    def _on_red_voice_changed(self, text):
        self.red_audio_input.setVisible(text == "Custom Audio File (.mp3/.wav)")
        
    def _on_red_bg_changed(self, text):
        self.red_bg_custom.setVisible("Custom" in text)

    def _on_red_bgm_changed(self, text):
        self.red_bgm_custom.setVisible("Custom" in text)

    def _resolve_font_path(self):
        text = self.font_family_combo.currentText()
        if text == "Mr Beast Font":
            return resolve_path("assets/fonts/MrBeast.ttf")
        if text == "Custom..." and self.custom_font_path:
            return self.custom_font_path
        return text

    def _tick_preview(self):
        self.preview_time += 0.1
        if self.preview_time > 3.0:
            self.preview_time = 0.0
        self._trigger_preview_update()


    def _start_bulk_reddit(self):
        urls = self.bulk_urls_input.toPlainText().strip().split("\n")
        urls = [u.strip() for u in urls if u.strip()]
        if not urls:
            QMessageBox.warning(self, "Bulk Creator", "Please paste at least one Reddit URL!")
            return
            
        font_settings = {
            'color1': self.COLORS.get(self.color_combo.currentText(), (255, 220, 0)),
            'color2': self.COLORS.get(self.color2_combo.currentText(), (255, 255, 255)),
            
            'style': self.style_combo.currentText(),
            'family': self._resolve_font_path(),
            'size': self.font_spin.value(),

            'stroke': self.stroke_spin.value(),
            'glow': self.glow_chk.isChecked(),
            'use_slide': self.slide_chk.isChecked(),
            'emoji': self.emoji_chk.isChecked(),
            'pbar': self.pbar_chk.isChecked(),
            'mw': 3
        }
        mwords = self.words_combo.currentText()
        if mwords == "Automax": font_settings['mw'] = 4
        else: font_settings['mw'] = int(mwords.split(" ")[0])
        
                                                         
        bg_settings = {
            'type': self.red_bg_combo.currentText(),
            'custom': self.red_bg_custom.text().strip(),
            'bgm_type': self.red_bgm_combo.currentText(),
            'bgm_custom': self.red_bgm_custom.text().strip(),
            'bgm_volume': self.red_bgm_vol.value() / 100.0
        }
        
                        
        voice_sel = self.red_voice.currentText()
        vid = "en-US-ChristopherNeural"
        if "Guy" in voice_sel: vid = "en-US-GuyNeural"
        elif "Aria" in voice_sel: vid = "en-US-AriaNeural"
        elif "Jenny" in voice_sel: vid = "en-US-JennyNeural"
        elif "Brian" in voice_sel: vid = "en-US-BrianNeural"
        elif "Emma" in voice_sel: vid = "en-US-EmmaNeural"
        elif "Andrew" in voice_sel: vid = "en-US-AndrewNeural"
        elif "Sonia" in voice_sel: vid = "en-GB-SoniaNeural"
        elif "Ryan" in voice_sel: vid = "en-GB-RyanNeural"
        elif "Natasha" in voice_sel: vid = "en-AU-NatashaNeural"
        elif "William" in voice_sel: vid = "en-AU-WilliamNeural"
        elif "Clone:" in voice_sel:
            vid = "cloned"
                                                            
            voice_name = voice_sel.replace("Clone: ", "").replace(" ", "_").lower() + ".wav"
            self.red_audio_input.setText(os.path.join(CLONE_DIR, voice_name))
        elif "Custom" in voice_sel: vid = "custom"
        
        voice_settings = {
            'id': vid,
            'custom_path': self.red_audio_input.text().strip()
        }
        
        self.bulk_log.clear()
        self.bulk_log.append(">>> Starting Bulk Process...")
        self.bulk_start_btn.setEnabled(False)
        self.bulk_stop_btn.setEnabled(True)
        self.bulk_prog_batch.setRange(0, len(urls))
        self.bulk_prog_batch.setValue(0)
        
        spd_txt = self.red_speed.currentText().split("x")[0]
        try:
            val = float(spd_txt)
            pct = int((val - 1.0) * 100)
            voice_rate = f"{'+' if pct >= 0 else ''}{pct}%"
        except:
            voice_rate = "+0%"
        
        use_dropdown_comment = self.bulk_dropdown_comment_chk.isChecked()
        use_top_comment = self.bulk_top_comment_chk.isChecked()
        self.bulk_thread = BulkRedditThread(
            urls, bg_settings, font_settings, voice_settings, 
            use_dropdown=self.bulk_dropdown_chk.isChecked() or use_dropdown_comment,
            use_dropdown_comment=use_dropdown_comment,
            use_top_comment=use_top_comment,
            whisper_engine=self.red_whisper_model.currentText(),
            voice_rate=voice_rate
        )
        self.bulk_thread.log.connect(lambda msg: self.bulk_log.append(msg))
        self.bulk_thread.progress.connect(self._on_bulk_clip_prog)
        self.batch_progress_val = 0 
        self.bulk_thread.batch_progress.connect(self._on_bulk_batch_prog)
        self.bulk_thread.finished.connect(self._on_bulk_finished)
        self.bulk_thread.error.connect(lambda e: QMessageBox.critical(self, "Bulk Error", e))
        self.bulk_thread.start()

    def _scrape_subreddit_auto(self):
        sub = self.bulk_sub_name.text().strip()
        if not sub:
            QMessageBox.warning(self, "Bulk Creator", "Please enter a subreddit name!")
            return
            
        count = self.bulk_sub_count.value()
        time_f = self.bulk_sub_time.currentText()
        min_d = self.bulk_sub_min.value()
        max_d = self.bulk_sub_max.value()
        
        self.bulk_log.append(f">>> Scraping r/{sub} ({time_f}). Please wait...")
        self.bulk_scrape_btn.setEnabled(False)
        QApplication.processEvents()
        
        try:
            from doogclips.reddit_pipeline import scrape_subreddit, estimate_duration, load_history
            
            all_posts = scrape_subreddit(sub, limit=count * 5, time_filter=time_f)
            history = load_history()
            
            valid_urls = []
            for p in all_posts:
                if p["id"] in history:
                    continue
                    
                dur = estimate_duration(p["title"], p["story"])
                if min_d <= dur <= max_d:
                    valid_urls.append(p["url"])
                    if len(valid_urls) >= count:
                        break
            
            if not valid_urls:
                self.bulk_log.append("!!! No new stories found matching your filters.")
                QMessageBox.information(self, "Scrape", "No new stories found matching filters correctly.")
            else:
                current_text = self.bulk_urls_input.toPlainText().strip()
                new_text = "\n".join(valid_urls)
                if current_text:
                    self.bulk_urls_input.setPlainText(current_text + "\n" + new_text)
                else:
                    self.bulk_urls_input.setPlainText(new_text)
                self.bulk_log.append(f">>> Successfully scraped {len(valid_urls)} stories!")
                
        except Exception as e:
            self.bulk_log.append(f"!!! Scrape failed: {e}")
            QMessageBox.critical(self, "Scrape Error", str(e))
        finally:
            self.bulk_scrape_btn.setEnabled(True)

    def _cancel_bulk_reddit(self):
        if hasattr(self, 'bulk_thread') and self.bulk_thread.isRunning():
            self.bulk_thread.cancel()
            self.bulk_log.append("!!! Cancellation requested...")
            self.bulk_stop_btn.setEnabled(False)

    def _on_bulk_clip_prog(self, msg, pct):
        self.bulk_prog_clip.setValue(pct)
        self.bulk_status.setText(f"Status: {msg}")

    def _on_bulk_batch_prog(self, cur, total):
        self.bulk_prog_batch.setValue(cur)
        self.bulk_status.setText(f"Batch Progress: {cur}/{total} clips finished")

    def _on_bulk_finished(self, results):
        self.bulk_start_btn.setEnabled(True)
        self.bulk_stop_btn.setEnabled(False)
        self.bulk_status.setText(f"Batch Complete! {len(results)} clips created.")
        self.bulk_log.append(f">>> FINISHED. Total clips exported: {len(results)}")
        QMessageBox.information(self, "Bulk Process", f"Successfully created {len(results)} clips!")

    def _trigger_preview_update(self, is_major=False):
        try:
            from doogclips.subtitle_renderer import render_subtitle_frame
            import cv2
            import numpy as np
            from PyQt6.QtGui import QImage, QPixmap
            from PyQt6.QtCore import Qt

                                               
            dummy_frame = np.full((1920, 1080, 3), 15, dtype=np.uint8)
            for y in range(1920):
                dummy_frame[y, :] = [30 + int((y / 1920) * 30), 20 + int((y / 1920) * 20), 40]

                          
            dummy_words = [
                {"word": "AWESOME", "start": 0.0, "end": 1.0},
                {"word": "VIRAL", "start": 1.0, "end": 2.0},
                {"word": "CLIPS", "start": 2.0, "end": 3.0}
            ]
            
            color = self.COLORS.get(self.color_combo.currentText(), (255, 220, 0))
            color2 = self.COLORS.get(self.color2_combo.currentText(), (255, 255, 255))
            style = self.style_combo.currentText()
            fsize = self.font_spin.value()
            mwords = self.words_combo.currentText()
            font_fam = self._resolve_font_path()
            stroke_w = self.stroke_spin.value()
            use_glow = self.glow_chk.isChecked()
            use_slide = self.slide_chk.isChecked()
            emoji = self.emoji_chk.isChecked()
            pbar = self.pbar_chk.isChecked()
            if mwords == "Automax": max_w = 4
            else: max_w = int(mwords.split(" ")[0])

            rendered = render_subtitle_frame(
                dummy_frame, dummy_words, current_time=self.preview_time,
                frame_w=1080, frame_h=1920, 
                highlight_color=color, secondary_color=color2, font_size=fsize, max_words=max_w, style=style, font_family=font_fam, stroke_width=stroke_w, use_glow=use_glow, use_slide=use_slide,
                enable_emojis=emoji, show_progress_bar=pbar, duration=3.0
            )

            rgb_img = cv2.cvtColor(rendered, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb_img.shape
            bpl = ch * w
            qimg = QImage(rgb_img.data, w, h, bpl, QImage.Format.Format_RGB888)
            scaled = qimg.scaled(self.preview_label.width(), self.preview_label.height(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.preview_label.setPixmap(QPixmap.fromImage(scaled))
        except Exception as e:
            print("Preview update error:", e)

    def _init_player(self):
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.audio_output.setVolume(1.0)
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_widget)
        self.player.playbackStateChanged.connect(self._on_playback_changed)

    def _start_analysis(self):
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "DoogClips", "Please paste a YouTube URL first.")
            return
        if self.analysis_thread and self.analysis_thread.isRunning():
            return
        
        color = self.COLORS.get(self.color_combo.currentText(), (255, 220, 0))
        color2 = self.COLORS.get(self.color2_combo.currentText(), (255, 255, 255))
        style = self.style_combo.currentText()
        font_fam = self._resolve_font_path()
        stroke_w = self.stroke_spin.value()

        glow = self.glow_chk.isChecked()
        use_slide = self.slide_chk.isChecked()
        emoji = self.emoji_chk.isChecked()
        pbar = self.pbar_chk.isChecked()
        min_d = self.min_dur_sp.value()
        max_d = self.max_dur_sp.value()
        mc = self.max_clips_sp.value()
        gp = self.gameplay_chk.isChecked()
        
        bg = self.bg_clip_combo.currentText()
        bgc = self.bg_clip_custom.text().strip()
        bgm = self.bgm_clip_combo.currentText()
        bgmc = self.bgm_clip_custom.text().strip()
        
        fsz = self.font_spin.value()
        mwords = self.words_combo.currentText()
        if mwords == "Automax": max_w = 4
        else: max_w = int(mwords.split(" ")[0])
        
        self.analyze_btn.setEnabled(False)
        self.analyze_btn.setText("Analyzing...")
        self.progress_bar.setValue(0)
        
        from doogclips.transcriber import set_model
        set_model(self.whisper_model_combo.currentText())
        
        bgm_vol = self.clip_bgm_vol.value() / 100.0
        
        self._clear_cards()
        
        speaker_colors = [
            self.COLORS.get(self.spk1_combo.currentText(), (255,220,0)),
            self.COLORS.get(self.spk2_combo.currentText(), (255,255,255)),
            self.COLORS.get(self.spk3_combo.currentText(), (50,255,50)),
            self.COLORS.get(self.spk4_combo.currentText(), (50,150,255))
        ]
        
        ts = self.track_strength_sp.value()
        fc = self.facecam_chk.isChecked()
        ct = self.custom_title_input.text().strip()
        
        self.analysis_thread = AnalysisThread(url, mc, min_d, max_d, color, gp, bg, bgc, bgm, bgmc, fsz, max_w, style, color2, font_fam, stroke_w, glow, use_slide, emoji, pbar, bgm_volume=bgm_vol, speaker_colors=speaker_colors, track_strength=ts, use_facecam=fc, custom_title=ct, use_gpu=self.gpu_chk.isChecked())
        self.analysis_thread.progress.connect(self._on_progress)
        self.analysis_thread.finished.connect(self._on_done)
        self.analysis_thread.error.connect(self._on_error)
        self.analysis_thread.start()
        
    def _start_reddit(self):
        t = self.red_title.text().strip()
        s = self.red_story.toPlainText().strip()
        sub = self.red_sub.text().strip()
        
        if not t or not s:
            QMessageBox.warning(self, "Reddit Generator", "Please provide both a Title and a Story!")
            return
            
        voice_sel = self.red_voice.currentText()
        if "GUY" in voice_sel.upper():
            vid = "en-US-GuyNeural"
        elif "ARIA" in voice_sel.upper():
            vid = "en-US-AriaNeural"
        elif "JENNY" in voice_sel.upper():
            vid = "en-US-JennyNeural"
        elif "BRIAN" in voice_sel.upper():
            vid = "en-US-BrianNeural"
        elif "EMMA" in voice_sel.upper():
            vid = "en-US-EmmaNeural"
        elif "ANDREW" in voice_sel.upper():
            vid = "en-US-AndrewNeural"
        elif "SONIA" in voice_sel.upper():
            vid = "en-GB-SoniaNeural"
        elif "RYAN" in voice_sel.upper():
            vid = "en-GB-RyanNeural"
        elif "NATASHA" in voice_sel.upper():
            vid = "en-AU-NatashaNeural"
        elif "WILLIAM" in voice_sel.upper():
            vid = "en-AU-WilliamNeural"
        elif "CLONE:" in voice_sel.upper():
            vid = "cloned"
            voice_name = voice_sel.replace("Clone: ", "").replace(" ", "_").lower() + ".wav"
            self.red_audio_input.setText(os.path.join(CLONE_DIR, voice_name))
        elif "CUSTOM" in voice_sel.upper():
            vid = "custom"
        else:
            vid = "en-US-ChristopherNeural"
        
        cust_aud = self.red_audio_input.text().strip()
        if vid == "custom" and not cust_aud:
            QMessageBox.warning(self, "Reddit Generator", "Please provide a path to your custom audio file!")
            return
            
        if self.reddit_thread and self.reddit_thread.isRunning():
            return
            
        color = self.COLORS.get(self.color_combo.currentText(), (255, 220, 0))
        color2 = self.COLORS.get(self.color2_combo.currentText(), (255, 255, 255))
        style = self.style_combo.currentText()
        font_fam = self._resolve_font_path()
        stroke_w = self.stroke_spin.value()

        glow = self.glow_chk.isChecked()
        use_slide = self.slide_chk.isChecked()
        emoji = self.emoji_chk.isChecked()
        pbar = self.pbar_chk.isChecked()
        
        bg = self.red_bg_combo.currentText()
        bgc = self.red_bg_custom.text().strip()
        bgm = self.red_bgm_combo.currentText()
        bgmc = self.red_bgm_custom.text().strip()
        
        fsz = self.font_spin.value()
        mwords = self.words_combo.currentText()
        if mwords == "Automax": max_w = 4
        else: max_w = int(mwords.split(" ")[0])
        spd_txt = self.red_speed.currentText().split("x")[0]
        try:
            val = float(spd_txt)
            pct = int((val - 1.0) * 100)
            voice_rate = f"{'+' if pct >= 0 else ''}{pct}%"
        except:
            voice_rate = "+0%"
            
        custom_out = None
        if self.red_export_path.text().strip():
            import time
            out_name = "".join(c for c in t[:20] if c.isalnum() or c in " _-").strip().replace(" ", "_")
            if not out_name: out_name = "reddit_clip"
            custom_out = os.path.join(self.red_export_path.text().strip(), f"{out_name}_{int(time.time())}.mp4")

        bgm_v = self.red_bgm_vol.value() / 100.0

        use_dropdown_comment = self.red_dropdown_comment_chk.isChecked()
        use_top_comment = self.red_top_comment_chk.isChecked()
        self.reddit_thread = RedditThread(
            t, s, bg, bgc, bgm, bgmc, color, fsz, max_w, sub, vid, cust_aud,
            style, color2, font_fam, stroke_w, glow, use_slide, emoji, pbar,
            voice_rate=voice_rate, out_path=custom_out,
            use_dropdown=self.red_dropdown_chk.isChecked() or use_dropdown_comment,
            use_dropdown_comment=use_dropdown_comment,
            use_top_comment=use_top_comment,
            post_meta=getattr(self, 'red_post_meta', None),
            comment_data=getattr(self, 'red_comment_data', None),
            subreddit_icon_url=getattr(self, 'red_sub_icon_url', None),
            post_id=getattr(self, 'red_post_id', None),
            whisper_engine=self.red_whisper_model.currentText(),
            bgm_volume=bgm_v,
            fast_mode=self.red_fast_mode_chk.isChecked(),
            use_gpu=self.red_gpu_chk.isChecked()
        )
        self.reddit_thread.progress.connect(self._on_red_prog)
        self.reddit_thread.finished.connect(self._on_red_done)
        self.reddit_thread.error.connect(self._on_red_err)
        self.reddit_thread.start()
        
    def _stop_reddit(self):
        if self.reddit_thread and self.reddit_thread.isRunning():
            self.reddit_thread.cancel()
            self.red_status.setText("Stopping...")
            self.red_stop_btn.setEnabled(False)

    def _preview_reddit_voice(self):
                            
        cur_voice = self.red_voice.currentText()
        if "Cloned" in cur_voice or "Custom" in cur_voice:
            QMessageBox.information(self, "Preview", "Preview is only for the AI voices.")
            return
            
        v_up = cur_voice.upper()
        if "GUY" in v_up: vid = "en-US-GuyNeural"
        elif "ARIA" in v_up: vid = "en-US-AriaNeural"
        elif "JENNY" in v_up: vid = "en-US-JennyNeural"
        elif "BRIAN" in v_up: vid = "en-US-BrianNeural"
        elif "EMMA" in v_up: vid = "en-US-EmmaNeural"
        elif "ANDREW" in v_up: vid = "en-US-AndrewNeural"
        elif "SONIA" in v_up: vid = "en-GB-SoniaNeural"
        elif "RYAN" in v_up: vid = "en-GB-RyanNeural"
        elif "NATASHA" in v_up: vid = "en-AU-NatashaNeural"
        elif "WILLIAM" in v_up: vid = "en-AU-WilliamNeural"
        else: vid = "en-US-ChristopherNeural"
        ext = ".mp3"
        
        text = "Hello. This is how the current voice sounds."
        
                         
        short_name = f"pv{ext}"
        temp_preview = os.path.abspath(short_name)
        
                             
        self.red_voice_preview_btn.setEnabled(False)
        self.red_voice_preview_btn.setText("⏳")
        
        from doogclips.reddit_pipeline import generate_reddit_audio
        
        try:
            if self.red_player:
                self.red_player.stop()
            
                                                      
            try:
                if os.path.exists(temp_preview): os.remove(temp_preview)
            except: pass
                
            generate_reddit_audio(text, temp_preview, vid)
            
            if self.red_player is None or self.red_audio_out is None:
                self.red_player = QMediaPlayer(self)
                self.red_audio_out = QAudioOutput(self)
                self.red_player.setAudioOutput(self.red_audio_out)
                self.red_player.mediaStatusChanged.connect(self._on_red_preview_status)
            
                                  
            self.red_audio_out.setVolume(1.0)
            self.red_audio_out.setMuted(False)
            
            self.red_player.setSource(QUrl.fromLocalFile(temp_preview))
                                           
            QTimer.singleShot(200, self.red_player.play)
        except Exception as e:
            QMessageBox.warning(self, "Preview Error", str(e))
        finally:
                              
            QTimer.singleShot(1500, lambda: self.red_voice_preview_btn.setEnabled(True))
            QTimer.singleShot(1500, lambda: self.red_voice_preview_btn.setText("▶️ Preview"))

    def _browse_reddit_export(self):
        d = QFileDialog.getExistingDirectory(self, "Select Export Folder")
        if d:
            self.red_export_path.setText(d)

    def _on_whisper_model_changed(self, text):
                                              
        if text == "large-v3":
            self.status_label.setText("Whisper: Large-v3 selected (High quality, slower heavy load)")
        else:
            self.status_label.setText("Whisper: Base model selected (Faster, lower accuracy)")

    def _on_red_prog(self, msg, pct):
        self.red_prog.setValue(pct)
        self.red_status.setText(msg)
        
    def _on_red_done(self, out):
        self.red_btn.setEnabled(True)
        self.red_stop_btn.setEnabled(False)
        self.red_prog.setValue(100)
        self.red_status.setText("Done!")
        
                                    
        target = out[0] if isinstance(out, list) and out else out
        
        if target and os.path.exists(target):
            self.red_player.setSource(QUrl.fromLocalFile(target))
            self.red_player.play()
            
            if isinstance(out, list) and len(out) > 1:
                QMessageBox.information(self, "Multi-Part Story", f"Created {len(out)} parts! Playing the first part now.")
            
    def _on_red_err(self, err):
        self.red_btn.setEnabled(True)
        self.red_stop_btn.setEnabled(False)
        self.red_prog.setValue(0)
        if err == "Cancelled":
            self.red_status.setText("Cancelled")
        else:
            self.red_status.setText("Error!")
            QMessageBox.critical(self, "Error", err)

    def _on_progress(self, msg, pct):
        self.progress_bar.setValue(pct)
        self.status_label.setText(msg)

    def _on_done(self, clips):
        self.clips = clips
        self.analyze_btn.setEnabled(True)
        self.analyze_btn.setText("Analyze Video")
        self.progress_bar.setValue(100)
        self.status_label.setText("Done! Found " + str(len(clips)) + " viral clips.")
        self._clear_cards()
        if self.empty_label:
            self.empty_label.hide()
        for clip in clips:
            card = ClipCard(clip)
            card.clicked.connect(self._on_clip_selected)
            self.clip_cards.append(card)
            self.cards_layout.addWidget(card)
        if clips:
            self._on_clip_selected(clips[0])

    def _on_error(self, error):
        self.analyze_btn.setEnabled(True)
        self.analyze_btn.setText("Analyze Video")
        self.progress_bar.setValue(0)
        self.status_label.setText("Analysis failed.")
        QMessageBox.critical(self, "DoogClips - Error", "Analysis failed:\n\n" + error[:800])

    def _on_clip_selected(self, clip):
        self.selected_clip = clip
        for card in self.clip_cards:
            card.set_selected(card.clip == clip)
        if hasattr(clip, 'video_path') and os.path.exists(clip.video_path):
            self.player.setSource(QUrl.fromLocalFile(clip.video_path))
            self.preview_stack.setCurrentIndex(1)
            self.player.play()
            self.play_btn.setText("Pause")
        
        c = clip.candidate
        @dataclass
        class DummyC:
            score=0; virality_label=""; end=0; start=0; reasons=[]
        
        score_v = int(c.score) if hasattr(c, 'score') else 99
        v_l = c.virality_label if hasattr(c, 'virality_label') else "Epic Moment"
        if hasattr(clip, 'duration'): dur = clip.duration
        else: dur = 30
        if hasattr(clip, 'layout'): lay = clip.layout
        else: lay = ""
        details = "Virality: " + str(score_v) + "/100  |  " + v_l + "  |  " + str(int(dur)) + "s  |  " + lay.title() + " speaker"
        if hasattr(c, 'reasons') and c.reasons:
            details += "\nKeywords: " + ", ".join(c.reasons[:3])
        self.clip_details.setText(details)

    def _toggle_play(self):
        if not self.player: return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _on_playback_changed(self, state):
        self.play_btn.setText("Pause" if state == QMediaPlayer.PlaybackState.PlayingState else "Play")

    def _clear_cards(self):
        for card in self.clip_cards:
            self.cards_layout.removeWidget(card)
            card.deleteLater()
        self.clip_cards.clear()
        self.selected_clip = None

    def _export_selected(self):
        if not self.selected_clip:
            QMessageBox.information(self, "DoogClips", "Select a clip first.")
            return
        if hasattr(self.selected_clip, 'video_path') and os.path.exists(self.selected_clip.video_path):
            self.status_label.setText("Clip ready: " + os.path.basename(self.selected_clip.video_path))
            self._open_exports()
        else:
            QMessageBox.warning(self, "DoogClips", "Clip file not found.")

    def _export_all(self):
        if not self.clips:
            QMessageBox.information(self, "DoogClips", "No clips to export. Analyze a video first.")
            return
        self._open_exports()

    def _open_exports(self):
        d = resolve_path("exports")
        os.makedirs(d, exist_ok=True)
        os.startfile(d)

    def _apply_mrbeast_preset(self):
                           
        self.font_family_combo.setCurrentText("Custom...")
        self.custom_font_path = resolve_path("assets/fonts/MrBeast.ttf")
        self.style_combo.setCurrentText("Pop")
        self.color_combo.setCurrentText("White")
        self.color2_combo.setCurrentText("Yellow")
        self.font_spin.setValue(110)
        self.stroke_spin.setValue(10)
        self.words_combo.setCurrentText("1 Word")
        self.glow_chk.setChecked(True)
        self.slide_chk.setChecked(True)
        self.emoji_chk.setChecked(True)
        self.pbar_chk.setChecked(True)
        self._trigger_preview_update(True)

    def _apply_hormozi_preset(self):
                           
        self.font_family_combo.setCurrentText("Impact")
        self.style_combo.setCurrentText("Hormozi")
        self.color_combo.setCurrentText("Yellow")
        self.color2_combo.setCurrentText("White")
        self.font_spin.setValue(120)
        self.stroke_spin.setValue(12)
        self.words_combo.setCurrentText("Automax")
        self.glow_chk.setChecked(False)
        self.slide_chk.setChecked(False)
        self.emoji_chk.setChecked(True)
        self.pbar_chk.setChecked(False)
        self._trigger_preview_update(True)

    def closeEvent(self, event):
        if self.player: self.player.stop()
        if self.red_player: self.red_player.stop()
        if self.analysis_thread and self.analysis_thread.isRunning():
            self.analysis_thread.terminate()
        event.accept()
