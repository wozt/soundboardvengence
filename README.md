# Vengeance Soundboard

Soundboard Linux natif en **GTK 4**, avec cache local, catalogue Freesound, effets GStreamer, macros et routage temporaire PipeWire vers l'entrée de Discord.

## Fonctionnalités

- onglets Populaires, Réactions, Gaming, Cinéma, Ambiance, Favoris et Perso ;
- récupération automatique des sons les mieux notés sur Freesound (sons de moins de 30 secondes) ;
- import de fichiers et téléchargement depuis une URL directe ;
- cache local et affichage de la source/licence ;
- volume 0–150 %, effets écho, chipmunk, démon, robot et accéléré ;
- macros séquentielles avec délai configurable ;
- raccourcis `1` à `9` pour les neuf premiers sons de l'onglet courant ;
- liaison PipeWire créée pendant le son puis supprimée à la fin ;
- réglages et bibliothèque persistants au format JSON.

## Installation

Sur Arch Linux :

```bash
sudo pacman -S gtk4 python-gobject python-requests gstreamer gst-plugins-base \
  gst-plugins-good gst-plugins-bad pipewire pipewire-pulse
python3 -m pip install --user -e .
vengeance-soundboard
```

Sur Debian/Ubuntu, installer les équivalents `gir1.2-gtk-4.0`, `python3-gi`, `python3-requests`, `gstreamer1.0-*`, `pipewire` et `pipewire-bin`, puis :

```bash
PYTHONPATH=src ./run.sh
```

Pour le catalogue, créer une clé gratuite sur <https://freesound.org/apiv2/apply/>. Copier `.env.example` vers `.env`, renseigner `FREESOUND_API_KEY`, puis relancer l'application. La clé peut également être collée dans les réglages. Les préécoutes sont téléchargeables sans OAuth ; la licence et l'auteur restent visibles via le bouton source.

## Discord et PipeWire

Pendant un appel Discord, l'entrée de capture apparaît normalement sous un nom semblable à `WEBRTC VoiceEngine:input_MONO`. L'application détecte ce port avec une expression régulière configurable, relie les sorties `Vengeance Soundboard`, puis retire uniquement les liens qu'elle a créés à la fin de la lecture.

Si Discord n'est pas détecté, lancer :

```bash
pw-link -i
```

et adapter le motif dans Réglages. Le micro existant n'est ni supprimé ni déconnecté.

## Données

- configuration : `~/.config/vengeance-soundboard/config.json` ;
- bibliothèque et sons : `~/.local/share/vengeance-soundboard/`.

Les emplacements suivent `XDG_CONFIG_HOME` et `XDG_DATA_HOME` lorsqu'ils sont définis.
