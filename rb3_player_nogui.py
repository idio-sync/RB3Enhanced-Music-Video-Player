"""
RB3Enhanced YouTube Video Player - VLC Version
Listens for Rock Band 3 Enhanced mod network events and automatically 
plays YouTube music videos using VLC.

Requirements:
pip install google-api-python-client yt-dlp

Setup:
1. Install VLC Media Player: https://www.videolan.org/vlc/
2. Get YouTube Data API v3 key from Google Cloud Console
3. Set your API key in the YOUTUBE_API_KEY variable below
4. Enable RB3Enhanced events in your config
"""

import socket
import struct
import subprocess
import threading
import time
import re
import os
from typing import Optional, Tuple, Dict
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import yt_dlp

# ==================== CONFIGURATION ====================
# Get your free API key from: https://console.cloud.google.com/
YOUTUBE_API_KEY = "YOUR_API_KEY"

# Debug mode - set to False to hide detailed packet info
DEBUG_MODE = False

# Timing synchronization settings
SYNC_VIDEO_TO_SONG = True  # Wait for song to start before playing video
VIDEO_START_DELAY = -5.0   # Additional delay in seconds (can be negative)
PRELOAD_VIDEOS = True      # Get video ready but don't play until song starts

# Video quality settings
PREFERRED_QUALITY = "1080p"  # Options: "4K", "1440p", "1080p", "720p", "480p", "360p"
FORCE_BEST_QUALITY = True    # Always try to get the highest available quality

# VLC control settings
AUTO_QUIT_ON_MENU = True       # Quit VLC when returning to song selection

