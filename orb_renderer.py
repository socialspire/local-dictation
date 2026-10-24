"""Procedural Orbital preview geometry, driven by the real audio envelope."""
import math
import numpy as np
from PIL import Image, ImageDraw, ImageChops

TAU = math.tau
NODES = []
for i in range(2200):
    y = 1 - 2 * (i + .5) / 2200
    a = i * 2.39996323
    NODES.append((math.sqrt(1-y*y)*math.cos(a), y,
                  math.sqrt(1-y*y)*math.sin(a), i*.731))


def voice_energy(level):
    """Visual gain only: suppress low noise and lift normal speech, not ASR input."""
    return min(1., max(0., (level-.035)/.60))**.65


class OrbRenderer:
    def __init__(self):
        self.angle = 0.
        self.time = 0.
        self.waves = []
        self.last_wave = -1.
        self.previous_energy = 0.
        # Cached radial gradients avoid per-frame per-pixel Python work.
        y, x = np.mgrid[-1:1:256j, -1:1:256j]
        d = np.sqrt(x*x+y*y)
        stops = [0, .13, .4, 1]
        colors = [(242,232,177), (178,147,62), (49,29,4), (0,0,0)]
        rgb = np.stack([np.interp(d, stops, [c[k] for c in colors]) for k in range(3)],axis=-1)
        self.glow = Image.fromarray(rgb.astype('uint8'))

    def render(self, size, level, processing=False, dt=.04, enabled=True):
        level = voice_energy(level) if enabled and not processing else 0.
        self.time += dt
        self.angle += dt*(.46 if processing else .025+level*.28)
        t, angle = self.time, self.angle
        # Speech launches wavefronts; silence never creates a simulated signal.
        if level>.10 and t-self.last_wave>(.12 if level-self.previous_energy>.10 else .28):
            self.waves.append((t,level))
            self.last_wave=t
        self.previous_energy=level
        self.waves=[wave for wave in self.waves if t-wave[0]<1.15]
        if not enabled or processing:
            self.waves.clear()
        image = Image.new('RGB', (size,size))
        draw = ImageDraw.Draw(image)
        center = size/2
        radius = size*.29*(1+level*.14)
        c,s = math.cos(angle),math.sin(angle)
        ct,st = math.cos(.22),math.sin(.22)

        def project(x,y,z):
            xx,zz = x*c+z*s,z*c-x*s
            yy,depth = y*ct-zz*st,y*st+zz*ct
            p = 2.8/(2.8-depth*.36)
            return center+xx*p*radius,center+yy*p*radius,depth

        def color(rgb, alpha):
            return tuple(int(v*max(0,min(1,alpha))) for v in rgb)

        for j in range(19):
            lat=-1+(j+1)/10; rr=math.sqrt(max(0,1-lat*lat)); points=[]
            for k in range(161):
                a=k/160*TAU
                n=1+.008*math.sin(a*11+j+t*.4)+level*.07*math.sin(a*19-t*3)
                p=project(math.cos(a)*rr*n,lat+math.sin(a*7+t+j)*.015,math.sin(a)*rr*n)
                points.append(p[:2])
            draw.line(points,fill=color((221,142,39),.08+level*.25))
        for x,y,z,seed in NODES:
            drift=1+.006*math.sin(t*.4+seed)+level*(.07+.11*math.sin(seed+t*4))
            px,py,depth=project(x*drift,y*drift,z*drift)
            front=max(0,min(1,(depth+1)/2))
            flicker=.85+.15*math.sin(seed*9+t*(.3+level*3))
            col=color((255,151+front*60,48+front*65),(.10+front*.48+level*.4)*flicker)
            sz=(.5+front*.7)*(1+level*.8)
            draw.ellipse((px,py,px+sz,py+sz),fill=col)
        for j in range(3):
            rot=angle*(-1.5 if j%2 else 1.2)+j*1.05
            rad=radius*(1.13+j*.085+level*.055)
            cr,sr=math.cos(rot),math.sin(rot)
            def ring(a):
                x,y=math.cos(a)*rad,math.sin(a)*rad*(.45+j*.18)
                return center+x*cr-y*sr,center+x*sr+y*cr
            points=[ring(.2+j+k/160*5.4) for k in range(161)]
            draw.line(points,fill=color((244,185,83),.3+level*.3))
            for k in range(3):
                x,y=ring(t*(.3+j*.08)+k*TAU/3)
                r=1.2+level
                draw.ellipse((x-r,y-r,x+r,y+r),fill=(255,231,166))
        core=radius*(.10+level*.23+math.sin(t*1.2)*.003)
        extent=max(4,int(core*5.6))
        glow_layer=Image.new('RGB',(size,size))
        glow_layer.paste(self.glow.resize((extent,extent),Image.Resampling.BILINEAR),((size-extent)//2,(size-extent)//2))
        image=ImageChops.add(image,glow_layer)
        draw=ImageDraw.Draw(image)
        for j in range(6):
            points=[]
            for k in range(71):
                a=k/70*TAU; r=core*(1+.22*math.sin(a*3+t*2+j))
                points.append((center+math.cos(a)*r,center+math.sin(a)*r*.75))
            draw.line(points,fill=color((255,206,92),.16+j*.018))
        for born,strength in self.waves:
            phase=(t-born)/1.15
            r=size*(.285+phase*.195)
            col=color((255,202,105),strength*(1-phase)**1.5*.85)
            # Open concentric arcs evoke a radio transmission around the sphere.
            for start,end in ((-65,65),(115,245)):
                draw.arc((center-r,center-r,center+r,center+r),start,end,fill=col,width=2)
        return image
