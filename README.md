# plex-scripts
Scripts and hints to help with Plex music library management. These scripts are not endorsed by Plex and could negatively impact your Plex environment.

## Available Scripts and Hints

| Category | Script | Description |
| :------- | :----- | :---------- |
| **Playlists** | [plex-m3u-to-playlist.py](plex-m3u-to-playlist.py) | Automates creating and synchronising a Plex playlist from an M3U file. |
| **Library** Health | [plex-find-broken-albums.py](plex-find-broken-albums.py) | Automates finding broken albums, including albums with tracks mapped to multiple album IDs (appear split across multiple albums in Plex) and albums combining tracks from different directories (appear to be merged into one album). These can then be corrected by updating metadata and/or [Plex Dancing](https://www.plexopedia.com/plex-media-server/general/plex-dance/). |
| | [plex-dance.py](plex-dance.py) | Use the output from plex-find-broken-albums.py to automate [Plex Dancing](https://www.plexopedia.com/plex-media-server/general/plex-dance/) the broken albums. Automating Plex Dancing should only be considered when there are a large number of albums to Dance, and only after having made a library backup/zfs snapshot.  WARNING: This script temporarily moves files out of your library to a temporary directory, and then moves them back after confirming Plex no longer sees the album (Plex Dancing). Read all directions carefully. Do not interrupt it while running. After successfully Plex Dancing, the album will be removed from playlists and any metadata such as ratings will need to be re-applied. |
| **Ratings** | [plex-ratings-remove.md](plex-ratings-remove.md) | Automates removing ratings from all Plex library albums and tracks. |
| **Plex Hints** | [plex-hint-zfs-and-dsd-audio.md](plex-hint-zfs-and-dsd-audio.md) | Meaningfully compress huge DSD albums using ZFS compression. |

## Getting Help
Scripts print detailed usage instructions when run with argument --help. They will also print brief usage instructions when run with no arguments unless intended to be used in pipes.

## Environment Setup
Scripts run on python3 from brew.  Modules are installed in uv virtual environments.  Scripts may require plexapi or other Python modules.

Scripts use the following environment variables:
* PLEX_URL: URL for your Plex server, default is http://localhost:32400
* PLEX_TOKEN: the active Plex token

Example environment setup:
```
$ export PLEX_URL=http://plexserver:32400
$ export PLEX_TOKEN=your-plex-token
$ brew install python3 uv
$ uv venv
$ source .venv/bin/activate
$ uv pip install plexapi
```

My Plex is deployed in a Docker container using the Plex standard container image.
