# RBEnhanced Music Video Player
This script listens for RB3Enhanced network events and automatically searches for and plays music videos based on 
the chosen song using yt-dlp and VLC media player. I use this on a laptop hooked up to a second TV where we pick 
songs using the RBEnhanced web page.  

It searches for "(artist) (song) official music video" "(artist) (song) music video" and "(artist) (song) official"
in that order and picks the top result based on relevency as well as song length if song database is provided (see 
below). If a music video is not avalable, it will play an audio version that usually just has album art as the image.

Requirements:
```
pip install google-api-python-client yt-dlp
```
## Screenshots

<img width="400" height="350" alt="image" src="https://github.com/user-attachments/assets/bb011aa5-625e-4eb8-bb39-9c67e129825f" />

<img width="400" height="350" alt="image" src="https://github.com/user-attachments/assets/e34b21e0-6c15-4f69-bc41-53a0139cd43d" />


<img width="400" height="350" alt="image" src="https://github.com/user-attachments/assets/851e720f-9556-45b5-85dc-8d26c9950a4a" />

## Instructions
1. Get a YouTube Data API v3 key from Google Cloud Console and enter the key in the Settings tab
2. Load optional song database JSON for better song syncing
3. Configure your video and sync preferences  
4. Make sure VLC Media Player is installed
5. In RB3Enhanced config [Events] section, ensure:
```
EnableEvents = true
BroadcastTarget = 255.255.255.255
```
6. Click "Start Listening" 
7. Launch Rock Band 3 and play a song

## Optional Song Database
You can also provide a JSON dump of your RB3 song cache to better match track lengths to videos in
order for them to sync better. To do this the RB3 song cache file needs to be loaded into Nautilis
and exported with the following settings to include track lengths:

<img width="400" height="300" alt="image" src="https://github.com/user-attachments/assets/29e323fa-6a25-4873-834b-c36f8361b511" />

JSON example:
```
{
"setlist":
[
{
"artist" : "\"Weird Al\" Yankovic",
"name" : "Gump",
"vocal_parts" : 2,
"duration" : "2:17",
"drums_diff" : "4",
"bass_diff" : "3",
"guitar_diff" : "3",
"keys_diff" : "0",
"vocal_diff" : "3",
"rating" : "SR",
"genre" : "Novelty",
"album" : "Bad Hair Day",
"track_number" : 7,
"master" : true,
"year_recorded" : 1996,
"year_released" : 1996,
"subgenre" : "",
"proguitar_diff" : "0",
"probass_diff" : "0",
"prokeys_diff" : "0",
"band_diff" : "3",
"shortname" : "Gumpv3",
"songid" : 2133037298,
"songid_string" : "",
"source" : "ugc_plus",
"filepath" : "songs/Gump/Gump",
"midifile" : "",
"preview_start" : 16000,
"preview_end" : 46000,
"version" : 30,
"scroll_speed" : 2300,
"tonic_note" : -1,
"tonality" : -1,
"percussion_bank" : "sfx/tambourine_bank.milo",
"drum_bank" : "sfx/kit01_bank.milo",
"bass_tuning" : "",
"guitar_tuning" : ""
}
```
