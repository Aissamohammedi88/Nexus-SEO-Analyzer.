#!/usr/bin/env python3# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════════
🔍 NEXUS SEO ANALYZER v1.0 — Analyseur de sites + Score SEO réel
═══════════════════════════════════════════════════════════════════════════════
Auteur : Aissa Mohammedi (DGK)
Rôle : Serveur local qui analyse n'importe quel site (URL) en quelques
minutes, et retourne un score SEO réel + rapport détaillé.

- Validation W3C HTML/CSS (API officielle w3.org, sans clé)
- Analyse SEO complète : meta, headings, images, links, perf
- Score réel pondéré sur 100
- Détection Shopify / WooCommerce / WordPress / Magento
- Interface web 3 colonnes + rapport JSON téléchargeable
- Python stdlib uniquement (0 dépendance)

Port : 8090
Standards : W3C HTML, CSS, SEO Best Practices (Google Search Central)
═══════════════════════════════════════════════════════════════════════════════
"""

import os
import sys
import re
import json
import time
import ssl
import socket
import threading
import urllib.request
import urllib.error
import urllib.parse
import argparse
from datetime import datetime
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from typing import Any, Dict, List, Optional, Tuple
from collections import Counter

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

VERSION = "1.0.0"
HOST = "127.0.0.1"
PORT = 8090
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 NexusSEO/1.0"
TIMEOUT = 30
MAX_HTML_SIZE = 5 * 1024 * 1024

W3C_HTML_VALIDATOR = "https://validator.w3.org/nu/"
W3C_CSS_VALIDATOR = "https://jigsaw.w3.org/css-validator/validator"


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def safe_get(url: str, timeout: int = TIMEOUT, headers: Optional[Dict] = None) -> Tuple[Optional[int], Optional[bytes], Dict]:
"""Requête HTTP safe."""
hdrs = {"User-Agent": USER_AGENT, "Accept": "*/*"}
if headers:
hdrs.update(headers)
try:
req = urllib.request.Request(url, headers=hdrs)
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
return r.status, r.read(MAX_HTML_SIZE), dict(r.headers)
except urllib.error.HTTPError as e:
try:
return e.code, e.read(MAX_HTML_SIZE), dict(e.headers)
except Exception:
return e.code, None, {}
except Exception:
return None, None, {}


def extract_domain(url: str) -> str:
"""Extrait le domaine."""
try:
return urlparse(url).netloc
except Exception:
return ""


def time_ago(ts: float) -> str:
"""Formatte un timestamp."""
diff = int(time.time() - ts)
if diff < 60:
return "just now"
if diff < 3600:
return "{} min ago".format(diff // 60)
if diff < 86400:
return "{} hours ago".format(diff // 3600)
return "{} days ago".format(diff // 86400)


# ═══════════════════════════════════════════════════════════════════════════════
# HTML PARSER (light, regex-based, no bs4)
# ═══════════════════════════════════════════════════════════════════════════════

class HTMLAnalyzer:
"""Analyse HTML sans dépendance."""

def __init__(self, html: str, base_url: str):
self.html = html or ""
self.base_url = base_url
self.domain = extract_domain(base_url)

def get_title(self) -> Optional[str]:
m = re.search(r"<title[^>]*>(.*?)</title>", self.html, re.IGNORECASE | re.DOTALL)
if m:
return re.sub(r"\s+", " ", m.group(1)).strip()
return None

def get_meta(self, name: str) -> Optional[str]:
# meta name="X" content="Y" OR meta property="X" content="Y"
patterns = [
r'<meta\s+name=["\']' + re.escape(name) + r'["\'][^>]*content=["\']([^"\']*)["\']',
r'<meta\s+content=["\']([^"\']*)["\'][^>]*name=["\']' + re.escape(name) + r'["\']',
r'<meta\s+property=["\']' + re.escape(name) + r'["\'][^>]*content=["\']([^"\']*)["\']',
r'<meta\s+content=["\']([^"\']*)["\'][^>]*property=["\']' + re.escape(name) + r'["\']',
]
for pat in patterns:
m = re.search(pat, self.html, re.IGNORECASE)
if m:
return m.group(1).strip()
return None

def get_headings(self) -> Dict[str, List[str]]:
"""Liste les H1..H6."""
result = {}
for level in range(1, 7):
tag = "h{}".format(level)
matches = re.findall(
r"<{0}[^>]*>(.*?)</{0}>".format(tag),
self.html, re.IGNORECASE | re.DOTALL
)
cleaned = []
for m in matches:
text = re.sub(r"<[^>]+>", "", m)
text = re.sub(r"\s+", " ", text).strip()
if text:
cleaned.append(text[:200])
result["h{}".format(level)] = cleaned
return result

def get_images(self) -> List[Dict[str, Any]]:
"""Liste les images avec attributs."""
images = []
for m in re.finditer(r"<img\b([^>]*)>", self.html, re.IGNORECASE):
attrs = m.group(1)
img = {"src": None, "alt": None, "width": None, "height": None}
for attr in ["src", "alt", "width", "height"]:
match = re.search(
r'{}\s*=\s*["\']([^"\']*)["\']'.format(attr), attrs, re.IGNORECASE
)
if match:
img[attr] = match.group(1)
images.append(img)
return images

def get_links(self) -> Dict[str, List[Dict[str, Any]]]:
"""Liste les liens internes et externes."""
internal = []
external = []
for m in re.finditer(r'<a\b([^>]*)>(.*?)</a>', self.html, re.IGNORECASE | re.DOTALL):
attrs = m.group(1)
href_m = re.search(r'href\s*=\s*["\']([^"\']*)["\']', attrs, re.IGNORECASE)
if not href_m:
continue
href = href_m.group(1).strip()
rel_m = re.search(r'rel\s*=\s*["\']([^"\']*)["\']', attrs, re.IGNORECASE)
rel = rel_m.group(1) if rel_m else ""
text = re.sub(r"<[^>]+>", "", m.group(2))
text = re.sub(r"\s+", " ", text).strip()[:100]

if href.startswith("http://") or href.startswith("https://"):
if self.domain and self.domain in href:
internal.append({"href": href, "text": text, "rel": rel})
else:
external.append({"href": href, "text": text, "rel": rel})
elif href.startswith("/") or href.startswith("#") or not href.startswith(("mailto:", "tel:", "javascript:")):
internal.append({"href": href, "text": text, "rel": rel})
return {"internal": internal, "external": external}

def get_lang(self) -> Optional[str]:
m = re.search(r'<html[^>]*\blang\s*=\s*["\']([^"\']*)["\']', self.html, re.IGNORECASE)
return m.group(1) if m else None

def get_viewport(self) -> Optional[str]:
return self.get_meta("viewport")

def get_charset(self) -> Optional[str]:
m = re.search(r'<meta[^>]*charset\s*=\s*["\']?([\w-]+)', self.html, re.IGNORECASE)
if m:
return m.group(1)
ct = self.get_meta("content-type")
if ct and "charset=" in ct:
return ct.split("charset=")[-1].split(";")[0].strip()
return None

def get_canonical(self) -> Optional[str]:
m = re.search(
r'<link[^>]*rel\s*=\s*["\']canonical["\'][^>]*href\s*=\s*["\']([^"\']*)["\']',
self.html, re.IGNORECASE
)
if not m:
m = re.search(
r'<link[^>]*href\s*=\s*["\']([^"\']*)["\'][^>]*rel\s*=\s*["\']canonical["\']',
self.html, re.IGNORECASE
)
return m.group(1) if m else None

def get_robots_meta(self) -> Optional[str]:
return self.get_meta("robots")

def get_hreflang(self) -> List[Dict[str, str]]:
result = []
for m in re.finditer(
r'<link[^>]*hreflang\s*=\s*["\']([^"\']*)["\'][^>]*href\s*=\s*["\']([^"\']*)["\']',
self.html, re.IGNORECASE
):
result.append({"hreflang": m.group(1), "href": m.group(2)})
return result

def get_structured_data(self) -> List[Dict[str, Any]]:
"""Extrait JSON-LD."""
results = []
for m in re.finditer(
r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
self.html, re.IGNORECASE | re.DOTALL
):
try:
data = json.loads(m.group(1).strip())
if isinstance(data, dict):
results.append({"@type": data.get("@type", "unknown")})
elif isinstance(data, list):
for item in data:
if isinstance(item, dict):
results.append({"@type": item.get("@type", "unknown")})
except Exception:
pass
return results

def get_open_graph(self) -> Dict[str, str]:
og = {}
for prop in ["og:title", "og:description", "og:image", "og:url", "og:type", "og:site_name"]:
val = self.get_meta(prop)
if val:
og[prop] = val
return og

def get_twitter_card(self) -> Dict[str, str]:
tw = {}
for prop in ["twitter:card", "twitter:title", "twitter:description", "twitter:image"]:
val = self.get_meta(prop)
if val:
tw[prop] = val
return tw

def get_inline_scripts_count(self) -> int:
return len(re.findall(r'<script(?![^>]*\bsrc\b)[^>]*>', self.html, re.IGNORECASE))

def get_external_scripts(self) -> List[str]:
result = []
for m in re.finditer(
r'<script[^>]*\bsrc\s*=\s*["\']([^"\']*)["\']',
self.html, re.IGNORECASE
):
result.append(m.group(1))
return result

def get_stylesheets(self) -> List[str]:
result = []
for m in re.finditer(
r'<link[^>]*\brel\s*=\s*["\']stylesheet["\'][^>]*\bhref\s*=\s*["\']([^"\']*)["\']',
self.html, re.IGNORECASE
):
result.append(m.group(1))
return result

def get_text_content(self) -> str:
"""Texte visible."""
text = re.sub(r'<script[^>]*>.*?</script>', ' ', self.html, flags=re.IGNORECASE | re.DOTALL)
text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.IGNORECASE | re.DOTALL)
text = re.sub(r'<[^>]+>', ' ', text)
text = re.sub(r'\s+', ' ', text)
return text.strip()

def detect_platform(self) -> Dict[str, Any]:
"""Détecte CMS/e-commerce depuis HTML."""
html_lower = self.html.lower()
platforms = []
if "cdn.shopify.com" in html_lower or "shopify" in html_lower:
platforms.append("Shopify")
if "wp-content" in html_lower or "wordpress" in html_lower:
platforms.append("WordPress")
if "woocommerce" in html_lower:
platforms.append("WooCommerce")
if "magento" in html_lower:
platforms.append("Magento")
if "wix.com" in html_lower:
platforms.append("Wix")
if "squarespace" in html_lower:
platforms.append("Squarespace")
if "bigcommerce" in html_lower:
platforms.append("BigCommerce")
if "prestashop" in html_lower:
platforms.append("PrestaShop")
return {"platforms": platforms or ["Unknown"]}


# ═══════════════════════════════════════════════════════════════════════════════
# W3C VALIDATOR (API officielle w3.org)
# ═══════════════════════════════════════════════════════════════════════════════

class W3CValidator:
"""Client pour les validateurs W3C."""

@staticmethod
def validate_html(url: str) -> Dict[str, Any]:
"""Valide HTML via API W3C."""
try:
params = urllib.parse.urlencode({"doc": url, "out": "json"})
full_url = "{}?{}".format(W3C_HTML_VALIDATOR, params)
status, body, _ = safe_get(full_url, timeout=45)
if status == 200 and body:
data = json.loads(body.decode("utf-8", errors="replace"))
messages = data.get("messages", [])
errors = [m for m in messages if m.get("type") == "error"]
warnings = [m for m in messages if m.get("type") == "info" and m.get("subType") == "warning"]
return {
"ok": True,
"errors_count": len(errors),
"warnings_count": len(warnings),
"errors": errors[:10],
"warnings": warnings[:10],
}
return {"ok": False, "error": "HTTP {}".format(status)}
except Exception as e:
return {"ok": False, "error": str(e)[:100]}

@staticmethod
def validate_css(url: str) -> Dict[str, Any]:
"""Valide CSS via API W3C."""
try:
params = urllib.parse.urlencode({
"uri": url, "output": "json", "profile": "css3"
})
full_url = "{}?{}".format(W3C_CSS_VALIDATOR, params)
status, body, _ = safe_get(full_url, timeout=45)
if status == 200 and body:
data = json.loads(body.decode("utf-8", errors="replace"))
cssvalidation = data.get("cssvalidation", {})
result = cssvalidation.get("result", {})
errors = result.get("errors", [])
warnings = result.get("warnings", [])
return {
"ok": True,
"errors_count": len(errors),
"warnings_count": len(warnings),
"errors": errors[:10],
"warnings": warnings[:10],
}
return {"ok": False, "error": "HTTP {}".format(status)}
except Exception as e:
return {"ok": False, "error": str(e)[:100]}


# ═══════════════════════════════════════════════════════════════════════════════
# SEO ANALYZER (score réel pondéré)
# ═══════════════════════════════════════════════════════════════════════════════

class SEOAnalyzer:
"""Analyse SEO complète et scoring."""

def __init__(self, url: str):
self.url = url
self.domain = extract_domain(url)
self.html = ""
self.headers: Dict[str, str] = {}
self.status_code: Optional[int] = None
self.load_time_ms: float = 0
self.checks: List[Dict[str, Any]] = []
self.analyzer: Optional[HTMLAnalyzer] = None
self.w3c_html: Dict[str, Any] = {}
self.w3c_css: Dict[str, Any] = {}

def _add_check(self, category: str, name: str, status: str,
points: float, max_points: float, message: str = "",
details: Optional[Dict] = None):
"""Enregistre un check."""
self.checks.append({
"category": category,
"name": name,
"status": status, # pass | warn | fail | info
"points": round(points, 2),
"max_points": round(max_points, 2),
"message": message,
"details": details or {},
})

def fetch(self) -> bool:
"""Télécharge le HTML."""
start = time.time()
status, body, headers = safe_get(self.url, timeout=TIMEOUT)
self.load_time_ms = round((time.time() - start) * 1000, 1)
self.status_code = status
self.headers = headers

if body is None:
return False

try:
charset = "utf-8"
ct = headers.get("Content-Type", "")
m = re.search(r"charset=([\w-]+)", ct, re.IGNORECASE)
if m:
charset = m.group(1)
self.html = body.decode(charset, errors="replace")
except Exception:
self.html = body.decode("utf-8", errors="replace")

self.analyzer = HTMLAnalyzer(self.html, self.url)
return True

def analyze(self) -> Dict[str, Any]:
"""Analyse complète."""
if not self.fetch():
return {
"url": self.url,
"ok": False,
"error": "Impossible de charger la page",
"timestamp": datetime.now().isoformat(),
}

a = self.analyzer

# ─── 1. ACCESSIBILITÉ / FONDAMENTAL (max 20 pts) ───
self._analyze_http_status()
self._analyze_lang()
self._analyze_charset()
self._analyze_viewport()
self._analyze_https()

# ─── 2. META / TITLES (max 25 pts) ───
self._analyze_title()
self._analyze_meta_description()
self._analyze_canonical()
self._analyze_robots_meta()

# ─── 3. STRUCTURE / HEADINGS (max 15 pts) ───
self._analyze_headings()

# ─── 4. IMAGES (max 10 pts) ───
self._analyze_images()

# ─── 5. LINKS (max 10 pts) ───
self._analyze_links()

# ─── 6. OPEN GRAPH / TWITTER (max 10 pts) ───
self._analyze_social()

# ─── 7. STRUCTURED DATA (max 5 pts) ───
self._analyze_structured_data()

# ─── 8. PERFORMANCE / TAILLE (max 5 pts) ───
self._analyze_performance()

# ─── W3C VALIDATION (info, hors score) ───
try:
self.w3c_html = W3CValidator.validate_html(self.url)
except Exception:
self.w3c_html = {"ok": False, "error": "timeout"}

# ─── Score total ───
total = sum(c["points"] for c in self.checks)
max_total = sum(c["max_points"] for c in self.checks)
score = round((total / max_total * 100) if max_total > 0 else 0, 1)

# ─── Compteurs ───
passed = sum(1 for c in self.checks if c["status"] == "pass")
warned = sum(1 for c in self.checks if c["status"] == "warn")
failed = sum(1 for c in self.checks if c["status"] == "fail")

# ─── Grade ───
if score >= 90:
grade = "A+"
color = "#1a7f37"
elif score >= 80:
grade = "A"
color = "#1a7f37"
elif score >= 70:
grade = "B"
color = "#9a6700"
elif score >= 60:
grade = "C"
color = "#9a6700"
elif score >= 40:
grade = "D"
color = "#bc4c00"
else:
grade = "F"
color = "#cf222e"

platform = a.detect_platform()

return {
"url": self.url,
"domain": self.domain,
"ok": True,
"timestamp": datetime.now().isoformat(),
"score": score,
"grade": grade,
"color": color,
"score_breakdown": {
"total": round(total, 2),
"max": round(max_total, 2),
},
"counters": {
"passed": passed,
"warned": warned,
"failed": failed,
"total": len(self.checks),
},
"http": {
"status_code": self.status_code,
"load_time_ms": self.load_time_ms,
"content_length": len(self.html),
"headers": {
k: v for k, v in self.headers.items()
if k.lower() in ["content-type", "server", "cache-control",
"content-encoding", "strict-transport-security",
"x-frame-options", "content-security-policy"]
},
},
"platform": platform,
"checks": self.checks,
"w3c": {
"html": self.w3c_html,
"css": self.w3c_css,
},
}

# ─── ANALYSES INDIVIDUELLES ───

def _analyze_http_status(self):
if self.status_code == 200:
self._add_check("accessibility", "HTTP Status 200", "pass", 3, 3, "OK")
elif self.status_code and self.status_code < 400:
self._add_check("accessibility", "HTTP Status", "warn", 1.5, 3,
"Status: {}".format(self.status_code))
else:
self._add_check("accessibility", "HTTP Status", "fail", 0, 3,
"Status: {}".format(self.status_code))

def _analyze_lang(self):
lang = self.analyzer.get_lang()
if lang:
self._add_check("accessibility", "HTML lang attribute", "pass", 3, 3,
"lang='{}'".format(lang))
else:
self._add_check("accessibility", "HTML lang attribute", "fail", 0, 3,
"Missing lang attribute on <html>")

def _analyze_charset(self):
charset = self.analyzer.get_charset()
if charset:
self._add_check("accessibility", "Charset declared", "pass", 3, 3,
"charset='{}'".format(charset))
else:
self._add_check("accessibility", "Charset declared", "warn", 1, 3,
"No charset detected")

def _analyze_viewport(self):
vp = self.analyzer.get_viewport()
if vp and "width=device-width" in vp:
self._add_check("accessibility", "Mobile viewport", "pass", 5, 5,
"Responsive viewport configured")
elif vp:
self._add_check("accessibility", "Mobile viewport", "warn", 2, 5,
"Viewport present but not responsive: {}".format(vp[:60]))
else:
self._add_check("accessibility", "Mobile viewport", "fail", 0, 5,
"Missing viewport meta tag")

def _analyze_https(self):
if self.url.startswith("https://"):
self._add_check("accessibility", "HTTPS", "pass", 6, 6, "Secured")
else:
self._add_check("accessibility", "HTTPS", "fail", 0, 6,
"Page not served over HTTPS")

def _analyze_title(self):
title = self.analyzer.get_title()
if not title:
self._add_check("meta", "Title tag", "fail", 0, 10,
"Missing <title>")
return
length = len(title)
if 30 <= length <= 60:
self._add_check("meta", "Title tag", "pass", 10, 10,
"Title length optimal ({} chars)".format(length),
{"title": title, "length": length})
elif 20 <= length <= 70:
self._add_check("meta", "Title tag", "warn", 6, 10,
"Title length suboptimal ({} chars, ideal 30-60)".format(length),
{"title": title, "length": length})
else:
self._add_check("meta", "Title tag", "fail", 2, 10,
"Title length off ({} chars, ideal 30-60)".format(length),
{"title": title, "length": length})

def _analyze_meta_description(self):
desc = self.analyzer.get_meta("description")
if not desc:
self._add_check("meta", "Meta description", "fail", 0, 8,
"Missing meta description")
return
length = len(desc)
if 120 <= length <= 160:
self._add_check("meta", "Meta description", "pass", 8, 8,
"Meta description optimal ({} chars)".format(length),
{"description": desc, "length": length})
elif 50 <= length <= 200:
self._add_check("meta", "Meta description", "warn", 4, 8,
"Meta description suboptimal ({} chars, ideal 120-160)".format(length),
{"description": desc, "length": length})
else:
self._add_check("meta", "Meta description", "fail", 2, 8,
"Meta description off ({} chars, ideal 120-160)".format(length),
{"description": desc, "length": length})

def _analyze_canonical(self):
canonical = self.analyzer.get_canonical()
if canonical:
self._add_check("meta", "Canonical URL", "pass", 3, 3,
"Canonical: {}".format(canonical[:80]))
else:
self._add_check("meta", "Canonical URL", "warn", 1, 3,
"Missing canonical link")

def _analyze_robots_meta(self):
robots = self.analyzer.get_robots_meta()
if robots and ("noindex" in robots.lower() or "nofollow" in robots.lower()):
self._add_check("meta", "Robots meta", "warn", 2, 4,
"Restrictions: {}".format(robots))
elif robots:
self._add_check("meta", "Robots meta", "pass", 4, 4,
"Robots: {}".format(robots))
else:
self._add_check("meta", "Robots meta", "info", 4, 4,
"No robots meta (default = index, follow)")

def _analyze_headings(self):
headings = self.analyzer.get_headings()
h1_count = len(headings["h1"])

if h1_count == 1:
self._add_check("headings", "Single H1", "pass", 8, 8,
"Exactly one H1 (correct)",
{"h1": headings["h1"][0] if headings["h1"] else ""})
elif h1_count == 0:
self._add_check("headings", "H1 present", "fail", 0, 8,
"No H1 found")
else:
self._add_check("headings", "Single H1", "warn", 4, 8,
"Multiple H1s found ({})".format(h1_count))

# Hiérarchie
h2_count = len(headings["h2"])
if h2_count > 0:
self._add_check("headings", "Subheadings", "pass", 4, 4,
"{} H2 found".format(h2_count))
else:
self._add_check("headings", "Subheadings", "warn", 1, 4,
"No H2 found")

# H3+
h3plus = sum(len(headings["h{}".format(i)]) for i in [3, 4, 5, 6])
self._add_check("headings", "Heading hierarchy", "pass" if h3plus > 0 else "warn",
3 if h3plus > 0 else 1, 3,
"{} deeper headings".format(h3plus))

def _analyze_images(self):
images = self.analyzer.get_images()
total = len(images)
if total == 0:
self._add_check("images", "Images", "info", 10, 10,
"No images found")
return

no_alt = [img for img in images if not img.get("alt")]
no_dim = [img for img in images if not (img.get("width") and img.get("height"))]

alt_pct = (total - len(no_alt)) / total * 100
if alt_pct >= 95:
self._add_check("images", "Alt attributes", "pass", 6, 6,
"{}/{} images have alt".format(total - len(no_alt), total))
elif alt_pct >= 70:
self._add_check("images", "Alt attributes", "warn", 3, 6,
"{}/{} images have alt ({}%)".format(
total - len(no_alt), total, int(alt_pct)))
else:
self._add_check("images", "Alt attributes", "fail", 0, 6,
"{}/{} images missing alt".format(len(no_alt), total))

if len(no_dim) == 0:
self._add_check("images", "Dimensions", "pass", 4, 4,
"All images have width/height")
elif len(no_dim) <= total * 0.3:
self._add_check("images", "Dimensions", "warn", 2, 4,
"{}/{} images missing dimensions".format(len(no_dim), total))
else:
self._add_check("images", "Dimensions", "fail", 0, 4,
"{}/{} images missing dimensions (CLS risk)".format(len(no_dim), total))

def _analyze_links(self):
links = self.analyzer.get_links()
internal = len(links["internal"])
external = len(links["external"])

if internal > 0:
self._add_check("links", "Internal links", "pass", 6, 6,
"{} internal links".format(internal))
else:
self._add_check("links", "Internal links", "warn", 2, 6,
"No internal links found")

# External links with rel
ext_with_rel = sum(1 for l in links["external"] if l["rel"])
if external == 0:
self._add_check("links", "External links", "info", 4, 4,
"No external links")
elif ext_with_rel / max(external, 1) >= 0.5:
self._add_check("links", "External rel", "pass", 4, 4,
"{}/{} external with rel".format(ext_with_rel, external))
else:
self._add_check("links", "External rel", "warn", 2, 4,
"{}/{} external with rel".format(ext_with_rel, external))

def _analyze_social(self):
og = self.analyzer.get_open_graph()
tw = self.analyzer.get_twitter_card()

og_score = len(og) * 1.0
tw_score = len(tw) * 0.8

total_points = min(og_score + tw_score, 10)
max_pts = 10

if len(og) >= 4:
status = "pass"
elif len(og) >= 2:
status = "warn"
else:
status = "fail"

self._add_check("social", "Open Graph", status, total_points, max_pts,
"OG tags: {}, Twitter cards: {}".format(len(og), len(tw)),
{"og": og, "twitter": tw})

def _analyze_structured_data(self):
ld = self.analyzer.get_structured_data()
if ld:
self._add_check("structured_data", "JSON-LD", "pass", 5, 5,
"{} schema(s) found".format(len(ld)),
{"schemas": [s["@type"] for s in ld]})
else:
self._add_check("structured_data", "JSON-LD", "warn", 1, 5,
"No structured data (Schema.org)")

def _analyze_performance(self):
# Taille HTML
size_kb = len(self.html) / 1024
if size_kb < 100:
self._add_check("performance", "HTML size", "pass", 3, 3,
"{:.0f} KB".format(size_kb))
elif size_kb < 500:
self._add_check("performance", "HTML size", "warn", 1.5, 3,
"{:.0f} KB".format(size_kb))
else:
self._add_check("performance", "HTML size", "fail", 0, 3,
"{:.0f} KB (heavy)".format(size_kb))

# Load time
if self.load_time_ms < 1000:
self._add_check("performance", "Load time", "pass", 2, 2,
"{:.0f} ms".format(self.load_time_ms))
elif self.load_time_ms < 3000:
self._add_check("performance", "Load time", "warn", 1, 2,
"{:.0f} ms".format(self.load_time_ms))
else:
self._add_check("performance", "Load time", "fail", 0, 2,
"{:.0f} ms (slow)".format(self.load_time_ms))


# ═══════════════════════════════════════════════════════════════════════════════
# HTML INTERFACE
# ═══════════════════════════════════════════════════════════════════════════════

INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Nexus SEO Analyzer</title>
<style>
:root {
--bg: #ffffff;
--bg-subtle: #f6f8fa;
--border: #d0d7de;
--border-muted: #e1e4e8;
--text: #24292f;
--text-muted: #57606a;
--text-link: #0969da;
--hn-orange: #ff6600;
--code-bg: #f6f8fa;
--font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
--font-mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
}
[data-theme="dark"] {
--bg: #0d1117;
--bg-subtle: #161b22;
--border: #30363d;
--border-muted: #21262d;
--text: #c9d1d9;
--text-muted: #8b949e;
--text-link: #58a6ff;
--code-bg: #161b22;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body {
background: var(--bg);
color: var(--text);
font-family: var(--font-sans);
font-size: 14px;
line-height: 1.5;
}
a { color: var(--text-link); }
button {
font-family: inherit;
font-size: 13px;
padding: 7px 16px;
border: 1px solid var(--border);
border-radius: 6px;
background: var(--bg-subtle);
color: var(--text);
cursor: pointer;
transition: all .1s;
}
button:hover { background: var(--border-muted); }
button.primary {
background: var(--hn-orange);
color: white;
border-color: var(--hn-orange);
font-weight: 600;
}
button.primary:hover { filter: brightness(1.1); }
button:disabled { opacity: 0.5; cursor: wait; }

.header {
background: var(--bg-subtle);
border-bottom: 1px solid var(--border);
padding: 14px 24px;
display: flex;
align-items: center;
gap: 16px;
flex-wrap: wrap;
}
.header-brand {
display: flex;
align-items: center;
gap: 10px;
font-weight: 600;
font-size: 16px;
}
.header-brand .logo {
width: 28px; height: 28px;
background: var(--hn-orange);
color: white;
border-radius: 6px;
display: inline-flex;
align-items: center;
justify-content: center;
font-size: 16px;
}
.header-input {
flex: 1;
max-width: 600px;
display: flex;
gap: 8px;
}
.header-input input {
flex: 1;
padding: 8px 14px;
border: 1px solid var(--border);
border-radius: 6px;
background: var(--bg);
color: var(--text);
font-size: 14px;
font-family: var(--font-mono);
outline: none;
}
.header-input input:focus { border-color: var(--text-link); }

.layout {
display: grid;
grid-template-columns: 1fr;
gap: 20px;
padding: 24px;
max-width: 1200px;
margin: 0 auto;
}

.card {
background: var(--bg);
border: 1px solid var(--border);
border-radius: 8px;
overflow: hidden;
}

/* SCORE CARD */
.score-card {
display: flex;
align-items: center;
gap: 32px;
padding: 32px;
flex-wrap: wrap;
}
.score-circle {
width: 140px;
height: 140px;
border-radius: 50%;
display: flex;
align-items: center;
justify-content: center;
flex-direction: column;
position: relative;
flex-shrink: 0;
}
.score-circle .score-val {
font-size: 42px;
font-weight: 800;
font-family: var(--font-mono);
line-height: 1;
}
.score-circle .score-grade {
font-size: 18px;
font-weight: 700;
margin-top: 4px;
opacity: 0.85;
}
.score-details {
flex: 1;
min-width: 200px;
}
.score-details h2 {
font-size: 20px;
margin-bottom: 8px;
}
.score-details .url {
font-family: var(--font-mono);
font-size: 12px;
color: var(--text-muted);
margin-bottom: 16px;
word-break: break-all;
}
.stats-grid {
display: grid;
grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
gap: 12px;
margin-top: 16px;
}
.stat-item {
background: var(--bg-subtle);
padding: 12px;
border-radius: 6px;
border: 1px solid var(--border-muted);
}
.stat-item .n {
font-size: 20px;
font-weight: 700;
font-family: var(--font-mono);
}
.stat-item .l {
font-size: 11px;
color: var(--text-muted);
text-transform: uppercase;
letter-spacing: 0.5px;
margin-top: 2px;
}
.stat-item.pass .n { color: #1a7f37; }
.stat-item.warn .n { color: #9a6700; }
.stat-item.fail .n { color: #cf222e; }

/* CHECK LIST */
.checklist { list-style: none; }
.check-group-header {
padding: 12px 20px;
background: var(--bg-subtle);
border-bottom: 1px solid var(--border);
font-size: 12px;
font-weight: 700;
color: var(--text-muted);
text-transform: uppercase;
letter-spacing: 0.5px;
}
.check-item {
padding: 14px 20px;
border-bottom: 1px solid var(--border-muted);
display: flex;
align-items: flex-start;
gap: 12px;
}
.check-item:last-child { border-bottom: none; }
.check-icon {
width: 22px; height: 22px;
border-radius: 50%;
display: inline-flex;
align-items: center;
justify-content: center;
flex-shrink: 0;
font-size: 12px;
font-weight: 700;
color: white;
}
.check-icon.pass { background: #1a7f37; }
.check-icon.warn { background: #9a6700; }
.check-icon.fail { background: #cf222e; }
.check-icon.info { background: #0969da; }
.check-content { flex: 1; }
.check-name {
font-weight: 600;
font-size: 14px;
margin-bottom: 2px;
}
.check-message {
font-size: 12px;
color: var(--text-muted);
}
.check-points {
font-family: var(--font-mono);
font-size: 12px;
color: var(--text-muted);
flex-shrink: 0;
}

/* LOADING */
.loading {
padding: 60px 20px;
text-align: center;
color: var(--text-muted);
}
.spinner {
display: inline-block;
width: 20px;
height: 20px;
border: 2px solid var(--border);
border-top-color: var(--hn-orange);
border-radius: 50%;
animation: spin 0.7s linear infinite;
margin-right: 12px;
vertical-align: middle;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* EMPTY */
.empty {
padding: 80px 20px;
text-align: center;
color: var(--text-muted);
}
.empty h2 {
font-size: 20px;
color: var(--text);
margin-bottom: 8px;
}
.empty p { font-size: 14px; margin-bottom: 20px; }

/* ERROR */
.error-card {
padding: 24px;
background: #ffebe9;
border: 1px solid #ff818266;
border-radius: 8px;
color: #82071e;
}
[data-theme="dark"] .error-card {
background: #67060c;
border-color: #8e151966;
color: #ffb6b6;
}

.footer {
text-align: center;
padding: 24px;
color: var(--text-muted);
font-size: 11px;
border-top: 1px solid var(--border);
margin-top: 32px;
}

@media (max-width: 700px) {
.score-card { flex-direction: column; align-items: flex-start; }
.score-circle { width: 120px; height: 120px; }
.score-circle .score-val { font-size: 36px; }
.header { padding: 12px 16px; }
.layout { padding: 16px; }
}
</style>
</head>
<body>

<div class="header">
<div class="header-brand">
<span class="logo">🔍</span>
<span>Nexus SEO Analyzer</span>
</div>
<div class="header-input">
<input type="text" id="url" placeholder="https://example.com" value="https://www.shopify.com">
<button class="primary" id="analyzeBtn" onclick="analyze()">Analyze</button>
</div>
<button onclick="toggleTheme()" title="Theme">🌓</button>
</div>

<div class="layout" id="layout">
<div class="card empty">
<h2>🔍 Analyze any website</h2>
<p>Enter a URL above to get a real SEO score with W3C validation.</p>
<p style="font-size:12px;color:var(--text-muted)">
Checks: HTTP, HTTPS, Meta, Headings, Images, Links, OpenGraph, JSON-LD, Performance, W3C
</p>
</div>
</div>

<div class="footer">
Nexus SEO Analyzer · v__V__ · Local only · W3C API + SEO Best Practices
</div>

<script>
let currentReport = null;

function esc(s) {
if (s == null) return '';
return String(s)
.replace(/&/g, '&amp;')
.replace(/</g, '&lt;')
.replace(/>/g, '&gt;')
.replace(/"/g, '&quot;');
}

function toggleTheme() {
const cur = document.documentElement.getAttribute('data-theme') || 'light';
const next = cur === 'light' ? 'dark' : 'light';
document.documentElement.setAttribute('data-theme', next);
try { localStorage.setItem('seo-theme', next); } catch(e) {}
}

async function analyze() {
const url = document.getElementById('url').value.trim();
if (!url) return;

const btn = document.getElementById('analyzeBtn');
btn.disabled = true;
btn.textContent = 'Analyzing...';

const layout = document.getElementById('layout');
layout.innerHTML = '<div class="card loading"><span class="spinner"></span>Fetching and analyzing ' + esc(url) + '...<br><span style="font-size:12px;margin-top:8px;display:inline-block;color:var(--text-muted)">This may take 30-60 seconds (W3C validation + full analysis)</span></div>';

try {
const res = await fetch('/api/analyze', {
method: 'POST',
headers: {'Content-Type': 'application/json'},
body: JSON.stringify({url: url})
});
const data = await res.json();
currentReport = data;
render(data);
} catch (e) {
layout.innerHTML = '<div class="error-card"><strong>Error:</strong> ' + esc(e.message) + '</div>';
} finally {
btn.disabled = false;
btn.textContent = 'Analyze';
}
}

function render(r) {
const layout = document.getElementById('layout');

if (!r.ok) {
layout.innerHTML = '<div class="error-card"><strong>Analysis failed:</strong> ' + esc(r.error || 'unknown') + '</div>';
return;
}

const score = r.score;
const grade = r.grade;
const color = r.color || '#0969da';

// Score circle
const circleStroke = score >= 60 ? '#1a7f37' : score >= 40 ? '#9a6700' : '#cf222e';
const gradient = 'conic-gradient(' + circleStroke + ' 0% ' + score + '%, var(--border-muted) ' + score + '% 100%)';

let html = '';

// ─── SCORE CARD ───
html += '<div class="card">';
html += '<div class="score-card">';
html += '<div class="score-circle" style="background:' + gradient + '">';
html += '<div style="background:var(--bg);border-radius:50%;width:110px;height:110px;display:flex;align-items:center;justify-content:center;flex-direction:column">';
html += '<div class="score-val" style="color:' + color + '">' + score + '</div>';
html += '<div class="score-grade" style="color:' + color + '">' + grade + '</div>';
html += '</div></div>';
html += '<div class="score-details">';
html += '<h2>SEO Score: ' + score + ' / 100</h2>';
html += '<div class="url">' + esc(r.url) + '</div>';
if (r.platform && r.platform.platforms) {
html += '<div style="font-size:12px;color:var(--text-muted);margin-top:8px">Detected: <strong>' + esc(r.platform.platforms.join(', ')) + '</strong></div>';
}
html += '<div class="stats-grid">';
html += '<div class="stat-item pass"><div class="n">' + (r.counters.passed || 0) + '</div><div class="l">Passed</div></div>';
html += '<div class="stat-item warn"><div class="n">' + (r.counters.warned || 0) + '</div><div class="l">Warnings</div></div>';
html += '<div class="stat-item fail"><div class="n">' + (r.counters.failed || 0) + '</div><div class="l">Failed</div></div>';
html += '<div class="stat-item"><div class="n">' + (r.http.load_time_ms || 0) + '</div><div class="l">Load (ms)</div></div>';
html += '<div class="stat-item"><div class="n">' + Math.round((r.http.content_length || 0) / 1024) + '</div><div class="l">HTML (KB)</div></div>';
html += '</div>';
html += '</div></div></div>';

// ─── W3C INFO ───
if (r.w3c && r.w3c.html && r.w3c.html.ok) {
html += '<div class="card">';
html += '<div class="check-group-header">W3C HTML Validation</div>';
html += '<div style="padding:16px 20px">';
html += '<div style="display:flex;gap:24px;font-family:var(--font-mono);font-size:13px">';
html += '<span><strong style="color:#cf222e">' + (r.w3c.html.errors_count || 0) + '</strong> errors</span>';
html += '<span><strong style="color:#9a6700">' + (r.w3c.html.warnings_count || 0) + '</strong> warnings</span>';
html += '<a href="https://validator.w3.org/nu/?doc=' + encodeURIComponent(r.url) + '" target="_blank" style="margin-left:auto">View full report →</a>';
html += '</div></div></div>';
}

// ─── CHECKLIST GROUPED BY CATEGORY ───
const categories = {};
r.checks.forEach(function(c) {
if (!categories[c.category]) categories[c.category] = [];
categories[c.category].push(c);
});

Object.keys(categories).forEach(function(cat) {
html += '<div class="card">';
html += '<div class="check-group-header">' + esc(cat.toUpperCase()) + '</div>';
html += '<ul class="checklist">';
categories[cat].forEach(function(c) {
let icon = '✓';
if (c.status === 'warn') icon = '!';
else if (c.status === 'fail') icon = '✕';
else if (c.status === 'info') icon = 'i';

html += '<li class="check-item">';
html += '<span class="check-icon ' + c.status + '">' + icon + '</span>';
html += '<div class="check-content">';
html += '<div class="check-name">' + esc(c.name) + '</div>';
if (c.message) {
html += '<div class="check-message">' + esc(c.message) + '</div>';
}
html += '</div>';
html += '<div class="check-points">' + c.points + '/' + c.max_points + '</div>';
html += '</li>';
});
html += '</ul></div>';
});

// ─── DOWNLOAD JSON ───
html += '<div style="text-align:center;padding:20px">';
html += '<button onclick="downloadJSON()" class="primary">⬇ Download full report (JSON)</button>';
html += '</div>';

layout.innerHTML = html;
}

function downloadJSON() {
if (!currentReport) return;
const blob = new Blob([JSON.stringify(currentReport, null, 2)], {type: 'application/json'});
const url = URL.createObjectURL(blob);
const a = document.createElement('a');
a.href = url;
const domain = currentReport.domain || 'report';
a.download = 'seo-report-' + domain + '-' + Date.now() + '.json';
a.click();
}

// Init theme
(function() {
try {
const saved = localStorage.getItem('seo-theme');
if (saved) document.documentElement.setAttribute('data-theme', saved);
} catch(e) {}
})();

// Enter to analyze
document.getElementById('url').addEventListener('keydown', function(e) {
if (e.key === 'Enter') analyze();
});
</script>
</body>
</html>"""


