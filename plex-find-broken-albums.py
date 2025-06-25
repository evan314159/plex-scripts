#!/usr/bin/env python3
from collections import defaultdict
import sys
from plexapi.server import PlexServer

def load_plex_data(plex_url, plex_token, music_library_name='Music'):
    """Load all track data with album ID and file directory."""
    import sys
    import os
    
    plex = PlexServer(plex_url, plex_token)
    music_library = plex.library.section(music_library_name)
    
    data = []
    
    # Get all tracks at once - much more efficient than album-by-album
    print("Fetching all tracks...", file=sys.stderr, flush=True)
    all_tracks = music_library.searchTracks()
    print(f"Retrieved {len(all_tracks)} tracks, processing...", file=sys.stderr, flush=True)
    
    for track in all_tracks:
        # Get album ID from parent key and directory from track location
        album_id = str(track.parentRatingKey) if hasattr(track, 'parentRatingKey') else None
        
        if album_id and hasattr(track, 'locations') and track.locations:
            for location in track.locations:
                directory = os.path.dirname(location)
                data.append({
                    'directory': directory,
                    'album_id': album_id
                })
    
    print(f"Finished processing {len(all_tracks)} tracks", file=sys.stderr)
    return data

def find_broken_albums(data):
    """Find broken albums: directories with multiple album IDs and album IDs spanning multiple directories."""
    broken_album_files = []
    
    # Group by directory
    directories = defaultdict(list)
    for row in data:
        directory = row['directory']
        album_id = row['album_id']
        if directory and album_id:
            directories[directory].append(album_id)
    
    # Check for multiple album IDs within the same directory
    for directory, album_ids in directories.items():
        unique_album_ids = set(album_ids)
        if len(unique_album_ids) > 1:
            broken_album_files.append(directory)
    
    # Group by album ID
    albums = defaultdict(list)
    for row in data:
        directory = row['directory']
        album_id = row['album_id']
        if directory and album_id:
            albums[album_id].append(directory)
    
    # Check for multiple directories within the same album ID
    for album_id, dirs in albums.items():
        unique_dirs = set(dirs)
        if len(unique_dirs) > 1:
            broken_album_files.extend(unique_dirs)
    
    return list(set(broken_album_files))

def print_plex_dance_output(file_paths):
    """Print file paths in format ready for plex-dance.sh."""
    import sys
    
    if not file_paths:
        print("No broken albums found.", file=sys.stderr)
        return

    print(f"Found {len(file_paths)} directories with broken albums:", file=sys.stderr)
    for file_path in sorted(file_paths):
        print(file_path)

def main():
    import argparse
    import os
    
    parser = argparse.ArgumentParser(
        description="Find broken albums in Plex library - directories with tracks mapped to different album IDs and vice-versa.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment variables:
  PLEX_URL              Default Plex server URL
  PLEX_TOKEN            Plex authentication token

Examples:
  python plex-find-broken-albums.py --plex-token TOKEN123
  python plex-find-broken-albums.py --plex-url http://plex:32400 --plex-token TOKEN123
        """
    )
    
    parser.add_argument('--plex-url', 
                       default=os.getenv('PLEX_URL', 'http://localhost:32400'),
                       help='Plex server URL (default: http://localhost:32400)')
    parser.add_argument('--plex-token', 
                       default=os.getenv('PLEX_TOKEN'),
                       help='Plex authentication token (required)')
    parser.add_argument('--music-library', 
                       default='Music',
                       help='Name of music library in Plex (default: Music)')
    
    args = parser.parse_args()
    
    if not args.plex_token:
        print("Error: Plex token is required. Use --plex-token or set PLEX_TOKEN environment variable.", file=sys.stderr)
        sys.exit(1)
    
    try:
        # Load Plex data and find broken album files
        plex_data = load_plex_data(args.plex_url, args.plex_token, args.music_library)
        print(f"Analyzing {len(plex_data)} track entries for broken albums...", file=sys.stderr)
        
        broken_album_files = find_broken_albums(plex_data)
        
        # Print file paths for plex-dance.sh
        print_plex_dance_output(broken_album_files)
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()

