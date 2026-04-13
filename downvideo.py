import argparse
import yt_dlp

def download_youtube_video(url, output_dir="downloads"):
    # Prefer best quality (video+audio merged); needs ffmpeg installed
    ydl_opts = {
        'outtmpl': f'{output_dir}/%(title)s.%(ext)s',
        'format': 'bestvideo+bestaudio/best',
        'merge_output_format': 'mp4',
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except yt_dlp.utils.DownloadError as e:
        if "ffmpeg" in str(e).lower():
            # Fallback: single format, no merge (no ffmpeg needed). Lower quality.
            print("ffmpeg not found. Downloading single format (no merge)...")
            ydl_opts['format'] = 'best[ext=mp4]/best'
            del ydl_opts['merge_output_format']
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        else:
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Download a YouTube video using yt-dlp. For best quality install ffmpeg.",
        epilog="Example: python downvideo.py 'https://www.youtube.com/watch?v=...' -o downloads",
    )
    parser.add_argument("url", nargs="?", default=None, help="YouTube URL (optional; will prompt if omitted)")
    parser.add_argument("-o", "--output-dir", default="downloads", help="Output directory (default: downloads)")
    args = parser.parse_args()
    video_url = args.url
    if not video_url:
        video_url = input("Enter YouTube URL: ").strip()
    if not video_url:
        print("Error: No URL provided.")
        exit(1)
    download_youtube_video(video_url, output_dir=args.output_dir)