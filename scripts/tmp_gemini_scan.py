import re
from pathlib import Path

p = Path(r"data\takeout-20260131T144819Z-3-001\Takeout\My Activity\Gemini Apps\MyActivity.html")

needles = [
    b'href="https://gemini.google.com',
    b'https://gemini.google.com/share',
    b'https://gemini.google.com/app',
]
counts = {n: 0 for n in needles}
urls: list[str] = []
rx = re.compile(br'https?://gemini\.google\.com/[^"\s<]+', re.IGNORECASE)

with p.open('rb') as f:
    for line in f:
        low = line.lower()
        for n in needles:
            counts[n] += low.count(n)
        if len(urls) < 30:
            for m in rx.finditer(line):
                u = m.group(0).decode('utf-8', 'ignore')
                if u not in urls:
                    urls.append(u)
                    if len(urls) >= 30:
                        break

print('file', p)
print('counts')
for n in needles:
    print(n.decode('utf-8', 'ignore'), counts[n])
print('urls', len(urls))
for u in urls:
    print(u)
