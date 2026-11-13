#!/usr/bin/env python
"""쿠팡 상품 상세 수집기.

쿠팡은 브라우저가 아닌 HTTP 요청을 Akamai 단에서 403으로 차단하므로, 이 도구는
봇 차단을 우회하지 않고 아래 두 가지 정당한 경로로만 상품 정보를 얻는다.

1. html   : 사용자가 자신의 브라우저에서 저장한 상품 상세 페이지(.html / .htm / .mhtml) 파싱
2. search : 쿠팡 파트너스 Open API(HMAC 인증)로 키워드 검색
   deeplink : 쿠팡 파트너스 Open API로 상품 URL -> 파트너스 단축 링크 변환
"""

from __future__ import annotations

import argparse
import email
import hashlib
import hmac
import json
import os
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

PARTNERS_HOST = "https://api-gateway.coupang.com"
PARTNERS_BASE = "/v2/providers/affiliate_open_api/apis/openapi/v1"
IMAGE_HOSTS = ("coupangcdn.com", "coupang.com")
MAX_IMAGES = 40


class CrawlerError(Exception):
    """사용자에게 그대로 보여줘도 되는 실패."""


# ---------------------------------------------------------------------------
# 공통 유틸
# ---------------------------------------------------------------------------

def clean_text(value: object) -> str:
    text = re.sub(r"<[^>]*>", " ", str(value or ""))
    return re.sub(r"\s+", " ", text).strip()


def parse_price(value: object) -> int | None:
    digits = re.sub(r"[^\d]", "", str(value or ""))
    return int(digits) if digits else None


def is_coupang_host(hostname: str, hosts: tuple[str, ...] = IMAGE_HOSTS) -> bool:
    hostname = (hostname or "").lower().rstrip(".")
    return any(hostname == h or hostname.endswith("." + h) for h in hosts)


def normalize_image_url(src: str, base_url: str = "https://www.coupang.com/") -> str:
    """쿠팡 CDN 이미지 주소만 https + 쿼리 제거 형태로 정규화. 아니면 빈 문자열."""
    src = (src or "").strip()
    if not src or src.startswith("data:"):
        return ""
    if src.startswith("//"):
        src = "https:" + src
    parsed = urlsplit(urljoin(base_url, src))
    if parsed.scheme not in ("http", "https") or not is_coupang_host(parsed.hostname or ""):
        return ""
    return urlunsplit(("https", (parsed.hostname or "").lower(), parsed.path, "", ""))


def dedupe(items: list[str], limit: int = MAX_IMAGES) -> list[str]:
    out: list[str] = []
    for item in items:
        if item and item not in out:
            out.append(item)
        if len(out) >= limit:
            break
    return out


def canonical_product_url(url: str) -> str:
    parsed = urlsplit(url or "")
    if not is_coupang_host(parsed.hostname or "", ("coupang.com",)):
        return ""
    keep = [
        (k, v) for k, v in parse_qsl(parsed.query)
        if k.lower() in {"itemid", "vendoritemid"}
    ]
    return urlunsplit(("https", "www.coupang.com", parsed.path, urlencode(keep), ""))


# ---------------------------------------------------------------------------
# 1) 브라우저 저장 HTML 파싱
# ---------------------------------------------------------------------------
# 쿠팡 상품 상세 신규 DOM (2026-11 실제 저장 페이지 기준) 주요 영역
#   div.prod-atf            : 메인 구매 영역 (제목/가격/평점/배송/판매자/옵션)
#                             -> 아래쪽 추천·광고 상품 값과 섞이지 않게 하는 기준
#   h1.product-title        : 상품명
#   .final-price-amount     : 최종 판매가 / .sales-price-amount : 할인 전 가격(할인 중일 때만 값 존재)
#   .rating-star-num        : style="width: 90%" -> 평점 4.5 / .rating-count-txt : "4 개 상품평"
#   .shipping-fee-desc, .regular-pdd-container, .seller-info, .instant-option-v2 > section
#   img.thumbnail, .product-image img : 대표 이미지 / #itemBrief table : 필수 표기 정보
#   .subType-IMAGE img      : 상세 설명 이미지

