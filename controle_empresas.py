import sys
import os
import re
import json
import uuid
import base64
import shutil
import ipaddress
import unicodedata
import urllib.request
import urllib.error
import urllib.parse
from html import unescape
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QStackedWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QAbstractItemView, QDateEdit, QInputDialog, QLineEdit,
    QAbstractItemDelegate, QFileDialog, QComboBox, QScrollArea,
    QDialog, QFormLayout, QDialogButtonBox
)
from PyQt6.QtCore import Qt, QDate, QSize, QRectF, QPointF, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor, QPixmap, QPainter, QPainterPath, QPen, QLinearGradient, QPalette

# --------------------------------------------------------------------------- #
# Configuração e caminhos
# --------------------------------------------------------------------------- #
# O app roda tanto "solto" (python controle_empresas.py) quanto empacotado com
# o PyInstaller (um .exe no Windows). Isso muda onde os arquivos ficam:
#   - assets (logos): acompanham o app. Empacotado, ficam numa pasta temporária
#     (sys._MEIPASS); soltos, ao lado do .py. `resource_path()` acha os dois.
#   - config e cache: NUNCA ao lado do executável (no Windows a pasta do
#     programa costuma ser somente-leitura). Sempre numa pasta gravável por
#     usuário do sistema: %APPDATA%/%LOCALAPPDATA% no Windows, ~/.config e
#     ~/.cache no Linux.

APP_NOME = "controle_empresas"


def _empacotado() -> bool:
    """True quando rodando como .exe/.bin gerado pelo PyInstaller."""
    return getattr(sys, "frozen", False)


def resource_path(*partes: str) -> str:
    """Caminho de um recurso somente-leitura que acompanha o app
    (ex: resource_path('assets', 'granola_pura.png'))."""
    if _empacotado():
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, *partes)


def _dir_dados_usuario(tipo: str) -> str:
    """Pasta gravável por-usuário pra 'config' ou 'cache', por SO."""
    if sys.platform.startswith("win"):
        raiz = os.environ.get("LOCALAPPDATA" if tipo == "cache" else "APPDATA")
        raiz = raiz or os.path.expanduser("~")
    elif tipo == "cache":
        raiz = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    else:
        raiz = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(raiz, APP_NOME)


ASSETS_DIR = resource_path("assets")
CONFIG_DIR = _dir_dados_usuario("config")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
CACHE_DIR = _dir_dados_usuario("cache")

# A URL do Web App do Apps Script (termina em "/exec") NÃO fica no código: quem
# tem essa URL lê e escreve na planilha inteira, então ela é um segredo e não
# pode entrar no git. Ela vem da variável de ambiente GOOGLE_SHEETS_WEBHOOK_URL
# ou do config.json (ver sheets_webhook_url()); o diálogo "⚙️ Configurar" grava.
# A chave da API do Gemini segue o mesmo caminho (GEMINI_API_KEY / config.json).

# Modelo padrão pra ler as notas. Se um dia ele for desligado, a primeira
# leitura que falhar com 404 dispara _ia_descobrir_modelo(), que acha um
# Flash válido na conta e grava no config.json — o usuário nem percebe.
MODELO_IA_PADRAO = "gemini-2.5-flash"

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

COLUNAS_ENTRADAS = ["Nome", "Data", "Quantidade", "Preço Unitário", "Preço Total"]
COL_NOME, COL_DATA, COL_QTD, COL_PRECO_UNIT, COL_TOTAL = range(5)

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


# --------------------------------------------------------------------------- #
# Configuração pessoal em disco (chave da API de IA, modelo escolhido)
# --------------------------------------------------------------------------- #

