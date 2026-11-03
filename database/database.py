"""SQLite persistence, schema creation and legacy database migration."""


import os
import re
import sqlite3
from datetime import datetime, timezone


from flask import current_app, g


from models.organization import seed_organization


SCHEMA = """
CREATE TABLE IF NOT EXISTS security_levels (
    level INTEGER PRIMARY KEY CHECK (level BETWEEN 1 AND 3),
    name TEXT NOT NULL UNIQUE
);


CREATE TABLE IF NOT EXISTS organization_areas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL UNIQUE,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);


CREATE TABLE IF NOT EXISTS organization_teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    area_id INTEGER NOT NULL REFERENCES organization_areas(id),
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    UNIQUE (area_id, code),
    UNIQUE (area_id, name),
    UNIQUE (area_id, id)
);


CREATE TABLE IF NOT EXISTS organization_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL UNIQUE,
    access_level INTEGER NOT NULL REFERENCES security_levels(level),
    scope TEXT NOT NULL CHECK (scope IN ('GLOBAL', 'AREA')),
    sort_order INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);


CREATE TABLE IF NOT EXISTS organization_position_reports (
    supervisor_position_id INTEGER NOT NULL REFERENCES organization_positions(id),
    subordinate_position_id INTEGER NOT NULL REFERENCES organization_positions(id),
    PRIMARY KEY (supervisor_position_id, subordinate_position_id),
    CHECK (supervisor_position_id != subordinate_position_id)
);


CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    matricula TEXT UNIQUE,
    name TEXT NOT NULL,
    birth_date TEXT,
    cpf_encrypted TEXT,
    cpf_digest TEXT UNIQUE,
    rg_encrypted TEXT,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    job_title TEXT NOT NULL DEFAULT '',
    division TEXT NOT NULL DEFAULT '',
    position_id INTEGER REFERENCES organization_positions(id),
    area_id INTEGER REFERENCES organization_areas(id),
    team_id INTEGER REFERENCES organization_teams(id),
    manager_user_id INTEGER REFERENCES users(id),
    profile_photo_encrypted BLOB,
    biometric_photo_consent_at TEXT,
    password_hash TEXT,
    role TEXT NOT NULL DEFAULT 'USER' CHECK (role IN ('ADMIN', 'USER')),
    access_level INTEGER NOT NULL CHECK (access_level IN (1, 2, 3)),
    access_level_assigned INTEGER NOT NULL DEFAULT 0 CHECK (access_level_assigned IN (0, 1)),
    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'SUSPENDED', 'INACTIVE')),
    rejection_reason TEXT,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    approved_by INTEGER REFERENCES users(id),
    approved_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_activity_at TEXT,
    deleted_at TEXT,
    FOREIGN KEY (access_level) REFERENCES security_levels(level),
    FOREIGN KEY (area_id, team_id) REFERENCES organization_teams(area_id, id)
);


CREATE TABLE IF NOT EXISTS matricula_counters (
    access_level INTEGER PRIMARY KEY REFERENCES security_levels(level),
    last_value INTEGER NOT NULL DEFAULT 0 CHECK (last_value >= 0)
);


CREATE TABLE IF NOT EXISTS biometric_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    angle TEXT NOT NULL CHECK (angle IN ('FRONT', 'RIGHT', 'LEFT')),
    embedding BLOB NOT NULL,
    model_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (user_id, angle)
);


CREATE TABLE IF NOT EXISTS toxins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    reference_code TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL,
    access_level INTEGER NOT NULL REFERENCES security_levels(level),
    description TEXT NOT NULL,
    origin TEXT NOT NULL DEFAULT '',
    appearance TEXT NOT NULL DEFAULT '',
    narrative_effects TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'ATIVO' CHECK (status IN ('ATIVO', 'ARQUIVADO'))
);


CREATE TABLE IF NOT EXISTS access_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    matricula TEXT,
    event TEXT NOT NULL,
    result TEXT NOT NULL CHECK (result IN ('SUCCESS', 'DENIED', 'FAILURE', 'INFO')),
    resource_id INTEGER REFERENCES toxins(id) ON DELETE SET NULL,
    required_level INTEGER,
    auth_type TEXT,
    details TEXT,
    created_at TEXT NOT NULL
);


CREATE TABLE IF NOT EXISTS admin_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    target_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    before_data TEXT,
    after_data TEXT,
    reason TEXT,
    result TEXT NOT NULL,
    created_at TEXT NOT NULL
);


"""


