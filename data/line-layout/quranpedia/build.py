import json, sqlite3, csv, collections

# ---------- 1. load words per page from quran.com (QCF v1 line numbers) ----------
pages = {}
for p in range(1, 605):
    d = json.load(open(f'raw/{p}.json'))
    ws = []
    for v in d['verses']:
        for w in v['words']:
            s, a, n = map(int, w['location'].split(':'))
            ws.append(dict(page=p, line=w['line_number'], surah=s, ayah=a, pos=n,
                           typ=w['char_type_name'], text=w['text_uthmani']))
    ws.sort(key=lambda x: (x['surah'], x['ayah'], x['pos']))
    pages[p] = ws

# ---------- 2. word ordinal inside each surah (join key independent of ayah numbering) ----------
allw = [w for p in range(1, 605) for w in pages[p]]
cnt = collections.Counter()
ayah_words = collections.Counter()
for w in allw:
    if w['typ'] == 'word':
        ayah_words[(w['surah'], w['ayah'])] += 1
offset = {}
run = collections.Counter()
for (s, a) in sorted(ayah_words):
    offset[(s, a)] = run[s]
    run[s] += ayah_words[(s, a)]
for w in allw:
    w['surah_word'] = offset[(w['surah'], w['ayah'])] + w['pos'] if w['typ'] == 'word' else None

# ---------- 3. line_type / is_centered / surah_name lines from the QUL KFGQPC layout db ----------
lay = {}
con = sqlite3.connect('/tmp/qullayouts/qpc-v1-15-lines.db')
for pg, ln, lt, ic, fw, lw, sn in con.execute('select * from pages'):
    lay[(pg, ln)] = dict(line_type=lt, is_centered=ic, surah_number=sn,
                         fw=int(fw) if str(fw).strip() else None,
                         lw=int(lw) if str(lw).strip() else None)

rows = []
mismatch = []
for p in range(1, 605):
    byline = collections.defaultdict(list)
    for w in pages[p]:
        byline[w['line']].append(w)
    for ln in range(1, 16):
        L = lay.get((p, ln), {})
        ws = byline.get(ln, [])
        r = dict(page=p, line=ln,
                 line_type=L.get('line_type') or ('ayah' if ws else ''),
                 is_centered=L.get('is_centered') or 0,
                 surah_number=L.get('surah_number') or '',
                 start_surah='', start_ayah='', start_word='', start_surah_word='',
                 end_surah='', end_ayah='', end_word='', end_surah_word='',
                 words_count=len(ws), text=' '.join(w['text'] for w in ws))
        if ws:
            f, l = ws[0], ws[-1]
            r.update(start_surah=f['surah'], start_ayah=f['ayah'], start_word=f['pos'],
                     start_surah_word=f['surah_word'] or '',
                     end_surah=l['surah'], end_ayah=l['ayah'], end_word=l['pos'],
                     end_surah_word=l['surah_word'] or '')
            if L.get('fw') is not None and (L['lw'] - L['fw'] + 1) != len(ws):
                mismatch.append((p, ln, L['lw'] - L['fw'] + 1, len(ws)))
        rows.append(r)

print('lines:', len(rows), 'ayah-lines with word-count mismatch vs QUL v1:', len(mismatch), mismatch[:10])
print('lines with no words & no type:', sum(1 for r in rows if not r['line_type']))
print('line_type counts:', collections.Counter(r['line_type'] for r in rows))

# ---------- 4. outputs ----------
cols = list(rows[0].keys())
with open('mushaf_line_layout.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, cols); w.writeheader(); w.writerows(rows)
json.dump(rows, open('mushaf_line_layout.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

db = sqlite3.connect('mushaf_line_layout.db')
db.execute('drop table if exists line_layout')
db.execute('''create table line_layout(
 page integer, line integer, line_type text, is_centered integer, surah_number text,
 start_surah integer, start_ayah integer, start_word integer, start_surah_word integer,
 end_surah integer, end_ayah integer, end_word integer, end_surah_word integer,
 words_count integer, text text, primary key(page,line))''')
db.executemany('insert into line_layout values(%s)' % ','.join('?' * len(cols)),
               [tuple(r[c] if r[c] != '' else None for c in cols) for r in rows])
db.commit()
print('ok')
