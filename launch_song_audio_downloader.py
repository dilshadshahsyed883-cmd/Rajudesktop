"""Song Audio Downloader standalone launch entry point."""
import sys


def self_test():
    import yt_dlp
    from smart_media_manager.youtube_downloader import ffmpeg_paths
    from song_audio_downloader.core import video_id_from_url
    assert hasattr(yt_dlp, "YoutubeDL")
    assert video_id_from_url("https://youtu.be/sQ74S7cZ3Kg") == "sQ74S7cZ3Kg"
    assert ffmpeg_paths()[0], "Bundled FFmpeg missing"


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        from song_audio_downloader.app import main
        main()
