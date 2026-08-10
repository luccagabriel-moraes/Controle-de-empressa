import sys
import os
import json
import uuid
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QStackedWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QAbstractItemView, QDateEdit, QInputDialog, QLineEdit,
    QAbstractItemDelegate
)
from PyQt6.QtCore import Qt, QDate, QSize, QRectF, QPointF, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor, QPixmap, QPainter, QPainterPath, QPen, QLinearGradient


# --------------------------------------------------------------------------- #
# Configuração
# --------------------------------------------------------------------------- #

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
CACHE_DIR = os.path.join(BASE_DIR, "cache")

# URL do Web App do Google Apps Script (termina em "/exec").
GOOGLE_SHEETS_WEBHOOK_URL = ""

# nome, cor de destaque, cor do texto sobre essa cor e o caminho da logo (None = ícone/texto)
COMPANIES = [
    {
        "nome": "Granola Pura",
        "logo": os.path.join(ASSETS_DIR, "granola_pura.png"),
        "logo_zoom": 0.86,
        "cor": "#c98a3e",
        "cor_texto": "#1a1208",
    },
    {
        "nome": "Narua",
        "logo": os.path.join(ASSETS_DIR, "narus.png"),
        "logo_zoom": 0.76,
        "cor": "#8a4b12",
        "cor_texto": "#ffffff",
    },
    {
        "nome": "Contas em Casa",
        "logo": None,
        "icone_texto": "🏠",
        "cor": "#f1c40f",
        "cor_texto": "#1a1a1a",
    },
]

BORDA_COR = "#e8e8e8"
BORDA_ESPESSURA = 3

COLUNAS_ENTRADAS = ["Data", "Quantidade", "Preço Unitário", "Preço Total"]
COL_DATA, COL_QTD, COL_PRECO_UNIT, COL_TOTAL = range(4)

ROWS_INICIAIS = 1  # linhas em branco ao abrir um produto novo/sem registros


# --------------------------------------------------------------------------- #
# Utilitários
# --------------------------------------------------------------------------- #

def format_moeda(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def parse_numero(texto: str) -> float:
    """Aceita '1234,56' ou '1234.56' e devolve float (0.0 se vazio/inválido)."""
    texto = (texto or "").strip().replace("R$", "").strip()
    if not texto:
        return 0.0
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return 0.0


def gerar_id() -> str:
    return uuid.uuid4().hex[:12]


def normalizar_data_sheets(valor) -> str:
    """O Sheets às vezes converte a data enviada em data real e devolve em
    ISO (ex: '2026-07-01T03:00:00.000Z'); aqui convertemos de volta pra
    dd/MM/yyyy."""
    texto = str(valor if valor is not None else "").strip()
    if not texto:
        return ""

    if "T" in texto and texto.endswith("Z"):
        for formato in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
            try:
                return datetime.strptime(texto, formato).strftime("%d/%m/%Y")
            except ValueError:
                continue

    return texto


def obter_ultima_compra(linhas_produto: list):
    """Retorna o registro com a data mais recente, ou o último da lista se
    nenhuma data for válida."""
    if not linhas_produto:
        return None
    melhor, melhor_data = None, None
    for linha in linhas_produto:
        data_qd = QDate.fromString(str(linha.get("data", "")), "dd/MM/yyyy")
        if data_qd.isValid() and (melhor_data is None or data_qd > melhor_data):
            melhor_data, melhor = data_qd, linha
    return melhor if melhor is not None else linhas_produto[-1]


# --------------------------------------------------------------------------- #
# Cache local (deixa a lista aparecer na hora, mesmo antes do Sheets responder)
# --------------------------------------------------------------------------- #
# Guarda em disco a última lista de cada empresa: a tela mostra isso na hora
# e atualiza em paralelo assim que o Sheets responder.

def _cache_arquivo(empresa: str) -> str:
    nome_seguro = "".join(c if c.isalnum() else "_" for c in empresa)
    return os.path.join(CACHE_DIR, f"{nome_seguro}.json")


def cache_carregar(empresa: str):
    """Retorna a lista de linhas em cache, ou None se não houver cache válido."""
    caminho = _cache_arquivo(empresa)
    if not os.path.exists(caminho):
        return None
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def cache_salvar(empresa: str, linhas: list):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(_cache_arquivo(empresa), "w", encoding="utf-8") as f:
            json.dump(linhas, f, ensure_ascii=False)
    except OSError:
        pass  # cache é só otimização; se falhar, seguimos sem ele


# --------------------------------------------------------------------------- #
# Integração com Google Sheets
# --------------------------------------------------------------------------- #
# Funções puras (sem Qt), executadas em segundo plano por SheetsWorker.

class ErroSheets(Exception):
    """Erro de comunicação com o Google Sheets (rede, configuração ou o
    próprio Apps Script reportando falha)."""


def _requisitar(url: str, dados: bytes = None, metodo: str = "GET", timeout: int = 20) -> dict:
    if not GOOGLE_SHEETS_WEBHOOK_URL:
        raise ErroSheets("A URL do Google Sheets não foi configurada (GOOGLE_SHEETS_WEBHOOK_URL).")
    try:
        requisicao = urllib.request.Request(
            url, data=dados,
            headers={"Content-Type": "application/json"} if dados else {},
            method=metodo,
        )
        with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:
            corpo_bruto = resposta.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise ErroSheets(f"O Google respondeu com erro HTTP {e.code}.") from e
    except urllib.error.URLError as e:
        raise ErroSheets(f"Não foi possível conectar ao Google Sheets: {e.reason}") from e
    except OSError as e:
        raise ErroSheets(f"Tempo esgotado ou falha de rede ao falar com o Google Sheets: {e}") from e

    try:
        corpo = json.loads(corpo_bruto)
    except (ValueError, json.JSONDecodeError) as e:
        trecho = corpo_bruto[:200].replace("\n", " ")
        raise ErroSheets(
            "A resposta do Apps Script não é um JSON válido (confira se o script está implantado "
            f"corretamente e o acesso é 'Qualquer pessoa'). Resposta recebida: {trecho}"
        ) from e

    if not corpo.get("ok"):
        raise ErroSheets(corpo.get("erro", "Erro desconhecido retornado pelo Apps Script."))
    return corpo


def sheets_buscar(empresa: str = None) -> list:
    url = GOOGLE_SHEETS_WEBHOOK_URL
    if empresa:
        url += "?" + urllib.parse.urlencode({"empresa": empresa})
    corpo = _requisitar(url, metodo="GET", timeout=40)
    linhas = corpo.get("linhas", [])

    for linha in linhas:
        linha["data"] = normalizar_data_sheets(linha.get("data"))

    return linhas


def sheets_salvar(novas: list, existentes: list) -> None:
    payload = json.dumps({"acao": "salvar", "novas": novas, "existentes": existentes}).encode("utf-8")
    _requisitar(GOOGLE_SHEETS_WEBHOOK_URL, dados=payload, metodo="POST")


def sheets_remover(ids: list) -> None:
    payload = json.dumps({"acao": "remover", "ids": ids}).encode("utf-8")
    _requisitar(GOOGLE_SHEETS_WEBHOOK_URL, dados=payload, metodo="POST")


class SheetsWorker(QThread):
    """Executa uma função de rede (sheets_buscar/sheets_salvar/sheets_remover)
    em segundo plano e avisa o resultado via sinal Qt."""

    concluido = pyqtSignal(bool, object)  # (sucesso, resultado_ou_mensagem_de_erro)

    def __init__(self, funcao, *args, **kwargs):
        super().__init__()
        self._funcao = funcao
        self._args = args
        self._kwargs = kwargs

    def run(self):
        try:
            resultado = self._funcao(*self._args, **self._kwargs)
            self.concluido.emit(True, resultado)
        except ErroSheets as e:
            self.concluido.emit(False, str(e))
        except Exception as e:
            self.concluido.emit(False, f"Erro inesperado: {e}")


# --------------------------------------------------------------------------- #
# Logos / avatares circulares
# --------------------------------------------------------------------------- #

def recortar_em_circulo(pixmap_original: QPixmap, tamanho: int, zoom: float = 1.0) -> QPixmap:
    """Recorta o centro da imagem, encaixa num círculo transparente e
    desenha uma borda fina ao redor."""
    largura_o, altura_o = pixmap_original.width(), pixmap_original.height()
    lado_o = min(largura_o, altura_o)
    lado_recorte = int(lado_o * zoom)
    x_o = (largura_o - lado_recorte) // 2
    y_o = (altura_o - lado_recorte) // 2
    recortado = pixmap_original.copy(x_o, y_o, lado_recorte, lado_recorte)

    resultado = QPixmap(tamanho, tamanho)
    resultado.fill(Qt.GlobalColor.transparent)

    escalado = recortado.scaled(
        tamanho, tamanho,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )

    painter = QPainter(resultado)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    margem = BORDA_ESPESSURA
    caminho_circulo = QPainterPath()
    caminho_circulo.addEllipse(margem / 2, margem / 2, tamanho - margem, tamanho - margem)
    painter.setClipPath(caminho_circulo)

    x = (tamanho - escalado.width()) // 2
    y = (tamanho - escalado.height()) // 2
    painter.drawPixmap(x, y, escalado)

    painter.setClipping(False)
    caneta = painter.pen()
    caneta.setColor(QColor(BORDA_COR))
    caneta.setWidth(BORDA_ESPESSURA)
    painter.setPen(caneta)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(QRectF(margem / 2, margem / 2, tamanho - margem, tamanho - margem))
    painter.end()
    return resultado


def criar_avatar_circular(empresa: dict, tamanho: int = 130) -> QLabel:
    """QLabel circular com a logo da empresa, ou um ícone/texto se não houver logo."""
    label = QLabel()
    label.setFixedSize(tamanho, tamanho)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)

    logo_path = empresa.get("logo")
    if logo_path and os.path.exists(logo_path):
        pixmap_original = QPixmap(logo_path)
        zoom = empresa.get("logo_zoom", 1.0)
        label.setPixmap(recortar_em_circulo(pixmap_original, tamanho, zoom))
    else:
        label.setText(empresa.get("icone_texto", empresa["nome"][:2].upper()))
        font = QFont()
        font.setPointSize(36)
        label.setFont(font)
        label.setStyleSheet(
            f"background-color: {empresa['cor']}; color: {empresa['cor_texto']}; "
            f"border-radius: {tamanho // 2}px; border: {BORDA_ESPESSURA}px solid {BORDA_COR};"
        )
    return label