def carregar_config() -> dict:
    """Lê o config.json (ver CONFIG_PATH). Devolve {} se não existir ou estiver
    corrompido — o app abre, mas não carrega nenhuma empresa até a URL da
    planilha ser configurada. Pode ser chamada de várias threads ao mesmo
    tempo; `salvar_config` grava de forma atômica pra a leitura nunca ver o
    arquivo pela metade."""
    try:
        with open(CONFIG_PATH, encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
        return dados if isinstance(dados, dict) else {}
    except (OSError, ValueError):
        return {}


def salvar_config(dados: dict) -> None:
    """Grava a configuração como texto puro num arquivo só do dono (permissão
    600 no POSIX) — a URL da planilha e a chave da API são segredos e não
    devem ficar legíveis pra outros usuários da máquina. A escrita é atômica
    (arquivo temporário + os.replace): um leitor concorrente vê a versão
    antiga inteira ou a nova inteira, nunca um JSON truncado."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    temporario = CONFIG_PATH + ".tmp"
    # abre já com 0600 (sem a janela entre criar com o umask e o chmod)
    fd = os.open(temporario, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2)
    os.replace(temporario, CONFIG_PATH)
    try:
        os.chmod(CONFIG_PATH, 0o600)  # caso o arquivo destino já existisse com outra permissão
    except OSError:
        pass  # sistemas de arquivos sem permissões POSIX (ex: pen drive) — segue sem


def sheets_webhook_url() -> str:
    """A URL do Web App do Apps Script, da variável de ambiente
    GOOGLE_SHEETS_WEBHOOK_URL (tem prioridade) ou do config.json. É um segredo:
    quem tem a URL lê e escreve na planilha inteira — por isso não fica no
    código. Devolve "" se ainda não foi configurada."""
    return (os.environ.get("GOOGLE_SHEETS_WEBHOOK_URL")
            or carregar_config().get("sheets_webhook_url") or "").strip()


def ia_api_key() -> str:
    """A chave da API do Gemini, da variável de ambiente GEMINI_API_KEY
    (tem prioridade) ou do config.json."""
    return (os.environ.get("GEMINI_API_KEY") or carregar_config().get("gemini_api_key") or "").strip()


def ia_modelo() -> str:
    return (carregar_config().get("gemini_modelo") or "").strip() or MODELO_IA_PADRAO


# --------------------------------------------------------------------------- #
# Importar compra a partir de foto de nota fiscal (IA de visão — Google Gemini)
# --------------------------------------------------------------------------- #
# A foto é enviada direto pra API do Gemini, que devolve os itens já
# estruturados (nome, data, quantidade, preço unitário). Não há OCR local:
# o modelo lê a imagem inteira, entende o layout da nota e separa os itens
# de linhas de total/imposto/estabelecimento sozinho. A tela de conferência
# (ImportarNotaFiscalPage) continua obrigatória — nada vai pro Sheets sem o
# usuário revisar.

class ErroIA(Exception):
    """Falha ao ler a nota com a IA: chave ausente/recusada, rede fora,
    modelo inexistente, limite de uso atingido ou resposta inesperada."""


_IA_URL_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

_IA_LIMITE_IMAGEM = 18 * 1024 * 1024  # a API aceita ~20 MB por requisição, contando o base64

_IA_REGRAS_ITENS = (
    "Extraia CADA produto comprado. Para cada item devolva:\n"
    "- nome: a descrição do produto como aparece na nota (marca/embalagem), sem códigos numéricos;\n"
    "- data: a data da compra no formato dd/mm/aaaa (use a data da nota; se não houver, deixe vazio);\n"
    "- quantidade: número decimal com ponto (se a nota não mostrar, use 1);\n"
    "- preco_unitario: o preço de UMA unidade, em reais, como número decimal com ponto (ex: 12.90). "
    "Se a nota só mostrar o total do item, divida o total pela quantidade.\n"
    "Ignore linhas de total, subtotal, troco, desconto, acréscimo, tributos/impostos, "
    "forma de pagamento e os dados do estabelecimento e do consumidor. "
)

_IA_PROMPT_NOTA = (
    "Você recebe a foto de uma nota fiscal, cupom fiscal ou comprovante de compra brasileiro. "
    + _IA_REGRAS_ITENS +
    "Se a imagem não for uma nota/cupom legível, devolva a lista de itens vazia."
)

_IA_PROMPT_LINK = (
    "O texto abaixo foi extraído da página oficial de consulta de uma nota fiscal eletrônica "
    "brasileira (NFC-e / NF-e) no site da SEFAZ. "
    + _IA_REGRAS_ITENS +
    "Se o texto não contiver a lista de produtos de uma nota fiscal, devolva a lista de itens vazia.\n\n"
    "TEXTO DA PÁGINA:\n"
)

_IA_SCHEMA_NOTA = {
    "type": "object",
    "properties": {
        "itens": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "nome": {"type": "string"},
                    "data": {"type": "string"},
                    "quantidade": {"type": "number"},
                    "preco_unitario": {"type": "number"},
                },
                "required": ["nome", "quantidade", "preco_unitario"],
            },
        }
    },
    "required": ["itens"],
}

_IA_MIMES = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".bmp": "image/bmp", ".heic": "image/heic", ".heif": "image/heif",
}


def _ia_requisitar(url: str, dados: bytes = None, timeout: int = 90, api_key: str = None) -> dict:
    """POST/GET na API do Gemini com tratamento de erro traduzido pro
    usuário (ErroIA). Usado tanto pra ler a nota quanto pra listar modelos.
    `api_key` permite testar uma chave ainda não salva (diálogo de config)."""
    cabecalhos = {"x-goog-api-key": api_key or ia_api_key()}
    if dados is not None:
        cabecalhos["Content-Type"] = "application/json"
    requisicao = urllib.request.Request(url, data=dados, headers=cabecalhos,
                                        method="POST" if dados is not None else "GET")
    try:
        with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:
            return json.loads(resposta.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detalhe = ""
        try:
            detalhe = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")
        except (ValueError, OSError):
            pass
        if e.code in (401, 403) or (e.code == 400 and "api key" in detalhe.lower()):
            raise ErroIA(f"A chave da API foi recusada pelo Google (HTTP {e.code}). "
                         f"Confira em '⚙️ Configurar'. {detalhe}".strip()) from e
        if e.code == 404:
            raise ErroIA(f"O modelo '{ia_modelo()}' não existe ou não está liberado pra sua chave. "
                         f"Escolha outro em '⚙️ Configurar'. {detalhe}".strip()) from e
        if e.code == 429:
            raise ErroIA("Limite de uso da API do Gemini atingido. Espere alguns minutos e tente de novo.") from e
        raise ErroIA(f"O Google respondeu com erro HTTP {e.code}. {detalhe}".strip()) from e
    except urllib.error.URLError as e:
        raise ErroIA(f"Não foi possível conectar à API do Gemini: {e.reason}") from e
    except (OSError, ValueError) as e:
        raise ErroIA(f"Falha ao falar com a API do Gemini: {e}") from e


def ler_nota_fiscal_ia(caminho_imagem: str) -> list:
    """Envia a foto pra API do Gemini e devolve a lista de itens reconhecidos
    (dicts com nome/data/quantidade/preco_unitario). Levanta ErroIA em
    qualquer falha. Função pura (sem Qt) — roda dentro de um SheetsWorker."""
    if not ia_api_key():
        raise ErroIA("Configure a chave da API do Google Gemini em '⚙️ Configurar' antes de importar uma nota.")

    try:
        with open(caminho_imagem, "rb") as arquivo:
            imagem_bytes = arquivo.read()
    except OSError as e:
        raise ErroIA(f"Não consegui abrir a imagem: {e}") from e

    if not imagem_bytes:
        raise ErroIA("O arquivo de imagem está vazio.")
    if len(imagem_bytes) > _IA_LIMITE_IMAGEM:
        raise ErroIA("A imagem é grande demais (acima de ~18 MB). Tire a foto numa resolução menor.")

    mime = _IA_MIMES.get(os.path.splitext(caminho_imagem)[1].lower(), "image/jpeg")
    return _ia_gerar_itens([
        {"inline_data": {"mime_type": mime, "data": base64.b64encode(imagem_bytes).decode("ascii")}},
        {"text": _IA_PROMPT_NOTA},
    ])


def _recusar_host_interno(url: str) -> None:
    """Levanta ErroIA se a URL aponta pra localhost ou pra um IP de rede
    interna (loopback, link-local, privado). O link da nota é digitado pelo
    usuário e vai pra um fetch do lado dele; isso evita que um link colado por
    engano (ou de má-fé) faça o app sondar a rede local — o texto da resposta
    ainda seria mandado pro Gemini."""
    host = (urllib.parse.urlparse(url).hostname or "").strip("[]").lower()
    if not host or host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        raise ErroIA("Esse endereço não parece ser o de uma nota fiscal da SEFAZ.")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return  # é um nome de domínio comum — segue
    if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved or ip.is_multicast:
        raise ErroIA("Esse endereço aponta pra rede interna e não pode ser aberto pelo app.")


def ler_nota_fiscal_link(url: str) -> list:
    """Baixa a página oficial de consulta de uma NFC-e (o link do QR code) e
    manda o texto pra IA extrair os itens. Dados oficiais e completos —
    melhor que ler a foto. Levanta ErroIA em qualquer falha; função pura."""
    if not ia_api_key():
        raise ErroIA("Configure a chave da API do Google Gemini em '⚙️ Configurar' antes de importar uma nota.")

    url = (url or "").strip()
    if not re.match(r"https?://", url, re.IGNORECASE):
        raise ErroIA("Cole o link completo do QR code da nota (deve começar com http:// ou https://).")
    _recusar_host_interno(url)

    try:
        requisicao = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml",
        })
        with urllib.request.urlopen(requisicao, timeout=40) as resposta:
            bruto = resposta.read(4 * 1024 * 1024)  # NFC-e é pequena; corta em 4 MB por segurança
            charset = resposta.headers.get_content_charset() or "utf-8"
    except urllib.error.HTTPError as e:
        raise ErroIA(f"A página da nota respondeu com erro HTTP {e.code}. Confira se o link está completo e correto.") from e
    except (urllib.error.URLError, OSError) as e:
        motivo = getattr(e, "reason", e)
        raise ErroIA(f"Não consegui abrir o link da nota: {motivo}") from e

    texto = _texto_de_html(bruto.decode(charset, errors="replace"))
    if len(texto) < 40:
        raise ErroIA("A página do link veio vazia. O link pode ter expirado — abra o QR code de novo e copie o endereço atual.")

    # alguns portais da SEFAZ (SC, por exemplo) protegem a consulta com um
    # desafio de segurança/CAPTCHA em JavaScript — um fetch simples só vê a
    # tela do desafio, nunca a nota. Detecta isso e orienta a usar a foto.
    if len(texto) < 3000 and re.search(
        r"valida[çc][ãa]o de seguran[çc]a|verifica[çc][ãa]o para prosseguimento|captcha|"
        r"n[ãa]o sou um rob[ôo]|habilite o javascript|enable javascript",
        texto, re.IGNORECASE,
    ):
        raise ErroIA(
            "O site da SEFAZ desse estado exige uma verificação de segurança (CAPTCHA) que "
            "o app não consegue passar. Use o botão '📷 Importar nota fiscal' com uma foto da nota."
        )

    if len(texto) > 60000:
        texto = texto[:60000]

    return _ia_gerar_itens([{"text": _IA_PROMPT_LINK + texto}])


def _texto_de_html(html: str) -> str:
    """Tira scripts, estilos e tags de um HTML, deixando só o texto visível —
    o suficiente pra IA achar a tabela de itens da nota sem gastar tokens à
    toa com marcação."""
    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?s)<[^>]+>", " ", html)
    html = unescape(html).replace("\xa0", " ")
    html = re.sub(r"[ \t\r\f\v]+", " ", html)
    return re.sub(r"\n[ \n]*\n+", "\n", html).strip()


def _ia_gerar_itens(parts: list) -> list:
    """Manda os `parts` (imagem+texto, ou só texto) pro modelo e devolve a
    lista de itens. Se o modelo configurado sumiu (404), acha outro Flash
    válido, grava no config e tenta de novo — uma vez só."""
    corpo = json.dumps({
        "contents": [{"parts": parts}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": _IA_SCHEMA_NOTA,
            "temperature": 0,
        },
    }).encode("utf-8")

    try:
        dados = _ia_requisitar(f"{_IA_URL_BASE}/{ia_modelo()}:generateContent", dados=corpo)
    except ErroIA as erro_modelo:
        # só troca de modelo se o erro foi especificamente "modelo não existe /
        # não liberado" (404). Rede fora, limite de uso (429) ou falha do
        # servidor não são problema de modelo — e _ia_descobrir_modelo()
        # sobrescreveria a escolha do usuário no config.json à toa.
        if "não existe" not in str(erro_modelo):
            raise
        modelo_novo = _ia_descobrir_modelo()
        if not modelo_novo:
            raise
        dados = _ia_requisitar(f"{_IA_URL_BASE}/{modelo_novo}:generateContent", dados=corpo)

    return _ia_itens_da_resposta(dados)


def _ia_descobrir_modelo() -> str:
    """Escolhe automaticamente um modelo Flash válido na conta e grava no
    config.json — chamado quando o modelo atual dá 404 (foi desligado ou o
    padrão embutido ficou velho). Devolve "" se a listagem também falhar."""
    try:
        nomes = listar_modelos_ia()
    except ErroIA:
        return ""
    escolhido = next(
        (n for n in nomes if "flash" in n and "lite" not in n and "image" not in n and "thinking" not in n),
        next((n for n in nomes if "flash" in n), nomes[0] if nomes else ""),
    )
    if escolhido:
        config = carregar_config()
        config["gemini_modelo"] = escolhido
        try:
            salvar_config(config)
        except OSError:
            pass
    return escolhido


def _ia_itens_da_resposta(dados: dict) -> list:
    candidatos = dados.get("candidates") or []
    if not candidatos:
        motivo = (dados.get("promptFeedback") or {}).get("blockReason")
        raise ErroIA("A IA não retornou nenhum resultado"
                     + (f" (conteúdo bloqueado: {motivo})." if motivo else "."))

    partes = (candidatos[0].get("content") or {}).get("parts") or []
    texto = "".join(parte.get("text", "") for parte in partes).strip()
    if not texto:
        if candidatos[0].get("finishReason") == "MAX_TOKENS":
            raise ErroIA("A nota tem itens demais pra uma leitura só. Fotografe em partes.")
        raise ErroIA("A IA respondeu em branco. Tente uma foto mais nítida.")

    try:
        conteudo = json.loads(texto)
    except ValueError as e:
        raise ErroIA(f"A IA não devolveu um JSON válido. Início da resposta: {texto[:200]}") from e

    brutos = conteudo.get("itens") if isinstance(conteudo, dict) else conteudo
    itens = []
    for bruto in brutos or []:
        if not isinstance(bruto, dict):
            continue
        nome = str(bruto.get("nome", "")).strip()
        if not nome:
            continue
        itens.append({
            "nome": _nome_apresentavel(nome),
            "data": _ia_normalizar_data(str(bruto.get("data", "")).strip()),
            "quantidade": _ia_para_numero(bruto.get("quantidade"), 1),
            "preco_unitario": _ia_para_numero(bruto.get("preco_unitario"), 0),
        })
    return _consolidar_itens_iguais(itens)


def _consolidar_itens_iguais(itens: list) -> list:
    """Junta, numa linha só, itens da MESMA nota com o mesmo nome, o mesmo
    preço unitário e a mesma data — somando a quantidade. Serve pra produtos
    vendidos por peso (verduras, carnes): a nota lista uma linha por pesagem
    ('4 brócolis, 5 repolhos'), mas como o preço do quilo é o mesmo em todas,
    o que interessa é uma linha com o peso total."""
    agrupados, ordem = {}, []
    for item in itens:
        chave = (
            re.sub(r"\s+", " ", item["nome"].strip().lower()),
            round(item["preco_unitario"], 2),
            item["data"],
        )
        if chave in agrupados:
            agrupados[chave]["quantidade"] = round(
                agrupados[chave]["quantidade"] + item["quantidade"], 3
            )
        else:
            agrupados[chave] = dict(item)
            ordem.append(chave)
    return [agrupados[chave] for chave in ordem]


def _nome_apresentavel(texto: str) -> str:
    """Padroniza o nome lido da nota como frase: só a primeira letra maiúscula
    e todo o resto minúsculo ('ARROZ TIPO 1 5KG' -> 'Arroz tipo 1 5kg',
    'Arroz Branco Tio João 5kg' -> 'Arroz branco tio joão 5kg').

    A nota quase sempre vem em CAIXA ALTA e a IA às vezes devolve em Title
    Case; o app grava sempre nesse formato pra a lista ficar uniforme. O
    efeito colateral é que marcas com maiúscula interna ('Coca-Cola',
    'iPhone') também são rebaixadas — se algum dia isso incomodar, dá pra
    manter uma lista de exceções aqui."""
    return re.sub(r"\s+", " ", texto).strip().capitalize()


def _ia_para_numero(valor, padrao):
    try:
        numero = float(str(valor).replace(",", "."))
        return numero if numero > 0 else padrao
    except (TypeError, ValueError):
        return padrao


def _ia_normalizar_data(texto: str) -> str:
    """Aceita dd/mm/aaaa, aaaa-mm-dd ou dd/mm/aa e devolve sempre dd/mm/aaaa
    (formato que o resto do app usa). Devolve "" se não reconhecer."""
    if not texto:
        return ""
    m = re.match(r"^\s*(\d{4})-(\d{1,2})-(\d{1,2})", texto)
    if m:
        ano, mes, dia = m.groups()
        return f"{int(dia):02d}/{int(mes):02d}/{ano}"
    m = re.match(r"^\s*(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})", texto)
    if m:
        dia, mes, ano = m.groups()
        if len(ano) == 2:
            ano = "20" + ano
        return f"{int(dia):02d}/{int(mes):02d}/{ano}"
    return ""


def listar_modelos_ia(api_key: str = None) -> list:
    """Nomes dos modelos da conta que aceitam generateContent (pra popular o
    seletor no diálogo de configuração). Já vem sem o prefixo 'models/'."""
    dados = _ia_requisitar(f"{_IA_URL_BASE}?pageSize=200", timeout=30, api_key=api_key)
    nomes = []
    for modelo in dados.get("models", []):
        if "generateContent" in (modelo.get("supportedGenerationMethods") or []):
            nomes.append(modelo.get("name", "").removeprefix("models/"))
    return sorted(n for n in nomes if n)


def _palavras_para_comparacao(texto: str) -> set:
    """Reduz um texto a um conjunto de palavras minúsculas sem acento, pra
    comparar nomes parecidos (ex: sugerir a pasta certa ao importar foto)."""
    texto = unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode("ascii")
    return set(re.findall(r"[a-z0-9]+", texto))


def sugerir_pasta(nome_lido: str, pastas_existentes: list):
    """Sugere qual pasta (produto) já cadastrada mais se parece com o nome
    lido na nota, comparando palavras em comum — ex: 'Aveia Flocos Marca X'
    sugere a pasta 'Aveia Flocos' se ela existir, mas não confunde com
    'Aveia Grão'. Devolve None se nenhuma pasta bater o suficiente (nesse
    caso quem chamou oferece criar uma pasta nova)."""
    palavras_nota = _palavras_para_comparacao(nome_lido)
    if not palavras_nota:
        return None

    melhor_pasta, melhor_pontuacao = None, 0.0
    for pasta in pastas_existentes:
        palavras_pasta = _palavras_para_comparacao(pasta)
        if not palavras_pasta:
            continue
        # pontuação = fração das palavras DA PASTA presentes na nota — assim
        # a nota cobre 100% de "aveia flocos" mas só ~50% de "aveia grão"
        pontuacao = len(palavras_nota & palavras_pasta) / len(palavras_pasta)
        if pontuacao > melhor_pontuacao:
            melhor_pasta, melhor_pontuacao = pasta, pontuacao

    return melhor_pasta if melhor_pontuacao >= 0.6 else None


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


def migrar_cache_antigo() -> None:
    """Até esta versão o cache ficava em <pasta do script>/cache. Agora fica
    numa pasta por-usuário (ver CACHE_DIR). Move os .json da pasta antiga pra
    nova, uma vez, pra não perder o 'aparece na hora' na primeira abertura
    depois da atualização. Best-effort: qualquer erro é ignorado."""
    if _empacotado():
        return
    antigo = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
    if os.path.abspath(antigo) == os.path.abspath(CACHE_DIR):
        return
    if not os.path.isdir(antigo) or os.path.isdir(CACHE_DIR):
        return
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        for nome in os.listdir(antigo):
            if nome.endswith(".json"):
                # shutil.move (não os.replace) pra funcionar mesmo se a pasta
                # nova estiver em outro sistema de arquivos que a antiga
                shutil.move(os.path.join(antigo, nome), os.path.join(CACHE_DIR, nome))
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# Integração com Google Sheets
# --------------------------------------------------------------------------- #
# Funções puras (sem Qt), executadas em segundo plano por SheetsWorker.

class ErroSheets(Exception):
    """Erro de comunicação com o Google Sheets (rede, configuração ou o
    próprio Apps Script reportando falha)."""


def _requisitar(url: str, dados: bytes = None, metodo: str = "GET", timeout: int = 20) -> dict:
    if not url:
        raise ErroSheets(
            "A URL da planilha não foi configurada. Abra '⚙️ Configurar' e cole a URL do "
            "Web App do Apps Script, ou defina a variável de ambiente GOOGLE_SHEETS_WEBHOOK_URL."
        )
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
    url = sheets_webhook_url()
    if empresa and url:
        url += "?" + urllib.parse.urlencode({"empresa": empresa})
    corpo = _requisitar(url, metodo="GET", timeout=40)
    linhas = corpo.get("linhas", [])

    for linha in linhas:
        linha["data"] = normalizar_data_sheets(linha.get("data"))

    return linhas


def sheets_salvar(novas: list, existentes: list) -> list:
    """Devolve a lista de IDs que o Apps Script não encontrou na planilha
    (linha apagada por fora, por exemplo) — essas edições não foram salvas,
    mesmo a requisição como um todo tendo dado certo."""
    payload = json.dumps({"acao": "salvar", "novas": novas, "existentes": existentes}).encode("utf-8")
    corpo = _requisitar(sheets_webhook_url(), dados=payload, metodo="POST")
    return corpo.get("idsNaoEncontrados", [])


def sheets_remover(ids: list) -> None:
    payload = json.dumps({"acao": "remover", "ids": ids}).encode("utf-8")
    _requisitar(sheets_webhook_url(), dados=payload, metodo="POST")


def sheets_renomear_produtos(itens: list) -> list:
    """Renomeia produto (pasta) e/ou nome de linhas já salvas, por ID — usado
    pra consolidar produtos parecidos numa única pasta (ver ferramenta de
    mesclagem/migração). Cada item de `itens` é um dict com "id" e, opcional,
    "produto" e/ou "nome". Devolve a lista de IDs não encontrados."""
    payload = json.dumps({"acao": "renomearProdutos", "itens": itens}).encode("utf-8")
    corpo = _requisitar(sheets_webhook_url(), dados=payload, metodo="POST")
    return corpo.get("idsNaoEncontrados", [])


class SheetsWorker(QThread):
    """Executa uma função de rede (sheets_buscar/sheets_salvar/sheets_remover
    ou ler_nota_fiscal_ia) em segundo plano e avisa o resultado via sinal Qt."""

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
        except (ErroSheets, ErroIA) as e:
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
        # texto puro: nomes de empresa/produto vêm da planilha e da IA; sem
        # isso, um nome com cara de HTML ("<b>...", "<img ...>") seria
        # interpretado como rich text pelo QLabel.
        self.setTextFormat(Qt.TextFormat.PlainText)
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
    """QTableWidget da tela de compras: Enter avança Nome -> Data ->
    Quantidade -> Preço Unitário em vez do padrão do Qt. Em Preço Unitário só
    confirma o valor e para ali, sem criar linha nova."""

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

        proxima_coluna = {COL_NOME: COL_DATA, COL_DATA: COL_QTD, COL_QTD: COL_PRECO_UNIT}.get(col)
        if proxima_coluna is None:
            return  # estava em Preço Unitário: fica parado ali, sem criar linha nova

        self.setCurrentCell(row, proxima_coluna)
        self.editItem(self.item(row, proxima_coluna))


# --------------------------------------------------------------------------- #
# Base das telas cheias (compras, importar nota, lista de produtos)
# --------------------------------------------------------------------------- #

class PaginaBase(QWidget):
    """Concentra o encanamento que era copiado nas três telas cheias:

    - `_disparar_worker`: roda uma função de rede num SheetsWorker mantendo
      uma referência forte a ele em `_workers_ativos` até terminar — sem isso,
      disparar uma segunda operação em paralelo (ex: remover duas linhas
      rápido) sobrescreveria a única referência à primeira QThread, que ainda
      rodando e sem dono podia ser coletada no meio da execução e derrubar o app;
    - `marcar_destruida` / `_destruida`: a MainWindow marca a página como "de
      saída" ANTES de destruí-la; os callbacks de rede atrasados checam essa
      flag antes de mexer em widgets já apagados pelo Qt (evita o
      `RuntimeError: wrapped C/C++ object ... has been deleted`);
    - `_definir_ocupado`: bloqueia os botões de `_botoes_bloqueaveis()`
      enquanto uma chamada de rede está em andamento;
    - `_texto_celula` / `_estilo_botao_destaque`: helpers de UI comuns.
    """

    def __init__(self):
        super().__init__()
        self._workers_ativos = []
        self._operacao_em_andamento = False
        self._destruida = False

    def marcar_destruida(self):
        self._destruida = True

    def _disparar_worker(self, funcao, *args, ao_concluir):
        worker = SheetsWorker(funcao, *args)
        self._workers_ativos.append(worker)

        def _finalizar(ok, resultado):
            if worker in self._workers_ativos:
                self._workers_ativos.remove(worker)
            ao_concluir(ok, resultado)

        worker.concluido.connect(_finalizar)
        worker.start()
        return worker

    def _botoes_bloqueaveis(self):
        """Botões desabilitados por `_definir_ocupado`. Cada página sobrescreve."""
        return ()

    def _definir_ocupado(self, ocupado: bool, mensagem: str = ""):
        self._operacao_em_andamento = ocupado
        for botao in self._botoes_bloqueaveis():
            botao.setEnabled(not ocupado)
        if mensagem and getattr(self, "status_label", None) is not None:
            self.status_label.setStyleSheet("color: #d9a441;")
            self.status_label.setText(mensagem)

    def _texto_celula(self, row: int, col: int) -> str:
        item = self.tabela.item(row, col)
        return item.text().strip() if item else ""

    def _estilo_botao_destaque(self) -> str:
        return (
            f"QPushButton {{ background-color: {self.cor}; color: {self.empresa['cor_texto']}; "
            f"font-weight: bold; padding: 6px 12px; border-radius: 4px; }}"
        )


# --------------------------------------------------------------------------- #
# Página 3: registros (compras) de um produto específico
# --------------------------------------------------------------------------- #

class ProductEntriesPage(PaginaBase):
    """Mostra e edita as compras de um produto. Cada linha da tabela guarda
    seu ID da planilha em Qt.ItemDataRole.UserRole (None = ainda não existe
    no Sheets). Encanamento de rede/ciclo de vida vem de PaginaBase."""

    def __init__(self, empresa: dict, produto: str, linhas_iniciais: list, voltar_callback):
        super().__init__()
        self.empresa = empresa
        self.produto = produto
        self.cor = empresa["cor"]
        self.voltar_callback = voltar_callback
        self._carregando = False
        self._remocoes_em_andamento = 0  # remoções de linha ainda não confirmadas (ver _salvar/_recarregar)
        self._alteracoes_nao_salvas = False  # edição pendente de salvar (ver _tentar_voltar)
        self._itens_editados = set()  # ids de objeto das linhas tocadas desde o último salvamento (ver _salvar)

        self._montar_ui()
        self._popular_tabela(linhas_iniciais)

    def _botoes_bloqueaveis(self):
        return (self.btn_add, self.btn_remover, self.btn_salvar, self.btn_recarregar, self.btn_voltar)

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

        item_nome = QTableWidgetItem(dados.get("nome") or "")
        item_data = QTableWidgetItem(dados.get("data") or QDate.currentDate().toString("dd/MM/yyyy"))
        item_data.setData(Qt.ItemDataRole.UserRole, dados.get("id"))
        item_qtd = QTableWidgetItem(str(dados.get("quantidade", "")) if dados.get("quantidade") else "")
        item_preco = QTableWidgetItem(str(dados.get("preco_unitario", "")) if dados.get("preco_unitario") else "")
        item_total = QTableWidgetItem(format_moeda(dados.get("preco_total", 0.0)))
        item_total.setFlags(item_total.flags() & ~Qt.ItemFlag.ItemIsEditable)

        for col, item in enumerate([item_nome, item_data, item_qtd, item_preco, item_total]):
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
        self._itens_editados = set()

    def _id_da_linha(self, row: int):
        item = self.tabela.item(row, COL_DATA)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _snapshot_linha(self, row: int) -> dict:
        qtd_txt = self._texto_celula(row, COL_QTD)
        preco_txt = self._texto_celula(row, COL_PRECO_UNIT)
        item_data = self.tabela.item(row, COL_DATA)
        return {
            "id": self._id_da_linha(row),
            "nome": self._texto_celula(row, COL_NOME),
            "data": self._texto_celula(row, COL_DATA),
            "quantidade": qtd_txt,
            "preco_unitario": preco_txt,
            "preco_total": parse_numero(qtd_txt) * parse_numero(preco_txt),
            "_editada": item_data is not None and id(item_data) in self._itens_editados,
        }

    def _esquecer_edicao(self, row: int):
        """Tira a marca de 'editada' da linha antes dela ser removida da
        tabela. Sem isso, o endereço de memória do item removido poderia ser
        reciclado depois por um item de outra linha nunca tocada, marcando-a
        como suja (e reenviando-a ao Sheets) por engano."""
        item_data = self.tabela.item(row, COL_DATA)
        if item_data is not None:
            self._itens_editados.discard(id(item_data))

    def _remover_linha(self):
        if self._operacao_em_andamento:
            return  # evita corromper os índices de linha de um Salvar/Recarregar em andamento
        row = self.tabela.currentRow()
        if row < 0:
            QMessageBox.information(self, "Remover linha", "Selecione uma linha para remover.")
            return

        id_linha = self._id_da_linha(row)
        if not id_linha:
            self._esquecer_edicao(row)
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

        # remoção otimista: some da tela na hora, sem esperar a rede — se o
        # Sheets recusar, a linha volta e um erro é mostrado
        dados_removidos = self._snapshot_linha(row)
        self._esquecer_edicao(row)
        self.tabela.removeRow(row)
        self._atualizar_indicadores()

        self._remocoes_em_andamento += 1
        self._disparar_worker(
            sheets_remover, [id_linha],
            ao_concluir=lambda ok, msg: self._on_remocao_concluida(ok, msg, dados_removidos),
        )

    def _on_remocao_concluida(self, sucesso: bool, mensagem, dados_removidos: dict):
        self._remocoes_em_andamento -= 1
        if self._destruida:
            return  # a página já foi fechada/trocada enquanto a rede respondia
        if sucesso:
            self.status_label.setStyleSheet("color: #2e7d32;")
            self.status_label.setText("Linha removida do Google Sheets.")
        else:
            row = self._adicionar_linha(dados_removidos)  # desfaz a remoção otimista
            if dados_removidos.get("_editada"):
                item_data = self.tabela.item(row, COL_DATA)
                if item_data is not None:
                    self._itens_editados.add(id(item_data))
                    self._alteracoes_nao_salvas = True
            self._atualizar_indicadores()
            self.status_label.setStyleSheet("color: #c0392b;")
            self.status_label.setText(f"Falha ao remover: {mensagem}")
            QMessageBox.critical(self, "Erro ao remover", str(mensagem))

    def _on_item_changed(self, item: QTableWidgetItem):
        if self._carregando:
            return
        self._alteracoes_nao_salvas = True
        item_data = self.tabela.item(item.row(), COL_DATA)
        if item_data is not None:
            self._itens_editados.add(id(item_data))  # marca a linha como suja, pro _salvar reenviar só ela
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
        if self._operacao_em_andamento or self._remocoes_em_andamento > 0:
            return

        novas, existentes, linhas_por_id_novo, itens_enviados = [], [], {}, set()

        for row in range(self.tabela.rowCount()):
            qtd = parse_numero(self._texto_celula(row, COL_QTD))
            preco = parse_numero(self._texto_celula(row, COL_PRECO_UNIT))
            if qtd <= 0 or preco <= 0:
                continue  # ignora linhas em branco/incompletas

            id_linha = self._id_da_linha(row)
            item_data = self.tabela.item(row, COL_DATA)
            if id_linha and id(item_data) not in self._itens_editados:
                continue  # já está salva e não foi tocada — não reenvia à toa

            registro = {
                "nome": self._texto_celula(row, COL_NOME),
                "data": self._texto_celula(row, COL_DATA),
                "quantidade": qtd,
                "preco_unitario": preco,
                "preco_total": qtd * preco,
            }

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

            itens_enviados.add(id(item_data))

        if not novas and not existentes:
            self.status_label.setStyleSheet("color: #2e7d32;")
            self.status_label.setText("Nada para salvar (preencha quantidade e preço unitário, ou nada mudou).")
            return

        self._definir_ocupado(True, "Salvando no Google Sheets...")
        self._disparar_worker(
            sheets_salvar, novas, existentes,
            ao_concluir=lambda ok, resultado: self._on_salvamento_concluido(
                ok, resultado, linhas_por_id_novo, itens_enviados
            ),
        )

    def _on_salvamento_concluido(self, sucesso: bool, resultado, linhas_por_id_novo: dict, itens_enviados: set):
        if self._destruida:
            return  # a página já foi fechada/trocada enquanto a rede respondia
        self._definir_ocupado(False)
        if sucesso:
            ids_nao_encontrados = set(resultado or [])
            self._carregando = True
            for novo_id, row in linhas_por_id_novo.items():
                item = self.tabela.item(row, COL_DATA)
                if item:
                    item.setData(Qt.ItemDataRole.UserRole, novo_id)
            self._carregando = False

            if ids_nao_encontrados:
                # o Apps Script avisou que algumas linhas "existentes" não
                # foram achadas na planilha (apagada por fora, por exemplo)
                # — mantém só essas específicas como pendentes, em vez de
                # assumir que tudo foi salvo
                itens_com_problema = set()
                for row in range(self.tabela.rowCount()):
                    if self._id_da_linha(row) in ids_nao_encontrados:
                        item_data = self.tabela.item(row, COL_DATA)
                        if item_data is not None:
                            itens_com_problema.add(id(item_data))
                self._itens_editados -= (itens_enviados - itens_com_problema)
                self._alteracoes_nao_salvas = bool(self._itens_editados)
                self.status_label.setStyleSheet("color: #c0392b;")
                self.status_label.setText(
                    f"⚠ {len(ids_nao_encontrados)} linha(s) não encontrada(s) no Sheets — continuam pendentes."
                )
                QMessageBox.warning(
                    self, "Salvamento parcial",
                    f"{len(ids_nao_encontrados)} linha(s) não foram encontradas no Google Sheets "
                    "(podem ter sido apagadas por fora) e continuam pendentes. Recarregue pra conferir."
                )
            else:
                # remove só o que foi enviado agora — uma edição feita em
                # outra linha enquanto este salvamento estava em andamento
                # continua marcada como pendente, em vez de ser descartada
                self._itens_editados -= itens_enviados
                self._alteracoes_nao_salvas = bool(self._itens_editados)
                self.status_label.setStyleSheet("color: #2e7d32;")
                self.status_label.setText("✓ Salvo no Google Sheets com sucesso.")
        else:
            self.status_label.setStyleSheet("color: #c0392b;")
            self.status_label.setText(f"Falha ao salvar: {resultado}")
            QMessageBox.critical(self, "Erro ao salvar no Google Sheets", str(resultado))

    def _recarregar_do_sheets(self):
        if self._operacao_em_andamento or self._remocoes_em_andamento > 0:
            return
        self._definir_ocupado(True, "Recarregando do Google Sheets...")
        self._disparar_worker(sheets_buscar, self.empresa["nome"], ao_concluir=self._on_recarregamento_concluido)

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
# Diálogo de configuração (URL da planilha + chave da API do Gemini + modelo)
# --------------------------------------------------------------------------- #

def _campo_segredo(valor: str, placeholder: str):
    """Um QLineEdit em modo senha + um botão 👁 pra revelar. Devolve
    (QHBoxLayout, QLineEdit) — usado pra URL da planilha e chave da API, que
    são segredos e não devem ficar visíveis na tela por padrão."""
    campo = QLineEdit(valor)
    campo.setEchoMode(QLineEdit.EchoMode.Password)
    campo.setPlaceholderText(placeholder)
    botao_ver = QPushButton("👁")
    botao_ver.setCheckable(True)
    botao_ver.setFixedWidth(36)
    botao_ver.setToolTip("Mostrar/ocultar")
    botao_ver.toggled.connect(
        lambda ver: campo.setEchoMode(
            QLineEdit.EchoMode.Normal if ver else QLineEdit.EchoMode.Password
        )
    )
    linha = QHBoxLayout()
    linha.addWidget(campo)
    linha.addWidget(botao_ver)
    return linha, campo


class ConfigDialog(QDialog):
    """Janela pra configurar a URL do Web App do Apps Script (obrigatória) e,
    opcionalmente, a chave da API do Google Gemini + o modelo (só pra ler notas
    fiscais). Grava em ~/.config/controle_empresas/config.json (via
    salvar_config). O botão "Buscar modelos" lista os modelos que a chave
    informada libera. A URL e a chave são segredos: não ficam no código nem
    no git, e o app também aceita as duas por variável de ambiente
    (GOOGLE_SHEETS_WEBHOOK_URL / GEMINI_API_KEY)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configurar")
        self.setMinimumWidth(480)
        config = carregar_config()

        layout = QVBoxLayout(self)

        explicacao = QLabel(
            "A URL da planilha é o endereço do Web App do Apps Script (termina em /exec) — "
            "sem ela o app não abre nenhuma empresa.\n"
            "A chave da API do Google Gemini é opcional: só serve pra ler notas fiscais por "
            "foto/link. Crie uma gratuita em aistudio.google.com/apikey."
        )
        explicacao.setWordWrap(True)
        explicacao.setStyleSheet("color: #999;")
        layout.addWidget(explicacao)

        formulario = QFormLayout()

        linha_url, self.campo_url = _campo_segredo(
            config.get("sheets_webhook_url", ""),
            "https://script.google.com/macros/s/.../exec",
        )
        formulario.addRow("URL da planilha:", linha_url)

        linha_chave, self.campo_chave = _campo_segredo(config.get("gemini_api_key", ""), "AIza...")
        formulario.addRow("Chave da API (IA):", linha_chave)

        self.combo_modelo = QComboBox()
        self.combo_modelo.setEditable(True)
        self.combo_modelo.addItem(config.get("gemini_modelo") or MODELO_IA_PADRAO)
        botao_buscar = QPushButton("Buscar modelos")
        botao_buscar.clicked.connect(self._buscar_modelos)
        linha_modelo = QHBoxLayout()
        linha_modelo.addWidget(self.combo_modelo)
        linha_modelo.addWidget(botao_buscar)
        formulario.addRow("Modelo:", linha_modelo)

        layout.addLayout(formulario)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        botoes.accepted.connect(self._salvar)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)

    def _buscar_modelos(self):
        chave = self.campo_chave.text().strip()
        if not chave:
            self.status.setStyleSheet("color: #c0392b;")
            self.status.setText("Cole a chave da API primeiro.")
            return
        self.status.setStyleSheet("color: #d9a441;")
        self.status.setText("Buscando modelos disponíveis...")
        QApplication.processEvents()
        try:
            modelos = listar_modelos_ia(api_key=chave)
        except ErroIA as e:
            self.status.setStyleSheet("color: #c0392b;")
            self.status.setText(str(e))
            return
        if not modelos:
            self.status.setStyleSheet("color: #c0392b;")
            self.status.setText("Nenhum modelo compatível encontrado pra essa chave.")
            return
        atual = self.combo_modelo.currentText().strip()
        self.combo_modelo.clear()
        self.combo_modelo.addItems(modelos)
        preferido = next(
            (m for m in modelos if "flash" in m and "lite" not in m and "image" not in m),
            atual if atual in modelos else modelos[0],
        )
        self.combo_modelo.setCurrentText(atual if atual in modelos else preferido)
        self.status.setStyleSheet("color: #2e7d32;")
        self.status.setText(f"{len(modelos)} modelo(s) disponível(is).")

    def _salvar(self):
        url = self.campo_url.text().strip()
        chave = self.campo_chave.text().strip()
        modelo = self.combo_modelo.currentText().strip() or MODELO_IA_PADRAO

        if not url and not chave:
            self.status.setStyleSheet("color: #c0392b;")
            self.status.setText("Preencha pelo menos a URL da planilha.")
            return
        if url and not re.match(r"https://script\.google\.com/.+/exec/?$", url):
            self.status.setStyleSheet("color: #c0392b;")
            self.status.setText("A URL deve ser a do Web App do Apps Script e terminar em /exec.")
            return

        config = carregar_config()
        config["sheets_webhook_url"] = url
        config["gemini_api_key"] = chave
        config["gemini_modelo"] = modelo
        try:
            salvar_config(config)
        except OSError as e:
            QMessageBox.critical(self, "Erro ao salvar", f"Não consegui gravar a configuração:\n{e}")
            return
        self.accept()


