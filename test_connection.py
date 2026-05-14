from backend.data.database import get_connection, init_db

init_db()
with get_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) AS n FROM closing_snapshot")
    row = cursor.fetchone()
    print(f"Righe in closing_snapshot: {row['n']}")