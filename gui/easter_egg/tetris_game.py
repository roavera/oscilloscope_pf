"""OscilloTetris: arcade independiente del sistema de adquisición."""
import random
from PySide6.QtCore import Qt, QTimer, QRectF, QSettings
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QShortcut, QKeySequence
from PySide6.QtWidgets import QWidget, QDialog, QVBoxLayout, QApplication

SHAPES = {'I': ((0,1),(1,1),(2,1),(3,1)), 'O': ((0,0),(1,0),(0,1),(1,1)),
          'T': ((1,0),(0,1),(1,1),(2,1)), 'S': ((1,0),(2,0),(0,1),(1,1)),
          'Z': ((0,0),(1,0),(1,1),(2,1)), 'J': ((0,0),(0,1),(1,1),(2,1)),
          'L': ((2,0),(0,1),(1,1),(2,1))}

class Board:
    W,H=10,20
    def __init__(self):
        self.grid=[[None]*self.W for _ in range(self.H)]
        self.bag=[]; self.next=self.draw(); self.hold=None; self.used_hold=False
        self.score=self.lines=0; self.over=False; self.spawn()
    @property
    def level(self): return 1+self.lines//10
    def draw(self):
        if not self.bag: self.bag=list(SHAPES); random.shuffle(self.bag)
        return self.bag.pop()
    def spawn(self,kind=None):
        if kind is None: kind=self.next; self.next=self.draw()
        self.kind=kind; self.cells=SHAPES[kind]; self.x=3; self.y=0
        if not self.valid(self.cells,self.x,self.y): self.over=True
    def valid(self,cells,x,y):
        return all(0<=x+a<self.W and 0<=y+b<self.H and not self.grid[y+b][x+a] for a,b in cells)
    def move(self,dx,dy):
        if not self.over and self.valid(self.cells,self.x+dx,self.y+dy): self.x+=dx; self.y+=dy; return True
        return False
    def rotate(self):
        if self.kind=='O' or self.over: return
        n=3 if self.kind=='I' else 2
        cells=tuple((n-b,a) for a,b in self.cells)
        for dx,dy in ((0,0),(-1,0),(1,0),(-2,0),(2,0),(0,-1),(0,-2)):
            if self.valid(cells,self.x+dx,self.y+dy): self.cells=cells; self.x+=dx; self.y+=dy; return
    def ghost(self):
        y=self.y
        if not self.over:
            while self.valid(self.cells,self.x,y+1): y+=1
        return y
    def lock(self):
        if self.over: return
        for a,b in self.cells: self.grid[self.y+b][self.x+a]=self.kind
        keep=[r for r in self.grid if not all(r)]; n=self.H-len(keep)
        self.score+=(0,100,300,500,800)[n]*self.level
        self.lines+=n; self.grid=[[None]*self.W for _ in range(n)]+keep
        self.used_hold=False; self.spawn()
    def step(self,manual=False):
        if self.move(0,1): self.score+=int(manual)
        else: self.lock()
    def drop(self):
        if self.over: return
        y=self.ghost(); self.score+=2*(y-self.y); self.y=y; self.lock()
    def reserve(self):
        if self.used_hold or self.over: return
        old=self.hold; self.hold=self.kind; self.spawn(old); self.used_hold=True

