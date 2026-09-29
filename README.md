# Protocolo Égide

Protótipo acadêmico de identificação e autenticação biométrica facial, níveis de autorização e auditoria para registros inteiramente fictícios. A entidade e os dados cenográficos não representam um órgão ou conteúdo real.

> **Limites:** este projeto não é apropriado para produção ou decisões reais de segurança. Não possui prova de vida, não foi submetido a avaliação independente e não oferece garantia contra fraude, falsos positivos ou falsos negativos. Não use dados pessoais reais nas demonstrações.

## Requisitos

- Linux e Python 3.11 ou superior;
- câmera e navegador com `getUserMedia` (localhost é tratado como contexto seguro);
- os modelos faciais YuNet e SFace do OpenCV Zoo para habilitar a biometria.

## Instalação em ambiente virtual

Todos os comandos Python da aplicação, dos testes e da administração devem usar `.venv`.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

Baixe os modelos ONNX do [OpenCV Zoo](https://github.com/opencv/opencv_zoo) e confira a licença publicada para cada modelo antes de redistribuí-los:

```bash
mkdir -p data/models
curl -L https://github.com/opencv/opencv_zoo/raw/refs/heads/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx -o data/models/face_detection_yunet_2023mar.onnx
curl -L https://github.com/opencv/opencv_zoo/raw/refs/heads/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx -o data/models/face_recognition_sface_2021dec.onnx
```

Os arquivos ficam em `data/models/`, fora do controle de versão. Sem os modelos instalados, as páginas continuam disponíveis, mas captura e autenticação biométrica falham de forma explícita e não concedem acesso.

Os nomes precisam terminar exatamente em `.onnx`: `face_detection_yunet_2023mar.onnx` e `face_recognition_sface_2021dec.onnx`. Alguns editores deixam cópias de segurança terminadas em `.onnx~`; essas cópias não são encontradas pela configuração. Os modelos também precisam ficar dentro de `data/models/` da mesma pasta de projeto usada para iniciar o Flask. Depois de copiá-los ou renomeá-los, atualize a página de captura e, se necessário, reinicie o servidor.

Crie o banco SQLite e inicie o servidor local:

```bash
.venv/bin/flask --app app run --host 127.0.0.1 --port 5000
```

Abra `http://127.0.0.1:5000`. O schema é inicializado na primeira execução e as migrações são aplicadas ao banco legado `database/egide.db`, sem apagar os registros existentes. Faça uma cópia de segurança do banco antes de atualizar uma instalação existente.

### Primeiro administrador

Não há administrador ou senha padrão. Em outro terminal, execute o comando administrativo e siga as solicitações interativas:

```bash
.venv/bin/flask --app app provision-admin
```

O comando cria uma única conta administrativa aprovada, com senha armazenada por hash, matrícula gerada no servidor e sem perfil facial. No primeiro login com matrícula e senha, o administrador deverá completar três capturas biométricas. O comando é recusado quando já há um administrador aprovado.

### Chaves e execução fora do modo local

O desenvolvimento local usa valores de conveniência; eles não devem ser reutilizados em ambientes compartilhados. Para executar fora do modo debug, defina `EGIDE_SECRET_KEY` e `EGIDE_DATA_ENCRYPTION_KEY`. Gere uma chave Fernet para criptografia de CPF, RG e representações biométricas e mantenha-a fora do repositório. Perder ou trocar a chave impossibilita descriptografar esses dados. Também configure `EGIDE_DEBUG=0` e use HTTPS para habilitar cookies `Secure`.

Exemplo para criar uma chave Fernet:

```bash
.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Defina `EGIDE_YUNET_MODEL`, `EGIDE_SFACE_MODEL` ou `EGIDE_FACE_THRESHOLD` para substituir os caminhos e o limiar padrão (`0.363`). Esse limiar deve ser validado em dados de avaliação apropriados ao contexto acadêmico; não representa uma taxa de erro ou uma garantia de desempenho.

## Fluxos implementados

1. **Cadastro público:** validação de nome, data, CPF, e-mail, senha e nível; hash de senha; criptografia de CPF/RG; geração transacional de matrícula (`Xnnn`, `Ynnn`, `Znnn`); criação em estado `PENDING`.
2. **Biometria de cadastro:** câmera do navegador, três orientações guiadas, detecção de um único rosto, verificações básicas de qualidade e posição, alinhamento e extração de embeddings YuNet/SFace. As capturas são processadas em memória e descartadas; os templates são criptografados antes de persistir.
3. **Aprovação:** a área administrativa exige sessão aprovada e papel `ADMIN`; só é possível aprovar após três templates faciais. Rejeição exige justificativa. As ações são auditadas.
4. **Login:** matrícula e senha; status precisa estar `APPROVED`; comparação facial subsequente; sessão autenticada somente após a confirmação. A biometria identifica, mas não decide permissões.
5. **Autorização:** cada consulta é conferida no backend com `nível do usuário >= nível do recurso`. Tentativas de nível superior são negadas e registradas sem expor os detalhes protegidos.
6. **Administração e auditoria:** pesquisa e filtros de usuários, alteração de nível sem trocar matrícula, suspensão com motivo, desativação lógica, monitoramento e filtros de eventos.

Os 15 registros do catálogo são fictícios e suas descrições não fornecem dados químicos, instruções de síntese, aquisição ou uso.

## Arquitetura

- `app.py`: fábrica Flask, sessão, proteção CSRF, tratamento de erros e comando inicial de provisionamento;
- `routes/`: páginas e APIs públicas, de autenticação e administrativas;
- `services/`: validação, autenticação, autorização, biometria e auditoria;
- `database/database.py`: schema SQLite, índices e migração legada;
- `models/`: identidade/status e níveis;
- `biometric/`: YuNet para detecção e SFace para alinhamento/extração/comparação;
- `templates/`, `static/css/` e `static/js/`: interface responsiva HTML/CSS/JavaScript.

SQLite persiste usuários, contadores transacionais de matrícula, templates biométricos, níveis, registros fictícios, eventos de acesso e ações administrativas. Senhas usam o hash `scrypt` do Werkzeug. CPF/RG e embeddings usam Fernet; CPF também tem um HMAC para unicidade sem índice em texto claro. Sessões usam cookie HTTP-only e `SameSite=Lax`; mutações exigem token CSRF.

## Rotas principais

| Área | Rotas |
|---|---|
| Institucional/cadastro | `/`, `/cadastro`, `/cadastro/biometria` |
| Autenticação | `/login`, `/autenticacao`, `/logout` |
| Biometria | `POST /api/biometrics/enroll`, `POST /api/auth/face` |
| Usuário/recursos | `/painel`, `/perfil`, `/toxinas`, `/toxinas/<id>`, `GET /api/toxins`, `POST /api/access/<id>` |
| Administração | `/admin/`, `/admin/solicitacoes`, `/admin/usuarios`, `/admin/acessos` |
| APIs administrativas | `GET /admin/api/resumo`, `GET /admin/api/acessos` |

Rotas de alteração exigem CSRF. Todas as rotas administrativas verificam a sessão e o papel no servidor, além de não serem expostas a usuários comuns.

## Testes e verificação

Execute os comandos sempre pelo ambiente virtual:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q app.py biometric config database models routes services tests
.venv/bin/python -m pip check
```

Os testes cobrem a hierarquia, migração de banco, cadastro e matrículas, aprovação e auditoria, proteção CSRF, estados de conta, login, rota administrativa e bloqueio de recursos. O pipeline de visão computacional requer câmera, modelos e avaliação manual adicional; os testes automatizados não devem ser interpretados como validação biométrica ou prova de vida.
