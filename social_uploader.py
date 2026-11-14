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
# 1. 배포 키트 파서 (publish_kit.md 분석)
# =====================================================================
def parse_publish_kit(project_folder: str) -> dict:
    """
    프로젝트 폴더 내 publish_kit.md 파일을 파싱하여
    추천 제목 리스트, 설명문, 해시태그 목록을 반환
    """
    pub_path = os.path.join(project_folder, "publish_kit.md")
    result = {
        "title": "쇼핑 쇼츠 추천 아이템 #Shorts",
        "titles": [],
        "description": "프로필 링크에서 자세한 상품 정보를 확인하세요!",
        "hashtags": "#쇼핑쇼츠 #추천템 #꿀템",
        "full_caption": ""
    }
    
    if not os.path.exists(pub_path):
        return result

    try:
        with open(pub_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 1) 제목 목록 파싱
        title_section = re.search(r'###\s*쇼츠\s*추천\s*제목.*?\n(.*?)(?=###|\Z)', content, re.DOTALL)
        if title_section:
            raw_titles = [line.strip() for line in title_section.group(1).splitlines() if line.strip()]
            titles = []
            for t in raw_titles:
                clean_t = re.sub(r'^\d+[\.\)]\s*', '', t).strip()
                if clean_t:
                    titles.append(clean_t)
            if titles:
                result["titles"] = titles
                result["title"] = titles[0]

        # 2) 설명문 파싱
        desc_section = re.search(r'###\s*영상\s*설명문.*?\n(.*?)(?=###|\Z)', content, re.DOTALL)
        if desc_section:
            desc_text = desc_section.group(1).strip()
            if desc_text:
                result["description"] = desc_text

        # 3) 해시태그 파싱
        tag_section = re.search(r'###\s*해시태그.*?\n(.*?)(?=###|\Z)', content, re.DOTALL)
        if tag_section:
            tag_text = tag_section.group(1).strip()
            if tag_text:
                result["hashtags"] = tag_text

        # 전체 캡션 조립 (설명문 + 해시태그)
        result["full_caption"] = f"{result['description']}\n\n{result['hashtags']}"

    except Exception as e:
        print(f"[!] publish_kit.md 파싱 실패: {e}")

    return result


# =====================================================================
# 2. 유튜브 쇼츠 업로더 (YouTube Data API v3)
# =====================================================================
class YouTubeUploader:
    SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

    def __init__(self):
        self.client_secret_file = self._find_client_secret()

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
        """인증 파일 준비 여부 확인"""
        return YOUTUBE_TOKEN_FILE.exists() or (self.client_secret_file is not None)

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
            if not self.client_secret_file or not os.path.exists(self.client_secret_file):
                raise FileNotFoundError(
                    "YouTube OAuth2 클라이언트 보안 비밀 파일(client_secret.json)이 필요합니다.\n"
                    "Google Cloud Console에서 다운로드하여 credentials/youtube_client_secret.json 경로에 넣어주세요."
                )
            flow = InstalledAppFlow.from_client_secrets_file(self.client_secret_file, self.SCOPES)
            creds = flow.run_local_server(port=0, prompt="consent", authorization_prompt_message="")
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
        progress_callback=None
    ) -> dict:
        """
        유튜브 쇼츠 영상 업로드
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
        return {
            "success": True,
            "video_id": video_id,
            "url": f"https://www.youtube.com/shorts/{video_id}",
            "title": upload_title,
            "privacy": privacy_status
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