class Arena(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent); self.setMinimumSize(500,540); self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.settings=QSettings('OsciloscopioPF','Osciloscopio'); self.best=self.settings.value('arcade/tetris_best',0,type=int)
        self.timer=QTimer(self); self.timer.timeout.connect(self.tick); self.reset()
    def reset(self):
        self.board=Board(); self.paused=True; self.timer.stop(); self.update()
    def sync(self):
        b=self.board
        if b.score>self.best: self.best=b.score; self.settings.setValue('arcade/tetris_best',self.best)
        if b.over or self.paused: self.timer.stop()
        else:
            interval=max(85,800-(b.level-1)*65)
            if not self.timer.isActive() or self.timer.interval()!=interval: self.timer.start(interval)
        self.update()
    def tick(self):
        if not self.paused and not self.board.over: self.board.step(); self.sync()
    def keyPressEvent(self,e):
        k=e.key(); K=Qt.Key; b=self.board
        if k in (K.Key_P,K.Key_Return,K.Key_Enter) and not e.isAutoRepeat():
            if b.over: self.reset()
            self.paused=not self.paused; self.sync()
        elif k==K.Key_R and not e.isAutoRepeat(): self.reset()
        elif not self.paused and not b.over:
            if k==K.Key_Left: b.move(-1,0)
            elif k==K.Key_Right: b.move(1,0)
            elif k==K.Key_Up: b.rotate()
            elif k==K.Key_Down: b.step(True)
            elif k==K.Key_Space and not e.isAutoRepeat(): b.drop()
            elif k==K.Key_C and not e.isAutoRepeat(): b.reserve()
            else: super().keyPressEvent(e); return
            self.sync()
        else: super().keyPressEvent(e); return
        e.accept()
    def focusOutEvent(self,e):
        self.paused=True; self.sync(); super().focusOutEvent(e)
    def paintEvent(self,e):
        light=self.settings.value('appearance/theme','dark',type=str)=='light'
        bg,field,grid,fg,accent=('#E8EFF5','#FFFFFF','#CCD9E4','#183149','#007F9C') if light else ('#030C1C','#071323','#183148','#EDF5FF','#00EFFF')
        colors=dict(zip(SHAPES,('#007F9C','#A67C00','#7545BC','#007D65','#B52390','#2857B5','#B65C12') if light else ('#00EFFF','#FFE45C','#B46CFF','#61DBBB','#FF31CE','#447EFF','#FFAD4D')))
        p=QPainter(self); p.fillRect(self.rect(),QColor(bg)); s=min(self.width()/540,self.height()/580); p.translate((self.width()-540*s)/2,(self.height()-580*s)/2); p.scale(s,s)
        p.setPen(QColor(accent)); p.setFont(QFont('Segoe UI',22,QFont.Weight.Bold)); p.drawText(QRectF(0,0,540,44),Qt.AlignmentFlag.AlignCenter,'OSCILLOTETRIS')
        ox,oy,d=28,50,24; p.fillRect(QRectF(ox,oy,240,480),QColor(field)); p.setPen(QPen(QColor(grid),1))
        for x in range(11): p.drawLine(ox+x*d,oy,ox+x*d,oy+480)
        for y in range(21): p.drawLine(ox,oy+y*d,ox+240,oy+y*d)
        def block(x,y,k,ghost=False,size=d):
            c=QColor(colors[k]); r=QRectF(x+1,y+1,size-2,size-2)
            p.setPen(QPen(c,1)); p.setBrush(Qt.BrushStyle.NoBrush if ghost else c); p.drawRoundedRect(r,2,2)
        b=self.board
        for y,row in enumerate(b.grid):
            for x,k in enumerate(row):
                if k: block(ox+x*d,oy+y*d,k)
        if not b.over:
            for a,z in b.cells: block(ox+(b.x+a)*d,oy+(b.ghost()+z)*d,b.kind,True)
            for a,z in b.cells: block(ox+(b.x+a)*d,oy+(b.y+z)*d,b.kind)
        for i,(label,value) in enumerate((('PUNTOS',b.score),('NIVEL',b.level),('LÍNEAS',b.lines),('RÉCORD',self.best))):
            y=55+i*65; p.setPen(QColor(fg)); p.setFont(QFont('Segoe UI',11)); p.drawText(300,y+15,label); p.setPen(QColor(accent)); p.setFont(QFont('Consolas',22)); p.drawText(300,y+43,str(value))
        for label,k,y in (('PRÓXIMA',b.next,320),('RESERVA',b.hold,420)):
            p.setPen(QColor(fg)); p.setFont(QFont('Segoe UI',11)); p.drawText(300,y,label)
            if k:
                for a,z in SHAPES[k]: block(300+a*20,y+10+z*20,k,size=20)
        if self.paused or b.over:
            p.fillRect(QRectF(ox,225,240,100),QColor(bg)); p.setPen(QColor(fg)); p.setFont(QFont('Segoe UI',16,QFont.Weight.Bold)); p.drawText(QRectF(ox,225,240,50),Qt.AlignmentFlag.AlignCenter,'FIN DE PARTIDA' if b.over else 'PAUSA'); p.setFont(QFont('Segoe UI',11)); p.drawText(QRectF(ox,275,240,45),Qt.AlignmentFlag.AlignCenter,'ENTER para '+('reiniciar' if b.over else 'jugar / continuar'))
        p.setPen(QColor(fg)); p.setFont(QFont('Segoe UI',10)); p.drawText(QRectF(0,535,540,40),Qt.AlignmentFlag.AlignCenter,'Flechas: mover/rotar · Espacio: caída · C: reserva\nP: pausa · R: reiniciar · ESC: salir'); p.end()

class TetrisDialog(QDialog):
    def __init__(self,parent):
        super().__init__(parent); self.setWindowTitle('OscilloTetris · Arcade'); self.resize(620,690)
        layout=QVBoxLayout(self); self.arena=Arena(self); layout.addWidget(self.arena); self.arena.setFocus()
    def done(self,result):
        self.arena.timer.stop(); super().done(result)

def install(page):
    if hasattr(page,'_tetris_shortcut'): return
    shortcut=QShortcut(QKeySequence('Ctrl+Shift+T'),page); shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
    def launch():
        app=QApplication.instance()
        if not page.isVisible() or app.activeModalWidget() is not None: return
        game=TetrisDialog(page)
        try: page.run_arcade_dialog(game)
        finally: game.arena.timer.stop(); game.deleteLater()
    shortcut.activated.connect(launch); page._tetris_shortcut=shortcut
