import os
import sys
import json
import shutil
import time
import subprocess
import glob
import asyncio
import argparse
import requests
from dotenv import load_dotenv

# 환경 변수 로드 (.env)
load_dotenv()

# 프로젝트 루트 및 레퍼런스 설정
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", ".."))
REF_AUDIO_PATH = os.path.join(PROJECT_ROOT, "reference_voice.mp3")
REF_TEXT = "안녕하세요 여러분. 반갑습니다. 오늘도 저희 채널을 찾아주셔서 감사합니다. 영상이 도움되셨다면 구독과 좋아요를 눌러주세요."

# 팩션 썰쇼츠 전용 기본값 (1.5배속)
DEFAULT_ENGINE = os.getenv("TTS_ENGINE", "edge").lower()
DEFAULT_EDGE_VOICE = os.getenv("TTS_VOICE", "ko-KR-SunHiNeural")
DEFAULT_GEMINI_VOICE = os.getenv("TTS_VOICE", "Kore") if os.getenv("TTS_VOICE") in ["Kore", "Puck", "Charon", "Fenrir", "Aoede"] else "Kore"
DEFAULT_SPEED_RATE = 1.5
OUTPUT_FILENAME = "output_1.5x.wav"
QWEN_BASE_URL = "http://127.0.0.1:7860"
QWEN_API_PREFIX = "/gradio_api"

def change_speed(input_file, output_file, rate=DEFAULT_SPEED_RATE):
    """FFmpeg를 사용하여 오디오 배속 변환 (샘플레이트 24000Hz 표준화)"""
    cmd = [
        "ffmpeg", "-i", input_file,
        "-filter:a", f"atempo={rate}",
        "-ar", "24000",
        output_file, "-y"
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

# -------------------------------------------------------------
# 1. Edge-TTS 엔진 (로컬/무료/고속)
# -------------------------------------------------------------
async def _run_edge_tts_async(text, temp_file, voice):
    import edge_tts
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(temp_file)

def generate_edge_tts(text, temp_file, voice=DEFAULT_EDGE_VOICE):
    print(f"[*] [Edge-TTS] 썰쇼츠 음성 합성 시작 (보이스: {voice})...")
    asyncio.run(_run_edge_tts_async(text, temp_file, voice))
    print("[+] [Edge-TTS] 원본 오디오 생성 완료")

# -------------------------------------------------------------
# 2. Gemini TTS 엔진 (Google GenAI)
# -------------------------------------------------------------
def generate_gemini_tts(text, temp_file, voice=DEFAULT_GEMINI_VOICE, model="gemini-3.8-flash-tts"):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY가 설정되지 않았습니다.\n"
            ".env 파일에 GEMINI_API_KEY=your_key 를 등록하시거나, "
            "--engine edge 옵션(무료/즉시사용)을 이용하세요."
        )
    
    print(f"[*] [Gemini-TTS] Google GenAI 호출 중 (모델: {model}, 보이스: {voice})...")
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    config = types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name=voice
                )
            )
        )
    )
    # 순수 대본 텍스트만 전달 (TTS 전용 모델은 안내 문구까지 소리 내어 읽으므로 대본 본문만 전달해야 함)
    clean_text = text.strip()
    response = client.models.generate_content(
        model=model,
        contents=clean_text,
        config=config
    )
    
    audio_bytes = None
    if response.candidates:
        for part in response.candidates[0].content.parts:
            if getattr(part, "inline_data", None) and part.inline_data.data:
                audio_bytes = part.inline_data.data
                break
                
    if not audio_bytes:
        raise RuntimeError("Gemini API로부터 오디오 데이터를 수신하지 못했습니다.")
        
    with open(temp_file, "wb") as f:
        f.write(audio_bytes)
    print("[+] [Gemini-TTS] 원본 오디오 생성 완료")

# -------------------------------------------------------------
# 3. Qwen3-TTS 엔진 (로컬 Gradio 서버 포트 7860)
# -------------------------------------------------------------
def upload_qwen_file(file_path):
    url = f"{QWEN_BASE_URL}{QWEN_API_PREFIX}/upload"
    with open(file_path, "rb") as f:
        files = {"files": f}
        response = requests.post(url, files=files, timeout=10)
    if response.status_code == 200:
        result = response.json()
        return {"path": result[0], "meta": {"_type": "gradio.FileData"}}
    raise Exception(f"파일 업로드 실패: {response.text}")

