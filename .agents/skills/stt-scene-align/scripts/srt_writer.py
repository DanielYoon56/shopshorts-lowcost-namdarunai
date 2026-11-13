"""scene_data.json → SRT 변환 (CapCut/편집툴용 자막). 외부 의존성 없음.

align.py(상품 쇼츠), faction align_scenes.py(팩션 쇼츠), dashboard.py 가 모두 이 모듈을 사용한다.
"""

import json
import os


def format_srt_time(sec: float) -> str:
    total_ms = int(round(float(sec) * 1000))  # 부동소수 오차 방지 (1.21 → 1,210ms)
    h, rem = divmod(total_ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def scenes_to_srt(scenes: list) -> str:
    blocks = []
    index = 1
    for sc in scenes:
        text = " ".join(b.get("text", "").strip() for b in sc.get("text_blocks", [])).strip()
        if not text:
            continue
        blocks.append(f"{index}\n{format_srt_time(sc['start'])} --> {format_srt_time(sc['end'])}\n{text}\n")
        index += 1
    return "\n".join(blocks)


def write_srt(folder: str, scenes: list | None = None) -> str:
    """<프로젝트 폴더>/subtitles.srt 를 scene_data.json 기준으로 (재)생성하고 경로를 반환.

    CapCut 투입 파일(동영상 클립·음성 wav·SRT)은 압축 없이 프로젝트 폴더에 함께 둔다.
    """
    if scenes is None:
        with open(os.path.join(folder, "scene_data.json"), encoding="utf-8") as f:
            scenes = json.load(f)
    path = os.path.join(folder, "subtitles.srt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(scenes_to_srt(scenes))
    # 예전 위치(assets/subtitles.srt)의 오래된 사본은 혼동 방지를 위해 제거
    legacy = os.path.join(folder, "assets", "subtitles.srt")
    if os.path.exists(legacy):
        os.remove(legacy)
    return path
