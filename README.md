# 🎬 Product Shorts Studio (쇼핑 쇼츠 자동 제작 스튜디오)

> 상품 URL이나 사진만 입력하면 **제품/회사 분석 → 스토리텔링/촬영 플랜 → 고속 TTS 음성 → Whisper STT 자막 씬 데이터(`scene_data.json`) → 실사 AI 에셋 & 영상 프롬프트 → Remotion 최종 영상 렌더링**까지 한 번에 자동 완성하는 올인원 쇼츠 제작 시스템입니다.

---

## ⚡ 빠른 시작 방법 (Quick Start)

사용자 환경과 취향에 따라 **웹 대시보드(GUI)** 또는 **대화창(AI Agent)** 중 편한 방식을 선택하여 바로 시작할 수 있습니다.

### 🎛️ 방법 1: 웹 대시보드 실행 (GUI 올인원 컨트롤러, 추천)

브라우저에서 마우스 클릭만으로 **대본 편집 → TTS 음성 생성/미리듣기 → Whisper 자막 싱크 확인 → 최종 9:16 비디오 렌더링**을 제어할 수 있습니다:

```bash
streamlit run dashboard.py
```
* 실행 즉시 브라우저에서 `http://localhost:8501`이 열립니다.
* **7대 핵심 탭 제공**:
  1. 🔍 **AI 제품 조사 & 기획**: 상품 URL 또는 제품명 입력 → 15초 시연 / 30초 썰쇼츠 자동 선택, `PRODUCT_TRUTH`, 촬영 플랜(`plan.md`), 대본(`script.md`) 자동 완성
  2. ✍️ **대본 및 플랜 편집**: `script.md` 실시간 문장 편집 및 저장
  3. 🔊 **TTS 음성 생성**: Edge-TTS(무료/초고속) 또는 Gemini-TTS 선택, 보이스 및 배속(1.2x/1.5x) 조절, 웹 오디오 플레이어로 즉시 청취
  4. 🎯 **Whisper 자막 싱크**: 원클릭 STT 정렬 실행, 씬별 자막/타임코드 시각화 테이블 확인
  5. 🎨 **AI 이미지 일괄 생성 (핵심)**: FLUX.1 / Imagen 3로 1x3 에셋 시트 2장 일괄 생성 → 1080x1920 (9:16) 6컷 개별 에셋으로 자동 슬라이스 크롭 (`assets/cut1_9_16.jpg` ~ `cut6_9_16.jpg`)
  6. 🎬 **Remotion 렌더링 & 프리뷰**: 원클릭 9:16 비디오 렌더링, 웹 비디오 플레이어로 재생 및 MP4 다운로드
  7. 📁 **에셋 및 미디어 관리**: 컷별 이미지 다운로드 및 추가 미디어 업로드

---

### 💬 방법 2: AI 대화창에서 전자동 실행 (Agent Workflow)

복잡한 설정 없이 **이 채팅창에 상품 URL이나 사진을 넣고 슬래시 커맨드를 입력**하면 AI가 전체 단계를 전자동으로 수행합니다:

* **단일 제품 시연 쇼핑쇼츠 (15초, 빠른 USP 증명)**:
  ```text
  https://상품링크주소 /product-shorts-full-pipeline
  ```
* **팩션 썰 쇼핑쇼츠 (30초, 도파민 스토리텔링/Soft Sell)**:
  ```text
  https://상품링크주소 /faction-shorts-full-pipeline
  ```
* **고속 오디오 & 자막 데이터만 생성**:
  ```text
  /tts-to-scene-pipeline
  ```

---

### 🖥️ 방법 3: 영상 실시간 캔버스 프리뷰 (Remotion Studio)

제작된 자막 텍스트의 크기, 폰트, 위치, 배경 비디오를 9:16 화면으로 보면서 실시간 튜닝하고 싶을 때:
```bash
cd my-video
npm run dev
```
* 브라우저에서 `http://localhost:3000`으로 접속하여 Remotion 플레이어를 확인합니다.

---

### ⌨️ 방법 4: CLI 터미널에서 단계별 실행

