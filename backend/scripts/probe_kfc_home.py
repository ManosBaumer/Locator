import httpx, re
r = httpx.get('https://www.kfc.com.cn/', headers={'User-Agent':'Mozilla/5.0'}, timeout=20)
text = r.text
print('status', r.status_code, 'len', len(text))
for m in sorted(set(re.findall(r'https?://[^\"\'\\s<>]+', text))):
    if any(k in m.lower() for k in ('store', 'shop', 'api', 'kfc', 'ashx', 'portal')):
        print('url', m)
for m in sorted(set(re.findall(r'/(?:api|store|shop)[^\"\'\\s<>]*', text, re.I))):
    print('path', m[:120])
for src in re.findall(r'src="([^"]+)"', text):
    print('src', src[:160])
