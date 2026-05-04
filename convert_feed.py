import os
import re
import time
import requests
import xml.etree.ElementTree as ET

API_KEY = os.environ['PS_API_KEY']
BASE_URL = 'https://mayorista.mohicano.cl'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'application/xml, text/xml, */*',
}


def strip_html(text):
    if not text:
        return ''
    return re.sub(r'<[^>]+>', ' ', text).strip()


def image_url(image_id):
    path = '/'.join(list(str(image_id)))
    return f"{BASE_URL}/img/p/{path}/{image_id}-large_default.jpg"


def fetch_with_retry(url, params, retries=3, delay=10):
    for attempt in range(1, retries + 1):
        try:
            print(f"Intento {attempt}/{retries}...")
            resp = requests.get(url, params=params, headers=HEADERS, timeout=180)
            resp.raise_for_status()
            return resp
        except Exception as e:
            print(f"Error en intento {attempt}: {e}")
            if attempt < retries:
                time.sleep(delay)
    raise RuntimeError("No se pudo conectar a la API después de varios intentos.")


print("Fetching categories from PrestaShop API...")
cat_resp = fetch_with_retry(f"{BASE_URL}/api/categories", params={
    'ws_key': API_KEY,
    'output_format': 'XML',
    'display': '[id,name]',
})
cat_tree = ET.fromstring(cat_resp.content)
categories = {
    c.findtext('id').strip(): (c.findtext('.//name/language') or '').strip()
    for c in cat_tree.findall('.//category')
    if c.findtext('id')
}
print(f"Found {len(categories)} categories.")

print("Fetching products from PrestaShop API...")
resp = fetch_with_retry(f"{BASE_URL}/api/products", params={
    'ws_key': API_KEY,
    'output_format': 'XML',
    'display': 'full',
})

ps = ET.fromstring(resp.content)
products = ps.findall('.//product')
print(f"Found {len(products)} products total.")

lines = [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">',
    '<channel>',
    '<title>Mohicano Mayorista</title>',
    f'<link>{BASE_URL}</link>',
    '<description>Catálogo de productos Mohicano Mayorista</description>',
]

count = 0
for p in products:
    # Saltar productos inactivos
    active = (p.findtext('active') or '0').strip()
    if active != '1':
        continue

    pid = (p.findtext('id') or '').strip()
    name = (p.findtext('.//name/language') or '').strip()
    if not pid or not name:
        continue

    desc = strip_html(
        p.findtext('.//description_short/language')
        or p.findtext('.//description/language')
        or ''
    ) or name  # fallback al nombre si no hay descripción
    price_raw = p.findtext('price') or '0'
    price = f"{float(price_raw):.0f} CLP"

    slug = (p.findtext('.//link_rewrite/language') or '').strip()
    link = (
        f"{BASE_URL}/{pid}-{slug}.html"
        if slug
        else f"{BASE_URL}/index.php?id_product={pid}&controller=product"
    )

    img_id = (p.findtext('id_default_image') or '').strip()
    img = image_url(img_id) if img_id and img_id != '0' else ''

    avail = (
        'in stock'
        if (p.findtext('available_for_order') or '0').strip() == '1'
        else 'out of stock'
    )
    ref = (p.findtext('reference') or '').strip()
    cat_id = (p.findtext('id_category_default') or '').strip()
    cat_name = categories.get(cat_id, '')

    lines.append('<item>')
    lines.append(f'<g:id>{pid}</g:id>')
    lines.append(f'<g:title><![CDATA[{name}]]></g:title>')
    lines.append(f'<g:description><![CDATA[{desc}]]></g:description>')
    lines.append(f'<g:price>{price}</g:price>')
    lines.append(f'<g:link>{link}</g:link>')
    if img:
        lines.append(f'<g:image_link>{img}</g:image_link>')
    lines.append(f'<g:availability>{avail}</g:availability>')
    lines.append('<g:condition>new</g:condition>')
    if cat_name:
        lines.append(f'<g:product_type><![CDATA[{cat_name}]]></g:product_type>')
    if ref:
        lines.append(f'<g:mpn><![CDATA[{ref}]]></g:mpn>')
    lines.append('</item>')
    count += 1

lines += ['</channel>', '</rss>']

with open('products.xml', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print(f"Done! Generated products.xml with {count} active products.")