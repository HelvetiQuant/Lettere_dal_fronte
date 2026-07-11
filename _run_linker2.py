import sys
import threading
import time

sys.stdout.reconfigure(line_buffering=True)
from linker import build_links, get_progress

result = [None]

def run():
    result[0] = build_links(resume=True)

t = threading.Thread(target=run)
t.start()

while t.is_alive():
    p = get_progress()
    cur = p.get("current", "")
    proc = p.get("processed", 0)
    tot = p.get("total", 0)
    pct = proc / tot * 100 if tot else 0
    print(f"  {cur:35s} {proc:,}/{tot:,} ({pct:.1f}%)", flush=True)
    time.sleep(10)

t.join()
r = result[0]
if r:
    print(f"DONE: entita={r['entita']:,}  collegamenti={r['collegamenti']:,}")
else:
    print("ERROR: result None")
