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
from tkinter import ttk, messagebox, scrolledtext, filedialog
import json
from datetime import datetime

class SongDatabase:
    """Handles loading and querying the JSON song database"""
    
    def __init__(self, gui_callback=None):
        self.gui_callback = gui_callback
        self.songs = {}  # shortname -> song data
        self.loaded_count = 0
        self.database_path = None
    
    def parse_duration(self, duration_str):
        """Convert duration string like '2:17' to seconds (137)"""
        try:
            if ':' in duration_str:
                parts = duration_str.split(':')
                if len(parts) == 2:
                    minutes, seconds = parts
                    return int(minutes) * 60 + int(seconds)
                elif len(parts) == 3:
                    hours, minutes, seconds = parts
                    return int(hours) * 3600 + int(minutes) * 60 + int(seconds)
            else:
                # Assume it's already in seconds
                return int(float(duration_str))
        except (ValueError, AttributeError):
            if self.gui_callback:
                self.gui_callback(f"⚠️ Could not parse duration: {duration_str}")
            return None
    
    def load_database(self, file_path):
        """Load songs from JSON file with BOM handling"""
        try:
            self.database_path = file_path
            
            if self.gui_callback:
                self.gui_callback(f"📁 Loading song database from: {file_path}")
            
            # Try different encodings to handle BOM issues
            data = None
            for encoding in ['utf-8-sig', 'utf-8', 'utf-16', 'cp1252']:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        data = json.load(f)
                    if self.gui_callback:
                        self.gui_callback(f"✅ Successfully read file with {encoding} encoding")
                    break
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
            
            if data is None:
                # Last resort: read as binary and strip BOM manually
                with open(file_path, 'rb') as f:
                    raw_data = f.read()
                
                # Remove common BOMs
                if raw_data.startswith(b'\xef\xbb\xbf'):  # UTF-8 BOM
                    raw_data = raw_data[3:]
                elif raw_data.startswith(b'\xff\xfe'):  # UTF-16 LE BOM
                    raw_data = raw_data[2:]
                elif raw_data.startswith(b'\xfe\xff'):  # UTF-16 BE BOM
                    raw_data = raw_data[2:]
                
                # Try to decode and parse
                text_data = raw_data.decode('utf-8')
                data = json.loads(text_data)
                
                if self.gui_callback:
                    self.gui_callback("✅ Successfully read file after removing BOM")
            
            # Clear existing data
            self.songs = {}
            self.loaded_count = 0
            
            # Parse the setlist
            if 'setlist' in data:
                for song in data['setlist']:
                    shortname = song.get('shortname')
                    if shortname:
                        # Parse duration and add to song data
                        duration_str = song.get('duration', '')
                        duration_seconds = self.parse_duration(duration_str)
                        
                        song_data = {
                            'shortname': shortname,
                            'name': song.get('name', ''),
                            'artist': song.get('artist', ''),
                            'album': song.get('album', ''),
                            'duration_str': duration_str,
                            'duration_seconds': duration_seconds,
                            'year_released': song.get('year_released'),
                            'genre': song.get('genre', ''),
                            'preview_start': song.get('preview_start', 0),
                            'preview_end': song.get('preview_end', 0)
                        }
                        
                        self.songs[shortname] = song_data
                        self.loaded_count += 1
            
            if self.gui_callback:
                self.gui_callback(f"✅ Loaded {self.loaded_count} songs from database")
            
            return True
            
        except Exception as e:
            if self.gui_callback:
                self.gui_callback(f"❌ Failed to load song database: {e}")
            return False
    
    def lookup_song(self, shortname, artist=None, title=None):
        """Look up song by shortname, with fallback to artist+title"""
        # Primary lookup by shortname (now we get this from Event 4!)
        if shortname and shortname in self.songs:
            return self.songs[shortname]
        
        # Fallback: search by artist + title (case insensitive)
        if artist and title:
            artist_lower = artist.lower()
            title_lower = title.lower()
            
            for song_data in self.songs.values():
                if (song_data['artist'].lower() == artist_lower and 
                    song_data['name'].lower() == title_lower):
                    return song_data
        
        return None
    
    def get_song_duration(self, shortname, artist=None, title=None):
        """Get song duration in seconds"""
        song_data = self.lookup_song(shortname, artist, title)
        if song_data:
            return song_data.get('duration_seconds')
        return None
    
    def is_loaded(self):
        """Check if database is loaded"""
        return self.loaded_count > 0
    
    def get_stats(self):
        """Get database statistics"""
        return {
            'loaded_count': self.loaded_count,
            'database_path': self.database_path,
            'has_data': self.loaded_count > 0
        }

