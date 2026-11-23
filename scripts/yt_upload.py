"""Tai video len YouTube va hen gio dang.

Dung: python yt_upload.py JOB_DIR [--privacy private|unlisted|public] [--publish-at ISO]
- Doc JOB_DIR/script.json (title, meta.youtube_description, meta.tags, meta.playlist, meta.publish).
- Mac dinh: private + publishAt = meta.publish (YouTube tu cong khai dung gio).
- Danh dau noi dung tong hop (AI), dat thumbnail, them vao playlist trung ten.
Bien moi truong: YT_TOKEN_JSON (noi dung token), YT_CLIENT_SECRET_JSON (khong bat buoc neu token co client_id/secret).
In dong cuoi la JSON {ok, video_id, url, publish_at}.
"""
import json, os, sys, argparse
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube"]
CREDIT = os.environ.get("MUSIC_CREDIT", "").strip()


def creds():
    info = json.loads(os.environ["YT_TOKEN_JSON"])
    if not info.get("client_id") and os.environ.get("YT_CLIENT_SECRET_JSON"):
        cs = json.loads(os.environ["YT_CLIENT_SECRET_JSON"])
        cs = cs.get("installed") or cs.get("web")
        info["client_id"], info["client_secret"] = cs["client_id"], cs["client_secret"]
    c = Credentials.from_authorized_user_info(info, SCOPES)
    if not c.valid:
        c.refresh(Request())
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("job")
    ap.add_argument("--privacy", default="private")
    ap.add_argument("--publish-at", default=None)
    ap.add_argument("--video", default=None)
    a = ap.parse_args()
    sc = json.load(open(os.path.join(a.job, "script.json"), encoding="utf-8"))
    meta = sc.get("meta", {})
    desc = meta.get("youtube_description", "")
    if CREDIT:
        desc += "\n\n" + CREDIT
    publish = a.publish_at if a.publish_at is not None else meta.get("publish")
    status = {"privacyStatus": a.privacy, "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}
    if publish and a.privacy == "private":
        status["publishAt"] = publish
    body = {"snippet": {"title": sc["title"][:100], "description": desc[:4900], "tags": meta.get("tags", []),
                        "categoryId": "22", "defaultLanguage": "vi", "defaultAudioLanguage": "vi"},
            "status": status}
    yt = build("youtube", "v3", credentials=creds(), cache_discovery=False)
    video = a.video or os.path.join(a.job, "youtube.mp4")
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(video, chunksize=8 * 1024 * 1024, resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    vid = resp["id"]
    thumb = os.path.join(a.job, "thumb.jpg")
    if os.path.exists(thumb):
        try:
            yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(thumb)).execute()
        except Exception as e:  # kenh chua xac minh so dien thoai thi khong dat thumbnail duoc
            print("thumbnail loi:", e, file=sys.stderr)
    pl_name = meta.get("playlist")
    if pl_name:
        try:
            pls = yt.playlists().list(part="snippet", mine=True, maxResults=50).execute().get("items", [])
            pid = next((p["id"] for p in pls if p["snippet"]["title"].strip().lower() == pl_name.lower()), None)
            if pid:
                yt.playlistItems().insert(part="snippet", body={"snippet": {"playlistId": pid,
                                          "resourceId": {"kind": "youtube#video", "videoId": vid}}}).execute()
        except Exception as e:
            print("playlist loi:", e, file=sys.stderr)
    print(json.dumps({"ok": True, "video_id": vid, "url": f"https://youtu.be/{vid}",
                      "studio": f"https://studio.youtube.com/video/{vid}/edit", "publish_at": publish}))


if __name__ == "__main__":
    main()
