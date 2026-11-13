#!/usr/bin/env python
"""쿠팡 상세 이미지 OCR → 스펙 후보 추출 (LLM 미사용).

- 상세 이미지는 저장한 .mhtml 안에 원본이 함께 들어 있으므로 쿠팡에 다시 접속하지 않는다.
- OCR: RapidOCR (PP-OCRv5 한국어 mobile, onnxruntime / CPU)
- 추출: 정규식 규칙. 결과는 '스펙 후보 + 근거 문장 + 출처 이미지'이며 확정 사실이 아니다.
"""

from __future__ import annotations

import argparse
import email
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

SLICE_HEIGHT = 1000   # 세로로 긴 상세 이미지를 이 높이로 잘라 OCR
SLICE_OVERLAP = 120   # 잘린 경계의 글자 손실 방지
MIN_SCORE = 0.6       # 이 신뢰도 미만 OCR 결과는 버림
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")


# ---------------------------------------------------------------------------
# 이미지 확보
# ---------------------------------------------------------------------------

def extract_images_from_mhtml(mhtml_path: Path, image_urls: list[str], out_dir: Path) -> list[Path]:
    """mhtml 에 함께 저장된 이미지 중 image_urls 에 해당하는 것만 순서대로 저장."""
    wanted = {urlsplit(u).path: i for i, u in enumerate(image_urls)}
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: dict[int, Path] = {}
    msg = email.message_from_bytes(mhtml_path.read_bytes())
    for part in msg.walk():
        path = urlsplit(part.get("Content-Location", "")).path
        if path in wanted and wanted[path] not in saved:
            data = part.get_payload(decode=True)
            if not data:
                continue
            idx = wanted[path]
            ext = Path(path).suffix.lower() if Path(path).suffix.lower() in IMAGE_EXTS else ".img"
            target = out_dir / f"detail_{idx:02d}{ext}"
            target.write_bytes(data)
            saved[idx] = target
    return [saved[i] for i in sorted(saved)]


def list_images(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTS + (".img",))


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------

_ENGINE = None


def get_engine():
    global _ENGINE
    if _ENGINE is None:
        try:
            from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR
        except ImportError as exc:
            raise RuntimeError("OCR 엔진이 없습니다: pip install rapidocr onnxruntime") from exc
        _ENGINE = RapidOCR(params={
            "Rec.lang_type": LangRec.KOREAN,
            "Rec.ocr_version": OCRVersion.PPOCRV5,
            "Rec.model_type": ModelType.MOBILE,
        })
    return _ENGINE


def ocr_image(path: Path) -> list[str]:
    import cv2
    import numpy as np

    img = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return []
    engine = get_engine()
    height = img.shape[0]
    lines: list[str] = []
    y = 0
    while True:
        result = engine(img[y:min(height, y + SLICE_HEIGHT)])
        for text, score in zip(result.txts or (), result.scores or ()):
            text = re.sub(r"\s+", " ", text).strip()
            # 겹침 구간에서 같은 줄이 두 번 읽히는 것 제거
            if score >= MIN_SCORE and text and text not in lines[-15:]:
                lines.append(text)
        if y + SLICE_HEIGHT >= height:
            break
        y += SLICE_HEIGHT - SLICE_OVERLAP
    return lines


# ---------------------------------------------------------------------------
# 규칙 기반 스펙 추출
# ---------------------------------------------------------------------------

NUM = r"\d+(?:[.,]\d+)?"

# (스펙 종류, 정규식) — 매칭된 원문 그대로 value 로 저장
SPEC_RULES: list[tuple[str, re.Pattern]] = [
    ("단계 조절", re.compile(rf"(?:[가-힣]+\s*)?{NUM}\s*단(?:계)?\s*(?:[가-힣]+\s*조절|조절|[가-힣]{{1,6}})?")),
    ("시간/타이머", re.compile(rf"{NUM}(?:\s*[/~-]\s*{NUM})+\s*(?:분|시간|h|H)|{NUM}\s*(?:분|시간)\s*(?:타이머|자동|후)")),
    ("가열/작동 시간", re.compile(rf"{NUM}\s*초\s*[가-힣]*(?:가열|발열|작동|충전)")),
    ("온도", re.compile(rf"{NUM}(?:\s*[~-]\s*{NUM})?\s*(?:℃|°C|°c|도씨)")),
    ("소비전력", re.compile(rf"{NUM}\s*(?:W|와트|kW)\b")),
    ("전압/주파수", re.compile(rf"{NUM}(?:\s*[~-]\s*{NUM})?\s*V\b|{NUM}\s*Hz", re.I)),
    ("크기", re.compile(rf"{NUM}\s*[x×X*]\s*{NUM}(?:\s*[x×X*]\s*{NUM})?\s*(?:cm|mm|m)\b")),
    ("무게", re.compile(rf"{NUM}\s*(?:kg|g)\b")),
    ("용량/배터리", re.compile(rf"{NUM}\s*(?:mAh|ml|mL|L|리터)\b")),
    ("방수 등급", re.compile(r"IP[X]?\d{1,2}", re.I)),
]