class YouTubeSearcher:
    """Handles YouTube API searches with duration-aware ranking"""
    
    def __init__(self, api_key: str, song_database=None, gui_callback=None):
        self.api_key = api_key
        self.youtube = None
        self.search_cache: Dict[str, str] = {}
        self.song_database = song_database
        self.gui_callback = gui_callback
        
        try:
            if api_key and api_key != "YOUR_YOUTUBE_API_KEY_HERE":
                self.youtube = build('youtube', 'v3', developerKey=api_key)
        except Exception as e:
            raise Exception(f"Failed to initialize YouTube API: {e}")
    
    def parse_youtube_duration(self, duration_str):
        """Parse YouTube duration from ISO 8601 format (PT2M17S) to seconds"""
        import re
        
        if not duration_str:
            return None
        
        # Pattern to match PT1H2M3S, PT2M17S, PT45S, etc.
        pattern = r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?'
        match = re.match(pattern, duration_str)
        
        if not match:
            return None
        
        hours = int(match.group(1)) if match.group(1) else 0
        minutes = int(match.group(2)) if match.group(2) else 0
        seconds = int(match.group(3)) if match.group(3) else 0
        
        return hours * 3600 + minutes * 60 + seconds
    
    def get_video_durations(self, video_ids):
        """Get durations for multiple videos using YouTube API"""
        if not self.youtube or not video_ids:
            return {}
        
        try:
            # YouTube API allows up to 50 video IDs per request
            video_ids_str = ','.join(video_ids[:50])
            
            response = self.youtube.videos().list(
                part='contentDetails',
                id=video_ids_str
            ).execute()
            
            durations = {}
            for item in response.get('items', []):
                video_id = item['id']
                duration_str = item['contentDetails']['duration']
                duration_seconds = self.parse_youtube_duration(duration_str)
                durations[video_id] = duration_seconds
            
            return durations
            
        except Exception as e:
            if self.gui_callback:
                self.gui_callback(f"⚠️ Error getting video durations: {e}")
            return {}
    
    def score_video_by_duration(self, video_duration, target_duration):
        """Score a video based on how close its duration is to the target"""
        if not video_duration or not target_duration:
            return 0
        
        # Calculate the difference in seconds
        diff = abs(video_duration - target_duration)
        
        # Perfect match gets score of 100
        if diff == 0:
            return 100
        
        # Score decreases as difference increases
        # Videos within 10 seconds get high scores
        if diff <= 10:
            return 90 - diff
        
        # Videos within 30 seconds get decent scores
        elif diff <= 30:
            return 70 - (diff - 10)
        
        # Videos within 60 seconds get lower scores
        elif diff <= 60:
            return 40 - (diff - 30)
        
        # Videos way off get very low scores
        else:
            return max(0, 20 - (diff - 60) // 10)
    
    def clean_search_terms(self, artist: str, song: str) -> Tuple[str, str]:
        """Clean up artist and song names for better search results"""
        clean_song = re.sub(r'\s*\([^)]*\)\s*', '', song)
        clean_song = re.sub(r'\s*-\s*(Live|Acoustic|Demo|Remix).*', '', clean_song, flags=re.IGNORECASE)
        clean_song = clean_song.strip()
        
        clean_artist = re.split(r'\s+(?:feat\.|ft\.|featuring)\s+', artist, flags=re.IGNORECASE)[0]
        clean_artist = clean_artist.strip()
        
        return clean_artist, clean_song
    
    def search_video(self, artist: str, song: str) -> Optional[str]:
        """Search for video and return the best match video ID with duration consideration"""
        if not self.youtube:
            return None
            
        clean_artist, clean_song = self.clean_search_terms(artist, song)
        search_key = f"{clean_artist.lower()} - {clean_song.lower()}"
        
        # Check cache first
        if search_key in self.search_cache:
            return self.search_cache[search_key]
        
        # Get target duration from database if available
        target_duration = None
        if self.song_database and self.song_database.is_loaded():
            target_duration = self.song_database.get_song_duration(None, artist, song)
        
        try:
            search_queries = [
                f"{clean_artist} {clean_song} official music video",
                f"{clean_artist} {clean_song} music video", 
                f"{clean_artist} {clean_song} official",
                f"{clean_artist} {clean_song}"
            ]
            
            best_video_id = None
            best_score = -1
            
            for query in search_queries:
                search_response = self.youtube.search().list(
                    q=query,
                    part='id,snippet',
                    maxResults=10,  # Get more results for duration filtering
                    type='video',
                    videoCategoryId='10',
                    order='relevance'
                ).execute()
                
                if not search_response['items']:
                    continue
                
                # Get video IDs and fetch their durations
                video_ids = [item['id']['videoId'] for item in search_response['items']]
                video_durations = self.get_video_durations(video_ids)
                
                # Score each video
                for item in search_response['items']:
                    video_id = item['id']['videoId']
                    video_title = item['snippet']['title'].lower()
                    video_channel = item['snippet']['channelTitle'].lower()
                    video_duration = video_durations.get(video_id)
                    
                    # Base score from title/channel matching (existing logic)
                    base_score = 0
                    
                    is_official = any(term in video_channel for term in ['official', 'records', 'music', clean_artist.lower()])
                    has_song_in_title = clean_song.lower() in video_title
                    has_artist_in_title = clean_artist.lower() in video_title
                    
                    if has_song_in_title and has_artist_in_title:
                        base_score += 30
                    elif has_song_in_title or has_artist_in_title:
                        base_score += 15
                    
                    if is_official:
                        base_score += 20
                    
                    # Add duration score if we have target duration
                    duration_score = 0
                    if target_duration and video_duration:
                        duration_score = self.score_video_by_duration(video_duration, target_duration)
                        
                        # Log duration comparison for debugging
                        target_min = target_duration // 60
                        target_sec = target_duration % 60
                        video_min = video_duration // 60
                        video_sec = video_duration % 60
                        if self.gui_callback:
                            self.gui_callback(f"🎵 Comparing: Target {target_min}:{target_sec:02d} vs Video {video_min}:{video_sec:02d} (Score: {duration_score})")
                    
                    # Combine scores (duration gets more weight)
                    total_score = base_score + (duration_score * 2)
                    
                    if total_score > best_score:
                        best_score = total_score
                        best_video_id = video_id
                
                # If we found a good match, use it
                if best_video_id and best_score > 50:
                    break
            
            # Fall back to first result if no good duration match found
            if not best_video_id and search_response['items']:
                best_video_id = search_response['items'][0]['id']['videoId']
            
            if best_video_id:
                self.search_cache[search_key] = best_video_id
                
                # Log the selection
                if target_duration and self.gui_callback:
                    target_min = target_duration // 60
                    target_sec = target_duration % 60
                    self.gui_callback(f"✅ Selected video for {clean_artist} - {clean_song} (target: {target_min}:{target_sec:02d}, score: {best_score})")
                
                return best_video_id
            
            return None
            
        except Exception as e:
            raise Exception(f"Search error: {e}")

class VLCPlayer:
    """VLC video player with GUI integration"""
    
    def __init__(self, gui_callback=None, song_database=None):
        self.vlc_path = self.find_vlc()
        self.current_process = None
        self.played_videos = set()
        self.gui_callback = gui_callback
        self.song_database = song_database
    
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
    
    def play_video(self, video_url: str, video_id: str, artist: str, song: str, settings: dict, shortname: str = None):
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
            
            if settings.get('always_on_top', False):
                vlc_cmd.append("--video-on-top")
            
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
            
            # Show duration info if available
            if self.song_database and self.song_database.is_loaded():
                duration = self.song_database.get_song_duration(shortname, artist, song)
                if duration:
                    if self.gui_callback:
                        self.gui_callback(f"🎬 Playing: {artist} - {song} (Duration: {duration//60}:{duration%60:02d})")
                else:
                    if self.gui_callback:
                        self.gui_callback(f"🎬 Playing: {artist} - {song} (No duration data)")
            else:
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
    """Listens for RB3Enhanced network events with complete event support"""
    
    RB3E_EVENTS_MAGIC = 0x52423345
    RB3E_EVENTS_PROTOCOL = 0
    
    # Complete event types from RB3Enhanced source
    RB3E_EVENT_ALIVE = 0           # Build info string
    RB3E_EVENT_STATE = 1           # 00=menus, 01=ingame  
    RB3E_EVENT_SONG_NAME = 2       # Song title string
    RB3E_EVENT_SONG_ARTIST = 3     # Artist name string
    RB3E_EVENT_SONG_SHORTNAME = 4  # Song shortname string (PERFECT for JSON lookup!)
    RB3E_EVENT_SCORE = 5           # Score data struct
    RB3E_EVENT_STAGEKIT = 6        # Stagekit rumble data
    RB3E_EVENT_BAND_INFO = 7       # Band member info
    RB3E_EVENT_VENUE_NAME = 8      # Venue name string
    RB3E_EVENT_SCREEN_NAME = 9     # Current screen name
    RB3E_EVENT_DX_DATA = 10        # Mod data
    
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
        self.current_shortname = ""  # Now we can get the exact shortname!
        self.game_state = 0
        self.pending_video = None
        self.settings = {}
        self.rb3_ip_address = None
        self.last_packet_time = None
        
        # Event discovery
        self.unknown_events = {}  # Track truly unknown event types
        self.event_history = []   # Store recent events for pattern analysis
        self.debug_events = True  # Set to False to reduce logging
    
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
        """Process incoming RB3Enhanced packet with complete event support"""
        if len(data) < 8:
            return
        
        try:
            magic = struct.unpack('>I', data[:4])[0]
            version, packet_type, packet_size, platform = struct.unpack('BBBB', data[4:8])
            
            if magic != self.RB3E_EVENTS_MAGIC or version != self.RB3E_EVENTS_PROTOCOL:
                return
            
            # Extract packet data
            if packet_size > 0:
                packet_data = data[8:8+packet_size].rstrip(b'\x00').decode('utf-8', errors='ignore')
            else:
                packet_data = ""
            
            # Log all events for discovery
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            event_info = {
                'timestamp': timestamp,
                'type': packet_type,
                'data': packet_data,
                'size': packet_size
            }
            self.event_history.append(event_info)
            
            # Keep only recent events (last 50)
            if len(self.event_history) > 50:
                self.event_history.pop(0)
            
            # Handle all known events
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
            
            elif packet_type == self.RB3E_EVENT_SONG_SHORTNAME:
                self.current_shortname = packet_data
                if self.gui_callback:
                    self.gui_callback(f"🔗 Shortname: {self.current_shortname}")
            
            elif packet_type == self.RB3E_EVENT_SCORE:
                # Score data - could be useful for displaying current score
                if self.debug_events and self.gui_callback:
                    self.gui_callback(f"🎯 Score update received")
            
            elif packet_type == self.RB3E_EVENT_STAGEKIT:
                # Stagekit rumble data - not useful for video sync
                if self.debug_events and self.gui_callback:
                    self.gui_callback(f"🥁 Stagekit data received")
            
            elif packet_type == self.RB3E_EVENT_BAND_INFO:
                # Band member info - could be useful for showing who's playing
                if self.debug_events and self.gui_callback:
                    self.gui_callback(f"👥 Band info update received")
            
            elif packet_type == self.RB3E_EVENT_VENUE_NAME:
                if self.debug_events and self.gui_callback:
                    self.gui_callback(f"🏟️ Venue: {packet_data}")
            
            elif packet_type == self.RB3E_EVENT_SCREEN_NAME:
                # This could be very useful for precise timing!
                if self.debug_events and self.gui_callback:
                    self.gui_callback(f"📺 Screen: {packet_data}")
                
                # Check if this indicates song start more precisely than state change
                if packet_data.lower() in ['gameplay', 'song', 'playing', 'ingame']:
                    if self.gui_callback:
                        self.gui_callback(f"🎯 Precise song start detected via screen: {packet_data}")
                    # Could trigger video start here instead of waiting for state change
            
            elif packet_type == self.RB3E_EVENT_DX_DATA:
                # Mod data - might contain useful info depending on what mods are loaded
                if self.debug_events and self.gui_callback:
                    self.gui_callback(f"🔧 Mod data: {packet_data[:50]}...")  # Truncate long data
            
            else:
                # Now these are truly unknown events (beyond the documented ones)
                if packet_type not in self.unknown_events:
                    self.unknown_events[packet_type] = []
                
                self.unknown_events[packet_type].append({
                    'timestamp': timestamp,
                    'data': packet_data,
                    'size': packet_size
                })
                
                # Log truly unknown events
                if self.debug_events and self.gui_callback:
                    self.gui_callback(f"❓ Unknown event {packet_type}: '{packet_data}' (size: {packet_size})")
            
            # Process song info when we have what we need
            # Now we prefer shortname + (artist/song) for better matching
            if self.current_shortname and (self.current_song or self.current_artist):
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
                
                # Clear all song-related data when returning to menu
                self.pending_video = None
                self.current_song = ""
                self.current_artist = ""
                self.current_shortname = ""
            
            self.game_state = new_state
            
        except Exception as e:
            pass
    
    def prepare_video(self):
        """Search for and prepare video using shortname when available"""
        try:
            # Use shortname for YouTube search context (but still search by artist+song)
            video_id = self.youtube_searcher.search_video(self.current_artist, self.current_song)
            
            if video_id:
                if self.gui_callback:
                    self.gui_callback("🔄 Getting video stream...")
                stream_url = self.stream_extractor.get_stream_url(video_id)
                
                if stream_url:
                    # Store shortname with video info for better JSON lookup
                    self.pending_video = (stream_url, video_id, self.current_artist, self.current_song, self.current_shortname)
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
            
            # Reset for next song
            self.current_song = ""
            self.current_artist = ""
            self.current_shortname = ""
            
        except Exception as e:
            if self.gui_callback:
                self.gui_callback(f"❌ Error preparing video: {e}")
    
    def start_pending_video(self):
        """Start the pending video with timing"""
        if not self.pending_video:
            return
        
        stream_url, video_id, artist, song, shortname = self.pending_video
        
        delay = self.settings.get('video_start_delay', 0.0)
        if delay != 0:
            if delay > 0:
                if self.gui_callback:
                    self.gui_callback(f"⏰ Waiting {delay}s before starting video...")
                time.sleep(delay)
        
        # Now we can pass the actual shortname for perfect JSON database lookup!
        self.vlc_player.play_video(
            stream_url, video_id, artist, song, self.settings, shortname
        )
        self.pending_video = None
    
    def play_current_song(self):
        """Play current song immediately using shortname when available"""
        try:
            video_id = self.youtube_searcher.search_video(self.current_artist, self.current_song)
            
            if video_id:
                stream_url = self.stream_extractor.get_stream_url(video_id)
                if stream_url:
                    # Pass the actual shortname for perfect JSON database lookup!
                    self.vlc_player.play_video(
                        stream_url, video_id, self.current_artist, self.current_song, 
                        self.settings, self.current_shortname
                    )
            
            self.current_song = ""
            self.current_artist = ""
            self.current_shortname = ""
            
        except Exception as e:
            if self.gui_callback:
                self.gui_callback(f"❌ Error playing song: {e}")
    
    def get_event_summary(self):
        """Get summary of discovered events"""
        summary = {
            'known_events': {
                0: 'ALIVE (RB3Enhanced build info)',
                1: 'STATE (00=menus, 01=ingame)', 
                2: 'SONG_NAME (song title)',
                3: 'SONG_ARTIST (artist name)',
                4: 'SONG_SHORTNAME (shortname for JSON lookup!)',
                5: 'SCORE (real-time scoring data)',
                6: 'STAGEKIT (rumble/lighting data)',
                7: 'BAND_INFO (member info & difficulties)',
                8: 'VENUE_NAME (current venue)',
                9: 'SCREEN_NAME (current screen - useful for timing!)',
                10: 'DX_DATA (mod data from RB3DX/other mods)'
            },
            'unknown_events': {},
            'recent_history': self.event_history[-10:]  # Last 10 events
        }
        
        for event_type, occurrences in self.unknown_events.items():
            summary['unknown_events'][event_type] = {
                'count': len(occurrences),
                'sample_data': [occ['data'] for occ in occurrences[-3:]],  # Last 3 samples
                'first_seen': occurrences[0]['timestamp'] if occurrences else None,
                'last_seen': occurrences[-1]['timestamp'] if occurrences else None
            }
        
        return summary
    
    def stop(self):
        """Stop listening"""
        self.running = False
        if self.sock:
            self.sock.close()

class RB3VideoPlayerGUI:
    """Main GUI application with Web UI integration and JSON database support"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("RB3Enhanced Music Video Player")
        self.root.geometry("625x525")
        self.root.resizable(True, True)
        
        # Application state
        self.youtube_searcher = None
        self.vlc_player = None
        self.stream_extractor = None
        self.listener = None
        self.listener_thread = None
        self.is_running = False
        self.detected_ip = None
        
        # Add song database
        self.song_database = SongDatabase(gui_callback=self.log_message)
        
        # Load settings
        self.settings = self.load_settings()
        
        self.create_widgets()
        self.update_ui_state()
        
        # Auto-load database if path is saved
        self.auto_load_database()
        
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
        """Create settings configuration tab with compact layout"""
        # Create main scrollable frame
        canvas = tk.Canvas(parent)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Row 1: YouTube API and Database side by side
        top_row = ttk.Frame(scrollable_frame)
        top_row.pack(fill='x', padx=10, pady=5)
        
        # YouTube API section (left)
        api_frame = ttk.LabelFrame(top_row, text="YouTube API Configuration", padding=10)
        api_frame.pack(side='left', fill='both', expand=True, padx=(0, 5))
        
        ttk.Label(api_frame, text="YouTube Data API v3 Key:").pack(anchor='w')
        self.api_key_var = tk.StringVar(value=self.settings.get('youtube_api_key', ''))
        api_entry = ttk.Entry(api_frame, textvariable=self.api_key_var, width=40, show='*')
        api_entry.pack(fill='x', pady=(5, 0))
        
        ttk.Label(api_frame, text="Get your free API key at:\nconsole.cloud.google.com", 
                 foreground='blue', font=('TkDefaultFont', 8)).pack(anchor='w', pady=(5, 0))
        
        # Song Database section (right)
        database_frame = ttk.LabelFrame(top_row, text="Song Database (Optional)", padding=10)
        database_frame.pack(side='left', fill='both', expand=True, padx=(5, 0))
        
        # Database status
        self.database_status_label = ttk.Label(database_frame, text="No database loaded", 
                                             foreground='orange')
        self.database_status_label.pack(anchor='w', pady=(0, 2))
        
        # Database path display
        self.database_path_label = ttk.Label(database_frame, text="", 
                                           foreground='gray', font=('TkDefaultFont', 7))
        self.database_path_label.pack(anchor='w', pady=(0, 5))
        
        # Database controls
        db_button_frame = ttk.Frame(database_frame)
        db_button_frame.pack(fill='x', pady=2)
        
        self.load_db_button = ttk.Button(db_button_frame, text="Load JSON", 
                                        command=self.load_song_database)
        self.load_db_button.pack(side='left', padx=(0, 5))
        
        self.clear_db_button = ttk.Button(db_button_frame, text="Clear", 
                                         command=self.clear_song_database, state='disabled')
        self.clear_db_button.pack(side='left')
        
        # Database info
        database_info = ttk.Label(database_frame, 
                                 text="Load JSON for video duration matching.",
                                 foreground='gray', font=('TkDefaultFont', 8))
        database_info.pack(anchor='w', pady=(5, 0))
        
        # Row 2: Video settings and Sync settings side by side
        middle_row = ttk.Frame(scrollable_frame)
        middle_row.pack(fill='x', padx=10, pady=5)
        
        # Video settings (left)
        video_frame = ttk.LabelFrame(middle_row, text="Video Settings", padding=10)
        video_frame.pack(side='left', fill='both', expand=True, padx=(0, 5))
        
        # Quality selection
        quality_frame = ttk.Frame(video_frame)
        quality_frame.pack(fill='x', pady=2)
        ttk.Label(quality_frame, text="Quality:").pack(side='left')
        self.quality_var = tk.StringVar(value=self.settings.get('preferred_quality', '1080p'))
        quality_combo = ttk.Combobox(quality_frame, textvariable=self.quality_var, 
                                   values=['4K', '1440p', '1080p', '720p', '480p', '360p'], 
                                   state='readonly', width=8)
        quality_combo.pack(side='left', padx=(10, 0))
        
        # Checkboxes
        self.fullscreen_var = tk.BooleanVar(value=self.settings.get('fullscreen', True))
        ttk.Checkbutton(video_frame, text="Start in fullscreen", 
                       variable=self.fullscreen_var).pack(anchor='w', pady=1)
        
        self.muted_var = tk.BooleanVar(value=self.settings.get('muted', True))
        ttk.Checkbutton(video_frame, text="Start muted", 
                       variable=self.muted_var).pack(anchor='w', pady=1)
        
        self.always_on_top_var = tk.BooleanVar(value=self.settings.get('always_on_top', False))
        ttk.Checkbutton(video_frame, text="Keep always on top", 
                       variable=self.always_on_top_var).pack(anchor='w', pady=1)
        
        self.force_quality_var = tk.BooleanVar(value=self.settings.get('force_best_quality', True))
        ttk.Checkbutton(video_frame, text="Force best quality", 
                       variable=self.force_quality_var).pack(anchor='w', pady=1)
        
        # Sync settings (right)
        sync_frame = ttk.LabelFrame(middle_row, text="Synchronization Settings", padding=10)
        sync_frame.pack(side='left', fill='both', expand=True, padx=(5, 0))
        
        self.sync_var = tk.BooleanVar(value=self.settings.get('sync_video_to_song', True))
        ttk.Checkbutton(sync_frame, text="Attempt to sync video to song start", 
                       variable=self.sync_var).pack(anchor='w', pady=1)
        
        self.auto_quit_var = tk.BooleanVar(value=self.settings.get('auto_quit_on_menu', True))
        ttk.Checkbutton(sync_frame, text="Auto-quit VLC on return to song menu", 
                       variable=self.auto_quit_var).pack(anchor='w', pady=1)
        
        # Delay setting
        delay_frame = ttk.Frame(sync_frame)
        delay_frame.pack(fill='x', pady=5)
        ttk.Label(delay_frame, text="Start delay (sec):").pack(anchor='w')
        delay_container = ttk.Frame(delay_frame)
        delay_container.pack(fill='x', pady=2)
        self.delay_var = tk.DoubleVar(value=self.settings.get('video_start_delay', 0.0))
        delay_spin = ttk.Spinbox(delay_container, from_=-10.0, to=10.0, increment=0.5, 
                               textvariable=self.delay_var, width=8)
        delay_spin.pack(side='left')
        ttk.Label(delay_container, text="(-=early)", font=('TkDefaultFont', 8)).pack(side='left', padx=(5, 0))
        
        # Row 3: Advanced section (full width)
        advanced_frame = ttk.LabelFrame(scrollable_frame, text="Advanced (Event Monitoring)", padding=10)
        advanced_frame.pack(fill='x', padx=10, pady=5)
        
        # Debug events checkbox
        self.debug_events_var = tk.BooleanVar(value=self.settings.get('debug_events', True))
        ttk.Checkbutton(advanced_frame, text="Enable detailed event logging of RB3Enhanced events", 
                       variable=self.debug_events_var, 
                       command=self.update_debug_mode).pack(anchor='w', pady=2)
        
        # Event discovery buttons
        event_button_frame = ttk.Frame(advanced_frame)
        event_button_frame.pack(fill='x', pady=5)
        
        self.show_events_button = ttk.Button(event_button_frame, text="Show Event Activity", 
                                           command=self.show_event_discovery, state='disabled')
        self.show_events_button.pack(side='left', padx=(0, 10))
        
        self.clear_events_button = ttk.Button(event_button_frame, text="Clear Event History", 
                                            command=self.clear_event_history, state='disabled')
        self.clear_events_button.pack(side='left')
        
        # Save button
        ttk.Button(scrollable_frame, text="Save Settings", command=self.save_settings).pack(pady=15)
        
        # Pack scrollbar and canvas
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
    
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
        
        # Database status
        self.db_status_control_label = ttk.Label(status_frame, text="Database: Not loaded", foreground='orange')
        self.db_status_control_label.pack(pady=(5, 0))
        
        # Control buttons
        button_frame = ttk.Frame(parent)
        button_frame.pack(pady=20)
        
        self.start_button = ttk.Button(button_frame, text="Start Listening", 
                                     command=self.start_listener, style='Accent.TButton')
        self.start_button.pack(side='left', padx=5)
        
        self.stop_button = ttk.Button(button_frame, text="Stop", 
                                    command=self.stop_listener, state='disabled')
        self.stop_button.pack(side='left', padx=5)
        
        # Web UI button (initially disabled)
        self.web_ui_button = ttk.Button(button_frame, text="Open RBE Web UI", 
                                       command=self.open_web_ui, state='disabled')
        self.web_ui_button.pack(side='left', padx=5)
        
        # RB3Enhanced connection info
        rb3_frame = ttk.LabelFrame(parent, text="RB3Enhanced Connection", padding=10)
        rb3_frame.pack(fill='x', padx=10, pady=5)
        
        self.rb3_info_label = ttk.Label(rb3_frame, text="Waiting for connection...", 
                                      font=('TkDefaultFont', 10))
        self.rb3_info_label.pack()
        
        # Instructions
        instructions_frame = ttk.LabelFrame(parent, text="Setup Instructions", padding=10)
        instructions_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        instructions = """
1. Enter your YouTube Data API v3 key in the Settings tab
2. Load optional song database JSON for better song syncing
3. Configure your video and sync preferences  
4. Make sure VLC Media Player is installed
5. In RB3Enhanced config [Events] section, ensure:
   • EnableEvents = true
   • BroadcastTarget = 255.255.255.255
6. Click "Start Listening" 
7. Launch Rock Band 3 and play a song
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
    
    def auto_load_database(self):
        """Auto-load database if path is saved in settings"""
        database_path = self.settings.get('database_path', '')
        if database_path and os.path.exists(database_path):
            if self.song_database.load_database(database_path):
                # Update UI
                stats = self.song_database.get_stats()
                self.database_status_label.config(
                    text=f"✅ Auto-loaded {stats['loaded_count']} songs", 
                    foreground='green'
                )
                # Show path
                path_display = database_path
                if len(path_display) > 50:
                    path_display = "..." + path_display[-47:]
                self.database_path_label.config(text=f"📁 {path_display}")
                
                self.db_status_control_label.config(
                    text=f"Database: {stats['loaded_count']} songs loaded", 
                    foreground='green'
                )
                self.clear_db_button.config(state='normal')
                self.log_message(f"🎵 Auto-loaded database: {stats['loaded_count']} songs from {database_path}")
            else:
                # Failed to load saved database
                self.database_status_label.config(
                    text="❌ Failed to auto-load saved database", 
                    foreground='red'
                )
                self.log_message(f"❌ Failed to auto-load database from: {database_path}")
        elif database_path:
            # Path saved but file doesn't exist
            self.database_status_label.config(
                text="⚠️ Saved database file not found", 
                foreground='orange'
            )
            self.log_message(f"⚠️ Saved database file not found: {database_path}")
    
    def update_debug_mode(self):
        """Update debug mode for event listener"""
        if self.listener:
            self.listener.debug_events = self.debug_events_var.get()
    
    def show_event_discovery(self):
        """Show all event activity in a popup window"""
        if not self.listener:
            messagebox.showinfo("No Data", "Start listening first to see event activity!")
            return
        
        summary = self.listener.get_event_summary()
        
        # Create popup window
        popup = tk.Toplevel(self.root)
        popup.title("RB3Enhanced Event Monitor")
        popup.geometry("800x600")
        popup.resizable(True, True)
        
        # Create notebook for different views
        notebook = ttk.Notebook(popup)
        notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Known events tab
        known_frame = ttk.Frame(notebook)
        notebook.add(known_frame, text="All RB3Enhanced Events")
        
        known_text = scrolledtext.ScrolledText(known_frame, wrap='word')
        known_text.pack(fill='both', expand=True, padx=10, pady=10)
        
        known_content = "COMPLETE RB3ENHANCED EVENT SPECIFICATION:\n\n"
        known_content += "Based on official RB3Enhanced source code, these are ALL available events:\n\n"
        for event_id, description in summary['known_events'].items():
            known_content += f"Event {event_id}: {description}\n"
        
        known_content += "\n🎯 KEY EVENTS FOR VIDEO SYNC:\n"
        known_content += "• Event 4 (SHORTNAME): Perfect JSON database matching!\n"
        known_content += "• Event 1 (STATE): Song start detection (01=playing)\n"
        known_content += "• Event 9 (SCREEN_NAME): May provide more precise timing\n"
        
        known_text.insert('1.0', known_content)
        known_text.config(state='disabled')
        
        # Unknown events tab (now for truly unknown events only)
        unknown_frame = ttk.Frame(notebook)
        notebook.add(unknown_frame, text="Undocumented Events")
        
        unknown_text = scrolledtext.ScrolledText(unknown_frame, wrap='word')
        unknown_text.pack(fill='both', expand=True, padx=10, pady=10)
        
        unknown_content = "UNDOCUMENTED EVENTS (Beyond Official Specification):\n\n"
        if summary['unknown_events']:
            unknown_content += "⚠️ These events are not in the official RB3Enhanced documentation:\n\n"
            for event_type, info in summary['unknown_events'].items():
                unknown_content += f"Event {event_type}:\n"
                unknown_content += f"  Count: {info['count']} occurrences\n"
                unknown_content += f"  First seen: {info['first_seen']}\n"
                unknown_content += f"  Last seen: {info['last_seen']}\n"
                unknown_content += f"  Sample data: {info['sample_data']}\n\n"
            unknown_content += "These might be from newer RB3Enhanced versions or custom mods."
        else:
            unknown_content += "✅ No undocumented events found!\n\n"
            unknown_content += "All received events match the official RB3Enhanced specification.\n"
            unknown_content += "Events 0-10 are fully documented and supported.\n\n"
            unknown_content += "📝 TIMING NOTES:\n"
            unknown_content += "• No precise countdown/millisecond timing events exist\n"
            unknown_content += "• STATE event (01=ingame) is the best available song start indicator\n"
            unknown_content += "• SCREEN_NAME event may provide additional timing context"
        
        unknown_text.insert('1.0', unknown_content)
        unknown_text.config(state='disabled')
        
        # Recent history tab
        history_frame = ttk.Frame(notebook)
        notebook.add(history_frame, text="Recent Events")
        
        history_text = scrolledtext.ScrolledText(history_frame, wrap='word')
        history_text.pack(fill='both', expand=True, padx=10, pady=10)
        
        history_content = "RECENT EVENT HISTORY:\n\n"
        for event in summary['recent_history']:
            history_content += f"[{event['timestamp']}] Event {event['type']}: '{event['data']}' (size: {event['size']})\n"
        
        history_text.insert('1.0', history_content)
        history_text.config(state='disabled')
        
        # Add close button
        ttk.Button(popup, text="Close", command=popup.destroy).pack(pady=10)
    
    def clear_event_history(self):
        """Clear event monitoring history"""
        if self.listener:
            self.listener.unknown_events = {}
            self.listener.event_history = []
            self.log_message("🗑️ Event monitoring history cleared")
        else:
            messagebox.showinfo("No Listener", "Start listening first!")
    
    def load_song_database(self):
        """Load song database from JSON file"""
        file_path = filedialog.askopenfilename(
            title="Select Song Database JSON File",
            filetypes=[
                ("JSON files", "*.json"),
                ("All files", "*.*")
            ],
            initialdir=os.path.expanduser("~")
        )
        
        if file_path:
            if self.song_database.load_database(file_path):
                # Save the path to settings
                self.settings['database_path'] = file_path
                
                # Update UI
                stats = self.song_database.get_stats()
                self.database_status_label.config(
                    text=f"✅ Loaded {stats['loaded_count']} songs", 
                    foreground='green'
                )
                # Show path
                path_display = file_path
                if len(path_display) > 50:
                    path_display = "..." + path_display[-47:]
                self.database_path_label.config(text=f"📁 {path_display}")
                
                self.db_status_control_label.config(
                    text=f"Database: {stats['loaded_count']} songs loaded", 
                    foreground='green'
                )
                self.clear_db_button.config(state='normal')
                
                # Update VLC player reference
                if self.vlc_player:
                    self.vlc_player.song_database = self.song_database
                
                # Update YouTube searcher reference
                if self.youtube_searcher:
                    self.youtube_searcher.song_database = self.song_database
                    self.youtube_searcher.gui_callback = self.log_message
                
                self.log_message(f"🎵 Song database loaded: {stats['loaded_count']} songs")
                
                # Auto-save settings with new database path
                try:
                    settings_path = self.get_settings_path()
                    with open(settings_path, 'w') as f:
                        json.dump(self.get_current_settings(), f, indent=2)
                    self.log_message(f"💾 Database path saved to settings")
                except Exception as e:
                    self.log_message(f"⚠️ Failed to auto-save database path: {e}")
                    
            else:
                self.database_status_label.config(
                    text="❌ Failed to load database", 
                    foreground='red'
                )
                self.db_status_control_label.config(
                    text="Database: Load failed", 
                    foreground='red'
                )
    
    def clear_song_database(self):
        """Clear the loaded song database"""
        self.song_database = SongDatabase(gui_callback=self.log_message)
        
        # Clear the saved path
        self.settings['database_path'] = ''
        
        self.database_status_label.config(
            text="No database loaded", 
            foreground='orange'
        )
        self.database_path_label.config(text="")
        self.db_status_control_label.config(
            text="Database: Not loaded", 
            foreground='orange'
        )
        self.clear_db_button.config(state='disabled')
        
        # Update VLC player reference
        if self.vlc_player:
            self.vlc_player.song_database = self.song_database
        
        # Update YouTube searcher reference
        if self.youtube_searcher:
            self.youtube_searcher.song_database = self.song_database
            self.youtube_searcher.gui_callback = self.log_message
        
        self.log_message("🗑️ Song database cleared")
        
        # Auto-save settings to clear database path
        try:
            settings_path = self.get_settings_path()
            with open(settings_path, 'w') as f:
                json.dump(self.get_current_settings(), f, indent=2)
            self.log_message(f"💾 Database path cleared from settings")
        except Exception as e:
            self.log_message(f"⚠️ Failed to auto-save cleared database path: {e}")
    
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
            self.show_events_button.config(state='normal')
            self.clear_events_button.config(state='normal')
        else:
            self.status_label.config(text="Stopped", foreground='red')
            self.start_button.config(state='normal')
            self.stop_button.config(state='disabled')
            self.show_events_button.config(state='disabled')
            self.clear_events_button.config(state='disabled')
            
            # Reset IP detection when stopped
            self.detected_ip = None
            self.ip_status_label.config(text="RB3Enhanced: Not detected", foreground='orange')
            self.rb3_info_label.config(text="Waiting for connection...")
            self.web_ui_button.config(state='disabled')
        
        # Update database status in control tab
        if self.song_database.is_loaded():
            stats = self.song_database.get_stats()
            self.db_status_control_label.config(
                text=f"Database: {stats['loaded_count']} songs loaded", 
                foreground='green'
            )
        else:
            self.db_status_control_label.config(
                text="Database: Not loaded", 
                foreground='orange'
            )
        
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
            self.youtube_searcher = YouTubeSearcher(api_key, song_database=self.song_database, gui_callback=self.log_message)
            
            self.log_message("Initializing VLC player...")
            # Create VLC player WITH song database reference
            self.vlc_player = VLCPlayer(
                gui_callback=self.log_message,
                song_database=self.song_database
            )
            
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
            self.listener.debug_events = settings.get('debug_events', True)
            
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
            'always_on_top': self.always_on_top_var.get(),
            'force_best_quality': self.force_quality_var.get(),
            'sync_video_to_song': self.sync_var.get(),
            'auto_quit_on_menu': self.auto_quit_var.get(),
            'video_start_delay': self.delay_var.get(),
            'debug_events': self.debug_events_var.get(),
            'database_path': self.settings.get('database_path', '')
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
                'always_on_top': False,
                'force_best_quality': True,
                'sync_video_to_song': True,
                'auto_quit_on_menu': True,
                'video_start_delay': 0.0,
                'debug_events': True,
                'database_path': ''
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
