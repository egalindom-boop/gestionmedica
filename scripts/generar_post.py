# -*- coding: utf-8 -*-
"""
Robot de blog diario de gestionmedica.org
- Elige un tema de temas.txt no usado (temas_usados.json), rotando categorías.
- Genera el artículo con la API de Claude usando marcadores de sección
  (inmunes a errores de escapado JSON), con 3 reintentos y validación.
- Crea /slug/index.html, y actualiza portada (ticker + sección + índice),
  la página de su categoría y sitemap.xml mediante marcadores AUTO.
"""
import os, re, json, random, time, unicodedata, html
from datetime import date
from urllib import request as urlreq
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_KEY = os.environ['ANTHROPIC_API_KEY']
MODELO = os.environ.get('MODELO_CLAUDE', 'claude-sonnet-4-5')
SITE = 'https://gestionmedica.org'
MESES = {1:'Ene',2:'Feb',3:'Mar',4:'Abr',5:'May',6:'Jun',7:'Jul',8:'Ago',9:'Sep',10:'Oct',11:'Nov',12:'Dic'}
CATS = {
    'software-medico':'Software Médico','telemedicina':'Telemedicina',
    'privacidad-seguridad':'Privacidad & Seguridad','gestion-medica':'Gestión Médica',
    'medicina-privada':'Medicina privada','marketing-clinicas':'Marketing Médico',
    'cita-online':'Cita online','noticias':'Noticias',
}
IMAGENES = [
    '/wp-content/uploads/2016/08/DriCloud-Apple-1.jpg',
    '/wp-content/uploads/2015/07/software-medico1.jpg',
    '/wp-content/uploads/2015/07/gestion-medica2.jpg',
    '/wp-content/uploads/2015/07/maketing-medico.jpg',
    '/wp-content/uploads/2015/07/software-clinicas.jpg',
]

def slugify(t):
    t = unicodedata.normalize('NFKD', t).encode('ascii', 'ignore').decode()
    t = re.sub(r'[^a-zA-Z0-9]+', '-', t).strip('-').lower()
    return t[:70].rstrip('-')

def hoy_fmt():
    d = date.today()
    return f'{d.day:02d} {MESES[d.month]} {d.year}'

# ---------- elegir tema ----------
temas = []
for ln in open(os.path.join(RAIZ, 'temas.txt'), encoding='utf-8'):
    ln = ln.strip()
    if ln and '|' in ln:
        c, t = ln.split('|', 1)
        temas.append((c.strip(), t.strip()))

usados_path = os.path.join(RAIZ, 'temas_usados.json')
usados = json.load(open(usados_path)) if os.path.exists(usados_path) else []
pendientes = [t for t in temas if t[1] not in usados]
if not pendientes:
    usados, pendientes = [], temas[:]
# rotar categoría: evitar repetir la última usada si es posible
ult_cat = usados and next((c for c, t in temas if t == usados[-1]), None)
candidatos = [t for t in pendientes if t[0] != ult_cat] or pendientes
cat, tema = random.choice(candidatos)
print('Tema elegido:', cat, '|', tema)

# ---------- generar con Claude (marcadores de sección) ----------
PROMPT = f"""Eres el redactor del blog gestionmedica.org, revista española sobre software médico y gestión de clínicas.
Escribe un artículo original y útil sobre: "{tema}" (categoría: {CATS[cat]}).

Reglas estrictas:
- Español de España, tono profesional cercano, dirigido a médicos propietarios de clínicas pequeñas.
- 700-1000 palabras. HTML con <p>, <h2>, <h3>, <ul>/<li>, <strong>. Sin <h1>, sin <html>/<body>.
- Incluye de forma natural 1 enlace <a href="https://dricloud.com/" target="_blank" rel="noopener">software medico</a> o con anchor "programa medico" o "software clinicas".
- Incluye 1 enlace interno a la comparativa: <a href="/software-medico/">comparativa de software médico</a>.
- No menciones nunca XClinics.
- No inventes datos concretos (cifras exactas, leyes inexistentes); habla en términos generales y prácticos.

Responde EXACTAMENTE en este formato, sin nada antes ni después:
===TITULO===
(título atractivo de 50-65 caracteres, sin comillas)
===SLUG===
(slug-url-en-minusculas-con-guiones, máx 60 caracteres)
===DESCRIPCION===
(meta descripción de 140-155 caracteres)
===LEDE===
(primer párrafo resumen de 2 frases, texto plano)
===CUERPO===
(el artículo completo en HTML)
===FIN===
"""

