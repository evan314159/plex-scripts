#!/usr/bin/env python3
"""
Script to remove all user ratings from tracks in Plex music libraries
"""

import sys
import os
import argparse
from plexapi.server import PlexServer

def main():
    parser = argparse.ArgumentParser(
        description="Remove all user ratings from tracks and albums in Plex music libraries. Runs in dry-run mode by default.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment variables:
  PLEX_URL              Default Plex server URL
  PLEX_TOKEN            Plex authentication token

Examples:
  python plex-ratings-remove.py --plex-token TOKEN123
  python plex-ratings-remove.py --plex-url http://plex:32400 --plex-token TOKEN123 --no-dry-run
        """
    )
    
    parser.add_argument('--plex-url', 
                       default=os.getenv('PLEX_URL', 'http://localhost:32400'),
                       help='Plex server URL (default: http://localhost:32400)')
    parser.add_argument('--plex-token', 
                       default=os.getenv('PLEX_TOKEN'),
                       help='Plex authentication token (required)')
    parser.add_argument('--no-dry-run', 
                       action='store_true',
                       help='Actually remove ratings (default is dry-run mode)')
    
    args = parser.parse_args()
    
    plex_url = args.plex_url
    plex_token = args.plex_token
    dry_run = not args.no_dry_run
    
    if not plex_token:
        print("Error: Plex token required. Provide via --plex-token or PLEX_TOKEN environment variable.")
        sys.exit(1)
    
    if dry_run:
        print("*** DRY RUN MODE - No ratings will actually be removed ***")
        print("*** Use --no-dry-run to actually remove ratings ***")
        print()
    
    # Connect to the Plex server
    try:
        print(f"Connecting to Plex server: {plex_url}")
        plex = PlexServer(plex_url, plex_token)
        print(f"Connected to Plex server: {plex.friendlyName}")
    except Exception as e:
        print(f"Error connecting to Plex server: {e}")
        sys.exit(1)
    
    # Get all music libraries
    print("Fetching music libraries...")
    music_libraries = [lib for lib in plex.library.sections() if lib.type == 'artist']
    
    if not music_libraries:
        print("No music libraries found.")
        return
    
    total_tracks = 0
    success_count = 0
    
    # Process each music library
    for library in music_libraries:
        print(f"\nProcessing library: {library.title}")
        
        # Get rated tracks - use very low threshold to catch all ratings
        print("Fetching rated tracks...")
        try:
            rated_tracks = library.search(libtype='track', filters={'userRating>>=': -10})
        except Exception as e:
            print(f"Error searching for rated tracks: {e}")
            rated_tracks = []

        # Get rated albums - use very low threshold to catch all ratings  
        print("Fetching rated albums...")
        try:
            rated_albums = library.search(libtype='album', filters={'userRating>>=': -10})
        except Exception as e:
            print(f"Error searching for rated albums: {e}")
            rated_albums = []
        
        if not rated_tracks and not rated_albums:
            print("No rated tracks or albums found in this library.")
            continue
            
        print(f"Found {len(rated_tracks)} rated tracks and {len(rated_albums)} rated albums.")
        
        # Remove ratings from tracks
        for i, track in enumerate(rated_tracks, 1):
            try:
                title = track.title
                artist = getattr(track, 'grandparentTitle', 'Unknown Artist')
                rating = getattr(track, 'userRating', None)
                
                if dry_run:
                    print(f"[{i}/{len(rated_tracks)}] Would remove track rating: {artist} - {title} (rating: {rating})")
                    success_count += 1
                else:
                    print(f"[{i}/{len(rated_tracks)}] Removing track rating: {artist} - {title} (rating: {rating})")
                    track.rate(None)
                    success_count += 1
                
            except Exception as e:
                print(f"Error removing track rating: {e}")
        
        # Remove ratings from albums
        for i, album in enumerate(rated_albums, 1):
            try:
                title = album.title
                artist = getattr(album, 'parentTitle', 'Unknown Artist')
                rating = getattr(album, 'userRating', None)
                
                if dry_run:
                    print(f"[{i}/{len(rated_albums)}] Would remove album rating: {artist} - {title} (rating: {rating})")
                    success_count += 1
                else:
                    print(f"[{i}/{len(rated_albums)}] Removing album rating: {artist} - {title} (rating: {rating})")
                    album.rate(None)
                    success_count += 1
                
            except Exception as e:
                print(f"Error removing album rating: {e}")
    
    if dry_run:
        print(f"\nDry run completed! Found {success_count} ratings that would be removed.")
        print("Use --no-dry-run to actually remove the ratings.")
    else:
        print(f"\nCompleted! Successfully removed {success_count} ratings from tracks and albums.")

if __name__ == "__main__":
    main()
