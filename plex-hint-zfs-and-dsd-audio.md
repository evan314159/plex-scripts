# Plex Hint: ZFS and DSD Audio
DSD audio is very compressible, but the standard DSD audio format that you will likely use with Plex (DSF) does not support compression.

ZFS has highly-configurable compression settings. With some trial and error I found zstd-6 very effective for compressing my DSD library, achieving ~1.57x compression across all my DSD -- a huge win!  Higher levels did not improve compression and use more CPU.  Surprisingly, the default ZFS compression algorithm, lz4, provided no visible compression on DSD in my testing.

zstd on zfs does not support "early abort" to avoid spending effort compressing material that cannot be compressed further, so zstd should only be enabled on datasets that can be meaningfully compressed.  So, DSD and other media should be stored on separate datasets to use compression optimally.

To create a new dataset "DSD" with zstd-6 compression:
```
zfs create -o compression=zstd-6 pool/parent/DSD
```

## Extra Hint: Fast Plex Dancing
Create a library folder inside the dataset to store DSD albums, such as pool/parent/DSD/library, and add this library folder to Plex -- not the dataset root.

Plex can become confused about albums, for example seeing 1 album split in 2. The fix for this is the infamous [Plex Dance](https://www.plexopedia.com/plex-media-server/general/plex-dance/).  To Plex Dance you need to move the broken album outside of the library folder that Plex is monitoring. If Plex is monitoring the root of the dataset then the album will need to be moved outside the dataset -- a slow data copy operation.  By adding the library folder, albums can be moved from library to the root of the dataset and back again with a quick metadata change only -- much better!

The resulting music library might look something like this:
```
pool/parent/music/PCM
                     /library
                             /Artist
                                    /Album
                                          /Tracks
pool/parent/music/DSD
                     /library
                             /Artist
                                    /Album
                                          /Tracks
```
with Plex watching the two library folders.

## Reminder
Check that the new dataset is included in scheduled snapshot and backup policies.
