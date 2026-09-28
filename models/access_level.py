"""
Níveis de acesso do BIOAUTH.

O nível de acesso (access_level) diz QUAIS RECURSOS PROTEGIDOS DO COFRE
uma pessoa pode acessar. Ele é independente do perfil (role) do usuário,
que diz o que a pessoa pode fazer DENTRO DO SISTEMA (ver models/user.py).

    Nível 1 -> acesso geral
    Nível 2 -> acesso de diretoria
    Nível 3 -> acesso ministerial

Toda a lógica sobre os níveis fica neste módulo. O restante do código deve
usar estas constantes e funções em vez de comparar números diretamente.
"""

LEVEL_1 = 1
LEVEL_2 = 2
LEVEL_3 = 3

LEVEL_LABELS = {
    LEVEL_1: "Acesso geral",
    LEVEL_2: "Acesso de diretoria",
    LEVEL_3: "Acesso ministerial",
}

VALID_LEVELS = tuple(LEVEL_LABELS)


def is_valid_level(value) -> bool:
    """Retorna True somente para os inteiros 1, 2 ou 3.

    `type(value) is int` rejeita bool de propósito: em Python,
    True == 1, e um True vindo de um formulário não deve virar nível 1.
    """
    return type(value) is int and value in LEVEL_LABELS


def level_label(level: int) -> str:
    """Nome descritivo do nível (ex.: 2 -> 'Acesso de diretoria')."""
    return LEVEL_LABELS[level]


def level_choices() -> list[tuple[int, str]]:
    """Opções para o <select> do formulário: (valor, texto exibido)."""
    return [(level, f"Nível {level} — {label}") for level, label in LEVEL_LABELS.items()]


def can_access(user_level: int, required_level: int) -> bool:
    """Regra de comparação entre nível do usuário e nível do recurso.

    Um nível maior inclui os menores: nível 2 acessa recursos 1 e 2, mas
    não o 3. Esta função apenas PREPARA a regra; ela ainda não é chamada
    por nenhuma rota. Quem vai aplicá-la é o access_service, na fase de
    autorização.
    """
    return (
        is_valid_level(user_level)
        and is_valid_level(required_level)
        and user_level >= required_level
    )