# ═══════════════════════════════════════════════════════════════════════════════
# HTTP HANDLER
# ═══════════════════════════════════════════════════════════════════════════════

class Handler(BaseHTTPRequestHandler):
def log_message(self, fmt, *args):
pass

def _send_json(self, code: int, data: Any):
try:
body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
self.send_response(code)
self.send_header("Content-Type", "application/json; charset=utf-8")
self.send_header("Access-Control-Allow-Origin", "*")
self.send_header("Content-Length", str(len(body)))
self.end_headers()
self.wfile.write(body)
except (BrokenPipeError, ConnectionResetError):
pass

def _send_html(self, code: int, html_str: str):
try:
body = html_str.encode("utf-8")
self.send_response(code)
self.send_header("Content-Type", "text/html; charset=utf-8")
self.send_header("Content-Length", str(len(body)))
self.end_headers()
self.wfile.write(body)
except (BrokenPipeError, ConnectionResetError):
pass

def do_GET(self):
parsed = urlparse(self.path)
path = parsed.path

if path in ("/", "/index.html"):
self._send_html(200, INDEX_HTML.replace("__V__", VERSION))
return

if path == "/api/version":
self._send_json(200, {"version": VERSION, "engine": "NexusSEO"})
return

if path == "/api/health":
self._send_json(200, {"ok": True, "timestamp": time.time()})
return

