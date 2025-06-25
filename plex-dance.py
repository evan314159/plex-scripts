#!/usr/bin/env python3
"""
Plex Dance script - temporarily moves files to force Plex to refresh its database
"""

import sys
import os
import time
import shutil
import tempfile
import argparse
from pathlib import Path
from plexapi.server import PlexServer
import shlex
import signal
import atexit

def apply_path_mapping(path, mapping):
    """Apply path mapping from Plex container paths to local system paths
    
    Args:
        path: Plex file path
        mapping: Dict with 'local_root' and 'plex_root' keys
    
    Returns:
        Mapped path for local system
    """
    if not mapping or 'local_root' not in mapping or 'plex_root' not in mapping:
        return path
    
    plex_root = mapping['plex_root']
    local_root = mapping['local_root']
    
    # Replace plex_root with local_root
    if path.startswith(plex_root):
        return path.replace(plex_root, local_root, 1)
    else:
        return path

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

def are_on_same_filesystem(path1, path2):
    """Check if two paths are on the same filesystem"""
    try:
        # If path2 doesn't exist, check its parent directory
        check_path2 = path2
        while not os.path.exists(check_path2):
            parent = os.path.dirname(check_path2)
            if parent == check_path2:  # reached root
                return False
            check_path2 = parent
        
        stat1 = os.stat(path1)
        stat2 = os.stat(check_path2)
        return stat1.st_dev == stat2.st_dev
    except OSError:
        return False

def move_file(orig_path, temp_path, original_plex_path=None):
    """Move a single file to temporary location using atomic rename"""
    try:
        # First check if source exists and is accessible
        if not os.path.exists(orig_path):
            if original_plex_path:
                print(f"Warning: Translated path does not exist: {orig_path} (from {original_plex_path})")
            else:
                print(f"Warning: Source path does not exist: {orig_path}")
            return False
        
        # Create parent directory if needed
        os.makedirs(os.path.dirname(temp_path), exist_ok=True)
        
        # Check if on same filesystem for atomic operation
        if not are_on_same_filesystem(orig_path, temp_path):
            if original_plex_path:
                print(f"Error: Source and temp directory not on same filesystem: {orig_path} (from {original_plex_path})")
            else:
                print(f"Error: Source and temp directory not on same filesystem: {orig_path}")
            return False
        
        # Use os.rename for atomic operation
        os.rename(orig_path, temp_path)
        
        # Also move any associated AppleDouble file
        parent_dir = os.path.dirname(orig_path)
        basename = os.path.basename(orig_path)
        appledouble_orig = os.path.join(parent_dir, f"._{basename}")
        appledouble_temp = os.path.join(os.path.dirname(temp_path), f"._{os.path.basename(temp_path)}")
        
        if os.path.exists(appledouble_orig):
            try:
                os.rename(appledouble_orig, appledouble_temp)
            except Exception:
                pass  # AppleDouble file move failed, but that's not critical
        
        return True
    except FileNotFoundError as e:
        if original_plex_path:
            print(f"File not found: {orig_path} (from {original_plex_path})")
        else:
            print(f"File not found: {orig_path}")
        return False
    except PermissionError as e:
        if original_plex_path:
            print(f"Permission denied: {orig_path} (from {original_plex_path})")
        else:
            print(f"Permission denied: {orig_path}")
        return False
    except OSError as e:
        if original_plex_path:
            print(f"Filesystem error with {orig_path} (from {original_plex_path}): {e}")
        else:
            print(f"Filesystem error with {orig_path}: {e}")
        return False
    except Exception as e:
        if original_plex_path:
            print(f"Error moving {orig_path} (from {original_plex_path}) to {temp_path}: {e}")
        else:
            print(f"Error moving {orig_path} to {temp_path}: {e}")
        return False

