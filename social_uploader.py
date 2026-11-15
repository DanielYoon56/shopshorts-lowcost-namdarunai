# -*- coding: utf-8 -*-
"""
social_uploader.py
유튜브 쇼츠(YouTube Data API v3) 및 인스타그램 릴스(instagrapi) 자동 업로드 모듈
"""

import os
import re
import json
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# 디렉토리 경로 설정
BASE_DIR = Path(__file__).resolve().parent
CREDENTIALS_DIR = BASE_DIR / "credentials"
CREDENTIALS_DIR.mkdir(exist_ok=True)

YOUTUBE_TOKEN_FILE = CREDENTIALS_DIR / "youtube_token.json"
INSTAGRAM_SESSION_FILE = CREDENTIALS_DIR / "instagram_session.json"


# =====================================================================
# 1. 배포 키트 파서 (publish_kit.md 분석 및 스마트 자동 추출)
# =====================================================================
def parse_publish_kit(project_folder: str) -> dict:
    """
    프로젝트 폴더 내 publish_kit.md 파일을 파싱하여
    추천 제목 리스트, 설명문, 해시태그 목록을 반환.
    파일이 없거나 특정 항목이 비어있으면 대본/기획에서 스마트하게 자동 추출 및 합성.
    """
    folder_base = os.path.basename(project_folder)
    clean_name = re.sub(r'^\d+[\-_]?', '', folder_base).strip() or folder_base

    result = {
        "title": f"{clean_name} 추천템 #Shorts",
        "titles": [],
        "description": "",
        "hashtags": "",
        "full_caption": ""
    }

    # 1. 파일 탐색 (publish_kit.md 또는 배포 관련 마크다운)
    pub_path = os.path.join(project_folder, "publish_kit.md")
    if not os.path.exists(pub_path):
        import glob
        cands = glob.glob(os.path.join(project_folder, "*publish*.md")) + glob.glob(os.path.join(project_folder, "*배포*.md"))
        if cands:
            pub_path = cands[0]

    content = ""
    if os.path.exists(pub_path):
        try:
            with open(pub_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            print(f"[!] publish_kit.md 읽기 실패: {e}")

    if content:
        # 1) 제목 목록 파싱 (제목, Title, 쇼츠 제목 등 다양한 포맷 지원)
        title_section = re.search(r'#{1,4}\s*.*?(?:제목|title).*?\n(.*?)(?=#{1,4}|\Z)', content, re.DOTALL | re.IGNORECASE)
        if title_section:
            raw_titles = [line.strip() for line in title_section.group(1).splitlines() if line.strip()]
            for t in raw_titles:
                clean_t = re.sub(r'^(\d+[\.\)]|\-|\*)\s*', '', t).strip(' "\'#')
                if clean_t and len(clean_t) > 3 and not clean_t.startswith("#"):
                    result["titles"].append(clean_t)

        # 2) 설명문 파싱 (설명문, 상세 설명문, 설명, Description 등)
        desc_section = re.search(r'#{1,4}\s*.*?(?:설명문|설명|description|본문).*?\n(.*?)(?=#{1,4}|\Z)', content, re.DOTALL | re.IGNORECASE)
        if desc_section:
            desc_text = desc_section.group(1).strip()
            if desc_text:
                result["description"] = desc_text

        # 3) 해시태그 파싱
        tag_section = re.search(r'#{1,4}\s*.*?(?:해시\s*태그|태그|hashtag).*?\n(.*?)(?=#{1,4}|\Z)', content, re.DOTALL | re.IGNORECASE)
        if tag_section:
            tag_text = tag_section.group(1).strip()
            if tag_text:
                result["hashtags"] = tag_text
        if not result["hashtags"]:
            # 본문에서 #태그만 모두 정규식 추출
            all_tags = re.findall(r'#[\w가-힣]+', content)
            if all_tags:
                result["hashtags"] = " ".join(all_tags)

    # 4. 폴백: script.md / plan.md / whisper / scene_data 기반 보완
    script_first_line = ""
    script_full_text = ""
    s_path = os.path.join(project_folder, "script.md")
    if os.path.exists(s_path):
        try:
            with open(s_path, "r", encoding="utf-8") as sf:
                s_lines = [l.strip() for l in sf.read().splitlines() if l.strip()]
                if s_lines:
                    script_first_line = s_lines[0]
                    script_full_text = "\n".join(s_lines)
        except Exception:
            pass
    elif os.path.exists(os.path.join(project_folder, "whisper_transcription.json")):
        try:
            with open(os.path.join(project_folder, "whisper_transcription.json"), "r", encoding="utf-8") as wf:
                w_data = json.load(wf)
                script_full_text = w_data.get("text", "")
                if "?" in script_full_text:
                    script_first_line = script_full_text.split("?")[0] + "?"
                else:
                    script_first_line = script_full_text[:35]
        except Exception:
            pass

    # 제목 보완
    if not result["titles"]:
        if script_first_line:
            clean_s1 = re.sub(r'^[^\w가-힣\?]+', '', script_first_line).strip()
            result["titles"].append(clean_s1)
        result["titles"].append(f"{clean_name} 써보고 진짜 놀란 3가지 이유! #Shorts")
        result["titles"].append(f"역대급 가성비 {clean_name} 솔직 후기")
    result["title"] = result["titles"][0]

    # 설명문 보완
    if not result["description"]:
        if script_full_text:
            result["description"] = f"{script_full_text[:140]}...\n\n👉 더 자세한 제품 정보와 할인은 프로필 링크를 확인해 보세요!"
        else:
            result["description"] = f"{clean_name} 실사용 솔직 후기 및 추천 영상입니다.\n더 자세한 제품 정보와 할인은 프로필 링크를 참조하세요!"

    # 해시태그 보완
    if not result["hashtags"]:
        tag_prod = re.sub(r'[^\w가-힣]', '', clean_name)
        result["hashtags"] = f"#{tag_prod} #쇼핑쇼츠 #추천템 #꿀템추천 #내돈내산 #가성비추천 #Shorts"

    # 전체 캡션 조립
    result["full_caption"] = f"{result['description']}\n\n{result['hashtags']}".strip()
    return result


# =====================================================================
# 2. 유튜브 쇼츠 업로더 (YouTube Data API v3)
# =====================================================================
class YouTubeUploader:
    SCOPES = [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube.force-ssl",
        "https://www.googleapis.com/auth/youtube",
        "https://www.googleapis.com/auth/youtube.readonly",
    ]

    def __init__(self):
        self.client_secret_file = self._find_client_secret()

    def logout(self):
        """저장된 토큰 삭제하여 다른 계정/브랜드 채널로 재인증할 수 있도록 함"""
        if YOUTUBE_TOKEN_FILE.exists():
            try:
                os.remove(YOUTUBE_TOKEN_FILE)
                return True
            except Exception as e:
                print(f"[!] 토큰 삭제 실패: {e}")
        return False

    def get_channel_info(self) -> dict | None:
        """현재 연결된 채널 이름 및 정보 조회"""
        if not self.is_authenticated():
            return None
        try:
            service = self.get_service()
            response = service.channels().list(mine=True, part="snippet").execute()
            items = response.get("items", [])
            if items:
                snippet = items[0].get("snippet", {})
                return {
                    "id": items[0].get("id"),
                    "title": snippet.get("title", ""),
                    "description": snippet.get("description", ""),
                    "customUrl": snippet.get("customUrl", ""),
                }
        except Exception as e:
            # 기존 구형 토큰 등으로 인한 권한 부족 시 조용히 넘김
            print(f"[!] 채널 정보 조회 오류 (재인증 권장): {e}")
        return None

    def _find_client_secret(self) -> str | None:
        """credentials 폴더 또는 루트에서 client_secret.json 탐색"""
        env_path = os.getenv("YOUTUBE_CLIENT_SECRET_FILE")
        if env_path and os.path.exists(env_path):
            return env_path
            
        cand_files = [
            CREDENTIALS_DIR / "youtube_client_secret.json",
            CREDENTIALS_DIR / "client_secret.json",
            BASE_DIR / "client_secret.json",
        ]
        for c in cand_files:
            if c.exists():
                return str(c)

        # 패턴 검색
        for f in CREDENTIALS_DIR.glob("*client_secret*.json"):
            return str(f)
        for f in BASE_DIR.glob("*client_secret*.json"):
            return str(f)
            
        return None

    def is_configured(self) -> bool:
        """인증 파일 또는 환경변수 설정 여부 확인"""
        has_env_credentials = bool(os.getenv("YOUTUBE_CLIENT_ID") and os.getenv("YOUTUBE_CLIENT_SECRET"))
        return YOUTUBE_TOKEN_FILE.exists() or (self.client_secret_file is not None) or has_env_credentials

    def is_authenticated(self) -> bool:
        """유효한 토큰 보유 여부 확인"""
        if not YOUTUBE_TOKEN_FILE.exists():
            return False
        try:
            from google.oauth2.credentials import Credentials
            creds = Credentials.from_authorized_user_file(str(YOUTUBE_TOKEN_FILE), self.SCOPES)
            return creds.valid or (creds.expired and creds.refresh_token is not None)
        except Exception:
            return False

    def get_service(self):
        """Google API 서비스 인스턴스 획득"""
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        creds = None
        if YOUTUBE_TOKEN_FILE.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(YOUTUBE_TOKEN_FILE), self.SCOPES)
            except Exception as e:
                print(f"[!] 기존 토큰 로드 실패: {e}")

        # 유효하지 않거나 만료된 경우 갱신
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open(YOUTUBE_TOKEN_FILE, "w", encoding="utf-8") as f:
                    f.write(creds.to_json())
            except Exception as e:
                print(f"[!] 토큰 갱신 실패, 재인증 필요: {e}")
                creds = None

        # 새로 인증해야 하는 경우
        if not creds or not creds.valid:
            client_id = os.getenv("YOUTUBE_CLIENT_ID", "").strip()
            client_secret = os.getenv("YOUTUBE_CLIENT_SECRET", "").strip()

            if client_id and client_secret:
                # .env 환경변수를 이용한 인메모리 OAuth2 Flow
                client_config = {
                    "installed": {
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "redirect_uris": ["http://localhost"]
                    }
                }
                flow = InstalledAppFlow.from_client_config(client_config, self.SCOPES)
            elif self.client_secret_file and os.path.exists(self.client_secret_file):
                flow = InstalledAppFlow.from_client_secrets_file(self.client_secret_file, self.SCOPES)
            else:
                raise FileNotFoundError(
                    "YouTube 업로드를 위한 OAuth2 설정이 필요합니다.\n"
                    "다음 두 가지 방법 중 하나를 선택하세요:\n"
                    "1) .env 파일에 YOUTUBE_CLIENT_ID 및 YOUTUBE_CLIENT_SECRET 등록\n"
                    "2) Google Cloud Console에서 다운로드한 client_secret.json을 credentials/ 폴더에 저장"
                )

            flow_run = getattr(flow, 'run_local_server', None)
            if flow_run:
                # select_account consent: 여러 채널/브랜드 계정이 있을 때 채널 선택 화면을 강제로 띄움
                creds = flow.run_local_server(port=0, prompt="select_account consent", authorization_prompt_message="")
            else:
                creds = flow.run_console()

            with open(YOUTUBE_TOKEN_FILE, "w", encoding="utf-8") as f:
                f.write(creds.to_json())

        return build("youtube", "v3", credentials=creds)

    def upload_shorts(
        self,
        video_path: str,
        title: str,
        description: str = "",
        tags: list = None,
        privacy_status: str = "public",
        thumbnail_path: str = None,
        progress_callback=None
    ) -> dict:
        """
        유튜브 쇼츠 영상 업로드 (맞춤 썸네일 지원)
        privacy_status: 'public', 'unlisted', 'private'
        """
        from googleapiclient.http import MediaFileUpload

        if not os.path.exists(video_path):
            raise FileNotFoundError(f"업로드할 비디오 파일이 없습니다: {video_path}")

        # 쇼츠 인식 보장을 위해 제목에 #Shorts 포함 확인
        upload_title = title.strip()
        if "#Shorts" not in upload_title and "#shorts" not in upload_title:
            if len(upload_title) + 8 <= 100:
                upload_title = f"{upload_title} #Shorts"

        upload_title = upload_title[:100]  # 유튜브 제목 100자 제한

        if tags is None:
            # 설명문 또는 제목에서 해시태그 추출
            found_tags = re.findall(r'#([A-Za-z0-9가-힣_-]+)', f"{title} {description}")
            tags = list(dict.fromkeys(found_tags))[:20]

        service = self.get_service()

        body = {
            "snippet": {
                "title": upload_title,
                "description": description,
                "tags": tags,
                "categoryId": "22"  # People & Blogs (쇼츠 커머스 기본)
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False
            }
        }

        # 5MB 청크 단위 재개 가능한 업로드
        media = MediaFileUpload(video_path, chunksize=5 * 1024 * 1024, resumable=True, mimetype="video/mp4")
        request = service.videos().insert(part="snippet,status", body=body, media_body=media)

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status and progress_callback:
                progress = status.progress()
                progress_callback(progress)

        video_id = response.get("id")

        # 썸네일 업로드 처리 (YouTube 2MB 제한 준수 및 인코딩 등록 대기 3회 재시도)
        thumbnail_uploaded = False
        thumbnail_note = ""
        if thumbnail_path and os.path.exists(thumbnail_path):
            if progress_callback:
                progress_callback(0.96)

            # [핵심] YouTube Data API의 엄격한 2MB(2,097,152 바이트) 파일 크기 제한 보장
            actual_thumb_path = thumbnail_path
            temp_thumb_jpg = None
            try:
                file_size = os.path.getsize(thumbnail_path)
                # 1.9MB 이상이거나 PNG 파일인 경우, 안전하게 고화질 JPEG(약 400~800KB)로 자동 최적화 변환
                if file_size >= 1950000 or thumbnail_path.lower().endswith(".png"):
                    from PIL import Image
                    temp_thumb_jpg = os.path.join(os.path.dirname(thumbnail_path), "_yt_thumb_optimized.jpg")
                    with Image.open(thumbnail_path) as im:
                        im.convert("RGB").save(temp_thumb_jpg, "JPEG", quality=90, optimize=True)
                    actual_thumb_path = temp_thumb_jpg
                    print(f"[*] YouTube 썸네일 2MB 규격 자동 최적화: {file_size:,}B -> {os.path.getsize(actual_thumb_path):,}B")
            except Exception as opt_err:
                print(f"[!] 썸네일 최적화 변환 실패 (원본 사용): {opt_err}")

            mime_t = "image/jpeg" if actual_thumb_path.lower().endswith((".jpg", ".jpeg")) else "image/png"
            
            # 유튜브 백엔드에서 비디오 ID 생성 직후 썸네일을 즉시 붙이면 거부되거나 덮어쓰여질 수 있으므로 재시도 처리
            for attempt in range(1, 4):
                try:
                    time.sleep(attempt * 2)  # 2초, 4초, 6초 지연 후 시도
                    thumb_media = MediaFileUpload(actual_thumb_path, mimetype=mime_t)
                    service.thumbnails().set(videoId=video_id, media_body=thumb_media).execute()
                    thumbnail_uploaded = True
                    thumbnail_note = "정상 등록 완료"
                    print(f"[+] YouTube 맞춤 썸네일 등록 성공! (시도 {attempt}회)")
                    break
                except Exception as te:
                    thumbnail_note = str(te)
                    print(f"[!] YouTube 썸네일 등록 시도 {attempt}회 실패: {te}")

            # 임시 최적화 파일 정리
            if temp_thumb_jpg and os.path.exists(temp_thumb_jpg):
                try:
                    os.remove(temp_thumb_jpg)
                except Exception:
                    pass

        return {
            "success": True,
            "video_id": video_id,
            "url": f"https://www.youtube.com/shorts/{video_id}",
            "title": upload_title,
            "privacy": privacy_status,
            "thumbnail_uploaded": thumbnail_uploaded,
            "thumbnail_note": thumbnail_note
        }


