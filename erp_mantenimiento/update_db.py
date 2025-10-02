import sqlite3

DATABASE = 'materiales.db'

def add_column_to_mantenimiento():
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # SQL command to add the column IF it doesn't exist
        cursor.execute("ALTER TABLE mantenimiento ADD COLUMN order_index INTEGER;")
        
        # Populate the new column with values
        cursor.execute("UPDATE mantenimiento SET order_index = id;")
        
        conn.commit()
        print("La columna 'order_index' se ha añadido y actualizado correctamente.")
        
    except sqlite3.OperationalError as e:
        print(f"Error: {e}")
        if "duplicate column name" in str(e):
            print("La columna 'order_index' ya existe. No es necesario hacer nada.")
    except Exception as e:
        print(f"Ocurrió un error inesperado: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    add_column_to_mantenimiento()