def restore_file(temp_path, orig_path):
    """Restore a single file from temporary location using atomic rename"""
    try:
        # Create parent directory if needed
        os.makedirs(os.path.dirname(orig_path), exist_ok=True)
        # Use os.rename for atomic operation
        os.rename(temp_path, orig_path)
        
        # Also restore any associated AppleDouble file
        temp_basename = os.path.basename(temp_path)
        orig_basename = os.path.basename(orig_path)
        appledouble_temp = os.path.join(os.path.dirname(temp_path), f"._{temp_basename}")
        appledouble_orig = os.path.join(os.path.dirname(orig_path), f"._{orig_basename}")
        
        if os.path.exists(appledouble_temp):
            try:
                os.rename(appledouble_temp, appledouble_orig)
            except Exception:
                pass  # AppleDouble file restore failed, but that's not critical
        
        return True
    except Exception as e:
        print(f"Error restoring {temp_path} to {orig_path}: {e}")
        return False

def get_plex_library_locations(plex_url, plex_token, music_library_name='Music'):
    """Get the library locations from Plex server"""
    try:
        plex = PlexServer(plex_url, plex_token)
        music_library = plex.library.section(music_library_name)
        locations = music_library.locations
        print(f"Plex library locations: {locations}", file=sys.stderr)
        return locations
    except Exception as e:
        print(f"Error: Could not connect to Plex or get library locations: {e}", file=sys.stderr)
        print("Check your Plex URL, token, and library name, or use --skip-validation", file=sys.stderr)
        sys.exit(1)

def check_albums_removed_from_plex(plex_url, plex_token, music_library_name, moved_albums_with_ids, path_mapping=None):
    """Check if moved albums are no longer visible in Plex library using fast album ID lookup"""
    try:
        print("connecting...", file=sys.stderr, end=" ", flush=True)
        plex = PlexServer(plex_url, plex_token)
        music_library = plex.library.section(music_library_name)
        
        total_albums_to_check = sum(len(album_ids) for _, album_ids in moved_albums_with_ids)
        print(f"checking {total_albums_to_check} albums...", file=sys.stderr, end=" ", flush=True)
        
        still_visible_paths = []
        
        # Check each moved path and its associated album IDs
        for plex_path, album_ids in moved_albums_with_ids:
            if not album_ids:
                # Legacy mode: fall back to path-based checking
                print("(legacy check)", file=sys.stderr, end=" ", flush=True)
                # Get all albums and check by path - this is the old slow method
                all_albums = music_library.searchAlbums()
                for album in all_albums:
                    tracks = album.tracks()
                    if tracks and hasattr(tracks[0], 'locations') and tracks[0].locations:
                        track_path = tracks[0].locations[0]
                        album_dir = os.path.dirname(track_path)
                        if album_dir == plex_path:
                            still_visible_paths.append(plex_path)
                            break
            else:
                # Fast mode: check specific album IDs
                path_has_visible_albums = False
                for album_id in album_ids:
                    try:
                        # Try to fetch the album by ID - if it exists, the album is still visible
                        album = music_library.fetchItem(int(album_id))
                        if album:
                            path_has_visible_albums = True
                            break
                    except Exception:
                        # Album not found = it's been removed (what we want)
                        continue
                
                if path_has_visible_albums:
                    still_visible_paths.append(plex_path)
        
        return len(still_visible_paths) == 0, len(still_visible_paths)
        
    except Exception as e:
        print(f"Warning: Could not check Plex status: {e}", file=sys.stderr)
        return False, len(moved_albums_with_ids)

def validate_paths_in_library(file_paths, library_locations, path_mapping=None):
    """Validate that all paths are within Plex library directories"""
    if not library_locations:
        print("Warning: No library locations available for validation", file=sys.stderr)
        return file_paths
    
    valid_paths = []
    invalid_paths = []
    
    for path in file_paths:
        # Apply reverse path mapping for validation (local -> plex path)
        validation_path = path
        if path_mapping:
            validation_path = path.replace(path_mapping['local_root'], path_mapping['plex_root'], 1)
        
        # Check if path is within any library location
        is_valid = any(validation_path.startswith(loc) for loc in library_locations)
        
        if is_valid:
            valid_paths.append(path)
        else:
            invalid_paths.append(path)
    
    if invalid_paths:
        print(f"Error: {len(invalid_paths)} paths are outside Plex library locations:", file=sys.stderr)
        for path in invalid_paths[:5]:  # Show first 5
            print(f"  {path}", file=sys.stderr)
        if len(invalid_paths) > 5:
            print(f"  ... and {len(invalid_paths) - 5} more", file=sys.stderr)
        sys.exit(1)
    
    return valid_paths