# =====================================================================
# 3. 인스타그램 릴스 업로더 (instagrapi)
# =====================================================================
class InstagramUploader:
    def __init__(self):
        self.session_file = INSTAGRAM_SESSION_FILE

    def is_authenticated(self) -> bool:
        """저장된 세션 파일 존재 여부"""
        return self.session_file.exists()

    def get_client(self, username: str = None, password: str = None, verification_code: str = None):
        """instagrapi Client 인스턴스 획득 및 로그인"""
        from instagrapi import Client

        cl = Client()
        cl.delay_range = [2, 5]  # 안정적인 API 딜레이

        # 1. 기존 세션 파일 재사용 시도
        if self.session_file.exists():
            try:
                cl.load_settings(str(self.session_file))
                # 세션 유효성 테스트
                cl.get_timeline_feed()
                return cl
            except Exception as e:
                print(f"[*] 기존 인스타그램 세션 만료 또는 무효, 재로그인 시도: {e}")

        # 2. 신규 로그인 진행
        user = username or os.getenv("INSTAGRAM_USERNAME")
        pwd = password or os.getenv("INSTAGRAM_PASSWORD")

        if not user or not pwd:
            raise ValueError("인스타그램 아이디(Username)와 비밀번호가 필요합니다.")

        if verification_code:
            cl.login(user, pwd, verification_code=verification_code)
        else:
            cl.login(user, pwd)

        # 세션 저장
        cl.dump_settings(str(self.session_file))
        return cl

    def upload_reels(
        self,
        video_path: str,
        caption: str,
        thumbnail_path: str = None,
        username: str = None,
        password: str = None,
        verification_code: str = None,
        progress_callback=None
    ) -> dict:
        """
        인스타그램 릴스(Reels) 영상 업로드
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"업로드할 비디오 파일이 없습니다: {video_path}")

        if progress_callback:
            progress_callback(0.1, "인스타그램 로그인 및 세션 확인 중...")

        cl = self.get_client(username=username, password=password, verification_code=verification_code)

        if progress_callback:
            progress_callback(0.4, "릴스 비디오 업로드 및 트랜스코딩 중...")

        thumb = thumbnail_path if (thumbnail_path and os.path.exists(thumbnail_path)) else None
        
        # 릴스 업로드 실행 (clip_upload)
        media = cl.clip_upload(
            path=video_path,
            caption=caption,
            thumbnail=thumb
        )

        if progress_callback:
            progress_callback(1.0, "릴스 업로드 완료!")

        code = getattr(media, "code", "")
        media_id = getattr(media, "id", "")
        reel_url = f"https://www.instagram.com/reel/{code}/" if code else "https://www.instagram.com/"

        return {
            "success": True,
            "media_id": str(media_id),
            "code": code,
            "url": reel_url,
            "caption": caption
        }


# 싱글톤 인스턴스
youtube_uploader = YouTubeUploader()
instagram_uploader = InstagramUploader()

