# RBEnhanced Music Video Player
This script listens for RB3Enhanced network events and automatically searches for and plays music videos based on 
the chosen song using yt-dlp and VLC media player. I use this on a laptop hooked up to a second TV where we pick 
songs using the RBEnhanced web page.  
## GUI Version Instructions
1. Get a YouTube Data API v3 key from Google Cloud Console and enter the key in the Settings tab
2. Configure your video and sync preferences
3. Make sure VLC Media Player is installed
4. In RB3Enhanced config [Events] section, ensure:
```
EnableEvents = true
BroadcastTarget = 255.255.255.255
```
6. Click "Start Listening" 
7. Launch Rock Band 3 and play a song!