FEATURE_RULES: list[tuple[str, re.Pattern]] = [
    ("자동 전원 차단", re.compile(r"자동\s*(?:전원)?\s*(?:끄기|차단|꺼짐|오프|OFF)", re.I)),
    ("과열 방지", re.compile(r"과열\s*(?:방지|보호|차단)")),
    ("급속 가열", re.compile(r"(?:급속|빠른)\s*(?:가열|발열)")),
    ("물세탁 가능", re.compile(r"(?:물\s*세탁|세탁기로?\s*세탁|세탁\s*가능|물\s*세척)")),
    ("방수", re.compile(r"방수|생활\s*방수")),
    ("무선/충전식", re.compile(r"무선|충전식|USB\s*-?\s*C?\s*충전", re.I)),
    ("저소음", re.compile(r"저소음|무소음")),
    ("휴대용", re.compile(r"휴대용|휴대\s*가능|접이식")),
]

CERT_RULES: list[tuple[str, re.Pattern]] = [
    ("KC", re.compile(r"\bKC\b|KC\s*인증|전기용품\s*안전")),
    ("CE", re.compile(r"\bCE\b")),
    ("FCC", re.compile(r"\bFCC?\b")),
    ("RoHS", re.compile(r"RoHS", re.I)),
    ("UKCA", re.compile(r"UKCA")),
    ("FDA", re.compile(r"\bFDA\b")),
    ("PSE", re.compile(r"\bPSE\b")),
]

PURCHASE_RULES: list[tuple[str, re.Pattern]] = [
    ("해외직구 상품 (개인통관고유부호 필요)", re.compile(r"개인\s*통관\s*고유\s*부호|통관부호")),
    ("해외 배송", re.compile(r"해외\s*(?:직구|배송)|통관\s*심사|유니패스|관세청")),
    ("변환 플러그 필요 가능성", re.compile(r"변환\s*플러그|돼지코|유럽형\s*(?:코드|플러그)")),
    ("단순 변심 반품 제한", re.compile(r"단순\s*변심")),
]


def _collect(rules, lines_by_image, keep_value=True):
    found: dict[str, dict] = {}
    for img, lines in lines_by_image:
        for line in lines:
            for name, pattern in rules:
                for m in pattern.finditer(line):
                    value = re.sub(r"\s+", " ", m.group(0)).strip() if keep_value else name
                    key = f"{name}|{value}"
                    if key not in found:
                        found[key] = {"type": name, "value": value, "evidence": line, "image": img}
    return list(found.values())


def extract_specs(lines_by_image: list[tuple[str, list[str]]]) -> dict:
    specs = _collect(SPEC_RULES, lines_by_image)
    # 단계 조절: '9단계 온도 조절'처럼 무엇을 조절하는지 붙은 것만 남기고, 숫자만 있는 짧은 매칭은 제거
    specs = [s for s in specs if not (s["type"] == "단계 조절" and re.fullmatch(rf"{NUM}\s*단(?:계)?", s["value"]) and len(s["evidence"]) <= 3)]
    return {
        "specs": specs,
        "features": _collect(FEATURE_RULES, lines_by_image, keep_value=False),
        "certifications": _collect(CERT_RULES, lines_by_image, keep_value=False),
        "purchase_notes": _collect(PURCHASE_RULES, lines_by_image, keep_value=False),
    }


STEP_SUBJECTS = {
    "온도": ("온도", "열", "발열", "가열"),
    "타이머": ("타이머", "타이밍", "시간"),
    "바람": ("바람", "풍량", "풍속"),
    "세기": ("세기", "강도", "진동", "출력"),
    "밝기": ("밝기", "조도", "밝게"),
}


def _step_pairs(text: str) -> list[tuple[str, str]]:
    """'온도조절 4단계' / '9단계 온도 조절' / '4단 타이밍' → [(주제, 숫자)]"""
    text = text or ""
    result = []
    for m in re.finditer(r"(\d+)\s*단(?:계)?", text):
        best = None  # (간격, 주제)
        for subject, words in STEP_SUBJECTS.items():
            for w in words:
                for wm in re.finditer(re.escape(w), text[max(0, m.start() - 10):m.end() + 10]):
                    start = max(0, m.start() - 10) + wm.start()
                    end = start + len(w)
                    # 단어와 '4단계' 토큰 사이의 글자 수 (앞/뒤 모두). '조절'은 앞쪽 주제에 붙는 말이므로 간격에서 뺀다
                    gap = m.start() - end if end <= m.start() else start - m.end()
                    between = text[end:m.start()] if end <= m.start() else text[m.end():start]
                    gap -= between.count("조절") * 2
                    if gap >= 0 and (best is None or gap < best[0]):
                        best = (gap, subject)
        if best:
            result.append((best[1], m.group(1)))
    return result


