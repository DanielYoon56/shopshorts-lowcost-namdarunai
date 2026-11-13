import os
import sys
import json
import glob
import time
import math
import shutil
import socket
import subprocess
import re
from datetime import datetime
import streamlit as st
from dotenv import load_dotenv

def is_port_open(port=3000, host="127.0.0.1"):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.4)
            return s.connect_ex((host, port)) == 0
    except Exception:
        return False

# 환경 변수 로드
load_dotenv()

# 경로 설정
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUTS_DIR = os.path.join(PROJECT_ROOT, "outputs")
MY_VIDEO_DIR = os.path.join(PROJECT_ROOT, "my-video")
TTS_GEN_SCRIPT = os.path.join(PROJECT_ROOT, ".agents", "skills", "tts-generate", "scripts", "generate.py")
TTS_FACTION_SCRIPT = os.path.join(PROJECT_ROOT, ".agents", "skills", "faction-shorts-studio", "scripts", "generate_tts.py")
STT_ALIGN_SCRIPT = os.path.join(PROJECT_ROOT, ".agents", "skills", "stt-scene-align", "scripts", "align.py")
RENDER_SCRIPT = os.path.join(PROJECT_ROOT, ".agents", "skills", "remotion-render", "scripts", "render.py")

# 모듈 임포트 (핫 리로드 보장)
import importlib
import ai_researcher
importlib.reload(ai_researcher)
from ai_researcher import run_product_research, save_research_artifacts, ingest_coupang_page, load_coupang_data, run_coupang_ocr
sys.path.insert(0, os.path.dirname(STT_ALIGN_SCRIPT))
from srt_writer import write_srt

import image_generator
importlib.reload(image_generator)
from image_generator import batch_generate_images, sync_sequential_images

