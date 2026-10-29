# Spotify StreamController Plugin

Ordner: `~/.local/share/wavelink-linux/Spotify`

## Buttons

- Play / Pause  
- Next Song  
- Previous Song  
- Shuffle  
- Favourite (Like)  
- Repeat (off → all → one)

## Setup

1. Im [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) bei deiner App unter **Redirect URIs** eintragen:

   `http://127.0.0.1:41837/callback`

2. StreamController neu starten  
3. Plugin-Einstellungen → **Spotify** → **Bei Spotify anmelden**  
4. Browser freigeben, dann Actions auf die Keys ziehen  

Spotify-App sollte laufen (Premium für Remote Control).

## Install

Wird nach `~/.var/app/com.core447.StreamController/data/plugins/Spotify` kopiert.