class YouTubeSearcher:
    """Handles YouTube API searches"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.youtube = None
        self.search_cache: Dict[str, str] = {}
        
        try:
            self.youtube = build('youtube', 'v3', developerKey=api_key)
            print("✅ YouTube API initialized successfully")
        except Exception as e:
            print(f"❌ Failed to initialize YouTube API: {e}")
    
    def clean_search_terms(self, artist: str, song: str) -> Tuple[str, str]:
        """Clean up artist and song names for better search results"""
        # Remove stuff in parentheses and common variations
        clean_song = re.sub(r'\s*\([^)]*\)\s*', '', song)
        clean_song = re.sub(r'\s*-\s*(Live|Acoustic|Demo|Remix).*', '', clean_song, flags=re.IGNORECASE)
        clean_song = clean_song.strip()
        
        # Remove featuring artists
        clean_artist = re.split(r'\s+(?:feat\.|ft\.|featuring)\s+', artist, flags=re.IGNORECASE)[0]
        clean_artist = clean_artist.strip()
        
        return clean_artist, clean_song
    
    def search_video(self, artist: str, song: str) -> Optional[str]:
        """Search for video and return the best match video ID"""
        if not self.youtube:
            return None
            
        clean_artist, clean_song = self.clean_search_terms(artist, song)
        search_key = f"{clean_artist.lower()} - {clean_song.lower()}"
        
        # Check cache first
        if search_key in self.search_cache:
            print(f"🔍 Using cached result for: {search_key}")
            return self.search_cache[search_key]
        
        try:
            # Try different search queries for best results
            search_queries = [
                f"{clean_artist} {clean_song} official music video",
                f"{clean_artist} {clean_song} music video",
                f"{clean_artist} {clean_song} official",
                f"{clean_artist} {clean_song}"
            ]
            
            for query in search_queries:
                print(f"🔍 Searching YouTube: {query}")
                
                search_response = self.youtube.search().list(
                    q=query,
                    part='id,snippet',
                    maxResults=5,
                    type='video',
                    videoCategoryId='10',  # Music category
                    order='relevance'
                ).execute()
                
                # Look for best match
                for item in search_response['items']:
                    video_title = item['snippet']['title'].lower()
                    video_channel = item['snippet']['channelTitle'].lower()
                    
                    # Prefer official channels and exact matches
                    is_official = any(term in video_channel for term in ['official', 'records', 'music', clean_artist.lower()])
                    has_song_in_title = clean_song.lower() in video_title
                    has_artist_in_title = clean_artist.lower() in video_title
                    
                    if (has_song_in_title and has_artist_in_title) or is_official:
                        video_id = item['id']['videoId']
                        self.search_cache[search_key] = video_id
                        print(f"✅ Found: {item['snippet']['title']} by {item['snippet']['channelTitle']}")
                        return video_id
                
                # If no perfect match, use first result
                if search_response['items']:
                    video_id = search_response['items'][0]['id']['videoId']
                    self.search_cache[search_key] = video_id
                    print(f"✅ Using first result: {search_response['items'][0]['snippet']['title']}")
                    return video_id
            
            print(f"❌ No videos found for: {artist} - {song}")
            return None
            
        except HttpError as e:
            print(f"❌ YouTube API error: {e}")
            return None
        except Exception as e:
            print(f"❌ Search error: {e}")
            return None

class VLCPlayer:
    """Simple VLC video player"""
    
    def __init__(self):
        self.vlc_path = self.find_vlc()
        self.current_process = None
        self.played_videos = set()
        
        if self.vlc_path:
            print(f"✅ Found VLC at: {self.vlc_path}")
        else:
            print("❌ VLC not found! Please install VLC Media Player")
    
    def find_vlc(self) -> Optional[str]:
        """Find VLC executable on Windows"""
        # Common Windows VLC installation paths
        possible_paths = [
            r"C:\Program Files\VideoLAN\VLC\vlc.exe",
            r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
            os.path.expanduser(r"~\AppData\Local\Programs\VLC\vlc.exe"),
        ]
        
        # Check if VLC is in PATH first
        try:
            subprocess.run(["vlc", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
            return "vlc"
        except:
            pass
        
        # Check common installation paths
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
                print("🛑 VLC closed")
            except subprocess.TimeoutExpired:
                self.current_process.kill()
                print("🛑 VLC force killed")
            except:
                pass
            finally:
                self.current_process = None
    
    def play_video(self, video_url: str, video_id: str, artist: str, song: str):
        """Play video with VLC"""
        if not self.vlc_path:
            print("❌ VLC not available")
            return
              
        # Stop any current video
        self.stop_current_video()
        
        try:
            print(f"🎬 Playing with VLC: {artist} - {song}")
            
            # Simple VLC command
            vlc_cmd = [
                self.vlc_path,
                video_url,
                "--intf", "dummy",
                "--no-video-title-show",
                "--volume=0",
                "--fullscreen",
                "--video-on-top",
                f"--meta-title={artist} - {song}"                
            ]
            
            # Add quality settings for HD content
            if PREFERRED_QUALITY in ["4K", "1440p", "1080p"]:
                vlc_cmd.extend([
                    "--avcodec-hw=any",  # Hardware acceleration
                    "--network-caching=2000",  # Network buffering
                ])
            
            if DEBUG_MODE:
                print(f"🔧 VLC command: {' '.join(vlc_cmd[:5])}...")
                print(f"🔗 Video URL: {video_url[:80]}...")
            
            # Start VLC
            self.current_process = subprocess.Popen(
                vlc_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            # Give VLC time to start
            time.sleep(2)
            
            if self.current_process.poll() is not None:
                exit_code = self.current_process.returncode
                print(f"❌ VLC exited immediately with code: {exit_code}")
                
                # Try fallback without advanced options
                print("🔄 Trying simplified VLC...")
                simple_cmd = [self.vlc_path, video_url]
                self.current_process = subprocess.Popen(simple_cmd)
            else:
                print("✅ VLC started successfully")
            
            # Remember this video
            self.played_videos.add(video_id)
            if len(self.played_videos) > 10:
                self.played_videos.pop()
            
        except Exception as e:
            print(f"❌ Error playing video: {e}")

class StreamExtractor:
    """Gets direct video URLs from YouTube with quality control"""
    
    def __init__(self):
        # Build format string based on quality preferences
        self.format_string = self._build_format_string()
        
        self.ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'format': self.format_string,
            'noplaylist': True,
        }
        
        if DEBUG_MODE:
            print(f"🎥 Video quality: {PREFERRED_QUALITY} (format: {self.format_string})")
    
    def _build_format_string(self) -> str:
        """Build yt-dlp format string for quality selection"""
        
        # Quality to height mapping
        quality_heights = {
            "4K": "2160",
            "1440p": "1440", 
            "1080p": "1080",
            "720p": "720",
            "480p": "480",
            "360p": "360"
        }
        
        target_height = quality_heights.get(PREFERRED_QUALITY, "1080")
        
        if FORCE_BEST_QUALITY:
            # Try for best quality first, then fallback to preferred, then any quality
            formats = [
                f"bestvideo[height<={target_height}]+bestaudio/best[height<={target_height}]",
                f"best[height<={target_height}]",
                "bestvideo+bestaudio/best",
                "best"
            ]
            return "/".join(formats)
        else:
            # Just try for the preferred quality
            return f"best[height<={target_height}]/best"
    
    def get_stream_url(self, video_id: str) -> Optional[str]:
        """Get direct stream URL for a YouTube video with quality info"""
        try:
            youtube_url = f"https://www.youtube.com/watch?v={video_id}"
            
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info = ydl.extract_info(youtube_url, download=False)
                
                # Show available formats in debug mode
                if DEBUG_MODE and 'formats' in info:
                    print("📺 Available video formats:")
                    for fmt in info['formats'][-5:]:  # Show last 5 formats
                        height = fmt.get('height', 'unknown')
                        ext = fmt.get('ext', 'unknown')
                        filesize = fmt.get('filesize')
                        size_mb = f" ({filesize//1024//1024}MB)" if filesize else ""
                        print(f"   {height}p {ext}{size_mb}")
                
                # Get the selected format info
                height = info.get('height', 'unknown')
                width = info.get('width', 'unknown')
                ext = info.get('ext', 'unknown')
                filesize = info.get('filesize')
                
                # Show what we got
                resolution = f"{width}x{height}" if width != 'unknown' and height != 'unknown' else f"{height}p"
                size_info = f" ({filesize//1024//1024}MB)" if filesize else ""
                print(f"🎥 Selected quality: {resolution} {ext}{size_info}")
                
                if 'url' in info:
                    return info['url']
                elif 'formats' in info and info['formats']:
                    # Find the best available format manually
                    for fmt in reversed(info['formats']):
                        if fmt.get('url') and fmt.get('vcodec') != 'none':
                            format_height = fmt.get('height', 0)
                            if DEBUG_MODE:
                                print(f"🎯 Using format: {format_height}p {fmt.get('ext', 'unknown')}")
                            return fmt['url']
            
            return None
            
        except Exception as e:
            print(f"❌ Error extracting stream: {e}")
            return None

class RB3EventListener:
    """Listens for RB3Enhanced network events"""
    
    # Constants from RB3Enhanced source
    RB3E_EVENTS_MAGIC = 0x52423345
    RB3E_EVENTS_PROTOCOL = 0
    RB3E_EVENT_ALIVE = 0
    RB3E_EVENT_STATE = 1
    RB3E_EVENT_SONG_NAME = 2
    RB3E_EVENT_SONG_ARTIST = 3
    
    def __init__(self, youtube_searcher, vlc_player, stream_extractor):
        self.youtube_searcher = youtube_searcher
        self.vlc_player = vlc_player
        self.stream_extractor = stream_extractor
        self.sock = None
        self.running = False
        self.current_song = ""
        self.current_artist = ""
        
        # Game state monitoring
        self.game_state = 0  # 0=menus, 1=in-game
        self.pending_video = None  # (stream_url, video_id, artist, song)
    
    def start_listening(self):
        """Start listening for RB3Enhanced events on port 21070"""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.settimeout(5.0)
            self.sock.bind(("0.0.0.0", 21070))
            self.running = True
            
            print("🎧 Listening for RB3Enhanced events on port 21070")
            if DEBUG_MODE:
                print("🔍 Debug mode: Will show all network activity")
            if SYNC_VIDEO_TO_SONG:
                print("⏱️ Video sync enabled: Videos will start when songs begin")
            print("🎸 Start playing songs in Rock Band 3!")
            
            no_data_count = 0
            
            while self.running:
                try:
                    data, addr = self.sock.recvfrom(1024)
                    no_data_count = 0
                    
                    if DEBUG_MODE:
                        print(f"📦 Received {len(data)} bytes from {addr}")
                        print(f"📦 Raw data (first 20 bytes): {data[:20].hex()}")
                    
                    self.process_packet(data)
                    
                except socket.timeout:
                    no_data_count += 1
                    if no_data_count % 6 == 0:  # Every 30 seconds
                        print(f"⏰ Still listening... ({no_data_count * 5} seconds, no packets received)")
                        print("💡 Make sure RB3Enhanced config has: EnableEvents = true")
                    continue
                    
                except socket.error as e:
                    if self.running:
                        print(f"❌ Socket error: {e}")
                        
        except Exception as e:
            print(f"❌ Failed to start listener: {e}")
            print("💡 Try running as administrator if on Windows")
    
    def process_packet(self, data: bytes):
        """Process incoming RB3Enhanced packet"""
        if len(data) < 8:
            if DEBUG_MODE:
                print(f"❌ Packet too short: {len(data)} bytes (need at least 8)")
            return
        
        try:
            # Parse header
            magic = struct.unpack('>I', data[:4])[0]
            version, packet_type, packet_size, platform = struct.unpack('BBBB', data[4:8])
            
            if DEBUG_MODE:
                print(f"📋 Packet info:")
                print(f"   Magic: 0x{magic:08X} (expected: 0x{self.RB3E_EVENTS_MAGIC:08X})")
                print(f"   Version: {version} (expected: {self.RB3E_EVENTS_PROTOCOL})")
                print(f"   Type: {packet_type}")
                print(f"   Size: {packet_size}")
                print(f"   Platform: {platform}")
            
            # Verify this is an RB3Enhanced packet
            if magic != self.RB3E_EVENTS_MAGIC:
                if DEBUG_MODE:
                    print(f"❌ Wrong magic number! Got 0x{magic:08X}, expected 0x{self.RB3E_EVENTS_MAGIC:08X}")
                return
                
            if version != self.RB3E_EVENTS_PROTOCOL:
                if DEBUG_MODE:
                    print(f"❌ Wrong protocol version! Got {version}, expected {self.RB3E_EVENTS_PROTOCOL}")
                return
            
            if DEBUG_MODE:
                print("✅ Valid RB3Enhanced packet!")
            
            # Extract the data
            if packet_size > 0:
                packet_data = data[8:8+packet_size].rstrip(b'\x00').decode('utf-8', errors='ignore')
                if DEBUG_MODE:
                    print(f"📝 Packet data: '{packet_data}'")
            else:
                packet_data = ""
            
            # Handle different packet types
            if packet_type == self.RB3E_EVENT_ALIVE:
                print(f"🎸 RB3Enhanced connected! Build: {packet_data}")
            
            elif packet_type == self.RB3E_EVENT_STATE:
                self.handle_state_change(packet_data)
            
            elif packet_type == self.RB3E_EVENT_SONG_NAME:
                self.current_song = packet_data
                print(f"🎵 Song: {self.current_song}")
            
            elif packet_type == self.RB3E_EVENT_SONG_ARTIST:
                self.current_artist = packet_data
                print(f"🎤 Artist: {self.current_artist}")
            
            else:
                # Only show unknown packet types in debug mode
                if DEBUG_MODE:
                    if packet_type not in [1, 5, 6]:  # Don't spam for common events
                        print(f"❓ Unknown event type: {packet_type}")
            
            # When we have both artist and song, prepare the video
            if self.current_song and self.current_artist:
                if SYNC_VIDEO_TO_SONG and PRELOAD_VIDEOS:
                    print(f"🎬 Preparing video: {self.current_artist} - {self.current_song}")
                    self.prepare_video()
                else:
                    print(f"🎬 Playing immediately: {self.current_artist} - {self.current_song}")
                    self.play_current_song()
        
        except Exception as e:
            print(f"❌ Error processing packet: {e}")
            if DEBUG_MODE:
                print(f"📊 Raw packet data: {data.hex()}")
    
    def handle_state_change(self, packet_data):
        """Handle game state changes (menus vs in-game)"""
        try:
            new_state = int(packet_data) if packet_data.isdigit() else ord(packet_data[0]) if packet_data else 0
            
            if DEBUG_MODE:
                state_names = {0: "menus", 1: "in-game"}
                print(f"🎮 Game state: {new_state} ({state_names.get(new_state, 'unknown')})")
            
            # Detect transition from menus (0) to in-game (1) - song starting
            if self.game_state == 0 and new_state == 1:
                print("🎵 Song starting!")
                
                # If we have a video waiting, start it now
                if self.pending_video and SYNC_VIDEO_TO_SONG:
                    self.start_pending_video()
            
            # Detect transition from in-game (1) to menus (0) - song ended or back to menu
            elif self.game_state == 1 and new_state == 0:
                print("📋 Returned to menus - song ended")
                
                # Stop VLC when returning to menus
                if AUTO_QUIT_ON_MENU:
                    print("🛑 Auto-closing video")
                    self.vlc_player.stop_current_video()
                
                # Clear any pending video when returning to menus
                self.pending_video = None
            
            self.game_state = new_state
            
        except Exception as e:
            if DEBUG_MODE:
                print(f"❌ Error processing state change: {e}")
    
    def prepare_video(self):
        """Search for and prepare video but don't play it yet"""
        try:
            # Search YouTube
            video_id = self.youtube_searcher.search_video(self.current_artist, self.current_song)
            
            if video_id:
                # Get stream URL
                print("🔄 Getting video stream...")
                stream_url = self.stream_extractor.get_stream_url(video_id)
                
                if stream_url:
                    # Store for later playback
                    self.pending_video = (stream_url, video_id, self.current_artist, self.current_song)
                    print("✅ Video ready - waiting for song to start...")
                    
                    # If we're already in-game, start immediately (song probably already started)
                    if self.game_state == 1:
                        print("💡 Song already playing, starting video now")
                        self.start_pending_video()
                else:
                    print(f"❌ Could not get stream for: {self.current_artist} - {self.current_song}")
            else:
                print(f"❌ Could not find video for: {self.current_artist} - {self.current_song}")
            
            # Reset for next song
            self.current_song = ""
            self.current_artist = ""
            
        except Exception as e:
            print(f"❌ Error preparing video: {e}")
    
    def start_pending_video(self):
        """Start the pending video with timing offset"""
        if not self.pending_video:
            return
        
        stream_url, video_id, artist, song = self.pending_video
        
        # Apply timing delay
        if VIDEO_START_DELAY != 0:
            if VIDEO_START_DELAY > 0:
                print(f"⏰ Waiting {VIDEO_START_DELAY}s before starting video...")
                time.sleep(VIDEO_START_DELAY)
            else:
                print(f"⏰ Starting video {abs(VIDEO_START_DELAY)}s early")
        
        # Start the video
        print(f"🎬 Starting synced video: {artist} - {song}")
        self.vlc_player.play_video(stream_url, video_id, artist, song)
        
        # Clear pending video
        self.pending_video = None
    
    def play_current_song(self):
        """Search for and play the current song immediately (no sync)"""
        try:
            # Search YouTube
            video_id = self.youtube_searcher.search_video(self.current_artist, self.current_song)
            
            if video_id:
                # Get stream URL
                print("🔄 Getting video stream...")
                stream_url = self.stream_extractor.get_stream_url(video_id)
                
                if stream_url:
                    # Play immediately
                    self.vlc_player.play_video(stream_url, video_id, self.current_artist, self.current_song)
                else:
                    print(f"❌ Could not get stream for: {self.current_artist} - {self.current_song}")
            else:
                print(f"❌ Could not find video for: {self.current_artist} - {self.current_song}")
            
            # Reset for next song
            self.current_song = ""
            self.current_artist = ""
            
        except Exception as e:
            print(f"❌ Error playing song: {e}")
    
    def stop(self):
        """Stop listening"""
        self.running = False
        if self.sock:
            self.sock.close()

