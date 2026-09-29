# Protocolo Égide

Protótipo acadêmico de identificação e autenticação biométrica facial, níveis de autorização e auditoria para registros inteiramente fictícios.

A entidade, os níveis, os registros e o catálogo apresentados no sistema são cenográficos e não representam um órgão, instituição ou conteúdo real.

> **Limites:** este projeto não é apropriado para produção ou decisões reais de segurança. Não possui prova de vida, não foi submetido a avaliação independente e não oferece garantia contra fraude, falsos positivos ou falsos negativos. Não use dados pessoais reais nas demonstrações.

## Requisitos

- Python 3.11 ou superior;
- Git;
- câmera e navegador compatível com `getUserMedia`;
- Windows, Linux ou macOS;
- os modelos YuNet e SFace do OpenCV Zoo para habilitar a biometria;
- conexão com a internet durante a instalação das dependências e dos modelos.

O projeto utiliza SQLite, portanto não é necessário instalar um servidor de banco de dados separado.

### Navegador

A captura biométrica utiliza a câmera do navegador por meio de `getUserMedia`.

Como o sistema é executado localmente, `localhost`/`127.0.0.1` é tratado pelo navegador como contexto seguro para esse recurso.

Recomenda-se utilizar uma versão atualizada de:

- Google Chrome;
- Microsoft Edge;
- Mozilla Firefox.

---

## 1. Clonar o projeto

Clone o repositório e entre na pasta do projeto:

```bash
git clone <URL-DO-REPOSITORIO>
cd sistema-biometrico
```

Substitua `<URL-DO-REPOSITORIO>` pela URL do repositório.

---

# 2. Criar o ambiente virtual

Todos os comandos Python da aplicação, dos testes e da administração devem utilizar o ambiente virtual `.venv`.

## Windows — PowerShell

Crie o ambiente virtual:

```powershell
py -3 -m venv .venv
```

Ative:

```powershell
.\.venv\Scripts\Activate.ps1
```

Depois de ativado, o terminal deverá mostrar algo semelhante a:

```text
(.venv) PS C:\...\sistema-biometrico>
```

Atualize o `pip` e instale as dependências:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Se o PowerShell bloquear a ativação

Em algumas instalações do Windows, a política de execução pode impedir scripts locais.

Nesse caso, execute:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Feche e abra o PowerShell novamente e tente:

```powershell
.\.venv\Scripts\Activate.ps1
```

Alternativamente, o projeto pode ser executado sem ativar o ambiente virtual, utilizando diretamente:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

e:

```powershell
.\.venv\Scripts\flask.exe --app app run --host 127.0.0.1 --port 5000
```

---

## Linux / macOS

Crie o ambiente virtual:

```bash
python3 -m venv .venv
```

Ative:

```bash
source .venv/bin/activate
```

Atualize o `pip` e instale as dependências:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Também é possível executar os comandos diretamente pelo ambiente virtual, sem ativá-lo:

```bash
.venv/bin/python -m pip install -r requirements.txt
```

---

# 3. Instalar os modelos de biometria

O Protocolo Égide utiliza:

- YuNet para detecção facial;
- SFace para extração e comparação de representações faciais.