터미널에서 특정 스크립트만 개별적으로 실행할 때 사용합니다:
```bash
# 1. TTS 음성 생성 (Edge-TTS 기본 탑재 / Gemini-TTS 옵션 지원)
python .agents/skills/tts-generate/scripts/generate.py outputs/작업폴더명

# 2. Whisper STT 자막 씬 싱크 분할 (scene_data.json 생성)
python .agents/skills/stt-scene-align/scripts/align.py outputs/작업폴더명

# 3. Remotion 최종 9:16 쇼츠 비디오 렌더링
python .agents/skills/remotion-render/scripts/render.py outputs/작업폴더명
```

---

## 🌟 파이프라인 개요

Product Shorts Studio는 채널의 성격과 상품의 특성에 맞춰 **3가지 워크플로우**와 **5개의 전문 에이전트 스킬**을 제공합니다.

### 1. 2대 핵심 쇼츠 제작 파이프라인 비교

| 구분 | 1. 단일 제품 시연 쇼핑쇼츠 🛍️ | 2. 팩션(Faction) 썰 쇼핑쇼츠 📖🔥 |
|---|---|---|
| **슬래시 커맨드** | `/product-shorts-full-pipeline` | `/faction-shorts-full-pipeline` |
| **핵심 스킬** | `product-shorts-studio` | `faction-shorts-studio` |
| **핵심 컨셉** | **직접 시연 & 제품 USP 중심** (1초 만에 증명) | **재밌는 썰 스토리텔링으로 위장한 Soft Sell** |
| **영상 길이 / 배속** | **15초** / **1.2배속** TTS | **30초** / **1.5배속** TTS |
| **서사 구조** | **6비트 촬영 플랜** (결과 선공개 → 대비 → 시연 → 루프) | **4단계 팩션 서사** (도파민 후킹 → 빌드업 → 반전 → 여운) |
| **비주얼 연출** | 5-Cut 실물 누끼/사용 컷 & 손 앵커 고정 | 6-Cut 시네마틱 실사 컷 (Hands-Only & POV 룰) |
| **CTA 방식** | 루프 엔딩 + 직접적 전환 CTA | **Soft Sell** (품절 대란/군중심리 자극, 직접 CTA 지양) |
| **주요 적용 대상** | 제형/기능/비포애프터가 직관적인 상품 (뷰티, 청소 등) | 비하인드 스토리, 개발자 집착, 품절 대란이 있는 모든 상품 |

---

## 🛠️ 제공 스킬 (Agents Skills)

`.agents/skills/` 폴더 내에 탑재된 독립형 모듈들입니다:

| 스킬명 | 설명 및 주요 기능 |
|---|---|
| 🛍️ **`product-shorts-studio`** | 단일 제품 쇼츠 기획. 8대 카테고리 매핑, 15초 6비트 촬영 플랜, 5-Cut 실물/누끼 에셋 번들 생성 및 프롬프트 작성 |
| 📖 **`faction-shorts-studio`** | 팩션 썰 쇼츠 기획. 4단계 서사 구조(후킹→빌드업→클라이맥스→여운), Hands-Only & POV 룰 기반 6-Cut 종합 에셋 시트 생성 |
| 🔊 **`tts-generate`** | 다중 TTS 엔진 지원 (Edge-TTS 무료/고속, Gemini-TTS, 로컬 Qwen3-TTS) 및 FFmpeg 배속 변환 (`generate.py`) |
| 🎯 **`stt-scene-align`** | OpenAI Whisper API 연동 및 쇼츠 자막 최적화 분할. 대본 기반 한글 숫자/기호 교정 및 프레임(30fps) 정밀 동기화 (`align.py`) |
| 🎥 **`remotion-render`** | Remotion 기반 9:16 비디오 자동 렌더링. 하이브리드 비디오 모드(단일/씬별), 중앙 볼드 자막 오버레이, 원본 오디오 보존(`--no-audio`) 옵션 (`render.py`) |

---

## 📦 시스템 요구사항 및 환경 설정