def llamar_api():
    datos = json.dumps({
        'model': MODELO, 'max_tokens': 4000,
        'messages': [{'role': 'user', 'content': PROMPT}],
    }).encode()
    req = urlreq.Request('https://api.anthropic.com/v1/messages', data=datos, headers={
        'x-api-key': API_KEY, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'})
    with urlreq.urlopen(req, timeout=180) as r:
        resp = json.load(r)
    return ''.join(b.get('text', '') for b in resp.get('content', []))

def extraer(texto, marca):
    m = re.search(f'==={marca}===\\s*(.*?)\\s*(?====[A-Z]+===)', texto, re.S)
    return m.group(1).strip() if m else ''

articulo = None
for intento in range(3):
    try:
        txt = llamar_api()
        titulo = extraer(txt, 'TITULO')
        slug = slugify(extraer(txt, 'SLUG') or titulo)
        desc = extraer(txt, 'DESCRIPCION')
        lede = extraer(txt, 'LEDE')
        cuerpo = extraer(txt, 'CUERPO')
        if titulo and slug and desc and len(cuerpo) > 500 and '<p>' in cuerpo and 'xclinics' not in cuerpo.lower():
            articulo = dict(titulo=titulo, slug=slug, desc=desc, lede=lede, cuerpo=cuerpo)
            break
        print(f'Intento {intento+1}: validación fallida (cuerpo={len(cuerpo)})')
    except Exception as e:
        print(f'Intento {intento+1}: error {e}')
    time.sleep(20)

if not articulo:
    raise SystemExit('No se pudo generar un artículo válido tras 3 intentos')

slug = articulo['slug']
if os.path.isdir(os.path.join(RAIZ, slug)):
    slug = f"{slug}-{date.today().strftime('%Y%m%d')}"
img = random.choice(IMAGENES)
fecha = hoy_fmt()
iso = date.today().isoformat()
titulo_e = html.escape(articulo['titulo'])
desc_e = html.escape(articulo['desc'])

# ---------- crear página del post a partir de la plantilla ----------
plantilla = open(os.path.join(RAIZ, 'scripts', 'plantilla_post.html'), encoding='utf-8').read()
pagina = (plantilla
    .replace('{{TITULO}}', titulo_e)
    .replace('{{DESCRIPCION}}', desc_e)
    .replace('{{SLUG}}', slug)
    .replace('{{CATEGORIA}}', cat)
    .replace('{{CATEGORIA_NOMBRE}}', CATS[cat])
    .replace('{{FECHA}}', fecha)
    .replace('{{FECHA_ISO}}', iso)
    .replace('{{IMAGEN}}', img)
    .replace('{{LEDE}}', f"<p><strong>{html.escape(articulo['lede'])}</strong></p>" if articulo['lede'] else '')
    .replace('{{CUERPO}}', articulo['cuerpo']))
os.makedirs(os.path.join(RAIZ, slug), exist_ok=True)
open(os.path.join(RAIZ, slug, 'index.html'), 'w', encoding='utf-8').write(pagina)

def insertar(ruta, marcador, linea):
    fp = os.path.join(RAIZ, ruta)
    if not os.path.exists(fp):
        print('AVISO: no existe', ruta); return
    h = open(fp, encoding='utf-8').read()
    if marcador not in h:
        print('AVISO: marcador no encontrado', marcador, 'en', ruta); return
    h = h.replace(marcador, marcador + '\n' + linea, 1)
    open(fp, 'w', encoding='utf-8').write(h)

enlace = f'<a href="/{slug}/">{titulo_e}</a>'
# portada: ticker, sección de su categoría e índice completo
insertar('index.html', '<!-- AUTO:TICKER -->', enlace)
insertar('index.html', f'<!-- AUTO:SEC:{cat} -->',
         f'<li>{enlace}<span class="fecha">{fecha}</span></li>')
insertar('index.html', f'<!-- AUTO:INDEX:{cat} -->', enlace + ' · ')
# página de categoría
insertar(f'category/{cat}/index.html', '<!-- AUTO:LISTA -->', f"""<li class="tarjeta"><img src="{img}" alt="" loading="lazy" width="220"><div>
<h2><a href="/{slug}/">{titulo_e}</a></h2>
<p>{desc_e}</p>
<p class="fecha">{fecha} · Editor</p>
</div></li>""")
# sitemap
# sitemap: se regenera entero desde la fecha real de cada página,
# para que el lastmod nunca se quede congelado
import subprocess
subprocess.run([sys.executable, os.path.join(RAIZ, 'scripts', 'generar_sitemap.py'), RAIZ], check=False)

# registrar tema usado
usados.append(tema)
json.dump(usados, open(usados_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('Publicado:', f'{SITE}/{slug}/')