Os modelos são obtidos do [OpenCV Zoo](https://github.com/opencv/opencv_zoo).

Antes de redistribuir os modelos junto com o projeto, confira a licença publicada para cada arquivo.

Os arquivos devem ficar exatamente em:

```text
data/
└── models/
    ├── face_detection_yunet_2023mar.onnx
    └── face_recognition_sface_2021dec.onnx
```

A pasta `data/models/` fica fora do controle de versão.

## Windows

Crie a pasta:

```powershell
New-Item -ItemType Directory -Force data\models
```

Depois baixe os dois modelos do OpenCV Zoo.

### YuNet

```powershell
Invoke-WebRequest `
  -Uri "https://github.com/opencv/opencv_zoo/raw/refs/heads/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx" `
  -OutFile "data\models\face_detection_yunet_2023mar.onnx"
```

### SFace

```powershell
Invoke-WebRequest `
  -Uri "https://github.com/opencv/opencv_zoo/raw/refs/heads/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx" `
  -OutFile "data\models\face_recognition_sface_2021dec.onnx"
```

Você também pode baixar os arquivos manualmente pelo navegador e copiá-los para `data\models\`.

## Linux / macOS

Crie a pasta:

```bash
mkdir -p data/models
```

Baixe os modelos:

```bash
curl -L https://github.com/opencv/opencv_zoo/raw/refs/heads/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx \
  -o data/models/face_detection_yunet_2023mar.onnx

curl -L https://github.com/opencv/opencv_zoo/raw/refs/heads/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx \
  -o data/models/face_recognition_sface_2021dec.onnx
```

### Nomes dos arquivos

Os nomes precisam terminar exatamente em `.onnx`:

```text
face_detection_yunet_2023mar.onnx
face_recognition_sface_2021dec.onnx
```

Alguns editores criam arquivos de backup com nomes como:

```text
face_recognition_sface_2021dec.onnx~
```

Esses arquivos **não são modelos válidos** e não são reconhecidos pela configuração padrão.

Os modelos também precisam estar dentro de `data/models/` da mesma pasta do projeto usada para iniciar o Flask.

Depois de adicionar ou renomear os modelos, atualize a página de captura. Se o servidor já estiver executando, reinicie-o caso necessário.

Sem os modelos instalados, as páginas continuam disponíveis, mas as operações de captura e autenticação biométrica falham explicitamente e não concedem acesso.

---

# 4. Verificar a instalação

Com o ambiente virtual ativado, você pode verificar se as principais dependências estão instaladas:

```bash
python -m pip check
```

Também é possível verificar a versão do Python:

### Windows

```powershell
python --version
```

### Linux / macOS

```bash
python --version
```

A versão deve ser Python 3.11 ou superior.

---

# 5. Inicializar o banco e executar o sistema

O banco SQLite é criado automaticamente na primeira execução.

O projeto utiliza:

```text
database/egide.db
```

Ao iniciar, o sistema inicializa o schema e aplica as migrações necessárias ao banco legado sem apagar os registros existentes.

> Faça uma cópia de segurança de `database/egide.db` antes de atualizar uma instalação existente.

## Windows

Com o ambiente virtual ativado:

```powershell
flask --app app run --host 127.0.0.1 --port 5000
```

Ou, sem ativar o ambiente:

```powershell
.\.venv\Scripts\flask.exe --app app run --host 127.0.0.1 --port 5000
```

## Linux / macOS

Com o ambiente virtual ativado:

```bash
flask --app app run --host 127.0.0.1 --port 5000
```

Ou, sem ativar:

```bash
.venv/bin/flask --app app run --host 127.0.0.1 --port 5000
```

Depois, abra no navegador:

```text
http://127.0.0.1:5000
```

---

# 6. Primeiro administrador

Não existe administrador ou senha padrão.

Com o servidor parado ou em outro terminal, execute:

## Windows

```powershell
flask --app app provision-admin
```

Sem ativar o ambiente:

```powershell
.\.venv\Scripts\flask.exe --app app provision-admin
```

## Linux / macOS

```bash
flask --app app provision-admin
```

Sem ativar o ambiente:

```bash
.venv/bin/flask --app app provision-admin
```

O comando solicita interativamente os dados necessários e cria uma única conta administrativa aprovada.

A conta possui:

- senha armazenada por hash;
- matrícula gerada pelo servidor;
- papel administrativo;
- nenhum perfil facial inicialmente cadastrado.

No primeiro login com matrícula e senha, o administrador deverá completar as três capturas biométricas.

O comando é recusado quando já existe um administrador aprovado.

---

# 7. Chaves e execução fora do modo local

O desenvolvimento local utiliza valores de conveniência. Esses valores não devem ser reutilizados em ambientes compartilhados.

Para execução fora do modo local, configure:

```text
EGIDE_SECRET_KEY
EGIDE_DATA_ENCRYPTION_KEY
EGIDE_DEBUG=0
```

A `EGIDE_DATA_ENCRYPTION_KEY` deve ser uma chave Fernet utilizada para criptografar CPF, RG e representações biométricas.

Mantenha essas chaves fora do repositório.

> Perder ou trocar a chave de criptografia impossibilita a descriptografia dos dados protegidos por ela.

Também utilize HTTPS quando o sistema for executado fora do ambiente local, especialmente para habilitar o comportamento seguro dos cookies.

## Gerar uma chave Fernet

### Windows

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Linux / macOS

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

---

# 8. Configurações opcionais

É possível substituir os valores padrão por variáveis de ambiente.

```text
EGIDE_YUNET_MODEL
EGIDE_SFACE_MODEL
EGIDE_FACE_THRESHOLD
```

Por exemplo:

```text
EGIDE_YUNET_MODEL=data/models/face_detection_yunet_2023mar.onnx
EGIDE_SFACE_MODEL=data/models/face_recognition_sface_2021dec.onnx
EGIDE_FACE_THRESHOLD=0.363
```

O limiar padrão é `0.363`.

Esse valor deve ser validado em dados de avaliação apropriados ao contexto acadêmico. Ele não representa uma taxa de erro nem uma garantia de desempenho biométrico.

---

# 9. Fluxos implementados

### Cadastro público

Validação de nome, data, CPF, e-mail, senha e nível; hash de senha; criptografia de CPF/RG; geração transacional de matrícula (`Xnnn`, `Ynnn`, `Znnn`) e criação da conta em estado `PENDING`.

### Biometria de cadastro

Utiliza a câmera do navegador para três orientações guiadas.

O processo inclui:

- detecção de um único rosto;
- verificações básicas de qualidade e posição;
- alinhamento;
- extração de embeddings com YuNet/SFace.

As imagens capturadas são processadas em memória e descartadas. Os templates biométricos são criptografados antes de serem persistidos.

### Aprovação

A área administrativa exige uma sessão aprovada e o papel `ADMIN`.

Uma solicitação só pode ser aprovada após a existência dos três templates faciais.

Rejeições exigem justificativa e as ações administrativas são auditadas.

### Login

O usuário informa matrícula e senha.

A conta precisa estar no estado `APPROVED`. Em seguida, ocorre a comparação facial.

A sessão autenticada somente é criada após a confirmação necessária.

A biometria identifica o usuário, mas não determina diretamente suas permissões.

### Autorização

Cada consulta protegida é verificada no backend utilizando a relação:

```text
nível do usuário >= nível do recurso
```

Tentativas de acessar recursos acima do nível autorizado são negadas e registradas sem expor os detalhes protegidos.

### Administração e auditoria

A área administrativa oferece:

- pesquisa de usuários;
- filtros;
- alteração de nível sem troca de matrícula;
- suspensão com motivo;
- desativação lógica;
- monitoramento;
- filtros de eventos;
- auditoria de ações administrativas.

Os 15 registros do catálogo são fictícios. Suas descrições não fornecem dados químicos, instruções de síntese, aquisição ou uso.

---

# 10. Arquitetura

```text
app.py
├── routes/
│   ├── páginas públicas
│   ├── autenticação
│   └── administração
│
├── services/
│   ├── validação
│   ├── autenticação
│   ├── autorização
│   ├── biometria
│   └── auditoria
│
├── database/
│   └── database.py
│
├── models/
│   ├── identidade/status
│   └── níveis
│
├── biometric/
│   ├── YuNet
│   └── SFace
│
├── templates/
├── static/
│   ├── css/
│   └── js/
│
├── data/
│   └── models/
│
└── tests/
```

### Principais responsabilidades

`app.py` contém a fábrica Flask, sessão, proteção CSRF, tratamento de erros e o comando inicial de provisionamento.

`routes/` contém as páginas e APIs públicas, de autenticação e administrativas.

`services/` concentra validação, autenticação, autorização, biometria e auditoria.

`database/database.py` contém o schema SQLite, índices e migração do banco legado.

`models/` contém estruturas relacionadas à identidade, status e níveis.

`biometric/` utiliza YuNet para detecção facial e SFace para alinhamento, extração e comparação.

`templates/`, `static/css/` e `static/js/` contêm a interface HTML, CSS e JavaScript.

---

# 11. Banco de dados e proteção dos dados

O SQLite persiste:

- usuários;
- contadores transacionais de matrícula;
- templates biométricos;
- níveis;
- registros fictícios;
- eventos de acesso;
- ações administrativas.

Senhas utilizam o hash `scrypt` do Werkzeug.

CPF, RG e embeddings biométricos utilizam Fernet.

O CPF também possui um HMAC para permitir verificação de unicidade sem manter o valor em texto claro para essa finalidade.

As sessões utilizam cookies `HTTP-only` e `SameSite=Lax`.

Operações de alteração exigem token CSRF.

---

# 12. Rotas principais

| Área                   | Rotas                                                                                         |
| ---------------------- | --------------------------------------------------------------------------------------------- |
| Institucional/cadastro | `/`, `/cadastro`, `/cadastro/biometria`                                                       |
| Autenticação           | `/login`, `/autenticacao`, `/logout`                                                          |
| Biometria              | `POST /api/biometrics/enroll`, `POST /api/auth/face`                                          |
| Usuário/recursos       | `/painel`, `/perfil`, `/toxinas`, `/toxinas/<id>`, `GET /api/toxins`, `POST /api/access/<id>` |
| Administração          | `/admin/`, `/admin/solicitacoes`, `/admin/usuarios`, `/admin/acessos`                         |
| APIs administrativas   | `GET /admin/api/resumo`, `GET /admin/api/acessos`                                             |

Rotas de alteração exigem CSRF.

As rotas administrativas verificam a sessão e o papel do usuário no servidor e não são disponibilizadas a usuários comuns.

---

# 13. Testes e verificação

Execute os comandos pelo ambiente virtual.

## Windows

Com o ambiente ativado:

```powershell
python -m pytest -q
python -m compileall -q app.py biometric config database models routes services tests
python -m pip check
```

Sem ativar:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q app.py biometric config database models routes services tests
.\.venv\Scripts\python.exe -m pip check
```

## Linux / macOS

Com o ambiente ativado:

```bash
python -m pytest -q
python -m compileall -q app.py biometric config database models routes services tests
python -m pip check
```

Sem ativar:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q app.py biometric config database models routes services tests
.venv/bin/python -m pip check
```

Os testes cobrem:

- hierarquia de níveis;
- migração do banco;
- cadastro e matrículas;
- aprovação;
- auditoria;
- proteção CSRF;
- estados de conta;
- login;
- rotas administrativas;
- bloqueio de recursos.

O pipeline de visão computacional requer câmera, modelos e avaliação manual adicional.

Os testes automatizados não devem ser interpretados como validação biométrica, prova de vida ou certificação de segurança.

---

# 14. Arquivos que não devem ser versionados

Os modelos ONNX, banco local, ambiente virtual e caches Python não devem ser enviados ao Git.

Exemplo de `.gitignore`:

```gitignore
# Ambiente virtual
.venv/

# Cache Python
__pycache__/
*.pyc
.pytest_cache/

# Banco local
*.db
*.sqlite
*.sqlite3

# Modelos de visão computacional
*.onnx
*.onnx~

# Arquivos de configuração local
.env
.env.*

# Backups de editores
*~
```

Se um modelo já tiver sido adicionado ao Git anteriormente, apenas adicionar `.onnx` ao `.gitignore` não é suficiente.

Nesse caso, remova-o do índice sem apagar o arquivo local:

```bash
git rm --cached caminho/para/modelo.onnx
```

Depois:

```bash
git status
```

---

# 15. Estrutura esperada após a instalação

A estrutura mínima esperada é:

```text
sistema-biometrico/
│
├── app.py
├── requirements.txt
├── README.md
├── .gitignore
│
├── biometric/
├── config/
├── database/
├── models/
├── routes/
├── services/
├── templates/
├── static/
├── tests/
│
├── data/
│   └── models/
│       ├── face_detection_yunet_2023mar.onnx
│       └── face_recognition_sface_2021dec.onnx
│
├── database/
│   └── egide.db
│
└── .venv/
```

`database/egide.db` e `.venv/` são criados localmente e não devem ser versionados.

---

# 16. Início rápido

Para uma instalação nova:

### Windows PowerShell

```powershell
git clone <URL-DO-REPOSITORIO>
cd sistema-biometrico

py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

New-Item -ItemType Directory -Force data\models
```

Baixe os dois modelos para `data\models\`, depois:

```powershell
flask --app app run --host 127.0.0.1 --port 5000
```

Em outro terminal:

```powershell
.\.venv\Scripts\flask.exe --app app provision-admin
```

Acesse:

```text
http://127.0.0.1:5000
```

### Linux / macOS

```bash
git clone <URL-DO-REPOSITORIO>
cd sistema-biometrico

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

mkdir -p data/models
```

Baixe os dois modelos para `data/models/` e execute:

```bash
flask --app app run --host 127.0.0.1 --port 5000
```

Em outro terminal:

```bash
.venv/bin/flask --app app provision-admin
```

Acesse:

```text
http://127.0.0.1:5000
```

---

## Aviso acadêmico

O Protocolo Égide é um protótipo acadêmico destinado exclusivamente a demonstração, estudo e desenvolvimento.

A implementação não deve ser utilizada para controle de acesso real, identificação de pessoas, decisões administrativas, investigação, vigilância ou qualquer outra finalidade que possa produzir consequências reais para indivíduos.

Não utilize dados pessoais, documentos ou imagens faciais reais durante as demonstrações.
