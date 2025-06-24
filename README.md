# plex-scripts
Scripts and hints to help with Plex maintenance. These scripts are not endorsed by Plex and could negatively impact your Plex environment.

## Available Scripts

### Category: Playlist Management
#### plex-m3u-to-playlist.py: Create and synchronize a Plex playlist to an M3U file.
Example: Create or synchronise Plex playlist named "Favourites" from the file "Favourites.m3u". Map relative paths (../) in the M3U relative to the current directory. Map local filesystem paths "/Users/user/Music" to container paths "/media/music". The resulting Plex playlist will match the order of the M3U.

```
$ ./plex-m3u-to-playlist.py --path-mapping="/Users/user/Music:/media/music" Favourites.m3u
```

### Category: Plex Hints
#### plex-hint-zfs-and-dsd-audio.md: Meaningfully compress huge DSD albums using ZFS compression

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
