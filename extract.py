#!/usr/bin/env python3
"""문제지 PDF(이미지본) -> 문항별 JPG + 정답표 PDF -> 정답 JSON.
usage: extract.py <문제지.pdf> <정답표.pdf> <out_dir> <exam_id>
"""
import sys, re, os, json
import pymupdf
from PIL import Image

DPI = 200
CIRC = {'①': 1, '②': 2, '③': 3, '④': 4, '⑤': 5}
# 200dpi 기준 단 영역(좌/우)과 본문 상하 한계
COLS = [(120, 1030), (1054, 1965)]
HEADER_LEFT = [(100, 260), (1020, 1180)]
TAG_X = [(940, 1035), (1840, 1955)]
NUM_X = [(145, 185), (1065, 1105)]   # 문항번호가 놓이는 x 범위
BODY_TOP, BODY_BOTTOM = 250, 2790


def parse_answers(path):
    doc = pymupdf.open(path)
    toks = []
    for p in doc:
        toks += [w[4] for w in p.get_text('words')]
    txt = ' '.join(toks)
    out = {}
    for m in re.finditer(r'(?<!\d)(\d{1,2})\s+([①②③④⑤1-5]|없음|전항)\s+(\d)(?!\d)', txt):
        n = int(m.group(1))
        if not (1 <= n <= 50) or n in out:
            continue
        v = m.group(2)
        ans = CIRC.get(v) or (int(v) if v.isdigit() else 0)   # 0 = 정답 없음(전원 정답 처리)
        out[n] = {'answer': ans, 'points': int(m.group(3))}
    return out


def find_headers(im, page_no, tag_min=80):
    """문항 번호(굵은 숫자) 위치를 픽셀로 탐지. 반환: [(단, y, None)]"""
    import numpy as np
    g = np.asarray(im.convert('L'))
    found = []
    for c, (a, b) in enumerate([(120, 230), (1040, 1150)]):
        rows = (g[:, a:b] < 110).sum(1)
        start = None
        for y in range(BODY_TOP - 20, BODY_BOTTOM + 1):
            on = rows[y] >= 3
            if on and start is None:
                start = y
            if (not on) and start is not None:
                h = y - start
                if 32 <= h <= 35 and rows[start:y].max() <= 60:
                    ta, tb = TAG_X[c]   # 같은 줄 오른쪽 끝의 배점 표시 [N점]이 있어야 문항 머리줄
                    tag = (g[start - 4:y + 4, ta:tb] < 110).sum()
                    xa = NUM_X[c][0]
                    above = g[max(start - 12, 0):start - 2, xa:xa + 110].mean()   # 번호 바로 위는 흰 여백
                    if tag_min <= tag <= 700 and above > 245:
                        found.append((c, start, None))
                start = None
    return found


def main(qpdf, apdf, outdir, exam):
    os.makedirs(outdir, exist_ok=True)
    ans = parse_answers(apdf)
    doc = pymupdf.open(qpdf)
    pages = []
    for pi, page in enumerate(doc):
        pm = page.get_pixmap(dpi=DPI)
        im = Image.frombytes('RGB', (pm.width, pm.height), pm.samples)
        pages.append(im)
    items = []
    for tag_min in (80, 50, 30):
        items = []; seq = 0
        for pi, im in enumerate(pages):
            hs = find_headers(im, pi, tag_min)
            for c in (0, 1):
                col = [h for h in hs if h[0] == c]
                for k, (cc, y, _) in enumerate(col):
                    seq += 1
                    nxt = col[k + 1][1] - 12 if k + 1 < len(col) else BODY_BOTTOM
                    items.append(dict(q=seq, page=pi, col=c, top=y - 14, bottom=nxt))
        if len(items) == 50:
            break
    print('문항 수:', len(items))

    # 공통 지문 문항 처리 (예: [35~36]) : 지문이 있는 단의 맨 위부터 자르기
    def crop(it, top=None):
        x0, x1 = COLS[it['col']]
        return pages[it['page']].crop((x0, top if top is not None else it['top'], x1, it['bottom']))

    shared = {}  # q -> passage image
    for it in items:
        # 단의 첫 문항인데 헤더 위에 큰 공백 이상의 내용이 있으면 공통 지문으로 간주
        col_items = [j for j in items if j['page'] == it['page'] and j['col'] == it['col']]
        base = 480 if it['page'] == 0 else BODY_TOP   # 1페이지는 제목 배너 아래부터 본문
        if it is col_items[0] and it['top'] - base > 150:
            it['top_override'] = BODY_TOP - 10
            # 다음 문항(다른 단/페이지)에도 지문 필요 -> 직후 문항에 붙임
            nxt = [j for j in items if j['q'] == it['q'] + 1]
            if nxt:
                shared[nxt[0]['q']] = pages[it['page']].crop(
                    (COLS[it['col']][0], BODY_TOP - 10, COLS[it['col']][1], it['top'] - 4))

    data = []
    for it in items:
        img = crop(it, it.get('top_override'))
        if it['q'] in shared:
            p = shared[it['q']]
            canvas = Image.new('RGB', (img.width, p.height + img.height), 'white')
            canvas.paste(p, (0, 0)); canvas.paste(img, (0, p.height)); img = canvas
        fn = f"{exam}_{it['q']:02d}.jpg"
        img.save(os.path.join(outdir, fn), quality=85)
        a = ans.get(it['q'], {})
        data.append({'id': f"{exam}-{it['q']:02d}", 'exam': exam, 'no': it['q'],
                     'image': fn, 'answer': a.get('answer'), 'points': a.get('points')})
    json.dump(data, open(os.path.join(outdir, f'{exam}.json'), 'w'), ensure_ascii=False, indent=1)
    miss = [d['no'] for d in data if d['answer'] is None]
    print('정답 파싱:', len(ans), '| 정답 누락 문항:', miss, '| 배점합:', sum(d['points'] or 0 for d in data), '| 정답없음:', [d['no'] for d in data if d['answer'] == 0])


if __name__ == '__main__':
    main(*sys.argv[1:5])