# Global variables for signal handling
library_temp_dirs = {}
temp_paths = []
file_paths = []

def cleanup_and_restore():
    """Cleanup function called on exit or signal"""
    global library_temp_dirs, temp_paths, file_paths
    
    if not library_temp_dirs:
        return
    
    # Prevent multiple cleanup calls
    temp_dirs_to_clean = library_temp_dirs.copy()
    library_temp_dirs.clear()
        
    print("\n🔄 Cleaning up and restoring files...", file=sys.stderr)
    
    # Restore any files still in temp directories
    for library_root, temp_dir in temp_dirs_to_clean.items():
        try:
            if os.path.exists(temp_dir):
                # Check for any files that need restoring
                temp_files = os.listdir(temp_dir)
                album_dirs = [f for f in temp_files if not f.startswith('.') and f not in ['lock', 'restore.log']]
                
                if album_dirs:
                    print(f"Restoring {len(album_dirs)} albums from {temp_dir}...", file=sys.stderr)
                    for temp_file in album_dirs:
                        temp_path = os.path.join(temp_dir, temp_file)
                        if os.path.isdir(temp_path):
                            # Find original path from our tracking
                            for i, tracked_temp_path in enumerate(temp_paths):
                                if tracked_temp_path == temp_path and i < len(file_paths):
                                    orig_path = file_paths[i]
                                    try:
                                        print(f"Restoring {os.path.basename(temp_path)} to {orig_path}", file=sys.stderr)
                                        os.rename(temp_path, orig_path)
                                    except Exception as restore_e:
                                        print(f"Failed to restore {temp_path}: {restore_e}", file=sys.stderr)
                                    break
                            else:
                                print(f"Warning: Could not determine original location for {temp_path}", file=sys.stderr)
                
                # Remove temp directory (including any leftover AppleDouble files)
                try:
                    shutil.rmtree(temp_dir)
                    print(f"Cleaned up {temp_dir}", file=sys.stderr)
                except OSError as e:
                    print(f"Warning: Failed to remove temp directory {temp_dir}: {e}", file=sys.stderr)
                    # Try to remove remaining files manually
                    try:
                        for remaining_file in os.listdir(temp_dir):
                            remaining_path = os.path.join(temp_dir, remaining_file)
                            if os.path.isfile(remaining_path):
                                os.remove(remaining_path)
                        os.rmdir(temp_dir)
                        print(f"Cleaned up {temp_dir} after manual file removal", file=sys.stderr)
                    except Exception as cleanup_e:
                        print(f"Could not fully clean up {temp_dir}: {cleanup_e}", file=sys.stderr)
        except Exception as e:
            print(f"Warning: Failed to clean up {temp_dir}: {e}", file=sys.stderr)

def truncate_utf8_safe(text, max_bytes):
    """Truncate text to max_bytes while preserving valid UTF-8"""
    if len(text.encode('utf-8')) <= max_bytes:
        return text
    
    # Start with max_bytes and work backwards to find valid UTF-8 boundary
    encoded = text.encode('utf-8')
    for i in range(max_bytes, 0, -1):
        try:
            truncated = encoded[:i].decode('utf-8')
            return truncated
        except UnicodeDecodeError:
            continue
    
    # Fallback: just return ascii-safe characters
    return ''.join(c for c in text if ord(c) < 128)[:max_bytes]