### 1. 시스템 요구사항
- **Python**: `>= 3.9`
- **Node.js**: `>= 18.0.0` (Remotion 렌더링용)
- **FFmpeg**: 시스템 PATH에 등록 필수 (오디오 배속 및 비디오 최적화용)
- **TTS 엔진**:
  - ⚡ **Edge-TTS (기본값, 추천)**: 별도 설치/서버 없이 무료 & 초고속 생성
  - 🎙️ **Gemini-TTS (옵션)**: Google GenAI 음성 (`GEMINI_API_KEY` 필요)
  - 🖥️ **로컬 Qwen3-TTS (선택)**: Pinokio 등을 통해 `http://127.0.0.1:7860` 가동 시 보이스 클로닝 가능

### 2. 의존성 설치

#### Python 패키지 설치
```bash
pip install -r requirements.txt
```

#### Remotion (Node.js) 패키지 설치
```bash
cd my-video
npm install
cd ..
```

### 3. 환경 변수 설정 (.env)
루트의 `.env.example` 파일을 복사하여 `.env` 파일을 만들고 키와 설정을 입력합니다:
```bash
cp .env.example .env
```
`.env` 파일 내용:
```env
# OpenAI API Key (Whisper STT 및 자막 싱크 정렬용 - 필수)
OPENAI_API_KEY=sk-...your_openai_api_key_here...

# TTS 엔진 설정: edge (기본값, 무료/고속), gemini (Gemini API), qwen (로컬 서버)
TTS_ENGINE=edge
TTS_VOICE=ko-KR-SunHiNeural

# (선택) Gemini API Key (Gemini TTS 사용 시)
# GEMINI_API_KEY=your_gemini_api_key_here
```

---

## 📂 프로젝트 디렉토리 구조

```text
11_ShopShorts_LowCost_namdarun/
├── dashboard.py                      # 🎛️ Streamlit 통합 웹 대시보드
├── .agents/
│   ├── skills/
│   │   ├── faction-shorts-studio/    # 팩션 썰 기획 스킬
│   │   ├── product-shorts-studio/    # 단일 제품 시연 쇼츠 기획 스킬
│   │   ├── remotion-render/          # Remotion 자동 렌더링 스크립트
│   │   ├── stt-scene-align/          # Whisper STT 자막 싱크 스크립트
│   │   └── tts-generate/             # Edge/Gemini/Qwen 다중 TTS 연동 스크립트
│   └── workflows/
│       ├── faction-shorts-full-pipeline.md
│       ├── product-shorts-full-pipeline.md
│       └── tts-to-scene-pipeline.md
├── my-video/                         # Remotion React 프로젝트 (자막 오버레이 및 비디오 컴포지션)
├── outputs/                          # 파이프라인 작업별 산출물 폴더 (gitignore 대상)
├── .env.example                      # 환경변수 템플릿
├── .gitignore                        # Git 추적 제외 설정
├── reference_voice.mp3               # TTS 클로닝용 기본 레퍼런스 음성
├── requirements.txt                  # Python 의존성 목록
└── README.md                         # 프로젝트 안내 문서
```

---

## 📁 산출물 세부 구성 (`outputs/YYMMDD_HHMM/`)

| 파일명 | 용도 및 내용 |
|---|---|
| 📄 `plan.md` | 기획안 (`PRODUCT_TRUTH` / `STORY_TRUTH`), 타임라인, 훅 가이드 |
| 📄 `script.md` | TTS 및 자막용 보이스오버 대본 (발음 표기 최적화) |
| 🔊 `output_*.wav` | 1.2배속 / 1.5배속 고음질 나레이션 음성 파일 |
| 📊 `raw_stt.json` | Whisper STT 원본 타임코드 데이터 |
| 🎬 `scene_data.json` | 2~4단어 호흡으로 분할/교정된 최종 자막 씬 데이터 |
| 🖼️ `asset_sheet.jpg` | 전체 씬 에셋을 한눈에 보는 콘택트 시트 (팩션 파이프라인) |
| 📁 `assets/` | 씬별 9:16 실사 이미지 및 원본 레퍼런스 이미지 |
| 📄 `prompts.md` | Kling / Runway / Luma용 I2V 및 T2I 영상 프롬프트 |
| 📄 `publish_kit.md` | 썸네일 카피, 유튜브 쇼츠·릴스·틱톡용 제목/설명/해시태그 |
| 🎥 `output.mp4` | Remotion 스킬 실행 시 최종 완성되는 9:16 쇼츠 영상 |
