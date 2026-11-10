import os
import sys
import json
import re
import time
import glob
import urllib.parse
import subprocess
import requests
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = SCRIPT_DIR

def generate_via_pollinations(prompt, output_path, width=1024, height=576, model="flux"):
    """
    Pollinations.ai를 통한 초고화질 FLUX.1 이미지 무료 생성 (API 키 불필요)
    16:9 캔버스 (1024x576 또는 1280x720) 또는 9:16 (576x1024)
    """
    encoded_prompt = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&model={model}&nologo=true&enhance=true"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    # 재시도 로직 포함 (최대 3회)
    for attempt in range(3):
        try:
            r = requests.get(url, headers=headers, timeout=45)
            if r.status_code == 200 and len(r.content) > 5000:
                with open(output_path, "wb") as f:
                    f.write(r.content)
                return True
        except Exception as e:
            print(f"[!] Pollinations 호출 실패 (시도 {attempt+1}/3): {e}")
            time.sleep(2)
            
    raise RuntimeError("Pollinations 이미지 생성 서버 응답 실패")

def generate_via_gemini_imagen(prompt, output_path, aspect_ratio="16:9", ref_image_path=None):
    """Google Gemini Nano Banana / Imagen 모델을 통한 이미지 생성 (GEMINI_API_KEY 필요, 실물 사진 멀티모달 참조)"""
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        raise ValueError("GEMINI_API_KEY가 설정되지 않았습니다.")
        
    from google import genai
    from google.genai import types
    from PIL import Image
    client = genai.Client(api_key=gemini_key)
    
    # 1순위: Gemini Nano Banana (Google AI Pro/Plus 기본 이미지 모델)
    try:
        ratio_desc = "horizontal 16:9 widescreen composition" if aspect_ratio == "16:9" else "vertical 9:16 mobile shorts composition"
        full_prompt = (
            f"Commercial advertising photography of the EXACT same product shown in the reference image. "
            f"{prompt}, {ratio_desc}, ultra photorealistic, high quality, pristine studio lighting, 8k resolution, no text, no watermark."
        )
        
        contents = [full_prompt]
        if ref_image_path and os.path.exists(ref_image_path):
            try:
                ref_img = Image.open(ref_image_path)
                contents = [ref_img, full_prompt]
                print(f"[*] 실물 레퍼런스 사진 주입 완료: {os.path.basename(ref_image_path)}")
            except Exception as ie:
                print(f"[!] 레퍼런스 사진 로드 실패, 텍스트 프롬프트만 사용: {ie}")

        cfg = types.GenerateContentConfig(response_modalities=["IMAGE"])
        res = client.models.generate_content(
            model="gemini-nano-banana-2.1",
            contents=contents,
            config=cfg
        )
        if res.candidates:
            for part in res.candidates[0].content.parts:
                if getattr(part, "inline_data", None) and part.inline_data.data:
                    with open(output_path, "wb") as f:
                        f.write(part.inline_data.data)
                    return True
    except Exception as e:
        print(f"[!] Gemini Nano Banana 시도 실패: {e}")

    # 2순위: Gemini 3.1 Flash Image
    try:
        cfg = types.GenerateContentConfig(response_modalities=["IMAGE"])
        res = client.models.generate_content(
            model="gemini-3.1-flash-image",
            contents=prompt,
            config=cfg
        )
        if res.candidates:
            for part in res.candidates[0].content.parts:
                if getattr(part, "inline_data", None) and part.inline_data.data:
                    with open(output_path, "wb") as f:
                        f.write(part.inline_data.data)
                    return True
    except Exception as e:
        print(f"[!] Gemini 3.1 Flash Image 시도 실패: {e}")
        
    raise RuntimeError("Gemini 이미지 모델로부터 이미지를 수신하지 못했습니다.")

