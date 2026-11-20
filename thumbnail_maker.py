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


def _crop_and_resize_9_16(image: Image.Image, target_w=1080, target_h=1920) -> Image.Image:
    """이미지를 9:16 (1080x1920) 비율로 중앙 크롭 및 리사이징"""
    w, h = image.size
    target_ratio = target_w / target_h
    current_ratio = w / h

    if current_ratio > target_ratio:
        # 가로가 더 넓음 -> 좌우 크롭
        new_w = int(h * target_ratio)
        offset = (w - new_w) // 2
        image = image.crop((offset, 0, offset + new_w, h))
    else:
        # 세로가 더 김 -> 상하 크롭
        new_h = int(w / target_ratio)
        offset = (h - new_h) // 2
        image = image.crop((0, offset, w, offset + new_h))

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
    badge_label: str = "🔥 화제의 추천템"
) -> str:
    """
    고화질 9:16 유튜브 쇼츠 썸네일 자동 합성 생성
    Returns: 생성된 섬네일.png 파일 경로
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

    # 2. 상단/중앙 시인성을 높이기 위한 반투명 어두운 오버레이 레이어
    overlay = Image.new("RGBA", bg.size, (0, 0, 0, 0))
    draw_overlay = ImageDraw.Draw(overlay)

    # 상단 텍스트 영역에 부드러운 그라데이션 어둡게 처리
    for y in range(800):
        alpha = int(140 * (1.0 - (abs(y - 420) / 450) ** 1.5))
        if alpha > 0:
            draw_overlay.line([(0, y), (1080, y)], fill=(0, 0, 0, min(140, alpha)))

    bg = Image.alpha_composite(bg, overlay)

    # 3. 텍스트 레이아웃 분할 (불필요한 메타 라벨 제거 및 줄바꿈 정리)
    raw_lines = [clean_thumbnail_line(l) for l in copy_text.splitlines()]
    raw_lines = [l for l in raw_lines if l]
    lines = []
    for clean_l in raw_lines:
        if len(clean_l) > 16:
            # 너무 긴 문장은 2줄로 분할
            mid = len(clean_l) // 2
            split_idx = clean_l.rfind(" ", 0, mid + 4)
            if split_idx == -1:
                split_idx = mid
            lines.append(clean_l[:split_idx].strip())
            lines.append(clean_l[split_idx:].strip())
        else:
            lines.append(clean_l)

    lines = lines[:3]  # 최대 3줄

    # 4. 텍스트 및 배지 렌더링
    draw = ImageDraw.Draw(bg)

    try:
        font_main = ImageFont.truetype(FONT_PATH, 74)
        font_badge = ImageFont.truetype(FONT_PATH, 42)
    except Exception:
        font_main = ImageFont.load_default()
        font_badge = ImageFont.load_default()

    # 텍스트 크기 계산
    line_bboxes = [draw.textbbox((0, 0), line, font=font_main, stroke_width=6) for line in lines]
    max_line_w = max((bb[2] - bb[0]) for bb in line_bboxes) if line_bboxes else 400
    line_h = max((bb[3] - bb[1]) for bb in line_bboxes) if line_bboxes else 80

    total_text_h = len(lines) * (line_h + 24)
    start_y = 360  # 모바일 쇼츠 UI 상단 여백 (프로필/아이콘 간섭 방지 최적 영역)

    # A. 상단 후킹 배지 (예: 🔥 화제의 추천템)
    if badge_label:
        badge_bb = draw.textbbox((0, 0), badge_label, font=font_badge)
        badge_w = badge_bb[2] - badge_bb[0] + 48
        badge_h = badge_bb[3] - badge_bb[1] + 24
        badge_x = (1080 - badge_w) // 2
        badge_y = start_y - badge_h - 26

        draw.rounded_rectangle(
            [badge_x, badge_y, badge_x + badge_w, badge_y + badge_h],
            radius=18,
            fill="#FFE500"  # 네온 옐로우 배지
        )
        draw.text(
            (badge_x + 24, badge_y + 8),
            badge_label,
            font=font_badge,
            fill="#000000"
        )

    # B. 메인 텍스트 박스 배경 (반투명 블랙 박스 + 네온 옐로우 테두리)
    pad_x = 44
    pad_y = 32
    box_w = min(1000, max_line_w + pad_x * 2)
    box_h = total_text_h + pad_y * 2
    box_x = (1080 - box_w) // 2
    box_y = start_y

    box_overlay = Image.new("RGBA", bg.size, (0, 0, 0, 0))
    box_draw = ImageDraw.Draw(box_overlay)

    # 반투명 블랙 백그라운드
    box_draw.rounded_rectangle(
        [box_x, box_y, box_x + box_w, box_y + box_h],
        radius=30,
        fill=(0, 0, 0, 205),
        outline="#FFE500",
        width=5
    )
    bg = Image.alpha_composite(bg, box_overlay)
    draw = ImageDraw.Draw(bg)

    # C. 메인 텍스트 그리기 (스트로크 + 색상 교차)
    cur_y = box_y + pad_y
    for idx, line in enumerate(lines):
        line_bb = draw.textbbox((0, 0), line, font=font_main, stroke_width=6)
        w = line_bb[2] - line_bb[0]
        x = (1080 - w) // 2
        # 첫 줄은 노란색, 둘째/셋째 줄은 화이트로 시선 분산 방지
        text_color = "#FFE500" if idx == 0 else "#FFFFFF"
        draw.text(
            (x, cur_y),
            line,
            font=font_main,
            fill=text_color,
            stroke_width=6,
            stroke_fill="#000000"
        )
        cur_y += line_h + 24

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
