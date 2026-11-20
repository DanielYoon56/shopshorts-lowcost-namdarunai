# -*- coding: utf-8 -*-
"""
thumbnail_maker.py
쇼핑 쇼츠용 고화질 9:16 맞춤 썸네일 자동 합성 생성 모듈
- 1번 컷(Cut 1) 또는 실물 사진 배경을 1080x1920으로 스마트 크롭
- publish_kit.md의 썸네일 후킹 카피를 볼드한 유튜브 쇼츠 타이포그래피로 자동 합성
- '섬네일.png' 및 'assets/custom_thumbnail.png'로 동시 저장
"""

import os
import re
import glob
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

FONT_PATH = "C:/Windows/Fonts/malgunbd.ttf"
if not os.path.exists(FONT_PATH):
    FONT_PATH = "C:/Windows/Fonts/malgun.ttf"


def _trim_letterbox_margins(image: Image.Image) -> Image.Image:
    """이미지 상하/좌우에 존재하는 불필요한 단색 여백(흰색/검은색 패딩 박스)을 감지하여 완전 제거"""
    try:
        import numpy as np
        rgb_im = image.convert("RGB")
        arr = np.array(rgb_im)
        h, w, _ = arr.shape

        # 상하 단색 여백 감지 (행별 평균 및 표준편차)
        row_means = np.mean(arr, axis=(1, 2))
        row_stds = np.std(arr, axis=(1, 2))
        is_row_margin = ((row_means > 238) | (row_means < 18)) & (row_stds < 14)

        top = 0
        while top < h and is_row_margin[top]:
            top += 1

        bottom = h - 1
        while bottom > top and is_row_margin[bottom]:
            bottom -= 1

        # 좌우 단색 여백 감지 (열별 평균 및 표준편차)
        col_means = np.mean(arr, axis=(0, 2))
        col_stds = np.std(arr, axis=(0, 2))
        is_col_margin = ((col_means > 238) | (col_means < 18)) & (col_stds < 14)

        left = 0
        while left < w and is_col_margin[left]:
            left += 1

        right = w - 1
        while right > left and is_col_margin[right]:
            right -= 1

        # 유의미한 여백이 감지된 경우에만 안전하게 크롭
        if top > 10 or bottom < h - 10 or left > 10 or right < w - 10:
            crop_box = (
                max(0, left),
                max(0, top),
                min(w, right + 1),
                min(h, bottom + 1)
            )
            trimmed = image.crop(crop_box)
            print(f"[*] 불필요한 여백 박스 제거 완료: {image.size} -> {trimmed.size}")
            return trimmed
    except Exception as e:
        print(f"[!] 여백 감지 생략: {e}")

    return image


def _crop_and_resize_9_16(image: Image.Image, target_w=1080, target_h=1920) -> Image.Image:
    """상하 여백 박스 제거 후 9:16 (1080x1920) 꽉 찬 풀이미지(Full Image)로 중앙 크롭 및 리사이징"""
    # 1. 흰색/검정색 레터박스 여백이 있으면 먼저 완전 제거
    image = _trim_letterbox_margins(image)

    w, h = image.size
    target_ratio = target_w / target_h
    current_ratio = w / h

    if current_ratio > target_ratio:
        # 가로가 더 넓음 -> 좌우 중앙 크롭
        new_w = int(h * target_ratio)
        offset = (w - new_w) // 2
        image = image.crop((offset, 0, offset + new_w, h))
    else:
        # 세로가 더 길거나 가로가 좁음 -> 상하 중앙 크롭
        new_h = int(w / target_ratio)
        offset = (h - new_h) // 2
        image = image.crop((0, offset, w, offset + new_h))

    # 1080x1920 캔버스에 여백 전혀 없이 100% 꽉 채운 풀이미지로 리사이즈
    return image.resize((target_w, target_h), Image.Resampling.LANCZOS)


def clean_thumbnail_line(line: str) -> str:
    """
    썸네일에 불필요한 메타 라벨 및 마크다운 기호 완전 제거:
    예: '- **메인 카피:** 핫팩 버리고 갈아탄 이유' -> '핫팩 버리고 갈아탄 이유'
    예: '- **서브 카피:** 켜자마자 양면 발열 (10,000mAh)' -> '켜자마자 양면 발열 (10,000mAh)'
    예: '1. 헤드라인: 3초만에 시원해지는 비밀' -> '3초만에 시원해지는 비밀'
    """
    if not line:
        return ""
    text = line.strip()

    # 1. 마크다운 리스트 불릿 및 번호 제거 (-, *, •, 1., 2) 등)
    text = re.sub(r'^[\s\-\*•\d\.\)\(\]]+', '', text).strip()

    # 2. 볼드 마크다운 분리 (**메인 카피:** -> 메인 카피:)
    text = re.sub(r'\*\*', '', text)
    text = re.sub(r'__', '', text)

    # 3. 불필요한 레이블 접두사 제거 (메인카피, 서브카피, 헤드라인, 옵션 등)
    prefix_pattern = r'^(?:메인\s*카피|서브\s*카피|메인|서브|헤드라인|타이틀|후킹\s*카피|썸네일\s*카피|추천\s*카피|옵션\s*[A-Za-z0-9]+)\s*[:\-–\=]\s*'
    text = re.sub(prefix_pattern, '', text, flags=re.IGNORECASE).strip()

    # 괄호형 라벨 제거: [메인], (메인카피) 등
    text = re.sub(r'^\[(?:메인|서브|카피|헤드라인)[^\]]*\]\s*', '', text)
    text = re.sub(r'^\((?:메인|서브|카피|헤드라인)[^\)]*\)\s*', '', text)

    # 4. 앞뒤 잔여 특수문자 및 따옴표 제거
    text = text.strip(' "\'#`*:-\t')
    return text