def run_crop_script(folder_path, is_faction=False):
    """생성된 종합 에셋 시트를 9:16 개별 에셋으로 스마트 분할"""
    crop_script = os.path.join(
        PROJECT_ROOT, ".agents", "skills",
        "faction-shorts-studio" if is_faction else "product-shorts-studio",
        "scripts", "crop_asset_sheet.py"
    )
    if not os.path.exists(crop_script):
        crop_script = os.path.join(PROJECT_ROOT, ".agents", "skills", "product-shorts-studio", "scripts", "crop_asset_sheet.py")
        
    cmd = [sys.executable, crop_script, folder_path]
    res = subprocess.run(cmd, capture_output=True, text=True)
    print(res.stdout)
    if res.returncode != 0:
        print(f"[!] 크롭 스크립트 경고: {res.stderr}")
    return res.returncode == 0

def extract_prompts_from_file(prompts_file):
    """prompts.md에서 6개 컷별 프롬프트를 정밀 추출"""
    if not os.path.exists(prompts_file):
        return []
    with open(prompts_file, "r", encoding="utf-8") as f:
        text = f.read()

    # 정규식을 통한 다양한 Cut 헤더 분할 (### Cut 1, Cut 1:, - Cut 1, 비트 1 등)
    pattern = r'(?:^|\n)(?:#{1,4}\s*)?(?:\*{1,2})?(?:Cut|비트|컷)\s*\d+[^:\n]*[:\)]?\s*'
    splits = re.split(pattern, text, flags=re.IGNORECASE)
    prompts = [s.strip() for s in splits if s.strip()]
    return prompts

def get_product_name_from_plan(folder_path):
    """plan.md에서 실제 제품명을 추출 (폴더 타임스탬프 대체)"""
    plan_path = os.path.join(folder_path, "plan.md")
    if os.path.exists(plan_path):
        with open(plan_path, "r", encoding="utf-8") as f:
            plan_text = f.read()
        m = re.search(r'name:\s*["\']?([^"\']+)["\']?', plan_text)
        if m:
            return m.group(1).strip()
        m_title = re.search(r'#\s*(.+)', plan_text)
        if m_title:
            return m_title.group(1).replace("기획안", "").replace("쇼핑쇼츠", "").strip()
    return "Commercial Tech Product"