_LEGACY_COLUMNS = {
"matricula": "TEXT",
"birth_date": "TEXT",
"cpf_encrypted": "TEXT",
"cpf_digest": "TEXT",
"rg_encrypted": "TEXT",
"password_hash": "TEXT",
"status": "TEXT NOT NULL DEFAULT 'PENDING'",
"rejection_reason": "TEXT",
"approved_by": "INTEGER REFERENCES users(id)",
"approved_at": "TEXT",
"last_activity_at": "TEXT",
"deleted_at": "TEXT",
"access_level_assigned": "INTEGER NOT NULL DEFAULT 1 CHECK (access_level_assigned IN (0, 1))",
"profile_photo_encrypted": "BLOB",
"biometric_photo_consent_at": "TEXT",
"position_id": "INTEGER REFERENCES organization_positions(id)",
"area_id": "INTEGER REFERENCES organization_areas(id)",
"team_id": "INTEGER REFERENCES organization_teams(id)",
"manager_user_id": "INTEGER REFERENCES users(id)",
}
_PREFIXES = {1: "X", 2: "Y", 3: "Z"}
_MATRICULA_PATTERN = re.compile(r"^[XYZ](\d{3,})$")
_TOXINS = (
    # Nível 1
    (1, "TOX-1101", "VER-01", "Verdo-A",
     "Registro cenográfico de um composto vegetal para um cenário agrícola.",
     "A Verdo-A é um composto extraído de plantas modificadas, desenvolvido originalmente para testes agrícolas controlados.",
     "Estado Físico: Pó fino e esverdeado (representação fictícia).\nOdor: Vegetal suave.\nSolubilidade: Em água e solventes.",
     "Manifestação clínica (fictícia):\nEstágio Inicial (0 a 5 minutos): Coceira leve na pele.\nEstágio Intermediário (5 a 15 minutos): Vermelhidão superficial e fraqueza leve nos músculos da área exposta.\nEstágio Crítico (acima de 15 minutos): Sem risco crítico registrado.\n\nProtocolos de contenção (cenográficos):\nEPI obrigatório: Luvas de borracha simples e jaleco fechado.\nDescontaminação: Lavagem imediata da superfície afetada com água corrente e sabão.\nDescarte: Frascos plásticos vedados em coletores de resíduos químicos comuns.\n\nTratamento de emergência (fictício):\nAntídoto primário: Não necessita de antídoto específico; uso de loções calmantes para a pele.\nSuporte: Lavagem local e repouso (tempo estimado de recuperação: 2 a 4 horas)."),
    (1, "TOX-1102", "HID-02", "Hidro-L",
     "Registro cenográfico de um resíduo de processos industriais leves.",
     "A Hidro-L é uma substância química líquida residual de processos de tratamento industrial leve.",
     "Estado Físico: Líquido transparente.\nOdor: Sem odor aparente.\nSolubilidade: Misturado em água em qualquer proporção.",
     "Manifestação clínica (fictícia):\nEstágio Inicial (0 a 5 minutos): Tontura leve e gosto amargo na boca após ingestão acidental.\nEstágio Intermediário (5 a 15 minutos): Enjoo passageiro.\nEstágio Crítico (acima de 15 minutos): Sem risco crítico registrado.\n\nProtocolos de contenção (cenográficos):\nEPI obrigatório: Luvas de nitrilo e óculos de proteção ampla visão.\nDescontaminação: Limpeza com grande volume de água e detergente neutro.\nDescarte: Galões devidamente rotulados.\n\nTratamento de emergência (fictício):\nAntídoto primário: Não necessita de antídoto específico.\nSuporte: Repouso (tempo estimado de recuperação: 2 a 4 horas)."),
    (1, "TOX-1103", "AGR-03", "Agri-Tox",
     "Registro cenográfico de um material em pó associado a controle de pragas.",
     "O Agri-Tox é um pó leve utilizado no controle de pragas.",
     "Estado Físico: Pó seco acinzentado.\nOdor: Odor de terra molhada.\nSolubilidade: Baixa solubilidade em água.",
     "Manifestação clínica (fictícia):\nEstágio Inicial (0 a 5 minutos): Irritação no nariz.\nEstágio Intermediário (5 a 15 minutos): Tosse seca persistente.\nEstágio Crítico (acima de 15 minutos): Desconforto respiratório leve.\n\nProtocolos de contenção (cenográficos):\nEPI obrigatório: Máscara simples com filtro contra poeira e luvas descartáveis.\nDescontaminação: Varredura úmida do piso.\nDescarte: Frascos plásticos vedados em coletores de resíduos químicos comuns.\n\nTratamento de emergência (fictício):\nAntídoto primário: Remoção imediata para ar fresco.\nSuporte: Repouso (tempo estimado de recuperação: 1 a 3 horas)."),
    (1, "TOX-1104", "ESP-04", "Esporina-1",
     "Registro cenográfico de esporos de um cenário de pesquisa de materiais orgânicos.",
     "A Esporina-1 consiste em pequenos esporos fúngicos mantidos para estudo de degradação de materiais orgânicos.",
     "Estado Físico: Pó seco.\nOdor: Sem odor aparente.\nSolubilidade: Não se mistura bem em água.",
     "Manifestação clínica (fictícia):\nEstágio Inicial (0 a 5 minutos): Coceira e ardência leve nos olhos.\nEstágio Intermediário (5 a 15 minutos): Vermelhidão e irritação leve.\nEstágio Crítico (acima de 15 minutos): Sem risco crítico registrado.\n\nProtocolos de contenção (cenográficos):\nEPI obrigatório: Óculos de proteção e luvas de látex.\nDescontaminação: Limpeza com álcool nas superfícies expostas.\nDescarte: Sacos herméticos.\n\nTratamento de emergência (fictício):\nAntídoto primário: Não necessita de antídoto específico.\nSuporte: Lavagem com soro e repouso (tempo estimado de recuperação: 2 horas)."),
    (1, "TOX-1105", "BAC-05", "Bactox-1",
     "Registro cenográfico de um resíduo bacteriano usado em um cenário de calibração.",
     "A Bactox-1 é um resíduo bacteriano leve usado para calibrar sensores de detecção.",
     "Estado Físico: Líquido turvo.\nOdor: Leve cheiro de fermentado.\nSolubilidade: Misturado em água em qualquer proporção.",
     "Manifestação clínica (fictícia):\nEstágio Inicial (0 a 5 minutos): Desconforto estomacal leve se ingerido.\nEstágio Intermediário (5 a 15 minutos): Cólicas leves e enjoo passageiro.\nEstágio Crítico (acima de 15 minutos): Sem risco crítico registrado.\n\nProtocolos de contenção (cenográficos):\nEPI obrigatório: Luvas descartáveis e avental impermeável.\nDescontaminação: Limpeza com solução de cloro diluído.\nDescarte: Frascos vedados.\n\nTratamento de emergência (fictício):\nAntídoto primário: Não necessita de antídoto específico.\nSuporte: Hidratação e repouso (tempo estimado de recuperação: 12 horas)."),
    # Nível 2
    (2, "TOX-2101", "NEC-01", "Necrosil-2",
     "Registro cenográfico de um composto para um cenário de testes industriais.",
     "O Necrosil-2 é um composto químico líquido desenvolvido para testes de resistência de revestimentos industriais, mas que causa danos aos tecidos orgânicos em caso de contato direto.",
     "Estado Físico: Líquido denso e amarelado.\nOdor: Cheiro forte de vinagre envelhecido.\nSolubilidade: Parcialmente solúvel em água.",
     "Manifestação clínica (fictícia):\nEstágio Inicial (0 a 5 minutos): Queimação na pele e vermelhidão imediata.\nEstágio Intermediário (5 a 15 minutos): Formação de pequenas bolhas e perda de sensibilidade local.\nEstágio Crítico (acima de 15 minutos): Danos profundos na pele que exigem limpeza médica especializada.\n\nProtocolos de contenção (cenográficos):\nEPI obrigatório: Luvas grossas de borracha e máscara facial com visor.\nDescontaminação: Uso de solução neutralizante leve e enxágue com bastante água.\nDescarte: Tambores plásticos resistentes a ácidos.\n\nTratamento de emergência (fictício):\nAntídoto primário: Pomada específica para queimaduras químicas.\nSuporte: Lavagem imediata e curativo protetor (tempo estimado de recuperação: 3 a 5 dias)."),
    (2, "TOX-2102", "CAR-02", "Cardionil-B",
     "Registro cenográfico de uma substância experimental de laboratório.",
     "O Cardionil-B é uma substância experimental usada para estudar a regulação do ritmo cardíaco em equipamentos de laboratório fechados.",
     "Estado Físico: Solução límpida.\nOdor: Sem odor perceptível.\nSolubilidade: Misturado em água em qualquer proporção.",
     "Manifestação clínica (fictícia):\nEstágio Inicial (0 a 5 minutos): Queda repentina da pressão arterial e tontura forte.\nEstágio Intermediário (5 a 15 minutos): Batimentos cardíacos muito lentos e sensação de desmaio.\nEstágio Crítico (acima de 15 minutos): Risco de perda de consciência se a circulação não for estabilizada.\n\nProtocolos de contenção (cenográficos):\nEPI obrigatório: Jaleco reforçado, óculos de proteção e luvas de nitrilo.\nDescontaminação: Lavagem do piso com água e sabão neutro.\nDescarte: Frascos de vidro âmbar bem vedados.\n\nTratamento de emergência (fictício):\nAntídoto primário: Administração supervisionada de medicamento estimulante do ritmo cardíaco.\nSuporte: Monitoramento dos batimentos e repouso absoluto (tempo estimado de recuperação: 6 a 12 horas)."),
    (2, "TOX-2103", "AMN-03", "Amnesina-2",
     "Registro cenográfico de um agente volátil de um cenário acadêmico.",
     "A Amnesina-2 é um agente químico volátil mantido sob rigoroso controle para testes de filtros de ar em ambientes confinados.",
     "Estado Físico: Gás leve e incolor.\nOdor: Leve aroma adocicado.\nSolubilidade: Baixa solubilidade em água.",
     "Manifestação clínica (fictícia):\nEstágio Inicial (0 a 5 minutos): Confusão mental passageira e dificuldade de foco.\nEstágio Intermediário (5 a 15 minutos): Perda temporária de memória recente e desorientação.\nEstágio Crítico (acima de 15 minutos): Sonolência profunda e incapacidade temporária de reação rápida.\n\nProtocolos de contenção (cenográficos):\nEPI obrigatório: Máscara com filtro químico completo e luvas impermeáveis.\nDescontaminação: Ventilação forçada do ambiente por exaustores.\nDescarte: Cilindros de metal pressurizados.\n\nTratamento de emergência (fictício):\nAntídoto primário: Oxigênio puro.\nSuporte: Descanso em local calmo e arejado (tempo estimado de recuperação: 4 a 8 horas)."),
    (2, "TOX-2104", "HEM-04", "Hemoliz-C",
     "Registro cenográfico de um derivado usado em um cenário de pesquisa biomédica.",
     "O Hemoliz-C é um derivado químico utilizado em pesquisas de hematologia para análise de comportamento celular.",
     "Estado Físico: Líquido avermelhado.\nOdor: Odor metálico fraco.\nSolubilidade: Totalmente solúvel em soluções aquosas.",
     "Manifestação clínica (fictícia):\nEstágio Inicial (0 a 5 minutos): Palidez repentina e cansaço físico anormal.\nEstágio Intermediário (5 a 15 minutos): Falta de ar leve ao realizar pequenos movimentos.\nEstágio Crítico (acima de 15 minutos): Queda nos níveis de oxigenação do sangue que necessita de suporte médico.\n\nProtocolos de contenção (cenográficos):\nEPI obrigatório: Luvas duplas de látex e avental de proteção impermeável.\nDescontaminação: Limpeza imediata com álcool isopropílico.\nDescarte: Recipientes próprios para resíduos biológicos líquidos.\n\nTratamento de emergência (fictício):\nAntídoto primário: Solução salina intravenosa para hidratação.\nSuporte: Oferta de oxigênio suplementar e repouso (tempo estimado de recuperação: 12 horas)."),
    (2, "TOX-2105", "PYR-05", "Pyrotox-2",
     "Registro cenográfico de um material sintético para um cenário de ensaios térmicos.",
     "O Pyrotox-2 é um pó sintético desenvolvido para testes de resposta térmica em materiais isolantes de laboratório.",
     "Estado Físico: Pó fino cinza.\nOdor: Sem odor aparente.\nSolubilidade: Pouco solúvel em água, dispersável no ar.",
     "Manifestação clínica (fictícia):\nEstágio Inicial (0 a 5 minutos): Sensação repentina de calor na pele e rubor facial.\nEstágio Intermediário (5 a 15 minutos): Febre leve e suor excessivo na área exposta.\nEstágio Crítico (acima de 15 minutos): Aumento rápido da temperatura corporal se o pó não for removido.\n\nProtocolos de contenção (cenográficos):\nEPI obrigatório: Máscara contra poeira fina e luvas de proteção térmica/química.\nDescontaminação: Aspiração com filtro especial e pano úmido.\nDescarte: Sacos plásticos lacrados.\n\nTratamento de emergência (fictício):\nAntídoto primário: Compressas frias locais e hidratação oral rápida.\nSuporte: Repouso em ambiente climatizado (tempo estimado de recuperação: 3 a 6 horas)."),
    # Nível 3
    (3, "TOX-3101", "VPR-01", "Vesperina-K",
     "Registro cenográfico de um composto sintético de um cenário agrícola.",
     "A Vesperina-K é um composto sintético de alta periculosidade desenvolvido originalmente para contenção agrícola, reclassificado devido ao impacto no sistema respiratório.",
     "Estado Físico: Líquido volátil incolor.\nOdor: Leve cheiro de amêndoas.\nSolubilidade: Evapora rapidamente e dispersa no ar.",
     "Manifestação clínica (fictícia):\nEstágio Inicial (0 a 5 minutos): Tontura forte, visão turva e salivação em excesso.\nEstágio Intermediário (5 a 15 minutos): Espasmos musculares e dificuldade severa para respirar.\nEstágio Crítico (acima de 15 minutos): Paralisia dos músculos respiratórios e perda de consciência.\n\nProtocolos de contenção (cenográficos):\nEPI obrigatório: Traje hermético completo com cilindro de oxigênio (Nível A).\nDescontaminação: Lavagem imediata com solução de cloro a 5%.\nDescarte: Cilindros de titânio selados a vácuo sob refrigeração.\n\nTratamento de emergência (fictício):\nAntídoto primário: Injeção imediata de antídoto neutralizante (Atropina com Pralidoxima).\nSuporte: Ventilação mecânica assistida urgente (tempo estimado de suporte: 12 a 24 horas)."),
    (3, "TOX-3102", "OMN-02", "Omnimort-9",
     "Registro cenográfico de um agente biológico de ficção científica.",
     "O Omnimort-9 é um agente biológico sintético mantido em isolamento máximo por causar falhas em múltiplos órgãos.",
     "Estado Físico: Gel denso e translúcido.\nOdor: Sem odor perceptível.\nSolubilidade: Estável em meio aquoso, de difícil degradação.",
     "Manifestação clínica (fictícia):\nEstágio Inicial (0 a 5 minutos): Dores abdominais intensas e náusea extrema.\nEstágio Intermediário (5 a 15 minutos): Queda drástica no funcionamento dos rins e fígado.\nEstágio Crítico (acima de 15 minutos): Comprometimento geral dos órgãos e manchas escuras na pele.\n\nProtocolos de contenção (cenográficos):\nEPI obrigatório: Traje de isolamento total com sistema de pressão positiva de ar.\nDescontaminação: Esterilização por radiação UV e produtos desinfetantes pesados.\nDescarte: Incineração a altas temperaturas em ambiente fechado.\n\nTratamento de emergência (fictício):\nAntídoto primário: Não há antídoto direto; tratamento focado na eliminação do agente.\nSuporte: Internação em UTI com filtragem de sangue e máquinas de respiração (tempo estimado: indeterminado)."),
    (3, "TOX-3103", "BIO-03", "Bio-Destruktor",
     "Registro cenográfico de uma substância corrosiva de fantasia científica.",
     "O Bio-Destruktor é uma substância altamente corrosiva capaz de degradar rapidamente qualquer tecido orgânico com o qual entre em contato.",
     "Estado Físico: Líquido viscoso de cor escura.\nOdor: Odor químico penetrante.\nSolubilidade: Reage de forma agressiva em contato com a água.",
     "Manifestação clínica (fictícia):\nEstágio Inicial (0 a 5 minutos): Destruição imediata da camada superficial da pele.\nEstágio Intermediário (5 a 15 minutos): Danos às camadas mais profundas de tecido e dor intensa.\nEstágio Crítico (acima de 15 minutos): Lesões graves e risco de contaminação sistêmica.\n\nProtocolos de contenção (cenográficos):\nEPI obrigatório: Roupa blindada contra produtos químicos agressivos e máscara autônoma.\nDescontaminação: Aplicação de pó absorvente especial para remoção do líquido.\nDescarte: Recipientes reforçados de chumbo e polímeros especiais.\n\nTratamento de emergência (fictício):\nAntídoto primário: Aplicação de agente neutralizador em pó.\nSuporte: Intervenção médica de emergência e isolamento da área (tempo de recuperação: longo prazo)."),
    (3, "TOX-3104", "FUR-04", "Furia-X",
     "Registro cenográfico de um agente de um cenário narrativo.",
     "O Furia-X é um agente neurotóxico gasoso formulado para estudar respostas de estresse extremo no sistema nervoso central.",
     "Estado Físico: Gás invisível.\nOdor: Inodoro.\nSolubilidade: Altamente volátil, mistura-se rápido no ar.",
     "Manifestação clínica (fictícia):\nEstágio Inicial (0 a 5 minutos): Agitação motora repentina e aceleração dos batimentos cardíacos.\nEstágio Intermediário (5 a 15 minutos): Comportamento agressivo incontrolável e confusão total.\nEstágio Crítico (acima de 15 minutos): Colapso físico por exaustão e desmaio prolongado.\n\nProtocolos de contenção (cenográficos):\nEPI obrigatório: Máscara de gás de especificação máxima e traje completamente selado.\nDescontaminação: Purificação do ar por filtros de carvão ativado de alta densidade.\nDescarte: Neutralização do gás restante em câmara química.\n\nTratamento de emergência (fictício):\nAntídoto primário: Aplicação de sedativo de ação rápida.\nSuporte: Repouso sob monitoramento contínuo em ambiente isolado (tempo estimado de recuperação: 24 horas)."),
    (3, "TOX-3105", "NEC-05", "Necroflux-3",
     "Registro cenográfico de um composto sintético de pesquisa avançada.",
     "O Necroflux-3 é um composto sintético avançado que desacelera e interrompe a regeneração celular no organismo exposto.",
     "Estado Físico: Pó denso e acinzentado.\nOdor: Sem odor aparente.\nSolubilidade: Insolúvel em água, transportado facilmente por correntes de ar.",
     "Manifestação clínica (fictícia):\nEstágio Inicial (0 a 5 minutos): Fraqueza muscular súbita e queda da imunidade local.\nEstágio Intermediário (5 a 15 minutos): Irritação grave na pele e sangramentos superficiais.\nEstágio Crítico (acima de 15 minutos): Falha generalizada no sistema de defesa do corpo.\n\nProtocolos de contenção (cenográficos):\nEPI obrigatório: Traje anti-radiação e biossegurança de Nível A.\nDescontaminação: Aspiração hermética e limpeza das superfícies com reagentes próprios.\nDescarte: Selamento em caixas metálicas de alta resistência.\n\nTratamento de emergência (fictício):\nAntídoto primário: Medicação para estímulo imediato da medula óssea.\nSuporte: Permanência em câmara estéril e transfusão de apoio (tempo estimado de recuperação: semanas)."),
)



