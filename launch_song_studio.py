"""Song Studio's single-file portable Windows EXE entrypoint."""
import sys


def self_test():
    import yt_dlp
    from googleapiclient.discovery import build
    from google_auth_oauthlib.flow import InstalledAppFlow
    from smart_media_manager.youtube_downloader import ffmpeg_paths
    from song_audio_downloader.core import video_id_from_url
    from song_studio.core import ffmpeg_filter, safe_folder, StudioStore
    assert hasattr(yt_dlp, "YoutubeDL")
    assert build is not None and InstalledAppFlow is not None
    assert video_id_from_url("https://youtu.be/sQ74S7cZ3Kg") == "sQ74S7cZ3Kg"
    assert "scale=1920:1080" in ffmpeg_filter("1080p", "Fit")
    assert safe_folder("Music") == "Music"
    assert ffmpeg_paths()[0] and ffmpeg_paths()[1], "Bundled FFmpeg / FFprobe missing"


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        from song_studio.app import main
        main()
