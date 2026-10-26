#!/usr/bin/env python3
"""index.html에서 쓰는 이미지의 웹용 사본을 Projects/_web/ 아래에 만든다.

- 원본 파일은 건드리지 않는다 (라이트박스에서는 원본을 그대로 띄움)
- JPG: 긴 변이 MAX_SIDE보다 크면 줄이고 품질 90으로 저장
- 투명한 부분이 없는 PNG: 같은 크기의 JPG(품질 92)로 변환
- 화면 크기에 맞게 브라우저가 고를 수 있도록 폭 SMALL_WIDTHS 버전도 함께 생성 (srcset)
- 영상은 원본 그대로 사용 (화면에 보일 때만 불러옴)
- 모든 이미지·영상의 가로세로 크기도 기록 → 로딩 전에 자리를 미리 잡아 둠
- 결과는 Projects/_web/manifest.js 에 기록 (index.html이 읽어감)

새 이미지를 추가한 뒤에는 프로젝트 폴더에서 `python3 tools/optimize_media.py` 를 다시 실행.
"""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = 'Projects/_web'
MAX_SIDE = 3200              # 5K 레티나 화면에서 우측 패널을 꽉 채워도 충분한 크기
SMALL_WIDTHS = (1200, 2000)  # 휴대폰·일반 노트북용
JPG_QUALITY = 90
PNG_TO_JPG_QUALITY = 92
MIN_SAVING = 0.8             # 원본 대비 80% 이하로 줄어들 때만 사본 사용


def image_props(path):
    out = subprocess.run(['sips', '-g', 'pixelWidth', '-g', 'pixelHeight', '-g', 'hasAlpha', path],
                         capture_output=True, text=True).stdout
    props = dict(re.findall(r'(\w+): (\S+)', out))
    return int(props['pixelWidth']), int(props['pixelHeight']), props.get('hasAlpha') == 'yes'


def alpha_is_opaque(path):
    """투명 채널이 있어도 실제로 전부 불투명하면 True (JPG로 바꿔도 똑같이 보임)"""
    out = subprocess.run(['ffmpeg', '-v', 'info', '-i', path, '-vf', 'alphaextract,signalstats,metadata=print',
                          '-f', 'null', '-'], capture_output=True, text=True).stderr
    found = re.search(r'signalstats\.YMIN=(\d+)', out)
    return bool(found) and int(found.group(1)) == 255


def video_size(path):
    out = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                          '-show_entries', 'stream=width,height:stream_side_data=rotation',
                          '-of', 'json', path], capture_output=True, text=True).stdout
    stream = json.loads(out)['streams'][0]
    width, height = stream['width'], stream['height']
    rotation = next((d.get('rotation', 0) for d in stream.get('side_data_list', [])), 0)
    return (height, width) if abs(int(rotation)) % 180 == 90 else (width, height)


def is_stale(dest, src):
    return not os.path.exists(dest) or os.path.getmtime(dest) < os.path.getmtime(src)


def sips_jpeg(src, dest, quality, resize_args):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    subprocess.run(['sips', '-s', 'format', 'jpeg', '-s', 'formatOptions', str(quality)] + resize_args
                   + [src, '--out', dest], check=True, capture_output=True)


def optimize_image(src, width, height, has_alpha):
    """[[사본 경로, 폭], ...] 작은 것부터. 사본이 필요 없으면 빈 목록."""
    is_png = src.lower().endswith('.png')
    if is_png and has_alpha and not alpha_is_opaque(src):
        return []  # 투명 배경은 JPG로 바꾸면 깨지므로 원본 유지
    if not is_png and max(width, height) <= MAX_SIDE:
        return []

    base = os.path.join(WEB_DIR, os.path.relpath(os.path.splitext(src)[0], 'Projects'))
    quality = PNG_TO_JPG_QUALITY if is_png else JPG_QUALITY

    large = base + '.jpg'
    if is_stale(large, src):
        sips_jpeg(src, large, quality, ['-Z', str(MAX_SIDE)] if max(width, height) > MAX_SIDE else [])
    if os.path.getsize(large) > os.path.getsize(src) * MIN_SAVING:
        os.remove(large)
        return []
    large_width = image_props(large)[0]

    variants = []
    for small_width in SMALL_WIDTHS:
        if small_width >= large_width * 0.85:
            continue
        dest = f'{base}_{small_width}.jpg'
        if is_stale(dest, src):
            sips_jpeg(large, dest, quality, ['--resampleWidth', str(small_width)])
        variants.append([dest, small_width])
    variants.append([large, large_width])
    return variants


def main():
    os.chdir(ROOT)
    with open('index.html', encoding='utf-8') as f:
        html = f.read()
    refs = sorted(set(re.findall(r"Projects/(?!_web/)[^'\"]+?\.(?:jpe?g|png|mp4|mov|webm)", html, re.I)))

    web, sizes = {}, {}
    for src in refs:
        if not os.path.exists(src):
            print('없음:', src, file=sys.stderr)
            continue
        if src.lower().endswith(('.mp4', '.mov', '.webm')):
            sizes[src] = list(video_size(src))
            continue
        width, height, has_alpha = image_props(src)
        sizes[src] = [width, height]
        variants = optimize_image(src, width, height, has_alpha)
        if variants:
            web[src] = variants
            total = sum(os.path.getsize(path) for path, _ in variants)
            print(f'{os.path.getsize(src) // 1024:>7}KB -> {total // 1024:>6}KB ({len(variants)}종)  {src}')

    with open(os.path.join(WEB_DIR, 'manifest.js'), 'w', encoding='utf-8') as f:
        f.write('// tools/optimize_media.py 로 자동 생성 — 직접 수정하지 말 것\n')
        f.write('// WEB_MEDIA: 원본 경로 -> [[사본 경로, 폭], ...] (작은 것부터)\n')
        f.write('window.WEB_MEDIA = ' + json.dumps(web, ensure_ascii=False) + ';\n')
        f.write('// MEDIA_SIZE: 원본 경로 -> [폭, 높이] (로딩 전에 자리를 잡는 용도)\n')
        f.write('window.MEDIA_SIZE = ' + json.dumps(sizes, ensure_ascii=False) + ';\n')
    print(f'사본 {len(web)}개, 크기 정보 {len(sizes)}개')


if __name__ == '__main__':
    main()
