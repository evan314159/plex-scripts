#!/usr/bin/env python3
"""
Script to upload M3U playlist to Plex Media Server
Converts local/real paths to container paths
Converts relative paths (../) to absolute paths
"""

import sys
import os
import argparse
from pathlib import Path
from plexapi.server import PlexServer
from plexapi.exceptions import NotFound

def parse_m3u(m3u_file, local_to_plex_mapping=None):
    """Parse M3U file and return list of file paths
    
    Args:
        m3u_file: Path to the M3U playlist file
        local_to_plex_mapping: Dict mapping local paths to Plex paths (optional)
    """
    tracks = []
    m3u_path = Path(m3u_file).resolve()
    m3u_dir = m3u_path.parent
    
    with open(m3u_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            
            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue
            
            track_path = line
            
            # Handle relative paths by resolving them relative to the M3U file location
            if not os.path.isabs(track_path):
                # Resolve relative path based on M3U file location
                absolute_local_path = (m3u_dir / track_path).resolve()
                track_path = str(absolute_local_path)
            
            # Apply path mapping if provided
            if local_to_plex_mapping:
                track_path = apply_path_mapping(track_path, local_to_plex_mapping)
            
            tracks.append(track_path)
    
    return tracks

def apply_path_mapping(path, mapping):
    """Apply path mapping from local system to Plex container paths
    
    Args:
        path: Local file path
        mapping: Dict with 'local_root' and 'plex_root' keys
    
    Returns:
        Mapped path for Plex
    """
    if not mapping or 'local_root' not in mapping or 'plex_root' not in mapping:
        return path
    
    local_root = Path(mapping['local_root']).resolve()
    plex_root = mapping['plex_root']
    path_obj = Path(path).resolve()
    
    # Check if the path is under the local root
    try:
        relative_path = path_obj.relative_to(local_root)
        # Convert to Plex path using forward slashes
        plex_path = plex_root + '/' + str(relative_path).replace('\\', '/')
        return plex_path
    except ValueError:
        # Path is not under local_root, return unchanged
        return path

def sync_plex_playlist(plex_server, playlist_name, track_paths, music_library):
    """Create or update playlist in Plex to match the given tracks exactly"""
    try:
        # Get the music library
        music = plex_server.library.section(music_library)
        
        print(f"Building track file path index from Plex library...")
        # Build a dictionary mapping file paths to tracks for faster lookup
        file_to_track = {}
        all_tracks = music.searchTracks()
        for track in all_tracks:
            for media in track.media:
                for part in media.parts:
                    file_to_track[part.file] = track
        
        print(f"Found {len(file_to_track)} tracks in Plex library")
        
        # Find tracks in Plex library
        plex_tracks = []
        not_found = []
        
        for track_path in track_paths:
            if track_path in file_to_track:
                plex_tracks.append(file_to_track[track_path])
            else:
                not_found.append(track_path)
        
        if not_found:
            print(f"Warning: {len(not_found)} tracks not found in Plex library:")
            for track in not_found:
                print(f"  {track}")
        
        # Check if playlist already exists
        existing_playlist = None
        try:
            existing_playlist = plex_server.playlist(playlist_name)
            print(f"Found existing playlist '{playlist_name}' with {len(existing_playlist.items())} tracks")
        except NotFound:
            print(f"Playlist '{playlist_name}' does not exist, will create new one")
        
        if existing_playlist is not None:
            # Update existing playlist to match M3U exactly
            existing_items = existing_playlist.items()
            existing_track_ids = {item.ratingKey for item in existing_items}
            new_track_ids = {track.ratingKey for track in plex_tracks}
            
            # Find tracks to remove (in existing but not in new)
            tracks_to_remove = [item for item in existing_items if item.ratingKey not in new_track_ids]
            
            # Find tracks to add (in new but not in existing)
            tracks_to_add = [track for track in plex_tracks if track.ratingKey not in existing_track_ids]
            
            # Check if order needs to change by comparing the full sequence
            order_changed = False
            if len(existing_items) == len(plex_tracks):
                # Same length, check if order matches
                for i, (existing, new) in enumerate(zip(existing_items, plex_tracks)):
                    if existing.ratingKey != new.ratingKey:
                        order_changed = True
                        break
            else:
                # Different lengths mean order will definitely change
                order_changed = True
            
            # Report all changes
            if tracks_to_remove:
                print(f"Removing {len(tracks_to_remove)} tracks:")
                for item in tracks_to_remove:
                    print(f"- {item.title} - {item.grandparentTitle}")
            
            if tracks_to_add:
                print(f"Adding {len(tracks_to_add)} tracks:")
                for track in tracks_to_add:
                    print(f"+ {track.title} - {track.grandparentTitle}")
            
            if order_changed and not tracks_to_remove and not tracks_to_add:
                print("Reordering playlist to match M3U...")
                for track in plex_tracks:
                    print(f"~ {track.title} - {track.grandparentTitle}")
            
            # Apply changes: always rebuild playlist to ensure correct order
            if tracks_to_remove or tracks_to_add or order_changed:
                print("Updating playlist to match M3U...")
                existing_playlist.removeItems(existing_playlist.items())
                existing_playlist.addItems(plex_tracks)
                print(f"Updated playlist '{playlist_name}' - now has {len(plex_tracks)} tracks")
            else:
                print(f"Playlist '{playlist_name}' is already up to date with {len(plex_tracks)} tracks")
                
            return existing_playlist
        else:
            # Create new playlist
            if plex_tracks:
                print(f"Adding {len(plex_tracks)} tracks to new playlist:")
                for track in plex_tracks:
                    print(f"+ {track.title} - {track.grandparentTitle}")
                playlist = plex_server.createPlaylist(playlist_name, items=plex_tracks)
                print(f"Created playlist '{playlist_name}' with {len(plex_tracks)} tracks")
                return playlist
            else:
                print("No tracks found in Plex library. Cannot create empty playlist.")
                return None
            
    except Exception as e:
        print(f"Error syncing playlist: {e}")
        return None

def parse_path_mapping(mapping_str):
    """Parse path mapping string in format 'local_root:plex_root'"""
    if not mapping_str:
        return None
    
    try:
        local_root, plex_root = mapping_str.split(':', 1)
        return {
            'local_root': local_root.strip(),
            'plex_root': plex_root.strip()
        }
    except ValueError:
        print(f"Error: Invalid path mapping format '{mapping_str}'. Use 'local_root:plex_root'")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description="Upload M3U playlist to Plex Media Server. Converts local/real paths to container paths and handles relative paths.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment variables:
  PLEX_URL              Default Plex server URL
  PLEX_TOKEN            Plex authentication token

Examples:
  python plex_m3u_to_playlist.py --plex-token TOKEN123 playlist.m3u
  python plex_m3u_to_playlist.py --playlist 'My Playlist' --plex-token TOKEN123 playlist.m3u
  python plex_m3u_to_playlist.py \\
    --plex-url http://plex:32400 --plex-token TOKEN123 \\
    --path-mapping '/home/user/music:/media/music' playlist.m3u
        """
    )
    
    parser.add_argument('m3u_file', 
                       help='Path to the M3U playlist file')
    parser.add_argument('--playlist', 
                       help='Name for the Plex playlist (default: M3U filename)')
    parser.add_argument('--plex-url', 
                       default=os.getenv('PLEX_URL', 'http://localhost:32400'),
                       help='Plex server URL (default: http://localhost:32400)')
    parser.add_argument('--plex-token', 
                       default=os.getenv('PLEX_TOKEN'),
                       help='Plex authentication token (required)')
    parser.add_argument('--music-library', 
                       default='Music',
                       help='Name of music library in Plex (default: Music)')
    parser.add_argument('--path-mapping', 
                       help="Path mapping in format 'local_library_root:container_library_root'")
    
    args = parser.parse_args()
    
    # Extract arguments
    m3u_file = args.m3u_file
    playlist_name = args.playlist
    plex_url = args.plex_url
    plex_token = args.plex_token
    music_library = args.music_library
    path_mapping = parse_path_mapping(args.path_mapping) if args.path_mapping else None
    
    # Default playlist name from M3U filename if not specified
    if playlist_name is None:
        m3u_path = Path(m3u_file)
        playlist_name = m3u_path.stem
    
    if not plex_token:
        print("Error: Plex token required. Provide via --plex-token or PLEX_TOKEN environment variable.")
        sys.exit(1)
    
    if not os.path.exists(m3u_file):
        print(f"Error: M3U file '{m3u_file}' not found.")
        sys.exit(1)
    
    # Parse M3U file
    print(f"Parsing M3U file: {m3u_file}")
    if path_mapping:
        print(f"Using path mapping: {path_mapping['local_root']} -> {path_mapping['plex_root']}")
    track_paths = parse_m3u(m3u_file, path_mapping)
    print(f"Found {len(track_paths)} tracks in M3U file")
    
    if not track_paths:
        print("No tracks found in M3U file.")
        sys.exit(1)
    
    # Connect to Plex
    try:
        print(f"Connecting to Plex server: {plex_url}")
        plex = PlexServer(plex_url, plex_token)
        print(f"Connected to Plex server: {plex.friendlyName}")
    except Exception as e:
        print(f"Error connecting to Plex server: {e}")
        sys.exit(1)
    
    # Sync playlist
    playlist = sync_plex_playlist(plex, playlist_name, track_paths, music_library)
    
    if playlist is not None:
        print(f"Playlist sync completed successfully!")
    else:
        print("Failed to sync playlist.")
        sys.exit(1)

if __name__ == "__main__":
    main()