def extract_thumbnail_copy(project_folder: str) -> str:
    """publish_kit.md 또는 script.md에서 썸네일 카피 텍스트 추출 (메타 라벨 자동 정제)"""
    pub_path = os.path.join(project_folder, "publish_kit.md")
    if os.path.exists(pub_path):
        try:
            with open(pub_path, "r", encoding="utf-8") as f:
                content = f.read()
            m = re.search(r'#{1,4}\s*.*?(?:썸네일|카피|thumbnail).*?\n(.*?)(?=#{1,4}|\Z)', content, re.DOTALL | re.IGNORECASE)
            if m:
                raw_lines = [clean_thumbnail_line(l) for l in m.group(1).splitlines()]
                lines = [l for l in raw_lines if l]
                if lines:
                    return "\n".join(lines[:2])
            # 제목 옵션에서 첫 번째 추출
            m_t = re.search(r'#{1,4}\s*.*?(?:제목|title).*?\n(.*?)(?=#{1,4}|\Z)', content, re.DOTALL | re.IGNORECASE)
            if m_t:
                raw_lines = [clean_thumbnail_line(l) for l in m_t.group(1).splitlines()]
                lines = [l for l in raw_lines if l]
                if lines:
                    return lines[0]
        except Exception as e:
            print(f"[!] 썸네일 카피 추출 실패: {e}")

    # 대본 첫 줄 폴백
    s_path = os.path.join(project_folder, "script.md")
    if os.path.exists(s_path):
        try:
            with open(s_path, "r", encoding="utf-8") as f:
                s_lines = [clean_thumbnail_line(l) for l in f.read().splitlines() if l.strip()]
                if s_lines:
                    return s_lines[0]
        except Exception:
            pass

    folder_name = os.path.basename(project_folder)
    clean_name = re.sub(r'^\d+[\-_]?', '', folder_name).strip() or folder_name
    return f"{clean_name} 솔직 후기!\n이거 진짜 물건이네"


def find_best_background_image(project_folder: str) -> str | None:
    """썸네일 배경으로 사용할 최적의 이미지 탐색"""
    # 01_Cut1_Hook.jpg 등 패턴 탐색
    cut1_patterns = glob.glob(os.path.join(project_folder, "assets", "*01_Cut1*.jpg")) + glob.glob(os.path.join(project_folder, "assets", "*01_Cut1*.png"))
    if cut1_patterns and os.path.exists(cut1_patterns[0]):
        return cut1_patterns[0]

    cands = [
        os.path.join(project_folder, "assets", "cut1_9_16.jpg"),
        os.path.join(project_folder, "assets", "ref_cut1.png"),
        os.path.join(project_folder, "assets", "ref_cut1.jpg"),
        os.path.join(project_folder, "cut1_9_16.jpg"),
        os.path.join(project_folder, "assets", "cut2_9_16.jpg"),
    ]
    for c in cands:
        if os.path.exists(c):
            return c

    # assets 폴더 내 첫 번째 jpg/png
    assets_dir = os.path.join(project_folder, "assets")
    if os.path.exists(assets_dir):
        for f in os.listdir(assets_dir):
            if f.lower().endswith((".jpg", ".png", ".jpeg", ".webp")) and "custom_thumb" not in f and "섬네일" not in f:
                return os.path.join(assets_dir, f)

    return None


