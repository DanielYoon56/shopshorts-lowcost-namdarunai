import os
import re
import json
import requests
from dotenv import load_dotenv

load_dotenv()

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

def call_llm(prompt, system_prompt, prefer_model="auto"):
    """OpenAI 또는 Gemini를 통해 LLM 호출"""
    openai_key = os.getenv("OPENAI_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")
    
    use_model = prefer_model
    if use_model == "auto":
        if openai_key and len(openai_key) > 5:
            use_model = "openai"
        elif gemini_key and len(gemini_key) > 5:
            use_model = "gemini"
        else:
            raise ValueError("OpenAI 또는 Gemini API 키가 설정되지 않았습니다. .env 파일을 확인하세요.")

    if use_model == "openai":
        from openai import OpenAI
        client = OpenAI(api_key=openai_key)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
        
    elif use_model == "gemini":
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=gemini_key)
        
        full_prompt = f"{system_prompt}\n\n반드시 순수 JSON 객체만 응답하세요.\n\n사용자 요청:\n{prompt}"
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=full_prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        return json.loads(response.text)
    else:
        raise ValueError(f"지원하지 않는 모델: {use_model}")

def run_product_research(product_text, url="", pipeline_type="product_15s", category="자동 감지", model_choice="auto"):
    """
    제품 텍스트 및 URL 정보를 분석하여:
    1. PRODUCT_TRUTH / STORY_TRUTH
    2. plan.md (6비트 또는 4단계 팩션 서사)
    3. script.md (자막 및 음성용 한국어 구어체 대본)
    4. prompts.md (미드저니/클링용 비주얼 프롬프트)
    5. publish_kit.md (제목/해시태그)
    를 한 번에 생성
    """
    url_info = fetch_url_metadata(url)
    
    context_text = f"사용자 입력 정보: {product_text}\n"
    if url:
        context_text += f"상품 URL: {url}\n"
    if url_info.get("title"):
        context_text += f"웹페이지 제목: {url_info['title']}\n"
    if url_info.get("description"):
        context_text += f"웹페이지 요약: {url_info['description']}\n"
    if category != "자동 감지":
        context_text += f"지정 카테고리: {category}\n"

    if pipeline_type == "product_15s":
        system_prompt = """
당신은 대한민국 상위 0.1% 숏폼 커머스 영상 총괄 기획자입니다.
단일 제품의 강렬한 15초(1.2배속 기준) 시연 쇼핑쇼츠를 기획합니다.

[핵심 규칙 - 검증된 15초 6비트 레시피]
1. 훅은 무조건 '결과 선공개'부터 시작합니다. (문제 화면이나 로고로 시작 금지)
2. 6비트 타임라인 (총 15초):
   - 비트 1 (3초): 결과 선공개 (Cut 1 Hero/Result) - 완성된 결과물 클로즈업
   - 비트 2 (2초): 대비 (Cut 2 Before/Problem) - 기존 방식의 불편함
   - 비트 3 (2초): 제품 공개 (Cut 3 Hero/Product) - 손이 제품을 들어올림
   - 비트 4 (4초): 핵심 시연 (Cut 4 Action/Detail) - 한 가지 핵심 동작
   - 비트 5 (2초): 재훅 (Cut 5 Re-Hook/Proof) - 결과물 손으로 집어 증명
   - 비트 6 (2초): 루프 엔딩 + CTA (Cut 6 Loop) - 첫 컷과 동일 앵글
3. 대본(script) 작성 규칙:
   - 문장 단위로 줄바꿈 (stt-scene-align이 1:1로 자막 씬에 매핑됨)
   - 숫자는 반드시 한글 발음으로 표기 (예: "46g" -> "사십육 그램", "30%" -> "삼십 퍼센트")
   - 발화 총 길이는 약 12~13초 (마지막 2초는 무음 CTA)
   - 광고 신호를 주는 진부한 표현("지금 사세요", "놀라운 효과") 배제하고 직관적인 USP 증명 중심

[반환 JSON 스키마]
{
  "product_name": "제품명",
  "category": "식품/뷰티/생활/가전 등",
  "usp": "핵심 소구점 한 줄",
  "product_truth": "PRODUCT_TRUTH YAML/마크다운 형식 요약",
  "plan_md": "6비트 타임라인과 촬영 플랜 마크다운",
  "script_md": "줄 단위로 분리된 음성 대본 텍스트",
  "prompts_md": "6개 컷별 Midjourney / Kling AI 비주얼 프롬프트",
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
4. 단계 4 (여운/Soft Sell, 25~30초): 대놓고 사라는 말 대신 품절 사태/군중심리 자극
5. 대본(script) 작성 규칙:
   - 몰입감 넘치는 썰 구어체 (~했대, ~더라고, 알고 보니)
   - 문장 단위 줄바꿈
   - 숫자는 한글 발음 표기 ("100만 개" -> "백만 개")
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
    return call_llm(prompt, system_prompt, prefer_model=model_choice)

def save_research_artifacts(target_folder, result_dict):
    """생성된 기획 아티팩트를 대상 폴더에 저장"""
    os.makedirs(target_folder, exist_ok=True)
    os.makedirs(os.path.join(target_folder, "assets"), exist_ok=True)
    
    # 1. script.md
    if result_dict.get("script_md"):
        with open(os.path.join(target_folder, "script.md"), "w", encoding="utf-8") as f:
            f.write(result_dict["script_md"].strip() + "\n")
            
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

