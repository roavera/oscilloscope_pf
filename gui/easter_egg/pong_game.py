"""OscilloPong: juego independiente de la adquisición."""
import random
from time import monotonic
from PySide6.QtCore import Qt, QEvent, QObject, QTimer, QRectF, QPointF, QSettings
from PySide6.QtGui import QColor, QPainter, QPen, QFont
from PySide6.QtWidgets import QApplication, QDialog, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox, QLabel

K = Qt.Key

class Arena(QWidget):
    W, H = 800, 460
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(480, 280)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.keys = set()
        self.settings = QSettings('OsciloscopioPF', 'Osciloscopio')
        self.best = self.settings.value('arcade/pong_best', 0, type=int)
        self.two = False
        self.difficulty = 1
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.tick)
        self.reset()
        self.timer.start()

    def reset(self):
        self.score = [0, 0]
        self.pads = [self.H/2, self.H/2]
        self.paused = True
        self.finished = False
        self.keys.clear()
        self.serve(random.choice([-1, 1]))
        self.last = monotonic()
        self.update()

    def serve(self, direction):
        self.x, self.y = self.W/2, self.H/2
        self.vx, self.vy = direction*310, random.choice([-1,1])*random.uniform(70,150)

    def keyPressEvent(self, e):
        if e.key() in (K.Key_Up,K.Key_Down,K.Key_W,K.Key_S):
            self.keys.add(e.key()); e.accept()
        elif e.key() == K.Key_Space:
            if not e.isAutoRepeat():
                if self.finished: self.reset()
                self.paused = not self.paused
            e.accept()
        else: super().keyPressEvent(e)

    def keyReleaseEvent(self,e):
        self.keys.discard(e.key())
        super().keyReleaseEvent(e)

    def focusOutEvent(self,e):
        self.keys.clear()
        self.paused = True
        self.update()
        super().focusOutEvent(e)

    def tick(self):
        now = monotonic(); dt = min(now-self.last, .035); self.last = now
        if self.paused or self.finished: return
        half = 47
        def clamp(v): return max(half,min(self.H-half,v))
        up, down = (K.Key_W,K.Key_S) if self.two else (K.Key_Up,K.Key_Down)
        self.pads[0] = clamp(self.pads[0]+420*dt*((down in self.keys)-(up in self.keys)))
        if self.two:
            self.pads[1] = clamp(self.pads[1]+420*dt*((K.Key_Down in self.keys)-(K.Key_Up in self.keys)))
        else:
            speed = (180,285,405)[self.difficulty]
            target = self.y if self.vx>0 else self.H/2
            self.pads[1] = clamp(self.pads[1]+max(-speed*dt,min(speed*dt,target-self.pads[1])))
        oldx = self.x
        self.x += self.vx*dt; self.y += self.vy*dt
        if self.y<7: self.y=14-self.y; self.vy=abs(self.vy)
        elif self.y>self.H-7: self.y=2*(self.H-7)-self.y; self.vy=-abs(self.vy)
        for i,edge in enumerate((39,self.W-39)):
            crossed = oldx>=edge>=self.x if i==0 else oldx<=edge<=self.x
            if crossed and abs(self.y-self.pads[i])<=half+7:
                self.x=edge
                self.vx=(1 if i==0 else -1)*min(650,abs(self.vx)*1.07)
                self.vy=380*(self.y-self.pads[i])/(half+7)
        if self.x < -10 or self.x > self.W+10:
            i=1 if self.x<0 else 0
            self.score[i]+=1
            if not self.two and self.score[0]>self.best:
                self.best=self.score[0]; self.settings.setValue('arcade/pong_best',self.best)
            if self.score[i]>=7: self.finished=True; self.paused=True
            else: self.serve(1 if i==0 else -1)
        self.update()

    def paintEvent(self,e):
        light = self.settings.value('appearance/theme','dark',type=str)=='light'
        bg,grid,fg,c1,c2,ball = ('#E8EFF5','#C4D3E0','#183149','#007F9C','#B52390','#007D65') if light else ('#030C1C','#153047','#EDF5FF','#00EFFF','#FF31CE','#61DBBB')
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(),QColor(bg)); s=min(self.width()/self.W,self.height()/self.H)
        p.translate((self.width()-self.W*s)/2,(self.height()-self.H*s)/2); p.scale(s,s)
        p.setPen(QPen(QColor(grid),1))
        for x in range(0,801,50): p.drawLine(x,0,x,460)
        for y in range(0,461,46): p.drawLine(0,y,800,y)
        p.setPen(QPen(QColor(grid),2,Qt.PenStyle.DashLine)); p.drawLine(400,0,400,460)
        p.setFont(QFont('Consolas',32,QFont.Weight.Bold))
        for i,c in enumerate((c1,c2)):
            p.setPen(QColor(c)); p.drawText(QRectF(250+i*200,12,100,65),Qt.AlignmentFlag.AlignCenter,str(self.score[i]).zfill(2))
            r=QRectF(20 if i==0 else 768,self.pads[i]-47,12,94)
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(c)); p.drawRoundedRect(r,3,3)
        p.setBrush(QColor(ball)); p.setPen(Qt.PenStyle.NoPen); p.drawEllipse(QPointF(self.x,self.y),7,7)
        if self.paused or self.finished:
            p.fillRect(QRectF(190,175,420,110),QColor(bg)); p.setPen(QColor(fg)); p.setFont(QFont('Segoe UI',19,QFont.Weight.Bold))
            msg=('¡Jugador 1 gana!' if self.score[0]>=7 else ('¡Jugador 2 gana!' if self.two else 'CPU gana')) if self.finished else 'OSCILLOPONG'
            p.drawText(QRectF(190,180,420,50),Qt.AlignmentFlag.AlignCenter,msg)
            p.setFont(QFont('Segoe UI',12)); p.drawText(QRectF(190,230,420,35),Qt.AlignmentFlag.AlignCenter,'ESPACIO para '+('reiniciar' if self.finished else 'jugar / continuar'))
        p.end()

