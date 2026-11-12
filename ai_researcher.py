def sanitize_script_no_price(text):
    """대본에서 상품 가격(예: 19,800원, 몇만 원 등) 표현을 제거/정제"""
    # 가격 패턴 매칭 (단돈 ~원, 숫자+원, 숫자+만원 등)
    text = re.sub(r'단돈\s*[\d,일이삼사오육칠팔구십백천만\s]+원[대|에|으로]?', '', text)
    text = re.sub(r'[\d,]+\s*원[대|에|으로]?', '', text)
    text = re.sub(r'[일이삼사오육칠팔구십\d]+\s*만\s*원[대|에|으로]?', '', text)
    text = re.sub(r'몇십만\s*원[대|에|으로]?', '많은 비용', text)
    text = re.sub(r'몇만\s*원[대|에|으로]?', '부담 없는 가격', text)
    return text.strip()

import os
import re
import json
import requests
from dotenv import load_dotenv

load_dotenv()

# 쿠팡 상품 상세 수집 스킬 (.agents/skills/coupang-crawler)
import sys as _sys
_COUPANG_SKILL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".agents", "skills", "coupang-crawler", "scripts")
if _COUPANG_SKILL_DIR not in _sys.path:
    _sys.path.insert(0, _COUPANG_SKILL_DIR)
import coupang_crawler
import coupang_ocr

COUPANG_JSON_NAME = "coupang-product.json"
COUPANG_OCR_JSON_NAME = "coupang-ocr.json"
COUPANG_DETAIL_DIR = os.path.join("assets", "coupang_detail")


def is_coupang_url(url):
    from urllib.parse import urlsplit
    host = (urlsplit(url or "").hostname or "").lower()
    return host == "coupang.com" or host.endswith(".coupang.com")


def ingest_coupang_page(saved_page_path, target_folder, source_url=""):
    """브라우저에서 저장한 쿠팡 상품 페이지(.html/.mhtml)를 파싱해 프로젝트 폴더에 JSON으로 저장."""
    from pathlib import Path
    html = coupang_crawler.read_saved_page(Path(saved_page_path))
    result = coupang_crawler.parse_product_html(html, source_url)
    os.makedirs(target_folder, exist_ok=True)
    with open(os.path.join(target_folder, COUPANG_JSON_NAME), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 새 상품이 들어오면 이전 상품의 상세 이미지/OCR 결과는 지운다
    import shutil
    detail_dir = os.path.join(target_folder, COUPANG_DETAIL_DIR)
    shutil.rmtree(detail_dir, ignore_errors=True)
    ocr_path = os.path.join(target_folder, COUPANG_OCR_JSON_NAME)
    if os.path.exists(ocr_path):
        os.remove(ocr_path)
    # .mhtml 에는 상세 이미지 원본이 함께 저장돼 있으므로 OCR/레퍼런스용으로 꺼내 둔다
    try:
        images = coupang_ocr.extract_images_from_mhtml(
            Path(saved_page_path), result["fields"].get("detail_images", []), Path(detail_dir)
        )
    except Exception as e:  # .html 저장본 등 이미지가 없는 경우
        print(f"[!] 상세 이미지 추출 건너뜀: {e}")
        images = []
    result["detail_image_files"] = len(images)
    return result


def run_coupang_ocr(target_folder):
    """프로젝트의 상세 이미지를 OCR 해 스펙 후보를 coupang-ocr.json 으로 저장 (LLM 미사용)."""
    from pathlib import Path
    detail_dir = Path(target_folder) / COUPANG_DETAIL_DIR
    images = coupang_ocr.list_images(detail_dir) if detail_dir.is_dir() else []
    if not images:
        raise RuntimeError("상세 이미지가 없습니다. 쿠팡 페이지를 '웹페이지, 단일 파일(.mhtml)'로 저장해 다시 올려 주세요.")
    product = load_coupang_data(target_folder) or {}
    result = coupang_ocr.run(images, product.get("fields", {}).get("title", ""))
    with open(os.path.join(target_folder, COUPANG_OCR_JSON_NAME), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return result


def load_coupang_data(target_folder):
    """coupang-product.json (+ 있으면 coupang-ocr.json 을 'ocr' 키로) 로드."""
    path = os.path.join(target_folder, COUPANG_JSON_NAME)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    ocr_path = os.path.join(target_folder, COUPANG_OCR_JSON_NAME)
    if os.path.exists(ocr_path):
        with open(ocr_path, encoding="utf-8") as f:
            data["ocr"] = json.load(f)
    return data

def fetch_url_metadata(url):
    """URL에서 제목, 메타 설명 등 기초 제품 정보 스크랩"""
    if not url or not url.startswith("http"):
        return {}
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
        }
        r = requests.get(url, headers=headers, timeout=5)
        html = r.text
        
        # 제목 추출
        title_match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
        title = title_match.group(1).strip() if title_match else ""
        
        # og:title
        og_title_match = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\'](.*?)["\']', html, re.IGNORECASE)
        if not og_title_match:
            og_title_match = re.search(r'<meta\s+content=["\'](.*?)["\']\s+property=["\']og:title["\']', html, re.IGNORECASE)
        og_title = og_title_match.group(1).strip() if og_title_match else ""
        
        # og:description
        og_desc_match = re.search(r'<meta\s+property=["\']og:description["\']\s+content=["\'](.*?)["\']', html, re.IGNORECASE)
        if not og_desc_match:
            og_desc_match = re.search(r'<meta\s+content=["\'](.*?)["\']\s+property=["\']og:description["\']', html, re.IGNORECASE)
        og_desc = og_desc_match.group(1).strip() if og_desc_match else ""

        return {
            "title": og_title or title,
            "description": og_desc
        }
    except Exception as e:
        print(f"[!] URL 메타데이터 수집 실패 ({url}): {e}")
        return {}

