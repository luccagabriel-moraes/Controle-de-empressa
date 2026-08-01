# 🏢 Controle de Empresas

> Gerenciador de compras e preços por empresa, com Google Sheets como banco de dados e interface gráfica.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![Interface](https://img.shields.io/badge/Interface-PyQt6-41CD52?logo=qt&logoColor=white)
![Banco](https://img.shields.io/badge/Banco-Google%20Sheets-34A853?logo=googlesheets&logoColor=white)
![Uso](https://img.shields.io/badge/Uso-Local-orange)
![Plataforma](https://img.shields.io/badge/Plataforma-Linux%20%7C%20Windows-blue)

## Como funciona

O app não guarda nada localmente — toda leitura e escrita acontece direto no Google Sheets, através de um **Web App do Google Apps Script**.

1. **Selecionar a empresa** — escolha entre os cards de empresas cadastradas.
2. **Ver os produtos** — lista os produtos da empresa, com data e valor da última compra de cada um.
3. **Abrir um produto** — mostra o histórico completo de compras, com total, melhor/pior preço e um mini gráfico de tendência.

Toda alteração (adicionar, editar ou remover uma linha) é enviada em tempo real para a planilha:

| Ação | Requisição | O que acontece |
|---|---|---|
| Abrir empresa/produto | `GET` | Busca os registros na planilha |
| Adicionar / editar e salvar | `POST` (`acao: "salvar"`) | Grava linhas novas e atualiza existentes |
| Remover linha ou produto | `POST` (`acao: "remover"`) | Apaga a linha de verdade, sem deixar espaço em branco |

## Tecnologias

- **Python 3.10+**
- `PyQt6` — interface gráfica
- `urllib` (biblioteca padrão) — comunicação HTTP com o Apps Script
- **Google Apps Script** — Web App que expõe a planilha como uma API simples

## Estrutura

```
controle_empresas.py   # app principal (única fonte de código)
apps_script.gs          # código do Web App (cole no editor do Apps Script)
assets/                 # logos das empresas (opcional)
```

O arquivo principal é organizado em blocos:

1. Configuração (empresas, cores, URL do Web App)
2. Funções utilitárias (formatação de moeda, datas, IDs)
3. Integração com o Google Sheets (`sheets_buscar`, `sheets_salvar`, `sheets_remover`)
4. Avatares circulares das empresas
5. Mini gráfico de tendência de preço
6. Página de compras de um produto
7. Página de lista de produtos de uma empresa
8. Página de seleção de empresa
9. Janela principal

## Como usar

1. Instale a dependência:
   ```bash
   pip install PyQt6
   ```
2. Publique o `apps_script.gs` como Web App no Google Apps Script, com acesso **"Qualquer pessoa"**, e copie a URL gerada (termina em `/exec`).
3. Cole essa URL na constante `GOOGLE_SHEETS_WEBHOOK_URL`, no topo de `controle_empresas.py`.
4. Rode o app:
   ```bash
   python controle_empresas.py
   ```

## Personalização

As empresas exibidas na tela inicial ficam na lista `COMPANIES`, em `controle_empresas.py`. Para cada uma é possível definir:

- `nome` — nome exibido
- `logo` — caminho de uma imagem (ou `None` para usar um ícone/texto)
- `cor` / `cor_texto` — cores de destaque e do texto sobre elas

## Licença

MIT