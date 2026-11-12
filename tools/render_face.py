from pathlib import Path
import cairosvg
from PIL import Image,ImageDraw,ImageFont
root=Path(__file__).resolve().parents[1]/'face-preview'
for p in root.glob('*.svg'):cairosvg.svg2png(url=str(p),write_to=str(p.with_suffix('.png')))
canvas=Image.new('RGB',(1500,790),'#0b1016');draw=ImageDraw.Draw(canvas)
font=ImageFont.truetype(str(Path(__file__).parent/'DejaVuSans.ttf') if (Path(__file__).parent/'DejaVuSans.ttf').exists() else 'DejaVuSans.ttf',24)
large=ImageFont.truetype(str(Path(__file__).parent/'DejaVuSans.ttf') if (Path(__file__).parent/'DejaVuSans.ttf').exists() else 'DejaVuSans.ttf',30)
draw.text((60,30),'TIMO / FIVE EXPRESSIONS',font=large,fill='#e7f4fb')
items=[('normal','معمولی',30,100),('happy','شاد',520,100),('surprised','متعجب',1010,100),('sad','غمگین',275,440),('angry','عصبانی',765,440)]
for mode,label,x,y in items:
 draw.rounded_rectangle((x,y,x+460,y+304),radius=22,fill='#1b1b1b')
 im=Image.open(root/(mode+'.png')).convert('RGB').resize((460,276),Image.Resampling.LANCZOS);canvas.paste(im,(x,y))
 draw.text((x+230,y+282),label,font=font,fill='#d8ebf7',anchor='mm',direction='rtl')
canvas.save(root/'five-expressions.png')
print(root/'five-expressions.png')