def safe_temp_name(index, artist, album, max_filename_bytes=255):
    """Create a safe temp directory name under filesystem limits"""
    # Remove problematic characters
    safe_chars = lambda s: ''.join(c if c.isalnum() or c in '-_. ' else '_' for c in s)
    artist = safe_chars(artist)
    album = safe_chars(album)
    
    # Start with the full name
    base_name = f"{index}_{artist}_{album}"
    
    # If it's already short enough, return it
    if len(base_name.encode('utf-8')) <= max_filename_bytes:
        return base_name
    
    # Calculate space needed for index and separators
    index_part = f"{index}_"
    remaining_bytes = max_filename_bytes - len(index_part.encode('utf-8')) - 1  # -1 for separator
    
    # Split remaining space between artist and album
    artist_bytes = remaining_bytes // 2
    album_bytes = remaining_bytes - artist_bytes
    
    # Truncate artist and album safely
    artist_trunc = truncate_utf8_safe(artist, artist_bytes)
    album_trunc = truncate_utf8_safe(album, album_bytes)
    
    return f"{index}_{artist_trunc}_{album_trunc}"

def signal_handler(signum, frame):
    """Handle interrupt signals gracefully"""
    print(f"\n⚠️  Received signal {signum}, cleaning up...", file=sys.stderr)
    cleanup_and_restore()
    # Unregister atexit handler to prevent double cleanup
    atexit.unregister(cleanup_and_restore)
    sys.exit(1)

