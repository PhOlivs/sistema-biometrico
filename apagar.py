import sqlite3

conn = sqlite3.connect("database/egide.db")
cursor = conn.cursor()

id_registro = 3

cursor.execute(
    "DELETE FROM users WHERE id = ?",
    (id_registro,)
)

if cursor.rowcount > 0:
    print("Registro apagado com sucesso!")
else:
    print("Nenhum usuário encontrado com esse ID.")

conn.commit()
conn.close()