# --------------------------------------------------------------------------- #
# Rótulo que trunca texto longo (em vez de desalinhar o layout)
# --------------------------------------------------------------------------- #

class LabelElidavel(QLabel):
    """QLabel que trunca o próprio texto com reticências quando não cabe no
    espaço disponível, em vez de empurrar o resto do layout. O texto completo
    continua acessível via tooltip.

    `minimumSizeHint()` é sobrescrito pra nunca acompanhar o texto atual —
    senão um texto grande travaria o layout num mínimo grande antes mesmo do
    primeiro redimensionamento, e a label nunca chegaria a encolher."""

    def __init__(self, texto: str = "", parent=None):
        super().__init__(parent)
        self._texto_completo = ""
        self.setText(texto)

    def setText(self, texto: str):
        self._texto_completo = texto
        self.setToolTip(texto)
        super().setText(texto)
        self._reelidir()

    def minimumSizeHint(self):
        largura_minima = self.fontMetrics().horizontalAdvance("...")
        return QSize(largura_minima, super().minimumSizeHint().height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reelidir()

    def _reelidir(self):
        texto_elidido = self.fontMetrics().elidedText(
            self._texto_completo, Qt.TextElideMode.ElideRight, self.width()
        )
        super().setText(texto_elidido)


# --------------------------------------------------------------------------- #
# Mini gráfico de tendência de preço
# --------------------------------------------------------------------------- #

class MiniGraficoPreco(QWidget):
    """Evolução do preço unitário ao longo do tempo, com área em gradiente e
    linha suavizada. Verde = tendência de queda, vermelho = tendência de alta."""

    def __init__(self, valores=None, parent=None):
        super().__init__(parent)
        self.valores = valores or []
        self.setFixedSize(230, 84)

    def set_valores(self, valores):
        self.valores = valores or []
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        largura, altura = self.width(), self.height()

        fundo = QPainterPath()
        fundo.addRoundedRect(0.5, 0.5, largura - 1, altura - 1, 10, 10)
        painter.fillPath(fundo, QColor("#1b1b1b"))
        painter.setPen(QPen(QColor("#3a3a3a"), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(fundo)

        if len(self.valores) < 2:
            painter.setPen(QColor("#777777"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "sem dados suficientes")
            painter.end()
            return

        minimo, maximo = min(self.valores), max(self.valores)
        amplitude = (maximo - minimo) or 1
        margem_lateral, margem_topo, margem_base = 12, 22, 12
        n = len(self.valores)
        area_util_altura = altura - margem_topo - margem_base

        pontos = []
        for i, valor in enumerate(self.valores):
            x = margem_lateral + (largura - 2 * margem_lateral) * (i / (n - 1))
            y = margem_topo + area_util_altura - area_util_altura * ((valor - minimo) / amplitude)
            pontos.append(QPointF(x, y))

        subiu = self.valores[-1] > self.valores[0]
        cor = QColor("#e74c3c") if subiu else QColor("#2ecc71")

        caminho = QPainterPath()
        caminho.moveTo(pontos[0])
        for i in range(1, len(pontos)):
            anterior, atual = pontos[i - 1], pontos[i]
            meio_x = (anterior.x() + atual.x()) / 2
            caminho.cubicTo(QPointF(meio_x, anterior.y()), QPointF(meio_x, atual.y()), atual)

        caminho_preenchido = QPainterPath(caminho)
        caminho_preenchido.lineTo(pontos[-1].x(), altura - margem_base)
        caminho_preenchido.lineTo(pontos[0].x(), altura - margem_base)
        caminho_preenchido.closeSubpath()

        gradiente = QLinearGradient(0, margem_topo, 0, altura - margem_base)
        cor_topo, cor_base = QColor(cor), QColor(cor)
        cor_topo.setAlpha(110)
        cor_base.setAlpha(0)
        gradiente.setColorAt(0.0, cor_topo)
        gradiente.setColorAt(1.0, cor_base)
        painter.fillPath(caminho_preenchido, gradiente)

        caneta_linha = QPen(cor)
        caneta_linha.setWidthF(2.4)
        caneta_linha.setCapStyle(Qt.PenCapStyle.RoundCap)
        caneta_linha.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(caneta_linha)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(caminho)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#1b1b1b"))
        painter.drawEllipse(pontos[-1], 5, 5)
        painter.setBrush(cor)
        painter.drawEllipse(pontos[-1], 3.2, 3.2)

        fonte_rotulo = QFont()
        fonte_rotulo.setPointSize(8)
        painter.setFont(fonte_rotulo)
        painter.setPen(QColor("#aaaaaa"))
        painter.drawText(
            QRectF(0, 2, largura - 10, 14),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            f"máx {format_moeda(maximo)}   mín {format_moeda(minimo)}",
        )
        painter.end()


# --------------------------------------------------------------------------- #
# Tabela de compras com navegação por Enter
# --------------------------------------------------------------------------- #

class TabelaComNavegacaoEnter(QTableWidget):
    """QTableWidget da tela de compras: Enter avança Data -> Quantidade ->
    Preço Unitário em vez do padrão do Qt. Em Preço Unitário só confirma o
    valor e para ali, sem criar linha nova."""

    # O hint oficial do Enter se chama "SubmitModelData", mas em algumas
    # versões do binding PyQt6 aparece como "SubmitModelCache" (erro
    # conhecido) — tenta o nome oficial e cai pro alternativo.
    _HINT_ENTER = getattr(
        QAbstractItemDelegate.EndEditHint, "SubmitModelData", None
    ) or QAbstractItemDelegate.EndEditHint.SubmitModelCache

    def closeEditor(self, editor, hint):
        if hint != self._HINT_ENTER:
            super().closeEditor(editor, hint)
            return

        row, col = self.currentRow(), self.currentColumn()
        super().closeEditor(editor, QAbstractItemDelegate.EndEditHint.NoHint)

        proxima_coluna = {COL_DATA: COL_QTD, COL_QTD: COL_PRECO_UNIT}.get(col)
        if proxima_coluna is None:
            return  # estava em Preço Unitário: fica parado ali, sem criar linha nova

        self.setCurrentCell(row, proxima_coluna)
        self.editItem(self.item(row, proxima_coluna))


# --------------------------------------------------------------------------- #
# Página 3: registros (compras) de um produto específico
# --------------------------------------------------------------------------- #

class ProductEntriesPage(QWidget):
    """Mostra e edita as compras de um produto. Cada linha da tabela guarda
    seu ID da planilha em Qt.ItemDataRole.UserRole (None = ainda não existe
    no Sheets)."""

    def __init__(self, empresa: dict, produto: str, linhas_iniciais: list, voltar_callback):
        super().__init__()
        self.empresa = empresa
        self.produto = produto
        self.cor = empresa["cor"]
        self.voltar_callback = voltar_callback
        self._carregando = False
        self._operacao_em_andamento = False
        self._worker = None
        self._alteracoes_nao_salvas = False  # edição pendente de salvar (ver _tentar_voltar)
        # True quando a MainWindow já destruiu esta página (ex: abriu outro
        # produto); callbacks de rede atrasados checam isso antes de mexer
        # em widgets, evitando o RuntimeError de objeto C++ já deletado.
        self._destruida = False

        self._montar_ui()
        self._popular_tabela(linhas_iniciais)

    def marcar_destruida(self):
        self._destruida = True

    def _montar_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        layout.addLayout(self._criar_linha_titulo())
        layout.addLayout(self._criar_linha_filtro())

        self.tabela = TabelaComNavegacaoEnter(0, len(COLUNAS_ENTRADAS))
        self.tabela.setHorizontalHeaderLabels(COLUNAS_ENTRADAS)
        self.tabela.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabela.setAlternatingRowColors(True)
        self.tabela.horizontalHeader().setStyleSheet(
            f"QHeaderView::section {{ background-color: {self.cor}; color: {self.empresa['cor_texto']}; "
            f"padding: 6px; font-weight: bold; }}"
        )
        self.tabela.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.tabela)

        self.label_total = QLabel("Total do produto: R$ 0,00")
        font_total = QFont()
        font_total.setPointSize(12)
        font_total.setBold(True)
        self.label_total.setFont(font_total)
        self.label_total.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.label_total.setStyleSheet(f"color: {self.cor};")
        layout.addWidget(self.label_total)

        layout.addLayout(self._criar_linha_botoes())

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #2e7d32;")
        layout.addWidget(self.status_label)

    def _criar_linha_titulo(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        self.btn_voltar = QPushButton("← Voltar")
        self.btn_voltar.clicked.connect(self._tentar_voltar)

        bloco_esquerdo_widget = QWidget()
        bloco_esquerdo = QHBoxLayout(bloco_esquerdo_widget)
        bloco_esquerdo.setContentsMargins(0, 0, 0, 0)
        bloco_esquerdo.setSpacing(10)
        bloco_esquerdo.addWidget(self.btn_voltar)
        bloco_esquerdo.addSpacing(14)

        self.label_melhor_compra = QLabel("Melhor compra: -")
        self.label_melhor_compra.setStyleSheet("color: #2ecc71; font-weight: bold;")
        bloco_esquerdo.addWidget(self.label_melhor_compra)

        self.label_pior_compra = QLabel("Pior compra: -")
        self.label_pior_compra.setStyleSheet("color: #e74c3c; font-weight: bold;")
        bloco_esquerdo.addWidget(self.label_pior_compra)

        self.mini_grafico = MiniGraficoPreco()
        bloco_esquerdo.addWidget(self.mini_grafico)

        titulo = LabelElidavel(f"{self.empresa['nome']}  ›  {self.produto}")
        fonte_titulo = QFont()
        fonte_titulo.setPointSize(16)
        fonte_titulo.setBold(True)
        titulo.setFont(fonte_titulo)
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        titulo.setStyleSheet(f"color: {self.cor};")

        # Espaçador do mesmo tamanho do bloco esquerdo, pra manter o título centralizado
        espacador = QLabel("")
        espacador.setMinimumWidth(bloco_esquerdo_widget.sizeHint().width())

        linha.addWidget(bloco_esquerdo_widget)
        linha.addWidget(titulo, stretch=1)
        linha.addWidget(espacador)
        return linha

    def _criar_linha_filtro(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setSpacing(8)
        linha.addStretch()

        linha.addWidget(QLabel("De:"))
        self.filtro_data_de = QDateEdit()
        self.filtro_data_de.setDisplayFormat("dd/MM/yyyy")
        self.filtro_data_de.setCalendarPopup(True)
        self.filtro_data_de.setMinimumWidth(120)
        self.filtro_data_de.setDate(QDate.currentDate().addYears(-5))
        linha.addWidget(self.filtro_data_de)

        linha.addSpacing(10)
        linha.addWidget(QLabel("Até:"))
        self.filtro_data_ate = QDateEdit()
        self.filtro_data_ate.setDisplayFormat("dd/MM/yyyy")
        self.filtro_data_ate.setCalendarPopup(True)
        self.filtro_data_ate.setMinimumWidth(120)
        self.filtro_data_ate.setDate(QDate.currentDate())
        linha.addWidget(self.filtro_data_ate)

        linha.addSpacing(10)
        btn_filtrar = QPushButton("Filtrar")
        btn_filtrar.setStyleSheet(self._estilo_botao_destaque())
        btn_filtrar.clicked.connect(self._aplicar_filtro_data)
        linha.addWidget(btn_filtrar)

        btn_limpar_filtro = QPushButton("Limpar filtro")
        btn_limpar_filtro.clicked.connect(self._limpar_filtro_data)
        linha.addWidget(btn_limpar_filtro)

        return linha

    def _criar_linha_botoes(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        self.btn_add = QPushButton("+ Adicionar linha")
        self.btn_add.setStyleSheet(self._estilo_botao_destaque())
        self.btn_add.clicked.connect(lambda: self._adicionar_linha())

        self.btn_remover = QPushButton("- Remover linha selecionada")
        self.btn_remover.clicked.connect(self._remover_linha)

        self.btn_recarregar = QPushButton("🔄 Recarregar do Sheets")
        self.btn_recarregar.clicked.connect(self._recarregar_do_sheets)

        self.btn_salvar = QPushButton("💾 Salvar")
        self.btn_salvar.setStyleSheet(self._estilo_botao_destaque())
        self.btn_salvar.clicked.connect(self._salvar)

        linha.addWidget(self.btn_add)
        linha.addWidget(self.btn_remover)
        linha.addWidget(self.btn_recarregar)
        linha.addStretch()
        linha.addWidget(self.btn_salvar)
        return linha

    def _estilo_botao_destaque(self) -> str:
        return (
            f"QPushButton {{ background-color: {self.cor}; color: {self.empresa['cor_texto']}; "
            f"font-weight: bold; padding: 6px 12px; border-radius: 4px; }}"
        )

    def _definir_ocupado(self, ocupado: bool, mensagem: str = ""):
        """Bloqueia os botões (inclusive Voltar) enquanto uma chamada de rede
        está em andamento, pra evitar sair da tela no meio de uma operação."""
        self._operacao_em_andamento = ocupado
        for botao in (self.btn_add, self.btn_remover, self.btn_salvar, self.btn_recarregar, self.btn_voltar):
            botao.setEnabled(not ocupado)
        if mensagem:
            self.status_label.setStyleSheet("color: #d9a441;")
            self.status_label.setText(mensagem)

    def _tentar_voltar(self):
        """Chamado pelo botão "← Voltar". Se existir alguma alteração ainda
        não salva (linha nova preenchida ou edição numa linha já existente),
        pede confirmação antes de sair — evita perder dados por engano."""
        if self._alteracoes_nao_salvas:
            resposta = QMessageBox.question(
                self, "Sair sem salvar",
                "Você tem alterações que ainda não foram salvas. Quer sair mesmo assim?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if resposta != QMessageBox.StandardButton.Yes:
                return
        self.voltar_callback()

    def _adicionar_linha(self, dados: dict = None):
        row = self.tabela.rowCount()
        self.tabela.insertRow(row)
        dados = dados or {}
        self._carregando = True

        item_data = QTableWidgetItem(dados.get("data") or QDate.currentDate().toString("dd/MM/yyyy"))
        item_data.setData(Qt.ItemDataRole.UserRole, dados.get("id"))
        item_qtd = QTableWidgetItem(str(dados.get("quantidade", "")) if dados.get("quantidade") else "")
        item_preco = QTableWidgetItem(str(dados.get("preco_unitario", "")) if dados.get("preco_unitario") else "")
        item_total = QTableWidgetItem(format_moeda(dados.get("preco_total", 0.0)))
        item_total.setFlags(item_total.flags() & ~Qt.ItemFlag.ItemIsEditable)

        for col, item in enumerate([item_data, item_qtd, item_preco, item_total]):
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tabela.setItem(row, col, item)

        self._carregando = False
        return row

    def _popular_tabela(self, linhas: list):
        self._carregando = True
        self.tabela.setRowCount(0)
        self._carregando = False

        if linhas:
            for dados in linhas:
                self._adicionar_linha(dados)
        else:
            for _ in range(ROWS_INICIAIS):
                self._adicionar_linha()

        self._atualizar_indicadores()
        self._alteracoes_nao_salvas = False  # dados recém-carregados: nada para salvar ainda

    def _id_da_linha(self, row: int):
        item = self.tabela.item(row, COL_DATA)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _remover_linha(self):
        if self._operacao_em_andamento:
            return
        row = self.tabela.currentRow()
        if row < 0:
            QMessageBox.information(self, "Remover linha", "Selecione uma linha para remover.")
            return

        id_linha = self._id_da_linha(row)
        if not id_linha:
            self.tabela.removeRow(row)
            self._atualizar_indicadores()
            return

        resposta = QMessageBox.question(
            self, "Remover linha",
            "Essa linha já está salva no Google Sheets. Remover mesmo?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return

        self._definir_ocupado(True, "Removendo do Google Sheets...")
        self._worker = SheetsWorker(sheets_remover, [id_linha])
        self._worker.concluido.connect(lambda ok, msg: self._on_remocao_concluida(ok, msg, row))
        self._worker.start()

    def _on_remocao_concluida(self, sucesso: bool, mensagem, row: int):
        if self._destruida:
            return  # a página já foi fechada/trocada enquanto a rede respondia
        self._definir_ocupado(False)
        if sucesso:
            self.tabela.removeRow(row)
            self._atualizar_indicadores()
            self.status_label.setStyleSheet("color: #2e7d32;")
            self.status_label.setText("Linha removida do Google Sheets.")
        else:
            self.status_label.setStyleSheet("color: #c0392b;")
            self.status_label.setText(f"Falha ao remover: {mensagem}")
            QMessageBox.critical(self, "Erro ao remover", str(mensagem))

    def _on_item_changed(self, item: QTableWidgetItem):
        if self._carregando:
            return
        self._alteracoes_nao_salvas = True
        if item.column() in (COL_QTD, COL_PRECO_UNIT):
            self._recalcular_linha(item.row())
        self._atualizar_indicadores()

    def _recalcular_linha(self, row: int):
        qtd = parse_numero(self._texto_celula(row, COL_QTD))
        preco = parse_numero(self._texto_celula(row, COL_PRECO_UNIT))

        self._carregando = True
        item_total = self.tabela.item(row, COL_TOTAL)
        if item_total is None:
            item_total = QTableWidgetItem()
            item_total.setFlags(item_total.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tabela.setItem(row, COL_TOTAL, item_total)
        item_total.setText(format_moeda(qtd * preco))
        item_total.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._carregando = False

    def _texto_celula(self, row: int, col: int) -> str:
        item = self.tabela.item(row, col)
        return item.text().strip() if item else ""

    def _atualizar_indicadores(self):
        total_geral = 0.0
        registros = []  # (data_ordenacao, data_texto, preco_unitario)

        for row in range(self.tabela.rowCount()):
            if self.tabela.isRowHidden(row):
                continue
            qtd = parse_numero(self._texto_celula(row, COL_QTD))
            preco = parse_numero(self._texto_celula(row, COL_PRECO_UNIT))
            total_geral += qtd * preco
            if preco > 0:
                data_txt = self._texto_celula(row, COL_DATA)
                data_qd = QDate.fromString(data_txt, "dd/MM/yyyy")
                registros.append((data_qd if data_qd.isValid() else QDate(2000, 1, 1), data_txt or "-", preco))

        self.label_total.setText(f"Total do produto: {format_moeda(total_geral)}")

        if not registros:
            self.label_melhor_compra.setText("Melhor compra: -")
            self.label_pior_compra.setText("Pior compra: -")
            self.mini_grafico.set_valores([])
            return

        melhor = min(registros, key=lambda item: item[2])
        pior = max(registros, key=lambda item: item[2])
        self.label_melhor_compra.setText(f"Melhor compra: {format_moeda(melhor[2])} ({melhor[1]})")
        self.label_pior_compra.setText(f"Pior compra: {format_moeda(pior[2])} ({pior[1]})")

        registros_ordenados = sorted(registros, key=lambda item: item[0])
        self.mini_grafico.set_valores([preco for _, _, preco in registros_ordenados])

    def _aplicar_filtro_data(self):
        data_de, data_ate = self.filtro_data_de.date(), self.filtro_data_ate.date()
        if data_de > data_ate:
            QMessageBox.warning(self, "Filtro inválido", "A data 'De' não pode ser depois da data 'Até'.")
            return

        for row in range(self.tabela.rowCount()):
            data_qd = QDate.fromString(self._texto_celula(row, COL_DATA), "dd/MM/yyyy")
            if not data_qd.isValid():
                self.tabela.setRowHidden(row, True)
                continue
            self.tabela.setRowHidden(row, not (data_de <= data_qd <= data_ate))

        self._atualizar_indicadores()
        self.status_label.setStyleSheet("color: #2e7d32;")
        self.status_label.setText(
            f"Filtro aplicado: {data_de.toString('dd/MM/yyyy')} até {data_ate.toString('dd/MM/yyyy')}"
        )

    def _limpar_filtro_data(self):
        for row in range(self.tabela.rowCount()):
            self.tabela.setRowHidden(row, False)
        self.filtro_data_de.setDate(QDate.currentDate())
        self.filtro_data_ate.setDate(QDate.currentDate())
        self._atualizar_indicadores()
        self.status_label.setStyleSheet("color: #2e7d32;")
        self.status_label.setText("Filtro removido.")

    def _salvar(self):
        if self._operacao_em_andamento:
            return

        novas, existentes, linhas_por_id_novo = [], [], {}

        for row in range(self.tabela.rowCount()):
            qtd = parse_numero(self._texto_celula(row, COL_QTD))
            preco = parse_numero(self._texto_celula(row, COL_PRECO_UNIT))
            if qtd <= 0 or preco <= 0:
                continue  # ignora linhas em branco/incompletas

            registro = {
                "data": self._texto_celula(row, COL_DATA),
                "quantidade": qtd,
                "preco_unitario": preco,
                "preco_total": qtd * preco,
            }

            id_linha = self._id_da_linha(row)
            if id_linha:
                registro["id"] = id_linha
                existentes.append(registro)
            else:
                novo_id = gerar_id()
                registro["id"] = novo_id
                registro["empresa"] = self.empresa["nome"]
                registro["produto"] = self.produto
                novas.append(registro)
                linhas_por_id_novo[novo_id] = row

        if not novas and not existentes:
            self.status_label.setStyleSheet("color: #2e7d32;")
            self.status_label.setText("Nada para salvar (preencha quantidade e preço unitário).")
            return

        self._definir_ocupado(True, "Salvando no Google Sheets...")
        self._worker = SheetsWorker(sheets_salvar, novas, existentes)
        self._worker.concluido.connect(lambda ok, msg: self._on_salvamento_concluido(ok, msg, linhas_por_id_novo))
        self._worker.start()

    def _on_salvamento_concluido(self, sucesso: bool, mensagem, linhas_por_id_novo: dict):
        if self._destruida:
            return  # a página já foi fechada/trocada enquanto a rede respondia
        self._definir_ocupado(False)
        if sucesso:
            self._carregando = True
            for novo_id, row in linhas_por_id_novo.items():
                item = self.tabela.item(row, COL_DATA)
                if item:
                    item.setData(Qt.ItemDataRole.UserRole, novo_id)
            self._carregando = False
            self._alteracoes_nao_salvas = False
            self.status_label.setStyleSheet("color: #2e7d32;")
            self.status_label.setText("✓ Salvo no Google Sheets com sucesso.")
        else:
            self.status_label.setStyleSheet("color: #c0392b;")
            self.status_label.setText(f"Falha ao salvar: {mensagem}")
            QMessageBox.critical(self, "Erro ao salvar no Google Sheets", str(mensagem))

    def _recarregar_do_sheets(self):
        if self._operacao_em_andamento:
            return
        self._definir_ocupado(True, "Recarregando do Google Sheets...")
        self._worker = SheetsWorker(sheets_buscar, self.empresa["nome"])
        self._worker.concluido.connect(self._on_recarregamento_concluido)
        self._worker.start()

    def _on_recarregamento_concluido(self, sucesso: bool, resultado):
        if self._destruida:
            return  # a página já foi fechada/trocada enquanto a rede respondia
        self._definir_ocupado(False)
        if not sucesso:
            self.status_label.setStyleSheet("color: #c0392b;")
            self.status_label.setText(f"Falha ao recarregar: {resultado}")
            QMessageBox.critical(self, "Erro ao recarregar", str(resultado))
            return
        linhas_produto = [l for l in resultado if l.get("produto") == self.produto]
        self._popular_tabela(linhas_produto)
        self.status_label.setStyleSheet("color: #2e7d32;")
        self.status_label.setText("Recarregado do Google Sheets.")


# --------------------------------------------------------------------------- #
# Página 2: lista de produtos de uma empresa
# --------------------------------------------------------------------------- #

class ProductListPage(QWidget):
    COL_PRODUTO, COL_ULTIMA_DATA, COL_ULTIMO_VALOR, COL_ABRIR = range(4)

    def __init__(self, empresa: dict, abrir_produto_callback, voltar_callback):
        super().__init__()
        self.empresa = empresa
        self.cor = empresa["cor"]
        self.abrir_produto_callback = abrir_produto_callback
        self.voltar_callback = voltar_callback

        self._linhas_por_produto = {}   # produto -> [linhas da planilha]
        self._produtos_pendentes = []   # produtos criados nesta sessão, sem nenhuma compra salva
        self._operacao_em_andamento = False
        self._worker = None
        self._ordem_crescente = True    # True = A-Z, False = Z-A
        self._texto_pesquisa = ""
        self._geracao_carregamento = 0

        self._montar_ui()
        self.recarregar()

    def _montar_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        linha_titulo = QHBoxLayout()
        btn_voltar = QPushButton("← Voltar")
        btn_voltar.clicked.connect(self.voltar_callback)

        titulo = QLabel(self.empresa["nome"])
        fonte_titulo = QFont()
        fonte_titulo.setPointSize(16)
        fonte_titulo.setBold(True)
        titulo.setFont(fonte_titulo)
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        titulo.setStyleSheet(f"color: {self.cor};")

        bloco_direito_widget = QWidget()
        bloco_direito = QHBoxLayout(bloco_direito_widget)
        bloco_direito.setContentsMargins(0, 0, 0, 0)
        bloco_direito.setSpacing(8)

        self.btn_ordenar = QPushButton("⬆ A-Z")
        self.btn_ordenar.setToolTip("Alternar ordem alfabética")
        self.btn_ordenar.clicked.connect(self._alternar_ordem)
        bloco_direito.addWidget(self.btn_ordenar)

        self.btn_pesquisar = QPushButton("🔍 Pesquisar")
        self.btn_pesquisar.setCheckable(True)
        self.btn_pesquisar.clicked.connect(self._alternar_pesquisa)
        bloco_direito.addWidget(self.btn_pesquisar)

        linha_titulo.addWidget(btn_voltar)
        linha_titulo.addWidget(titulo, stretch=1)
        linha_titulo.addWidget(bloco_direito_widget)
        layout.addLayout(linha_titulo)

        linha_pesquisa = QHBoxLayout()
        linha_pesquisa.addStretch()
        self.campo_pesquisa = QLineEdit()
        self.campo_pesquisa.setPlaceholderText("Pesquisar produto pelo nome...")
        self.campo_pesquisa.setMaximumWidth(320)
        self.campo_pesquisa.textChanged.connect(self._on_texto_pesquisa_mudou)
        self.campo_pesquisa.setVisible(False)
        linha_pesquisa.addWidget(self.campo_pesquisa)
        layout.addLayout(linha_pesquisa)

        self.dica_label = QLabel("Carregando produtos do Google Sheets...")
        self.dica_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.dica_label.setStyleSheet("color: #999;")
        layout.addWidget(self.dica_label)

        self.tabela = QTableWidget(0, 4)
        self.tabela.setHorizontalHeaderLabels(["Produto", "Última compra", "Valor da última compra", ""])
        header = self.tabela.horizontalHeader()
        header.setSectionResizeMode(self.COL_PRODUTO, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(self.COL_ULTIMA_DATA, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.COL_ULTIMO_VALOR, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.COL_ABRIR, QHeaderView.ResizeMode.ResizeToContents)
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabela.setAlternatingRowColors(True)
        self.tabela.horizontalHeader().setStyleSheet(
            f"QHeaderView::section {{ background-color: {self.cor}; color: {self.empresa['cor_texto']}; "
            f"padding: 6px; font-weight: bold; }}"
        )
        self.tabela.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.tabela)

        botoes = QHBoxLayout()
        self.btn_add = QPushButton("+ Adicionar novo item")
        self.btn_add.setStyleSheet(self._estilo_botao_destaque())
        self.btn_add.clicked.connect(self._adicionar_produto)

        self.btn_remover = QPushButton("- Remover item selecionado")
        self.btn_remover.clicked.connect(self._remover_produto)

        self.btn_recarregar = QPushButton("🔄 Recarregar do Sheets")
        self.btn_recarregar.clicked.connect(self.recarregar)

        botoes.addWidget(self.btn_add)
        botoes.addWidget(self.btn_remover)
        botoes.addWidget(self.btn_recarregar)
        botoes.addStretch()
        layout.addLayout(botoes)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #2e7d32;")
        layout.addWidget(self.status_label)

    def _estilo_botao_destaque(self) -> str:
        return (
            f"QPushButton {{ background-color: {self.cor}; color: {self.empresa['cor_texto']}; "
            f"font-weight: bold; padding: 6px 12px; border-radius: 4px; }}"
        )

    def _definir_ocupado(self, ocupado: bool):
        self._operacao_em_andamento = ocupado
        for botao in (self.btn_add, self.btn_remover, self.btn_recarregar):
            botao.setEnabled(not ocupado)

    def recarregar(self):
        if self._operacao_em_andamento:
            return

        # mostra o cache local na hora, sem esperar a rede
        dados_cache = cache_carregar(self.empresa["nome"])
        if dados_cache:
            self._linhas_por_produto = {}
            for linha in dados_cache:
                self._linhas_por_produto.setdefault(linha["produto"], []).append(linha)
            self._produtos_pendentes = [p for p in self._produtos_pendentes if p not in self._linhas_por_produto]
            self._reconstruir_tabela()
            self.dica_label.setStyleSheet("color: #999;")
            self.dica_label.setText("Mostrando dados salvos localmente — atualizando com o Google Sheets...")
        else:
            self.dica_label.setStyleSheet("color: #999;")
            self.dica_label.setText("Carregando produtos do Google Sheets...")

        # busca a versão atual em paralelo, pra confirmar/atualizar
        self._definir_ocupado(True)

        self._geracao_carregamento = getattr(self, "_geracao_carregamento", 0) + 1
        geracao_desta_chamada = self._geracao_carregamento

        self._worker = SheetsWorker(sheets_buscar, self.empresa["nome"])
        self._worker.concluido.connect(self._on_carregamento_concluido)
        self._worker.start()

        # watchdog: sai do "Carregando..." se não vier resposta em 45s
        QTimer.singleShot(45000, lambda: self._verificar_timeout_carregamento(geracao_desta_chamada))

    def _verificar_timeout_carregamento(self, geracao_esperada: int):
        if not self._operacao_em_andamento or geracao_esperada != self._geracao_carregamento:
            return  # já respondeu, ou uma nova busca começou nesse meio-tempo
        self._definir_ocupado(False)
        self.dica_label.setStyleSheet("color: #c0392b;")
        self.dica_label.setText(
            "Demorou demais e não veio resposta do Google Sheets (mais de 45s). "
            "Confira a URL configurada e se o Apps Script está implantado com acesso "
            "\"Qualquer pessoa\". Clique em \"🔄 Recarregar do Sheets\" pra tentar de novo."
        )

    def _on_carregamento_concluido(self, sucesso: bool, resultado):
        if not self._operacao_em_andamento:
            return  # o watchdog já assumiu o controle (resposta chegou tarde demais)
        self._definir_ocupado(False)
        if not sucesso:
            # mantém o cache visível e só avisa que a atualização falhou
            if self._linhas_por_produto:
                self.dica_label.setStyleSheet("color: #c0392b;")
                self.dica_label.setText(f"Não consegui atualizar do Sheets agora: {resultado}")
            else:
                self.dica_label.setText(f"Erro ao carregar do Google Sheets: {resultado}")
                self.dica_label.setStyleSheet("color: #c0392b;")
                QMessageBox.critical(self, "Erro ao carregar do Google Sheets", str(resultado))
            return

        self.dica_label.setStyleSheet("color: #999;")
        self.dica_label.setText("Clique em \"Abrir lista\" (ou dê duplo clique) para ver as compras do produto.")

        self._linhas_por_produto = {}
        for linha in resultado:
            self._linhas_por_produto.setdefault(linha["produto"], []).append(linha)

        # produtos pendentes que já vieram na busca deixam de ser "pendentes"
        self._produtos_pendentes = [
            p for p in self._produtos_pendentes if p not in self._linhas_por_produto
        ]

        cache_salvar(self.empresa["nome"], resultado)
        self._reconstruir_tabela()

    def _reconstruir_tabela(self):
        self.tabela.setRowCount(0)
        nomes_produtos = list(self._linhas_por_produto.keys()) + self._produtos_pendentes
        nomes_produtos = sorted(nomes_produtos, key=lambda n: n.lower(), reverse=not self._ordem_crescente)

        if self._texto_pesquisa:
            termo = self._texto_pesquisa.lower()
            nomes_produtos = [n for n in nomes_produtos if termo in n.lower()]

        for nome_produto in nomes_produtos:
            self._inserir_linha_produto(nome_produto)

    def _alternar_ordem(self):
        self._ordem_crescente = not self._ordem_crescente
        self.btn_ordenar.setText("⬆ A-Z" if self._ordem_crescente else "⬇ Z-A")
        self._reconstruir_tabela()

    def _alternar_pesquisa(self):
        mostrar = self.btn_pesquisar.isChecked()
        self.campo_pesquisa.setVisible(mostrar)
        if mostrar:
            self.campo_pesquisa.setFocus()
        else:
            self.campo_pesquisa.clear()

    def _on_texto_pesquisa_mudou(self, texto: str):
        self._texto_pesquisa = texto.strip()
        self._reconstruir_tabela()

    def _inserir_linha_produto(self, nome_produto: str):
        row = self.tabela.rowCount()
        self.tabela.insertRow(row)

        ultima = obter_ultima_compra(self._linhas_por_produto.get(nome_produto, []))
        data_txt = (ultima.get("data") if ultima else None) or "-"
        valor_txt = format_moeda((ultima.get("quantidade", 0) * ultima.get("preco_unitario", 0)) if ultima else 0)

        item_nome = QTableWidgetItem(nome_produto)
        item_nome.setFlags(item_nome.flags() & ~Qt.ItemFlag.ItemIsEditable)
        item_nome.setToolTip(nome_produto)  # nomes longos ficam visíveis ao passar o mouse
        item_data = QTableWidgetItem(data_txt)
        item_data.setFlags(item_data.flags() & ~Qt.ItemFlag.ItemIsEditable)
        item_data.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item_valor = QTableWidgetItem(valor_txt)
        item_valor.setFlags(item_valor.flags() & ~Qt.ItemFlag.ItemIsEditable)
        item_valor.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        self.tabela.setItem(row, self.COL_PRODUTO, item_nome)
        self.tabela.setItem(row, self.COL_ULTIMA_DATA, item_data)
        self.tabela.setItem(row, self.COL_ULTIMO_VALOR, item_valor)

        btn_abrir = QPushButton("Abrir lista →")
        btn_abrir.setStyleSheet(self._estilo_botao_destaque())
        btn_abrir.clicked.connect(lambda checked, n=nome_produto: self._abrir_produto(n))
        self.tabela.setCellWidget(row, self.COL_ABRIR, btn_abrir)

    def _on_item_double_clicked(self, item: QTableWidgetItem):
        nome_produto = self.tabela.item(item.row(), self.COL_PRODUTO).text()
        self._abrir_produto(nome_produto)

    def _abrir_produto(self, nome_produto: str):
        linhas = self._linhas_por_produto.get(nome_produto, [])
        self.abrir_produto_callback(self.empresa, nome_produto, linhas)

    def _adicionar_produto(self):
        nome, ok = QInputDialog.getText(self, "Novo item", "Nome do novo produto:")
        nome = (nome or "").strip()
        if not ok or not nome:
            return
        if nome in self._linhas_por_produto or nome in self._produtos_pendentes:
            QMessageBox.information(self, "Item já existe", "Já existe um produto com esse nome.")
            return

        self._produtos_pendentes.append(nome)
        self._reconstruir_tabela()
        self.status_label.setStyleSheet("color: #2e7d32;")
        self.status_label.setText(
            f"'{nome}' criado. Salve pelo menos uma compra pra ele aparecer no Sheets."
        )
        self._abrir_produto(nome)  # abre na hora, sem precisar procurar o item recém-criado na lista

    def _remover_produto(self):
        if self._operacao_em_andamento:
            return
        row = self.tabela.currentRow()
        if row < 0:
            QMessageBox.information(self, "Remover item", "Selecione um produto para remover.")
            return

        nome_produto = self.tabela.item(row, self.COL_PRODUTO).text()
        ids = [l["id"] for l in self._linhas_por_produto.get(nome_produto, []) if l.get("id")]

        resposta = QMessageBox.question(
            self, "Remover item",
            f"Tem certeza que quer remover '{nome_produto}' e todos os registros dele"
            + (" do Google Sheets" if ids else "") + "?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return

        if not ids:
            # produto pendente, nunca chegou a ter compra salva no Sheets
            self._produtos_pendentes = [p for p in self._produtos_pendentes if p != nome_produto]
            self._reconstruir_tabela()
            return

        self._definir_ocupado(True)
        self.status_label.setStyleSheet("color: #d9a441;")
        self.status_label.setText("Removendo do Google Sheets...")
        self._worker = SheetsWorker(sheets_remover, ids)
        self._worker.concluido.connect(lambda ok, msg: self._on_remocao_produto_concluida(ok, msg, nome_produto))
        self._worker.start()

    def _on_remocao_produto_concluida(self, sucesso: bool, mensagem, nome_produto: str):
        self._definir_ocupado(False)
        if sucesso:
            self._linhas_por_produto.pop(nome_produto, None)
            self._reconstruir_tabela()
            self.status_label.setStyleSheet("color: #2e7d32;")
            self.status_label.setText(f"'{nome_produto}' removido do Google Sheets.")
        else:
            self.status_label.setStyleSheet("color: #c0392b;")
            self.status_label.setText(f"Falha ao remover: {mensagem}")
            QMessageBox.critical(self, "Erro ao remover do Google Sheets", str(mensagem))


# --------------------------------------------------------------------------- #
# Página 1: seleção de empresa
# --------------------------------------------------------------------------- #

class CompanySelectPage(QWidget):
    def __init__(self, escolher_callback):
        super().__init__()
        layout_externo = QVBoxLayout(self)
        layout_externo.setContentsMargins(60, 60, 60, 60)
        layout_externo.addStretch()

        titulo = QLabel("Selecione a empresa")
        fonte = QFont()
        fonte.setPointSize(20)
        fonte.setBold(True)
        titulo.setFont(fonte)
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout_externo.addWidget(titulo)
        layout_externo.addSpacing(30)

        if not GOOGLE_SHEETS_WEBHOOK_URL:
            aviso = QLabel("⚠ GOOGLE_SHEETS_WEBHOOK_URL não configurada — configure no topo do arquivo .py")
            aviso.setAlignment(Qt.AlignmentFlag.AlignCenter)
            aviso.setStyleSheet("color: #e74c3c; font-weight: bold;")
            layout_externo.addWidget(aviso)
            layout_externo.addSpacing(10)

        linha_cards = QHBoxLayout()
        linha_cards.addStretch()

        for empresa in COMPANIES:
            card = QVBoxLayout()
            card.setSpacing(14)

            avatar = criar_avatar_circular(empresa, tamanho=130)
            card.addWidget(avatar, alignment=Qt.AlignmentFlag.AlignHCenter)

            btn = QPushButton(empresa["nome"])
            btn.setFixedWidth(220)
            btn.setMinimumHeight(50)
            fonte_btn = QFont()
            fonte_btn.setPointSize(12)
            fonte_btn.setBold(True)
            btn.setFont(fonte_btn)
            btn.setStyleSheet(
                f"QPushButton {{ background-color: {empresa['cor']}; color: {empresa['cor_texto']}; "
                f"border-radius: 6px; padding: 8px; }}"
            )
            btn.clicked.connect(lambda checked, e=empresa: escolher_callback(e))
            card.addWidget(btn, alignment=Qt.AlignmentFlag.AlignHCenter)

            container = QWidget()
            container.setLayout(card)
            linha_cards.addWidget(container)
            linha_cards.addSpacing(40)

        linha_cards.addStretch()
        layout_externo.addLayout(linha_cards)
        layout_externo.addStretch()


# --------------------------------------------------------------------------- #
# Janela principal
# --------------------------------------------------------------------------- #

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Controle de Empresas")
        self.resize(1100, 680)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.pagina_selecao = CompanySelectPage(self.abrir_empresa)
        self.stack.addWidget(self.pagina_selecao)

        self._paginas_produtos = {}    # nome_empresa -> ProductListPage
        self._pagina_entradas_atual = None

    def abrir_empresa(self, empresa: dict):
        nome_empresa = empresa["nome"]
        if nome_empresa not in self._paginas_produtos:
            pagina = ProductListPage(
                empresa,
                abrir_produto_callback=self.abrir_produto,
                voltar_callback=self.voltar_para_selecao,
            )
            self._paginas_produtos[nome_empresa] = pagina
            self.stack.addWidget(pagina)
        else:
            self._paginas_produtos[nome_empresa].recarregar()

        self.stack.setCurrentWidget(self._paginas_produtos[nome_empresa])

    def abrir_produto(self, empresa: dict, produto: str, linhas: list):
        # sempre cria uma página nova, com dados frescos vindos do Sheets
        pagina = ProductEntriesPage(
            empresa, produto, linhas,
            voltar_callback=lambda: self.voltar_para_lista_produtos(empresa),
        )
        if self._pagina_entradas_atual is not None:
            # avisa a página antiga ANTES de destruí-la, pra um worker de
            # rede atrasado saber que deve ignorar o resultado
            self._pagina_entradas_atual.marcar_destruida()
            self.stack.removeWidget(self._pagina_entradas_atual)
            self._pagina_entradas_atual.deleteLater()

        self._pagina_entradas_atual = pagina
        self.stack.addWidget(pagina)
        self.stack.setCurrentWidget(pagina)

    def voltar_para_lista_produtos(self, empresa: dict):
        nome_empresa = empresa["nome"]
        self.stack.setCurrentWidget(self._paginas_produtos[nome_empresa])
        self._paginas_produtos[nome_empresa].recarregar()

    def voltar_para_selecao(self):
        self.stack.setCurrentWidget(self.pagina_selecao)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    janela = MainWindow()
    janela.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()