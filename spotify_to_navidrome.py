import json
import os
import re
import subprocess
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import requests

PORT = 8888
PUBLIC_DOMAIN = "music.jobbisoft.com.mx"
REDIRECT_URI = f"https://{PUBLIC_DOMAIN}/downloader/callback"
INVIDIOUS_INSTANCE = "https://yt.jobbisoft.com.mx"
MUSIC_OUTPUT_DIR = "/app/music"

USER_SESSIONS = {}


def download_audio_with_ytdlp(target_url_or_query, output_dir=MUSIC_OUTPUT_DIR):
    """Downloads audio matching a YouTube URL or search query, normalizes loudness, and saves MP3."""
    os.makedirs(output_dir, exist_ok=True)
    out_tmpl = os.path.join(output_dir, "%(title)s.%(ext)s")

    # If it's a search query rather than a URL, prepend ytsearch1:
    if not target_url_or_query.startswith("http://") and not target_url_or_query.startswith("https://"):
        query = f"ytsearch1:{target_url_or_query}"
    else:
        query = target_url_or_query

    cmd = [
        "yt-dlp",
        "-x",
        "--audio-format", "mp3",
        "--audio-quality", "0",
        "--postprocessor-args", "ffmpeg:-af loudnorm=I=-14:LRA=11:TP=-1.5",
        "--no-playlist",
        "--quiet",
        "--no-warnings",
        "-o", out_tmpl,
        query,
    ]
    try:
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error running yt-dlp: {e}")
        return False