def call_qwen_api(api_name, data):
    url = f"{QWEN_BASE_URL}{QWEN_API_PREFIX}/call{api_name}"
    payload = {"data": data}
    response = requests.post(url, json=payload, timeout=10)
    if response.status_code == 200:
        return response.json()["event_id"]
    raise Exception(f"API 호출 시작 실패 ({api_name}): {response.text}")

def get_qwen_result(api_name, event_id):
    url = f"{QWEN_BASE_URL}{QWEN_API_PREFIX}/call{api_name}/{event_id}"
    response = requests.get(url, stream=True, timeout=120)
    current_event = None
    for line in response.iter_lines():
        if line:
            line_str = line.decode('utf-8').strip()
            if line_str.startswith("event:"):
                current_event = line_str[6:].strip()
            elif line_str.startswith("data:"):
                data_str = line_str[5:].strip()
                if current_event == "complete":
                    return json.loads(data_str)
                if current_event == "error":
                    raise Exception(f"API 에러 이벤트: {data_str}")
    raise Exception("결과를 찾지 못했습니다.")

def generate_qwen_tts(text, temp_file):
    print(f"[*] [Qwen3-TTS] 로컬 서버({QWEN_BASE_URL}) 연결 확인 중...")
    try:
        r = requests.get(QWEN_BASE_URL, timeout=3)
        if r.status_code != 200:
            raise Exception("서버 비정상")
    except Exception as e:
        raise ConnectionError(
            f"로컬 Qwen3-TTS 서버({QWEN_BASE_URL})에 연결할 수 없습니다.\n"
            "Pinokio를 실행하거나, --engine edge 옵션을 사용해 Edge-TTS를 이용하세요."
        ) from e

    if not os.path.exists(REF_AUDIO_PATH):
        raise FileNotFoundError(f"레퍼런스 오디오 파일을 찾을 수 없습니다: {REF_AUDIO_PATH}")
        
    print("[*] 레퍼런스 오디오 업로드 중...")
    ref_file_info = upload_qwen_file(REF_AUDIO_PATH)
    ref_text = REF_TEXT

    print("[*] Voice Clone 생성 중...")
    clone_data = [ref_file_info, ref_text, text, "Korean", False, "1.7B", 200, 0.0, -1]
    event_id = call_qwen_api("/generate_voice_clone", clone_data)
    result_data = get_qwen_result("/generate_voice_clone", event_id)
    
    audio_file_info = result_data[0]
    if not audio_file_info:
        raise Exception("Qwen TTS 생성 실패")

    remote_path = audio_file_info.get("path")
    audio_url = f"{QWEN_BASE_URL}{QWEN_API_PREFIX}/file={remote_path}"
    
    r = requests.get(audio_url, stream=True, timeout=30)
    if r.status_code == 200:
        with open(temp_file, 'wb') as f:
            shutil.copyfileobj(r.raw, f)
        print("[+] [Qwen3-TTS] 원본 오디오 생성 완료")
    else:
        raise Exception(f"오디오 다운로드 실패: {r.status_code}")