def main():
    print("🎸 ========== RB3Enhanced YouTube Video Player ========== 🎸")
    print("🎵 VLC Version 🎵\n")
    
    # Check API key
    if YOUTUBE_API_KEY == "YOUR_YOUTUBE_API_KEY_HERE":
        print("❌ Please set your YouTube API key in the script!")
        print("Get one free at: https://console.cloud.google.com/")
        return
    
    # Initialize everything
    print("🔧 Initializing...")
    youtube_searcher = YouTubeSearcher(YOUTUBE_API_KEY)
    vlc_player = VLCPlayer()
    stream_extractor = StreamExtractor()
    
    if not vlc_player.vlc_path:
        print("\n❌ VLC not found!")
        print("Please install VLC from: https://www.videolan.org/vlc/")
        print("Make sure to install it in the default location.")
        return
    
    # Start the listener
    listener = RB3EventListener(youtube_searcher, vlc_player, stream_extractor)
    
    try:
        print("🎧 Starting listener...")
        listener_thread = threading.Thread(target=listener.start_listening)
        listener_thread.daemon = True
        listener_thread.start()
        
        print("\n✅ Ready to rock!")
        print("📝 IMPORTANT: Check your RB3Enhanced configuration:")
        print("   • Make sure EnableEvents = true")
        print("   • Make sure BroadcastTarget = 255.255.255.255")
        print("   • Both should be in the [Events] section of your config")
        print("\n🎸 Start Rock Band 3 and play some songs!")
        
        # Show settings
        if AUTO_QUIT_ON_MENU:
            print("🎮 VLC control: auto-quit on menu")
        
        if SYNC_VIDEO_TO_SONG:
            print("⏱️ Video sync enabled - videos will start when songs begin")
            if VIDEO_START_DELAY != 0:
                if VIDEO_START_DELAY > 0:
                    print(f"⏰ Videos will start {VIDEO_START_DELAY}s after song begins")
                else:
                    print(f"⏰ Videos will start {abs(VIDEO_START_DELAY)}s before song begins")
        else:
            print("🚀 Immediate mode - videos start as soon as song info is received")
        
        quality_status = "best available" if FORCE_BEST_QUALITY else PREFERRED_QUALITY
        print(f"🎥 Video quality: {quality_status}")
        
        if DEBUG_MODE:
            print("🔍 Debug mode enabled - showing all packet details")
        else:
            print("🔇 Quiet mode - only showing song events (set DEBUG_MODE = True for details)")
        
        print("\n💡 Configuration:")
        print("   🎥 Quality: set PREFERRED_QUALITY = '1080p' or '4K'")
        print("   ⏱️ Timing: adjust VIDEO_START_DELAY for sync (+/- seconds)")
        print("   🔍 Debug: set DEBUG_MODE = True for network troubleshooting")
        print("\n🛑 Press Ctrl+C to exit\n")
        
        # Keep running
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")
        vlc_player.stop_current_video()
        listener.stop()

if __name__ == "__main__":
    main()