def find_conflicts(title: str, specs: list[dict]) -> list[str]:
    """상품명의 '온도 N단계'와 상세 이미지의 '온도 M단계'처럼 같은 항목의 단계 수가 다르면 경고."""
    image_steps: dict[str, tuple[str, str]] = {}
    for s in specs:
        if s["type"] == "단계 조절":
            for subject, num in _step_pairs(s["evidence"]):
                image_steps.setdefault(subject, (num, s["evidence"]))
    conflicts = []
    for subject, num in _step_pairs(title):
        if subject in image_steps and image_steps[subject][0] != num:
            img_num, evidence = image_steps[subject]
            conflicts.append(
                f"상품명에는 {subject} {num}단계, 상세 이미지에는 {subject} {img_num}단계 (원문: \"{evidence}\") — 대본에 쓰기 전 확인 필요"
            )
    return conflicts


def run(images: list[Path], title: str = "") -> dict:
    started = time.time()
    lines_by_image = []
    for path in images:
        lines_by_image.append((path.name, ocr_image(path)))
    extracted = extract_specs(lines_by_image)
    return {
        "source": "detail_image_ocr",
        "engine": "rapidocr PP-OCRv5 korean mobile (CPU)",
        "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "elapsed_sec": round(time.time() - started, 1),
        **extracted,
        "conflicts": find_conflicts(title, extracted["specs"]),
        "ocr_text": [{"image": name, "lines": lines} for name, lines in lines_by_image],
        "notes": [
            "OCR 기반 '후보'입니다. 장식 폰트·사진 위 글자는 잘못 읽힐 수 있으니 영상에 쓰기 전 근거 이미지를 확인하세요.",
        ],
    }


def to_research_context(ocr: dict) -> str:
    if not ocr:
        return ""
    lines = ["[상세 이미지 OCR 스펙 후보 - 근거 문장 있는 것만, 확인 필요]"]
    for s in ocr.get("specs", [])[:25]:
        lines.append(f"- {s['type']}: {s['value']}  (원문: \"{s['evidence']}\")")
    if ocr.get("features"):
        lines.append("- 기능: " + ", ".join(f["type"] for f in ocr["features"]))
    if ocr.get("certifications"):
        lines.append("- 인증 마크: " + ", ".join(c["type"] for c in ocr["certifications"]))
    for n in ocr.get("purchase_notes", []):
        lines.append(f"- [구매 주의] {n['type']}  (원문: \"{n['evidence']}\")")
    for c in ocr.get("conflicts", []):
        lines.append(f"- [불일치 주의] {c}")
    if any(n["type"].startswith("해외") for n in ocr.get("purchase_notes", [])):
        lines.append("- [대본 규칙] 해외 발송 상품이므로 '빠른 배송/로켓배송' 등 배송 속도 소구 금지")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="쿠팡 상세 이미지 OCR 스펙 추출 (LLM 미사용)")
    ap.add_argument("--product-json", required=True, help="coupang_crawler.py html 결과 JSON")
    ap.add_argument("--mhtml", help="같은 상품의 저장 .mhtml (상세 이미지 원본 추출용)")
    ap.add_argument("--images-dir", help="이미 추출된 상세 이미지 폴더 (mhtml 대신)")
    ap.add_argument("--output", required=True, help="결과 JSON 경로")
    args = ap.parse_args(argv)

    product = json.loads(Path(args.product_json).read_text(encoding="utf-8"))
    fields = product.get("fields", {})
    out = Path(args.output)
    try:
        if args.mhtml:
            images = extract_images_from_mhtml(Path(args.mhtml), fields.get("detail_images", []), out.parent / "coupang_detail")
        elif args.images_dir:
            images = list_images(Path(args.images_dir))
        else:
            raise RuntimeError("--mhtml 또는 --images-dir 중 하나가 필요합니다.")
        if not images:
            raise RuntimeError("OCR 할 상세 이미지가 없습니다 (.mhtml 로 저장했는지, 끝까지 스크롤했는지 확인).")
        result = run(images, fields.get("title", ""))
    except (RuntimeError, OSError) as exc:
        print(f"OCR 실패: {exc}", file=sys.stderr)
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"스펙 후보 {len(result['specs'])}개 · 기능 {len(result['features'])}개 · 인증 {len(result['certifications'])}개 "
          f"· 구매주의 {len(result['purchase_notes'])}개 ({result['elapsed_sec']}초) → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