class DownloaderHandler(BaseHTTPRequestHandler):

    def send_html(self, html_content, status_code=200):
        self.send_response(status_code)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html_content.encode("utf-8"))

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path.rstrip("/")

        # Direct File Upload Endpoint
        if path == "/downloader/upload":
            content_type = self.headers.get("Content-Type", "")
            if "multipart/form-data" in content_type:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)

                try:
                    boundary = content_type.split("boundary=")[1].encode()
                    parts = body.split(b"--" + boundary)

                    for part in parts:
                        if b'filename="' in part:
                            header_part, file_data = part.split(b"\r\n\r\n", 1)
                            file_data = file_data.rsplit(b"\r\n", 1)[0]

                            header_text = header_part.decode("utf-8", errors="ignore")
                            match = re.search(r'filename="([^"]+)"', header_text)
                            if match:
                                filename = os.path.basename(match.group(1))
                                if filename:
                                    os.makedirs(MUSIC_OUTPUT_DIR, exist_ok=True)
                                    save_path = os.path.join(MUSIC_OUTPUT_DIR, filename)
                                    with open(save_path, "wb") as f:
                                        f.write(file_data)
                                    self.send_html(
                                        f"<h3>Successfully uploaded '{filename}' to music folder!</h3>"
                                        "<p><a href='/downloader/'>Back to Hub</a></p>"
                                    )
                                    return
                    self.send_html("<h3>Failed to parse uploaded file.</h3>", status_code=400)
                except Exception as e:
                    self.send_html(f"<h3>Upload processing error: {e}</h3>", status_code=500)
            else:
                self.send_html("<h3>Invalid upload request.</h3>", status_code=400)

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path.rstrip("/")
        params = urllib.parse.parse_qs(parsed_url.query)

        # 1. Main Dashboard UI
        if path in ["", "/downloader"]:
            search_query = params.get("q", [""])[0]
            search_results_html = ""

            if search_query:
                try:
                    api_url = f"{INVIDIOUS_INSTANCE}/api/v1/search?q={urllib.parse.quote(search_query)}&type=video"
                    req = requests.get(api_url, timeout=8)
                    if req.status_code == 200:
                        results = req.json()[:5]
                        search_results_html = "<h4>Search Results (via Invidious):</h4><ul style='list-style:none; padding:0;'>"
                        for item in results:
                            video_id = item.get("videoId")
                            title = item.get("title")
                            author = item.get("author")
                            search_results_html += f"""
                            <li style='margin-bottom: 12px; padding: 12px; border: 1px solid var(--border-color); border-radius: 6px; background: #252525; display: flex; justify-content: space-between; align-items: center;'>
                                <div><strong style='color:#fff;'>{title}</strong><br><small style='color:var(--text-muted);'>{author}</small></div>
                                <a href='/downloader/direct_download?id={video_id}&title={urllib.parse.quote(title)}' style='background:var(--accent-green); color:white; padding:8px 14px; border-radius:14px; text-decoration:none; font-weight:bold; font-size:13px;'>Download</a>
                            </li>
                            """
                        search_results_html += "</ul>"
                    else:
                        search_results_html = "<p style='color:#ff5555;'>Could not connect to Invidious instance.</p>"
                except Exception as e:
                    search_results_html = f"<p style='color:#ff5555;'>Search error: {e}</p>"

            html = f"""
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Music Server Downloader</title>
                <style>
                    :root {{
                        --bg-color: #121212;
                        --card-bg: #1e1e1e;
                        --text-color: #e0e0e0;
                        --text-muted: #a0a0a0;
                        --border-color: #2d2d2d;
                        --accent-green: #1DB954;
                        --accent-hover: #1ed760;
                    }}
                    body {{ 
                        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; 
                        max-width: 680px; 
                        margin: 30px auto; 
                        padding: 20px; 
                        line-height: 1.5; 
                        color: var(--text-color); 
                        background-color: var(--bg-color); 
                    }}
                    h2, h3, h4 {{ color: #ffffff; margin-top: 0; }}
                    .card {{ 
                        background: var(--card-bg); 
                        border: 1px solid var(--border-color); 
                        border-radius: 8px; 
                        padding: 20px; 
                        margin-bottom: 20px; 
                        box-shadow: 0 4px 10px rgba(0,0,0,0.3); 
                    }}
                    label {{ font-size: 14px; font-weight: 600; color: var(--text-muted); }}
                    input[type="text"], input[type="password"], input[type="file"] {{ 
                        width: 100%; 
                        padding: 10px; 
                        margin: 6px 0 14px 0; 
                        box-sizing: border-box; 
                        border: 1px solid var(--border-color); 
                        background: #2a2a2a;
                        color: #ffffff;
                        border-radius: 6px; 
                        font-size: 14px; 
                    }}
                    button, input[type="submit"] {{ 
                        background-color: var(--accent-green); 
                        color: white; 
                        border: none; 
                        padding: 10px 18px; 
                        cursor: pointer; 
                        border-radius: 20px; 
                        font-weight: bold; 
                        font-size: 14px; 
                    }}
                    button:hover, input[type="submit"]:hover {{ background-color: var(--accent-hover); }}
                    a {{ color: var(--accent-green); text-decoration: none; font-weight: 600; }}
                    .drop-zone {{ border: 2px dashed var(--border-color); border-radius: 6px; padding: 20px; text-align: center; color: var(--text-muted); background: #181818; }}
                </style>
            </head>
            <body>
                <h2>Music Server Downloader & Hub</h2>
                
                <!-- Section 1: Song Search -->
                <div class="card">
                    <h3>Search & Download Songs</h3>
                    <form action="/downloader/" method="GET">
                        <label>Song Title or Artist Name:</label>
                        <input type="text" name="q" value="{search_query}" placeholder="Search track or artist..." required>
                        <button type="submit">Search</button>
                    </form>
                    {search_results_html}
                </div>

                <!-- Section 2: Direct File Upload -->
                <div class="card">
                    <h3>Upload Audio Files Directly</h3>
                    <form action="/downloader/upload" method="POST" enctype="multipart/form-data">
                        <div class="drop-zone">
                            <label>Select or Drop Audio File (.mp3, .flac, .m4a):</label><br><br>
                            <input type="file" name="file" accept="audio/*" required>
                        </div>
                        <br>
                        <button type="submit">Upload to Server</button>
                    </form>
                </div>

                <!-- Section 3: Spotify Downloader -->
                <div class="card">
                    <h3>Spotify Track Downloader</h3>
                    <form action="/downloader/auth" method="GET">
                        <label>Spotify Client ID:</label>
                        <input type="text" name="client_id" required placeholder="Client ID">
                        
                        <label>Spotify Client Secret:</label>
                        <input type="password" name="client_secret" required placeholder="Client Secret">
                        
                        <label>Spotify Track Link:</label>
                        <input type="text" name="spotify_url" required placeholder="https://open.spotify.com/track/...">
                        
                        <button type="submit">Authenticate & Download</button>
                    </form>
                </div>
            </body>
            </html>
            """
            self.send_html(html)

        # 2. Invidious / YouTube Direct Download Route
        elif path == "/downloader/direct_download":
            video_id = params.get("id", [""])[0]
            title = params.get("title", ["Track"])[0]

            if not video_id:
                self.send_html("<h3>Missing video ID.</h3>", status_code=400)
                return

            youtube_url = f"https://www.youtube.com/watch?v={video_id}"
            success = download_audio_with_ytdlp(youtube_url)

            if success:
                self.send_html(
                    f"<h3>Successfully downloaded: {title}</h3>"
                    "<p><a href='/downloader/'>Back to Hub</a></p>"
                )
            else:
                self.send_html("<h3>Failed to download track from YouTube/Invidious.</h3>", status_code=500)

        # 3. Spotify OAuth Redirect Route
        elif path == "/downloader/auth":
            client_id = params.get("client_id", [""])[0]
            client_secret = params.get("client_secret", [""])[0]
            spotify_url = params.get("spotify_url", [""])[0]

            if not client_id or not client_secret:
                self.send_html("<h3>Error: Missing Client ID or Client Secret</h3>", status_code=400)
                return

            state = urllib.parse.quote(spotify_url)
            USER_SESSIONS[state] = {
                "client_id": client_id,
                "client_secret": client_secret,
                "spotify_url": spotify_url,
            }

            scope = "playlist-read-private user-library-read"
            auth_query = urllib.parse.urlencode({
                "response_type": "code",
                "client_id": client_id,
                "scope": scope,
                "redirect_uri": REDIRECT_URI,
                "state": state,
            })
            spotify_auth_url = f"https://accounts.spotify.com/authorize?{auth_query}"

            self.send_response(302)
            self.send_header("Location", spotify_auth_url)
            self.end_headers()

        # 4. Spotify Callback Route
        elif path == "/downloader/callback":
            code = params.get("code", [None])[0]
            state = params.get("state", [None])[0]

            if not code or not state or state not in USER_SESSIONS:
                self.send_html("<h3>Authentication failed or session expired.</h3>", status_code=400)
                return

            session = USER_SESSIONS.pop(state)

            token_response = requests.post(
                "https://accounts.spotify.com/api/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": REDIRECT_URI,
                    "client_id": session["client_id"],
                    "client_secret": session["client_secret"],
                },
                timeout=10,
            )

            if token_response.status_code != 200:
                self.send_html(f"<h3>Failed to obtain access token from Spotify</h3><p>{token_response.text}</p>", status_code=400)
                return

            access_token = token_response.json().get("access_token")
            spotify_url = session["spotify_url"]

            track_id = spotify_url.split("/")[-1].split("?")[0]
            headers = {"Authorization": f"Bearer {access_token}"}
            track_req = requests.get(f"https://api.spotify.com/v1/tracks/{track_id}", headers=headers, timeout=10)

            if track_req.status_code == 200:
                track_data = track_req.json()
                artist = track_data["artists"][0]["name"]
                title = track_data["name"]
                search_query = f"{artist} - {title}"

                success = download_audio_with_ytdlp(search_query)

                if success:
                    self.send_html(
                        f"<h3>Successfully downloaded: {search_query}</h3>"
                        "<p><a href='/downloader/'>Back to Hub</a></p>"
                    )
                else:
                    self.send_html(f"<h3>Failed to download audio for: {search_query}</h3>", status_code=500)
            else:
                self.send_html("<h3>Could not fetch track metadata from Spotify.</h3>", status_code=400)

        else:
            self.send_html("<h3>404 Not Found</h3>", status_code=404)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), DownloaderHandler)
    print(f"🚀 Server listening on http://0.0.0.0:{PORT}")
    server.serve_forever()
