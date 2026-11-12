from pathlib import Path
root=Path(__file__).resolve().parents[1]
assets=root/'android/robot/src/main/assets';assets.mkdir(parents=True,exist_ok=True)
# فایل چهرهٔ اندروید و پیش‌نمایش‌ها از یک منبع برداری ساخته می‌شوند.
blue='#238ed5';pink='#ff646f'
def eye(x,y=275,r=79,mode='normal'):
 glint=f'<circle cx="{x+23}" cy="{y-25}" r="30" fill="#f6fbff"/><circle cx="{x-37}" cy="{y+38}" r="9" fill="#dcf5ff"/>'
 ball=f'<circle cx="{x}" cy="{y}" r="{r}" fill="url(#iris)"/>'+glint
 if mode=='happy':
  ball=f'<path d="M{x-82} {y+22} Q{x} {y-113} {x+82} {y+22}" fill="none" stroke="{blue}" stroke-width="29" stroke-linecap="round"/>'
 elif mode=='sad':
  ball=f'<g clip-path="url(#sad-{x})">{ball}</g><path d="M{x-70} {y-29} Q{x} {y-5} {x+70} {y-29}" stroke="#182027" fill="none" stroke-width="13"/>'
 elif mode=='upset':
  sign=1 if x<500 else -1
  ball=f'<g clip-path="url(#upset-{x})">{ball}</g>'
  ball+=f'<path d="M{x-78} {y-90-sign*17} L{x+78} {y-90+sign*17}" fill="none" stroke="{blue}" stroke-width="16" stroke-linecap="round"/>'
 elif mode=='surprised':
  ball=f'<circle cx="{x}" cy="{y-12}" r="92" fill="url(#iris)"/><circle cx="{x+24}" cy="{y-40}" r="32" fill="#f6fbff"/><circle cx="{x-42}" cy="{y+32}" r="10" fill="#dcf5ff"/>'
 return f'<g class="eye blink">{ball}</g>'
def expression(mode):
 eyes=eye(323,mode=mode)+eye(677,mode=mode)
 mouth={
 'normal':f'<path d="M474 385 Q500 447 526 385"/>',
 'happy':f'<path d="M441 382 Q500 431 559 382 Q546 455 500 458 Q454 455 441 382Z" fill="{blue}" stroke="none"/><path d="M473 443 Q500 429 527 443" stroke="#83d6ff" stroke-width="9"/>',
 'sad':'<path d="M470 422 Q500 378 530 422"/>',
 'upset':'<path d="M468 417 Q500 399 532 417"/>',
 'surprised':f'<ellipse cx="500" cy="404" rx="25" ry="36"/>'}[mode]
 tear=''
 if mode=='sad':tear='<path class="tear" d="M245 337 C245 337 226 362 226 374 A19 19 0 0 0 264 374 C264 362 245 337 245 337Z" fill="#67ceff"/><circle cx="238" cy="375" r="5" fill="#d8f9ff"/>'
 cheeks=f'<g fill="{pink}" opacity=".94"><ellipse cx="253" cy="390" rx="35" ry="18"/><ellipse cx="747" cy="390" rx="35" ry="18"/></g>'
 return f'{cheeks}{eyes}<g class="mouth" fill="none" stroke="{blue}" stroke-width="7" stroke-linecap="round" stroke-linejoin="round">{mouth}</g>{tear}'
def defs():
 return '''<defs><radialGradient id="iris" cx="35%" cy="26%" r="85%"><stop offset="0" stop-color="#2a9ce5"/><stop offset="1" stop-color="#1678bd"/></radialGradient>
 <clipPath id="sad-323"><path d="M220 251 Q323 277 426 251 V380 H220Z"/></clipPath><clipPath id="sad-677"><path d="M574 251 Q677 277 780 251 V380 H574Z"/></clipPath>
 <clipPath id="upset-323"><path d="M220 212 L426 270 V380 H220Z"/></clipPath><clipPath id="upset-677"><path d="M574 270 L780 212 V380 H574Z"/></clipPath></defs>'''
styles='''html,body{margin:0;width:100%;height:100%;overflow:hidden;background:#1b1b1b}body{display:grid;place-items:center}svg{display:block;width:100%;height:100%;max-height:100vh;user-select:none;-webkit-user-select:none}.expression{opacity:0;transition:opacity .24s ease}.expression.active{opacity:1}.eye{transform-box:fill-box;transform-origin:center}.active .blink{animation:blink 6.3s infinite}.face-breathe{transform-origin:500px 310px;animation:breathe 5s ease-in-out infinite}@keyframes blink{0%,44%,48%,100%{transform:scaleY(1)}46%{transform:scaleY(.07)}}@keyframes breathe{0%,100%{transform:translateY(0)}50%{transform:translateY(-3px)}}@media(prefers-reduced-motion:reduce){.blink,.face-breathe{animation:none!important}.expression{transition:none}}'''
modes=['normal','happy','sad','upset','surprised']
svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 600" role="img" aria-label="Timo face">'+defs()+'<g class="face-breathe">'+''.join(f'<g id="{m}" class="expression'+(' active' if m=='normal' else '')+'">'+expression(m)+'</g>' for m in modes)+'</g></svg>'
html='''<!doctype html><html lang="fa"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'"><title>Timo face</title><style>'''+styles+'</style></head><body>'+svg+'''<script>'use strict';window.setTimoExpression=function(name){if(!['normal','happy','sad','upset','surprised'].includes(name))return false;document.querySelectorAll('.expression').forEach(function(el){el.classList.toggle('active',el.id===name);});document.body.dataset.expression=name;return true;};window.setTimoExpression('normal');</script></body></html>'''
(assets/'face.html').write_text(html)
previews=root/'face-preview';previews.mkdir(exist_ok=True)
for m in modes:
 (previews/(m+'.svg')).write_text('<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="600" viewBox="0 0 1000 600"><rect width="1000" height="600" fill="#1b1b1b"/>'+defs()+expression(m)+'</svg>')
(previews/'index.html').write_text('''<!doctype html><html lang="fa" dir="rtl"><meta charset="utf-8"><title>پیش‌نمایش چهرهٔ تیمو</title><style>body{background:#111;color:#eee;font:18px Tahoma;margin:30px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}figure{margin:0;background:#1b1b1b;border-radius:24px;overflow:hidden}img{width:100%;display:block}figcaption{text-align:center;padding:14px}</style><h1>پنج حالت چهرهٔ تیمو</h1><div class="grid">'''+''.join(f'<figure><img src="{m}.svg"><figcaption>{label}</figcaption></figure>' for m,label in zip(modes,['معمولی','شاد','غمگین','عصبانی','متعجب']))+'</div></html>')
print('Offline native face + five SVG previews generated.')

p=previews/'index.html';p.write_text(p.read_text().replace('upset.svg','angry.svg'))

# نام نمایشی تازه برای گرافیک عصبانیِ نسخه‌های قبلی.
import shutil
shutil.copyfile(previews/'upset.svg',previews/'angry.svg')
