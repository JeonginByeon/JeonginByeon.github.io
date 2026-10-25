#!/usr/bin/env python3
"""index.html에서 쓰는 이미지의 웹용 사본을 Projects/_web/ 아래에 만든다.

- 원본 파일은 건드리지 않는다 (라이트박스에서는 원본을 그대로 띄움)
- JPG: 긴 변이 MAX_SIDE보다 크면 줄이고 품질 90으로 저장
- 투명도 없는 PNG: 같은 크기의 JPG(품질 92)로 변환
- 영상은 원본 그대로 사용 (상세페이지에서 화면에 보일 때만 불러옴)
- 결과 매핑은 Projects/_web/manifest.js 에 기록 (index.html이 읽어감)

새 이미지를 추가한 뒤에는 프로젝트 폴더에서 `python3 tools/optimize_media.py` 를 다시 실행.
"""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = 'Projects/_web'
MAX_SIDE = 3200          # 5K 레티나 화면에서 우측 패널을 꽉 채워도 충분한 크기
JPG_QUALITY = 90
PNG_TO_JPG_QUALITY = 92
MIN_SAVING = 0.8         # 원본 대비 80% 이하로 줄어들 때만 사본 사용


def sips_props(path):
    out = subprocess.run(['sips', '-g', 'pixelWidth', '-g', 'pixelHeight', '-g', 'hasAlpha', path],
                         capture_output=True, text=True).stdout
    props = dict(re.findall(r'(\w+): (\S+)', out))
    return int(props['pixelWidth']), int(props['pixelHeight']), props.get('hasAlpha') == 'yes'


def optimize_image(src):
    width, height, has_alpha = sips_props(src)
    is_png = src.lower().endswith('.png')
    if is_png and has_alpha:
        return None  # 투명 배경은 JPG로 바꾸면 깨지므로 원본 유지
    if not is_png and max(width, height) <= MAX_SIDE:
        return None

    base, _ = os.path.splitext(src)
    dest = os.path.join(WEB_DIR, os.path.relpath(base, 'Projects') + '.jpg')
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if not os.path.exists(dest) or os.path.getmtime(dest) < os.path.getmtime(src):
        quality = PNG_TO_JPG_QUALITY if is_png else JPG_QUALITY
        cmd = ['sips', '-s', 'format', 'jpeg', '-s', 'formatOptions', str(quality)]
        if max(width, height) > MAX_SIDE:
            cmd += ['-Z', str(MAX_SIDE)]
        subprocess.run(cmd + [src, '--out', dest], check=True, capture_output=True)
    if os.path.getsize(dest) > os.path.getsize(src) * MIN_SAVING:
        os.remove(dest)
        return None
    return dest


def main():
    os.chdir(ROOT)
    with open('index.html', encoding='utf-8') as f:
        html = f.read()
    refs = sorted(set(re.findall(r"Projects/(?!_web/)[^'\"]+?\.(?:jpe?g|png)", html, re.I)))

    manifest = {}
    for src in refs:
        if not os.path.exists(src):
            print('없음:', src, file=sys.stderr)
            continue
        dest = optimize_image(src)
        if dest:
            manifest[src] = dest
            print(f'{os.path.getsize(src) // 1024:>7}KB -> {os.path.getsize(dest) // 1024:>6}KB  {src}')

    with open(os.path.join(WEB_DIR, 'manifest.js'), 'w', encoding='utf-8') as f:
        f.write('// tools/optimize_media.py 로 자동 생성 — 직접 수정하지 말 것\n')
        f.write('window.WEB_MEDIA = ' + json.dumps(manifest, ensure_ascii=False, indent=1) + ';\n')
    print(f'{len(manifest)}개 사본 생성')


if __name__ == '__main__':
    main()