def call_llm(prompt, system_prompt, prefer_model="auto", image_path=None):
    """OpenAI 또는 Gemini를 통해 LLM 호출 (멀티모달 이미지 분석 지원)"""
    openai_key = os.getenv("OPENAI_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")
    
    use_model = prefer_model
    if use_model == "auto":
        # 이미지 분석이 필요하거나 Gemini 키가 있으면 gemini 우선 (Google AI Pro 최적화)
        if gemini_key and len(gemini_key) > 5:
            use_model = "gemini"
        elif openai_key and len(openai_key) > 5:
            use_model = "openai"
        else:
            raise ValueError("OpenAI 또는 Gemini API 키가 설정되지 않았습니다. .env 파일을 확인하세요.")

    if use_model == "openai":
        from openai import OpenAI
        client = OpenAI(api_key=openai_key)
        
        user_content = prompt
        if image_path and os.path.exists(image_path):
            import base64
            with open(image_path, "rb") as img_f:
                b64 = base64.b64encode(img_f.read()).decode("utf-8")
            user_content = [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
            ]
            
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            temperature=0.7,
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
        
    elif use_model == "gemini":
        from google import genai
        from google.genai import types
        from PIL import Image
        client = genai.Client(api_key=gemini_key)
        
        full_text = f"{system_prompt}\n\n반드시 순수 JSON 객체만 응답하세요.\n\n사용자 요청:\n{prompt}"
        contents = [full_text]
        if image_path and os.path.exists(image_path):
            img = Image.open(image_path)
            contents.insert(0, img)
            
        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        return json.loads(response.text)
    else:
        raise ValueError(f"지원하지 않는 모델: {use_model}")

