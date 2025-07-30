# Quick dependency installer
import sys
import subprocess

def install_if_missing(package_name, import_name):
    try:
        __import__(import_name)
    except ImportError:
        print(f"Installing {package_name}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
        print(f"✅ {package_name} installed!")

# Install missing packages
install_if_missing("google-api-python-client", "googleapiclient")
install_if_missing("yt-dlp", "yt_dlp")

"""
RB3Enhanced YouTube Video Player - GUI Version with Web UI Detection
"""

import socket
import struct
import subprocess
import threading
import time
import re
import os
import webbrowser
from typing import Optional, Tuple, Dict
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import yt_dlp
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import json
from datetime import datetime

class YouTubeSearcher:
    """Handles YouTube API searches"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.youtube = None
        self.search_cache: Dict[str, str] = {}
        
        try:
            if api_key and api_key != "YOUR_YOUTUBE_API_KEY_HERE":
                self.youtube = build('youtube', 'v3', developerKey=api_key)
        except Exception as e:
            raise Exception(f"Failed to initialize YouTube API: {e}")
    
    def clean_search_terms(self, artist: str, song: str) -> Tuple[str, str]:
        """Clean up artist and song names for better search results"""
        clean_song = re.sub(r'\s*\([^)]*\)\s*', '', song)
        clean_song = re.sub(r'\s*-\s*(Live|Acoustic|Demo|Remix).*', '', clean_song, flags=re.IGNORECASE)
        clean_song = clean_song.strip()
        
        clean_artist = re.split(r'\s+(?:feat\.|ft\.|featuring)\s+', artist, flags=re.IGNORECASE)[0]
        clean_artist = clean_artist.strip()
        
        return clean_artist, clean_song
    
    def search_video(self, artist: str, song: str) -> Optional[str]:
        """Search for video and return the best match video ID"""
        if not self.youtube:
            return None
            
        clean_artist, clean_song = self.clean_search_terms(artist, song)
        search_key = f"{clean_artist.lower()} - {clean_song.lower()}"
        
        if search_key in self.search_cache:
            return self.search_cache[search_key]
        
        try:
            search_queries = [
                f"{clean_artist} {clean_song} official music video",
                f"{clean_artist} {clean_song} music video",
                f"{clean_artist} {clean_song} official",
                f"{clean_artist} {clean_song}"
            ]
            
            for query in search_queries:
                search_response = self.youtube.search().list(
                    q=query,
                    part='id,snippet',
                    maxResults=5,
                    type='video',
                    videoCategoryId='10',
                    order='relevance'
                ).execute()
                
                for item in search_response['items']:
                    video_title = item['snippet']['title'].lower()
                    video_channel = item['snippet']['channelTitle'].lower()
                    
                    is_official = any(term in video_channel for term in ['official', 'records', 'music', clean_artist.lower()])
                    has_song_in_title = clean_song.lower() in video_title
                    has_artist_in_title = clean_artist.lower() in video_title
                    
                    if (has_song_in_title and has_artist_in_title) or is_official:
                        video_id = item['id']['videoId']
                        self.search_cache[search_key] = video_id
                        return video_id
                
                if search_response['items']:
                    video_id = search_response['items'][0]['id']['videoId']
                    self.search_cache[search_key] = video_id
                    return video_id
            
            return None
            
        except Exception as e:
            raise Exception(f"Search error: {e}")

class VLCPlayer:
    """VLC video player with GUI integration"""
    
    def __init__(self, gui_callback=None):
        self.vlc_path = self.find_vlc()
        self.current_process = None
        self.played_videos = set()
        self.gui_callback = gui_callback
    
    def find_vlc(self) -> Optional[str]:
        """Find VLC executable"""
        possible_paths = [
            r"C:\Program Files\VideoLAN\VLC\vlc.exe",
            r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
            os.path.expanduser(r"~\AppData\Local\Programs\VLC\vlc.exe"),
        ]
        
        try:
            subprocess.run(["vlc", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
            return "vlc"
        except:
            pass
        
        for path in possible_paths:
            if os.path.isfile(path):
                return path
        
        return None
    
    def stop_current_video(self):
        """Stop any currently playing video"""
        if self.current_process and self.current_process.poll() is None:
            try:
                self.current_process.terminate()
                self.current_process.wait(timeout=3)
                if self.gui_callback:
                    self.gui_callback("VLC stopped")
            except subprocess.TimeoutExpired:
                self.current_process.kill()
            except:
                pass
            finally:
                self.current_process = None
    
    def play_video(self, video_url: str, video_id: str, artist: str, song: str, settings: dict):
        """Play video with VLC using GUI settings"""
        if not self.vlc_path:
            if self.gui_callback:
                self.gui_callback("❌ VLC not available")
            return
        
        if video_id in self.played_videos:
            if self.gui_callback:
                self.gui_callback(f"⏭️ Already played: {artist} - {song}")
            return
        
        self.stop_current_video()
        
        try:
            vlc_cmd = [
                self.vlc_path,
                video_url,
                "--intf", "dummy",
                "--no-video-title-show",
                f"--meta-title={artist} - {song}"
            ]
            
            # Add GUI-configured options
            if settings.get('fullscreen', True):
                vlc_cmd.append("--fullscreen")
            
            if settings.get('muted', True):
                vlc_cmd.append("--volume=0")
            
            if settings.get('force_best_quality', True):
                vlc_cmd.extend([
                    "--avcodec-hw=any",
                    "--network-caching=3000",
                ])
            
            self.current_process = subprocess.Popen(
                vlc_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            time.sleep(2)
            
            if self.current_process.poll() is not None:
                vlc_cmd = [self.vlc_path, video_url]
                self.current_process = subprocess.Popen(vlc_cmd)
            
            self.played_videos.add(video_id)
            if len(self.played_videos) > 10:
                self.played_videos.pop()
            
            if self.gui_callback:
                self.gui_callback(f"🎬 Playing: {artist} - {song}")
            
        except Exception as e:
            if self.gui_callback:
                self.gui_callback(f"❌ Error playing video: {e}")

class StreamExtractor:
    """Gets direct video URLs from YouTube"""
    
    def __init__(self, gui_callback=None):
        self.gui_callback = gui_callback
        self.ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'format': 'bestvideo+bestaudio/best',
            'noplaylist': True,
        }
    
    def get_stream_url(self, video_id: str) -> Optional[str]:
        """Get direct stream URL for a YouTube video"""
        try:
            youtube_url = f"https://www.youtube.com/watch?v={video_id}"
            
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info = ydl.extract_info(youtube_url, download=False)
                
                if 'url' in info:
                    return info['url']
                elif 'formats' in info and info['formats']:
                    for fmt in reversed(info['formats']):
                        if fmt.get('url') and fmt.get('vcodec') != 'none':
                            return fmt['url']
            
            return None
            
        except Exception as e:
            if self.gui_callback:
                self.gui_callback(f"❌ Error extracting stream: {e}")
            return None

class RB3EventListener:
    """Listens for RB3Enhanced network events with IP detection"""
    
    RB3E_EVENTS_MAGIC = 0x52423345
    RB3E_EVENTS_PROTOCOL = 0
    RB3E_EVENT_ALIVE = 0
    RB3E_EVENT_STATE = 1
    RB3E_EVENT_SONG_NAME = 2
    RB3E_EVENT_SONG_ARTIST = 3
    
    def __init__(self, youtube_searcher, vlc_player, stream_extractor, gui_callback=None, ip_detected_callback=None):
        self.youtube_searcher = youtube_searcher
        self.vlc_player = vlc_player
        self.stream_extractor = stream_extractor
        self.gui_callback = gui_callback
        self.ip_detected_callback = ip_detected_callback
        self.sock = None
        self.running = False
        self.current_song = ""
        self.current_artist = ""
        self.game_state = 0
        self.pending_video = None
        self.settings = {}
        self.rb3_ip_address = None
        self.last_packet_time = None
    
    def update_settings(self, settings: dict):
        """Update settings from GUI"""
        self.settings = settings.copy()
    
    def start_listening(self):
        """Start listening for RB3Enhanced events"""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.settimeout(5.0)
            self.sock.bind(("0.0.0.0", 21070))
            self.running = True
            
            if self.gui_callback:
                self.gui_callback("🎧 Listening for RB3Enhanced events on port 21070")
            
            no_data_count = 0
            
            while self.running:
                try:
                    data, addr = self.sock.recvfrom(1024)
                    no_data_count = 0
                    
                    # Extract IP address from sender
                    sender_ip = addr[0]
                    self.last_packet_time = datetime.now()
                    
                    # Update detected IP if it's changed or first detection
                    if self.rb3_ip_address != sender_ip:
                        self.rb3_ip_address = sender_ip
                        if self.gui_callback:
                            self.gui_callback(f"🌐 RB3Enhanced detected at: {sender_ip}")
                        
                        # Notify GUI that IP was detected
                        if self.ip_detected_callback:
                            self.ip_detected_callback(sender_ip)
                    
                    self.process_packet(data)
                    
                except socket.timeout:
                    no_data_count += 1
                    if no_data_count % 12 == 0:  # Every minute
                        if self.gui_callback:
                            self.gui_callback(f"⏰ Still listening... ({no_data_count * 5}s)")
                    continue
                    
                except socket.error as e:
                    if self.running and self.gui_callback:
                        self.gui_callback(f"❌ Socket error: {e}")
                        
        except Exception as e:
            if self.gui_callback:
                self.gui_callback(f"❌ Failed to start listener: {e}")
    
    def get_rb3_ip(self) -> Optional[str]:
        """Get the detected RB3Enhanced IP address"""
        return self.rb3_ip_address
    
    def is_rb3_active(self) -> bool:
        """Check if RB3Enhanced is currently active (received packet recently)"""
        if not self.last_packet_time:
            return False
        
        # Consider active if received packet within last 30 seconds
        time_since_last = datetime.now() - self.last_packet_time
        return time_since_last.total_seconds() < 30
    
    def process_packet(self, data: bytes):
        """Process incoming RB3Enhanced packet"""
        if len(data) < 8:
            return
        
        try:
            magic = struct.unpack('>I', data[:4])[0]
            version, packet_type, packet_size, platform = struct.unpack('BBBB', data[4:8])
            
            if magic != self.RB3E_EVENTS_MAGIC or version != self.RB3E_EVENTS_PROTOCOL:
                return
            
            if packet_size > 0:
                packet_data = data[8:8+packet_size].rstrip(b'\x00').decode('utf-8', errors='ignore')
            else:
                packet_data = ""
            
            if packet_type == self.RB3E_EVENT_ALIVE:
                if self.gui_callback:
                    self.gui_callback(f"🎸 RB3Enhanced connected! Build: {packet_data}")
            
            elif packet_type == self.RB3E_EVENT_STATE:
                self.handle_state_change(packet_data)
            
            elif packet_type == self.RB3E_EVENT_SONG_NAME:
                self.current_song = packet_data
                if self.gui_callback:
                    self.gui_callback(f"🎵 Song: {self.current_song}")
            
            elif packet_type == self.RB3E_EVENT_SONG_ARTIST:
                self.current_artist = packet_data
                if self.gui_callback:
                    self.gui_callback(f"🎤 Artist: {self.current_artist}")
            
            if self.current_song and self.current_artist:
                if self.settings.get('sync_video_to_song', True):
                    self.prepare_video()
                else:
                    self.play_current_song()
        
        except Exception as e:
            if self.gui_callback:
                self.gui_callback(f"❌ Error processing packet: {e}")
    
    def handle_state_change(self, packet_data):
        """Handle game state changes"""
        try:
            new_state = int(packet_data) if packet_data.isdigit() else ord(packet_data[0]) if packet_data else 0
            
            if self.game_state == 0 and new_state == 1:
                if self.gui_callback:
                    self.gui_callback("🎵 Song starting!")
                
                if self.pending_video and self.settings.get('sync_video_to_song', True):
                    self.start_pending_video()
            
            elif self.game_state == 1 and new_state == 0:
                if self.gui_callback:
                    self.gui_callback("📋 Returned to menus")
                
                if self.settings.get('auto_quit_on_menu', True):
                    self.vlc_player.stop_current_video()
                
                self.pending_video = None
            
            self.game_state = new_state
            
        except Exception as e:
            pass
    
    def prepare_video(self):
        """Search for and prepare video"""
        try:
            video_id = self.youtube_searcher.search_video(self.current_artist, self.current_song)
            
            if video_id:
                if self.gui_callback:
                    self.gui_callback("🔄 Getting video stream...")
                stream_url = self.stream_extractor.get_stream_url(video_id)
                
                if stream_url:
                    self.pending_video = (stream_url, video_id, self.current_artist, self.current_song)
                    if self.gui_callback:
                        self.gui_callback("✅ Video ready - waiting for song to start...")
                    
                    if self.game_state == 1:
                        self.start_pending_video()
                else:
                    if self.gui_callback:
                        self.gui_callback(f"❌ Could not get stream for: {self.current_artist} - {self.current_song}")
            else:
                if self.gui_callback:
                    self.gui_callback(f"❌ Could not find video for: {self.current_artist} - {self.current_song}")
            
            self.current_song = ""
            self.current_artist = ""
            
        except Exception as e:
            if self.gui_callback:
                self.gui_callback(f"❌ Error preparing video: {e}")
    
    def start_pending_video(self):
        """Start the pending video with timing"""
        if not self.pending_video:
            return
        
        stream_url, video_id, artist, song = self.pending_video
        
        delay = self.settings.get('video_start_delay', 0.0)
        if delay != 0:
            if delay > 0:
                if self.gui_callback:
                    self.gui_callback(f"⏰ Waiting {delay}s before starting video...")
                time.sleep(delay)
        
        self.vlc_player.play_video(stream_url, video_id, artist, song, self.settings)
        self.pending_video = None
    
    def play_current_song(self):
        """Play current song immediately"""
        try:
            video_id = self.youtube_searcher.search_video(self.current_artist, self.current_song)
            
            if video_id:
                stream_url = self.stream_extractor.get_stream_url(video_id)
                if stream_url:
                    self.vlc_player.play_video(stream_url, video_id, self.current_artist, self.current_song, self.settings)
            
            self.current_song = ""
            self.current_artist = ""
            
        except Exception as e:
            if self.gui_callback:
                self.gui_callback(f"❌ Error playing song: {e}")
    
    def stop(self):
        """Stop listening"""
        self.running = False
        if self.sock:
            self.sock.close()

class RB3VideoPlayerGUI:
    """Main GUI application with Web UI integration"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("RB3Enhanced YouTube Video Player")
        self.root.geometry("600x500")
        self.root.resizable(True, True)
        
        # Application state
        self.youtube_searcher = None
        self.vlc_player = None
        self.stream_extractor = None
        self.listener = None
        self.listener_thread = None
        self.is_running = False
        self.detected_ip = None
        
        # Load settings
        self.settings = self.load_settings()
        
        self.create_widgets()
        self.update_ui_state()
        
        # Handle window closing
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def get_settings_path(self):
        """Get the proper path for settings file"""
        try:
            # Try AppData first (recommended)
            appdata_dir = os.environ.get('APPDATA')
            if appdata_dir:
                settings_dir = os.path.join(appdata_dir, 'RB3VideoPlayer')
                # Create directory if it doesn't exist
                os.makedirs(settings_dir, exist_ok=True)
                return os.path.join(settings_dir, 'settings.json')
        except Exception:
            pass
        
        try:
            # Fallback to Documents folder
            user_home = os.path.expanduser("~")
            documents_dir = os.path.join(user_home, 'Documents', 'RB3VideoPlayer')
            os.makedirs(documents_dir, exist_ok=True)
            return os.path.join(documents_dir, 'settings.json')
        except Exception:
            pass
        
        # Last resort - script directory (current behavior)
        return 'rb3_video_player_settings.json'
    
    def create_widgets(self):
        """Create all GUI widgets"""
        # Main notebook for tabs
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Control tab
        control_frame = ttk.Frame(notebook)
        notebook.add(control_frame, text="Control")
        self.create_control_tab(control_frame)
        
        # Settings tab
        settings_frame = ttk.Frame(notebook)
        notebook.add(settings_frame, text="Settings")
        self.create_settings_tab(settings_frame)    
        
        # Log tab
        log_frame = ttk.Frame(notebook)
        notebook.add(log_frame, text="Log")
        self.create_log_tab(log_frame)
    
    def create_settings_tab(self, parent):
        """Create settings configuration tab"""
        # YouTube API section
        api_frame = ttk.LabelFrame(parent, text="YouTube API Configuration", padding=10)
        api_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(api_frame, text="YouTube Data API v3 Key:").pack(anchor='w')
        self.api_key_var = tk.StringVar(value=self.settings.get('youtube_api_key', ''))
        api_entry = ttk.Entry(api_frame, textvariable=self.api_key_var, width=50, show='*')
        api_entry.pack(fill='x', pady=(5, 0))
        
        ttk.Label(api_frame, text="Get your free API key at: https://console.cloud.google.com/", 
                 foreground='blue').pack(anchor='w', pady=(5, 0))
        
        # Video settings
        video_frame = ttk.LabelFrame(parent, text="Video Settings", padding=10)
        video_frame.pack(fill='x', padx=10, pady=5)
        
        # Quality selection
        quality_frame = ttk.Frame(video_frame)
        quality_frame.pack(fill='x', pady=5)
        ttk.Label(quality_frame, text="Preferred Quality:").pack(side='left')
        self.quality_var = tk.StringVar(value=self.settings.get('preferred_quality', '1080p'))
        quality_combo = ttk.Combobox(quality_frame, textvariable=self.quality_var, 
                                   values=['4K', '1440p', '1080p', '720p', '480p', '360p'], 
                                   state='readonly', width=10)
        quality_combo.pack(side='left', padx=(10, 0))
        
        # Checkboxes
        self.fullscreen_var = tk.BooleanVar(value=self.settings.get('fullscreen', True))
        ttk.Checkbutton(video_frame, text="Start videos in fullscreen", 
                       variable=self.fullscreen_var).pack(anchor='w', pady=2)
        
        self.muted_var = tk.BooleanVar(value=self.settings.get('muted', True))
        ttk.Checkbutton(video_frame, text="Start videos muted", 
                       variable=self.muted_var).pack(anchor='w', pady=2)
        
        self.force_quality_var = tk.BooleanVar(value=self.settings.get('force_best_quality', True))
        ttk.Checkbutton(video_frame, text="Force best available quality", 
                       variable=self.force_quality_var).pack(anchor='w', pady=2)
        
        # Sync settings
        sync_frame = ttk.LabelFrame(parent, text="Synchronization Settings", padding=10)
        sync_frame.pack(fill='x', padx=10, pady=5)
        
        self.sync_var = tk.BooleanVar(value=self.settings.get('sync_video_to_song', True))
        ttk.Checkbutton(sync_frame, text="Sync video to song start", 
                       variable=self.sync_var).pack(anchor='w', pady=2)
        
        self.auto_quit_var = tk.BooleanVar(value=self.settings.get('auto_quit_on_menu', True))
        ttk.Checkbutton(sync_frame, text="Auto-quit VLC when returning to menu", 
                       variable=self.auto_quit_var).pack(anchor='w', pady=2)
        
        # Delay setting
        delay_frame = ttk.Frame(sync_frame)
        delay_frame.pack(fill='x', pady=5)
        ttk.Label(delay_frame, text="Video start delay (seconds):").pack(side='left')
        self.delay_var = tk.DoubleVar(value=self.settings.get('video_start_delay', 0.0))
        delay_spin = ttk.Spinbox(delay_frame, from_=-10.0, to=10.0, increment=0.5, 
                               textvariable=self.delay_var, width=10)
        delay_spin.pack(side='left', padx=(10, 0))
        ttk.Label(delay_frame, text="(negative = start early)").pack(side='left', padx=(10, 0))
        
        # Save button
        ttk.Button(parent, text="Save Settings", command=self.save_settings).pack(pady=10)
    
    def create_control_tab(self, parent):
        """Create control panel tab"""
        # Status section
        status_frame = ttk.LabelFrame(parent, text="Status", padding=10)
        status_frame.pack(fill='x', padx=10, pady=5)
        
        self.status_label = ttk.Label(status_frame, text="Stopped", font=('TkDefaultFont', 12, 'bold'))
        self.status_label.pack()
        
        # VLC status
        self.vlc_status_label = ttk.Label(status_frame, text="VLC: Not checked")
        self.vlc_status_label.pack(pady=(5, 0))
        
        # RB3Enhanced IP status
        self.ip_status_label = ttk.Label(status_frame, text="RB3Enhanced: Not detected", foreground='orange')
        self.ip_status_label.pack(pady=(5, 0))
        
        # Control buttons
        button_frame = ttk.Frame(parent)
        button_frame.pack(pady=20)
        
        self.start_button = ttk.Button(button_frame, text="Start Listening", 
                                     command=self.start_listener, style='Accent.TButton')
        self.start_button.pack(side='left', padx=5)
        
        self.stop_button = ttk.Button(button_frame, text="Stop", 
                                    command=self.stop_listener, state='disabled')
        self.stop_button.pack(side='left', padx=5)
        
        self.stop_vlc_button = ttk.Button(button_frame, text="Stop VLC", 
                                        command=self.stop_vlc)
        self.stop_vlc_button.pack(side='left', padx=5)
               
        # RB3Enhanced connection info
        rb3_frame = ttk.LabelFrame(parent, text="RB3Enhanced Connection", padding=10)
        rb3_frame.pack(fill='x', padx=10, pady=5)
        
        self.rb3_info_label = ttk.Label(rb3_frame, text="Waiting for connection...", 
                                      font=('TkDefaultFont', 10))
        self.rb3_info_label.pack()
        
        # Web UI button (initially disabled)
        self.web_ui_button = ttk.Button(button_frame, text="🌐 Open RBE Web UI", 
                                       command=self.open_web_ui, state='disabled')
        self.web_ui_button.pack(side='left', padx=5)
        
        # Instructions
        instructions_frame = ttk.LabelFrame(parent, text="Setup Instructions", padding=10)
        instructions_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        instructions = """
1. Enter your YouTube Data API v3 key in the Settings tab
2. Configure your video and sync preferences
3. Make sure VLC Media Player is installed
4. In RB3Enhanced config [Events] section, ensure:
   • EnableEvents = true
   • BroadcastTarget = 255.255.255.255
5. Click "Start Listening" 
6. Launch Rock Band 3 and play a song
        """.strip()
        
        instructions_text = tk.Text(instructions_frame, wrap='word', height=10, 
                                  background=self.root.cget('bg'), relief='flat')
        instructions_text.pack(fill='both', expand=True)
        instructions_text.insert('1.0', instructions)
        instructions_text.config(state='disabled')
    
    def create_log_tab(self, parent):
        """Create log display tab"""
        # Log display
        self.log_text = scrolledtext.ScrolledText(parent, wrap='word', height=20)
        self.log_text.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Clear log button
        ttk.Button(parent, text="Clear Log", command=self.clear_log).pack(pady=5)
    
    def on_ip_detected(self, ip_address):
        """Called when RB3Enhanced IP is detected"""
        self.detected_ip = ip_address
        
        # Update UI in main thread
        self.root.after(0, self._update_ip_ui, ip_address)
    
    def _update_ip_ui(self, ip_address):
        """Update IP-related UI elements"""
        self.ip_status_label.config(text=f"RB3Enhanced: {ip_address}", foreground='green')
        self.rb3_info_label.config(text=f"Connected to: {ip_address}\nWeb UI: http://{ip_address}:21070")
        self.web_ui_button.config(state='normal')
    
    def open_web_ui(self):
        """Open RB3Enhanced web interface in browser"""
        if self.detected_ip:
            url = f"http://{self.detected_ip}:21070"
            try:
                webbrowser.open(url)
                self.log_message(f"🌐 Opened RBE Web UI: {url}")
            except Exception as e:
                self.log_message(f"❌ Failed to open web browser: {e}")
                messagebox.showerror("Error", f"Failed to open web browser.\n\nManually navigate to: {url}")
        else:
            messagebox.showwarning("No Connection", "RB3Enhanced not detected yet.\n\nStart listening and play a song in Rock Band 3 first.")
    
    def log_message(self, message):
        """Add message to log display"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message}\n"
        
        # Update in main thread
        self.root.after(0, self._update_log, formatted_message)
    
    def _update_log(self, message):
        """Update log in main thread"""
        self.log_text.insert('end', message)
        self.log_text.see('end')
        
        # Keep log size reasonable
        lines = int(self.log_text.index('end-1c').split('.')[0])
        if lines > 1000:
            self.log_text.delete('1.0', '100.0')
    
    def clear_log(self):
        """Clear the log display"""
        self.log_text.delete('1.0', 'end')
        self.log_message("Log cleared")
    
    def update_ui_state(self):
        """Update UI based on current state"""
        if self.is_running:
            self.status_label.config(text="Listening for RB3Enhanced events", foreground='green')
            self.start_button.config(state='disabled')
            self.stop_button.config(state='normal')
        else:
            self.status_label.config(text="Stopped", foreground='red')
            self.start_button.config(state='normal')
            self.stop_button.config(state='disabled')
            
            # Reset IP detection when stopped
            self.detected_ip = None
            self.ip_status_label.config(text="RB3Enhanced: Not detected", foreground='orange')
            self.rb3_info_label.config(text="Waiting for connection...")
            self.web_ui_button.config(state='disabled')
        
        # Check VLC status
        if not hasattr(self, '_vlc_checked'):
            self.check_vlc_status()
            self._vlc_checked = True
    
    def check_vlc_status(self):
        """Check if VLC is available"""
        vlc_player = VLCPlayer()
        if vlc_player.vlc_path:
            self.vlc_status_label.config(text=f"VLC: Available at {vlc_player.vlc_path}", 
                                       foreground='green')
        else:
            self.vlc_status_label.config(text="VLC: Not found - Please install VLC Media Player", 
                                       foreground='red')
    
    def start_listener(self):
        """Start the RB3Enhanced listener"""
        # Validate settings
        api_key = self.api_key_var.get().strip()
        if not api_key or api_key == "YOUR_YOUTUBE_API_KEY_HERE":
            messagebox.showerror("Error", "Please enter your YouTube API key in the Settings tab!")
            return
        
        try:
            # Initialize components
            self.log_message("Initializing YouTube API...")
            self.youtube_searcher = YouTubeSearcher(api_key)
            
            self.log_message("Initializing VLC player...")
            self.vlc_player = VLCPlayer(gui_callback=self.log_message)
            
            if not self.vlc_player.vlc_path:
                messagebox.showerror("Error", "VLC Media Player not found!\nPlease install VLC from https://www.videolan.org/vlc/")
                return
            
            self.log_message("Initializing stream extractor...")
            self.stream_extractor = StreamExtractor(gui_callback=self.log_message)
            
            # Create listener with IP detection callback
            self.listener = RB3EventListener(
                self.youtube_searcher, 
                self.vlc_player, 
                self.stream_extractor,
                gui_callback=self.log_message,
                ip_detected_callback=self.on_ip_detected
            )
            
            # Update settings
            settings = self.get_current_settings()
            self.listener.update_settings(settings)
            
            # Start listener thread
            self.listener_thread = threading.Thread(target=self.listener.start_listening)
            self.listener_thread.daemon = True
            self.listener_thread.start()
            
            self.is_running = True
            self.update_ui_state()
            self.log_message("Started listening for RB3Enhanced events!")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to start listener: {e}")
            self.log_message(f"❌ Failed to start: {e}")
    
    def stop_listener(self):
        """Stop the listener"""
        if self.listener:
            self.listener.stop()
        
        if self.vlc_player:
            self.vlc_player.stop_current_video()
        
        self.is_running = False
        self.update_ui_state()
        self.log_message("Stopped listening")
    
    def stop_vlc(self):
        """Stop VLC playback"""
        if self.vlc_player:
            self.vlc_player.stop_current_video()
            self.log_message("VLC stopped manually")
    
    def get_current_settings(self):
        """Get current settings from GUI"""
        return {
            'youtube_api_key': self.api_key_var.get().strip(),
            'preferred_quality': self.quality_var.get(),
            'fullscreen': self.fullscreen_var.get(),
            'muted': self.muted_var.get(),
            'force_best_quality': self.force_quality_var.get(),
            'sync_video_to_song': self.sync_var.get(),
            'auto_quit_on_menu': self.auto_quit_var.get(),
            'video_start_delay': self.delay_var.get()
        }
    
    def save_settings(self):
        """Save settings to file"""
        try:
            settings = self.get_current_settings()
            self.settings = settings
            
            settings_path = self.get_settings_path()
            
            with open(settings_path, 'w') as f:
                json.dump(settings, f, indent=2)
            
            # Update listener if running
            if self.listener:
                self.listener.update_settings(settings)
            
            messagebox.showinfo("Success", f"Settings saved successfully!\n\nLocation: {settings_path}")
            self.log_message(f"Settings saved to: {settings_path}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save settings: {e}")
            self.log_message(f"❌ Failed to save settings: {e}")
    
    def load_settings(self):
        """Load settings from file"""
        settings_path = self.get_settings_path()
        
        try:
            with open(settings_path, 'r') as f:
                settings = json.load(f)
                self.log_message(f"Settings loaded from: {settings_path}")
                return settings
        except FileNotFoundError:
            # No settings file exists yet - use defaults
            self.log_message(f"No settings file found, using defaults. Will create: {settings_path}")
            return {
                'youtube_api_key': '',
                'preferred_quality': '1080p',
                'fullscreen': True,
                'muted': True,
                'force_best_quality': True,
                'sync_video_to_song': True,
                'auto_quit_on_menu': True,
                'video_start_delay': 0.0
            }
        except Exception as e:
            self.log_message(f"❌ Error loading settings: {e}")
            return {}
    
    def on_closing(self):
        """Handle window closing"""
        if self.is_running:
            self.stop_listener()
        
        # Save settings
        try:
            settings = self.get_current_settings()
            settings_path = self.get_settings_path()
            
            with open(settings_path, 'w') as f:
                json.dump(settings, f, indent=2)
            
            self.log_message(f"Settings saved on exit to: {settings_path}")
        except Exception as e:
            self.log_message(f"❌ Failed to save settings on exit: {e}")
        
        self.root.destroy()
    
    def run(self):
        """Start the GUI application"""
        self.root.mainloop()

def main():
    """Main application entry point"""
    app = RB3VideoPlayerGUI()
    app.run()

if __name__ == "__main__":
    main()
