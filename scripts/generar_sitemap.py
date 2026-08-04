# -*- coding: utf-8 -*-
"""Genera sitemap.xml con lastmod real, leído del schema de cada página.

Reglas:
  lastmod = dateModified del schema si existe, si no datePublished.
  Las páginas con reescritura de fondo llevan la fecha de esa reescritura.
Este script es el que debe ejecutar el robot en cada publicación, para que
el lastmod no vuelva a quedarse congelado.
"""
import re, os, json, sys
from datetime import date

BASE = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
SITE = 'https://gestionmedica.org'
HOY = date.today().isoformat()

# páginas reescritas a fondo hoy
REESCRITAS = {'software-medico', 'sobre-nosotros', ''}

PRIORIDAD = {'': '1.0', 'software-medico': '1.0', 'sobre-nosotros': '0.6',
             'politica-editorial': '0.6'}
FREQ = {'': 'daily', 'software-medico': 'weekly'}

EXCLUIR_DIR = {'.git', 'wp-content', 'images', 'scripts', '.github', 'category'}


def fecha_de(ruta):
    """Saca la fecha de modificación declarada en la propia página."""
    try:
        h = open(ruta, encoding='utf-8').read()
    except Exception:
        return None
    # 1. schema dateModified
    for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', h, re.S):
        try:
            d = json.loads(b)
        except Exception:
            continue
        nodos = d.get('@graph', [d])
        for g in nodos:
            if g.get('@type') == 'Article':
                f = g.get('dateModified') or g.get('datePublished')
                if f:
                    return f[:10]
    # 2. <time datetime="...">
    m = re.search(r'<time datetime="(\d{4}-\d{2}-\d{2})"', h)
    if m:
        return m.group(1)
    return None


urls = []
# raíz
raiz = os.path.join(BASE, 'index.html')
if os.path.isfile(raiz):
    urls.append(('', fecha_de(raiz) or HOY))
# subcarpetas
for d in sorted(os.listdir(BASE)):
    ruta_dir = os.path.join(BASE, d)
    if d.startswith('.') or d in EXCLUIR_DIR or not os.path.isdir(ruta_dir):
        continue
    fp = os.path.join(ruta_dir, 'index.html')
    if os.path.isfile(fp):
        urls.append((d + '/', fecha_de(fp) or HOY))
# categorías
cat_dir = os.path.join(BASE, 'category')
if os.path.isdir(cat_dir):
    for c in sorted(os.listdir(cat_dir)):
        fp = os.path.join(cat_dir, c, 'index.html')
        if os.path.isfile(fp):
            urls.append((f'category/{c}/', HOY))

# las reescritas llevan la fecha de hoy
urls = [(u, (HOY if u.strip('/') in REESCRITAS else f)) for u, f in urls]

lineas = []
for u, f in urls:
    slug = u.strip('/')
    p = PRIORIDAD.get(slug, '0.7' if slug.startswith('category/') else '0.8')
    cf = FREQ.get(slug, 'monthly')
    lineas.append(f'<url><loc>{SITE}/{u}</loc><lastmod>{f}</lastmod>'
                  f'<changefreq>{cf}</changefreq><priority>{p}</priority></url>')

sm = ('<?xml version="1.0" encoding="UTF-8"?>\n'
      '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
      + '\n'.join(lineas) + '\n<!-- AUTO:SITEMAP -->\n</urlset>\n')
open(os.path.join(BASE, 'sitemap.xml'), 'w', encoding='utf-8').write(sm)

print(f'✓ sitemap.xml con {len(urls)} URLs')
from collections import Counter
print('  reparto de fechas:', Counter(f for _, f in urls).most_common(6))
print('  comparativa ->', dict(urls).get('software-medico/'))