def connect(path: str) -> sqlite3.Connection:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn



def _add_legacy_columns(conn: sqlite3.Connection) -> tuple[bool, bool]:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
    had_status_column = "status" in existing
    had_level_assignment_column = "access_level_assigned" in existing
    for column, definition in _LEGACY_COLUMNS.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE users ADD COLUMN {column} {definition}")
    return not had_status_column, not had_level_assignment_column



def _add_toxin_columns(conn: sqlite3.Connection) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(toxins)")}
    for column, definition in (
        ("reference_code", "TEXT NOT NULL DEFAULT ''"),
        ("origin", "TEXT NOT NULL DEFAULT ''"),
        ("appearance", "TEXT NOT NULL DEFAULT ''"),
        ("narrative_effects", "TEXT NOT NULL DEFAULT ''"),
    ):
        if column not in existing:
            conn.execute(
                f"ALTER TABLE toxins ADD COLUMN {column} {definition}"
            )



def _migrate_legacy_users(
    conn: sqlite3.Connection, migrate_status: bool, migrate_level_assignment: bool
) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = conn.execute(
        "SELECT id, access_level, role, active, matricula, status FROM users ORDER BY id"
    ).fetchall()
    counters = {1: 0, 2: 0, 3: 0}
    for row in rows:
        level = row["access_level"] if row["access_level"] in _PREFIXES else 1
        existing = row["matricula"]
        if existing and _MATRICULA_PATTERN.fullmatch(existing):
            counters[level] = max(counters[level], int(existing[1:]))
        elif existing:
            existing = None
        if not existing and migrate_level_assignment:
            counters[level] += 1
            existing = f"{_PREFIXES[level]}{counters[level]:03d}"

        status = row["status"]
        if migrate_status:
            if row["role"] == "ADMIN":
                status = "INACTIVE"
            else:
                status = "APPROVED" if row["active"] else "SUSPENDED"
        conn.execute(
            "UPDATE users SET matricula = ?, status = ?, active = ?, "
            "access_level_assigned = CASE WHEN ? THEN 1 ELSE access_level_assigned END, "
            "updated_at = COALESCE(updated_at, ?) "
            "WHERE id = ?",
            (existing, status, int(status in ("APPROVED", "PENDING")) if migrate_status
             else row["active"], int(migrate_level_assignment), now, row["id"]),
        )
    for level, value in counters.items():
        conn.execute(
            "INSERT INTO matricula_counters(access_level, last_value) VALUES (?, ?) "
            "ON CONFLICT(access_level) DO UPDATE SET last_value = MAX(last_value, excluded.last_value)",
            (level, value),
        )