def run_product_research(product_text, url="", pipeline_type="product_15s", category="자동 감지", model_choice="auto", image_path=None, custom_script=None, coupang_data=None):
    """
    제품 텍스트, URL, 실물 이미지, 커스텀 대본을 분석하여:
    1. PRODUCT_TRUTH / STORY_TRUTH
    2. plan.md (6비트 또는 4단계 팩션 서사)
    3. script.md (자막 및 음성용 한국어 구어체 대본)
    4. prompts.md (미드저니/클링용 비주얼 프롬프트)
    5. publish_kit.md (제목/해시태그)
    를 한 번에 생성
    """
    # 쿠팡은 비브라우저 요청을 403으로 차단하므로 범용 메타 수집을 건너뛰고 저장 페이지 파싱 결과를 쓴다
    url_info = {} if is_coupang_url(url) else fetch_url_metadata(url)

    context_text = f"사용자 입력 정보: {product_text}\n"
    if url:
        context_text += f"상품 URL: {url}\n"
    if coupang_data:
        context_text += "\n" + coupang_crawler.to_research_context(coupang_data)
        if coupang_data.get("ocr"):
            context_text += coupang_ocr.to_research_context(coupang_data["ocr"])
        context_text += "(위 쿠팡 수집 정보에 없는 성능·효능·후기는 지어내지 말 것. [불일치 주의]/[구매 주의] 항목은 대본에서 반드시 피하거나 반영할 것. [중요] 쇼츠 대본에는 가격 변동 이슈 방지를 위해 상품 가격 및 할인 금액을 절대 언급하지 말 것)\n\n"
    if url_info.get("title"):
        context_text += f"웹페이지 제목: {url_info['title']}\n"
    if url_info.get("description"):
        context_text += f"웹페이지 요약: {url_info['description']}\n"
    if category != "자동 감지":
        context_text += f"지정 카테고리: {category}\n"
    if image_path and os.path.exists(image_path):
        context_text += f"\n[중요] 첨부된 실물 제품 사진을 시각적으로 정밀 분석하여 제품의 정확한 색상, 재질, 형태, 버튼/LED 유무, 패키지 특징을 PRODUCT_TRUTH 및 6컷 비주얼 프롬프트에 100% 일치하도록 반영하세요.\n"
    if custom_script and custom_script.strip():
        context_text += f"\n[사용자 제공 원문 대본 및 콘티]:\n{custom_script}\n(주의: 사용자가 제공한 대본과 의도를 100% 계승하여 문장 단위 script.md와 타임라인을 정렬하세요.)\n"

    if pipeline_type == "product_15s":
        system_prompt = """
당신은 대한민국 상위 0.1% 숏폼 커머스 영상 총괄 기획자입니다.
단일 제품의 강렬한 15초~25초(1.2배속 기준) 시연 쇼핑쇼츠를 기획합니다.

[핵심 규칙 - 검증된 15초 6비트 레시피]
1. 훅은 무조건 '결과 선공개'부터 시작합니다. (문제 화면이나 로고로 시작 금지)
2. 6비트 타임라인:
   - 비트 1 (Hook): 결과 선공개 (Cut 1 Hero/Result) - 완성된 결과물 클로즈업
   - 비트 2 (Before): 대비 (Cut 2 Before/Problem) - 기존 방식의 불편함/분실 불안감
   - 비트 3 (Hero): 제품 공개 (Cut 3 Hero/Product) - 제품 정면 고정 팩샷
   - 비트 4 (Action): 핵심 시연 (Cut 4 Action/Detail) - 한 가지 핵심 동작 (착용, 작동)
   - 비트 5 (Proof): 재훅/증명 (Cut 5 Re-Hook/Proof) - 결과물 및 기능 증명 (방수, 내구성)
   - 비트 6 (CTA): 루프 엔딩 + 구매 유도 (Cut 6 Loop) - 첫 컷과 연결되는 팩샷이며, 마지막 CTA 멘트는 반드시 '프로필 링크를 참조하세요'로 끝남
3. 대본(script) 작성 규칙:
   - 문장 단위로 줄바꿈 (stt-scene-align이 1:1로 자막 씬에 매핑됨)
   - [절대 금지 - 가격 언급 금지] 대본에 구체적인 상품 가격(예: 19,800원, 3만 원대, 몇십만 원 등)이나 할인 금액은 절대 넣지 마세요. (영상 생명주기 및 실시간 가격 변동 문제 방지)
   - 숫자는 반드시 한글 발음으로 표기 (예: "46g" -> "사십육 그램", "30%" -> "삼십 퍼센트", "USB-C" -> "유에스비 씨")
   - 사용자가 직접 대본을 제공한 경우 해당 문장을 우선 정제하여 적용할 것.
   - [필수] 대본의 마지막 CTA 문장은 반드시 '프로필 링크를 참조하세요'로 끝나야 합니다. (이 멘트가 없으면 쇼핑 전환이 일어나지 않습니다.)
4. 프롬프트(prompts.md) 작성 규칙:
   - 첨부된 실물 사진의 외형(색상, 재질, LED 불빛 등)을 반드시 반영한 고화질 영문 프롬프트 작성 (Pure authentic photography, studio lighting, no text).

[반환 JSON 스키마]
{
  "product_name": "제품명",
  "category": "식품/뷰티/생활/가전 등",
  "usp": "핵심 소구점 한 줄",
  "product_truth": "PRODUCT_TRUTH YAML/마크다운 형식 요약",
  "plan_md": "6비트 타임라인과 촬영 플랜 마크다운",
  "script_md": "줄 단위로 분리된 음성 대본 텍스트",
  "prompts_md": "6개 컷별 AI 비주얼 프롬프트 (Cut 1~6)",
  "publish_kit_md": "쇼츠 제목 3종, 설명문, 해시태그 10개, 썸네일 카피"
}
"""
    else:  # faction_30s
        system_prompt = """
당신은 유튜브 100만 바이럴 썰 쇼츠 전문 크리에이터입니다.
대놓고 파는 광고가 아니라, 도파민 넘치는 '흥미진진한 비하인드 썰'로 위장하여 끝까지 보게 만드는 30초(1.5배속 기준) 팩션(Faction) 쇼츠를 기획합니다.

[핵심 규칙 - 4단계 팩션 서사 구조]
1. 단계 1 (도파민 후킹, 0~4초): 상식을 깨는 충격적 사실, 논란, 창업자 집착, 품절 대란
2. 단계 2 (빌드업, 5~15초): 왜 그런 일이 벌어졌는지 흥미진진한 뒷이야기, 개발 과정의 광기
3. 단계 3 (클라이맥스/반전, 16~24초): 알고 보니 이 제품의 미친 성능/기능 때문이었다는 증명
4. 단계 4 (여운/CTA, 25~30초): 썰의 여운을 남긴 후, 마지막 마무리 멘트는 반드시 '프로필 링크를 참조하세요'로 끝납니다.
5. 대본(script) 작성 규칙:
   - [절대 금지 - 가격 언급 금지] 대본에 구체적인 상품 가격(예: 19,800원, 몇만 원 등)이나 할인 금액은 절대 넣지 마세요.
   - 몰입감 넘치는 썰 구어체 (~했대, ~더라고, 알고 보니)
   - 문장 단위 줄바꿈
   - 숫자는 한글 발음 표기 ("100만 개" -> "백만 개")
   - [필수] 대본의 마지막 문장(CTA 멘트)은 반드시 '프로필 링크를 참조하세요'를 넣어주어야 합니다.
   - 1.5배속 기준 약 26~28초 분량

[반환 JSON 스키마]
{
  "product_name": "제품명 및 회사명",
  "category": "카테고리",
  "usp": "스토리의 핵심 갈등 및 소구점",
  "product_truth": "STORY_TRUTH 마크다운 요약",
  "plan_md": "4단계 팩션 서사 촬영 플랜 마크다운",
  "script_md": "줄 단위로 분리된 팩션 대본 텍스트",
  "prompts_md": "시네마틱 실사 AI 비주얼 프롬프트",
  "publish_kit_md": "어그로 쇼츠 제목 3종, 설명문, 해시태그 10개, 썸네일 카피"
}
"""

    prompt = f"다음 제품 정보를 바탕으로 최적의 쇼핑 쇼츠 기획을 작성해주세요:\n\n{context_text}"
    res = call_llm(prompt, system_prompt, prefer_model=model_choice, image_path=image_path)
    
    # 가격 언급 제거 및 마지막 CTA 문장은 반드시 '프로필 링크를 참조하세요' 강제 보장
    if isinstance(res, dict) and res.get("script_md"):
        cleaned_script = sanitize_script_no_price(res["script_md"])
        lines = [l.strip() for l in cleaned_script.split("\n") if l.strip()]
        cta_target = "프로필 링크를 참조하세요"
        if lines:
            if lines[-1] != cta_target:
                if any(k in lines[-1] for k in ["프로필", "링크", "구매", "참조", "확인"]):
                    lines[-1] = cta_target
                else:
                    lines.append(cta_target)
            res["script_md"] = "\n".join(lines)
    return res