self._send_json(404, {"error": "not found"})

def do_POST(self):
parsed = urlparse(self.path)
path = parsed.path

if path == "/api/analyze":
try:
length = int(self.headers.get("Content-Length", 0))
body = self.rfile.read(length)
data = json.loads(body.decode("utf-8"))
url = (data.get("url") or "").strip()

if not url:
self._send_json(400, {"ok": False, "error": "URL missing"})
return

# Auto-add https://
if not url.startswith(("http://", "https://")):
url = "https://" + url

# Validate
parsed_url = urlparse(url)
if not parsed_url.netloc:
self._send_json(400, {"ok": False, "error": "Invalid URL"})
return

analyzer = SEOAnalyzer(url)
result = analyzer.analyze()
self._send_json(200, result)

except json.JSONDecodeError:
self._send_json(400, {"ok": False, "error": "Invalid JSON"})
except Exception as e:
self._send_json(500, {"ok": False, "error": str(e)[:200]})
return

self._send_json(404, {"error": "not found"})


class Server(ThreadingHTTPServer):
daemon_threads = True
allow_reuse_address = True


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def print_banner():
print("")
print(" ╔══════════════════════════════════════════════════════════════╗")
print(" ║ ║")
print(" ║ ███╗ ██╗███████╗██╗ ██╗██╗ ██╗███████╗ ║")
print(" ║ ████╗ ██║██╔════╝╚██╗██╔╝██║ ██║██╔════╝ ║")
print(" ║ ██╔██╗ ██║█████╗ ╚███╔╝ ██║ ██║███████╗ ║")
print(" ║ ██║╚██╗██║██╔══╝ ██╔██╗ ██║ ██║╚════██║ ║")
print(" ║ ██║ ╚████║███████╗██╔╝ ██╗╚██████╔╝███████║ ║")
print(" ║ ╚═╝ ╚═══╝╚══════╝╚═╝ ╚═╝ ╚═════╝ ╚══════╝ ║")
print(" ║ ║")
print(" ║ SEO ANALYZER v{} ║".format(VERSION))
print(" ║ W3C Validation · Real SEO Score ║")
print(" ║ No API key · No dependency ║")
print(" ║ ║")
print(" ╚══════════════════════════════════════════════════════════════╝")
print("")


def main():
parser = argparse.ArgumentParser(description="Nexus SEO Analyzer")
parser.add_argument("--port", type=int, default=PORT)
parser.add_argument("--host", type=str, default=HOST)
args = parser.parse_args()

print_banner()
print(" Platform : {} {}".format(
__import__("platform").system(),
__import__("platform").release()
))
print(" URL : http://{}:{}".format(args.host, args.port))
print(" Checks : HTTP · HTTPS · Meta · Headings · Images · Links · OG · JSON-LD · Perf")
print(" W3C : HTML + CSS validation (w3.org API)")
print(" Ctrl+C to stop")
print("")

try:
server = Server((args.host, args.port), Handler)
server.serve_forever()
except KeyboardInterrupt:
print("\n Shutting down...")
try:
server.shutdown()
except Exception:
pass
except OSError as e:
print(" Port {} error: {}".format(args.port, e))
print(" Try: python3 nexus_seo.py --port 8091")
return 1

return 0


if __name__ == "__main__":
sys.exit(main())
