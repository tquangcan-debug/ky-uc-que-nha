"""In ra duong dan file tap co meta.publish trung ngay hom nay (gio Viet Nam), hoac rong neu khong co."""
import json, glob, sys, datetime
today = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=7)).date().isoformat()
want = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else None
for f in sorted(glob.glob("tap/*.json")):
    if want and want in f:
        print(f); break
    if not want and json.load(open(f, encoding="utf-8")).get("meta", {}).get("publish", "").startswith(today):
        print(f); break
