---
name: coupang-crawler
description: 쿠팡 상품 상세 정보(상품명·브랜드·판매가/정가/할인율·평점·리뷰수·배송·옵션·필수표기정보·썸네일/상세 이미지)를 JSON으로 수집한다. 브라우저에서 저장한 상품 페이지(.html/.mhtml) 파싱과 쿠팡 파트너스 Open API(키워드 검색·파트너스 링크 변환)를 지원한다. 쿠팡 상품 크롤링, 상품 상세 정보 추출, 쇼핑 쇼츠용 PRODUCT_TRUTH 사실 데이터, 파트너스 링크가 필요할 때 사용한다.
argument-hint: "저장한 쿠팡 상품 페이지 파일 경로 또는 검색 키워드"
---

# coupang-crawler — 쿠팡 상품 상세 수집

## 왜 '저장 HTML' 방식인가
쿠팡은 Akamai 봇 차단으로 브라우저가 아닌 요청을 `robots.txt` 포함 전부 **HTTP 403**으로 막는다.
이 스킬은 차단을 우회(헤드리스 스텔스, 지문 위조, 쿠키 탈취, 프록시 회전)하지 않는다.
대신 사용자가 **자기 브라우저로 정상 열람한 페이지**를 저장하면 그 파일에서 상세 정보를 뽑는다.

## 모드 1 — 저장한 상품 페이지 파싱 (상세 정보 전체)

1. 크롬에서 쿠팡 상품 페이지를 연다. 옵션을 고를 상품이면 원하는 옵션을 선택한다.
2. **페이지 맨 아래까지 스크롤**해 상세 이미지가 로드되게 한다 (상세 이미지 수집용).
3. `Ctrl+S` → 형식 **"웹페이지, 단일 파일(.mhtml)"** 또는 "웹페이지, HTML만"으로 저장한다.
4. 실행:

   ```powershell
   python .agents\skills\coupang-crawler\scripts\coupang_crawler.py html --file "C:\Downloads\상품.mhtml" --output "outputs\{project}\coupang-product.json"
   ```

   대시보드 1번 탭에서도 같은 파일을 업로드하면 자동으로 파싱되어 AI 기획에 반영된다.

### 출력 필드 (`fields`)
`title`, `brand`, `description`, `product_id`, `item_id`, `vendor_item_id`, `sku`,
`sale_price`, `original_price`, `discount_rate`, `unit_price`, `currency`, `availability`, `rating`, `review_count`,
`seller`, `seller_rating`, `courier`, `shipping`, `arrival`, `category_path[]`,
`options[{group,name,price_delta,sold_out}]`, `bullet_points[]`, `specs[{name,value}]`,
`gallery_images[]`(대표 이미지, 640x640 통일), `detail_images[]`(상세 설명 이미지)

- 2026-11 실제 쿠팡 저장 페이지 기준 DOM(`.prod-atf` 메인 구매 영역, `.final-price-amount`, `.rating-star-num`, `.instant-option-v2`, `#itemBrief`, `.subType-IMAGE`)에 맞춰져 있다.
- 가격·평점·판매자·옵션은 메인 구매 영역(`.prod-atf`) 안에서만 읽어, 아래쪽 추천/광고 상품 값이 섞이지 않는다. 상품 ID도 자기 상품번호 링크에서만 읽는다.
- 할인 중이 아니면 `original_price`/`discount_rate`는 비어 있다. 브랜드는 페이지에 표기된 경우에만 채워진다.
- JSON-LD/og 메타가 있으면 대체 경로로 사용한다. 쿠팡 마크업이 바뀌면 해당 필드만 비므로, 빈 값이 늘면 새로 저장한 파일로 선택자를 갱신한다.
- 이미지 주소는 쿠팡 CDN만 남기고 쿼리 문자열을 제거한다.
- `notes[]`에 누락 원인 안내가 들어간다.

## 모드 1-b — 상세 이미지 OCR 스펙 추출 (LLM 미사용)

쿠팡 상품은 필수 표기정보가 "상세페이지 참조"뿐이고 실제 스펙이 상세 이미지 안에만 있는 경우가 많다.
`.mhtml`에는 상세 이미지 원본이 함께 저장되므로 쿠팡에 다시 접속하지 않고 OCR 한다.

```powershell
pip install rapidocr onnxruntime   # 최초 1회 (CPU, 한국어 PP-OCRv5 mobile 모델 자동 다운로드)
python .agents\skills\coupang-crawler\scripts\coupang_ocr.py --product-json "outputs\{project}\coupang-product.json" --mhtml "C:\Downloads\상품.mhtml" --output "outputs\{project}\coupang-ocr.json"
```

- 세로로 긴 상세 이미지를 1000px 단위(120px 겹침)로 잘라 OCR → 정규식으로 `specs`(단계·타이머·온도·W·V·크기·무게·용량·방수), `features`, `certifications`, `purchase_notes`(해외직구·변환플러그·반품 제한) 추출. 모든 항목에 근거 문장(`evidence`)과 출처 이미지가 붙는다.
- `conflicts`: 상품명과 상세 이미지의 같은 항목 단계 수가 다르면 경고 (예: 상품명 "온도조절 4단계" vs 이미지 "9단계 온도 조절").
- 대시보드 1번 탭의 "상세 이미지 OCR 스펙 추출" 버튼과 같은 기능이며, 결과는 AI 기획 프롬프트에 자동 포함된다.
- 이미지 10장 기준 CPU 약 40초. 장식 폰트·사진 위 글자는 오인식될 수 있으므로 결과는 '후보'로 취급한다.

## 모드 2 — 쿠팡 파트너스 Open API (`.env` 키 필요)

`.env`에 `COUPANG_ACCESS_KEY`, `COUPANG_SECRET_KEY` (쿠팡 파트너스 > 추가기능 > Open API)를 넣는다.

```powershell
# 키워드 검색: 상품명·가격·대표이미지·로켓배송 여부·파트너스 링크 (최대 10개)
python .agents\skills\coupang-crawler\scripts\coupang_crawler.py search --keyword "무선 이어폰" --limit 5 --output "outputs\{project}\coupang-search.json"

# 상품 URL -> 파트너스 단축 링크 (쇼츠 설명란/고정댓글용)
python .agents\skills\coupang-crawler\scripts\coupang_crawler.py deeplink --url "https://www.coupang.com/vp/products/123?vendorItemId=456"
```

- 검색 API는 쿠팡 측 호출 한도(시간당 제한)가 있으므로 반복 호출하지 않는다.
- 검색 API는 상세 설명·옵션·리뷰를 주지 않는다. 상세가 필요하면 모드 1을 쓴다.

## 결과 사용 규칙
- 결과는 `PRODUCT_TRUTH` 초안으로만 쓴다. 페이지에 없는 효능·성능·후기를 지어내지 않는다.
- 가격·할인·재고·배송은 수집 시점 값이다. 영상/설명란에 쓰기 전 다시 확인한다.
- 비어 있는 필드는 추측으로 채우지 않는다.
- 쇼츠 설명란 링크는 파트너스 정책에 따라 대가성 문구("이 포스팅은 쿠팡 파트너스 활동의 일환으로…")를 함께 넣는다.