# -------------------------------------------------------------
# 메인 실행 로직
# -------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="팩션 썰쇼츠 TTS 생성 (Edge-TTS / Gemini-TTS / Qwen3-TTS 지원)")
    parser.add_argument("folder_path", nargs="?", default=None, help="대상 폴더 경로 (기본값: outputs 최신 폴더)")
    parser.add_argument("--engine", choices=["edge", "gemini", "qwen"], default=None, help="TTS 엔진 (기본: .env의 TTS_ENGINE 또는 edge)")
    parser.add_argument("--voice", default=None, help="보이스 이름 (Edge: ko-KR-SunHiNeural 등, Gemini: Kore, Puck 등)")
    parser.add_argument("--rate", type=float, default=DEFAULT_SPEED_RATE, help="배속 (기본값: 1.5)")
    
    args = parser.parse_args()
    
    outputs_dir = os.path.join(PROJECT_ROOT, "outputs")
    folder_path = None

    if args.folder_path:
        arg_path = args.folder_path
        if os.path.exists(arg_path):
            folder_path = arg_path
        elif os.path.exists(os.path.join(outputs_dir, arg_path)):
            folder_path = os.path.join(outputs_dir, arg_path)
        else:
            print(f"에러: 지정한 폴더를 찾을 수 없습니다: {arg_path}")
            return
    else:
        if not os.path.exists(outputs_dir):
            print("에러: outputs 디렉토리가 존재하지 않습니다.")
            return
            
        subdirs = [os.path.join(outputs_dir, d) for d in os.listdir(outputs_dir) if os.path.isdir(os.path.join(outputs_dir, d))]
        target_dirs = []
        for sd in subdirs:
            md_files = glob.glob(os.path.join(sd, "*.md"))
            has_output = os.path.exists(os.path.join(sd, OUTPUT_FILENAME))
            if md_files and not has_output:
                target_dirs.append(sd)
                
        if not target_dirs:
            if subdirs:
                subdirs.sort(key=lambda x: os.path.getmtime(x), reverse=True)
                folder_path = subdirs[0]
                print(f"[*] 미처리 폴더가 없어 가장 최근 수정된 폴더를 선택했습니다: {folder_path}")
            else:
                print("사용법: python generate_tts.py [폴더경로] [--engine edge|gemini|qwen] [--rate 1.5]")
                return
        else:
            target_dirs.sort(key=lambda x: os.path.getmtime(x), reverse=True)
            folder_path = target_dirs[0]
            print(f"[*] 최신 미처리 폴더를 탐색했습니다: {folder_path}")

    # 대본 파일 탐색
    script_path = None
    priority_names = ["script.md", "대본.md"]
    for name in priority_names:
        candidate = os.path.join(folder_path, name)
        if os.path.exists(candidate):
            script_path = candidate
            break
            
    if not script_path:
        script_candidates = glob.glob(os.path.join(folder_path, "*script*.md")) + glob.glob(os.path.join(folder_path, "*대본*.md"))
        if script_candidates:
            script_path = script_candidates[0]
            
    if not script_path:
        md_files = glob.glob(os.path.join(folder_path, "*.md"))
        non_script = ["asset_sheet.md", "plan.md", "prompts.md", "publish_kit.md", "README.md"]
        filtered = [f for f in md_files if os.path.basename(f) not in non_script]
        if filtered:
            script_path = filtered[0]
        elif md_files:
            script_path = md_files[0]

    if not script_path:
        print(f"에러: {folder_path} 내에 대본 MD 파일이 없습니다.")
        return
    
    print(f"[*] 대본 파일 선택됨: {script_path}")
    with open(script_path, 'r', encoding='utf-8') as f:
        script_text = f.read().strip()

    # 엔진 결정
    engine = args.engine or DEFAULT_ENGINE
    if engine not in ["edge", "gemini", "qwen"]:
        engine = "edge"
        
    rate = args.rate
    temp_file = os.path.join(folder_path, "temp_tts_raw.mp3")
    final_wav = os.path.join(folder_path, OUTPUT_FILENAME)

    print(f"[*] 팩션 썰쇼츠 TTS 작업 시작: 엔진={engine}, 목표배속={rate}x")

    try:
        if engine == "edge":
            voice = args.voice or DEFAULT_EDGE_VOICE
            generate_edge_tts(script_text, temp_file, voice=voice)
        elif engine == "gemini":
            voice = args.voice or DEFAULT_GEMINI_VOICE
            generate_gemini_tts(script_text, temp_file, voice=voice)
        elif engine == "qwen":
            generate_qwen_tts(script_text, temp_file)
            
        print(f"[*] 배속 변환 중 ({rate}x) -> {final_wav}...")
        change_speed(temp_file, final_wav, rate=rate)
        
        # 호환성을 위한 복사본 (기본 output_1.5x.wav 외 output.wav 도 보장)
        shutil.copyfile(final_wav, os.path.join(folder_path, "output.wav"))
        
        if os.path.exists(temp_file):
            os.remove(temp_file)
            
        print(f"[+] 최종 오디오 생성 성공: {final_wav}")
        
    except Exception as e:
        if os.path.exists(temp_file):
            os.remove(temp_file)
            
        # qwen이나 gemini 실패 시 edge-tts로 자동 fallback 시도
        if engine != "edge":
            print(f"[!] {engine.upper()} TTS 실패 ({e}). 무료 Edge-TTS로 자동 전환하여 재시도합니다...")
            try:
                generate_edge_tts(script_text, temp_file, voice=DEFAULT_EDGE_VOICE)
                change_speed(temp_file, final_wav, rate=rate)
                shutil.copyfile(final_wav, os.path.join(folder_path, "output.wav"))
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                print(f"[+] Edge-TTS로 최종 오디오 생성 성공: {final_wav}")
                return
            except Exception as fb_err:
                print(f"[!] Edge-TTS Fallback도 실패: {fb_err}")
        print(f"에러: TTS 생성 중 오류 발생: {e}")

if __name__ == "__main__":
    main()
