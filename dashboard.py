import os
import sys
import json
import glob
import time
import math
import shutil
import socket
import subprocess
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
from ai_researcher import run_product_research, save_research_artifacts

import image_generator
importlib.reload(image_generator)
from image_generator import batch_generate_images

# 페이지 기본 설정
st.set_page_config(
    page_title="Lowcost ShopShorts namdarunAi",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 커스텀 스타일
st.markdown("""
<style>
    .main-title { font-size: 2.1rem; font-weight: 700; margin-bottom: 0.2rem; }
    .sub-title { font-size: 1.05rem; color: #888; margin-bottom: 1.5rem; }
    .status-badge { display: inline-block; padding: 4px 10px; border-radius: 6px; font-size: 0.85rem; font-weight: 600; }
    .badge-done { background-color: #d1fae5; color: #065f46; }
    .badge-wait { background-color: #fef3c7; color: #92400e; }
    .badge-none { background-color: #f3f4f6; color: #4b5563; }
</style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------
# 유틸리티 함수
# ------------------------------------------------------------------
def ensure_capcut_package(folder_path):
    """CapCut 전용 00_음성, 01~06_이미지, subtitles.srt 패키지 자동 생성"""
    capcut_dir = os.path.join(folder_path, "capcut_assets")
    os.makedirs(capcut_dir, exist_ok=True)
    
    # 1. 오디오 복사
    for wav_name in ["output_1.2x.wav", "output_1.5x.wav", "output.wav"]:
        w_path = os.path.join(folder_path, wav_name)
        if os.path.exists(w_path):
            import shutil
            shutil.copyfile(w_path, os.path.join(capcut_dir, "00_voiceover.wav"))
            break
            
    # 2. 6컷 이미지 번호순 복사
    cut_labels = [
        ("cut1_9_16.jpg", "01_Cut1_Hook.jpg"),
        ("cut2_9_16.jpg", "02_Cut2_Before.jpg"),
        ("cut3_9_16.jpg", "03_Cut3_Hero.jpg"),
        ("cut4_9_16.jpg", "04_Cut4_Action.jpg"),
        ("cut5_9_16.jpg", "05_Cut5_Proof.jpg"),
        ("cut6_9_16.jpg", "06_Cut6_CTA.jpg")
    ]
    for src, dst in cut_labels:
        sp = os.path.join(folder_path, "assets", src)
        if os.path.exists(sp):
            import shutil
            shutil.copyfile(sp, os.path.join(capcut_dir, dst))
            
    # 3. CapCut 로컬 자막용 subtitles.srt 생성
    scene_file = os.path.join(folder_path, "scene_data.json")
    if os.path.exists(scene_file):
        try:
            with open(scene_file, "r", encoding="utf-8") as f:
                scenes = json.load(f)
            def fmt_t(sec):
                h = int(sec // 3600)
                m = int((sec % 3600) // 60)
                s = int(sec % 60)
                ms = int((sec - int(sec)) * 1000)
                return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
            srt_lines = []
            for i, sc in enumerate(scenes):
                t_str = " ".join([b["text"] for b in sc.get("text_blocks", [])])
                srt_lines.append(f"{i+1}\n{fmt_t(sc['start'])} --> {fmt_t(sc['end'])}\n{t_str}\n")
            with open(os.path.join(capcut_dir, "subtitles.srt"), "w", encoding="utf-8") as f:
                f.write("\n".join(srt_lines))
        except Exception:
            pass
            
    zip_base = os.path.join(folder_path, "capcut_package")
    import shutil
    shutil.make_archive(zip_base, "zip", capcut_dir)
    return zip_base + ".zip"

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
    has_images = bool(glob.glob(os.path.join(folder_path, "assets", "cut*.jpg")) or os.path.exists(os.path.join(folder_path, "asset_sheet_1.jpg")))
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
    for cand in ["output_1.2x.wav", "output_1.5x.wav", "output.wav"]:
        if os.path.exists(os.path.join(folder_path, cand)):
            audio_file = cand
            break

    # 3. my-video/src/active_props.json 갱신
    active_props = {
        "folderName": folder_name,
        "audioFileName": audio_file,
        "durationInFrames": duration_in_frames,
        "sceneData": scenes
    }
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
        if rel.startswith("remotion_") or "node_modules" in rel or rel.startswith("capcut"):
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
    st.markdown("### 🎬 Loco ShopShorts")
    st.markdown("---")

    folders = get_project_folders()
    
    st.markdown("#### 📁 프로젝트 선택")
    if folders:
        selected_folder = st.selectbox(
            "작업 폴더",
            folders,
            index=0,
            help="outputs 디렉토리 내의 프로젝트 폴더입니다."
        )
    else:
        st.info("현재 작업 폴더가 없습니다. 아래에서 새로 생성하세요.")
        selected_folder = None

    # 새 프로젝트 폴더 생성
    with st.expander("➕ 새 프로젝트 폴더 생성"):
        default_new_name = datetime.now().strftime("%y%m%d_%H%M")
        new_folder_name = st.text_input("폴더명", value=default_new_name)
        if st.button("폴더 생성", use_container_width=True):
            new_path = os.path.join(OUTPUTS_DIR, new_folder_name)
            os.makedirs(new_path, exist_ok=True)
            os.makedirs(os.path.join(new_path, "assets"), exist_ok=True)
            st.success(f"생성 완료: {new_folder_name}")
            st.rerun()

    st.markdown("---")
    st.markdown("#### ⚙️ 시스템 상태")
    
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key and len(openai_key) > 5:
        st.markdown("🟢 **OpenAI**: 연동됨 (Whisper/GPT-4o)")
    else:
        st.markdown("🔴 **OpenAI**: 키 미설정 (`.env`)")
        
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key and len(gemini_key) > 5:
        st.markdown("🟢 **Gemini API**: 연동됨 (Gemini 2.0)")
    else:
        st.markdown("⚪ **Gemini API**: 미설정 (선택)")

    st.markdown("🟢 **Edge-TTS**: 준비 완료 (무료/고속)")
    st.markdown("🟢 **FLUX 이미지**: 준비 완료 (무료/고속)")

    # Remotion Studio 상태 및 제어
    studio_active = is_port_open(port=3000)
    if studio_active:
        st.markdown("🟢 **Remotion Studio**: 실행 중 (3000)")
        st.link_button("🌐 Studio 프리뷰 열기", "http://localhost:3000", use_container_width=True)
    else:
        st.markdown("⚪ **Remotion Studio**: 미실행")
        if st.button("▶️ Remotion Studio 시작", use_container_width=True):
            npx_bin = "npx.cmd" if sys.platform == "win32" else "npx"
            subprocess.Popen([npx_bin, "remotion", "studio", "--port=3000"], cwd=MY_VIDEO_DIR)
            time.sleep(1.5)
            st.rerun()

    st.markdown("---")
    st.markdown("#### ⚡ 퀵 액션 (바로 렌더링)")
    if st.button("🎥 9:16 비디오 렌더링 시작", use_container_width=True):
        if not selected_folder:
            st.warning("먼저 작업 폴더를 선택하세요.")
        else:
            p_path = os.path.join(OUTPUTS_DIR, selected_folder)
            st_check = check_project_status(p_path)
            if not st_check["scenes"]:
                st.warning("먼저 4번 탭에서 자막(`scene_data.json`)을 생성해 주세요.")
            else:
                with st.spinner("Remotion 9:16 비디오 렌더링 진행 중..."):
                    cmd = [sys.executable, RENDER_SCRIPT, p_path]
                    r = subprocess.run(cmd, capture_output=True, text=True)
                    if r.returncode == 0:
                        st.success("✅ 비디오 렌더링 완료!")
                        st.rerun()
                    else:
                        st.error(f"렌더링 실패: {r.stderr or r.stdout}")

# ------------------------------------------------------------------
# 메인 화면
# ------------------------------------------------------------------
st.markdown('<div class="main-title">🎬 Loco ShopShorts Studio</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">AI 제품 조사부터 대본, 고속 TTS, Whisper 자막 싱크, AI 이미지 일괄 생성, 9:16 비디오 렌더링까지 올인원 제어합니다.</div>', unsafe_allow_html=True)

if not selected_folder:
    st.warning("👈 왼쪽 사이드바에서 프로젝트 폴더를 생성하거나 선택해 주세요.")
    st.stop()

current_project_path = os.path.join(OUTPUTS_DIR, selected_folder)
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
        key="ref_image_uploader"
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
    st.markdown("#### 📝 제품 상세 및 대본 입력")
    
    custom_script_content = ""
    if "직접 입력" in input_mode:
        custom_script_content = st.text_area(
            "✍️ 작성하신 대본 및 씬 스토리보드 (자유 양식)",
            placeholder="""예시:
🎧 솔직히 이어폰에 몇십만 원씩 써야 할까요?
이 가격대인데 무선 블루투스 이어폰에 노이즈 캔슬링 기능까지 들어가 있습니다.
게다가 방수 기능, 통화용 내장 마이크, 그리고 USB-C 충전까지...

| 시간 | 화면 | 자막 |
|---|---|---|
| 0~3초 | 고가 이어폰 이미지 → 제품 등장 | 이어폰에 몇십만 원? |
| 3~6초 | 이어폰 케이스 오픈 | 이 가격이면? |""",
            height=200
        )
        product_url = ""
        product_text_desc = "사용자 직접 입력 대본 기반 쇼츠"
    else:
        col_in1, col_in2 = st.columns([1.5, 1])
        with col_in1:
            product_url = st.text_input(
                "🔗 상품 URL (쿠팡, 스마트스토어, Amazon 등 - 선택사항)",
                placeholder="https://www.coupang.com/vp/products/..."
            )
            product_text_desc = st.text_area(
                "📝 제품명 / 브랜드 / 핵심 특징 / 썰 키워드",
                placeholder="예: 초가성비 무선 노이즈캔슬링 블루투스 이어폰\nLED 배터리 100 잔량 표시, 생활 방수, USB-C 충전, 운동/출퇴근용",
                height=130
            )
        with col_in2:
            category_choice = st.selectbox(
                "카테고리 선택",
                ["자동 감지", "가전/디지털", "뷰티/스킨케어", "생활/청소/욕실", "주방/조리도구", "식품/간식", "패션/잡화", "여행/아웃도어", "아이디어/기타"],
                index=0
            )
            model_choice = st.selectbox(
                "분석 AI 모델",
                ["auto (OpenAI / Gemini 자동 감지)", "gemini (Gemini 3.8 Flash)", "openai (GPT-4o)"],
                index=0
            )

    st.markdown("---")
    st.markdown("#### 🚀 파이프라인 가동 선택")
    
    col_btn1, col_btn2 = st.columns([1, 1.3])
    
    with col_btn1:
        if st.button("📄 1단계만 실행: AI 기획 및 대본 생성", use_container_width=True):
            if "직접 입력" not in input_mode and not product_url and not product_text_desc.strip():
                st.error("상품 URL 또는 제품 설명 중 최소 하나를 입력해 주세요!")
            elif "직접 입력" in input_mode and not custom_script_content.strip():
                st.error("대본 내용을 입력해 주세요!")
            else:
                with st.spinner("AI가 상품 정보 수집 및 실물 사진 분석, 숏폼 서사 설계를 진행 중입니다..."):
                    try:
                        res = run_product_research(
                            product_text=product_text_desc,
                            url=product_url,
                            pipeline_type=pipeline_code,
                            category=category_choice if "직접 입력" not in input_mode else "자동 감지",
                            model_choice=model_choice.split(" ")[0] if "직접 입력" not in input_mode else "auto",
                            image_path=ref_image_path if os.path.exists(ref_image_path) else None,
                            custom_script=custom_script_content if "직접 입력" in input_mode else None
                        )
                        save_research_artifacts(current_project_path, res)
                        st.success("🎉 AI 제품 기획 및 대본 저장이 완료되었습니다! (2번 탭에서 확인)")
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
                    full_status.markdown("🔄 **[1단계]** AI 제품 조사 & 실물 사진 비전 분석 & 대본/프롬프트 생성 중...")
                    full_prog.progress(0.15)
                    res = run_product_research(
                        product_text=product_text_desc,
                        url=product_url,
                        pipeline_type=pipeline_code,
                        category=category_choice if "직접 입력" not in input_mode else "자동 감지",
                        model_choice=model_choice.split(" ")[0] if "직접 입력" not in input_mode else "auto",
                        image_path=ref_image_path if os.path.exists(ref_image_path) else None,
                        custom_script=custom_script_content if "직접 입력" in input_mode else None
                    )
                    save_research_artifacts(current_project_path, res)
                    
                    # 2. TTS 음성 생성
                    full_status.markdown("🔄 **[2단계]** Gemini TTS 고품질 나레이션 음성 합성 및 배속 인코딩 중...")
                    full_prog.progress(0.35)
                    speed_rate = 1.2 if is_product_shorts else 1.5
                    target_tts = TTS_FACTION_SCRIPT if speed_rate == 1.5 else TTS_GEN_SCRIPT
                    tts_cmd = [
                        sys.executable, target_tts, current_project_path,
                        "--engine", "gemini" if os.getenv("GEMINI_API_KEY") else "edge",
                        "--rate", str(speed_rate)
                    ]
                    subprocess.run(tts_cmd, check=True, capture_output=True, text=True)
                    
                    # 3. Whisper STT 자막 싱크
                    full_status.markdown("🔄 **[3단계]** Whisper STT 오디오 음성 분석 & 0.1초 정밀 자막 타임코드 싱크 정렬 중...")
                    full_prog.progress(0.55)
                    stt_cmd = [sys.executable, STT_ALIGN_SCRIPT, current_project_path]
                    subprocess.run(stt_cmd, check=True, capture_output=True, text=True)
                    
                    # 4. 이미지 6컷 일괄 생성 및 9:16 자동 분할
                    full_status.markdown("🔄 **[4단계]** Google Gemini Nano Banana 1x3 에셋 시트 생성 및 9:16 자동 스마트 크롭 중...")
                    full_prog.progress(0.75)
                    img_eng = "gemini" if os.getenv("GEMINI_API_KEY") else "flux"
                    batch_generate_images(
                        folder_path=current_project_path,
                        engine=img_eng,
                        mode="1x3_sheets"
                    )

                    # 5. Remotion 9:16 비디오 렌더링 (선택 시)
                    if include_remotion_render:
                        full_status.markdown("🔄 **[5단계]** Remotion 9:16 비디오 고속 렌더링 중 (Rspack 합성)...")
                        full_prog.progress(0.88)
                        render_cmd = [sys.executable, RENDER_SCRIPT, current_project_path]
                        subprocess.run(render_cmd, check=True, capture_output=True, text=True)
                    
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
    else:
        current_script_content = "1번 탭에서 AI 조사를 실행하거나, 쇼츠 대본 문장을 여기에 줄 단위로 입력하세요."

    edited_script = st.text_area(
        "대본 내용 (한 줄당 하나의 자막 씬으로 분할됩니다)",
        value=current_script_content,
        height=260,
        help="숫자는 한글 발음(예: 46g -> 사십육 그램)으로 표기되어 있는지 확인하세요."
    )

    if st.button("💾 대본 저장하기", type="primary"):
        with open(script_file_path, "w", encoding="utf-8") as f:
            f.write(edited_script.strip() + "\n")
        st.success(f"대본 저장 완료: {os.path.basename(script_file_path)}")
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
    
    has_gemini_key = bool(os.getenv("GEMINI_API_KEY"))
    col_t1, col_t2, col_t3 = st.columns([1.2, 1.2, 1])
    with col_t1:
        engine_options = (
            ["Gemini-TTS (Google GenAI, 추천)", "Edge-TTS (무료 / 즉시 사용)", "Qwen3-TTS (로컬 서버 7860)"]
            if has_gemini_key
            else ["Edge-TTS (무료 / 즉시 사용, 추천)", "Gemini-TTS (Google GenAI)", "Qwen3-TTS (로컬 서버 7860)"]
        )
        engine_choice = st.selectbox(
            "TTS 엔진 선택",
            engine_options,
            index=0
        )
        engine_code = "gemini" if "Gemini" in engine_choice else ("edge" if "Edge" in engine_choice else "qwen")

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
                    st.success("자막 싱크 분할 완료!")
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

    col_im1, col_im2 = st.columns([1.2, 1.2])
    with col_im1:
        has_gemini = bool(os.getenv("GEMINI_API_KEY"))
        img_engine_options = (
            ["Google Gemini Nano Banana (Google AI Pro/Plus, 초고화질 추천)", "FLUX.1 (Pollinations 무료/무제한)"]
            if has_gemini
            else ["FLUX.1 (초고화질 / 무료 / 즉시 사용, 추천)", "Google Gemini Nano Banana (GEMINI_API_KEY 필요)"]
        )
        img_engine = st.selectbox(
            "이미지 생성 AI 엔진",
            img_engine_options,
            index=0
        )
        img_engine_code = "gemini" if "Gemini" in img_engine else "flux"

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
            value=existing_prompts_text if existing_prompts_text else "1번 탭에서 기획을 생성하면 6개 컷 프롬프트가 자동으로 채워집니다.",
            height=180
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
    st.markdown("#### 🖼️ 생성된 9:16 쇼츠 컷 에셋 갤러리 (`assets/cut*_9_16.jpg`)")
    
    # 생성된 9:16 컷 탐색
    cut_images = sorted(glob.glob(os.path.join(current_project_path, "assets", "cut*_9_16.jpg")))
    if not cut_images:
        cut_images = sorted(glob.glob(os.path.join(current_project_path, "assets", "*.jpg")) + glob.glob(os.path.join(current_project_path, "assets", "*.png")))
        
    if cut_images:
        st.success(f"총 {len(cut_images)}개 9:16 에셋 준비 완료 (쇼츠 배경 및 I2V 영상 원본으로 즉시 사용 가능)")
        
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
                st.image(cut_p, caption=label, use_container_width=True)
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

    # 1. Remotion 자동 렌더링 섹션 (상단 메인 배치)
    col_r1, col_r2 = st.columns([2, 1])
    with col_r1:
        bg_videos = glob.glob(os.path.join(current_project_path, "video*.mp4")) + \
                    glob.glob(os.path.join(current_project_path, "background*.mp4")) + \
                    glob.glob(os.path.join(current_project_path, "scene*.mp4"))
        if bg_videos:
            st.success(f"🎬 배경 비디오 소스 감지됨 ({len(bg_videos)}개)")
        else:
            st.info("💡 동영상 클립이 없는 경우, 5번 탭에서 생성된 9:16 실사 이미지 에셋들을 기반으로 자동 조립 렌더링됩니다.")

    with col_r2:
        no_audio_opt = st.checkbox("배경 원본 오디오 보존 (--no-audio)", value=False)

    col_btn_render, col_btn_studio = st.columns([1.5, 1])
    with col_btn_render:
        if st.button("🎥 최종 9:16 비디오 렌더링 시작 (Remotion Render)", type="primary", use_container_width=True):
            if not status["scenes"]:
                st.error("먼저 4번 탭에서 `scene_data.json` 자막 데이터를 생성해 주세요!")
            else:
                with st.spinner("Remotion Rspack 번들링 및 9:16 MP4 렌더링 진행 중 (약 30~50초 소요)..."):
                    cmd = [sys.executable, RENDER_SCRIPT, current_project_path]
                    if no_audio_opt:
                        cmd.append("--no-audio")
                    res = subprocess.run(cmd, capture_output=True, text=True)
                    if res.returncode == 0:
                        st.success("🎉 Remotion 렌더링이 성공적으로 완료되었습니다!")
                        st.rerun()
                    else:
                        st.error(f"렌더링 실패:\n{res.stderr or res.stdout}")

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

    # 2. CapCut 등 외부 편집기 완성본 업로드 섹션
    with st.expander("📤 또는 캡컷(CapCut) 등 외부 편집기에서 렌더링해온 완성 MP4 파일 등록하기"):
        st.markdown("캡컷(CapCut), 프리미어 등에서 편집을 마치고 내보낸(Export) **최종 9:16 MP4 영상**을 등록하면 대시보드 플레이어에서 바로 확인하고 배포 키트를 복사할 수 있습니다.")
        uploaded_final_video = st.file_uploader(
            "완성된 쇼츠 비디오 파일 선택 (MP4 / MOV)",
            type=["mp4", "mov"],
            key="capcut_final_uploader"
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
        type=["png", "jpg", "jpeg", "webp", "mp4", "mov"]
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
    st.markdown("#### 🎬 CapCut(캡컷) 편집 패키지 원클릭 다운로드")
    st.caption("음성 파일 + 9:16 이미지 6컷 + 자막 싱크 파일(`subtitles.srt`)이 모두 포함된 CapCut 전용 패키지입니다.")
    
    col_cp1, col_cp2 = st.columns([1.5, 1])
    with col_cp1:
        if st.button("📦 CapCut 최신 패키지 빌드 / 갱신", use_container_width=True):
            ensure_capcut_package(current_project_path)
            st.success("CapCut 패키지 갱신 완료!")
            st.rerun()
            
    capcut_zip_path = os.path.join(current_project_path, "capcut_package.zip")
    if os.path.exists(capcut_zip_path):
        with col_cp2:
            with open(capcut_zip_path, "rb") as zf:
                st.download_button(
                    label="📥 CapCut 풀 패키지 (.zip) 다운로드",
                    data=zf,
                    file_name=f"{selected_folder}_capcut_package.zip",
                    mime="application/zip",
                    type="primary",
                    use_container_width=True
                )