def save_research_artifacts(target_folder, result_dict):
    """생성된 기획 아티팩트를 대상 폴더에 저장"""
    os.makedirs(target_folder, exist_ok=True)
    os.makedirs(os.path.join(target_folder, "assets"), exist_ok=True)
    
    # 1. script.md
    if result_dict.get("script_md"):
        lines = [l.strip() for l in result_dict["script_md"].strip().split("\n") if l.strip()]
        cta_target = "프로필 링크를 참조하세요"
        if lines and lines[-1] != cta_target:
            if any(k in lines[-1] for k in ["프로필", "링크", "구매", "참조", "확인"]):
                lines[-1] = cta_target
            else:
                lines.append(cta_target)
        final_script = "\n".join(lines)
        with open(os.path.join(target_folder, "script.md"), "w", encoding="utf-8") as f:
            f.write(final_script.strip() + "\n")
            
    # 2. plan.md
    plan_content = ""
    if result_dict.get("product_truth"):
        plan_content += f"# 제품 분석 (TRUTH)\n\n{result_dict['product_truth']}\n\n---\n\n"
    if result_dict.get("plan_md"):
        plan_content += result_dict["plan_md"].strip() + "\n"
    if plan_content:
        with open(os.path.join(target_folder, "plan.md"), "w", encoding="utf-8") as f:
            f.write(plan_content)

    # 3. prompts.md
    if result_dict.get("prompts_md"):
        with open(os.path.join(target_folder, "prompts.md"), "w", encoding="utf-8") as f:
            f.write(result_dict["prompts_md"].strip() + "\n")

    # 4. publish_kit.md
    if result_dict.get("publish_kit_md"):
        with open(os.path.join(target_folder, "publish_kit.md"), "w", encoding="utf-8") as f:
            f.write(result_dict["publish_kit_md"].strip() + "\n")