def generate_shorts_thumbnail(
    project_folder: str,
    copy_text: str = None,
    bg_image_path: str = None,
    badge_label: str = None
) -> str:
    """
    고화질 9:16 유튜브 쇼츠 썸네일 자동 합성 생성
    - 박스 및 추천템 배지 완전 제거
    - 1줄: 메인 카피 분홍색(#FF2A85) 굵은 글씨 한 줄
    - 2줄: 서브 카피 초록색(#00E676) 같은 크기 폰트 한 줄
    """
    if not copy_text:
        copy_text = extract_thumbnail_copy(project_folder)

    # 1. 배경 이미지 로드
    if not bg_image_path or not os.path.exists(bg_image_path):
        bg_image_path = find_best_background_image(project_folder)

    if bg_image_path and os.path.exists(bg_image_path):
        try:
            base_img = Image.open(bg_image_path).convert("RGBA")
        except Exception:
            base_img = Image.new("RGBA", (1080, 1920), color=(20, 20, 30, 255))
    else:
        base_img = Image.new("RGBA", (1080, 1920), color=(20, 20, 30, 255))

    # 9:16 비율 크롭 및 리사이징 (1080x1920)
    bg = _crop_and_resize_9_16(base_img, 1080, 1920)

    # 2. 상단 텍스트 가독성을 위한 은은한 비네팅 그라데이션 레이어
    overlay = Image.new("RGBA", bg.size, (0, 0, 0, 0))
    draw_overlay = ImageDraw.Draw(overlay)
    for y in range(650):
        alpha = int(110 * (1.0 - (y / 650) ** 1.3))
        if alpha > 0:
            draw_overlay.line([(0, y), (1080, y)], fill=(0, 0, 0, alpha))
    bg = Image.alpha_composite(bg, overlay)

    # 3. 텍스트 추출: 메인 카피 1줄, 서브 카피 1줄
    raw_lines = [clean_thumbnail_line(l) for l in copy_text.splitlines()]
    raw_lines = [l for l in raw_lines if l]

    main_copy = raw_lines[0] if len(raw_lines) > 0 else ""
    sub_copy = raw_lines[1] if len(raw_lines) > 1 else ""
    display_lines = [l for l in [main_copy, sub_copy] if l]

    # 4. 동일한 크기의 폰트 자동 스케일링 (시인성 극대화: 94pt부터 시작, 1000px 폭 한 줄 맞춤)
    draw = ImageDraw.Draw(bg)
    font_size = 94
    try:
        for f_sz in range(94, 56, -2):
            font_test = ImageFont.truetype(FONT_PATH, f_sz)
            max_w = max(
                (draw.textbbox((0, 0), l, font=font_test, stroke_width=9)[2] - 
                 draw.textbbox((0, 0), l, font=font_test, stroke_width=9)[0])
                for l in display_lines
            ) if display_lines else 0
            if max_w <= 1000:
                font_size = f_sz
                break
            font_size = f_sz
        font_main = ImageFont.truetype(FONT_PATH, font_size)
    except Exception:
        font_main = ImageFont.load_default()

    # 5. 텍스트 렌더링 (박스 없음, 배지 없음)
    # 1줄: 분홍색(#FF1A75), 2줄: 초록색(#00E676), 굵은 폰트 + 9px 외곽선
    start_y = 300
    line_bboxes = [draw.textbbox((0, 0), line, font=font_main, stroke_width=9) for line in display_lines]
    line_h = max((bb[3] - bb[1]) for bb in line_bboxes) if line_bboxes else 90

    cur_y = start_y
    colors = ["#FF1A75", "#00E676"]  # 1줄 핫핑크, 2줄 네온그린

    for idx, line in enumerate(display_lines):
        line_bb = draw.textbbox((0, 0), line, font=font_main, stroke_width=9)
        w = line_bb[2] - line_bb[0]
        x = (1080 - w) // 2
        text_color = colors[idx] if idx < len(colors) else "#FFFFFF"

        # 입체 그림자 효과 (블랙 섀도우)
        draw.text(
            (x + 4, cur_y + 5),
            line,
            font=font_main,
            fill="#000000",
            stroke_width=7,
            stroke_fill="#000000"
        )
        # 메인 텍스트 (분홍색/초록색 + 굵은 검은색 외곽선 9px)
        draw.text(
            (x, cur_y),
            line,
            font=font_main,
            fill=text_color,
            stroke_width=9,
            stroke_fill="#000000"
        )
        cur_y += line_h + 32

    # 5. 최종 이미지 저장 (YouTube 2MB 규격 완벽 호환 고화질 JPEG 및 PNG 동시 저장)
    final_rgb = bg.convert("RGB")
    out_root = os.path.join(project_folder, "섬네일.jpg")
    final_rgb.save(out_root, "JPEG", quality=92, optimize=True)

    out_png = os.path.join(project_folder, "섬네일.png")
    final_rgb.save(out_png, "PNG", optimize=True)

    assets_dir = os.path.join(project_folder, "assets")
    os.makedirs(assets_dir, exist_ok=True)
    out_assets_jpg = os.path.join(assets_dir, "custom_thumbnail.jpg")
    final_rgb.save(out_assets_jpg, "JPEG", quality=92, optimize=True)
    out_assets_png = os.path.join(assets_dir, "custom_thumbnail.png")
    final_rgb.save(out_assets_png, "PNG", optimize=True)

    print(f"[+] 썸네일 자동 생성 완료: {out_root} ({os.path.getsize(out_root):,} bytes)")
    return out_root


if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "outputs/261115_신일EMF싱글매트"
    generate_shorts_thumbnail(target)