# 페이지 기본 설정
st.set_page_config(
    page_title="Lowcost ShopShorts namdarunAi",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 커스텀 스타일: Google AI Studio 스타일 테마
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Google+Sans:wght@400;500;700&family=Roboto:wght@400;500;700&display=swap');

    /* Google AI Studio 기본 테마 */
    html, body, [class*="css"] {
        font-family: 'Google Sans', 'Roboto', -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
    }

    /* 상단 Google AI Studio 네비게이션 헤더 */
    .aistudio-topbar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 10px 18px;
        background: #ffffff;
        border: 1px solid #dadce0;
        border-radius: 12px;
        margin-bottom: 16px;
    }
    @media (prefers-color-scheme: dark) {
        .aistudio-topbar {
            background: #1e1f20;
            border-color: #3c4043;
        }
    }
    .aistudio-brand {
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .aistudio-sparkle {
        font-size: 1.3rem;
        background: linear-gradient(135deg, #4285f4 0%, #9b72cf 50%, #d96570 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        display: inline-block;
        filter: drop-shadow(0 0 6px rgba(66, 133, 244, 0.45));
    }
    .aistudio-brand-title {
        font-size: 1.05rem;
        font-weight: 700;
        letter-spacing: -0.01em;
    }
    .aistudio-slash {
        color: #9aa0a6;
        font-size: 1rem;
        font-weight: 300;
    }
    .aistudio-brand-sub {
        font-size: 0.95rem;
        color: #5f6368;
        font-weight: 500;
    }
    @media (prefers-color-scheme: dark) {
        .aistudio-brand-sub { color: #bdc1c6; }
    }
    .aistudio-chip {
        font-size: 0.72rem;
        font-weight: 600;
        padding: 4px 10px;
        border-radius: 16px;
        background: #e8f0fe;
        color: #1a73e8;
        border: 1px solid #d2e3fc;
    }
    @media (prefers-color-scheme: dark) {
        .aistudio-chip {
            background: #1e2638;
            color: #8ab4f8;
            border-color: #2b3b5e;
        }
    }

    /* Google AI Studio 사이드바 (Run settings) */
    [data-testid="stSidebar"] {
        padding-top: 0.8rem !important;
        background-color: #f8f9fa !important;
        border-right: 1px solid #dadce0 !important;
    }
    @media (prefers-color-scheme: dark) {
        [data-testid="stSidebar"] {
            background-color: #18191a !important;
            border-right: 1px solid #3c4043 !important;
        }
    }
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
        gap: 0.35rem !important;
    }

    .aistudio-sidebar-header {
        display: flex;
        align-items: center;
        gap: 8px;
        padding-bottom: 8px;
        margin-bottom: 8px;
        border-bottom: 1px solid #e8eaed;
    }
    @media (prefers-color-scheme: dark) {
        .aistudio-sidebar-header { border-bottom-color: #303134; }
    }
    .aistudio-sidebar-title {
        font-size: 0.95rem;
        font-weight: 700;
        letter-spacing: -0.01em;
    }
    
    .aistudio-section-header {
        font-size: 0.68rem !important;
        font-weight: 700 !important;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #5f6368;
        margin-top: 8px;
        margin-bottom: 3px;
    }
    @media (prefers-color-scheme: dark) {
        .aistudio-section-header { color: #9aa0a6; }
    }

    /* Google AI Studio 미니 상태 칩 */
    .aistudio-chip-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 5px;
        margin-top: 4px;
        margin-bottom: 6px;
    }
    .aistudio-chip-item {
        display: flex;
        align-items: center;
        gap: 5px;
        padding: 3px 8px;
        border-radius: 12px;
        font-size: 0.72rem;
        font-weight: 500;
        border: 1px solid #dadce0;
        background: #ffffff;
        color: #3c4043;
    }
    @media (prefers-color-scheme: dark) {
        .aistudio-chip-item {
            border-color: #3c4043;
            background: #202124;
            color: #bdc1c6;
        }
    }
    .dot-online {
        width: 6px;
        height: 6px;
        border-radius: 50%;
        background-color: #1e8e3e;
        box-shadow: 0 0 5px rgba(30, 142, 62, 0.5);
    }
    .dot-offline {
        width: 6px;
        height: 6px;
        border-radius: 50%;
        background-color: #d93025;
    }
    .dot-idle {
        width: 6px;
        height: 6px;
        border-radius: 50%;
        background-color: #9aa0a6;
    }

    /* Google Primary Button Style (Google Blue Pill) */
    .stButton > button[kind="primary"], [data-testid="stSidebar"] button {
        background-color: #1a73e8 !important;
        color: #ffffff !important;
        border-radius: 20px !important;
        border: none !important;
        font-weight: 600 !important;
        font-size: 0.82rem !important;
        padding: 0.4rem 0.9rem !important;
        box-shadow: 0 1px 2px rgba(26, 115, 232, 0.25) !important;
        transition: background-color 0.2s, box-shadow 0.2s !important;
    }
    .stButton > button[kind="primary"]:hover, [data-testid="stSidebar"] button:hover {
        background-color: #1557b0 !important;
        box-shadow: 0 2px 6px rgba(26, 115, 232, 0.4) !important;
    }

    /* Google AI Studio 탭 스타일 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px !important;
        border-bottom: 1px solid #dadce0 !important;
    }
    @media (prefers-color-scheme: dark) {
        .stTabs [data-baseweb="tab-list"] {
            border-bottom: 1px solid #3c4043 !important;
        }
    }
    .stTabs [data-baseweb="tab"] {
        padding: 8px 16px !important;
        font-weight: 600 !important;
        font-size: 0.85rem !important;
    }
    .stTabs [aria-selected="true"] {
        color: #1a73e8 !important;
        border-bottom-color: #1a73e8 !important;
    }
    @media (prefers-color-scheme: dark) {
        .stTabs [aria-selected="true"] {
            color: #8ab4f8 !important;
            border-bottom-color: #8ab4f8 !important;
        }
    }

    /* 위젯 간격 축소 및 폰트 촘촘화 */
    [data-testid="stSidebar"] label {
        font-size: 0.77rem !important;
        font-weight: 600 !important;
        color: #3c4043 !important;
        margin-bottom: 1px !important;
    }
    @media (prefers-color-scheme: dark) {
        [data-testid="stSidebar"] label {
            color: #bdc1c6 !important;
        }
    }
    [data-testid="stSidebar"] .stSelectbox, 
    [data-testid="stSidebar"] .stRadio,
    [data-testid="stSidebar"] .stTextInput {
        margin-bottom: 2px !important;
    }
    [data-testid="stSidebar"] div[role="radiogroup"] {
        gap: 2px !important;
    }
    [data-testid="stSidebar"] div[role="radiogroup"] > label {
        padding: 2px 6px !important;
        border-radius: 4px !important;
        margin: 0 !important;
        font-size: 0.76rem !important;
    }
    [data-testid="stSidebar"] div[role="radiogroup"] > label p {
        font-size: 0.76rem !important;
        line-height: 1.25 !important;
    }
    [data-testid="stSidebar"] .stCaption {
        font-size: 0.71rem !important;
        line-height: 1.25 !important;
        color: #5f6368 !important;
        margin-top: 1px !important;
        margin-bottom: 3px !important;
    }
    @media (prefers-color-scheme: dark) {
        [data-testid="stSidebar"] .stCaption { color: #9aa0a6 !important; }
    }
    [data-testid="stSidebar"] hr {
        margin: 6px 0 !important;
        border-color: #e8eaed !important;
    }
    @media (prefers-color-scheme: dark) {
        [data-testid="stSidebar"] hr { border-color: #303134 !important; }
    }
    [data-testid="stSidebar"] .stExpander {
        border: 1px solid #dadce0 !important;
        border-radius: 8px !important;
        background: #ffffff !important;
        margin-top: 3px !important;
        margin-bottom: 3px !important;
    }
    @media (prefers-color-scheme: dark) {
        [data-testid="stSidebar"] .stExpander {
            border-color: #3c4043 !important;
            background: #202124 !important;
        }
    }
    [data-testid="stSidebar"] .stExpander details summary {
        padding: 4px 8px !important;
        font-size: 0.75rem !important;
        font-weight: 600 !important;
    }

    /* 프로젝트 상태 칩 */
    .status-badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 0.76rem; font-weight: 500; }
    .badge-done { background-color: #e6f4ea; color: #137333; border: 1px solid #ceead6; }
    .badge-wait { background-color: #fef7e0; color: #b06000; border: 1px solid #feefc3; }
    .badge-none { background-color: #f1f3f4; color: #5f6368; border: 1px solid #dadce0; }
    @media (prefers-color-scheme: dark) {
        .badge-done { background-color: #132d1e; color: #81c995; border-color: #1e5230; }
        .badge-wait { background-color: #332400; color: #fdd663; border-color: #593e00; }
        .badge-none { background-color: #202124; color: #9aa0a6; border-color: #3c4043; }
    }
</style>

""", unsafe_allow_html=True)

# ------------------------------------------------------------------
# 유틸리티 함수
# ------------------------------------------------------------------
def capcut_input_files(folder_path):
    """CapCut 투입 파일 = 6컷 이미지(순차) + 동영상 클립 + 음성 wav + subtitles.srt (모두 프로젝트 폴더/하부 폴더에 압축 없이 존재).

    - 이미지: 01_Cut1 ~ 06_Cut6 순차 컷 (assets/ 및 images/ 폴더)
    - 동영상: video*.mp4 / scene*.mp4 / background*.mp4 (트랜스코딩 전 원본 *.orig.mp4, 최종 렌더 output.mp4 제외)
    - 음성: Whisper 자막 싱크에 쓴 것과 같은 우선순위 (1.2x → 1.5x → 원본)
    """
    videos = []
    for pattern in ("video*.mp4", "scene*.mp4", "background*.mp4"):
        for p in sorted(glob.glob(os.path.join(folder_path, pattern))):
            if not p.endswith(".orig.mp4") and p not in videos:
                videos.append(p)
    voice = next(
        (os.path.join(folder_path, n) for n in ("output_1.2x.wav", "output_1.5x.wav", "output.wav")
         if os.path.exists(os.path.join(folder_path, n))),
        None,
    )
    srt = os.path.join(folder_path, "subtitles.srt")

    # 순차 이미지 목록
    assets_dir = os.path.join(folder_path, "assets")
    images_dir = os.path.join(folder_path, "images")
    sync_sequential_images(folder_path)
    seq_images = sorted(glob.glob(os.path.join(images_dir, "0[1-6]_Cut*.jpg")))
    if not seq_images:
        seq_images = sorted(glob.glob(os.path.join(assets_dir, "0[1-6]_Cut*.jpg")))
    if not seq_images:
        seq_images = sorted(glob.glob(os.path.join(assets_dir, "cut*_9_16.jpg")))

    return {"videos": videos, "voice": voice, "srt": srt if os.path.exists(srt) else None, "images": seq_images}


def refresh_capcut_files(folder_path):
    """SRT 를 최신 scene_data.json 으로 재생성 (자막을 손으로 고친 경우용). 압축은 하지 않는다."""
    if os.path.exists(os.path.join(folder_path, "scene_data.json")):
        write_srt(folder_path)
    # 예전 방식의 압축 패키지는 오래된 내용이라 혼동을 막기 위해 제거
    old_zip = os.path.join(folder_path, "capcut_package.zip")
    if os.path.exists(old_zip):
        os.remove(old_zip)
    return capcut_input_files(folder_path)

def render_remotion_with_progress(project_path, progress_bar, status_text, extra_args=None, log_area=None):
    """Remotion render.py를 실시간 스트리밍으로 실행하여 Streamlit 진행바에 표시"""
    cmd = [sys.executable, "-u", RENDER_SCRIPT, project_path]
    if extra_args:
        cmd.extend(extra_args)
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        encoding="utf-8",
        errors="replace"
    )
    
    last_pct = 0.0
    last_msg = "렌더링 사전 작업 준비 중..."
    progress_bar.progress(0.0)
    status_text.markdown(f"**⏳ [0%]** {last_msg}")
    
    logs = []
    buffer = ""
    while True:
        char = process.stdout.read(1)
        if not char:
            if buffer:
                line = buffer.strip()
                if line:
                    logs.append(line)
            break
        if char in ("\r", "\n"):
            line = buffer.strip()
            buffer = ""
            if not line:
                continue
            logs.append(line)
            if log_area:
                log_area.text("\n".join(logs[-6:]))
            
            # PROGRESS 이벤트 파싱 (PROGRESS: 0.45 | 메시지)
            if line.startswith("PROGRESS:"):
                try:
                    parts = line[9:].split("|", 1)
                    pct = max(0.0, min(1.0, float(parts[0].strip())))
                    msg = parts[1].strip() if len(parts) > 1 else ""
                    if pct >= last_pct:
                        last_pct = pct
                        last_msg = msg
                        progress_bar.progress(last_pct)
                        status_text.markdown(f"**🎬 [{int(last_pct * 100)}%]** {last_msg}")
                except Exception:
                    pass
            else:
                # Fallback: Remotion CLI의 원시 출력에서도 프레임 진행률 탐색
                m_frame = re.search(r'(?:Rendered\s+)?(\d+)\s*/\s*(\d+)', line, re.IGNORECASE)
                if m_frame:
                    try:
                        cur_f = int(m_frame.group(1))
                        tot_f = int(m_frame.group(2))
                        if tot_f > 0 and cur_f <= tot_f:
                            pct = 0.25 + (cur_f / tot_f) * 0.65
                            if pct > last_pct:
                                last_pct = pct
                                last_msg = f"프레임 렌더링 중: {cur_f}/{tot_f} ({int((cur_f/tot_f)*100)}%)"
                                progress_bar.progress(last_pct)
                                status_text.markdown(f"**🎬 [{int(last_pct * 100)}%]** {last_msg}")
                    except Exception:
                        pass
        else:
            buffer += char
            
    returncode = process.wait()
    if returncode == 0:
        progress_bar.progress(1.0)
        status_text.markdown("**✅ [100%]** 9:16 비디오 렌더링 완료!")
        return True, "\n".join(logs)
    else:
        return False, "\n".join(logs)

def get_project_folders():
    if not os.path.exists(OUTPUTS_DIR):
        os.makedirs(OUTPUTS_DIR, exist_ok=True)
    dirs = [d for d in os.listdir(OUTPUTS_DIR) if os.path.isdir(os.path.join(OUTPUTS_DIR, d))]
    dirs.sort(key=lambda d: os.path.getmtime(os.path.join(OUTPUTS_DIR, d)), reverse=True)
    return dirs

def check_project_status(folder_path):
    has_script = bool(glob.glob(os.path.join(folder_path, "*script*.md")) or os.path.exists(os.path.join(folder_path, "대본.md")))
    has_audio = bool(glob.glob(os.path.join(folder_path, "*.wav")))
    has_scenes = os.path.exists(os.path.join(folder_path, "scene_data.json"))
    has_images = bool(
        glob.glob(os.path.join(folder_path, "assets", "cut*.jpg"))
        or glob.glob(os.path.join(folder_path, "assets", "0[1-6]_Cut*.jpg"))
        or glob.glob(os.path.join(folder_path, "images", "0[1-6]_Cut*.jpg"))
        or os.path.exists(os.path.join(folder_path, "asset_sheet_1.jpg"))
    )
    has_video = os.path.exists(os.path.join(folder_path, "output.mp4"))
    return {
        "script": has_script,
        "audio": has_audio,
        "scenes": has_scenes,
        "images": has_images,
        "video": has_video
    }

def sync_remotion_active_project(folder_path):
    """활성 프로젝트 폴더의 에셋과 설정(active_props.json)을 Remotion Studio용으로 자동 동기화"""
    if not folder_path or not os.path.exists(folder_path):
        return
    folder_name = os.path.basename(folder_path)
    
    # 1. scene_data.json 확인
    scene_data_path = os.path.join(folder_path, "scene_data.json")
    scenes = []
    duration_in_frames = 600
    if os.path.exists(scene_data_path):
        try:
            with open(scene_data_path, "r", encoding="utf-8") as f:
                scenes = json.load(f)
            if scenes:
                max_end = max(s.get("end", 0.0) for s in scenes)
                duration_in_frames = max(1, int(math.ceil(max_end * 30)))
        except Exception:
            pass

    # 2. 오디오 파일 확인
    audio_file = "output_1.2x.wav"
    for cand in ["output_1.2x.wav", "output.wav", "output_1.5x.wav"]:
        if os.path.exists(os.path.join(folder_path, cand)):
            audio_file = cand
            break

    # 2-1. 6개 컷 비디오 확인 (Cut 1 ~ Cut 6)
    cut_videos_info = []
    for i in range(1, 7):
        p_cands = [f"cut{i}.mp4", f"0{i}_Cut{i}.mp4", f"cut_{i}.mp4", f"Cut{i}.mp4", f"cut{i}.mov", f"0{i}_Cut{i}.mov"]
        found_name = next((c for c in p_cands if os.path.exists(os.path.join(folder_path, c))), None)
        cut_videos_info.append({
            "cutIndex": i,
            "hasVideo": bool(found_name),
            "fileName": found_name
        })

    # 3. my-video/src/active_props.json 갱신
    active_props = {
        "folderName": folder_name,
        "audioFileName": audio_file,
        "durationInFrames": duration_in_frames,
        "sceneData": scenes
    }
    if any(c["hasVideo"] for c in cut_videos_info):
        active_props["cutVideos"] = cut_videos_info
    src_props_path = os.path.join(MY_VIDEO_DIR, "src", "active_props.json")
    try:
        with open(src_props_path, "w", encoding="utf-8") as f:
            json.dump(active_props, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    # 4. my-video/public/outputs/<folder_name> 에셋 동기화
    public_target_dir = os.path.join(MY_VIDEO_DIR, "public", "outputs", folder_name)
    os.makedirs(public_target_dir, exist_ok=True)
    for root, dirs, files in os.walk(folder_path):
        rel = os.path.relpath(root, folder_path)
        if rel.startswith("remotion_") or "node_modules" in rel:
            continue
        dest_dir = os.path.join(public_target_dir, rel) if rel != "." else public_target_dir
        os.makedirs(dest_dir, exist_ok=True)
        for f in files:
            if f.endswith(".zip") or f.endswith(".tmp") or "transcode_temp" in f:
                continue
            s_f = os.path.join(root, f)
            d_f = os.path.join(dest_dir, f)
            if not os.path.exists(d_f) or os.path.getmtime(s_f) > os.path.getmtime(d_f):
                try:
                    shutil.copy2(s_f, d_f)
                except Exception:
                    pass

# ------------------------------------------------------------------
# 사이드바: 프로젝트 탐색 & 환경 설정 상태
# ------------------------------------------------------------------
with st.sidebar:
    # Google AI Studio 사이드바 헤더 (Run settings)
    st.markdown("""
    <div class="aistudio-sidebar-header">
        <span class="aistudio-sparkle">✦</span>
        <span class="aistudio-sidebar-title">Run settings</span>
    </div>
    """, unsafe_allow_html=True)

    folders = get_project_folders()
    
    st.markdown('<div class="aistudio-section-header">WORKSPACE</div>', unsafe_allow_html=True)
    if folders:
        target_folder = st.session_state.get("selected_project_folder")
        default_idx = folders.index(target_folder) if (target_folder and target_folder in folders) else 0
        selected_folder = st.selectbox(
            "작업 폴더",
            folders,
            index=default_idx,
            key="main_project_selector",
            label_visibility="collapsed",
            help="outputs 디렉토리 내의 프로젝트 폴더입니다."
        )
        st.session_state["selected_project_folder"] = selected_folder
    else:
        st.info("현재 작업 폴더가 없습니다. 아래에서 새로 생성하세요.")
        selected_folder = None

    # 새 프로젝트 폴더 생성
    with st.expander("➕ 새 프로젝트 생성"):
        default_new_name = datetime.now().strftime("%y%m%d_%H%M")
        new_folder_name = st.text_input("새 폴더명", value=default_new_name, key="new_folder_name_input", label_visibility="collapsed")
        if st.button("폴더 생성", use_container_width=True):
            clean_name = new_folder_name.strip()
            if clean_name:
                new_path = os.path.join(OUTPUTS_DIR, clean_name)
                os.makedirs(new_path, exist_ok=True)
                os.makedirs(os.path.join(new_path, "assets"), exist_ok=True)
                os.makedirs(os.path.join(new_path, "images"), exist_ok=True)
                st.session_state["selected_project_folder"] = clean_name
                st.session_state["main_project_selector"] = clean_name
                st.session_state["_last_loaded_project"] = clean_name
                st.session_state.pop("coupang_ingested", None)
                st.session_state.pop("last_uploaded_capcut_sig", None)
                st.session_state.pop("uploaded_video_just_now", None)
                st.success(f"생성 완료: {clean_name}")
                st.rerun()

    st.markdown("<hr/>", unsafe_allow_html=True)
    st.markdown('<div class="aistudio-section-header">STORY & SCRIPT STYLE</div>', unsafe_allow_html=True)

    # 1) 대본 스타일
    sidebar_script_style_choice = st.selectbox(
        "사용할 대본 스토리텔링 스타일",
        options=[
            "💡 문제공감 & 해결형 (일상 공감, 기본 추천)",
            "📖 비하인드 썰 & 스토리텔링형 (도파민/썰)",
            "🔍 내돈내산 솔직 리뷰형 (3개월 찐후기)",
            "⚡ 초고속 결과선공개형 (3초 즉시 증명)",
            "🚨 충격 경고 & 반전형 (호기심/반전 솔루션)"
        ],
        index=0,
        key="sidebar_script_style_select",
        label_visibility="collapsed",
        help="• 문제공감: 일상 속 불편함에 깊이 공감하고 제품 해결책 제시\n• 비하인드 썰: 창업자 비화, 품절 대란 등 도파민 넘치는 썰로 몰입\n• 내돈내산 리뷰: 찐 소비자의 솔직 담백한 리얼 리뷰\n• 초고속 결과선공개: 3초 만에 결과를 선공개하고 핵심 기능 속도감 있게 전달\n• 충격 경고: 강렬한 경고성 후킹 후 상식을 깨는 반전 솔루션"
    )
    if "문제공감" in sidebar_script_style_choice:
        selected_script_style = "empathy"
        st.caption("✨ 일상 불편함 공감 ➔ 즉각적인 제품 해결책 제시")
    elif "비하인드" in sidebar_script_style_choice:
        selected_script_style = "story"
        st.caption("✨ 창업 비화/품절 대란 등 도파민 썰로 극대화")
    elif "내돈내산" in sidebar_script_style_choice:
        selected_script_style = "review"
        st.caption("✨ 3개월 찐사용자의 과장 없는 솔직 리얼 보이스")
    elif "결과선공개" in sidebar_script_style_choice:
        selected_script_style = "fast_usp"
        st.caption("✨ 3초 즉시 결과 증명 + 빠른 템포의 핵심 장점")
    else:
        selected_script_style = "warning"
        st.caption("✨ '아직도 모르셨다면 당장 멈추세요' 경고 ➔ 반전")
    st.session_state["global_script_style"] = selected_script_style

    st.markdown("<hr/>", unsafe_allow_html=True)
    st.markdown('<div class="aistudio-section-header">GENERATION ENGINES</div>', unsafe_allow_html=True)

    # 2) AI 이미지 엔진
    st.markdown('<div style="font-size:0.75rem; font-weight:600; color:#5f6368; margin-top:3px; margin-bottom:2px;">IMAGE MODEL</div>', unsafe_allow_html=True)
    g_key = os.getenv("GEMINI_API_KEY")
    hf_token = os.getenv("HF_TOKEN")
    sf_key = os.getenv("SILICONFLOW_API_KEY")

    sidebar_img_choice = st.radio(
        "사용할 AI 이미지 엔진",
        options=[
            "Google Gemini (실물 사진 레퍼런스, 추천)",
            "Hugging Face FLUX (HF 무료 토큰)",
            "SiliconFlow FLUX (2천만 무료 토큰)"
        ],
        index=0,
        key="sidebar_img_engine_radio",
        label_visibility="collapsed",
        help="• Google Gemini: 첨부된 실제 상품 사진의 외형을 100% 반영하여 6컷 정밀 생성 (추천)\n• Hugging Face: HF 무료 토큰으로 FLUX.1-schnell 생성\n• SiliconFlow: 가입 즉시 2천만 토큰 무료 제공"
    )
    if "Gemini" in sidebar_img_choice:
        selected_img_engine = "gemini"
    elif "Hugging" in sidebar_img_choice:
        selected_img_engine = "hf"
    else:
        selected_img_engine = "siliconflow"
    st.session_state["global_image_engine"] = selected_img_engine

    if selected_img_engine == "gemini":
        st.caption("✨ 실물 사진 1:1 레퍼런스 9:16 정밀 생성" if (g_key and len(g_key) > 5) else "⚠️ .env에 GEMINI_API_KEY 필요")
    elif selected_img_engine == "hf":
        st.caption("🤗 Hugging Face Serverless FLUX 활성화" if hf_token else "⚠️ .env에 HF_TOKEN 필요")
    else:
        st.caption("🚀 SiliconFlow 고속 생성 활성화" if sf_key else "⚠️ .env에 SILICONFLOW_API_KEY 필요")

    # 3) TTS 음성 엔진
    st.markdown('<div style="font-size:0.75rem; font-weight:600; color:#5f6368; margin-top:5px; margin-bottom:2px;">SPEECH & TTS</div>', unsafe_allow_html=True)
    sidebar_tts_choice = st.radio(
        "사용할 TTS 나레이션 엔진",
        options=["무료 Edge-TTS (고속/무제한 추천)", "Google Gemini-TTS (GenAI)", "Qwen3-TTS (로컬 7860)"],
        index=0,
        key="sidebar_tts_engine_radio",
        label_visibility="collapsed",
        help="• 무료 Edge-TTS: Microsoft Edge 음성 합성 (가장 안정적이고 고품질 무료 무제한 생성)\n• Gemini-TTS: Google GenAI 음성 모델\n• Qwen3-TTS: 로컬 음성 클로닝"
    )
    selected_tts_engine = "edge" if "Edge" in sidebar_tts_choice else ("gemini" if "Gemini" in sidebar_tts_choice else "qwen")
    st.session_state["global_tts_engine"] = selected_tts_engine
    if selected_tts_engine == "edge":
        st.caption("⚡ Edge-TTS (SunHiNeural) 고속 활성화")
    elif selected_tts_engine == "gemini":
        st.caption("✨ Google Gemini TTS (Kore/Puck) 활성화")
    else:
        st.caption("🎙️ 로컬 Qwen3-TTS 보이스 클론 활성화")

    st.markdown("<hr/>", unsafe_allow_html=True)
    st.markdown('<div class="aistudio-section-header">ENVIRONMENT STATUS</div>', unsafe_allow_html=True)
    
    openai_key = os.getenv("OPENAI_API_KEY")
    oa_ok = bool(openai_key and len(openai_key) > 5)
    oa_dot = "dot-online" if oa_ok else "dot-offline"
    oa_txt = "OpenAI 연결" if oa_ok else "OpenAI 누락"

    gm_ok = bool(g_key and len(g_key) > 5)
    gm_dot = "dot-online" if gm_ok else "dot-idle"
    gm_txt = "Gemini API" if gm_ok else "Gemini 미설정"

    studio_active = is_port_open(port=3000)
    st_dot = "dot-online" if studio_active else "dot-idle"
    st_txt = "Studio :3000" if studio_active else "Studio 대기"

    st.markdown(f"""
    <div class="aistudio-chip-grid">
        <div class="aistudio-chip-item"><span class="{oa_dot}"></span> {oa_txt}</div>
        <div class="aistudio-chip-item"><span class="{gm_dot}"></span> {gm_txt}</div>
        <div class="aistudio-chip-item"><span class="dot-online"></span> Edge-TTS 준비</div>
        <div class="aistudio-chip-item"><span class="{st_dot}"></span> {st_txt}</div>
    </div>
    """, unsafe_allow_html=True)

    # Remotion Studio 상태 및 제어
    if studio_active:
        st.link_button("🌐 Studio 프리뷰 열기 (포트 3000)", "http://localhost:3000", use_container_width=True)
    else:
        if st.button("▶️ Remotion Studio 시작", use_container_width=True):
            npx_bin = "npx.cmd" if sys.platform == "win32" else "npx"
            subprocess.Popen([npx_bin, "remotion", "studio", "--port=3000"], cwd=MY_VIDEO_DIR)
            time.sleep(1.5)
            st.rerun()

# ------------------------------------------------------------------
# 메인 화면: Google AI Studio 스타일 상단 네비게이션
# ------------------------------------------------------------------
st.markdown("""
<div class="aistudio-topbar">
    <div class="aistudio-brand">
        <span class="aistudio-sparkle">✦</span>
        <span class="aistudio-brand-title">Loco ShopShorts Maker</span>
    </div>
    <div class="aistudio-chip">✦ Gemini 2.0 • Multimodal Studio</div>
</div>
""", unsafe_allow_html=True)

if not selected_folder:
    st.warning("👈 왼쪽 사이드바에서 프로젝트 폴더를 생성하거나 선택해 주세요.")
    st.stop()

current_project_path = os.path.join(OUTPUTS_DIR, selected_folder)

# 프로젝트 전환 감지 및 이전 프로젝트 임시 세션 정리
prev_active_project = st.session_state.get("_last_loaded_project")
if selected_folder != prev_active_project:
    st.session_state["_last_loaded_project"] = selected_folder
    st.session_state.pop("coupang_ingested", None)
    st.session_state.pop("last_uploaded_capcut_sig", None)
    st.session_state.pop("uploaded_video_just_now", None)

status = check_project_status(current_project_path)

# Remotion Studio용 활성 프로젝트 설정 및 에셋 자동 동기화
if status["scenes"] or status["images"]:
    sync_remotion_active_project(current_project_path)

# 프로젝트 현황 5개 배지
col_h1, col_h2, col_h3, col_h4, col_h5 = st.columns(5)
with col_h1:
    b = "badge-done" if status["script"] else "badge-wait"
    st.markdown(f'기획/대본: <span class="status-badge {b}">{"✅ 작성됨" if status["script"] else "⏳ 필요"}</span>', unsafe_allow_html=True)
with col_h2:
    b = "badge-done" if status["audio"] else "badge-wait"
    st.markdown(f'음성 상태: <span class="status-badge {b}">{"✅ 생성됨" if status["audio"] else "⏳ 필요"}</span>', unsafe_allow_html=True)
with col_h3:
    b = "badge-done" if status["scenes"] else "badge-wait"
    st.markdown(f'자막 싱크: <span class="status-badge {b}">{"✅ 완료" if status["scenes"] else "⏳ 필요"}</span>', unsafe_allow_html=True)
with col_h4:
    b = "badge-done" if status["images"] else "badge-wait"
    st.markdown(f'에셋 이미지: <span class="status-badge {b}">{"✅ 생성됨" if status["images"] else "⏳ 필요"}</span>', unsafe_allow_html=True)
with col_h5:
    b = "badge-done" if status["video"] else "badge-wait"
    st.markdown(f'영상 렌더: <span class="status-badge {b}">{"✅ 렌더완료" if status["video"] else "⏳ 미완료"}</span>', unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ------------------------------------------------------------------
# 7대 탭 구성
# ------------------------------------------------------------------
tab_research, tab_script, tab_audio, tab_subtitles, tab_images, tab_video, tab_assets = st.tabs([
    "🔍 1. AI 제품 조사 & 기획",
    "✍️ 2. 대본 편집 & 플랜",
    "🔊 3. TTS 음성 생성",
    "🎯 4. Whisper 자막 싱크",
    "🎨 5. AI 이미지 일괄 생성 (핵심)",
    "🎬 6. Remotion 렌더링 & 프리뷰",
    "📁 7. 에셋 갤러리"
])

# ------------------------------------------------------------------
# TAB 1: AI 제품 조사 & 기획 (스킬 워크플로우 통합)
# ------------------------------------------------------------------
with tab_research:
    st.markdown("### 🔍 AI 제품 조사 및 숏폼 기획 생성")
    st.markdown("상품 URL, 실물 사진, 또는 준비된 대본을 입력하여 **촬영 플랜(`plan.md`), 대본(`script.md`), AI 영상 프롬프트(`prompts.md`), 배포 키트(`publish_kit.md`)**를 자동 생성합니다.")

    # 1. 쇼츠 유형 및 기획 모드 선택
    col_opt1, col_opt2 = st.columns([1.2, 1.2])
    with col_opt1:
        pipeline_type_label = st.radio(
            "🎯 제작할 쇼츠 유형:",
            [
                "🛍️ 단일 제품 시연 쇼핑쇼츠 (15초, 빠른 USP 증명, 1.2배속)",
                "📖 팩션(Faction) 썰 쇼핑쇼츠 (30초, 도파민 스토리텔링 / Soft Sell, 1.5배속)"
            ],
            index=0,
            help="단일 시연 쇼츠는 기능/제형이 직관적인 상품에 적합하며, 팩션 썰 쇼츠는 비하인드 스토리나 품절 대란 소재가 있는 상품에 최적입니다."
        )
        is_product_shorts = "단일 제품" in pipeline_type_label
        pipeline_code = "product_15s" if is_product_shorts else "faction_30s"

    with col_opt2:
        input_mode = st.radio(
            "📝 기획 입력 모드:",
            [
                "🤖 URL 또는 제품 키워드로 AI 자동 기획",
                "✍️ 내 대본 / 콘티 직접 입력 모드 (스킬과 100% 동일)"
            ],
            index=0,
            help="스킬처럼 이미 작성된 대본이나 스토리보드 테이블이 있다면 '직접 입력 모드'를 선택하세요."
        )

    st.markdown("---")
    st.markdown("#### 📷 실물 제품 사진 업로드 (스킬 핵심 기능)")
    st.caption("실물 사진을 업로드하면 Gemini 비전 AI가 제품의 실제 외형(색상, 재질, 형태, LED 등)을 정밀 분석하여 일관된 9:16 에셋을 생성합니다.")
    
    uploaded_file = st.file_uploader(
        "실물 제품 사진 파일 선택 (JPG / PNG)",
        type=["jpg", "jpeg", "png"],
        key=f"ref_image_uploader_{selected_folder}"
    )
    
    ref_image_path = os.path.join(current_project_path, "assets", "ref_cut1.png")
    if uploaded_file is not None:
        os.makedirs(os.path.join(current_project_path, "assets"), exist_ok=True)
        with open(ref_image_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        st.success(f"실물 레퍼런스 사진 등록 완료: `assets/ref_cut1.png`")
        
    if os.path.exists(ref_image_path):
        col_img_prev, col_img_info = st.columns([1, 3])
        with col_img_prev:
            st.image(ref_image_path, caption="현재 등록된 실물 레퍼런스", width=180)
        with col_img_info:
            st.info("등록된 실물 사진의 색상, 버튼, LED 인디케이터 등의 시각적 특성이 AI 기획안 및 6개 컷 비주얼 프롬프트에 자동 반영됩니다.")

    st.markdown("---")
    st.markdown("#### 🛒 쿠팡 상품 상세 가져오기 (coupang-crawler 스킬)")
    st.caption("쿠팡은 자동 요청을 차단하므로, 크롬에서 상품 페이지를 연 뒤 맨 아래까지 스크롤하고 Ctrl+S → '웹페이지, 단일 파일(.mhtml)'로 저장한 파일을 올려 주세요.")
    coupang_file = st.file_uploader(
        "저장한 쿠팡 상품 페이지 (.mhtml / .html)",
        type=["mhtml", "mht", "html", "htm"],
        key=f"coupang_page_uploader_{selected_folder}"
    )
    if coupang_file is not None and st.session_state.get("coupang_ingested") != (selected_folder, coupang_file.file_id):
        import tempfile
        suffix = os.path.splitext(coupang_file.name)[1] or ".html"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(coupang_file.getbuffer())
            tmp_path = tmp.name
        try:
            ingest_coupang_page(tmp_path, current_project_path)
            st.session_state["coupang_ingested"] = (selected_folder, coupang_file.file_id)
            st.success("쿠팡 상품 상세 수집 완료: `coupang-product.json`")
        except Exception as e:
            st.error(f"쿠팡 페이지 파싱 실패: {e}")
        finally:
            os.remove(tmp_path)

    coupang_data = load_coupang_data(current_project_path)
    if coupang_data:
        cf = coupang_data.get("fields", {})
        col_cp1, col_cp2 = st.columns([1, 3])
        with col_cp1:
            if cf.get("gallery_images"):
                st.image(cf["gallery_images"][0], width=180)
        with col_cp2:
            st.markdown(f"**{cf.get('title', '')}**")
            if cf.get("brand"):
                st.caption(cf["brand"])
            price_line = f"{cf['sale_price']:,}원" if cf.get("sale_price") else "가격 정보 없음"
            if cf.get("original_price"):
                price_line += f" (정가 {cf['original_price']:,}원 {cf.get('discount_rate', '')})"
            st.markdown(price_line)
            if cf.get("rating") or cf.get("review_count"):
                st.markdown(f"⭐ {cf.get('rating', '-')} · 리뷰 {cf.get('review_count') or 0:,}개")
            st.caption(f"옵션 {len(cf.get('options', []))} · 표기정보 {len(cf.get('specs', []))} · 썸네일 {len(cf.get('gallery_images', []))} · 상세이미지 {len(cf.get('detail_images', []))}")
            for note in coupang_data.get("notes", []):
                st.caption(f"ℹ️ {note}")
        # 상세 이미지 OCR (LLM 미사용, RapidOCR CPU)
        detail_dir = os.path.join(current_project_path, "assets", "coupang_detail")
        n_detail_files = len(os.listdir(detail_dir)) if os.path.isdir(detail_dir) else 0
        col_ocr1, col_ocr2 = st.columns([1, 2])
        with col_ocr1:
            run_ocr = st.button(
                f"🔎 상세 이미지 {n_detail_files}장 OCR 스펙 추출",
                disabled=n_detail_files == 0,
                use_container_width=True,
                help="상세 이미지 속 글자를 읽어 소비전력·단계·타이머·인증·구매주의 등을 뽑습니다 (이미지 10장 기준 약 40초)."
            )
        with col_ocr2:
            if n_detail_files == 0:
                st.caption("상세 이미지 원본이 없습니다. '.mhtml(단일 파일)'로 저장해 올리면 OCR을 쓸 수 있습니다.")
        if run_ocr:
            with st.spinner("상세 이미지 OCR 중... (CPU, 이미지 10장 기준 약 40초)"):
                try:
                    run_coupang_ocr(current_project_path)
                    coupang_data = load_coupang_data(current_project_path)
                except Exception as e:
                    st.error(f"OCR 실패: {e}")

        ocr = coupang_data.get("ocr")
        if ocr:
            st.markdown(f"**🔎 상세 이미지 OCR 결과** ({ocr.get('elapsed_sec', '?')}초)")
            for c in ocr.get("conflicts", []):
                st.warning(f"불일치: {c}")
            for n in ocr.get("purchase_notes", []):
                st.warning(f"구매 주의: {n['type']} — \"{n['evidence']}\"")
            if ocr.get("specs"):
                st.table([{"항목": s["type"], "값": s["value"], "원문": s["evidence"], "이미지": s["image"]} for s in ocr["specs"]])
            tags = [f["type"] for f in ocr.get("features", [])] + [f"인증 {c['type']}" for c in ocr.get("certifications", [])]
            if tags:
                st.markdown(" · ".join(f"`{t}`" for t in tags))
            st.caption("OCR 기반 후보입니다. 영상에 쓰기 전 근거 이미지를 확인하세요.")

        with st.expander("수집된 원본 JSON 보기"):
            st.json(coupang_data)
        st.info("이 정보는 AI 기획 시 PRODUCT_TRUTH 사실 데이터로 자동 반영됩니다.")

    st.markdown("---")
    st.markdown("#### 📝 제품 상세 및 대본 입력")
    
    custom_script_content = ""
    if "직접 입력" in input_mode:
        custom_script_content = st.text_area(
            "✍️ 작성하신 대본 및 씬 스토리보드 (자유 양식)",
            placeholder="""예시:
🎧 솔직히 가성비 끝판왕 무선 이어폰을 아직도 고민하시나요?
이 작은 크기에 프리미엄 노이즈 캔슬링 기능까지 확실하게 들어가 있습니다.
게다가 생활 방수 기능, 선명한 통화 마이크, 그리고 고속 충전까지...
프로필 링크를 참조하세요

| 시간 | 화면 | 자막 |
|---|---|---|
| 0~3초 | 이어폰 착용 클로즈업 | 아직도 고민하세요? |
| 3~6초 | 이어폰 케이스 오픈 | 노캔 기능 탑재 |""",
            height=200,
            key=f"custom_script_input_{selected_folder}"
        )
        product_url = ""
        product_text_desc = "사용자 직접 입력 대본 기반 쇼츠"
    else:
        col_in1, col_in2 = st.columns([1.5, 1])
        with col_in1:
            product_url = st.text_input(
                "🔗 상품 URL (쿠팡, 스마트스토어, Amazon 등 - 선택사항)",
                placeholder="https://www.coupang.com/vp/products/...",
                key=f"product_url_input_{selected_folder}"
            )
            product_text_desc = st.text_area(
                "📝 제품명 / 브랜드 / 핵심 특징 / 썰 키워드",
                placeholder="예: 초가성비 무선 노이즈캔슬링 블루투스 이어폰\nLED 배터리 100 잔량 표시, 생활 방수, USB-C 충전, 운동/출퇴근용",
                height=130,
                key=f"product_desc_input_{selected_folder}"
            )
        with col_in2:
            category_choice = st.selectbox(
                "카테고리 선택",
                ["자동 감지", "가전/디지털", "뷰티/스킨케어", "생활/청소/욕실", "주방/조리도구", "식품/간식", "패션/잡화", "여행/아웃도어", "아이디어/기타"],
                index=0,
                key=f"category_choice_{selected_folder}"
            )
            model_choice = st.selectbox(
                "분석 AI 모델",
                ["auto (OpenAI / Gemini 자동 감지)", "gemini (Gemini 3.8 Flash)", "openai (GPT-4o)"],
                index=0,
                key=f"model_choice_{selected_folder}"
            )

    st.markdown("---")
    st.markdown("#### 🚀 파이프라인 가동 선택")
    active_tts_desc = "무료 Edge-TTS" if selected_tts_engine == "edge" else ("Google Gemini-TTS" if selected_tts_engine == "gemini" else "Qwen3-TTS")
    active_img_desc = "Google Gemini (실물 레퍼런스)" if selected_img_engine == "gemini" else ("Hugging Face FLUX" if selected_img_engine == "hf" else "SiliconFlow FLUX")
    style_labels = {
        "empathy": "문제공감 & 해결형",
        "story": "비하인드 썰 & 스토리텔링형",
        "review": "내돈내산 솔직 리뷰형",
        "fast_usp": "초고속 결과선공개형",
        "warning": "충격 경고 & 반전형"
    }
    active_style_desc = style_labels.get(st.session_state.get("global_script_style", selected_script_style), "문제공감 & 해결형")
    st.info(f"🌐 **현재 전역 엔진 & 스타일 설정 (좌측 사이드바에서 변경 가능)**: ✍️ 대본 스타일 = **{active_style_desc}** | 🔊 음성 = **{active_tts_desc}** | 🎨 이미지 = **{active_img_desc}**")
    
    col_btn1, col_btn2 = st.columns([1, 1.3])
    
    with col_btn1:
        if st.button("📄 1단계만 실행: AI 기획 및 대본 생성", use_container_width=True):
            if "직접 입력" not in input_mode and not product_url and not product_text_desc.strip():
                st.error("상품 URL 또는 제품 설명 중 최소 하나를 입력해 주세요!")
            elif "직접 입력" in input_mode and not custom_script_content.strip():
                st.error("대본 내용을 입력해 주세요!")
            else:
                with st.spinner(f"AI가 [{active_style_desc}] 스타일로 상품 조사 및 실물 사진 분석, 숏폼 서사 설계를 진행 중입니다..."):
                    try:
                        res = run_product_research(
                            product_text=product_text_desc,
                            url=product_url,
                            pipeline_type=pipeline_code,
                            category=category_choice if "직접 입력" not in input_mode else "자동 감지",
                            model_choice=model_choice.split(" ")[0] if "직접 입력" not in input_mode else "auto",
                            image_path=ref_image_path if os.path.exists(ref_image_path) else None,
                            custom_script=custom_script_content if "직접 입력" in input_mode else None,
                            coupang_data=coupang_data,
                            script_style=st.session_state.get("global_script_style", selected_script_style)
                        )
                        save_research_artifacts(current_project_path, res)
                        st.success(f"🎉 [{active_style_desc}] 스타일로 AI 제품 기획 및 대본 저장이 완료되었습니다! (2번 탭에서 확인)")
                    except Exception as e:
                        st.error(f"기획 생성 중 오류 발생: {e}")

    with col_btn2:
        include_remotion_render = st.checkbox("🎬 [5단계] 9:16 비디오 렌더링(Remotion)까지 한번에 완성", value=True)
        if st.button("⚡ 원클릭 올인원 풀 파이프라인 가동 (기획 ➔ TTS ➔ STT ➔ 이미지 ➔ 9:16 렌더링)", type="primary", use_container_width=True):
            if "직접 입력" not in input_mode and not product_url and not product_text_desc.strip():
                st.error("상품 URL 또는 제품 설명 중 최소 하나를 입력해 주세요!")
            elif "직접 입력" in input_mode and not custom_script_content.strip():
                st.error("대본 내용을 입력해 주세요!")
            else:
                full_prog = st.progress(0.0)
                full_status = st.empty()
                
                try:
                    # 1. 기획 생성
                    full_status.markdown(f"🔄 **[1단계]** [{active_style_desc}] 스타일로 AI 제품 조사 & 비전 분석 & 대본/프롬프트 생성 중...")
                    full_prog.progress(0.15)
                    res = run_product_research(
                        product_text=product_text_desc,
                        url=product_url,
                        pipeline_type=pipeline_code,
                        category=category_choice if "직접 입력" not in input_mode else "자동 감지",
                        model_choice=model_choice.split(" ")[0] if "직접 입력" not in input_mode else "auto",
                        image_path=ref_image_path if os.path.exists(ref_image_path) else None,
                        custom_script=custom_script_content if "직접 입력" in input_mode else None,
                        coupang_data=coupang_data,
                        script_style=st.session_state.get("global_script_style", selected_script_style)
                    )
                    save_research_artifacts(current_project_path, res)
                    
                    # 2. TTS 음성 생성
                    active_tts_eng = st.session_state.get("global_tts_engine", selected_tts_engine)
                    tts_label = "무료 Edge-TTS" if active_tts_eng == "edge" else ("Google Gemini-TTS" if active_tts_eng == "gemini" else "Qwen3-TTS")
                    speed_rate = 1.2 if is_product_shorts else 1.5
                    full_status.markdown(f"🔄 **[2단계]** {tts_label} 나레이션 음성 합성 및 {speed_rate}배속 인코딩 중...")
                    full_prog.progress(0.35)
                    target_tts = TTS_FACTION_SCRIPT if speed_rate == 1.5 else TTS_GEN_SCRIPT
                    tts_cmd = [
                        sys.executable, target_tts, current_project_path,
                        "--engine", active_tts_eng,
                        "--rate", str(speed_rate)
                    ]
                    if active_tts_eng == "edge":
                        tts_cmd.extend(["--voice", "ko-KR-SunHiNeural"])
                    subprocess.run(tts_cmd, check=True, capture_output=True, text=True)
                    
                    # 3. Whisper STT 자막 싱크
                    full_status.markdown("🔄 **[3단계]** Whisper STT 오디오 음성 분석 & 0.1초 정밀 자막 타임코드 싱크 정렬 중...")
                    full_prog.progress(0.55)
                    stt_cmd = [sys.executable, STT_ALIGN_SCRIPT, current_project_path]
                    subprocess.run(stt_cmd, check=True, capture_output=True, text=True)
                    
                    # 4. 이미지 6컷 일괄 생성 및 9:16 자동 분할
                    active_img_eng = st.session_state.get("global_image_engine", selected_img_engine)
                    eng_label = "무료 FLUX.1" if active_img_eng == "flux" else "Google Gemini"
                    full_status.markdown(f"🔄 **[4단계]** {eng_label} 1x3 에셋 시트 생성 및 9:16 자동 스마트 크롭 중...")
                    full_prog.progress(0.75)
                    batch_generate_images(
                        folder_path=current_project_path,
                        engine=active_img_eng,
                        mode="1x3_sheets"
                    )

                    # 5. Remotion 9:16 비디오 렌더링 (선택 시)
                    if include_remotion_render:
                        full_status.markdown("🔄 **[5단계]** Remotion 9:16 비디오 렌더링 중 (프레임 생성 및 실시간 진행률 추적)...")
                        r_prog = st.progress(0.0)
                        r_status = st.empty()
                        r_success, r_logs = render_remotion_with_progress(current_project_path, r_prog, r_status)
                        if not r_success:
                            st.warning("비디오 렌더링 중 오류가 발생했습니다. 6번 탭에서 로그를 확인하세요.")
                    
                    full_prog.progress(1.0)
                    msg_tail = "6번 탭에서 최종 영상을 재생하세요!" if include_remotion_render else "상단 3, 4, 5번 탭에서 확인하세요."
                    full_status.markdown(f"✅ **[완료]** 모든 파이프라인 처리가 성공적으로 완료되었습니다! {msg_tail}")
                    st.success(f"🎉 원클릭 풀 파이프라인 가동 성공! {msg_tail}")
                    st.balloons()
                except Exception as e:
                    full_status.empty()
                    st.error(f"풀 파이프라인 실행 중 오류 발생: {e}")

    plan_file = os.path.join(current_project_path, "plan.md")
    if os.path.exists(plan_file):
        st.markdown("---")
        st.markdown("#### 📊 현재 작업 폴더에 생성된 기획 요약 (`plan.md`)")
        with open(plan_file, "r", encoding="utf-8") as f:
            st.markdown(f.read())

# ------------------------------------------------------------------
# TAB 2: 대본 및 기획 편집
# ------------------------------------------------------------------
with tab_script:
    st.markdown("### ✍️ 쇼츠 대본 편집 (`script.md`)")
    
    script_file_path = os.path.join(current_project_path, "script.md")
    if not os.path.exists(script_file_path):
        cands = glob.glob(os.path.join(current_project_path, "*script*.md")) + glob.glob(os.path.join(current_project_path, "*대본*.md"))
        if cands:
            script_file_path = cands[0]

    current_script_content = ""
    if os.path.exists(script_file_path):
        with open(script_file_path, "r", encoding="utf-8") as f:
            current_script_content = f.read()

    edited_script = st.text_area(
        "대본 내용 (한 줄당 하나의 자막 씬으로 분할됩니다)",
        value=current_script_content,
        placeholder="1번 탭에서 AI 조사를 실행하거나, 쇼츠 대본 문장을 여기에 줄 단위로 입력하세요.",
        height=260,
        key=f"edited_script_{selected_folder}",
        help="숫자는 한글 발음(예: 46g -> 사십육 그램)으로 표기되어 있는지 확인하세요."
    )

    st.info("💡 **대본 필수 규칙**: 1) 마지막 CTA 멘트는 반드시 **'프로필 링크를 참조하세요'** 포함  2) **상품 가격(예: 19,800원, 몇만 원 등)은 대본에 절대 들어가지 않음** (가격 변동 및 심의 이슈 방지)")

    if st.button("💾 대본 저장하기", type="primary"):
        lines = [l.strip() for l in edited_script.strip().split("\n") if l.strip()]
        cta_target = "프로필 링크를 참조하세요"
        if lines:
            if lines[-1] != cta_target:
                if any(k in lines[-1] for k in ["프로필", "링크", "구매", "참조", "확인"]):
                    lines[-1] = cta_target
                else:
                    lines.append(cta_target)
            edited_script = "\n".join(lines)
        
        # 가격 표현 감지 검사
        price_found = re.search(r'(\d+[\d,]*\s*원|[일이삼사오육칠팔구십\d]+\s*만\s*원)', edited_script)
        if price_found:
            st.warning(f"⚠️ 대본에 상품 가격 표현('{price_found.group(0)}')이 감지되었습니다! 가격 변동 문제 방지를 위해 가격 언급을 삭제하는 것을 권장합니다.")
            
        with open(script_file_path, "w", encoding="utf-8") as f:
            f.write(edited_script.strip() + "\n")
        st.success(f"대본 저장 완료: {os.path.basename(script_file_path)} (마지막 CTA '프로필 링크를 참조하세요' 포함)")
        st.rerun()

    st.markdown("---")
    st.markdown("#### 📋 기타 기획 파일 확인")
    plan_path = os.path.join(current_project_path, "plan.md")
    prompts_path = os.path.join(current_project_path, "prompts.md")
    publish_path = os.path.join(current_project_path, "publish_kit.md")
    
    col_p1, col_p2, col_p3 = st.columns(3)
    with col_p1:
        if os.path.exists(plan_path):
            with st.expander("촬영 플랜 (`plan.md`)"):
                with open(plan_path, "r", encoding="utf-8") as f:
                    st.markdown(f.read())
    with col_p2:
        if os.path.exists(prompts_path):
            with st.expander("영상 프롬프트 (`prompts.md`)"):
                with open(prompts_path, "r", encoding="utf-8") as f:
                    st.markdown(f.read())
    with col_p3:
        if os.path.exists(publish_path):
            with st.expander("배포 키트 (`publish_kit.md`)"):
                with open(publish_path, "r", encoding="utf-8") as f:
                    st.markdown(f.read())

# ------------------------------------------------------------------
# TAB 3: TTS 음성 생성
# ------------------------------------------------------------------
with tab_audio:
    st.markdown("### 🔊 TTS 나레이션 음성 생성")
    
    active_sidebar_tts = st.session_state.get("global_tts_engine", selected_tts_engine)
    col_t1, col_t2, col_t3 = st.columns([1.2, 1.2, 1])
    with col_t1:
        st.markdown("#### ⚙️ 적용된 음성 엔진")
        if active_sidebar_tts == "edge":
            st.success("⚡ **무료 Edge-TTS** (고속/무제한)")
            st.caption("좌측 사이드바 메뉴에서 변경 가능")
        elif active_sidebar_tts == "gemini":
            st.success("✨ **Google Gemini-TTS** (GenAI)")
            st.caption("좌측 사이드바 메뉴에서 변경 가능")
        else:
            st.success("🎙️ **로컬 Qwen3-TTS** (클로닝)")
            st.caption("좌측 사이드바 메뉴에서 변경 가능")
        engine_code = active_sidebar_tts

    with col_t2:
        if engine_code == "edge":
            voice_choice = st.selectbox(
                "보이스 선택",
                ["ko-KR-SunHiNeural (여성, 쇼핑 추천)", "ko-KR-InJoonNeural (남성)", "ko-KR-HyunsuMultilingualNeural (남성 다국어)"],
                index=0
            )
            voice_code = voice_choice.split(" ")[0]
        elif engine_code == "gemini":
            voice_choice = st.selectbox(
                "보이스 선택 (Gemini)",
                ["Kore (여성)", "Puck (남성)", "Charon", "Fenrir", "Aoede"],
                index=0
            )
            voice_code = voice_choice.split(" ")[0]
        else:
            st.info("로컬 Qwen3-TTS는 `reference_voice.mp3` 클로닝 보이스를 사용합니다.")
            voice_code = "default"

    with col_t3:
        speed_rate = st.selectbox(
            "오디오 재생 배속",
            [1.2, 1.5, 1.0, 1.3],
            index=0,
            help="쇼핑쇼츠는 1.2배속, 팩션 썰쇼츠는 1.5배속을 추천합니다."
        )

    if st.button("🚀 TTS 음성 생성하기", type="primary", use_container_width=True):
        if not status["script"]:
            st.error("먼저 대본(script.md)을 작성하고 저장해 주세요!")
        else:
            with st.spinner("음성 합성 및 FFmpeg 배속 인코딩 진행 중..."):
                target_script = TTS_FACTION_SCRIPT if speed_rate == 1.5 else TTS_GEN_SCRIPT
                cmd = [
                    sys.executable,
                    target_script,
                    current_project_path,
                    "--engine", engine_code,
                    "--voice", voice_code,
                    "--rate", str(speed_rate)
                ]
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode == 0:
                    st.success("음성 생성이 완료되었습니다!")
                    st.rerun()
                else:
                    st.error(f"오류 발생:\n{res.stderr or res.stdout}")

    st.markdown("---")
    st.markdown("#### 🎧 생성된 오디오 미리 듣기")
    
    audio_files = glob.glob(os.path.join(current_project_path, "*.wav"))
    if audio_files:
        audio_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        selected_audio = audio_files[0]
        st.caption(f"현재 선택된 오디오: `{os.path.basename(selected_audio)}` ({round(os.path.getsize(selected_audio) / 1024, 1)} KB)")
        with open(selected_audio, "rb") as f:
            st.audio(f.read(), format="audio/wav")
    else:
        st.info("아직 생성된 오디오 파일이 없습니다. 위 버튼을 눌러 음성을 생성하세요.")

# ------------------------------------------------------------------
# TAB 4: Whisper 자막 싱크
# ------------------------------------------------------------------
with tab_subtitles:
    st.markdown("### 🎯 Whisper STT 자막 씬 싱크 정렬")
    st.markdown("OpenAI Whisper API를 통해 생성된 오디오와 대본을 비교하여 쇼츠용 2~4단어 호흡의 `scene_data.json`을 생성합니다.")

    if st.button("⚡ Whisper STT 자막 싱크 실행", type="primary", use_container_width=True):
        if not status["audio"]:
            st.error("먼저 3번 탭에서 TTS 음성을 생성해 주세요!")
        else:
            with st.spinner("Whisper STT 음성 인식 및 자막 씬 분할 정렬 중..."):
                cmd = [sys.executable, STT_ALIGN_SCRIPT, current_project_path]
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode == 0:
                    st.success("자막 싱크 분할 완료! (`scene_data.json` + `subtitles.srt` 갱신)")
                    st.rerun()
                else:
                    st.error(f"오류 발생:\n{res.stderr or res.stdout}")

    st.markdown("---")
    st.markdown("#### 📜 생성된 씬별 자막 데이터 (`scene_data.json`)")

    scene_data_path = os.path.join(current_project_path, "scene_data.json")
    if os.path.exists(scene_data_path):
        try:
            with open(scene_data_path, "r", encoding="utf-8") as f:
                scenes = json.load(f)
            
            st.success(f"총 {len(scenes)}개 씬 구성 완료")
            
            table_data = []
            for sc in scenes:
                sc_id = sc.get("scene_id")
                start = sc.get("start")
                end = sc.get("end")
                dur_frames = sc.get("duration_frames")
                blocks = sc.get("text_blocks", [])
                text_combined = " ".join([b.get("text", "") for b in blocks])
                table_data.append({
                    "씬 #": f"Scene {sc_id}",
                    "시작 시간": f"{start:.2f}s",
                    "종료 시간": f"{end:.2f}s",
                    "프레임 수": f"{dur_frames}f (30fps)",
                    "자막 텍스트": text_combined
                })
            
            st.table(table_data)

            with st.expander("JSON 원본 보기"):
                st.json(scenes)
        except Exception as e:
            st.error(f"JSON 로드 오류: {e}")
    else:
        st.info("아직 `scene_data.json`이 생성되지 않았습니다. 위 버튼을 눌러 정렬을 실행하세요.")

# ------------------------------------------------------------------
# TAB 5: AI 이미지 일괄 생성 (NEW! 핵심 기능)
# ------------------------------------------------------------------
with tab_images:
    st.markdown("### 🎨 6개 씬 AI 이미지 일괄 생성")
    st.markdown("쇼츠 영상 6개 컷에 필요한 **초고화질 실사 AI 에셋을 일괄 생성**하고, 찌그러짐 없는 완벽한 **9:16 (1080x1920) 규격**으로 자동 크롭 분할합니다.")

    with st.expander("💡 이미지 생성 엔진 안내"):
        st.markdown("""
- **1. Google Gemini (실물 사진 레퍼런스, 기본 권장)**:
  - 첨부하신 실제 상품 사진(`tl신일가습기.png` 등)을 분석하여, **외형 왜곡 없이 동일한 제품의 6개 씬**을 정밀 생성합니다.
- **2. Hugging Face FLUX (무료)**:
  - [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)에서 무료 계정 생성 후 `Read` 토큰 생성.
  - `.env`에 `HF_TOKEN=hf_...` 등록 시 FLUX.1-schnell 서버리스 무료 생성.
- **3. SiliconFlow FLUX (무료 토큰)**:
  - [cloud.siliconflow.cn](https://cloud.siliconflow.cn) 가입 시 수천 장 분량(2천만 토큰) 무료 제공.
  - `.env`에 `SILICONFLOW_API_KEY=sk-...` 등록 시 2초 초고속 생성.
        """)

    col_im1, col_im2 = st.columns([1.2, 1.2])
    with col_im1:
        st.markdown("#### ⚙️ 적용된 이미지 엔진")
        cur_global_engine = st.session_state.get("global_image_engine", selected_img_engine)
        if cur_global_engine == "hf":
            st.success("🤗 **Hugging Face FLUX.1-schnell**")
            st.caption("좌측 사이드바 메뉴에서 변경 가능")
        elif cur_global_engine == "siliconflow":
            st.success("🚀 **SiliconFlow FLUX (2천만 무료 토큰)**")
            st.caption("좌측 사이드바 메뉴에서 변경 가능")
        else:
            st.success("✨ **Google Gemini (실물 사진 레퍼런스, 8K)**")
            st.caption("좌측 사이드바 메뉴에서 변경 가능 | 실물 왜곡 0% 정밀 생성")
        img_engine_code = cur_global_engine

    with col_im2:
        img_mode = st.selectbox(
            "에셋 생성 방식",
            [
                "1x3 에셋 시트 2장 생성 후 자동 9:16 크롭 (권장, 황금 종횡비 1.69)",
                "9:16 개별 컷 직접 생성 (Cut 1 ~ Cut 6)"
            ],
            index=0
        )
        img_mode_code = "1x3_sheets" if "1x3" in img_mode else "direct_cuts"

    # 프롬프트 확인 및 편집
    prompts_file_path = os.path.join(current_project_path, "prompts.md")
    existing_prompts_text = ""
    if os.path.exists(prompts_file_path):
        with open(prompts_file_path, "r", encoding="utf-8") as f:
            existing_prompts_text = f.read()

    with st.expander("✏️ 6개 컷별 비주얼 프롬프트 확인 / 커스텀 편집"):
        custom_prompts_input = st.text_area(
            "프롬프트 내용 (`prompts.md`)",
            value=existing_prompts_text,
            placeholder="1번 탭에서 기획을 생성하면 6개 컷 프롬프트가 자동으로 채워집니다.",
            height=180,
            key=f"custom_prompts_{selected_folder}"
        )
        if st.button("프롬프트 저장"):
            with open(prompts_file_path, "w", encoding="utf-8") as f:
                f.write(custom_prompts_input)
            st.success("프롬프트 저장 완료!")

    # 일괄 생성 버튼
    if st.button("✨ 6개 씬 이미지 일괄 생성 시작 (Batch Generate)", type="primary", use_container_width=True):
        progress_bar = st.progress(0.0)
        status_text = st.empty()

        def update_progress(current, total, msg):
            pct = float(current) / float(total)
            progress_bar.progress(pct)
            status_text.markdown(f"**[{current}/{total}]** {msg}")

        try:
            with st.spinner("AI 이미지 생성 엔진 구동 중..."):
                batch_generate_images(
                    folder_path=current_project_path,
                    engine=img_engine_code,
                    mode=img_mode_code,
                    progress_callback=update_progress
                )
            st.success("🎉 모든 컷의 AI 이미지 일괄 생성 및 9:16 크롭 완료!")
            st.balloons()
            st.rerun()
        except Exception as e:
            st.error(f"이미지 생성 중 오류 발생: {e}")

    st.markdown("---")
    st.markdown("#### 🖼️ 생성된 9:16 쇼츠 컷 에셋 갤러리 (`assets/` 및 `images/` 순차 저장)")
    
    # 순차 에셋 동기화 실행
    sync_sequential_images(current_project_path)

    # 순차 컷 파일 우선 탐색 (01_Cut1 ~ 06_Cut6 또는 cut*_9_16)
    cut_images = sorted(glob.glob(os.path.join(current_project_path, "assets", "0[1-6]_Cut*.jpg")))
    if not cut_images:
        cut_images = sorted(glob.glob(os.path.join(current_project_path, "assets", "cut*_9_16.jpg")))
    if not cut_images:
        cut_images = sorted(glob.glob(os.path.join(current_project_path, "assets", "*.jpg")) + glob.glob(os.path.join(current_project_path, "assets", "*.png")))
        
    if cut_images:
        st.success(f"총 {len(cut_images)}개 9:16 에셋 준비 완료 (압축 없이 `assets/` 및 `images/` 하부 폴더에 순차 저장됨)")
        
        # 순차 일괄 다운로드 및 폴더 열기 액션 바
        col_act1, col_act2, col_act3 = st.columns([1, 1, 1.6])
        with col_act1:
            if st.button("📂 하부 assets 폴더 열기", use_container_width=True, disabled=not hasattr(os, "startfile")):
                a_dir = os.path.join(current_project_path, "assets")
                os.startfile(a_dir if os.path.exists(a_dir) else current_project_path)
        with col_act2:
            if st.button("📁 하부 images 폴더 열기", use_container_width=True, disabled=not hasattr(os, "startfile")):
                i_dir = os.path.join(current_project_path, "images")
                os.startfile(i_dir if os.path.exists(i_dir) else current_project_path)
        with col_act3:
            import base64
            seq_b64 = []
            for cp in cut_images[:6]:
                try:
                    with open(cp, "rb") as bf:
                        b64_str = base64.b64encode(bf.read()).decode("utf-8")
                        seq_b64.append({"name": os.path.basename(cp), "data": f"data:image/jpeg;base64,{b64_str}"})
                except Exception:
                    pass
            if seq_b64:
                b64_json = json.dumps(seq_b64)
                st.components.v1.html(f"""
                <div style="font-family: sans-serif;">
                    <button id="dl_seq_btn" style="width:100%; padding:9px 12px; background:#2563eb; color:white; border:none; border-radius:6px; font-weight:600; cursor:pointer; font-size:13px;">
                        📥 6개 컷 브라우저 순차 다운로드 (압축 없음)
                    </button>
                    <div id="dl_seq_msg" style="font-size:11px; color:#4b5563; margin-top:4px; font-weight:500;"></div>
                </div>
                <script>
                const files = {b64_json};
                document.getElementById('dl_seq_btn').addEventListener('click', () => {{
                    const msg = document.getElementById('dl_seq_msg');
                    msg.innerText = '⏳ 순차 다운로드 시작...';
                    files.forEach((f, idx) => {{
                        setTimeout(() => {{
                            const a = document.createElement('a');
                            a.href = f.data;
                            a.download = f.name;
                            document.body.appendChild(a);
                            a.click();
                            document.body.removeChild(a);
                            msg.innerText = `[${{idx+1}}/${{files.length}}] ${{f.name}} 다운로드 중...`;
                            if (idx === files.length - 1) {{
                                setTimeout(() => {{ msg.innerText = '✅ 6개 컷 다운로드 완료! (압축 없음)'; }}, 500);
                            }}
                        }}, idx * 450);
                    }});
                }});
                </script>
                """, height=65)

        cut_labels = [
            "Cut 1: 결과 선공개 (Hook)",
            "Cut 2: 대비 (Before/Problem)",
            "Cut 3: 히어로 제품 (Product)",
            "Cut 4: 핵심 시연 (Action)",
            "Cut 5: 결과 증명 (Proof)",
            "Cut 6: 루프 엔딩 (CTA)"
        ]
        
        # 6개 컷 가로 3개씩 2줄 그리드 표시
        cols = st.columns(3)
        for i, cut_p in enumerate(cut_images[:6]):
            with cols[i % 3]:
                label = cut_labels[i] if i < len(cut_labels) else os.path.basename(cut_p)
                st.image(cut_p, caption=f"{os.path.basename(cut_p)}\n({label})", use_container_width=True)
                with open(cut_p, "rb") as f:
                    st.download_button(
                        label=f"📥 {os.path.basename(cut_p)} 다운로드",
                        data=f,
                        file_name=os.path.basename(cut_p),
                        mime="image/jpeg",
                        key=f"dl_cut_{i}"
                    )
    else:
        st.info("아직 생성된 이미지가 없습니다. 위 [일괄 생성 시작] 버튼을 누르면 6개 컷이 자동으로 완성됩니다.")

    # 종합 에셋 시트 원본 (1x3) 확인
    sheets = sorted(glob.glob(os.path.join(current_project_path, "asset_sheet_*.jpg")) + glob.glob(os.path.join(current_project_path, "asset_sheet.jpg")))
    if sheets:
        with st.expander("원본 1x3 종합 에셋 시트 (16:9 가로 캔버스) 보기"):
            sh_cols = st.columns(len(sheets))
            for i, sh_p in enumerate(sheets):
                with sh_cols[i]:
                    st.image(sh_p, caption=os.path.basename(sh_p), use_container_width=True)

# ------------------------------------------------------------------
# TAB 6: Remotion 렌더링 & 최종 쇼츠 비디오 관리
# ------------------------------------------------------------------
with tab_video:
    st.markdown("### 🎬 Remotion 9:16 비디오 렌더링 & 비디오 플레이어")
    st.markdown("자막 오버레이(`scene_data.json`)와 배경 비디오/에셋 이미지를 합성하여 **최종 9:16 쇼츠 MP4 비디오**를 렌더링합니다.")

    # 6개 컷 비디오 감지 상태 확인
    cut_video_files = []
    for i in range(1, 7):
        p_cands = [f"cut{i}.mp4", f"0{i}_Cut{i}.mp4", f"cut_{i}.mp4", f"Cut{i}.mp4", f"cut{i}.mov", f"0{i}_Cut{i}.mov"]
        f_name = next((c for c in p_cands if os.path.exists(os.path.join(current_project_path, c))), None)
        cut_video_files.append((i, f_name))
    
    found_cut_count = sum(1 for _, f in cut_video_files if f)

    # 1. Remotion 자동 렌더링 섹션 (상단 메인 배치)
    col_r1, col_r2 = st.columns([2, 1])
    with col_r1:
        if found_cut_count > 0:
            st.success(f"🎬 **6컷 AI 비디오 시퀀스 모드 활성화됨 ({found_cut_count}/6개 컷 비디오 적용)**")
            cut_pills = []
            cut_labels = ["1:Hook", "2:Before", "3:Hero", "4:Action", "5:Proof", "6:CTA"]
            for idx, f_name in cut_video_files:
                badge = "✅" if f_name else "🖼️"
                cut_pills.append(f"`Cut {cut_labels[idx-1]}`: {badge}")
            st.caption(" | ".join(cut_pills) + " (비디오가 없는 컷은 AI 생성 이미지로 자동 보완)")
        else:
            bg_videos = glob.glob(os.path.join(current_project_path, "video*.mp4")) + \
                        glob.glob(os.path.join(current_project_path, "background*.mp4")) + \
                        glob.glob(os.path.join(current_project_path, "scene*.mp4"))
            if bg_videos:
                st.success(f"🎬 단일 배경 비디오 소스 감지됨 ({len(bg_videos)}개)")
            else:
                st.info("💡 동영상 클립이 없는 경우, 5번 탭에서 생성된 9:16 실사 이미지 에셋들을 기반으로 자동 조립 렌더링됩니다.")

    with col_r2:
        no_audio_opt = st.checkbox(
            "배경 비디오 원본 오디오 보존 (캡컷 소리 그대로 사용)",
            value=True,
            help="체크 시(기본값) 캡컷 등에서 가져온 비디오 자체의 음성/나레이션/BGM을 100% 그대로 유지하고 자막만 오버레이합니다. 체크 해제 시 폴더 내 별도 생성된 WAV 음성 파일로 덮어씌웁니다."
        )

    col_btn_render, col_btn_studio = st.columns([1.5, 1])
    with col_btn_render:
        if st.button("🎥 최종 9:16 비디오 렌더링 시작 (Remotion Render)", type="primary", use_container_width=True):
            if not status["scenes"]:
                st.error("먼저 4번 탭에서 `scene_data.json` 자막 데이터를 생성해 주세요!")
            else:
                extra = ["--no-audio"] if (no_audio_opt and found_cut_count == 0) else None
                progress_bar = st.progress(0.0)
                status_text = st.empty()
                log_box = st.empty()
                success, logs = render_remotion_with_progress(current_project_path, progress_bar, status_text, extra_args=extra, log_area=log_box)
                if success:
                    st.success("🎉 Remotion 9:16 비디오 렌더링이 성공적으로 완료되었습니다!")
                    st.balloons()
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("렌더링 실패:")
                    with st.expander("에러 상세 로그 보기", expanded=True):
                        st.code(logs)

    with col_btn_studio:
        if is_port_open(port=3000):
            st.link_button("🌐 Remotion Studio 실시간 프리뷰 열기 (3000)", "http://localhost:3000", use_container_width=True)
        else:
            if st.button("▶️ Remotion Studio 프리뷰 서버 시작", use_container_width=True):
                npx_bin = "npx.cmd" if sys.platform == "win32" else "npx"
                subprocess.Popen([npx_bin, "remotion", "studio", "--port=3000"], cwd=MY_VIDEO_DIR)
                time.sleep(1.5)
                st.rerun()

    st.markdown("---")

    # 1-1. 6컷 AI 비디오 일괄 업로드 섹션
    with st.expander("🎬 Flow / Kling 6컷 AI 비디오 일괄 등록 (Cut 1 ~ Cut 6) - 캡컷 없이 완성하기", expanded=(found_cut_count > 0)):
        st.markdown("""
        **Flow, Kling, Luma, Runway 등에서 생성한 6개 비디오 클립을 여기에 한 번에 업로드하세요.**  
        • 리모션이 6개 클립을 15초 6비트 타임라인에 맞춰 **자동 순차 연결**하고, TTS 음성과 Whisper 자막을 합성하여 **캡컷 작업 없이 100% 자동 완성**합니다.  
        • 파일명에 `cut1`, `1`, `01` 등이 포함되어 있으면 해당 컷 번호로 자동 매핑됩니다. (비디오가 없는 컷은 AI 생성 이미지로 자동 대체)
        """)
        uploaded_cut_videos = st.file_uploader(
            "AI 생성 컷 비디오 파일 선택 (여러 개 동시 선택 가능)",
            type=["mp4", "mov"],
            accept_multiple_files=True,
            key=f"ai_cut_videos_uploader_{selected_folder}"
        )
        if uploaded_cut_videos:
            saved_cnt = 0
            for idx, f in enumerate(uploaded_cut_videos):
                m = re.search(r'([1-6])', f.name)
                cut_num = int(m.group(1)) if m else (idx + 1)
                if 1 <= cut_num <= 6:
                    target_path = os.path.join(current_project_path, f"cut{cut_num}.mp4")
                    with open(target_path, "wb") as out_f:
                        out_f.write(f.getbuffer())
                    saved_cnt += 1
            if saved_cnt > 0:
                st.success(f"🎉 {saved_cnt}개의 AI 컷 비디오가 성공적으로 등록되었습니다! 위의 렌더링 버튼을 누르면 캡컷 없이 자동 완성됩니다.")
                time.sleep(1)
                st.rerun()

    # 2. CapCut 등 외부 편집기 완성본 업로드 섹션
    with st.expander("📤 또는 캡컷(CapCut) 등 외부 편집기에서 렌더링해온 완성 MP4 파일 등록하기"):
        st.markdown("캡컷(CapCut), 프리미어 등에서 편집을 마치고 내보낸(Export) **최종 9:16 MP4 영상**을 등록하면 대시보드 플레이어에서 바로 확인하고 배포 키트를 복사할 수 있습니다.")
        uploaded_final_video = st.file_uploader(
            "완성된 쇼츠 비디오 파일 선택 (MP4 / MOV)",
            type=["mp4", "mov"],
            key=f"capcut_final_uploader_{selected_folder}"
        )
        if uploaded_final_video is not None:
            file_sig = f"{uploaded_final_video.name}_{uploaded_final_video.size}_{selected_folder}"
            if st.session_state.get("last_uploaded_capcut_sig") != file_sig:
                final_save_path = os.path.join(current_project_path, "output.mp4")
                with open(final_save_path, "wb") as f:
                    f.write(uploaded_final_video.getbuffer())
                st.session_state["last_uploaded_capcut_sig"] = file_sig
                st.session_state["uploaded_video_just_now"] = True
                st.rerun()

        if st.session_state.pop("uploaded_video_just_now", False):
            st.success("✅ 캡컷 완성 영상이 대시보드에 성공적으로 등록되었습니다! (`output.mp4`)")

    st.markdown("---")
    st.markdown("#### 📺 최종 완성된 쇼츠 비디오 플레이어")
    
    output_video_path = os.path.join(current_project_path, "output.mp4")
    if os.path.exists(output_video_path):
        col_vid, col_meta = st.columns([1, 1.2])
        with col_vid:
            with open(output_video_path, "rb") as f:
                video_bytes = f.read()
                st.video(video_bytes)
        with col_meta:
            st.success(f"✅ 현재 등록된 최종 쇼츠: `output.mp4`")
            st.caption(f"파일 크기: {round(os.path.getsize(output_video_path) / (1024 * 1024), 2)} MB")
            with open(output_video_path, "rb") as f:
                st.download_button(
                    label="📥 최종 쇼츠 MP4 다운로드",
                    data=f,
                    file_name=f"{selected_folder}_shorts.mp4",
                    mime="video/mp4",
                    type="primary",
                    use_container_width=True
                )
            
            # 배포용 키트 확인 (유튜브 제목/해시태그)
            pub_path = os.path.join(current_project_path, "publish_kit.md")
            if os.path.exists(pub_path):
                with st.expander("📋 유튜브/인스타 배포용 제목 & 설명문 복사"):
                    with open(pub_path, "r", encoding="utf-8") as pf:
                        st.markdown(pf.read())
    else:
        st.info("아직 생성된 최종 영상(`output.mp4`)이 없습니다. 위에서 Remotion 렌더링을 실행하거나 캡컷 영상을 등록하세요.")

# ------------------------------------------------------------------
# TAB 7: 에셋 및 미디어 업로더
# ------------------------------------------------------------------
with tab_assets:
    st.markdown("### 📁 에셋 및 미디어 업로드 / 관리")
    st.markdown("이 프로젝트 폴더에 사용할 추가 상품 사진이나 비디오 클립을 업로드할 수 있습니다.")

    uploaded_files = st.file_uploader(
        "파일 업로드 (이미지 또는 영상 클립)",
        accept_multiple_files=True,
        type=["png", "jpg", "jpeg", "webp", "mp4", "mov"],
        key=f"tab_assets_uploader_{selected_folder}"
    )
    if uploaded_files:
        for uf in uploaded_files:
            if uf.name.endswith(".mp4") or uf.name.endswith(".mov"):
                target_save = os.path.join(current_project_path, uf.name)
            else:
                assets_dir = os.path.join(current_project_path, "assets")
                os.makedirs(assets_dir, exist_ok=True)
                target_save = os.path.join(assets_dir, uf.name)
            with open(target_save, "wb") as f:
                f.write(uf.getbuffer())
        st.success(f"{len(uploaded_files)}개 파일 업로드 완료!")
        st.rerun()

    st.markdown("---")
    st.markdown("#### 📁 현재 저장된 에셋 목록")
    
    all_imgs = glob.glob(os.path.join(current_project_path, "assets", "*.png")) + \
               glob.glob(os.path.join(current_project_path, "assets", "*.jpg")) + \
               glob.glob(os.path.join(current_project_path, "*.png")) + \
               glob.glob(os.path.join(current_project_path, "*.jpg"))
               
    if all_imgs:
        cols = st.columns(4)
        for i, img_p in enumerate(all_imgs):
            with cols[i % 4]:
                st.image(img_p, caption=os.path.basename(img_p), use_container_width=True)
    else:
        st.info("현재 저장된 이미지 에셋이 없습니다.")

    st.markdown("---")
    st.markdown("#### 🎬 CapCut(캡컷) 투입 파일 (압축 없음)")
    st.caption(f"6컷 이미지 + 동영상 클립 + 음성 + 자막(SRT)이 압축 없이 프로젝트 하부 폴더(`assets/`, `images/`)에 순차로 저장되어 있습니다. CapCut이나 외부 편집기에서 이 파일들을 순서대로 바로 가져오세요.")

    capcut = capcut_input_files(current_project_path)
    rows = []
    if capcut.get("images"):
        img_names = ", ".join([os.path.basename(im) for im in capcut["images"][:6]])
        rows.append({"구분": "이미지 (6컷 순차)", "파일": f"✅ {len(capcut['images'])}개 ({img_names})"})
    else:
        rows.append({"구분": "이미지 (6컷 순차)", "파일": "❌ 없음 (5번 탭에서 6개 씬 이미지 일괄 생성 필요)"})

    if capcut["videos"]:
        for v in capcut["videos"]:
            rows.append({"구분": "동영상", "파일": os.path.basename(v)})
    else:
        rows.append({"구분": "동영상", "파일": "ℹ️ 6컷 이미지 또는 외부 클립(video*.mp4) 사용 가능"})

    rows.append({"구분": "음성", "파일": os.path.basename(capcut["voice"]) if capcut["voice"] else "❌ 없음 (3번 탭 TTS)"})
    rows.append({"구분": "자막 SRT", "파일": "subtitles.srt" if capcut["srt"] else "❌ 없음 (4번 탭 Whisper 자막 싱크)"})

    st.table(rows)

    col_cp1, col_cp2, col_cp3 = st.columns([1, 1, 1])
    with col_cp1:
        if st.button("📂 프로젝트 폴더 열기", use_container_width=True, disabled=not hasattr(os, "startfile")):
            os.startfile(current_project_path)
    with col_cp2:
        if st.button("🖼️ 하부 이미지 폴더 열기 (`assets/`)", use_container_width=True, disabled=not hasattr(os, "startfile")):
            a_dir = os.path.join(current_project_path, "assets")
            os.startfile(a_dir if os.path.exists(a_dir) else current_project_path)
    with col_cp3:
        if st.button("🔄 순차 에셋 / SRT 동기화", use_container_width=True):
            try:
                refresh_capcut_files(current_project_path)
                sync_sequential_images(current_project_path)
                st.success("순차 에셋 및 subtitles.srt 동기화 완료!")
                st.rerun()
            except Exception as e:
                st.error(f"동기화 실패: {e}")
