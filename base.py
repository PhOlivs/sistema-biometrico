import sqlite3

conn = sqlite3.connect("database/egide.db")
cursor = conn.cursor()

id_registro = 2

cursor.execute(
    "DELETE FROM users WHERE id = ?",
    (id_registro,)
)

conn.commit()
conn.close()

print("Registro apagado com sucesso!")