def main():
    global library_temp_dirs, temp_paths, file_paths
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    atexit.register(cleanup_and_restore)
    
    parser = argparse.ArgumentParser(
        description='Plex Dance - temporarily move files to force Plex database refresh',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''Examples:
  python plex-dance.py files.txt
  python plex-dance.py --path-mapping '/Users/user/Music:/media/Music' < files.txt
  find-split-albums.py export.csv | python plex-dance.py --path-mapping '/Users/user/Music:/media/Music'
        '''
    )
    
    parser.add_argument('input_file', nargs='?', 
                       help='File containing list of paths (one per line). If not provided, reads from stdin')
    parser.add_argument('--path-mapping', 
                       help='Path mapping in format "local_root:plex_root" to map container paths to local paths')
    parser.add_argument('--parallel', action='store_true',
                       help='Process all directories simultaneously instead of one at a time (use with caution)')
    parser.add_argument('--max-wait', type=int, default=300,
                       help='Maximum time to wait for Plex to notice changes (default: 300 seconds)')
    parser.add_argument('--no-dry-run', action='store_true',
                       help='Actually perform the operations (default: dry-run mode)')
    parser.add_argument('--plex-url', 
                       default=os.getenv('PLEX_URL', 'http://localhost:32400'),
                       help='Plex server URL for validation (default: http://localhost:32400)')
    parser.add_argument('--plex-token', 
                       default=os.getenv('PLEX_TOKEN'),
                       help='Plex authentication token for validation')
    parser.add_argument('--music-library', 
                       default='Music',
                       help='Name of music library in Plex (default: Music)')
    parser.add_argument('--skip-validation', action='store_true',
                       help='Skip Plex library path validation (use with caution)')
    
    args = parser.parse_args()
    
    # Parse path mapping
    path_mapping = parse_path_mapping(args.path_mapping) if args.path_mapping else None
    
    # Read file paths and album IDs
    file_paths = []
    album_ids_map = {}  # path -> list of album IDs
    
    if args.input_file:
        if not os.path.exists(args.input_file):
            print(f"Error: File '{args.input_file}' not found.")
            sys.exit(1)
        with open(args.input_file, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]
    else:
        # Read from stdin
        lines = [line.strip() for line in sys.stdin if line.strip()]
    
    if not lines:
        print("No file paths provided.")
        sys.exit(1)
    
    # Parse path and album IDs from each line
    for line in lines:
        if '\t' in line:
            # New format: path\talbum_id1,album_id2
            path, album_ids_str = line.split('\t', 1)
            album_ids = album_ids_str.split(',')
            file_paths.append(path)
            album_ids_map[path] = album_ids
        else:
            # Legacy format: just path
            file_paths.append(line)
            album_ids_map[line] = []
    
    # Keep original Plex paths for validation, store mapping info
    plex_paths = file_paths.copy()
    if path_mapping:
        print(f"Using path mapping: {path_mapping['local_root']} -> {path_mapping['plex_root']}")
        print("Path mapping examples:")
        for i, plex_path in enumerate(plex_paths[:3]):
            local_path = apply_path_mapping(plex_path, path_mapping)
            album_ids = album_ids_map.get(plex_path, [])
            album_ids_str = f" ({','.join(album_ids)})" if album_ids else ""
            print(f"  {plex_path}{album_ids_str} -> {local_path}")
    
    # Validate paths against Plex library locations (using original Plex paths)
    if not args.skip_validation:
        if not args.plex_token:
            print("Error: Plex token is required for path validation. Use --skip-validation to bypass.", file=sys.stderr)
            sys.exit(1)
        print("Validating paths against Plex library locations...", file=sys.stderr)
        library_locations = get_plex_library_locations(args.plex_url, args.plex_token, args.music_library)
        plex_paths = validate_paths_in_library(plex_paths, library_locations, None)  # No path mapping for validation
    
    print(f"Processing {len(plex_paths)} files...")
    
    if not args.no_dry_run:
        print("\n📋 DRY RUN MODE: Validating configuration and paths...")
        print("   Use --no-dry-run to actually perform operations")
        
        validation_errors = 0
        
        # Validate each path
        for plex_path in sorted(plex_paths):
            local_path = apply_path_mapping(plex_path, path_mapping) if path_mapping else plex_path
            print(f"\n   Checking: {local_path}")
            
            # Check if local path exists
            if not os.path.exists(local_path):
                print(f"   ❌ ERROR: Path does not exist on local filesystem")
                validation_errors += 1
                continue
            
            # Find library location and temp directory
            library_root = None
            if not args.skip_validation:
                for loc in library_locations:
                    if plex_path.startswith(loc):
                        library_root = loc
                        break
            
            if not library_root:
                library_root = os.path.dirname(plex_path)
            
            # Map library root to local path and get parent directory  
            local_library_root = apply_path_mapping(library_root, path_mapping) if path_mapping else library_root
            local_library_parent = os.path.dirname(local_library_root)
            temp_dir = os.path.join(local_library_parent, "tmp.plexdance")
            
            print(f"   📁 Temp dir would be: {temp_dir}")
            
            # Check same filesystem
            if not are_on_same_filesystem(local_path, temp_dir):
                print(f"   ❌ ERROR: Album and temp directory not on same filesystem")
                validation_errors += 1
            else:
                print(f"   ✅ Same filesystem check passed")
            
            # Check if temp directory already exists
            if os.path.exists(temp_dir):
                temp_contents = [f for f in os.listdir(temp_dir) if not f.startswith('.')]
                if temp_contents:
                    print(f"   ⚠️  WARNING: Temp directory exists with {len(temp_contents)} items")
                else:
                    print(f"   ⚠️  WARNING: Empty temp directory exists (will be removed)")
            else:
                print(f"   ✅ Temp directory location is available")
        
        print(f"\n📋 DRY RUN SUMMARY:")
        if validation_errors > 0:
            print(f"   ❌ {validation_errors} validation errors found - fix before running")
            sys.exit(1)
        else:
            print(f"   ✅ All {len(plex_paths)} paths validated successfully")
            print(f"   Ready to proceed with --no-dry-run")
        return
    
    print("\n⚠️  WARNING: Do not interrupt this script while running!")
    print("   Interrupting during file moves can result in data loss.")
    print("   Files will be temporarily moved and then restored.\n")
    
    # Create temporary directories for each library location
    # (using global variable for signal handling)
    
    try:
        # Phase 1: Move all files to temporary locations
        print("Phase 1: Moving files to temporary locations...")
        # temp_paths and file_paths are global for signal handling
        move_operations = []
        
        for i, plex_path in enumerate(plex_paths):
            # Apply path mapping to get local path
            local_path = apply_path_mapping(plex_path, path_mapping) if path_mapping else plex_path
            
            # Find which library location this path belongs to (using Plex path)
            library_root = None
            if not args.skip_validation:
                for loc in library_locations:
                    if plex_path.startswith(loc):
                        library_root = loc
                        break
            
            if not library_root:
                # Fallback: use the directory containing the album directory (Plex path)
                library_root = os.path.dirname(plex_path)
            
            # Map library root to local path and get parent directory  
            local_library_root = apply_path_mapping(library_root, path_mapping) if path_mapping else library_root
            local_library_parent = os.path.dirname(local_library_root)
            
            # Create temp directory for this library location
            if local_library_parent not in library_temp_dirs:
                temp_dir = os.path.join(local_library_parent, "tmp.plexdance")
                
                # Check if temp directory already exists
                if os.path.exists(temp_dir):
                    # Check if it's empty (ignoring hidden files)
                    temp_contents = [f for f in os.listdir(temp_dir) if not f.startswith('.')]
                    if not temp_contents:
                        print(f"Found empty temp directory, removing: {temp_dir}", file=sys.stderr)
                        os.rmdir(temp_dir)
                    else:
                        print(f"Error: Temp directory already exists: {temp_dir}", file=sys.stderr)
                        print("This may indicate a previous interrupted run. Please check for files to restore or remove manually.", file=sys.stderr)
                        restore_log = os.path.join(temp_dir, "restore.log")
                        if os.path.exists(restore_log):
                            print(f"To restore files manually, run: bash {restore_log}", file=sys.stderr)
                        sys.exit(1)
                
                # Check same filesystem (using mapped local path)
                if not are_on_same_filesystem(local_path, temp_dir):
                    print(f"Error: Album directory and temp directory not on same filesystem: {local_path}", file=sys.stderr)
                    print(f"  Album path: {local_path}", file=sys.stderr)
                    print(f"  Temp dir: {temp_dir}", file=sys.stderr)
                    sys.exit(1)
                
                os.makedirs(temp_dir, exist_ok=True)
                
                # Create lock file
                lock_file = os.path.join(temp_dir, "lock")
                with open(lock_file, 'w') as f:
                    f.write(f"PID: {os.getpid()}\n")
                    f.write(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                
                library_temp_dirs[local_library_parent] = temp_dir
            
            temp_dir = library_temp_dirs[local_library_parent]
            # Create human-readable temp name: {number}_{artist}_{album}
            album_name = os.path.basename(local_path)
            artist_name = os.path.basename(os.path.dirname(local_path))
            safe_name = safe_temp_name(i, artist_name, album_name)
            temp_path = os.path.join(temp_dir, safe_name)
            temp_paths.append(temp_path)
            move_operations.append((local_path, temp_path, plex_path))
        
        # Write restore log before moving files
        for library_root, temp_dir in library_temp_dirs.items():
            restore_log = os.path.join(temp_dir, "restore.log")
            with open(restore_log, 'w') as f:
                f.write("#!/bin/bash\n")
                f.write("# Restore script for plex-dance operation\n")
                f.write(f"# Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                for local_path, temp_path, _ in move_operations:
                    if temp_path.startswith(temp_dir):
                        f.write(f"mv {shlex.quote(temp_path)} {shlex.quote(local_path)}\n")
        
        # Execute moves sequentially with progress indication
        results = []
        print("Moving albums:", file=sys.stderr)
        for i, (local_path, temp_path, plex_path) in enumerate(move_operations):
            album_name = os.path.basename(local_path)
            temp_dir = os.path.dirname(temp_path)
            print(f"  [{i+1}/{len(move_operations)}] {album_name} -> {temp_dir}...", file=sys.stderr, end=" ")
            result = move_file(local_path, temp_path, plex_path)
            print("✓" if result else "✗", file=sys.stderr)
            results.append(result)
        
        # Update global variables for signal handling
        file_paths = [op[0] for op in move_operations]  # local paths
        
        failed_moves = sum(1 for result in results if not result)
        successful_moves = len(results) - failed_moves
        
        if failed_moves > 0:
            print(f"Warning: {failed_moves} files failed to move")
        
        # If no files were successfully moved, exit early
        if successful_moves == 0:
            print("No files were successfully moved. Exiting without waiting.")
            return
        
        print(f"Successfully moved {successful_moves} files.")
        
        # Phase 2: Wait for Plex to notice the changes
        if not args.skip_validation:
            print("Phase 2: Waiting for Plex to notice the changes...")
            poll_interval = 5  # Check every 5 seconds
            max_wait_time = args.max_wait
            elapsed_time = 0
            
            # Initial check
            moved_plex_paths = [move_operations[i][2] for i, result in enumerate(results) if result]
            
            while elapsed_time < max_wait_time:
                print(f"⏳ Checking Plex library ({elapsed_time}s elapsed)...", file=sys.stderr, end=" ", flush=True)
                
                # Create list of (plex_path, album_ids) tuples for checking
                moved_albums_with_ids = []
                for i, result in enumerate(results):
                    if result:  # Only check successfully moved albums
                        plex_path = move_operations[i][2]  # Original Plex path
                        album_ids = album_ids_map.get(plex_path, [])
                        moved_albums_with_ids.append((plex_path, album_ids))
                
                all_removed, still_visible_count = check_albums_removed_from_plex(
                    args.plex_url, args.plex_token, args.music_library, 
                    moved_albums_with_ids, path_mapping
                )
                
                if all_removed:
                    print(f"✅ All albums temporarily moved!", file=sys.stderr)
                    print(f"✅ Plex has noticed all changes after {elapsed_time} seconds!", file=sys.stderr)
                    break
                
                print(f"{still_visible_count}/{len(moved_plex_paths)} albums still visible", file=sys.stderr)
                time.sleep(poll_interval)
                elapsed_time += poll_interval
            
            if elapsed_time >= max_wait_time and not all_removed:
                print(f"⏰ Timeout reached ({max_wait_time}s), proceeding with restore...", file=sys.stderr)
        else:
            print("Phase 2: Skipping Plex polling (validation disabled), proceeding immediately to restore...")
            print("Note: Files will be restored immediately without waiting for Plex to notice changes")
        
        # Phase 3: Restore all files
        print("Phase 3: Restoring files to original locations...")
        restore_operations = []
        
        for i, orig_path in enumerate(file_paths):
            temp_path = temp_paths[i]
            if os.path.exists(temp_path):  # Only restore if temp file exists
                restore_operations.append((temp_path, orig_path))
        
        # Execute restores sequentially with progress indication
        results = []
        print("Restoring albums:", file=sys.stderr)
        for i, (temp_path, orig_path) in enumerate(restore_operations):
            album_name = os.path.basename(orig_path)
            temp_dir = os.path.dirname(temp_path)
            print(f"  [{i+1}/{len(restore_operations)}] {album_name} <- {temp_dir}...", file=sys.stderr, end=" ")
            result = restore_file(temp_path, orig_path)
            print("✓" if result else "✗", file=sys.stderr)
            results.append(result)
        
        failed_restores = sum(1 for result in results if not result)
        if failed_restores > 0:
            print(f"Warning: {failed_restores} files failed to restore")
        
        print("Plex dance completed!")
        
        # Clear globals to prevent cleanup on normal exit
        library_temp_dirs = {}
        temp_paths = []
        file_paths = []
        
    except Exception as e:
        print(f"Error during operation: {e}", file=sys.stderr)
        # cleanup_and_restore will be called by atexit or signal handler
        raise

if __name__ == "__main__":
    main()