VOID_TAGS = {"img", "meta", "link", "br", "input", "hr", "source", "area", "base", "col", "embed", "param", "track", "wbr"}
SKIP_TEXT_TAGS = {"script", "style", "noscript", "svg", "template"}
NON_PRODUCT_IMAGE_MARKERS = ("/mobile_app/", "/dragonstone/", "/cmg/", "/badge", "/icon", "_icon", "/sprite")
THUMB_SIZE_RE = re.compile(r"/thumbnails/remote/[^/]+/")


class Frame:
    __slots__ = ("tag", "classes", "id", "uid")

    def __init__(self, tag: str, classes: frozenset, id_: str, uid: int) -> None:
        self.tag, self.classes, self.id, self.uid = tag, classes, id_, uid


class FlatDomParser(HTMLParser):
    """HTML을 '텍스트 노드 + 조상 요소 스택' 목록으로 평탄화한다.

    추출은 '어떤 클래스/ID 영역 안의 텍스트·이미지' 질의로 하므로 마크업 일부가 바뀌어도 견고하다.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: tuple[Frame, ...] = ()
        self.texts: list[tuple[str, tuple[Frame, ...]]] = []
        self.images: list[tuple[dict, tuple[Frame, ...]]] = []
        self.styles: list[tuple[str, tuple[Frame, ...]]] = []
        self.meta: dict[str, str] = {}
        self.json_ld: list[str] = []
        self.canonical = ""
        self.title_tag = ""
        self._uid = 0
        self._skip = 0
        self._json_buf: list[str] | None = None
        self._in_title = False

    def handle_starttag(self, tag, attrs_list):
        tag = tag.lower()
        attrs = {k.lower(): (v or "") for k, v in attrs_list}
        if tag == "meta":
            key = (attrs.get("property") or attrs.get("name") or attrs.get("itemprop") or "").lower()
            if key and attrs.get("content"):
                self.meta.setdefault(key, attrs["content"].strip())
            return
        if tag == "link":
            if "canonical" in attrs.get("rel", "").lower() and not self.canonical:
                self.canonical = attrs.get("href", "")
            return
        if tag == "img":
            self.images.append((attrs, self.stack))
            return
        if tag in VOID_TAGS:
            return
        if tag == "title":
            self._in_title = True
        if tag == "script" and "ld+json" in attrs.get("type", "").lower():
            self._json_buf = []
        elif tag in SKIP_TEXT_TAGS:
            self._skip += 1
        self._uid += 1
        frame = Frame(tag, frozenset(attrs.get("class", "").split()), attrs.get("id", ""), self._uid)
        self.stack = self.stack + (frame,)
        if attrs.get("style"):
            self.styles.append((attrs["style"], self.stack))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag.lower() not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in VOID_TAGS:
            return
        if tag == "title":
            self._in_title = False
        if tag == "script" and self._json_buf is not None:
            self.json_ld.append("".join(self._json_buf))
            self._json_buf = None
        elif tag in SKIP_TEXT_TAGS and self._skip:
            self._skip -= 1
        # 짝이 안 맞는 태그는 가장 가까운 같은 태그까지 닫는다
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i].tag == tag:
                self.stack = self.stack[:i]
                break

    def handle_data(self, data):
        if self._in_title:
            self.title_tag += data
        if self._json_buf is not None:
            self._json_buf.append(data)
            return
        if self._skip:
            return
        text = clean_text(data)
        if text:
            self.texts.append((text, self.stack))


def _in(stack: tuple[Frame, ...], key: str) -> bool:
    """key: '.class' / '#id' / 'tag'"""
    if key.startswith("."):
        return any(key[1:] in f.classes for f in stack)
    if key.startswith("#"):
        return any(f.id == key[1:] for f in stack)
    return any(f.tag == key for f in stack)


def _nearest(stack: tuple[Frame, ...], tag: str) -> Frame | None:
    for f in reversed(stack):
        if f.tag == tag:
            return f
    return None


class CoupangDom:
    def __init__(self, html: str) -> None:
        self.p = FlatDomParser()
        self.p.feed(html)
        self.p.close()
        # 메인 구매 영역이 있으면 그 안으로 한정 (없으면 페이지 전체 = 구버전 DOM)
        self.main = ".prod-atf" if any(_in(s, ".prod-atf") for _, s in self.p.texts) else None

    def texts(self, *keys: str, main: bool = True) -> list[str]:
        out = []
        for text, stack in self.p.texts:
            if main and self.main and not _in(stack, self.main):
                continue
            if all(_in(stack, k) for k in keys):
                out.append(text)
        return out

    def text(self, *keys: str, main: bool = True) -> str:
        return " ".join(self.texts(*keys, main=main)).strip()

    def first(self, keys_list: tuple[tuple[str, ...], ...], main: bool = True) -> str:
        for keys in keys_list:
            value = self.text(*keys, main=main)
            if value:
                return value
        return ""


def _image_src(attrs: dict) -> str:
    return attrs.get("data-img-src") or attrs.get("data-src") or attrs.get("src") or ""


def _is_product_image(url: str) -> bool:
    return bool(url) and not any(m in url.lower() for m in NON_PRODUCT_IMAGE_MARKERS)


def _gallery_size(url: str) -> str:
    """썸네일 크기 변형(48x48ex, 120x120ex ...)을 640x640ex 하나로 통일해 중복 제거."""
    return THUMB_SIZE_RE.sub("/thumbnails/remote/640x640ex/", url, count=1)


def _flatten_ld(value: object) -> list[dict]:
    out: list[dict] = []
    if isinstance(value, list):
        for v in value:
            out.extend(_flatten_ld(v))
    elif isinstance(value, dict):
        out.append(value)
        for key in ("@graph", "mainEntity", "itemListElement", "hasVariant"):
            if key in value:
                out.extend(_flatten_ld(value[key]))
    return out


def _ld_product(blocks: list[str]) -> dict:
    for block in blocks:
        try:
            data = json.loads(block.strip())
        except (json.JSONDecodeError, TypeError):
            continue
        for item in _flatten_ld(data):
            types = item.get("@type", [])
            types = [types] if isinstance(types, str) else types
            if any(str(t).lower().endswith("product") for t in types):
                return item
    return {}


def read_saved_page(path: Path) -> str:
    """.html/.htm 또는 크롬 '웹페이지, 단일 파일'(.mhtml)에서 HTML 본문을 꺼낸다."""
    raw = path.read_bytes()
    head = raw[:3000].lower()
    if path.suffix.lower() in (".mhtml", ".mht") or b"multipart/related" in head:
        msg = email.message_from_bytes(raw)
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
        raise CrawlerError("MHTML 파일 안에서 HTML 본문을 찾지 못했습니다.")
    for enc in ("utf-8", "cp949"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _parse_options(dom: CoupangDom) -> list[dict]:
    """.instant-option-v2 > section 마다 '라벨: 선택값' + 옵션 항목(추가금/품절)을 구조화."""
    groups: dict[int, list[str]] = {}
    for text, stack in dom.p.texts:
        if not _in(stack, ".instant-option-v2"):
            continue
        section = _nearest(stack, "section")
        groups.setdefault(section.uid if section else 0, []).append(text)

    options: list[dict] = []
    for texts in groups.values():
        label, rest = "", texts
        if texts and texts[0].endswith(":"):
            label = texts[0].rstrip(":").strip()
            rest = texts[2:]  # texts[1] = 현재 선택값 (아래 목록에 다시 나옴)
        for t in rest:
            if re.fullmatch(r"[+-]\s?[\d,]+원", t) and options:
                options[-1]["price_delta"] = parse_price(t) * (-1 if t.startswith("-") else 1)
            elif t in ("일시품절", "품절") and options:
                options[-1]["sold_out"] = True
            else:
                options.append({"group": label, "name": t, "price_delta": 0, "sold_out": False})
    if not options:  # 구버전 DOM
        for t in dom.texts(".prod-option__item"):
            options.append({"group": "", "name": t, "price_delta": 0, "sold_out": "품절" in t})
    return options[:60]


def _parse_specs(dom: CoupangDom) -> list[dict]:
    rows: dict[int, dict[int, list[str]]] = {}
    for text, stack in dom.p.texts:
        if not (_in(stack, "#itemBrief") or _in(stack, ".essential-info")):
            continue
        tr, cell = _nearest(stack, "tr"), (_nearest(stack, "td") or _nearest(stack, "th"))
        if not tr or not cell:
            continue
        rows.setdefault(tr.uid, {}).setdefault(cell.uid, []).append(text)
    specs = []
    for cells in rows.values():
        values = [" ".join(v) for v in cells.values()]
        for i in range(0, len(values) - 1, 2):
            if values[i] and values[i + 1]:
                specs.append({"name": values[i], "value": values[i + 1]})
    return specs[:80]


def _parse_seller(dom: CoupangDom) -> dict:
    joined = " ".join(dom.texts(".seller-info"))
    info = {"name": "", "rating": "", "courier": ""}
    m = re.search(r"판매자\s*:\s*(.+?)(?=\s*판매자 상품 보러가기|\s*판매자 평가|\s*배송사|$)", joined)
    if m:
        info["name"] = m.group(1).strip()
    m = re.search(r"판매자 평가\s*(\d+%)\s*\(([\d,]+)\)", joined)
    if m:
        info["rating"] = f"{m.group(1)} ({m.group(2)})"
    m = re.search(r"배송사\s*:\s*(.+?)$", joined)
    if m:
        info["courier"] = m.group(1).strip()
    if not info["name"]:
        info["name"] = dom.text(".prod-sale-vendor-name")
    return info


def _rating_from_stars(dom: CoupangDom) -> str:
    for style, stack in dom.p.styles:
        if "rating-star-num" in stack[-1].classes and (not dom.main or _in(stack, dom.main)):
            m = re.search(r"width:\s*([\d.]+)%", style)
            if m:
                return f"{round(float(m.group(1)) / 20, 1):g}"
    return ""


def _main_item_ids(html: str, product_id: str, source_url: str) -> tuple[str, str]:
    query = {k.lower(): v for k, v in parse_qsl(urlsplit(source_url).query)}
    item_id, vendor_item_id = query.get("itemid", ""), query.get("vendoritemid", "")
    if product_id and not (item_id and vendor_item_id):
        # 같은 상품번호를 가진 링크에서만 읽는다 (광고/추천 상품 ID 오염 방지)
        pattern = re.compile(r"/vp/products/" + re.escape(product_id) + r"\?([^\"'\s<>]+)")
        for m in pattern.finditer(html.replace("&amp;", "&")):
            q = {k.lower(): v for k, v in parse_qsl(m.group(1))}
            item_id = item_id or q.get("itemid", "")
            vendor_item_id = vendor_item_id or q.get("vendoritemid", "")
            if item_id and vendor_item_id:
                break
    return item_id, vendor_item_id


def parse_product_html(html: str, source_url: str = "") -> dict:
    if "access denied" in html[:3000].lower() and "coupang" not in html[:3000].lower():
        raise CrawlerError("저장된 파일이 '접근 거부' 페이지입니다. 브라우저에서 상품 페이지가 정상 표시된 상태로 다시 저장해 주세요.")

    dom = CoupangDom(html)
    p = dom.p
    ld = _ld_product(p.json_ld)
    offers = ld.get("offers", {})
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    if not isinstance(offers, dict):
        offers = {}
    ld_rating = ld.get("aggregateRating") if isinstance(ld.get("aggregateRating"), dict) else {}
    brand = ld.get("brand", "")
    if isinstance(brand, dict):
        brand = brand.get("name", "")

    page_url = source_url or p.canonical or p.meta.get("og:url", "")
    path_match = re.search(r"/vp/products/(\d+)", page_url)
    product_id = path_match.group(1) if path_match else str(ld.get("productID") or "")
    item_id, vendor_item_id = _main_item_ids(html, product_id, page_url)

    title = (
        dom.first(((".product-title",), (".prod-buy-header__title",)))
        or clean_text(ld.get("name"))
        or clean_text(p.meta.get("og:title", ""))
        or clean_text(p.title_tag)
    )
    title = re.sub(r"\s*-\s*[^-]*\|\s*쿠팡!?$", "", title).strip()

    sale_price = (
        parse_price(dom.text(".final-price-amount"))
        or parse_price(offers.get("price"))
        or parse_price(dom.first(((".total-price",), (".prod-sale-price",))))
    )
    original_price = parse_price(dom.text(".sales-price-amount")) or parse_price(dom.text(".origin-price"))
    if not (original_price and sale_price and original_price > sale_price):
        original_price = None
    discount_rate = ""
    if original_price:
        discount_rate = dom.first(((".discount-rate",), (".discount-percentage",))) or \
            f"{round((1 - sale_price / original_price) * 100)}%"

    rating = _rating_from_stars(dom) or str(ld_rating.get("ratingValue") or "")
    review_count = parse_price(dom.text(".rating-count-txt")) or parse_price(
        ld_rating.get("reviewCount") or ld_rating.get("ratingCount")
    )
    seller = _parse_seller(dom)

    # 대표 이미지: JSON-LD + img.thumbnail(썸네일 스트립) + .product-image 안 이미지 + og:image
    ld_images = ld.get("image", [])
    ld_images = [ld_images] if isinstance(ld_images, str) else (ld_images if isinstance(ld_images, list) else [])
    gallery_raw = [normalize_image_url(u) for u in ld_images if isinstance(u, str)]
    for attrs, stack in p.images:
        if "thumbnail" in attrs.get("class", "").split() or _in(stack, ".product-image") or _in(stack, ".prod-image"):
            gallery_raw.append(normalize_image_url(_image_src(attrs)))
    gallery_raw.append(normalize_image_url(p.meta.get("og:image", "")))
    gallery = dedupe([_gallery_size(u) for u in gallery_raw if _is_product_image(u)])

    detail_raw = [
        normalize_image_url(_image_src(attrs))
        for attrs, stack in p.images
        if any(_in(stack, k) for k in (".subType-IMAGE", "#productDetail", ".product-detail-content"))
    ]
    detail = [u for u in dedupe([u for u in detail_raw if _is_product_image(u)], limit=60) if u not in gallery]

    breadcrumb = dom.texts(".breadcrumb", main=False) or dom.texts("#breadcrumb", main=False)
    breadcrumb = list(dict.fromkeys(t for t in breadcrumb if t not in ("쿠팡 홈", ">", "›")))

    specs = _parse_specs(dom)
    if not brand:
        brand = next((s["value"] for s in specs if s["name"] in ("브랜드", "브랜드명")), "") or dom.text(".prod-brand-name")

    description = clean_text(ld.get("description")) or clean_text(p.meta.get("og:description", ""))
    if description.startswith("쿠팡에서") and "혜택" in description:
        description = ""  # 쿠팡 기본 SEO 문구 (상품 정보 아님)

    fields = {
        "title": title,
        "brand": clean_text(brand),
        "description": description,
        "product_id": product_id,
        "item_id": item_id,
        "vendor_item_id": vendor_item_id,
        "sku": clean_text(ld.get("sku")),
        "sale_price": sale_price,
        "original_price": original_price,
        "discount_rate": discount_rate,
        "unit_price": dom.text(".final-unit-price"),
        "currency": str(offers.get("priceCurrency") or ("KRW" if sale_price else "")),
        "availability": str(offers.get("availability") or "").rsplit("/", 1)[-1],
        "rating": rating,
        "review_count": review_count,
        "seller": seller["name"],
        "seller_rating": seller["rating"],
        "courier": seller["courier"],
        "shipping": dom.first(((".shipping-fee-desc",), (".prod-shipping-fee-message",))),
        "arrival": dom.first(((".regular-pdd-container",), (".prod-pdd-container",))),
        "category_path": breadcrumb,
        "options": _parse_options(dom),
        "bullet_points": dom.texts(".prod-attr-item") or dom.texts(".prod-description-attribute"),
        "specs": specs,
        "gallery_images": gallery,
        "detail_images": detail,
    }
    if not fields["title"] and not fields["sale_price"] and not gallery:
        raise CrawlerError("상품 정보를 찾지 못했습니다. 쿠팡 상품 상세 페이지를 저장한 파일인지 확인해 주세요.")

    return {
        "marketplace": "coupang",
        "source": "browser_saved_html",
        "source_url": canonical_product_url(page_url) or page_url,
        "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fields": fields,
        "notes": _notes(fields),
    }


def _notes(fields: dict) -> list[str]:
    notes = ["가격·재고·배송 정보는 저장 시점 기준이므로 영상에 쓰기 전 다시 확인하세요."]
    if not fields["detail_images"]:
        notes.append("상세 설명 이미지가 비어 있습니다. 페이지를 끝까지 스크롤해 상세 이미지가 로드된 뒤 저장하면 함께 수집됩니다.")
    if not fields["options"]:
        notes.append("옵션 목록을 찾지 못했습니다(단일 상품이거나 옵션 UI가 클릭 후 로드되는 경우).")
    if fields["specs"] and all("상세페이지 참조" in s["value"] for s in fields["specs"]):
        notes.append("필수 표기 정보가 모두 '상세페이지 참조'입니다. 실제 스펙은 상세 이미지 안에 있으니 이미지를 직접 확인하세요.")
    return notes


# ---------------------------------------------------------------------------
# 2) 쿠팡 파트너스 Open API
# ---------------------------------------------------------------------------

def partners_keys() -> tuple[str, str]:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    access, secret = os.getenv("COUPANG_ACCESS_KEY", ""), os.getenv("COUPANG_SECRET_KEY", "")
    if not access or not secret:
        raise CrawlerError("COUPANG_ACCESS_KEY / COUPANG_SECRET_KEY 가 .env 에 없습니다 (쿠팡 파트너스 > 추가기능 > Open API 에서 발급).")
    return access, secret


def partners_authorization(method: str, path: str, query: str, access: str, secret: str, now: datetime | None = None) -> str:
    signed_date = (now or datetime.now(timezone.utc)).strftime("%y%m%dT%H%M%SZ")
    message = f"{signed_date}{method.upper()}{path}{query}"
    signature = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    return f"CEA algorithm=HmacSHA256, access-key={access}, signed-date={signed_date}, signature={signature}"


def partners_request(method: str, path: str, params: dict | None = None, body: dict | None = None) -> dict:
    import requests

    access, secret = partners_keys()
    query = urlencode(params or {})
    headers = {
        "Authorization": partners_authorization(method, path, query, access, secret),
        "Content-Type": "application/json;charset=UTF-8",
    }
    url = PARTNERS_HOST + path + (f"?{query}" if query else "")
    try:
        resp = requests.request(method, url, headers=headers, json=body, timeout=(5, 15))
    except requests.RequestException as exc:
        raise CrawlerError(f"파트너스 API 요청 실패 ({type(exc).__name__}).") from exc
    try:
        data = resp.json()
    except ValueError:
        data = {}
    if resp.status_code == 429:
        raise CrawlerError("파트너스 API 호출 한도를 초과했습니다. 잠시 후 다시 시도하세요.")
    if resp.status_code >= 400 or str(data.get("rCode", "0")) != "0":
        raise CrawlerError(f"파트너스 API 오류 (HTTP {resp.status_code}): {data.get('rMessage') or data.get('message') or resp.text[:200]}")
    return data


def partners_search(keyword: str, limit: int = 10) -> dict:
    data = partners_request("GET", f"{PARTNERS_BASE}/products/search", {"keyword": keyword, "limit": max(1, min(limit, 10))})
    payload = data.get("data") or {}
    products = []
    for item in payload.get("productData", []) or []:
        products.append({
            "product_id": str(item.get("productId", "")),
            "title": clean_text(item.get("productName")),
            "sale_price": parse_price(item.get("productPrice")),
            "image": normalize_image_url(item.get("productImage", "")) or item.get("productImage", ""),
            "partners_url": item.get("productUrl", ""),
            "category": item.get("categoryName", ""),
            "is_rocket": bool(item.get("isRocket")),
            "is_free_shipping": bool(item.get("isFreeShipping")),
            "rank": item.get("rank"),
        })
    return {
        "marketplace": "coupang",
        "source": "coupang_partners_search_api",
        "keyword": keyword,
        "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "landing_url": payload.get("landingUrl", ""),
        "products": products,
    }


def partners_deeplink(urls: list[str]) -> dict:
    for u in urls:
        if not is_coupang_host(urlsplit(u).hostname or "", ("coupang.com",)):
            raise CrawlerError(f"쿠팡 URL이 아닙니다: {u}")
    data = partners_request("POST", f"{PARTNERS_BASE}/deeplink", body={"coupangUrls": urls})
    return {
        "source": "coupang_partners_deeplink_api",
        "links": [
            {"original_url": d.get("originalUrl", ""), "short_url": d.get("shortenUrl", ""), "landing_url": d.get("landingUrl", "")}
            for d in data.get("data", []) or []
        ],
    }


# ---------------------------------------------------------------------------
# 앱 연동용 헬퍼
# ---------------------------------------------------------------------------

def to_research_context(result: dict) -> str:
    """ai_researcher 프롬프트에 넣을 사실 요약 (값이 있는 것만)."""
    f = result.get("fields", {})
    lines = ["[쿠팡 상품 상세 수집 결과 - 페이지에 표시된 사실만, 추측 금지]"]
    def add(label, value):
        if value not in (None, "", [], {}):
            lines.append(f"- {label}: {value}")
    add("상품명", f.get("title"))
    add("브랜드", f.get("brand"))
    add("카테고리", " > ".join(f.get("category_path") or []))
    add("판매가", f"{f['sale_price']:,}원" if f.get("sale_price") else "")
    add("정가", f"{f['original_price']:,}원" if f.get("original_price") else "")
    add("할인율", f.get("discount_rate"))
    add("평점", f.get("rating"))
    add("리뷰 수", f.get("review_count"))
    add("배송", " / ".join(x for x in (f.get("shipping"), f.get("arrival")) if x))
    add("판매자", " ".join(x for x in (f.get("seller"), f.get("seller_rating") and f"(평가 {f['seller_rating']})") if x))
    opts = []
    for o in (f.get("options") or [])[:15]:
        if isinstance(o, dict):
            label = (f"{o['group']}: " if o.get("group") else "") + o["name"]
            if o.get("price_delta"):
                label += f" ({o['price_delta']:+,}원)"
            if o.get("sold_out"):
                label += " [품절]"
        else:
            label = str(o)
        opts.append(label)
    add("옵션", ", ".join(opts))
    add("설명", (f.get("description") or "")[:500])
    for b in (f.get("bullet_points") or [])[:10]:
        lines.append(f"- 특징: {b}")
    for s in [s for s in (f.get("specs") or []) if "상세페이지 참조" not in s["value"]][:20]:
        lines.append(f"- {s['name']}: {s['value']}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _write(result: dict, output: str | None) -> None:
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if output:
        out = Path(output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"저장 완료: {out}")
    else:
        sys.stdout.write(text)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="쿠팡 상품 상세 수집기 (저장 HTML 파싱 / 파트너스 API)")
    sub = ap.add_subparsers(dest="mode", required=True)

    h = sub.add_parser("html", help="브라우저에서 저장한 상품 페이지 파싱")
    h.add_argument("--file", required=True, help=".html / .htm / .mhtml 파일 경로")
    h.add_argument("--url", default="", help="(선택) 원본 상품 URL — 파일에 canonical 이 없을 때 사용")
    h.add_argument("--output", help="결과 JSON 경로 (생략 시 표준출력)")

    s = sub.add_parser("search", help="파트너스 API 키워드 검색")
    s.add_argument("--keyword", required=True)
    s.add_argument("--limit", type=int, default=5)
    s.add_argument("--output")

    d = sub.add_parser("deeplink", help="파트너스 API 단축 링크 변환")
    d.add_argument("--url", action="append", required=True)
    d.add_argument("--output")

    args = ap.parse_args(argv)
    try:
        if args.mode == "html":
            path = Path(args.file)
            if not path.is_file():
                raise CrawlerError(f"파일이 없습니다: {path}")
            result = parse_product_html(read_saved_page(path), args.url)
        elif args.mode == "search":
            result = partners_search(args.keyword, args.limit)
        else:
            result = partners_deeplink(args.url)
        _write(result, args.output)
    except (CrawlerError, OSError) as exc:
        print(f"수집 실패: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
