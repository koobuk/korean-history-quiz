#!/usr/bin/env python3
"""questions/ 폴더의 회차별 JSON(eXX.json)을 합쳐 data.js를 만든다.
usage: python3 build_data.py
"""
import glob, json, os

here = os.path.dirname(os.path.abspath(__file__))
items = []
for f in sorted(glob.glob(os.path.join(here, 'questions', '*.json'))):
    items += json.load(open(f, encoding='utf-8'))
bad = [q['id'] for q in items if q.get('answer') is None]
if bad:
    print('정답 누락:', bad)
with open(os.path.join(here, 'data.js'), 'w', encoding='utf-8') as fp:
    fp.write('window.QUESTIONS = ' + json.dumps(items, ensure_ascii=False) + ';\n')
print(f'{len(items)}문항 -> data.js')