def batch_generate_images(folder_path, engine="gemini", mode="1x3_sheets", custom_prompts=None, progress_callback=None):
    """
    쇼츠 영상용 에셋 일괄 생성:
    - mode="1x3_sheets": 1x3 가로 에셋 시트 2장(총 6컷) 생성 후 자동 9:16 크롭
    - mode="direct_cuts": 6개 씬 개별 9:16 실사 이미지 직접 생성
    """
    assets_dir = os.path.join(folder_path, "assets")
    os.makedirs(assets_dir, exist_ok=True)
    
    # 실물 레퍼런스 이미지 자동 감지
    ref_image_path = None
    ref_candidates = [
        os.path.join(assets_dir, "ref_cut1.png"),
        os.path.join(assets_dir, "ref_cut1.jpg"),
        os.path.join(assets_dir, "ref_cut1.jpeg"),
    ]
    for cand in ref_candidates:
        if os.path.exists(cand):
            ref_image_path = cand
            break
    if not ref_image_path:
        wildcards = glob.glob(os.path.join(assets_dir, "ref*.*"))
        if wildcards:
            ref_image_path = wildcards[0]
            
    if ref_image_path:
        print(f"[*] 감지된 실물 제품 사진: {ref_image_path}")

    # 대본 및 프롬프트 파일 파싱
    prompts_file = os.path.join(folder_path, "prompts.md")
    
    prompt_items = []
    if custom_prompts and isinstance(custom_prompts, list):
        prompt_items = custom_prompts
    elif os.path.exists(prompts_file):
        prompt_items = extract_prompts_from_file(prompts_file)

    # 기본 프롬프트 폴백 (폴더명 대신 실제 제품명 기반)
    if len(prompt_items) < 6:
        product_name = get_product_name_from_plan(folder_path)
        base_subject = f"Commercial product photography of {product_name}, ultra realistic, 8k, pristine studio lighting, highly detailed"
        prompt_items = [
            f"{base_subject}, opening hero result shot, pristine condition, sharp focus",
            f"{base_subject}, contrasting before scene, problem depiction, subtle tension",
            f"{base_subject}, clean hero shot held by hands, modern minimal background",
            f"{base_subject}, close-up action demonstration, functioning in real use",
            f"{base_subject}, proof of result, crisp macro details, satisfying result",
            f"{base_subject}, final loop ending anchor shot, packshot on podium"
        ]

    generated_files = []

    if mode == "1x3_sheets":
        # 1행 3열 16:9 가로 시트 2장 생성 (총 6컷)
        # Sheet 1: Cut 1, 2, 3
        # Sheet 2: Cut 4, 5, 6
        sheets = [
            ("asset_sheet_1.jpg", [prompt_items[0], prompt_items[1], prompt_items[2]]),
            ("asset_sheet_2.jpg", [prompt_items[3], prompt_items[4], prompt_items[5]])
        ]
        
        for idx, (sheet_name, cut_prompts) in enumerate(sheets):
            if progress_callback:
                progress_callback(idx + 1, len(sheets), f"에셋 시트 {idx+1}/2 생성 중...")
                
            combined_prompt = (
                "A clean 1x3 commercial photographic contact sheet, horizontal 16:9 canvas divided into exactly 3 equal vertical panels side by side. "
                "Pure authentic photography, commercial product lighting, realistic texture, no text, no captions. "
                f"Panel 1: {cut_prompts[0]}. "
                f"Panel 2: {cut_prompts[1]}. "
                f"Panel 3: {cut_prompts[2]}."
            )
            out_sheet_path = os.path.join(folder_path, sheet_name)
            
            print(f"[*] [{engine.upper()}] {sheet_name} 생성 중...")
            if engine == "gemini":
                try:
                    generate_via_gemini_imagen(combined_prompt, out_sheet_path, aspect_ratio="16:9", ref_image_path=ref_image_path)
                except Exception as e:
                    print(f"[!] Gemini Imagen 실패, FLUX로 대체: {e}")
                    generate_via_pollinations(combined_prompt, out_sheet_path, width=1280, height=720)
            else:
                generate_via_pollinations(combined_prompt, out_sheet_path, width=1280, height=720)
                
            generated_files.append(out_sheet_path)

        # 자동 9:16 슬라이스 크롭 실행
        if progress_callback:
            progress_callback(len(sheets), len(sheets), "1080x1920 9:16 개별 에셋으로 스마트 크롭 중...")
            
        print("[*] crop_asset_sheet.py 실행하여 9:16 개별 컷 분할...")
        run_crop_script(folder_path)
        
    else:
        # direct_cuts: 6개 컷 9:16 직접 생성
        for idx, prompt_text in enumerate(prompt_items[:6]):
            cut_num = idx + 1
            if progress_callback:
                progress_callback(cut_num, 6, f"컷 {cut_num}/6 이미지 생성 중...")
                
            cut_filename = f"cut{cut_num}_9_16.jpg"
            out_cut_path = os.path.join(assets_dir, cut_filename)
            
            clean_prompt = f"Vertical 9:16 mobile aspect ratio commercial product shot, {prompt_text}, commercial lighting, sharp focus, 8k, professional"
            
            print(f"[*] [{engine.upper()}] {cut_filename} 생성 중...")
            if engine == "gemini":
                try:
                    generate_via_gemini_imagen(clean_prompt, out_cut_path, aspect_ratio="9:16", ref_image_path=ref_image_path)
                except Exception:
                    generate_via_pollinations(clean_prompt, out_cut_path, width=576, height=1024)
            else:
                generate_via_pollinations(clean_prompt, out_cut_path, width=576, height=1024)
                
            generated_files.append(out_cut_path)
            time.sleep(1)

    print("[+] 모든 컷 이미지 일괄 생성 완료!")
    return generated_files

