# Protocolo Égide

Protótipo acadêmico em Flask para demonstrar cadastro institucional, autenticação facial, autorização hierárquica e auditoria. A organização e os registros exibidos são fictícios.

> **Uso exclusivamente acadêmico.** Este projeto não está pronto para produção, não deve ser usado para decisões reais de acesso e não oferece garantia contra fraude, falsos aceites ou falsas rejeições. O desafio de movimento é experimental; não é um sistema anti-spoofing certificado. Use somente dados fictícios nas demonstrações.

## Conteúdo

- [Requisitos](#requisitos)
- [Instalação e execução](#instalação-e-execução)
- [Primeiro administrador](#primeiro-administrador)
- [Fluxos do sistema](#fluxos-do-sistema)
- [Como funciona a biometria](#como-funciona-a-biometria)
- [Avaliação experimental do limiar](#avaliação-experimental-do-limiar)
- [Configuração e proteção de dados](#configuração-e-proteção-de-dados)
- [Rotas principais](#rotas-principais)
- [Arquitetura](#arquitetura)
- [Testes](#testes)
- [Limitações conhecidas](#limitações-conhecidas)

## Requisitos

- Python 3.11 ou superior;
- Git;
- câmera e navegador com suporte a `getUserMedia` (Chrome, Edge ou Firefox atualizados);
- modelos YuNet e SFace do OpenCV Zoo para habilitar as capturas e verificações faciais;
- conexão com a internet para instalar dependências e baixar os modelos.

O banco de dados é SQLite; não é necessário instalar um servidor de banco separado. Em desenvolvimento local, abra o sistema por `http://127.0.0.1:5000` ou `http://localhost:5000`, origens tratadas pelos navegadores como contexto seguro para acesso à câmera.

## Instalação e execução

Os comandos de aplicação, testes e administração devem ser executados com a `.venv` deste projeto. Ative o ambiente no terminal antes de instalar pacotes ou executar o sistema.

### 1. Obter o projeto e criar a `.venv`

```bash
git clone <URL-DO-REPOSITORIO>
cd sistema-biometrico
```

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Se o PowerShell bloquear a ativação, use uma política restrita ao usuário atual:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Depois de ativar, confirme que o prompt mostra `(.venv)` e instale as dependências **dentro do ambiente**:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 2. Instalar os modelos faciais

Crie `data/models/` na raiz do projeto e coloque nela estes arquivos:

```text
data/models/
├── face_detection_yunet_2023mar.onnx
└── face_recognition_sface_2021dec.onnx
```

Linux/macOS:

```bash
mkdir -p data/models
curl -L "https://github.com/opencv/opencv_zoo/raw/refs/heads/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx" \
  -o data/models/face_detection_yunet_2023mar.onnx
curl -L "https://github.com/opencv/opencv_zoo/raw/refs/heads/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx" \
  -o data/models/face_recognition_sface_2021dec.onnx
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force data\models
Invoke-WebRequest "https://github.com/opencv/opencv_zoo/raw/refs/heads/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx" -OutFile "data\models\face_detection_yunet_2023mar.onnx"
Invoke-WebRequest "https://github.com/opencv/opencv_zoo/raw/refs/heads/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx" -OutFile "data\models\face_recognition_sface_2021dec.onnx"
```

Confira os nomes e extensões: arquivos de backup, como `.onnx~`, não são carregados. Os modelos são fornecidos pelo [OpenCV Zoo](https://github.com/opencv/opencv_zoo); consulte as licenças e condições dos modelos antes de redistribuí-los. A pasta `data/models/` e os arquivos `.onnx` não devem ser enviados ao Git.

Sem os modelos, a interface continua disponível, mas as operações biométricas ficam indisponíveis e não concedem acesso.

### 3. Criar o primeiro administrador

Com a `.venv` ativada, execute em um terminal:

```bash
flask --app app provision-admin
```

O comando solicita nome, e-mail institucional e senha. Use o domínio `@egíde.com.br` e uma senha com pelo menos 12 caracteres. Não existe senha ou conta administrativa padrão. O comando cria apenas o primeiro administrador e falha se já houver um administrador aprovado.

A conta recebe matrícula gerada pelo sistema. No primeiro login, o administrador deverá concluir o cadastro facial antes de usar as telas protegidas.

### 4. Iniciar o servidor local

Com a `.venv` ainda ativada:

```bash
flask --app app run --host 127.0.0.1 --port 5000
```

Abra <http://127.0.0.1:5000>. A aplicação cria o SQLite em `database/egide.db` e inicializa o schema na primeira execução. Antes de atualizar um banco já existente, faça uma cópia de segurança.

Para parar o servidor, pressione `Ctrl+C`. Se iniciar um segundo terminal para executar comandos do projeto, ative nele a mesma `.venv`.

## Primeiro acesso e administração

- **Cadastro público:** a pessoa informa dados pessoais, e-mail institucional, senha e consentimento biométrico. Não escolhe cargo, nível, área, equipe, matrícula ou superior.
- **Cadastro facial:** são solicitadas capturas frontal, direita e esquerda. A solicitação permanece pendente até revisão administrativa.
- **Aprovação:** um administrador analisa a foto e o cadastro, seleciona cargo, área, equipe e superior na seção **Delegação Institucional**, e aprova ou rejeita. O nível é derivado do cargo e a matrícula é criada pelo sistema.
- **Edição institucional:** administradores podem editar os dados e a delegação de usuários. O servidor valida novamente as relações de cargo, área, equipe e superior.
- **Organograma:** em **Administração → Usuários → Organograma Institucional**, ou diretamente em `/admin/usuarios?view=chart`. A árvore usa as relações persistidas de superior e subordinado.
- **Auditoria:** administradores consultam eventos e filtros em **Administração → Auditoria**. Os scores faciais também são registrados; são dados sensíveis e não representam uma probabilidade de identidade.
- **Usuário aprovado:** após autenticar-se, pode consultar seu painel, perfil e registros fictícios permitidos pelo nível atribuído.

Áreas, equipes, cargos e relações hierárquicas iniciais são registros controlados no banco. O sistema filtra equipes pela área e valida no servidor que a combinação é válida. A interface administrativa de aprovação/edição não permite cadastrar novas áreas ou equipes.

## Como funciona a biometria

### Cadastro

1. YuNet detecta o rosto e seus pontos de referência.
2. O sistema exige um único rosto e verifica condições básicas de imagem, confiança e orientação.
3. SFace alinha o rosto, extrai um embedding e o normaliza.
4. São registrados três templates: frontal, direita e esquerda. A foto frontal é guardada separadamente para consulta administrativa; as capturas laterais não são mantidas como fotos.

### Autenticação facial

Depois de validar matrícula e senha, o servidor gera uma sequência aleatória de três movimentos para a direita ou esquerda. Para cada captura, o servidor verifica imagem, detecção de um único rosto e orientação aproximada pelos landmarks de YuNet. Com o desafio aceito, a captura frontal atual é convertida em embedding SFace e comparada com os três templates cadastrados pela similaridade do cosseno:

```text
S = max(
    cosine(E_atual, E_frontal),
    cosine(E_atual, E_direita),
    cosine(E_atual, E_esquerda)
)

aceitar se S >= threshold
```

O limiar padrão é `0.363`. O resultado, os três scores, o máximo e o limiar são gravados na auditoria. Um administrador recém-provisionado passa por uma configuração inicial dos três templates no primeiro login; os demais usuários precisam ter o perfil biométrico completo.

O desafio de movimento é uma **prova de presença experimental**. Ele dificulta aceitar uma única imagem estática sem resposta ao desafio, mas não prova resistência a vídeo, reprodução em tela, deepfake ou outros ataques. Não equivale a liveness/anti-spoofing certificado.

## Avaliação experimental do limiar

O limiar `0.363` é um parâmetro experimental, não um valor universal. A ferramenta local calcula FAR (falsa aceitação), FRR (falsa rejeição) e uma estimativa discreta de EER a partir de scores rotulados.

Prepare um CSV com scores de comparações genuínas (mesma pessoa) e impostoras (pessoas diferentes):

```csv
pair_type,score
genuine,0.421
genuine,0.387
impostor,0.291
impostor,0.352
```

Execute dentro da `.venv`, a partir da raiz do repositório:

```bash
python -m scripts.evaluate_face_threshold dados_scores.csv --threshold 0.363
```

A regra usada é `score >= threshold` para aceitar; portanto, FAR é a fração dos impostores acima ou igual ao limiar, e FRR é a fração dos genuínos abaixo dele. O EER reportado é uma aproximação por busca em thresholds discretos, não uma certificação. Para uma avaliação acadêmica defensável, colete os scores com consentimento, não inclua imagens ou dados identificáveis no CSV, separe pessoas/sessões entre calibração e avaliação e descreva tamanho e limitações da amostra.

## Configuração e proteção de dados

### Variáveis de ambiente

| Variável | Finalidade | Padrão |
| --- | --- | --- |
| `EGIDE_SECRET_KEY` | Assinatura das sessões Flask | Chave local de desenvolvimento |
| `EGIDE_DATA_ENCRYPTION_KEY` | Chave Fernet para dados sensíveis | Derivada da chave Flask apenas no modo local |
| `EGIDE_DEBUG` | Modo de desenvolvimento | `1` |
| `EGIDE_YUNET_MODEL` | Caminho alternativo do modelo YuNet | `data/models/face_detection_yunet_2023mar.onnx` |
| `EGIDE_SFACE_MODEL` | Caminho alternativo do modelo SFace | `data/models/face_recognition_sface_2021dec.onnx` |
| `EGIDE_FACE_THRESHOLD` | Limiar de similaridade facial | `0.363` |

Exemplo de geração de uma chave Fernet, executado dentro da `.venv`:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Configure as variáveis no ambiente do processo antes de iniciar o servidor. Não armazene chaves no código ou no Git. Quando `EGIDE_DEBUG=0`, a aplicação exige `EGIDE_SECRET_KEY` e `EGIDE_DATA_ENCRYPTION_KEY`; use também HTTPS e um servidor WSGI apropriado antes de qualquer implantação. `flask run` é o servidor de desenvolvimento e não deve ser exposto à internet.

Trocar ou perder a chave Fernet impede descriptografar os dados existentes. Planeje backup protegido e recuperação de chave; não troque a chave sem um procedimento de migração dos dados.

### Dados armazenados

- senhas: hash `scrypt` do Werkzeug;
- CPF e RG: criptografados com Fernet; o CPF também possui um HMAC para verificação de unicidade;
- embeddings faciais e foto frontal: criptografados antes de persistir;
- eventos de autenticação e ações administrativas: persistidos para auditoria;
- banco: SQLite em `database/egide.db`, com chaves estrangeiras e modo WAL.

Sessões usam cookies `HttpOnly` e `SameSite=Lax`; com debug desativado, o cookie é configurado como `Secure`. Operações de alteração exigem CSRF. O consentimento biométrico é registrado no cadastro. Os dados são demonstração: defina retenção, remoção, backups e controle de acesso antes de usar qualquer dado real; este protótipo não oferece um processo institucional completo de gestão de dados biométricos.

## Rotas principais

| Uso | Rotas |
| --- | --- |
| Páginas públicas | `/`, `/cadastro`, `/cadastro/biometria`, `/cadastro/concluido` |
| Autenticação | `/login`, `/autenticacao`, `POST /logout` |
| Biometria | `POST /api/biometrics/enroll`, `POST /api/auth/face`, `POST /api/biometrics/admin-setup` |
| Área do usuário | `/painel`, `/perfil`, `/toxinas`, `/toxinas/<id>` |
| API de recursos | `GET /api/toxins`, `POST /api/access/<id>` |
| Administração | `/admin/`, `/admin/solicitacoes`, `/admin/solicitacoes/<id>`, `/admin/usuarios`, `/admin/usuarios/<id>`, `/admin/acessos` |
| API administrativa | `GET /admin/api/resumo`, `GET /admin/api/acessos` |

Rotas administrativas verificam sessão e papel no servidor. APIs e formulários não substituem a validação de autorização feita pelo backend.

## Arquitetura

```text
app.py                    fábrica Flask, sessão, CSRF e CLI
biometric/                detector YuNet e integração SFace
config/                   configuração e caminhos
database/                 schema SQLite, seed e migrações
models/                   estruturas de usuário e organização
routes/                   páginas e APIs públicas, de usuário e administrativas
services/                 autenticação, biometria, organização, acesso e auditoria
scripts/                  ferramentas locais, incluindo avaliação do limiar
templates/                templates Jinja, incluindo áreas pública e administrativa
static/css/               identidade visual, temas e responsividade
static/js/                formulários, organização e captura de câmera
tests/                    testes automatizados
data/models/              arquivos ONNX locais (não versionados)
```

O tema claro/escuro é controlado no navegador e a preferência fica em `localStorage`. A navegação autenticada usa uma barra lateral responsiva; as páginas públicas mantêm navegação própria.

## Testes

Ative a `.venv` e execute da raiz do repositório:

```bash
python -m pytest -q
python -m compileall -q app.py biometric config database models routes services tests scripts
python -m pip check
node --check static/js/forms.js
node --check static/js/organization.js
node --check static/js/camera.js
git diff --check
```

Os testes automatizados cobrem validações, estados de usuário, matrícula, delegação e hierarquia, autenticação, auditoria, rotas administrativas, CSRF, autorização, persistência e métricas biométricas. Eles não substituem testes de câmera em dispositivos reais, avaliação de FAR/FRR com dados representativos, revisão independente de segurança ou certificação biométrica.

## Limitações conhecidas

- O threshold não foi calibrado com uma amostra representativa independente.
- A prova de presença usa movimentos orientados por landmarks e não é liveness certificado.
- CPF exige 11 dígitos, mas os dígitos verificadores não são validados.
- O projeto não é adequado a dados reais ou uso em produção.
- O catálogo e os níveis são fictícios; os registros não descrevem conteúdo operacional.
- O catálogo de áreas/equipes é inicializado pelo banco; a interface atual não oferece gerenciamento desse catálogo.
- Esta aplicação não documenta nem fornece uma política operacional de retenção, resposta a incidentes ou recuperação institucional de chaves.

## Arquivos locais e Git

Não versione `.venv/`, bancos SQLite locais, dados faciais, modelos ONNX ou segredos. O `.gitignore` do projeto já cobre os principais artefatos locais. Antes de compartilhar alterações, confira:

```bash
git status --short
```

## Aviso acadêmico

O Protocolo Égide destina-se somente a demonstração, estudo e desenvolvimento acadêmico. Não o utilize para identificação de pessoas, vigilância, investigação, controle de acesso real ou decisões que possam produzir consequências para indivíduos. Não utilize imagens faciais, documentos ou outros dados pessoais reais nas demonstrações.
