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

def generate_via_gemini_imagen(prompt, output_path, aspect_ratio="9:16", ref_image_path=None):
    """Google Gemini 멀티모달 이미지 생성 (GEMINI_API_KEY 필요, 실물 사진 레퍼런스 주입)"""
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        raise ValueError("GEMINI_API_KEY가 설정되지 않았습니다.")
        
    from google import genai
    from google.genai import types
    from PIL import Image
    client = genai.Client(api_key=gemini_key)
    
    ratio_desc = "horizontal 16:9 widescreen composition" if aspect_ratio == "16:9" else "vertical 9:16 mobile shorts composition"
    full_prompt = (
        f"Commercial advertising product photography of the EXACT same product shown in the reference image. "
        f"{prompt}, {ratio_desc}, ultra photorealistic, pristine studio lighting, sharp focus, 8k resolution, authentic photography, no text, no watermark."
    )
    
    contents = [full_prompt]
    if ref_image_path and os.path.exists(ref_image_path):
        try:
            ref_img = Image.open(ref_image_path)
            contents = [ref_img, full_prompt]
            print(f"[*] 실물 레퍼런스 사진 주입 완료: {os.path.basename(ref_image_path)}")
        except Exception as ie:
            print(f"[!] 레퍼런스 사진 로드 실패: {ie}")

    cfg = types.GenerateContentConfig(response_modalities=["IMAGE"])
    
    for model_name in ["gemini-2.5-flash-image", "gemini-3.1-flash-image-preview", "gemini-3.1-flash-lite-image"]:
        try:
            print(f"[*] Gemini 이미지 모델 호출 중 ({model_name})...")
            res = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=cfg
            )
            if res.candidates:
                for part in res.candidates[0].content.parts:
                    if getattr(part, "inline_data", None) and part.inline_data.data:
                        with open(output_path, "wb") as f:
                            f.write(part.inline_data.data)
                        
                        # 9:16 캔버스 패딩 보정
                        try:
                            img = Image.open(output_path)
                            w, h = img.size
                            if aspect_ratio == "9:16" and (w != 1080 or h != 1920):
                                target_w, target_h = 1080, 1920
                                canvas = Image.new("RGB", (target_w, target_h), (255, 255, 255))
                                scale = min(target_w / w, target_h / h)
                                nw, nh = int(w * scale), int(h * scale)
                                resized = img.resize((nw, nh), Image.LANCZOS)
                                canvas.paste(resized, ((target_w - nw) // 2, (target_h - nh) // 2))
                                canvas.save(output_path, quality=95)
                        except Exception:
                            pass
                        print(f"[+] [{model_name}] 실물 레퍼런스 반영 이미지 생성 성공 -> {output_path}")
                        return True
        except Exception as e:
            print(f"[!] {model_name} 호출 오류: {e}")
            
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

def sync_sequential_images(folder_path):
    """
    프로젝트 내 생성된 6컷 이미지를 압축 없이 순차 파일명(01_Cut1_Hook.jpg ~ 06_Cut6_CTA.jpg)으로
    하부 에셋 및 이미지 폴더(assets/, images/)에 배치/동기화합니다.
    """
    import shutil
    assets_dir = os.path.join(folder_path, "assets")
    images_dir = os.path.join(folder_path, "images")
    os.makedirs(assets_dir, exist_ok=True)
    os.makedirs(images_dir, exist_ok=True)

    cut_map = [
        ("cut1_9_16.jpg", "01_Cut1_Hook.jpg"),
        ("cut2_9_16.jpg", "02_Cut2_Before.jpg"),
        ("cut3_9_16.jpg", "03_Cut3_Hero.jpg"),
        ("cut4_9_16.jpg", "04_Cut4_Action.jpg"),
        ("cut5_9_16.jpg", "05_Cut5_Proof.jpg"),
        ("cut6_9_16.jpg", "06_Cut6_CTA.jpg")
    ]
    synced = []
    for src_name, dst_name in cut_map:
        sp = os.path.join(assets_dir, src_name)
        if os.path.exists(sp):
            for target_dir in (assets_dir, images_dir):
                dp = os.path.join(target_dir, dst_name)
                if not os.path.exists(dp) or os.path.getmtime(sp) > os.path.getmtime(dp):
                    shutil.copyfile(sp, dp)
            synced.append(os.path.join(assets_dir, dst_name))
    return synced

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

    # Gemini의 경우 실물 레퍼런스 멀티모달 주입을 위해 6컷 개별 정밀 생성을 기본 적용
    if mode == "1x3_sheets" and engine != "gemini":
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
        
        # 컷 분할 완료 후 임시 1x3 시트 파일 자동 삭제
        for s_path in glob.glob(os.path.join(folder_path, "asset_sheet*.*")):
            try:
                os.remove(s_path)
            except Exception:
                pass
                
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

    # 순차 파일명(01_Cut1_Hook.jpg ~ 06_Cut6_CTA.jpg)으로 assets/ 및 images/ 폴더 동기화
    sync_sequential_images(folder_path)

    print("[+] 모든 컷 이미지 일괄 생성 및 순차 에셋 동기화 완료!")
    return generated_files