class PongDialog(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent); self.setWindowTitle('OscilloPong · Arcade'); self.resize(850,600)
        layout=QVBoxLayout(self); row=QHBoxLayout(); layout.addLayout(row)
        self.mode=QComboBox(); self.mode.addItems(['Jugador vs CPU','Dos jugadores']); row.addWidget(self.mode)
        self.level=QComboBox(); self.level.addItems(['Fácil','Normal','Difícil']); self.level.setCurrentIndex(1); row.addWidget(self.level)
        reset=QPushButton('Reiniciar'); row.addWidget(reset); close=QPushButton('Salir'); row.addWidget(close)
        self.arena=Arena(self); layout.addWidget(self.arena,1)
        self.help=QLabel(); self.help.setWordWrap(True); layout.addWidget(self.help)
        self.mode.currentIndexChanged.connect(self.configure); self.level.currentIndexChanged.connect(self.configure); reset.clicked.connect(self.configure); close.clicked.connect(self.reject)
        self.configure()
    def configure(self,*_):
        self.arena.two=self.mode.currentIndex()==1; self.arena.difficulty=self.level.currentIndex(); self.level.setEnabled(not self.arena.two)
        self.arena.reset(); self.arena.setFocus()
        self.help.setText(('J1: W/S · J2: ↑/↓' if self.arena.two else '↑/↓: mover')+' · Espacio: jugar/pausa · ESC: salir · Primero a 7')
    def done(self,result):
        self.arena.timer.stop(); super().done(result)

class SecretCode(QObject):
    CODE=(K.Key_Up,K.Key_Up,K.Key_Down,K.Key_Down,K.Key_Left,K.Key_Right,K.Key_Left,K.Key_Right,K.Key_B,K.Key_A)
    def __init__(self,page):
        super().__init__(page); self.page=page; self.history=[]; self.last=0; self.opened=False
        QApplication.instance().installEventFilter(self)
    def eventFilter(self, obj, event):
        if event.type() != QEvent.Type.KeyPress or event.isAutoRepeat():
            return False
        app = QApplication.instance()
        if self.opened or not self.page.isVisible() or app.activeModalWidget() is not None:
            self.history.clear()
            return False
        # El evento puede llegar a QWindow, a un hijo o al botón de inicio.
        active = app.activeWindow()
        if active is not None and active != self.page.window():
            self.history.clear()
            return False
        mods = event.modifiers()
        alternative = (event.key() == K.Key_P and
                       bool(mods & Qt.KeyboardModifier.ControlModifier) and
                       bool(mods & Qt.KeyboardModifier.ShiftModifier))
        now = monotonic()
        if now - self.last > 10:
            self.history.clear()
        self.last = now
        self.history = (self.history + [event.key()])[-len(self.CODE):]
        if alternative or tuple(self.history) == self.CODE:
            self.history.clear()
            self.opened = True
            QTimer.singleShot(0, self.open_game)
            return True
        return False
    def open_game(self):
        try:
            if self.page.isVisible():
                game=PongDialog(self.page); self.page.run_arcade_dialog(game); game.deleteLater()
        finally: self.opened=False

def install(page):
    page._pong_secret=SecretCode(page)
    # OSCILLOPONG_ACCESS_V2
    from PySide6.QtGui import QShortcut, QKeySequence
    shortcut = QShortcut(QKeySequence("Ctrl+Shift+P"), page)
    shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
    def launch():
        secret = page._pong_secret
        if page.isVisible() and not secret.opened and QApplication.instance().activeModalWidget() is None:
            secret.opened = True
            secret.history.clear()
            QTimer.singleShot(0, secret.open_game)
    shortcut.activated.connect(launch)
    page._pong_shortcut = shortcut
    page.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
