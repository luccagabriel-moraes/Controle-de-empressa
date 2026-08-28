# 🏢 Controle de Empresas

> Gerenciador de compras e preços por empresa, com Google Sheets como banco de dados e interface gráfica.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![Interface](https://img.shields.io/badge/Interface-PyQt6-41CD52?logo=qt&logoColor=white)
![Banco](https://img.shields.io/badge/Banco-Google%20Sheets-34A853?logo=googlesheets&logoColor=white)
![Uso](https://img.shields.io/badge/Uso-Local-orange)
![Plataforma](https://img.shields.io/badge/Plataforma-Linux%20%7C%20Windows-blue)

## Como funciona

O Google Sheets é a fonte de verdade dos dados — toda leitura e escrita "de verdade" acontece direto na planilha, através de um **Web App do Google Apps Script**. A URL desse Web App (que dá acesso de leitura/escrita à planilha inteira) **não fica no código**: você a configura na primeira vez em **"⚙️ Configurar"**, e ela é gravada em `~/.config/controle_empresas/config.json` (fora do repositório) — ou passada pela variável de ambiente `GOOGLE_SHEETS_WEBHOOK_URL`. O app também mantém um pequeno **cache local em disco** (pasta `cache/`), usado só para a tela aparecer instantaneamente ao abrir uma empresa; ele nunca substitui a planilha, é sempre atualizado a partir dela em segundo plano.

1. **Selecionar a empresa** — escolha entre os cards de empresas cadastradas.
2. **Ver os produtos** — lista os produtos da empresa, com data e valor da última compra de cada um.
3. **Abrir um produto** — mostra o histórico completo de compras, com total, melhor/pior preço e um mini gráfico de tendência.

Cada produto é uma **pasta por tipo** (ex: "Aveia Flocos"), e cada compra dentro dela tem seu próprio campo **Nome** — o texto exato de como veio na nota/marca daquela compra (ex: "Aveia Flocos Marca X" numa linha, "Aveia Flocos Marca Y" em outra, ambas dentro da mesma pasta "Aveia Flocos"). Isso separa "que tipo de produto é" (a pasta) de "qual embalagem/marca foi comprada daquela vez" (o Nome de cada linha).

### 📷 Importar compra de uma foto (IA)

Em vez de digitar a compra na mão, dá pra selecionar uma foto de uma nota impressa/cupom: a imagem é enviada para a **API do Google Gemini**, que lê a nota inteira e devolve os itens já separados (Nome, Data, Quantidade, Preço Unitário) — entendendo o layout da nota e ignorando linhas de total, imposto e dados do estabelecimento. Todo nome lido é padronizado como frase — só a primeira letra maiúscula e o resto minúsculo ("ARROZ TIPO 1 5KG" e "Arroz Tipo 1 5kg" viram os dois "Arroz tipo 1 5kg"), pra lista ficar uniforme —, e itens repetidos com o mesmo nome e o mesmo preço unitário (verduras e carnes pesadas várias vezes na mesma nota) são somados numa linha só, com o peso total. O app então sugere em qual pasta (produto) cada item entra, comparando as palavras do nome lido com as pastas já cadastradas daquela empresa (ex: uma nota "Aveia Flocos Marca X" sugere a pasta "Aveia Flocos", mas não confunde com "Aveia Grão"). Antes de qualquer coisa ir pro Sheets, uma janela mostra os campos reconhecidos pra você conferir e corrigir — inclusive trocar a pasta sugerida ou criar uma nova.

Precisa de uma **chave da API do Google Gemini** (gratuita, criada em [aistudio.google.com/apikey](https://aistudio.google.com/apikey)). No app, clique em **"⚙️ Configurar"**, cole a chave e escolha o modelo (o botão "Buscar modelos" lista os disponíveis para a sua chave; o padrão é um modelo *Flash*, rápido e de baixo custo). A chave fica salva em `~/.config/controle_empresas/config.json` (permissão `600`, fora do repositório) — ou pode ser passada pela variável de ambiente `GEMINI_API_KEY`. Não há OCR local: sem chave configurada, o botão "📷 Importar nota fiscal" abre direto a tela de configuração.

### 🔗 Importar por link do QR code (NFC-e)

As notas de consumidor (NFC-e) trazem um QR code que aponta para a página oficial de consulta da SEFAZ, com **todos os itens, quantidades e preços exatos** — dado mais confiável do que ler a foto. No botão **"🔗 Importar por link"**, escaneie o QR com a câmera do celular, copie o endereço e cole no app: ele baixa essa página, extrai só o texto e manda para a mesma IA, que devolve os itens já estruturados. Cai na mesma tela de conferência da importação por foto.

Alguns estados (Santa Catarina, por exemplo) protegem a consulta pública com um CAPTCHA que o app não consegue passar — nesses casos ele avisa e você usa a importação por foto. Onde o portal não bloqueia (boa parte dos estados), o link funciona direto.

Toda alteração (adicionar, editar ou remover uma linha) é enviada em tempo real para a planilha:

| Ação | Requisição | O que acontece |
|---|---|---|
| Abrir empresa/produto | `GET` | Busca os registros na planilha (via cache de leitura no Apps Script, quando disponível) |
| Adicionar / editar e salvar | `POST` (`acao: "salvar"`) | Grava linhas novas em lote e atualiza as existentes |
| Remover linha ou produto | `POST` (`acao: "remover"`) | Apaga a linha de verdade, sem deixar espaço em branco |

## Usabilidade da tela de compras

- **Preenchimento rápido com Enter:** ao apertar Enter, o foco pula pelos campos na ordem Nome → Data → Quantidade → Preço Unitário — sem precisar clicar em cada um. Em Preço Unitário o Enter só confirma o valor e para ali (não cria uma linha nova).
- **Produto novo começa enxuto:** um produto sem nenhuma compra ainda abre com só 1 linha em branco (em vez de 3) e já é aberto automaticamente assim que criado, sem precisar procurá-lo na lista.
- **Aviso ao sair sem salvar:** se você editou algo na tabela de compras e clicar em "← Voltar" sem ter salvado, o app pede confirmação antes de descartar as alterações.
- **Nomes longos não quebram mais a tela:** títulos e nomes de produto muito grandes são truncados com "..." em vez de desalinhar o layout — passe o mouse por cima para ver o nome completo.

## Desempenho e confiabilidade

- **Cache local (Python):** ao abrir uma empresa, o app mostra na hora os últimos dados salvos em `cache/`, enquanto busca a versão atual do Sheets em segundo plano — sem precisar esperar a rede pra ver algo na tela.
- **Cache de leitura (Apps Script):** o backend guarda a última listagem por 60 segundos, evitando reler a planilha inteira a cada requisição. Qualquer `salvar`/`remover` invalida esse cache na hora, então nunca há dado desatualizado depois de uma alteração.
- **Escrita em lote:** linhas novas são gravadas todas de uma vez, e um índice de IDs é montado uma única vez por requisição — em vez de relerem a planilha item por item, o que pesa bastante em listas grandes.
- **Navegação segura:** cada tela sabe se já foi fechada antes de uma resposta do Sheets chegar, então respostas atrasadas (por exemplo, depois de trocar de produto rapidamente) são simplesmente ignoradas em vez de causar um erro.

## Tecnologias

- **Python 3.10+**
- `PyQt6` — interface gráfica (única dependência externa)
- `urllib` / `json` / `base64` (biblioteca padrão) — HTTP com o Apps Script e com a API do Gemini, cache local em disco
- **Google Apps Script** — Web App que expõe a planilha como uma API simples, com cache e escrita em lote
- **API do Google Gemini** — leitura das notas fiscais fotografadas (visão + saída estruturada)

## Estrutura

```
controle_empresas.py     # app principal (única fonte de código da interface)
apps_script_backend.gs   # código do Web App (cole no editor do Apps Script)
assets/                  # logos das empresas (opcional)
cache/                   # gerado automaticamente — cache local por empresa, pode ser apagado a qualquer momento
~/.config/controle_empresas/config.json   # URL da planilha + chave da API do Gemini + modelo (segredos, fora do repositório)
```

O arquivo principal é organizado em blocos:

1. Configuração (empresas, cores, caminho do `config.json`)
2. Funções utilitárias (formatação de moeda, datas, IDs)
3. Configuração pessoal em disco (`carregar_config`, `salvar_config`, `sheets_webhook_url`, `ia_api_key`, `ia_modelo`)
4. Leitura de nota fiscal com IA — por foto (`ler_nota_fiscal_ia`) ou por link do QR code (`ler_nota_fiscal_link`)
5. Integração com o Google Sheets (`sheets_buscar`, `sheets_salvar`, `sheets_remover`, `sheets_renomear_produtos`)
6. Cache local em disco (`cache_carregar`, `cache_salvar`)
7. Avatares circulares das empresas
8. Mini gráfico de tendência de preço, rótulo elidível (`LabelElidavel`) e tabela com navegação por Enter (`TabelaComNavegacaoEnter`)
9. Diálogo de configuração (`ConfigDialog`)
10. Página de compras de um produto
11. Página de conferência dos itens lidos de uma nota fiscal (`ImportarNotaFiscalPage`)
12. Página de lista de produtos de uma empresa
13. Página de seleção de empresa
14. Janela principal

Documentação completa, função por função (incluindo o backend `.gs`), em [`doc.md`](doc.md).

## Como usar

1. Instale a única dependência:
   ```bash
   pip install PyQt6
   ```
   (Não há outras: a comunicação com o Google Sheets e com a API do Gemini usa só a biblioteca padrão do Python.)
2. Publique o `apps_script_backend.gs` como Web App no Google Apps Script, com acesso **"Qualquer pessoa"**, e copie a URL gerada (termina em `/exec`). Se você já tinha uma implantação publicada antes, edite-a e gere uma **nova versão** em vez de criar uma implantação nova — assim a URL continua a mesma. A planilha ganha a coluna "Nome" sozinha, na primeira requisição depois da nova versão (sem precisar editar a planilha na mão).
3. Rode o app:
   ```bash
   python controle_empresas.py
   ```
4. Abra qualquer empresa, clique em **"⚙️ Configurar"** e cole a URL do passo 2 no campo **"URL da planilha"**. (A URL é um segredo — quem a tem lê e escreve na planilha inteira — por isso não fica no código; ela é gravada em `~/.config/controle_empresas/config.json`, ou pode vir da variável de ambiente `GOOGLE_SHEETS_WEBHOOK_URL`.)
5. (Opcional, só para importar notas fiscais) No mesmo diálogo, cole sua chave da [API do Google Gemini](https://aistudio.google.com/apikey).

## Personalização

As empresas exibidas na tela inicial ficam na lista `COMPANIES`, em `controle_empresas.py`. Para cada uma é possível definir:

- `nome` — nome exibido
- `logo` — caminho de uma imagem (ou `None` para usar um ícone/texto)
- `cor` / `cor_texto` — cores de destaque e do texto sobre elas

No `apps_script_backend.gs`, o tempo de vida do cache de leitura pode ser ajustado na constante `CACHE_SEGUNDOS` (padrão: 60 segundos) — valores maiores reduzem ainda mais as leituras da planilha, mas aumentam o tempo até que uma edição feita direto no Google Sheets (fora do app) apareça para todo mundo.

## Licença

MIT