def init_db(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    _add_toxin_columns(conn)
    migrate_status, migrate_level_assignment = _add_legacy_columns(conn)
    conn.executemany(
        "INSERT OR IGNORE INTO security_levels(level, name) VALUES (?, ?)",
        ((1, "Acesso geral"), (2, "Acesso de diretoria"), (3, "Acesso ministerial")),
    )
    seed_organization(conn)
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);
        CREATE INDEX IF NOT EXISTS idx_users_level ON users(access_level);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_matricula ON users(matricula);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_cpf_digest ON users(cpf_digest);
        CREATE INDEX IF NOT EXISTS idx_users_org_position ON users(position_id, area_id, team_id);
        CREATE INDEX IF NOT EXISTS idx_users_org_manager ON users(manager_user_id);
        CREATE INDEX IF NOT EXISTS idx_access_logs_created ON access_logs(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_access_logs_event_result ON access_logs(event, result);
        CREATE INDEX IF NOT EXISTS idx_admin_actions_created ON admin_actions(created_at DESC);
        """
    )
    conn.executemany(
        "INSERT OR IGNORE INTO matricula_counters(access_level, last_value) VALUES (?, 0)",
        ((1,), (2,), (3,)),
    )
    _migrate_legacy_users(conn, migrate_status, migrate_level_assignment)
    for level, code, reference, name, description, origin, appearance, effects in _TOXINS:
        migrated = conn.execute(
            "UPDATE toxins SET code = ?, reference_code = ?, name = ?, access_level = ?, "
            "description = ?, origin = ?, appearance = ?, narrative_effects = ? "
            "WHERE code = ?",
            (
                code, reference, name, level, description, origin, appearance, effects,
                code,
            ),
        )
        if not migrated.rowcount:
            # tenta migrar de códigos legados antigos se existirem
            legacy_map = {
                "TOX-1101": "ASTER01", "TOX-1102": "ASTER02", "TOX-1103": "ASTER03",
                "TOX-1104": "ASTER04", "TOX-1105": "ASTER05",
                "TOX-2101": "COBALTO01", "TOX-2102": "COBALTO02", "TOX-2103": "COBALTO03",
                "TOX-2104": "COBALTO04", "TOX-2105": "COBALTO05",
                "TOX-3101": "ORION01", "TOX-3102": "ORION02", "TOX-3103": "ORION03",
                "TOX-3104": "ORION04", "TOX-3105": "ORION05",
            }
            legacy_code = legacy_map.get(code)
            if legacy_code:
                migrated = conn.execute(
                    "UPDATE toxins SET code = ?, reference_code = ?, name = ?, access_level = ?, "
                    "description = ?, origin = ?, appearance = ?, narrative_effects = ? "
                    "WHERE code = ?",
                    (code, reference, name, level, description, origin, appearance, effects, legacy_code),
                )
            if not migrated.rowcount:
                conn.execute(
                    "INSERT OR IGNORE INTO toxins("
                    "code, reference_code, name, access_level, description, origin, appearance, "
                    "narrative_effects) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (code, reference, name, level, description, origin, appearance, effects),
                )
    conn.commit()



def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE_PATH"])
    return g.db



def close_db(_error=None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()



def init_app(app) -> None:
    app.teardown_appcontext(close_db)