# --------------------------------------------------------------------------- #
# Página de conferência dos itens lidos por foto de uma nota fiscal
# --------------------------------------------------------------------------- #

class ImportarNotaFiscalPage(PaginaBase):
    """Página cheia (não é uma janela flutuante) pra revisar os itens que a
    IA leu de uma foto de nota fiscal: a própria foto fica visível à
    esquerda, pra conferência lado a lado, e a tabela à direita mostra cada
    item reconhecido — pra qual pasta ele vai, com que nome, data, quantidade
    e preço. Nada é salvo no Sheets até o usuário revisar e clicar em
    "✅ Confirmar tudo". Encanamento de rede/ciclo de vida vem de PaginaBase."""

    COL_PASTA, COL_NOME, COL_DATA, COL_QTD, COL_PRECO = range(5)

    def __init__(self, empresa: dict, caminho_imagem: str, itens_lidos: list, pastas_existentes: list,
                 voltar_callback, ao_confirmar_callback):
        super().__init__()
        self.empresa = empresa
        self.cor = empresa["cor"]
        self.caminho_imagem = caminho_imagem
        self.pastas_existentes = sorted(pastas_existentes, key=str.lower)
        self.voltar_callback = voltar_callback
        self.ao_confirmar_callback = ao_confirmar_callback  # chamado com a quantidade salva, após sucesso

        self._montar_ui()
        self._popular_tabela(itens_lidos)

    def _botoes_bloqueaveis(self):
        return (self.btn_add, self.btn_remover, self.btn_confirmar, self.btn_voltar)

    def _montar_ui(self):
        layout_principal = QHBoxLayout(self)
        layout_principal.setContentsMargins(16, 16, 16, 16)
        layout_principal.setSpacing(16)

        # -- painel esquerdo: a foto da nota (quando veio de foto), pra conferência --
        painel_foto_widget = QWidget()
        painel_foto_widget.setMaximumWidth(420)
        painel_foto = QVBoxLayout(painel_foto_widget)
        painel_foto.setContentsMargins(0, 0, 0, 0)

        veio_de_foto = bool(self.caminho_imagem) and not QPixmap(self.caminho_imagem).isNull()

        titulo_foto = QLabel("📷 Nota importada" if veio_de_foto else "🔗 Nota importada por link")
        titulo_foto.setStyleSheet(f"color: {self.cor}; font-weight: bold; font-size: 14px;")
        painel_foto.addWidget(titulo_foto)

        self.label_foto = QLabel()
        self.label_foto.setWordWrap(True)
        self.label_foto.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        if veio_de_foto:
            self._pixmap_original = QPixmap(self.caminho_imagem)
            self.label_foto.setPixmap(
                self._pixmap_original.scaledToWidth(380, Qt.TransformationMode.SmoothTransformation)
            )
        else:
            self._pixmap_original = QPixmap()
            self.label_foto.setText(
                "Os itens ao lado vieram da página oficial da SEFAZ (via link do QR code).\n\n"
                "Confira mesmo assim antes de confirmar."
            )
            self.label_foto.setStyleSheet("color: #999;")

        scroll_foto = QScrollArea()
        scroll_foto.setWidget(self.label_foto)
        scroll_foto.setWidgetResizable(True)
        painel_foto.addWidget(scroll_foto)

        layout_principal.addWidget(painel_foto_widget)

        # -- painel direito: itens reconhecidos, editáveis, com pasta de destino --
        painel_direito = QVBoxLayout()

        linha_titulo = QHBoxLayout()
        self.btn_voltar = QPushButton("← Cancelar")
        self.btn_voltar.clicked.connect(self._cancelar)
        linha_titulo.addWidget(self.btn_voltar)

        titulo = QLabel("Conferir itens da nota")
        fonte_titulo = QFont()
        fonte_titulo.setPointSize(16)
        fonte_titulo.setBold(True)
        titulo.setFont(fonte_titulo)
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        titulo.setStyleSheet(f"color: {self.cor};")
        linha_titulo.addWidget(titulo, stretch=1)

        espacador = QLabel("")
        espacador.setMinimumWidth(self.btn_voltar.sizeHint().width())
        linha_titulo.addWidget(espacador)
        painel_direito.addLayout(linha_titulo)

        dica = QLabel(
            "Confira ou corrija a pasta, nome, data, quantidade e preço de cada item antes de confirmar. "
            "Pastas que ainda não existem são criadas na hora."
        )
        dica.setWordWrap(True)
        dica.setStyleSheet("color: #999;")
        painel_direito.addWidget(dica)

        self.tabela = QTableWidget(0, 5)
        self.tabela.setHorizontalHeaderLabels(["Pasta (produto)", "Nome", "Data", "Quantidade", "Preço Unitário"])
        self.tabela.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabela.setAlternatingRowColors(True)
        self.tabela.horizontalHeader().setStyleSheet(
            f"QHeaderView::section {{ background-color: {self.cor}; color: {self.empresa['cor_texto']}; "
            f"padding: 6px; font-weight: bold; }}"
        )
        painel_direito.addWidget(self.tabela)

        botoes = QHBoxLayout()
        self.btn_add = QPushButton("+ Adicionar item")
        self.btn_add.clicked.connect(lambda: self._adicionar_linha())
        self.btn_remover = QPushButton("- Remover item selecionado")
        self.btn_remover.clicked.connect(self._remover_linha)
        botoes.addWidget(self.btn_add)
        botoes.addWidget(self.btn_remover)
        botoes.addStretch()

        self.btn_confirmar = QPushButton("✅ Confirmar tudo")
        self.btn_confirmar.setStyleSheet(
            f"QPushButton {{ background-color: {self.cor}; color: {self.empresa['cor_texto']}; "
            f"font-weight: bold; padding: 8px 18px; border-radius: 4px; }}"
        )
        self.btn_confirmar.clicked.connect(self._confirmar_tudo)
        botoes.addWidget(self.btn_confirmar)
        painel_direito.addLayout(botoes)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #2e7d32;")
        painel_direito.addWidget(self.status_label)

        layout_principal.addLayout(painel_direito, stretch=1)

    def _popular_tabela(self, itens: list):
        if itens:
            for item in itens:
                self._adicionar_linha(item)
        else:
            self._adicionar_linha()  # nenhum item reconhecido: começa com 1 linha em branco

    def _adicionar_linha(self, dados: dict = None):
        dados = dados or {}
        row = self.tabela.rowCount()
        self.tabela.insertRow(row)

        combo_pasta = QComboBox()
        combo_pasta.setEditable(True)
        combo_pasta.addItems(self.pastas_existentes)
        pasta_sugerida = dados.get("pasta") or sugerir_pasta(dados.get("nome", ""), self.pastas_existentes)
        combo_pasta.setCurrentText(pasta_sugerida or dados.get("nome", ""))
        self.tabela.setCellWidget(row, self.COL_PASTA, combo_pasta)

        item_nome = QTableWidgetItem(dados.get("nome", ""))
        item_data = QTableWidgetItem(dados.get("data") or QDate.currentDate().toString("dd/MM/yyyy"))
        item_qtd = QTableWidgetItem(str(dados.get("quantidade", "")))
        item_preco = QTableWidgetItem(str(dados.get("preco_unitario", "")))
        for col, item in ((self.COL_NOME, item_nome), (self.COL_DATA, item_data),
                           (self.COL_QTD, item_qtd), (self.COL_PRECO, item_preco)):
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tabela.setItem(row, col, item)
        return row

    def _remover_linha(self):
        row = self.tabela.currentRow()
        if row >= 0:
            self.tabela.removeRow(row)

    def _cancelar(self):
        self.voltar_callback()

    def _confirmar_tudo(self):
        if self._operacao_em_andamento:
            return

        novas, ignoradas = [], 0
        for row in range(self.tabela.rowCount()):
            combo = self.tabela.cellWidget(row, self.COL_PASTA)
            pasta = combo.currentText().strip() if combo else ""
            qtd = parse_numero(self._texto_celula(row, self.COL_QTD))
            preco = parse_numero(self._texto_celula(row, self.COL_PRECO))
            if not pasta or qtd <= 0 or preco <= 0:
                ignoradas += 1  # linha incompleta: não trava a confirmação das outras, mas conta
                continue

            novas.append({
                "id": gerar_id(),
                "empresa": self.empresa["nome"],
                "produto": pasta,
                "nome": self._texto_celula(row, self.COL_NOME),
                "data": self._texto_celula(row, self.COL_DATA),
                "quantidade": qtd,
                "preco_unitario": preco,
                "preco_total": qtd * preco,
            })

        if not novas:
            QMessageBox.warning(
                self, "Nada pra confirmar",
                "Preencha pelo menos um item com pasta, quantidade e preço maiores que zero.",
            )
            return

        if ignoradas:
            resposta = QMessageBox.question(
                self, "Linhas incompletas",
                f"{ignoradas} linha(s) sem pasta, quantidade ou preço válido vão ser ignoradas.\n"
                f"Salvar as outras {len(novas)}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if resposta != QMessageBox.StandardButton.Yes:
                return

        self._definir_ocupado(True, f"Salvando {len(novas)} item(ns) no Google Sheets...")

        def _ao_salvar(sucesso, resultado):
            if self._destruida:
                return  # a página já foi fechada/trocada enquanto a rede respondia
            self._definir_ocupado(False)
            if sucesso:
                self.ao_confirmar_callback(len(novas))
            else:
                self.status_label.setStyleSheet("color: #c0392b;")
                self.status_label.setText(f"Falha ao salvar: {resultado}")
                QMessageBox.critical(self, "Erro ao salvar", str(resultado))

        self._disparar_worker(sheets_salvar, novas, [], ao_concluir=_ao_salvar)


# --------------------------------------------------------------------------- #
# Página 2: lista de produtos de uma empresa
# --------------------------------------------------------------------------- #

class ProductListPage(PaginaBase):
    """Lista os produtos de uma empresa. É a única página reaproveitada pela
    MainWindow (uma por empresa), então não usa a flag `_destruida` — mas
    herda o resto do encanamento de PaginaBase."""

    COL_PRODUTO, COL_ULTIMA_DATA, COL_ULTIMO_VALOR, COL_ABRIR = range(4)

    def __init__(self, empresa: dict, abrir_produto_callback, abrir_importar_foto_callback, voltar_callback):
        super().__init__()
        self.empresa = empresa
        self.cor = empresa["cor"]
        self.abrir_produto_callback = abrir_produto_callback
        self.abrir_importar_foto_callback = abrir_importar_foto_callback
        self.voltar_callback = voltar_callback

        self._linhas_por_produto = {}   # produto -> [linhas da planilha]
        self._produtos_pendentes = []   # produtos criados nesta sessão, sem nenhuma compra salva
        self._remocoes_em_andamento = 0  # remoções de produto ainda não confirmadas (ver recarregar)
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
        bloco_esquerdo_widget = QWidget()
        bloco_esquerdo = QHBoxLayout(bloco_esquerdo_widget)
        bloco_esquerdo.setContentsMargins(0, 0, 0, 0)
        bloco_esquerdo.setSpacing(10)

        btn_voltar = QPushButton("← Voltar")
        btn_voltar.clicked.connect(self.voltar_callback)
        bloco_esquerdo.addWidget(btn_voltar)
        bloco_esquerdo.addSpacing(28)  # afasta o botão de importar do "Voltar"

        self.btn_importar_foto = QPushButton("📷 Importar nota fiscal")
        self.btn_importar_foto.setStyleSheet(
            f"QPushButton {{ background-color: {self.cor}; color: {self.empresa['cor_texto']}; "
            f"font-weight: bold; font-size: 13px; padding: 10px 18px; border-radius: 4px; }}"
        )
        self.btn_importar_foto.clicked.connect(self._importar_de_foto)
        bloco_esquerdo.addWidget(self.btn_importar_foto)

        self.btn_importar_link = QPushButton("🔗 Importar por link")
        self.btn_importar_link.setToolTip(
            "Cole o link do QR code da nota fiscal (NFC-e) — o app busca a página oficial "
            "da SEFAZ e a IA extrai os itens de lá"
        )
        self.btn_importar_link.clicked.connect(self._importar_por_link)
        bloco_esquerdo.addWidget(self.btn_importar_link)

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

        # o título só fica centralizado de verdade se os blocos das duas
        # pontas tiverem a mesma largura — o esquerdo cresceu com o botão de
        # importar nota fiscal, então igualamos os dois pela largura do maior
        largura_maior = max(bloco_esquerdo_widget.sizeHint().width(), bloco_direito_widget.sizeHint().width())
        bloco_esquerdo_widget.setMinimumWidth(largura_maior)
        bloco_direito_widget.setMinimumWidth(largura_maior)

        linha_titulo.addWidget(bloco_esquerdo_widget)
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

        self.btn_config_ia = QPushButton("⚙️ Configurar")
        self.btn_config_ia.setToolTip("URL da planilha, chave da API e modelo da IA")
        self.btn_config_ia.clicked.connect(self._configurar_ia)

        botoes.addWidget(self.btn_add)
        botoes.addWidget(self.btn_remover)
        botoes.addWidget(self.btn_recarregar)
        botoes.addStretch()
        botoes.addWidget(self.btn_config_ia)
        layout.addLayout(botoes)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #2e7d32;")
        layout.addWidget(self.status_label)

    def _botoes_bloqueaveis(self):
        return (self.btn_add, self.btn_remover, self.btn_recarregar,
                self.btn_importar_foto, self.btn_importar_link, self.btn_config_ia)

    def recarregar(self):
        if self._operacao_em_andamento or self._remocoes_em_andamento > 0:
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

        self._disparar_worker(sheets_buscar, self.empresa["nome"], ao_concluir=self._on_carregamento_concluido)

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
        # parse_numero tolera célula vazia/texto: o Sheets ou o cache podem
        # devolver quantidade/preço como string, e "" * float é TypeError
        total_ultima = (
            parse_numero(str(ultima.get("quantidade", ""))) * parse_numero(str(ultima.get("preco_unitario", "")))
            if ultima else 0
        )
        valor_txt = format_moeda(total_ultima)

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

    def _configurar_ia(self):
        ConfigDialog(self).exec()

    def _garantir_ia_configurada(self) -> bool:
        """Se ainda não há chave da API, oferece abrir a configuração. Devolve
        True se dá pra seguir (chave presente)."""
        if ia_api_key():
            return True
        resposta = QMessageBox.question(
            self, "IA não configurada",
            "Pra importar uma nota fiscal é preciso configurar a chave da API "
            "do Google Gemini.\n\nQuer configurar agora?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return False
        return ConfigDialog(self).exec() == QDialog.DialogCode.Accepted and bool(ia_api_key())

    def _importar_de_foto(self):
        """Envia uma foto de nota fiscal pra IA (Google Gemini), que devolve
        os itens já estruturados, e abre a página de conferência com a foto
        do lado — nada é salvo até o usuário revisar e confirmar lá."""
        if self._operacao_em_andamento or not self._garantir_ia_configurada():
            return

        caminho, _ = QFileDialog.getOpenFileName(
            self, "Selecionar foto da nota", "",
            "Imagens (*.png *.jpg *.jpeg *.bmp *.webp *.heic *.heif)"
        )
        if not caminho:
            return

        self._definir_ocupado(True)
        self.status_label.setStyleSheet("color: #d9a441;")
        self.status_label.setText("Lendo a nota fiscal com a IA (pode levar alguns segundos)...")
        self._disparar_worker(ler_nota_fiscal_ia, caminho,
                              ao_concluir=lambda ok, res: self._on_leitura_ia(ok, res, caminho))

    def _importar_por_link(self):
        """Pede o link do QR code de uma NFC-e, baixa a página oficial da
        SEFAZ e manda o texto pra IA extrair os itens — mesma tela de
        conferência da importação por foto."""
        if self._operacao_em_andamento or not self._garantir_ia_configurada():
            return

        url, ok = QInputDialog.getText(
            self, "Importar nota por link",
            "Cole o link do QR code da nota fiscal\n(escaneie o QR com a câmera do celular e copie o endereço):",
        )
        url = (url or "").strip()
        if not ok or not url:
            return

        self._definir_ocupado(True)
        self.status_label.setStyleSheet("color: #d9a441;")
        self.status_label.setText("Baixando a nota da SEFAZ e lendo com a IA...")
        self._disparar_worker(ler_nota_fiscal_link, url,
                              ao_concluir=lambda ok_, res: self._on_leitura_ia(ok_, res, ""))

    def _on_leitura_ia(self, sucesso: bool, resultado, origem: str):
        """Callback comum das duas importações (foto e link). `origem` é o
        caminho da imagem, ou "" quando veio de um link."""
        self._definir_ocupado(False)
        self.status_label.setText("")
        if not sucesso:
            self.status_label.setStyleSheet("color: #c0392b;")
            self.status_label.setText(f"Falha ao ler a nota: {resultado}")
            QMessageBox.critical(self, "Erro ao ler a nota fiscal", str(resultado))
            return

        itens = resultado
        if not itens:
            QMessageBox.information(
                self, "Nenhum item reconhecido",
                "A IA não encontrou itens de compra nessa nota. Você pode abrir a tela de "
                "conferência mesmo assim e adicionar os itens na mão.",
            )
        pastas_existentes = sorted(set(list(self._linhas_por_produto.keys()) + self._produtos_pendentes), key=str.lower)
        self.abrir_importar_foto_callback(self.empresa, origem, itens, pastas_existentes)

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

        # remoção otimista: some da lista na hora, sem esperar a rede — se o
        # Sheets recusar, o produto volta e um erro é mostrado
        linhas_removidas = self._linhas_por_produto.pop(nome_produto, [])
        self._reconstruir_tabela()

        self._remocoes_em_andamento += 1
        self._disparar_worker(
            sheets_remover, ids,
            ao_concluir=lambda ok, msg: self._on_remocao_produto_concluida(ok, msg, nome_produto, linhas_removidas),
        )

    def _on_remocao_produto_concluida(self, sucesso: bool, mensagem, nome_produto: str, linhas_removidas: list):
        self._remocoes_em_andamento -= 1
        if sucesso:
            self.status_label.setStyleSheet("color: #2e7d32;")
            self.status_label.setText(f"'{nome_produto}' removido do Google Sheets.")
        else:
            self._linhas_por_produto[nome_produto] = linhas_removidas  # desfaz a remoção otimista
            self._reconstruir_tabela()
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

        if not sheets_webhook_url():
            aviso = QLabel(
                "⚠ URL da planilha não configurada — abra uma empresa e clique em "
                "\"⚙️ Configurar\" pra colar a URL do Web App do Apps Script."
            )
            aviso.setWordWrap(True)
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
        self._pagina_importar_atual = None

    def abrir_empresa(self, empresa: dict):
        nome_empresa = empresa["nome"]
        if nome_empresa not in self._paginas_produtos:
            pagina = ProductListPage(
                empresa,
                abrir_produto_callback=self.abrir_produto,
                abrir_importar_foto_callback=self.abrir_importar_nota_fiscal,
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

    def abrir_importar_nota_fiscal(self, empresa: dict, caminho_imagem: str, itens_lidos: list, pastas_existentes: list):
        pagina = ImportarNotaFiscalPage(
            empresa, caminho_imagem, itens_lidos, pastas_existentes,
            voltar_callback=lambda: self.voltar_para_lista_produtos(empresa),
            ao_confirmar_callback=lambda quantidade: self._on_nota_fiscal_confirmada(empresa, quantidade),
        )
        if self._pagina_importar_atual is not None:
            self._pagina_importar_atual.marcar_destruida()
            self.stack.removeWidget(self._pagina_importar_atual)
            self._pagina_importar_atual.deleteLater()

        self._pagina_importar_atual = pagina
        self.stack.addWidget(pagina)
        self.stack.setCurrentWidget(pagina)

    def _on_nota_fiscal_confirmada(self, empresa: dict, quantidade: int):
        QMessageBox.information(
            self, "Itens salvos",
            f"{quantidade} item(ns) salvo(s) com sucesso no Google Sheets.",
        )
        self.voltar_para_lista_produtos(empresa)

    def voltar_para_lista_produtos(self, empresa: dict):
        nome_empresa = empresa["nome"]
        self.stack.setCurrentWidget(self._paginas_produtos[nome_empresa])
        self._paginas_produtos[nome_empresa].recarregar()

    def voltar_para_selecao(self):
        self.stack.setCurrentWidget(self.pagina_selecao)


def aplicar_tema_escuro(app: QApplication):
    """Paleta escura fixa, aplicada por cima do estilo Fusion — o app sempre
    fica com esse visual, não importa o tema (claro/escuro) do sistema ou do
    ambiente onde for executado."""
    paleta = QPalette()
    paleta.setColor(QPalette.ColorRole.Window, QColor(37, 37, 38))
    paleta.setColor(QPalette.ColorRole.WindowText, QColor(220, 220, 220))
    paleta.setColor(QPalette.ColorRole.Base, QColor(30, 30, 30))
    paleta.setColor(QPalette.ColorRole.AlternateBase, QColor(45, 45, 48))
    paleta.setColor(QPalette.ColorRole.ToolTipBase, QColor(220, 220, 220))
    paleta.setColor(QPalette.ColorRole.ToolTipText, QColor(37, 37, 38))
    paleta.setColor(QPalette.ColorRole.Text, QColor(220, 220, 220))
    paleta.setColor(QPalette.ColorRole.Button, QColor(51, 51, 55))
    paleta.setColor(QPalette.ColorRole.ButtonText, QColor(220, 220, 220))
    paleta.setColor(QPalette.ColorRole.BrightText, QColor(255, 80, 80))
    paleta.setColor(QPalette.ColorRole.Link, QColor(100, 160, 220))
    paleta.setColor(QPalette.ColorRole.Highlight, QColor(60, 110, 165))
    paleta.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    paleta.setColor(QPalette.ColorRole.PlaceholderText, QColor(150, 150, 150))
    paleta.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(120, 120, 120))
    paleta.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(120, 120, 120))
    paleta.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(120, 120, 120))
    app.setPalette(paleta)


def main():
    migrar_cache_antigo()
    app = QApplication(sys.argv)
    app.setApplicationName("Controle de Empresas")
    app.setStyle("Fusion")
    aplicar_tema_escuro(app)
    janela = MainWindow()
    janela.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()