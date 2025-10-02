import sqlite3

conn = sqlite3.connect('materiales.db')
cursor = conn.cursor()

# Tabla para el registro de materiales
cursor.execute('''
CREATE TABLE IF NOT EXISTS materiales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    material TEXT,
    proveedor TEXT,
    longitud_barra REAL,
    peso_barra REAL,
    longitud_pieza REAL,
    cantidad_laton INTEGER,
    piezas_por_barra INTEGER,
    cantidad_kilogramos REAL,
    numero_parte TEXT,
    densidad REAL,
    tipo_materia_prima TEXT
)
''')

# Tabla para la información de los lockers
cursor.execute('''
CREATE TABLE IF NOT EXISTS lockers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero_locker TEXT NOT NULL,
    codigo_producto TEXT,
    nombre_producto TEXT NOT NULL,
    medida_producto TEXT,
    cantidad_producto INTEGER,
    valor_unitario REAL,
    stock_minimo INTEGER,
    stock_maximo INTEGER,
    stock_producto INTEGER
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS gambetas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo_gambeta TEXT NOT NULL,
    nombre_producto TEXT NOT NULL,
    nivel TEXT NOT NULL,
    codigo TEXT,
    cantidad_prestada INTEGER NOT NULL,
    vu_pesos REAL,
    minimo INTEGER,
    maximo INTEGER,
    cantidad_actual INTEGER
);
''')

cursor.execute('''
            CREATE TABLE IF NOT EXISTS carrito_herramientas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                zona_producto TEXT NOT NULL,
                nombre_producto TEXT NOT NULL,
                proveedor TEXT,
                medida_descripcion TEXT NOT NULL,
                codigo_cliente TEXT,
                cantidad_prestada INTEGER NOT NULL,
                cantidad_actual INTEGER NOT NULL
            )
        ''')  


cursor.execute('''
            CREATE TABLE IF NOT EXISTS material_estanteria (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ubicacion TEXT NOT NULL,
                nombre_producto TEXT NOT NULL,
                proveedor TEXT,
                descripcion TEXT NOT NULL,
                marca1 TEXT,
                marca2 TEXT,
                marca3 TEXT,
                codigo1 TEXT,
                codigo2 TEXT,
                codigo3 TEXT,
                valor_unitario1 REAL,
                valor_unitario2 REAL,
                valor_unitario3 REAL,
                valor_unitario4 REAL,
                cantidad_a_prestar INTEGER,
                cantidad_actual INTEGER,
                observaciones TEXT
            )
        ''')         

conn.commit()
conn.close()

print("Tablas 'materiales' y 'lockers' creadas o ya existentes en materiales.db")