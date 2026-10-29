# WaveLink → StreamController (Stream Deck +)

Plugin für **StreamController**, damit du WaveLink-Spuren mit den **4 Drehreglern** des Stream Deck+ steuern kannst.

## Bedienung

| Aktion | Effekt |
|--------|--------|
| Drehen | Lautstärke der Spur (± Step) |
| Drücken | Mute / Unmute |
| Anzeige | VU-Meter (Audio-Ausschlag der Spur) + Lautstärke-Balken |

Pro Regler wählst du in den Action-Einstellungen:

- **Spur:** Music, Voice Chat, Game, Browser, System, SFX, Aux, Microphone, Master  
- **Mix:** Monitor (Headset) oder Stream (OBS/Discord)  
- **Step:** z. B. 5 % pro Tick

## Empfohlene Belegung (4 Regler)

1. Music → Monitor  
2. Voice Chat → Monitor  
3. Game → Monitor  
4. Microphone → Stream  

## Voraussetzungen

1. **WaveLink Linux** muss laufen (API auf `127.0.0.1:24772`)  
2. **StreamController** Flatpak  
3. Plugin installiert (macht `install.sh` automatisch)

Nach der Installation StreamController **neu starten**, dann unter Actions **WaveLink → Channel Dial** auf die Dials ziehen.
