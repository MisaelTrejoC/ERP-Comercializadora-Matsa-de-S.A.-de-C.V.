from flask import Flask, request, jsonify, render_template, g, send_from_directory, session, redirect, url_for
import sqlite3
import os
import json
from datetime import datetime, date, timedelta
from werkzeug.security import generate_password_hash, check_password_hash # <- NUEVO
import pytz
import calendar
from functools import wraps # <--- Asegúrate de esta importación arriba


app = Flask(__name__, template_folder='templates')
app.secret_key = 'cookiesMatsa2025' 

# Define the database file
DATABASE = 'materiales.db'
MEXICO_TZ = pytz.timezone('America/Mexico_City')
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
DYNAMIC_COLUMNS_FILE = 'dynamic_columns.json'


# Asegura que la carpeta de subida exista
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Function to get a database connection for the current request
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        # Set row_factory to sqlite3.Row for dictionary-like access to columns
        db.row_factory = sqlite3.Row
    return db


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# Decorador para requerir un rol específico
def role_required(role_name):
    def decorator(f):
        @wraps(f)
        @login_required # Primero verifica que esté logeado
        def decorated_function(*args, **kwargs):
            if session.get('role') != role_name:
                # Si no tiene el rol, puede redirigir a un error 403 o a la página principal
                return "Acceso denegado: Se requiere rol de " + role_name, 403 
            return f(*args, **kwargs)
        return decorated_function
    return decorator



def load_dynamic_columns():
    """Carga las columnas dinámicas desde un archivo JSON."""
    if os.path.exists(DYNAMIC_COLUMNS_FILE):
        with open(DYNAMIC_COLUMNS_FILE, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []

# --- Función para guardar las columnas dinámicas en el archivo JSON ---
def save_dynamic_columns(columns):
    """Guarda las columnas dinámicas en un archivo JSON."""
    with open(DYNAMIC_COLUMNS_FILE, 'w') as f:
        json.dump(columns, f)

def get_last_week_start_date():
    """Calcula la fecha de inicio de la semana anterior (lunes)."""
    today = datetime.now()
    # Retrocede a la semana anterior
    start_of_week = today - timedelta(days=today.weekday())
    last_week_start = start_of_week - timedelta(weeks=1)
    return last_week_start.strftime('%Y-%m-%d')

def reset_weekly_data():
    """Mueve los datos de la semana pasada a una tabla histórica y los borra."""
    try:
        # Reemplaza 'tu_base_de_datos.db' con el nombre de tu archivo de base de datos
        conn = sqlite3.connect('materiales.db')
        cursor = conn.cursor()

        last_week_start = get_last_week_start_date()

        # Inserta los datos de eficiencia de la semana pasada en una tabla de historial
        cursor.execute('''
            INSERT INTO historial_eficiencia (maquina, fecha, no_parte_interno, piezas_programadas, piezas_reales, scrap, eficiencia, cumplimiento)
            SELECT maquina, fecha, no_parte_interno, piezas_programadas, piezas_reales, scrap, eficiencia, cumplimiento
            FROM eficiencia
            WHERE fecha >= ?
        ''', (last_week_start,))

        # Inserta los datos de disponibilidad de la semana pasada en una tabla de historial
        cursor.execute('''
            INSERT INTO historial_disponibilidad (maquina, fecha, operador, no_parte_interno, estandar, causa, minutos_perdidos)
            SELECT maquina, fecha, operador, no_parte_interno, estandar, causa, minutos_perdidos
            FROM disponibilidad
            WHERE fecha >= ?
        ''', (last_week_start,))

        # Borra los datos de la semana pasada de las tablas principales
        cursor.execute("DELETE FROM eficiencia WHERE fecha >= ?", (last_week_start,))
        cursor.execute("DELETE FROM disponibilidad WHERE fecha >= ?", (last_week_start,))

        conn.commit()
        conn.close()

        print(f"Datos de la semana que comenzó el {last_week_start} movidos al historial y borrados.")
    except Exception as e:
        print(f"Error durante el reinicio semanal: {e}")



# Function to close the database connection at the end of the request
@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# Function to initialize all tables if they don't exist
def init_db():
    with app.app_context():
        db = get_db()
        cur = db.cursor()
        
        # Tabla para el registro de materiales
        cur.execute('''
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
                tipo_materia_prima TEXT,
                diametro_material REAL, 
                volumen_kg REAL,
                horas_x_pieza REAL,
                no_parte_interno TEXT,
                cantidad_de_orden INTEGER,
                tornos INTEGER,
                scrap INTEGER,
                fecha_orden TEXT
            )
        ''')

        # Tabla para la información de los lockers
        cur.execute('''
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

        # Tabla para la información de las gambetas
        cur.execute('''
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
            )
        ''')

        # NUEVA TABLA para las revisiones del AMEF
        cur.execute('''
            CREATE TABLE IF NOT EXISTS amef_revisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                no_parte_interno TEXT NOT NULL,
                no_parte_cliente TEXT,
                revision INTEGER NOT NULL,
                descripcion TEXT NOT NULL,
                autor TEXT NOT NULL,
                equipo TEXT NOT NULL,
                sev REAL,
                class REAL,
                causas TEXT,
                occ REAL,
                control_preventivo TEXT,
                control_deteccion TEXT,
                det REAL,
                rpn REAL,
                acciones TEXT,
                responsables TEXT,
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(no_parte_interno) REFERENCES partes_piezas(no_parte_interno)
            )
        ''')


        # Tabla para la nueva sección de partes y piezas
        cur.execute('''
            CREATE TABLE IF NOT EXISTS partes_piezas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                no_parte_interno TEXT NOT NULL UNIQUE,
                no_parte_cliente TEXT,
                descripcion TEXT,
                cliente TEXT,
                materia_prima TEXT,
                medida_pulgadas REAL,       
                medida_milimetros REAL,     
                pieza_x_hora INTEGER,       
                pieza_x_turno_laj INTEGER,  
                piezas_por_barra INTEGER,
                longitud_medida REAL
            )
        ''')
        
        # --- NUEVA TABLA PARA BANDAS ---
        cur.execute('''
            CREATE TABLE IF NOT EXISTS bandas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre_producto TEXT NOT NULL,
                marca_producto TEXT,
                columna TEXT NOT NULL,
                codigo_proveedor TEXT NOT NULL,
                cantidad_prestada INTEGER NOT NULL,
                cantidad_actual INTEGER NOT NULL
            )
        ''')


        # --- NUEVA TABLA PARA CARRITO DE HERRAMIENTAS ---
        cur.execute('''
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

        


        # Nueva tabla para material_estanteria
        cur.execute('''
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
                observaciones TEXT,
                minimo INTEGER,
                maximo INTEGER
            )
        ''')
         # Drop for easy schema updates in development
        cur.execute('''
            CREATE TABLE IF NOT EXISTS papeleria (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lugar_zona TEXT NOT NULL,
                nombre_producto TEXT NOT NULL,
                medida_descripcion TEXT,
                codigo TEXT,
                valor_unitario REAL,
                cantidad_actual INTEGER NOT NULL,
                cantidad_minima INTEGER NOT NULL,
                cantidad_maxima INTEGER NOT NULL,
                observaciones_requerimientos TEXT
            )
        ''')

        cur.execute('''
            CREATE TABLE IF NOT EXISTS eficiencia (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                maquina TEXT NOT NULL,
                no_parte_interno TEXT NOT NULL,
                nombre_operador TEXT NOT NULL,
                piezas_programadas REAL NOT NULL,
                piezas_reales REAL NOT NULL,
                scrap REAL NOT NULL,
                fecha TEXT NOT NULL,
                semana INTEGER,
                anio INTEGER
            )
        ''')

        # --- NUEVA: tabla para registro de disponibilidad
        cur.execute('''
            CREATE TABLE IF NOT EXISTS disponibilidad (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                maquina TEXT NOT NULL,
                no_parte_interno TEXT,
                operador TEXT,
                estandar_paro REAL,
                causa_paro TEXT,
                minutos INTEGER,
                fecha TEXT NOT NULL
            )
        ''')


        cur.execute('''
            CREATE TABLE IF NOT EXISTS movimientos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                material_id INTEGER,
                tipo TEXT,
                cantidad INTEGER,
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(material_id) REFERENCES materiales(id)
            )
        ''')
        db.commit()
        #NUEVA: tabla para registro de mantenimiento
        cur.execute('''
            CREATE TABLE IF NOT EXISTS mantenimiento (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                machine_name TEXT NOT NULL,
                week_number INTEGER NOT NULL,
                status TEXT NOT NULL,
                order_index INTEGER
            )
        ''')

        db.commit()

                # Tabla para la gestión de USUARIOS y ROLES (Admin/Employee)
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'employee' -- 'admin' o 'employee'
            )
        ''')
        
        # Opcional: Insertar un usuario administrador por defecto si la tabla está vacía
        try:
            cur.execute("SELECT id FROM users WHERE role = 'admin'")
            if cur.fetchone() is None:
                # ¡ADVERTENCIA! Cambia 'admin_password' por una contraseña segura
                admin_password_hash = generate_password_hash('admin_password') 
                cur.execute('''
                    INSERT INTO users (username, password_hash, role) 
                    VALUES (?, ?, ?)
                ''', ('admin', admin_password_hash, 'admin'))
                print("Usuario 'admin' creado por defecto.")
        except Exception as e:
            # Esto puede ocurrir si generate_password_hash no está importado o la tabla no se creó
            print(f"Error al intentar crear usuario admin: {e}") 
        
        db.commit() # Asegúrate de que este commit incluya la nueva tabla.
    
        

        # --- INSTRUCCIONES DE MIGRACIÓN PARA TABLAS EXISTENTES ---
        # Si ya tienes una base de datos 'materiales.db' y quieres añadir estas columnas
        # sin perder datos, puedes ejecutar estos comandos ALTER TABLE una vez.
        # Descomenta y ejecuta si es necesario, luego vuelve a comentar.
        try:
            cur.execute("ALTER TABLE carrito_herramientas ADD COLUMN minimo INTEGER DEFAULT 0")
            print("Columna 'minimo' añadida a carrito_herramientas.")
        except sqlite3.OperationalError:
            print("La columna 'minimo' ya existe.")

        try:
            cur.execute("ALTER TABLE carrito_herramientas ADD COLUMN maximo INTEGER DEFAULT 0")
            print("Columna 'maximo' añadida a carrito_herramientas.")
        except sqlite3.OperationalError:
            print("La columna 'maximo' ya existe.")


        try:
            cur.execute("ALTER TABLE materiales ADD COLUMN diametro_material REAL")
            print("Columna 'diametro_material' añadida a la tabla 'materiales'.")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e):
                print(f"Error al añadir columna diametro_material: {e}")

        try:
            cur.execute("ALTER TABLE materiales ADD COLUMN volumen_kg REAL")
            print("Columna 'volumen_kg' añadida a la tabla 'materiales'.")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e):
                print(f"Error al añadir columna volumen_kg: {e}")

        try:
            cur.execute("ALTER TABLE partes_piezas ADD COLUMN medida_pulgadas REAL")
            print("Columna 'medida_pulgadas' añadida a la tabla 'partes_piezas'.")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e):
                print(f"Error al añadir columna medida_pulgadas: {e}")

        try:
            cur.execute("ALTER TABLE partes_piezas ADD COLUMN medida_milimetros REAL")
            print("Columna 'medida_milimetros' añadida a la tabla 'partes_piezas'.")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e):
                print(f"Error al añadir columna medida_milimetros: {e}")
        
        try:
            cur.execute("ALTER TABLE partes_piezas ADD COLUMN pieza_x_hora INTEGER")
            print("Columna 'pieza_x_hora' añadida a la tabla 'partes_piezas'.")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e):
                print(f"Error al añadir columna pieza_x_hora: {e}")

        try:
            cur.execute("ALTER TABLE partes_piezas ADD COLUMN pieza_x_turno_laj INTEGER")
            print("Columna 'pieza_x_turno_laj' añadida a la tabla 'partes_piezas'.")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e):
                print(f"Error al añadir columna pieza_x_turno_laj: {e}")
        # --- FIN DE INSTRUCCIONES DE MIGRACIÓN ---
def update_db_schema():
    with app.app_context():
        db = get_db()
        cur = db.cursor()
        try:
            # Check and add 'no_parte_interno' to 'eficiencia' table
            cur.execute("PRAGMA table_info(eficiencia)")
            columns = [column[1] for column in cur.fetchall()]
            if 'semana' not in columns:
                print("Adding 'semana' column to 'eficiencia' table.")
                cur.execute("ALTER TABLE eficiencia ADD COLUMN semana INTEGER")
            if 'anio' not in columns:
                print("Adding 'anio' column to 'eficiencia' table.")
                cur.execute("ALTER TABLE eficiencia ADD COLUMN anio INTEGER")

            if 'no_parte_interno' not in columns:
                print("Adding 'no_parte_interno' column to 'eficiencia' table.")
                cur.execute("ALTER TABLE eficiencia ADD COLUMN no_parte_interno TEXT")
            if 'nombre_operador' not in columns:
                print("Adding 'nombre_operador' column to 'eficiencia' table.")
                cur.execute("ALTER TABLE eficiencia ADD COLUMN nombre_operador TEXT")
            if 'piezas_programadas' not in columns:
                print("Adding 'piezas_programadas' column to 'eficiencia' table.")
                cur.execute("ALTER TABLE eficiencia ADD COLUMN piezas_programadas REAL")
            if 'piezas_reales' not in columns:
                print("Adding 'piezas_reales' column to 'eficiencia' table.")
                cur.execute("ALTER TABLE eficiencia ADD COLUMN piezas_reales REAL")
            
            # Check and add 'minutos_perdidos' and 'no_parte_interno' to 'disponibilidad' table
            cur.execute("PRAGMA table_info(disponibilidad)")
            columns = [column[1] for column in cur.fetchall()]
            if 'minutos_perdidos' not in columns:
                print("Adding 'minutos_perdidos' column to 'disponibilidad' table.")
                cur.execute("ALTER TABLE disponibilidad ADD COLUMN minutos_perdidos INTEGER")
            if 'no_parte_interno' not in columns:
                print("Adding 'no_parte_interno' column to 'disponibilidad' table.")
                cur.execute("ALTER TABLE disponibilidad ADD COLUMN no_parte_interno TEXT")
            if 'estandar' not in columns:
                print("Adding 'estandar' column to 'disponibilidad' table.")
                cur.execute("ALTER TABLE disponibilidad ADD COLUMN estandar REAL")
            if 'fecha_creacion' not in columns:
                print("Adding 'fecha_creacion' column to 'disponibilidad' table.")
                cur.execute("ALTER TABLE disponibilidad ADD COLUMN fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
                
            db.commit()
            print("Database schema updated successfully.")
        except sqlite3.Error as e:
            print(f"Error updating database schema: {e}")


        db.commit()

# Asegúrate de llamar a init_db al inicio de la aplicación
with app.app_context():
    init_db()

# --- ROUTES ---

@app.route('/')
@login_required # <- SOLO USUARIOS LOGEADOS
def index():
    db = get_db()
    cur = db.cursor()
    inventario = []
    valor_total_inventario = 0

    user_role = session.get('role', 'employee') 

    # Obtener datos de Gambetas
    cur.execute("SELECT nombre_producto, cantidad_actual, vu_pesos FROM gambetas WHERE cantidad_actual > 0 AND vu_pesos IS NOT NULL")
    gambetas_guardadas = cur.fetchall()
    for row in gambetas_guardadas:
        inventario.append({'nombre': row['nombre_producto'], 'cantidad': row['cantidad_actual'], 'vu': row['vu_pesos'], 'fuente': 'Gambeta'})
        valor_total_inventario += row['cantidad_actual'] * row['vu_pesos']

    # Obtener datos de Lockers
    cur.execute("SELECT nombre_producto, stock_producto, valor_unitario FROM lockers WHERE stock_producto > 0 AND valor_unitario IS NOT NULL")
    lockers_guardados = cur.fetchall()
    for row in lockers_guardados:
        inventario.append({'nombre': row['nombre_producto'], 'cantidad': row['stock_producto'], 'vu': row['valor_unitario'], 'fuente': 'Locker'})
        valor_total_inventario += row['stock_producto'] * row['valor_unitario']

    # Obtener datos de Materiales para el resumen de inventario
    cur.execute("""
        SELECT
            CASE
                WHEN pp.materia_prima IS NOT NULL THEN pp.materia_prima
                ELSE m.material
            END AS display_nombre,
            COUNT(m.id) as cantidad_registros,
            m.proveedor as fuente,
            AVG(m.longitud_barra * m.peso_barra) as valor_promedio_estimado
        FROM
            materiales m
        LEFT JOIN
            partes_piezas pp ON m.material = pp.no_parte_interno
        GROUP BY
            display_nombre, m.proveedor;
    """)
    materiales_guardados = cur.fetchall()
    for row in materiales_guardados:
        inventario.append({'nombre': row['display_nombre'], 'cantidad': row['cantidad_registros'], 'vu': row['valor_promedio_estimado'] or 0, 'fuente': row['fuente']})
        valor_total_inventario += row['cantidad_registros'] * (row['valor_promedio_estimado'] or 0) 

    return render_template('almacenamiento.html', inventario=inventario, valor_total=valor_total_inventario, user_role=user_role)

@app.route('/formato_impresion')
def formato_impresion():
    return render_template('formato_impresion.html')

@app.route("/listas_lockers")
@login_required 
def listas_lockers():
    user_role =  session.get('role','employee')
    return render_template('listas_lockers.html', user_role=user_role)

@app.route("/gambetas")
@login_required
def gambetas():
    user_role = session.get('role', 'employee') 
    return render_template('gambetas.html', user_role=user_role)

@app.route("/carrito_de_herramientas")
@login_required
def carrito_de_herramientas():
    user_role = session.get('role', 'employee')
    return render_template("carrito_de_herramientas.html", user_role=user_role)

@app.route("/estanterias")
@login_required
def estanterias():
    user_role = session.get('role', 'enployee')
    return render_template("estanterias.html", user_role=user_role)

@app.route("/bandas")
@login_required
def bandas():
    user_role = session.get('role', 'employee')
    return render_template("zona_bandas.html", user_role=user_role)

@app.route("/lista_numeros_de_parte_y_piezas_por_barra")
@login_required
def lista_numeros_de_parte_y_piezas_por_barra():
    user_role = session.get('role', 'employee')
    return render_template("lista_numeros_de_parte_y_piezas_por_barra.html", user_role=user_role)

@app.route("/papeleria")
def papeleira():
    return render_template("papeleria.html")

@app.route("/mantenimento")
@login_required
def mantenimento():
    user_role = session.get('role','employee')
    return render_template("mantenimento.html", user_role=user_role)

@app.route("/piezas")
@login_required
def piezas():
    user_role = session.get('role', 'employee')
    return render_template("piezas.html", user_role=user_role)

@app.route("/indicadores")
def indicadores():
    return render_template("indicadores.html")

@app.route("/ventas")
def ventas():
    return render_template("ventas.html")

@app.route("/indicador_mantenimiento")
def indicador_mantenimiento():
    return render_template("/indicador_mantenimiento.html")

@app.route("/indicador_produccion")
def indicador_produccion():
    return render_template("/indicador_produccion.html")

@app.route("/indicador_calidad")
def indicador_calidad():
    return render_template("/indicador_calidad.html")


@app.route("/orden_de_trabajo")
def orden_de_trabajo():
    return render_template("orden_de_trabajo.html")

@app.route("/eficiencia")
@login_required
def eficiencia():
    user_role = session.get('role', 'eployee')
    return render_template("eficiencia.html", user_role=user_role)

@app.route("/disponibilidad")
@login_required
def disponibilidad():
    user_role = session.get('role', 'employee')
    return render_template("disponibilidad.html", user_role=user_role)

@app.route("/oee")
@login_required
def oee():
    user_role = session.get('role', 'employee')
    return render_template("oee.html", user_role=user_role)

@app.route("/tiempo_muerto_scrap")
@login_required
def tiempo_muerto_scrap():
    user_role = session.get('role', 'employee')
    return render_template("tiempo_muerto_scrap.html", user_role=user_role)

@app.route("/costeos")
def costeos():
    return render_template("costeos.html")



# --- Endpoint para obtener datos mensuales de órdenes de manufactura ---
@app.route('/api/get_monthly_data', methods=['GET'])
def get_monthly_data():
    try:
        month = request.args.get('month', type=int)
        
        if month is None:
            return jsonify({'success': False, 'message': 'Falta el parámetro del mes.'}), 400

        db = get_db()
        cursor = db.cursor()

        # Asegúrate de que los nombres de la tabla y las columnas sean correctos
        # Según tu código, la tabla es 'materiales' y las columnas son 'cantidad_de_orden' y 'scrap'
        cursor.execute("""
            SELECT SUM(cantidad_laton) as total_manufactured, SUM(scrap) as total_scrap
            FROM materiales
            WHERE strftime('%m', fecha_orden) = ?
        """, (f'{month:02}',))
        
        result = cursor.fetchone()

        total_manufactured = result['total_manufactured'] if result and result['total_manufactured'] else 0
        total_scrap = result['total_scrap'] if result and result['total_scrap'] else 0
        
        return jsonify({
            'success': True,
            'data': {
                'total_manufactured': total_manufactured,
                'total_scrap': total_scrap
            }
        })

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error en el servidor: {str(e)}'}), 500
    
@app.route('/api/get_all_monthly_data', methods=['GET'])
def get_all_monthly_data():
    try:
        db = get_db()
        cursor = db.cursor()

        # Query to get data for all months
        cursor.execute("""
            SELECT 
                strftime('%m', fecha_orden) as month,
                SUM(cantidad_laton) as total_manufactured,
                SUM(scrap) as total_scrap
            FROM materiales
            GROUP BY month
            ORDER BY month
        """)
        
        results = cursor.fetchall()

        # Format the data into a list of dictionaries
        monthly_data = []
        for row in results:
            monthly_data.append({
                'month': int(row['month']),
                'total_manufactured': row['total_manufactured'] if row['total_manufactured'] else 0,
                'total_scrap': row['total_scrap'] if row['total_scrap'] else 0
            })
            
        return jsonify({
            'success': True,
            'data': monthly_data
        })

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error en el servidor: {str(e)}'}), 500

@app.route('/guardar', methods=['POST'])
def guardar():
    data = request.get_json()
    db = get_db()
    cur = db.cursor()
    try:
        tornos = data.get('tornos', 0)
        scrap = data.get('scrap', 0)
        fecha_orden = data.get('fecha_orden', None)

        cur.execute('''
            INSERT INTO materiales (material, proveedor, longitud_barra, peso_barra,
                                     longitud_pieza, cantidad_laton, piezas_por_barra, numero_parte, 
                                     cantidad_kilogramos, densidad, tipo_materia_prima, diametro_material, volumen_kg,
                                     no_parte_interno, cantidad_de_orden, horas_x_pieza, tornos, scrap, fecha_orden) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (data['material'], data['proveedor'], data['longitud_barra'], data['peso_barra'],
             data['longitud_pieza'], data.get('cantidad_laton'), data['piezas_por_barra'], data['numero_parte'], 
             data.get('cantidad_kilogramos'), data.get('densidad'), data.get('tipo_materia_prima'), 
             data.get('diametro_material'), data.get('volumen_kg'),
             data.get('no_parte_interno'), data.get('cantidad_de_orden'), data.get('horas_x_pieza'), tornos, scrap, fecha_orden)
        )
        db.commit()
        return jsonify({"status": "guardado", "message": "Material guardado exitosamente!"}), 201
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({"status": "error", "message": f"Error al guardar material: {str(e)}"}), 500

@app.route('/materiales', methods=['POST'])
def guardar_material():
    data = request.json
    material = data.get('tipoMateriaPrima')
    proveedor = data.get('proveedor', '')
    longitud_barra = data.get('longitudBarra')
    peso_barra = data.get('pesoBarra')
    longitud_pieza = data.get('longitudPieza')
    cantidad_laton = data.get('cantidadLaton')
    piezas_por_barra = data.get('piezasPorBarra')
    cantidad_kilogramos = data.get('cantidadKilogramos')
    numero_parte = data.get('numeroParteInterno') #Este es No. parte interno
    densidad = data.get('densidad')
    diametro_material = data.get('diametroMaterial')
    # fuente_material = data.get('fuenteMaterial') # Esta columna no existe en tu tabla materiales
    cantidad_de_orden = data.get('cantidadDeOrden') # Asegúrate de que el frontend envíe este campo
    horas_x_pieza = data.get('horasXPieza')
    tornos =  data.get('tornos', 0)
    scrap = data.get('scrap', 0)
    fecha_orden = data.get('fecha_orden', None)

    db = get_db()
    try:
        cur = db.cursor()
        cur.execute('''
            INSERT INTO materiales (
                material, proveedor, longitud_barra, peso_barra, longitud_pieza,
                cantidad_laton, piezas_por_barra, cantidad_kilogramos, numero_parte,
                densidad, tipo_materia_prima, diametro_material,
                no_parte_interno, cantidad_de_orden, horas_x_pieza, tornos, scrap, fecha_orden
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            material, proveedor, longitud_barra, peso_barra, longitud_pieza,
            cantidad_laton, piezas_por_barra, cantidad_kilogramos, numero_parte,
            densidad, material, diametro_material,
            numero_parte, cantidad_de_orden, horas_x_pieza, tornos, scrap, fecha_orden # Se asume numero_parte es no_parte_interno
        ))
        material_id = cur.lastrowid # <-- Obtiene el ID de la fila insertada
        db.commit()
        # Asegúrate de que esta línea devuelva el ID
        return jsonify({'message': 'Material registrado exitosamente!', 'id': material_id}), 201
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({'error': f'Error al guardar material: {str(e)}'}), 500


@app.route('/obtener_materiales', methods=['GET'])
def obtener_materiales():
    query = request.args.get('q', '').strip()
    db = get_db()
    cur = db.cursor()
    search_term = f'%{query}%'

    sql_query = """
        SELECT
            m.id,
            CASE
                WHEN pp.materia_prima IS NOT NULL THEN pp.materia_prima
                ELSE m.material
            END AS display_material,
            m.proveedor,
            m.longitud_barra,
            m.peso_barra,
            m.longitud_pieza,
            m.cantidad_laton,
            m.piezas_por_barra,
            m.cantidad_kilogramos,
            m.numero_parte,          -- 9: No. Parte Cliente (desde materiales)
            m.no_parte_interno,      -- 10: No. Parte Interno (desde materiales)
            m.densidad,
            m.tipo_materia_prima,
            m.diametro_material,
            m.volumen_kg,
            m.horas_x_pieza,         -- 15: horas_x_pieza (desde materiales)
            m.cantidad_de_orden,     -- 16: Cantidad de Orden
            pp.pieza_x_hora,          -- 17: pieza_x_hora (desde partes_piezas)
            m.tornos
        FROM
            materiales m
        LEFT JOIN
            partes_piezas pp ON m.no_parte_interno = pp.no_parte_interno
    """
    params = []

    if query:
        sql_query += """
            WHERE
                m.numero_parte LIKE ? OR        -- Busca en No. Parte Cliente (materiales)
                m.no_parte_interno LIKE ? OR    -- Busca en No. Parte Interno (materiales)
                pp.no_parte_cliente LIKE ? OR   -- Busca en No. Parte Cliente (partes_piezas)
                pp.no_parte_interno LIKE ?      -- Busca en No. Parte Interno (partes_piezas)
        """
        # Se utilizan 4 placeholders porque se buscan en 4 campos específicos
        params.extend([search_term] * 4)

    sql_query += " ORDER BY m.id DESC" # Ordena los resultados por ID descendente

    cur.execute(sql_query, tuple(params))
    resultados = [list(row) for row in cur.fetchall()]
    return jsonify(resultados)
    
@app.route('/obtener/<int:id>', methods=['GET'])
def obtener_material(id):
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT
            m.id, 
            m.material, 
            m.proveedor, 
            m.longitud_barra, 
            m.peso_barra,
            m.longitud_pieza, 
            m.cantidad_laton, m.piezas_por_barra, m.cantidad_kilogramos,
            m.numero_parte, 
            m.densidad, 
            m.tipo_materia_prima, 
            m.diametro_material,
            m.volumen_kg,
            pp.pieza_x_hora,
            m.no_parte_interno,
            m.cantidad_de_orden,
            m.tornos
            
        FROM
            materiales m
        LEFT JOIN
            partes_piezas pp ON m.material = pp.no_parte_interno
        WHERE m.id = ?
    """, (id,))
    resultado = cur.fetchone()
    # Convertir el resultado a lista para jsonify
    return jsonify(list(resultado) if resultado else None)

@app.route('/actualizar/<int:id>', methods=['POST'])
@role_required('admin') # <- SOLO ADMINISTRADORES
def actualizar(id):
    data = request.get_json()
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute('''
            UPDATE materiales SET material=?, proveedor=?, longitud_barra=?, peso_barra=?,
                                 longitud_pieza=?, cantidad_laton=?, piezas_por_barra=?, numero_parte=?, 
                                 cantidad_kilogramos=?, densidad=?, tipo_materia_prima=?, diametro_material=?, volumen_kg=?,
                                 no_parte_interno=?, cantidad_de_orden=?, horas_x_pieza=?, tornos=? -- Añadidos
            WHERE id=?''',
            (data['material'], data['proveedor'], data['longitud_barra'], 
            data['peso_barra'], data['longitud_pieza'], data.get('cantidad_laton'), 
            data['piezas_por_barra'], data['numero_parte'], 
            data.get('cantidad_kilogramos'), data.get('densidad'), 
            data.get('tipo_materia_prima'), data.get('diametro_material'), 
            data.get('volumen_kg'), data.get('no_parte_interno'), 
            data.get('cantidad_de_orden'), data.get('horas_x_pieza'), 
            data.get('tornos', 0), id)
        )
        db.commit()
        if cur.rowcount == 0:
            return jsonify({"status": "error", "message": "Material no encontrado para actualizar."}), 404
        return jsonify({"status": "actualizado", "message": "Material actualizado exitosamente!"}), 200
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({"status": "error", "message": f"Error al actualizar material: {str(e)}"}), 500

# Este es el código corregido que debes usar en tu app.py
@app.route('/eliminar/<string:no_parte_interno>', methods=['POST'])
@role_required('admin') # <- SOLO ADMINISTRADORES
def eliminar_material(no_parte_interno):
    try:
        db = get_db()
        cur = db.cursor()
        # Cambiamos la consulta para buscar por no_parte_interno en lugar de id
        cur.execute("DELETE FROM materiales WHERE no_parte_interno = ?", (no_parte_interno,))
        db.commit()

        if cur.rowcount == 0:
            return jsonify({"message": "Material no encontrado para eliminar.", "status": "error"}), 404
        else:
            return jsonify({"message": f"Material con No. de Parte Interno {no_parte_interno} eliminado correctamente.", "status": "success"})

    except sqlite3.Error as e:
        return jsonify({"message": str(e), "status": "error"}), 500
    
@app.route('/buscar', methods=['GET'])
def buscar():
    termino = request.args.get('q', '')
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT
            m.id,
            CASE
                WHEN pp.materia_prima IS NOT NULL THEN pp.materia_prima
                ELSE m.material
            END AS display_material,
            m.proveedor,
            m.longitud_barra,
            m.peso_barra,
            m.longitud_pieza,
            m.cantidad_laton,
            m.piezas_por_barra,
            m.cantidad_kilogramos,
            m.numero_parte,
            pp.no_parte_interno,
            m.densidad,
            m.tipo_materia_prima,
            m.diametro_material,
            m.volumen_kg,
            NULL,
            m.cantidad_de_orden,
            pp.pieza_x_hora,
            m.tornos
        FROM
            materiales m
        LEFT JOIN
            partes_piezas pp ON m.material = pp.no_parte_interno
        WHERE
            m.material LIKE ? OR m.numero_parte LIKE ? OR pp.materia_prima LIKE ? OR pp.no_parte_interno LIKE ? OR m.densidad LIKE ? OR m.tipo_materia_prima LIKE ? OR m.diametro_material LIKE ? OR m.volumen_kg LIKE ? OR pp.pieza_x_hora LIKE ? OR m.cantidad_de_orden LIKE ? OR m.tornos LIKE ?;
    """, (f"%{termino}%", f"%{termino}%", f"%{termino}%", f"%{termino}%", f"%{termino}%", f"%{termino}%", f"%{termino}%", f"%{termino}%", f"%{termino}%", f"%{termino}%", f"%{termino}%"))
    resultados = [list(row) for row in cur.fetchall()]
    return jsonify(resultados)


@app.route('/guardar_locker', methods=['POST'])
def guardar_locker():
    data = request.get_json()
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute('''
            INSERT INTO lockers (numero_locker, codigo_producto, nombre_producto, medida_producto,
                                 cantidad_producto, valor_unitario, stock_minimo, stock_maximo, stock_producto)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (data['numero_locker'], data['codigo_producto'], data['nombre_producto'], data['medida_producto'],
             data['cantidad_producto'], data['valor_unitario'], data['stock_minimo'], data['stock_maximo'], data['stock_producto'])
        )
        db.commit()
        return jsonify({"status": "guardado", "message": "Locker guardado exitosamente!"}), 201
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({"status": "error", "message": f"Error al guardar locker: {str(e)}"}), 500

@app.route('/obtener_lista_lockers', methods=['GET'])
def obtener_lista_lockers():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id, numero_locker, codigo_producto, nombre_producto, medida_producto, cantidad_producto, valor_unitario, stock_minimo, stock_maximo, stock_producto FROM lockers")
    lockers = [list(row) for row in cur.fetchall()]
    return jsonify(lockers)


@app.route('/obtener_lockers', methods=['GET'])
def obtener_lockers():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT nombre_producto, medida_producto FROM lockers")
    lockers = [list(row) for row in cur.fetchall()]
    return jsonify([{'nombre_producto': l['nombre_producto'], 'medida_producto': l['medida_producto']} for l in lockers])

# Nueva ruta para obtener todos los nombres de productos de lockers
@app.route('/obtener_todos_nombres_lockers', methods=['GET'])
def obtener_todos_nombres_lockers():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT DISTINCT nombre_producto FROM lockers")
    nombres = [row['nombre_producto'] for row in cur.fetchall()]
    return jsonify(nombres)

@app.route('/obtener_locker/<int:id>', methods=['GET'])
def obtener_locker(id):
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM lockers WHERE id = ?", (id,))
    resultado = cur.fetchone()
    return jsonify(list(resultado) if resultado else None)

@app.route('/actualizar_locker/<int:id>', methods=['POST'])
@role_required('admin') # <- SOLO ADMINISTRADORES
def actualizar_locker(id):
    data = request.get_json()
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute('''
            UPDATE lockers SET numero_locker=?, codigo_producto=?, nombre_producto=?, medida_producto=?,
                                 cantidad_producto=?, valor_unitario=?, stock_minimo=?, stock_maximo=?, stock_producto=?
            WHERE id=?''',
            (data['numero_locker'], data['codigo_producto'], data['nombre_producto'], data['medida_producto'],
             data['cantidad_producto'], data['valor_unitario'], data['stock_minimo'], data['stock_maximo'], data['stock_producto'], id)
        )
        db.commit()
        if cur.rowcount == 0:
            return jsonify({"status": "error", "message": "Locker no encontrado para actualizar."}), 404
        return jsonify({"status": "actualizado", "message": "Locker actualizado exitosamente!"}), 200
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({"status": "error", "message": f"Error al actualizar locker: {str(e)}"}), 500

@app.route('/eliminar_locker/<int:id>', methods=['POST'])
@role_required('admin') # <- SOLO ADMINISTRADORES
def eliminar_locker(id):
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("DELETE FROM lockers WHERE id = ?", (id,))
        db.commit()
        if cur.rowcount == 0:
            return jsonify({"status": "error", "message": "Locker no encontrado para eliminar."}), 404
        return jsonify({"status": "eliminado", "message": "Locker eliminado exitosamente!"}), 200
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({"status": "error", "message": f"Error al eliminar locker: {str(e)}"}), 500

@app.route('/obtener_info_producto_gambeta/<nombre_producto>/<nivel>')
def obtener_info_producto_gambeta(nombre_producto, nivel):
    try:
        db = get_db()
        cursor = db.cursor()
        query = "SELECT minimo, maximo, cantidad_actual FROM gambetas WHERE nombre_producto = ? AND nivel = ?"
        cursor.execute(query, (nombre_producto, nivel))
        data = cursor.fetchone()
        
        if data:
            return jsonify({
                'minimo': data['minimo'],
                'maximo': data['maximo'],
                'cantidad_actual': data['cantidad_actual']
            })
        else:
            return jsonify({'message': 'Producto no encontrado.'}), 404
            
    except Exception as e:
        return jsonify({'message': f'Error en el servidor: {str(e)}'}), 500

@app.route('/guardar_gambeta', methods=['POST'])
def guardar_gambeta():
    data = request.json
    tipo_gambeta = data.get('tipo_gambeta')
    nombre_producto = data.get('nombre_producto')
    nivel = data.get('nivel')
    codigo = data.get('codigo')
    cantidad_prestada = data.get('cantidad_prestada')
    vu_pesos = data.get('vu_pesos')
    minimo = data.get('minimo')
    maximo = data.get('maximo')
    cantidad_actual = data.get('cantidad_actual')

    # Validación de campos requeridos
    if not tipo_gambeta or not nombre_producto or nivel is None or cantidad_prestada is None:
        return jsonify({'message': 'Tipo de Gambeta, Nombre de Producto, Nivel y Cantidad a Prestar son campos requeridos.'}), 400

    db = get_db()
    try:
        db.execute('''
            INSERT INTO gambetas (
                tipo_gambeta, nombre_producto, nivel, codigo,
                cantidad_prestada, vu_pesos, minimo, maximo, cantidad_actual
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            tipo_gambeta, nombre_producto, nivel, codigo,
            cantidad_prestada, vu_pesos, minimo, maximo, cantidad_actual
        ))
        db.commit()
        return jsonify({'message': 'Gambeta guardada exitosamente!'}), 201
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({'message': f'Error al guardar gambeta: {str(e)}'}), 500

@app.route('/obtener_gambetas')
def obtener_gambetas():
    db = get_db()
    gambetas = db.execute('SELECT * FROM gambetas').fetchall()
    # === CORRECCIÓN CLAVE AQUÍ: Asegúrate de que las filas se convierten a listas ===
    gambetas_list = [list(g) for g in gambetas]
    return jsonify(gambetas_list)

@app.route('/obtener_gambeta/<int:id>')
def obtener_gambeta_por_id(id):
    db = get_db()
    gambeta = db.execute('SELECT * FROM gambetas WHERE id = ?', (id,)).fetchone()
    if gambeta:
        return jsonify(list(gambeta)) # También convierte a lista
    return jsonify({'message': 'Gambeta no encontrada.'}), 404

@app.route('/actualizar_gambeta/<int:id>', methods=['POST'])
@role_required('admin') # <- SOLO ADMINISTRADORES
def actualizar_gambeta(id):
    data = request.json
    tipo_gambeta = data.get('tipo_gambeta')
    nombre_producto = data.get('nombre_producto')
    nivel = data.get('nivel')
    codigo = data.get('codigo')
    cantidad_prestada = data.get('cantidad_prestada')
    vu_pesos = data.get('vu_pesos')
    minimo = data.get('minimo')
    maximo = data.get('maximo')
    cantidad_actual = data.get('cantidad_actual')

    if not tipo_gambeta or not nombre_producto or nivel is None or cantidad_prestada is None:
        return jsonify({'message': 'Tipo de Gambeta, Nombre de Producto, Nivel y Cantidad a Prestar son campos requeridos.'}), 400

    db = get_db()
    try:
        cursor = db.execute('''
            UPDATE gambetas
            SET tipo_gambeta = ?, nombre_producto = ?, nivel = ?, codigo = ?,
                cantidad_prestada = ?, vu_pesos = ?, minimo = ?, maximo = ?, cantidad_actual = ?
            WHERE id = ?
        ''', (
            tipo_gambeta, nombre_producto, nivel, codigo,
            cantidad_prestada, vu_pesos, minimo, maximo, cantidad_actual, id
        ))
        db.commit()
        if cursor.rowcount == 0:
            return jsonify({'message': 'Gambeta no encontrada para actualizar.'}), 404
        return jsonify({'message': 'Gambeta actualizada exitosamente!'}), 200
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({'message': f'Error al actualizar gambeta: {str(e)}'}), 500

@app.route('/eliminar_gambeta/<int:id>', methods=['POST'])
@role_required('admin') # <- SOLO ADMINISTRADORES
def eliminar_gambeta(id):
    db = get_db()
    try:
        cursor = db.execute('DELETE FROM gambetas WHERE id = ?', (id,))
        db.commit()
        if cursor.rowcount == 0:
            return jsonify({'message': 'Gambeta no encontrada para eliminar.'}), 404
        return jsonify({'message': 'Gambeta eliminada exitosamente!'}), 200
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({'message': f'Error al eliminar la gambeta: {str(e)}'}), 500

@app.route('/buscar_gambetas')
def buscar_gambetas():
    query = request.args.get('q', '').strip()
    db = get_db()
    if query:
        search_term = f'%{query}%'
        gambetas = db.execute('SELECT * FROM gambetas WHERE codigo LIKE ?', (search_term,)).fetchall()
    else:
        gambetas = db.execute('SELECT * FROM gambetas').fetchall()
    
    gambetas_list = [list(g) for g in gambetas]
    return jsonify(gambetas_list)

# Nuevas rutas para obtener todos los registros de lockers y gambetas
@app.route('/obtener_registros_lockers', methods=['GET'])
def obtener_registros_lockers():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT nombre_producto, stock_producto, medida_producto FROM lockers")
    registros = [list(row) for row in cur.fetchall()]
    return jsonify([{'nombre_producto': registro[0], 'cantidad_actual': registro[1], 'medida_producto': registro[2]} for registro in registros])

@app.route('/obtener_registros_gambetas', methods=['GET'])
def obtener_registros_gambetas():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT nombre_producto, cantidad_actual, nivel FROM gambetas")
    registros = [list(row) for row in cur.fetchall()]
    return jsonify([{'nombre_producto': registro[0], 'cantidad_actual': registro[1], 'medida_producto': registro[2] if len(registro) > 2 else None} for registro in registros])


@app.route('/obtener_detalle_locker_por_nombre', methods=['GET'])
def obtener_detalle_locker_por_nombre():
    nombre = request.args.get('nombre')
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT medida_producto FROM lockers WHERE nombre_producto = ?", (nombre,))
    detalle = cur.fetchone()
    return jsonify({'medida_producto': detalle['medida_producto']} if detalle else None)

@app.route('/obtener_detalle_gambeta_por_nombre', methods=['GET'])
def obtener_detalle_gambeta_por_nombre():
    nombre = request.args.get('nombre')
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT nivel FROM gambetas WHERE nombre_producto = ?", (nombre,))
    detalle = cur.fetchone()
    return jsonify({'nivel': detalle['nivel']} if detalle else None)

# --- RUTAS PARA LA SECCIÓN: partes_piezas ---
@app.route('/guardar_parte_pieza', methods=['POST'])
def guardar_parte_pieza():
    data = request.get_json()
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute('''
            INSERT INTO partes_piezas (no_parte_interno, no_parte_cliente, descripcion, cliente, materia_prima, medida_pulgadas, medida_milimetros, pieza_x_hora, pieza_x_turno_laj, piezas_por_barra, longitud_medida)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['no_parte_interno'],
            data['no_parte_cliente'],
            data['descripcion'],
            data['cliente'],
            data['materia_prima'],
            data.get('medida_pulgadas'),    
            data.get('medida_milimetros'),
            data.get('pieza_x_hora'),
            data.get('pieza_x_turno_laj'),
            data.get('piezas_por_barra'),
            data.get('longitud_medida')
        ))
        db.commit()
        return jsonify({"status": "guardado", "message": "Parte/Pieza guardada exitosamente!"}), 201
    except sqlite3.IntegrityError: # Specific error for UNIQUE constraint
        db.rollback()
        return jsonify({"status": "error", "message": "Error: El número de parte interno ya existe. Debe ser único."}), 409 # Conflict
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({"status": "error", "message": f"Error al guardar Parte/Pieza: {str(e)}"}), 500

@app.route('/obtener_partes_piezas', methods=['GET'])
def obtener_partes_piezas():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id, no_parte_interno, no_parte_cliente, descripcion, cliente, materia_prima, medida_pulgadas, medida_milimetros, pieza_x_hora, pieza_x_turno_laj, piezas_por_barra, longitud_medida FROM partes_piezas")
    partes_piezas = [list(row) for row in cur.fetchall()]
    return jsonify(partes_piezas)

@app.route('/obtener_parte_pieza_interno', methods=['GET'])
def obtener_parte_pieza_interno():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT no_parte_interno FROM partes_piezas")
    partes_piezas = [list(row) for row in cur.fetchall()]
    return jsonify(partes_piezas)

@app.route('/obtener_numeros_parte_interno', methods=['GET'])
def obtener_numeros_parte_interno():
    db = get_db()
    try:
        cur = db.cursor()
        # *** CORRECCIÓN CRÍTICA: Consulta la tabla correcta y selecciona todas las columnas ***
        # Esto asegura que los índices del frontend (item[1], item[5], item[8]) correspondan.
        cur.execute("SELECT * FROM partes_piezas")
        
        # fetchall() con db.row_factory = sqlite3.Row devuelve objetos Row.
        # Los convertimos explícitamente a listas para que el frontend pueda usar índices numéricos.
        resultados_crudos = cur.fetchall()
        resultados_finales = [list(row) for row in resultados_crudos]
        
        return jsonify(resultados_finales)
    
    except sqlite3.OperationalError as e:
        # Captura errores como "no such table" o "no such column"
        print(f"Database Operational Error in /obtener_numeros_parte_interno: {str(e)}")
        return jsonify({'message': f'Error de base de datos: {str(e)}. Por favor, verifica que la tabla "numeros_de_parte_y_piezas_por_barra" existe y contiene datos.'}), 500
    except sqlite3.Error as e:
        # Captura otros errores generales de SQLite
        print(f"SQLite Error in /obtener_numeros_parte_interno: {str(e)}")
        return jsonify({'message': f'Error en la base de datos al obtener números de parte: {str(e)}'}), 500
    except Exception as e:
        # Captura cualquier otro error inesperado
        print(f"Unexpected Error in /obtener_numeros_parte_interno: {str(e)}")
        return jsonify({'message': f'Error inesperado del servidor: {str(e)}'}), 500

@app.route('/obtener_parte_pieza/<int:id>', methods=['GET'])
def obtener_parte_pieza(id):
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id, no_parte_interno, no_parte_cliente, descripcion, cliente, materia_prima, medida_pulgadas, medida_milimetros, pieza_x_hora, pieza_x_turno_laj, piezas_por_barra, longitud_medida FROM partes_piezas WHERE id = ?", (id,))
    parte_pieza = cur.fetchone()
    return jsonify(list(parte_pieza) if parte_pieza else None)

@app.route('/actualizar_parte_pieza/<int:id>', methods=['POST'])
@role_required('admin') # <- SOLO ADMINISTRADORES
def actualizar_parte_pieza(id):
    data = request.get_json()
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute('''
            UPDATE partes_piezas SET no_parte_interno=?, no_parte_cliente=?, descripcion=?, cliente=?, materia_prima=?, medida_pulgadas=?, medida_milimetros=?, pieza_x_hora=?, pieza_x_turno_laj=?, piezas_por_barra=?, longitud_medida=?
            WHERE id=?
        ''', (
            data['no_parte_interno'],
            data['no_parte_cliente'],
            data['descripcion'],
            data['cliente'],
            data['materia_prima'],
            data.get('medida_pulgadas'),    
            data.get('medida_milimetros'),  
            data.get('pieza_x_hora'),      
            data.get('pieza_x_turno_laj'),  
            data.get('piezas_por_barra'),
            data.get('longitud_medida'),
            id
        ))
        db.commit()
        if cur.rowcount == 0:
            return jsonify({"status": "error", "message": "Parte/Pieza no encontrada para actualizar."}), 404
        return jsonify({"status": "actualizado", "message": "Parte/Pieza actualizada exitosamente!"}), 200
    except sqlite3.IntegrityError:
        db.rollback()
        return jsonify({"status": "error", "message": "Error: El número de parte interno ya existe. Debe ser único."}), 409
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({"status": "error", "message": f"Error al actualizar Parte/Pieza: {str(e)}"}), 500

@app.route('/eliminar_parte_pieza/<int:id>', methods=['POST'])
@role_required('admin') # <- SOLO ADMINISTRADORES
def eliminar_parte_pieza(id):
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("DELETE FROM partes_piezas WHERE id = ?", (id,))
        db.commit()
        if cur.rowcount == 0:
            return jsonify({"status": "error", "message": "Parte/Pieza no encontrada para eliminar."}), 404
        return jsonify({"status": "eliminado", "message": "Parte/Pieza eliminada exitosamente!"}), 200
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({"status": "error", "message": f"Error al eliminar Parte/Pieza: {str(e)}"}), 500

@app.route('/buscar_parte_pieza_interno', methods=['GET'])
def buscar_parte_pieza_interno():
    termino = request.args.get('q', '')
    db = get_db()
    cur = db.cursor()
    search_term = f'%{termino}%'
    cur.execute("""
        SELECT id, no_parte_interno, no_parte_cliente, descripcion, cliente, materia_prima, medida_pulgadas, medida_milimetros, pieza_x_hora, pieza_x_turno_laj, piezas_por_barra, longitud_medida
        FROM partes_piezas
        WHERE no_parte_interno LIKE ? OR no_parte_cliente LIKE ? OR descripcion LIKE ? OR cliente LIKE ? OR materia_prima LIKE ?
    """, (search_term, search_term, search_term, search_term, search_term))
    resultados = [list(row) for row in cur.fetchall()]
    return jsonify(resultados)

# --- RUTAS PARA LA SECCIÓN: BANDAS ---

@app.route('/guardar_banda', methods=['POST'])
def guardar_banda():
    data = request.get_json()
    nombre_producto = data['nombre_producto']
    marca_producto = data.get('marca_producto', '')
    columna = data['columna']
    codigo_proveedor = data['codigo_proveedor']
    cantidad_prestada = int(data['cantidad_prestada'])
    cantidad_actual = int(data['cantidad_actual'])

    if cantidad_prestada > cantidad_actual:
        return jsonify({"status": "error", "message": "La cantidad a prestar no puede ser mayor que la cantidad actual."}), 400

    nueva_cantidad_actual = cantidad_actual - cantidad_prestada
    
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute('''
            INSERT INTO bandas (nombre_producto, marca_producto, columna, codigo_proveedor, cantidad_prestada, cantidad_actual)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (nombre_producto, marca_producto, columna, codigo_proveedor, cantidad_prestada, nueva_cantidad_actual))
        db.commit()
        return jsonify({"status": "guardado", "message": "Banda guardada correctamente."}), 201
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({"status": "error", "message": f"Error al guardar la banda: {str(e)}"}), 500

@app.route('/obtener_bandas', methods=['GET'])
def obtener_bandas():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id, nombre_producto, marca_producto, columna, codigo_proveedor, cantidad_prestada, cantidad_actual FROM bandas")
    bandas = [list(row) for row in cur.fetchall()]
    return jsonify(bandas)

@app.route('/buscar_bandas', methods=['GET'])
def buscar_bandas():
    termino = request.args.get('q', '')
    db = get_db()
    cur = db.cursor()
    search_term = f'%{termino}%'
    cur.execute("""
        SELECT id, nombre_producto, marca_producto, columna, codigo_proveedor, cantidad_prestada, cantidad_actual 
        FROM bandas 
        WHERE columna LIKE ? OR codigo_proveedor LIKE ?
    """, (search_term, search_term))
    resultados = [list(row) for row in cur.fetchall()]
    return jsonify(resultados)

@app.route('/obtener_banda/<int:id>', methods=['GET'])
def obtener_banda(id):
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id, nombre_producto, marca_producto, columna, codigo_proveedor, cantidad_prestada, cantidad_actual FROM bandas WHERE id = ?", (id,))
    banda = cur.fetchone()
    return jsonify(list(banda) if banda else None)

@app.route('/actualizar_banda/<int:id>', methods=['POST'])
@role_required('admin') # <- SOLO ADMINISTRADORES
def actualizar_banda(id):
    data = request.get_json()
    nombre_producto = data['nombre_producto']
    marca_producto = data.get('marca_producto', '')
    columna = data['columna']
    codigo_proveedor = data['codigo_proveedor']
    cantidad_prestada = int(data['cantidad_prestada'])
    cantidad_actual = int(data['cantidad_actual']) # Esta es la cantidad actual que se envía desde el formulario

    # Primero, obtenemos la cantidad_actual original de la base de datos para la validación
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT cantidad_actual FROM bandas WHERE id = ?", (id,))
    original_cantidad_actual_db = cur.fetchone()['cantidad_actual'] # Acceder por nombre de columna
    
    # Validar que la cantidad a prestar no exceda el stock actual original de la base de datos
    # Esta lógica es crucial para evitar stock negativo si la 'cantidad_prestada' es una resta de stock
    if cantidad_prestada > original_cantidad_actual_db:
        return jsonify({"status": "error", "message": "La cantidad a prestar no puede ser mayor que la cantidad actual en inventario."}), 400

    # La 'cantidad_actual' recibida del formulario se asume como el nuevo stock final deseado.
    # Si la 'cantidad_prestada' debe restarse del stock del formulario para obtener el stock final:
    # nueva_cantidad_actual_final = cantidad_actual - cantidad_prestada
    # Si 'cantidad_prestada' es un dato informativo y 'cantidad_actual' es el stock final ingresado:
    nueva_cantidad_actual_para_db = cantidad_actual 
    
    # Si la intención es que 'cantidad_prestada' SIEMPRE signifique una reducción del stock de la BD:
    # nueva_cantidad_actual_para_db = original_cantidad_actual_db - cantidad_prestada
    # En ese caso, la validación de arriba sería suficiente.

    db = get_db() # Re-establecer la conexión si se cerró antes, o simplemente usar la que ya está abierta
    cur = db.cursor()
    try:
        cur.execute('''
            UPDATE bandas SET nombre_producto=?, marca_producto=?, columna=?, codigo_proveedor=?, cantidad_prestada=?, cantidad_actual=?
            WHERE id=?
        ''', (nombre_producto, marca_producto, columna, codigo_proveedor, cantidad_prestada, nueva_cantidad_actual_para_db, id))
        db.commit()
        if cur.rowcount == 0:
            return jsonify({"status": "error", "message": "Banda no encontrada para actualizar."}), 404
        return jsonify({"status": "actualizado", "message": "Banda actualizada correctamente."}), 200
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({"status": "error", "message": f"Error al actualizar la banda: {str(e)}"}), 500


@app.route('/eliminar_banda/<int:id>', methods=['POST'])
@role_required('admin') # <- SOLO ADMINISTRADORES
def eliminar_banda(id):
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("DELETE FROM bandas WHERE id = ?", (id,))
        db.commit()
        if cur.rowcount == 0:
            return jsonify({"status": "error", "message": "Banda no encontrada para eliminar."}), 404
        return jsonify({"status": "eliminado", "message": "Banda eliminada correctamente."}), 200
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({"status": "error", "message": f"Error al eliminar la banda: {str(e)}"}), 500

# --- RUTAS PARA CARRITO DE HERRAMIENTAS ---
@app.route('/guardar_carrito_herramientas', methods=['POST'])
def guardar_carrito_herramientas():
    data = request.json
    zona_producto = data.get('zona_producto')
    nombre_producto = data.get('nombre_producto')
    proveedor = data.get('proveedor')
    medida_descripcion = data.get('medida_descripcion')
    codigo_cliente = data.get('codigo_cliente')
    cantidad_prestada = data.get('cantidad_prestada')
    cantidad_actual = data.get('cantidad_actual')
    minimo = data.get('minimo', 0)  # Nuevo campo
    maximo = data.get('maximo', 0)  # Nuevo campo

    if not zona_producto or not nombre_producto or not medida_descripcion:
        return jsonify({'message': 'Zona, Nombre de Producto y Medida/Descripción son campos requeridos.'}), 400

    db = get_db()
    try:
        db.execute('''
            INSERT INTO carrito_herramientas (zona_producto, nombre_producto, proveedor, medida_descripcion, codigo_cliente, cantidad_prestada, cantidad_actual, minimo, maximo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (zona_producto, nombre_producto, proveedor, medida_descripcion, codigo_cliente, cantidad_prestada, cantidad_actual, minimo, maximo))
        db.commit()
        return jsonify({'message': 'Elemento del carrito guardado exitosamente!'}), 201
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({'message': f'Error al guardar el elemento del carrito: {str(e)}'}), 500

@app.route('/obtener_carrito_herramientas')
def obtener_carrito_herramientas():
    db = get_db()
    # Consulta actualizada para incluir las nuevas columnas
    productos = db.execute('SELECT id, zona_producto, nombre_producto, proveedor, medida_descripcion, codigo_cliente, cantidad_prestada, cantidad_actual, minimo, maximo FROM carrito_herramientas').fetchall()
    productos_list = [list(p) for p in productos]
    return jsonify(productos_list)

@app.route('/obtener_carrito_herramientas/<int:id>')
def obtener_carrito_herramientas_por_id(id):
    db = get_db()
    # Consulta actualizada para incluir las nuevas columnas
    producto = db.execute('SELECT id, zona_producto, nombre_producto, proveedor, medida_descripcion, codigo_cliente, cantidad_prestada, cantidad_actual, minimo, maximo FROM carrito_herramientas WHERE id = ?', (id,)).fetchone()
    if producto:
        return jsonify(list(producto))
    return jsonify({'message': 'Elemento del carrito no encontrado.'}), 404

@app.route('/actualizar_carrito_herramientas/<int:id>', methods=['POST'])
@role_required('admin') # <- SOLO ADMINISTRADORES
def actualizar_carrito_herramientas(id):
    data = request.json
    zona_producto = data.get('zona_producto')
    nombre_producto = data.get('nombre_producto')
    proveedor = data.get('proveedor')
    medida_descripcion = data.get('medida_descripcion')
    codigo_cliente = data.get('codigo_cliente')
    cantidad_prestada = data.get('cantidad_prestada')
    cantidad_actual = data.get('cantidad_actual')
    minimo = data.get('minimo', 0)  # Nuevo campo
    maximo = data.get('maximo', 0)  # Nuevo campo

    if not zona_producto or not nombre_producto or not medida_descripcion:
        return jsonify({'message': 'Zona, Nombre de Producto y Medida/Descripción son campos requeridos.'}), 400

    db = get_db()
    try:
        cursor = db.execute('''
            UPDATE carrito_herramientas
            SET zona_producto = ?, nombre_producto = ?, proveedor = ?, medida_descripcion = ?, codigo_cliente = ?, cantidad_prestada = ?, cantidad_actual = ?, minimo = ?, maximo = ?
            WHERE id = ?
        ''', (zona_producto, nombre_producto, proveedor, medida_descripcion, codigo_cliente, cantidad_prestada, cantidad_actual, minimo, maximo, id))
        db.commit()
        if cursor.rowcount == 0:
            return jsonify({'message': 'Elemento del carrito no encontrado para actualizar.'}), 404
        return jsonify({'message': 'Elemento del carrito actualizado exitosamente!'}), 200
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({'message': f'Error al actualizar el elemento del carrito: {str(e)}'}), 500

@app.route('/eliminar_carrito_herramientas/<int:id>', methods=['POST'])
@role_required('admin') # <- SOLO ADMINISTRADORES
def eliminar_carrito_herramientas(id):
    db = get_db()
    try:
        cursor = db.execute('DELETE FROM carrito_herramientas WHERE id = ?', (id,))
        db.commit()
        if cursor.rowcount == 0:
            return jsonify({'message': 'Elemento del carrito no encontrado para eliminar.'}), 404
        return jsonify({'message': 'Elemento del carrito eliminado exitosamente!'}), 200
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({'message': f'Error al eliminar el elemento del carrito: {str(e)}'}), 500

@app.route('/buscar_carrito_herramientas')
def buscar_carrito_herramientas():
    query = request.args.get('q', '').strip()
    db = get_db()
    if query:
        search_term = f'%{query}%'
        # Consulta actualizada para incluir las nuevas columnas en los resultados
        productos = db.execute('SELECT id, zona_producto, nombre_producto, proveedor, medida_descripcion, codigo_cliente, cantidad_prestada, cantidad_actual, minimo, maximo FROM carrito_herramientas WHERE medida_descripcion LIKE ? OR nombre_producto LIKE ? OR zona_producto LIKE ?', (search_term, search_term, search_term)).fetchall()
    else:
        # Consulta actualizada para incluir las nuevas columnas en los resultados
        productos = db.execute('SELECT id, zona_producto, nombre_producto, proveedor, medida_descripcion, codigo_cliente, cantidad_prestada, cantidad_actual, minimo, maximo FROM carrito_herramientas').fetchall()
    
    productos_list = [list(p) for p in productos]
    return jsonify(productos_list)

@app.route('/guardar_material_estanteria', methods=['POST'])
def guardar_material_estanteria():
    data = request.json
    ubicacion = data.get('ubicacion')
    nombre_producto = data.get('nombre_producto')
    proveedor = data.get('proveedor')
    descripcion = data.get('descripcion')
    marca1 = data.get('marca1')
    marca2 = data.get('marca2')
    marca3 = data.get('marca3')
    codigo1 = data.get('codigo1')
    codigo2 = data.get('codigo2')
    codigo3 = data.get('codigo3')
    valor_unitario1 = data.get('valor_unitario1')
    valor_unitario2 = data.get('valor_unitario2')
    valor_unitario3 = data.get('valor_unitario3')
    valor_unitario4 = data.get('valor_unitario4')
    cantidad_a_prestar = data.get('cantidad_a_prestar')
    cantidad_actual = data.get('cantidad_actual')
    observaciones = data.get('observaciones')
    minimo = data.get('minimo')
    maximo = data.get('maximo')

    # Validación de campos requeridos (Valores unitarios ya NO están aquí)
    if not ubicacion or not nombre_producto or not descripcion or \
       cantidad_a_prestar is None or cantidad_actual is None:
        return jsonify({'message': 'Faltan campos requeridos (Ubicación, Nombre de Producto, Descripción, Cantidades).'}), 400

    db = get_db()
    try:
        db.execute('''
            INSERT INTO material_estanteria (
                ubicacion, nombre_producto, proveedor, descripcion,
                marca1, marca2, marca3,
                codigo1, codigo2, codigo3,
                valor_unitario1, valor_unitario2, valor_unitario3, valor_unitario4,
                cantidad_a_prestar, cantidad_actual, observaciones, minimo, maximo
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) -- Corregido: 17 signos de interrogación para 17 columnas
        ''', (
            ubicacion, nombre_producto, proveedor, descripcion,
            marca1, marca2, marca3,
            codigo1, codigo2, codigo3,
            valor_unitario1, valor_unitario2, valor_unitario3, valor_unitario4,
            cantidad_a_prestar, cantidad_actual, observaciones, minimo, maximo
        ))
        db.commit()
        return jsonify({'message': 'Material de estantería guardado exitosamente!'}), 201
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({'message': f'Error al guardar el material de estantería: {str(e)}'}), 500

@app.route('/obtener_material_estanteria')
def obtener_material_estanteria():
    db = get_db()
    materiales = db.execute('SELECT * FROM material_estanteria').fetchall()
    materiales_list = [list(m) for m in materiales]
    return jsonify(materiales_list)

# NUEVA RUTA: Obtener un solo registro de material de estantería por ID
@app.route('/obtener_material_estanteria/<int:id>', methods=['GET'])
def obtener_material_estanteria_por_id(id):
    db = get_db()
    try:
        cur = db.cursor()
        # La consulta selecciona todas las columnas de la tabla material_estanteria
        cur.execute("SELECT * FROM material_estanteria WHERE id = ?", (id,))
        material = cur.fetchone()
        
        if material:
            # Convierte el resultado a una lista para que sea serializable por jsonify
            # y coincida con el formato que espera el frontend.
            return jsonify(list(material))
        else:
            return jsonify({'message': 'Material no encontrado.'}), 404
    except sqlite3.Error as e:
        return jsonify({'message': f'Error de base de datos: {str(e)}'}), 500
    
@app.route('/actualizar_material_estanteria/<int:id>', methods=['POST'])
@role_required('admin') # <- SOLO ADMINISTRADORES
def actualizar_material_estanteria(id):
    data = request.json
    ubicacion = data.get('ubicacion')
    nombre_producto = data.get('nombre_producto')
    proveedor = data.get('proveedor')
    descripcion = data.get('descripcion')
    marca1 = data.get('marca1')
    marca2 = data.get('marca2')
    marca3 = data.get('marca3')
    codigo1 = data.get('codigo1')
    codigo2 = data.get('codigo2')
    codigo3 = data.get('codigo3')
    valor_unitario1 = data.get('valor_unitario1')
    valor_unitario2 = data.get('valor_unitario2')
    valor_unitario3 = data.get('valor_unitario3')
    valor_unitario4 = data.get('valor_unitario4')
    cantidad_a_prestar = data.get('cantidad_a_prestar')
    cantidad_actual = data.get('cantidad_actual')
    observaciones = data.get('observaciones')
    minimo = data.get('minimo')
    maximo = data.get('maximo')

    # Validación de campos requeridos (Valores unitarios ya NO están aquí)
    if not ubicacion or not nombre_producto or not descripcion or \
       cantidad_a_prestar is None or cantidad_actual is None:
        return jsonify({'message': 'Faltan campos requeridos (Ubicación, Nombre de Producto, Descripción, Cantidades).'}), 400

    db = get_db()
    try:
        cursor = db.execute('''
            UPDATE material_estanteria
            SET ubicacion = ?, nombre_producto = ?, proveedor = ?, descripcion = ?,
                marca1 = ?, marca2 = ?, marca3 = ?,
                codigo1 = ?, codigo2 = ?, codigo3 = ?,
                valor_unitario1 = ?, valor_unitario2 = ?, valor_unitario3 = ?, valor_unitario4 = ?,
                cantidad_a_prestar = ?, cantidad_actual = ?, observaciones = ?,
                minimo =?, maximo =?
            WHERE id = ?
        ''', (
            ubicacion, nombre_producto, proveedor, descripcion,
            marca1, marca2, marca3,
            codigo1, codigo2, codigo3,
            valor_unitario1, valor_unitario2, valor_unitario3, valor_unitario4,
            cantidad_a_prestar, cantidad_actual, observaciones, minimo, maximo, id
        ))
        db.commit()
        if cursor.rowcount == 0:
            return jsonify({'message': 'Material de estantería no encontrado para actualizar.'}), 404
        return jsonify({'message': 'Material de estantería actualizado exitosamente!'}), 200
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({'message': f'Error al actualizar el material de estantería: {str(e)}'}), 500

@app.route('/eliminar_material_estanteria/<int:id>', methods=['POST'])
@role_required('admin') # <- SOLO ADMINISTRADORES
def eliminar_material_estanteria(id):
    db = get_db()
    try:
        cursor = db.execute('DELETE FROM material_estanteria WHERE id = ?', (id,))
        db.commit()
        if cursor.rowcount == 0:
            return jsonify({'message': 'Material de estantería no encontrado para eliminar.'}), 404
        return jsonify({'message': 'Material de estantería eliminado exitosamente!'}), 200
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({'message': f'Error al eliminar el material de estantería: {str(e)}'}), 500

@app.route('/buscar_material_estanteria')
def buscar_material_estanteria():
    query = request.args.get('q', '').strip()
    db = get_db()
    if query:
        search_term = f'%{query}%'
        materiales = db.execute('SELECT * FROM material_estanteria WHERE descripcion LIKE ?', (search_term,)).fetchall()
    else:
        materiales = db.execute('SELECT * FROM material_estanteria').fetchall()
    
    materiales_list = [list(m) for m in materiales]
    return jsonify(materiales_list)

# --- Nueva Ruta para renderizar la página de Papelería ---
@app.route('/papeleria')
def papeleria():
    return render_template('papeleria.html')

# --- Rutas API para Papelería ---

@app.route('/guardar_papeleria', methods=['POST'])
def guardar_papeleria():
    data = request.json
    lugar_zona = data.get('lugar_zona')
    nombre_producto = data.get('nombre_producto')
    medida_descripcion = data.get('medida_descripcion')
    codigo = data.get('codigo')
    valor_unitario = data.get('valor_unitario')
    cantidad_actual = data.get('cantidad_actual')
    cantidad_minima = data.get('cantidad_minima')
    cantidad_maxima = data.get('cantidad_maxima')
    observaciones_requerimientos = data.get('observaciones_requerimientos')

    if not lugar_zona or not nombre_producto or cantidad_actual is None or \
       cantidad_minima is None or cantidad_maxima is None:
        return jsonify({'message': 'Zona, Nombre de Producto y Cantidades son campos requeridos.'}), 400

    db = get_db()
    try:
        db.execute('''
            INSERT INTO papeleria (
                lugar_zona, nombre_producto, medida_descripcion, codigo,
                valor_unitario, cantidad_actual, cantidad_minima, cantidad_maxima,
                observaciones_requerimientos
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            lugar_zona, nombre_producto, medida_descripcion, codigo,
            valor_unitario, cantidad_actual, cantidad_minima, cantidad_maxima,
            observaciones_requerimientos
        ))
        db.commit()
        return jsonify({'message': 'Producto de papelería guardado exitosamente!'}), 201
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({'message': f'Error al guardar el producto de papelería: {str(e)}'}), 500

@app.route('/obtener_papeleria')
def obtener_papeleria():
    db = get_db()
    productos = db.execute('SELECT * FROM papeleria').fetchall()
    productos_list = [list(p) for p in productos]
    return jsonify(productos_list)

@app.route('/obtener_papeleria/<int:id>')
def obtener_papeleria_por_id(id):
    db = get_db()
    producto = db.execute('SELECT * FROM papeleria WHERE id = ?', (id,)).fetchone()
    if producto:
        return jsonify(list(producto))
    return jsonify({'message': 'Producto de papelería no encontrado.'}), 404

@app.route('/actualizar_papeleria/<int:id>', methods=['POST'])
@role_required('admin') # <- SOLO ADMINISTRADORES
def actualizar_papeleria(id):
    data = request.json
    lugar_zona = data.get('lugar_zona')
    nombre_producto = data.get('nombre_producto')
    medida_descripcion = data.get('medida_descripcion')
    codigo = data.get('codigo')
    valor_unitario = data.get('valor_unitario')
    cantidad_actual = data.get('cantidad_actual')
    cantidad_minima = data.get('cantidad_minima')
    cantidad_maxima = data.get('cantidad_maxima')
    observaciones_requerimientos = data.get('observaciones_requerimientos')

    if not lugar_zona or not nombre_producto or cantidad_actual is None or \
       cantidad_minima is None or cantidad_maxima is None:
        return jsonify({'message': 'Zona, Nombre de Producto y Cantidades son campos requeridos.'}), 400

    db = get_db()
    try:
        cursor = db.execute('''
            UPDATE papeleria
            SET lugar_zona = ?, nombre_producto = ?, medida_descripcion = ?, codigo = ?,
                valor_unitario = ?, cantidad_actual = ?, cantidad_minima = ?, cantidad_maxima = ?,
                observaciones_requerimientos = ?
            WHERE id = ?
        ''', (
            lugar_zona, nombre_producto, medida_descripcion, codigo,
            valor_unitario, cantidad_actual, cantidad_minima, cantidad_maxima,
            observaciones_requerimientos, id
        ))
        db.commit()
        if cursor.rowcount == 0:
            return jsonify({'message': 'Producto de papelería no encontrado para actualizar.'}), 404
        return jsonify({'message': 'Producto de papelería actualizado exitosamente!'}), 200
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({'message': f'Error al actualizar el producto de papelería: {str(e)}'}), 500

@app.route('/eliminar_papeleria/<int:id>', methods=['POST'])
@role_required('admin') # <- SOLO ADMINISTRADORES
def eliminar_papeleria(id):
    db = get_db()
    try:
        cursor = db.execute('DELETE FROM papeleria WHERE id = ?', (id,))
        db.commit()
        if cursor.rowcount == 0:
            return jsonify({'message': 'Producto de papelería no encontrado para eliminar.'}), 404
        return jsonify({'message': 'Producto de papelería eliminado exitosamente!'}), 200
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({'message': f'Error al eliminar el producto de papelería: {str(e)}'}), 500

@app.route('/buscar_papeleria')
def buscar_papeleria():
    query = request.args.get('q', '').strip()
    db = get_db()
    if query:
        search_term = f'%{query}%'
        productos = db.execute('SELECT * FROM papeleria WHERE nombre_producto LIKE ? OR medida_descripcion LIKE ?', (search_term, search_term)).fetchall()
    else:
        productos = db.execute('SELECT * FROM papeleria').fetchall()
    
    productos_list = [list(p) for p in productos]
    return jsonify(productos_list)


# API route to get all maintenance records
@app.route('/api/mantenimiento')
def get_mantenimiento_records():
    db = get_db()
    try:
        # Fetch all records from the mantenimiento table
        records = db.execute('SELECT * FROM mantenimiento').fetchall()
        # Convert fetched rows to a list of dictionaries, parsing the status JSON
        records_list = []
        for rec in records:
            record_dict = dict(rec)
            record_dict['status'] = json.loads(record_dict['status'])
            records_list.append(record_dict)
        return jsonify(records_list), 200
    except sqlite3.Error as e:
        return jsonify({'message': f'Error fetching records: {str(e)}'}), 500

# API route to save a new maintenance record
@app.route('/api/mantenimiento/save', methods=['POST'])
def save_mantenimiento_record():
    data = request.get_json()
    machine_name = data.get('machineName')
    week_number = data.get('weekNumber')
    status = json.dumps(data.get('status')) # Convert the status dictionary to a JSON string

    if not machine_name or not week_number or not status:
        return jsonify({'message': 'Missing data'}), 400

    db = get_db()
    try:
        # Check if a record for this machine already exists
        existing_record = db.execute('SELECT * FROM mantenimiento WHERE machine_name = ?', (machine_name,)).fetchone()
        
        if existing_record:
            # If exists, update the status
            existing_status = json.loads(existing_record['status'])
            new_status_to_add = json.loads(status)
            existing_status.update(new_status_to_add)
            updated_status = json.dumps(existing_status)
            db.execute('UPDATE mantenimiento SET status = ? WHERE machine_name = ?', (updated_status, machine_name))
            db.commit()
            return jsonify({'message': 'Record updated successfully!'}), 200
        else:
            # Otherwise, insert a new record
            db.execute('INSERT INTO mantenimiento (machine_name, week_number, status) VALUES (?, ?, ?)',
                       (machine_name, week_number, status))
            db.commit()
            return jsonify({'message': 'Record saved successfully!'}), 201
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({'message': f'Error saving record: {str(e)}'}), 500

# API route to update a maintenance record's status
@app.route('/api/mantenimiento/update', methods=['POST'])
def update_mantenimiento_status():
    data = request.get_json()
    machine_id = data.get('machineId')
    month_week_key = f"{data.get('month')}-{data.get('week')}"
    new_status = data.get('newStatus')
    new_date = data.get('newDate')

    if not machine_id or not month_week_key or not new_status:
        return jsonify({'message': 'Missing data'}), 400

    db = get_db()
    try:
        # Fetch the record to update
        record = db.execute('SELECT status FROM mantenimiento WHERE id = ?', (machine_id,)).fetchone()
        if not record:
            return jsonify({'message': 'Record not found'}), 404

        # Parse the JSON status, update the specific week, and save back
        status_dict = json.loads(record['status'])
        status_dict[month_week_key] = {'status': new_status, 'date': new_date}
        updated_status_json = json.dumps(status_dict)

        db.execute('UPDATE mantenimiento SET status = ? WHERE id = ?', (updated_status_json, machine_id))
        db.commit()
        return jsonify({'message': 'Status updated successfully!'}), 200
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({'message': f'Error updating status: {str(e)}'}), 500

@app.route('/api/mantenimiento/delete/<int:id>', methods=['DELETE'])
@role_required('admin') # <- SOLO ADMINISTRADORES
def delete_maintenance_record(id):
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("DELETE FROM mantenimiento WHERE id = ?", (id,))
        db.commit()
        if cur.rowcount == 0:
            return jsonify({"status": "error", "message": "Registro de mantenimiento no encontrado para eliminar."}), 404
        return jsonify({"status": "success", "message": "Registro de mantenimiento eliminado exitosamente!"}), 200
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({"status": "error", "message": f"Error al eliminar registro de mantenimiento: {str(e)}"}), 500

@app.route('/api/mantenimiento/reorder', methods=['POST'])
def reorder_maintenance_records():
    data = request.json
    if not data:
        return jsonify({"message": "No data provided"}), 400

    conn = get_db()
    try:
        for item in data:
            record_id = item.get('id')
            order_index = item.get('order_index')
            if record_id is not None and order_index is not None:
                conn.execute(
                    'UPDATE mantenimiento SET order_index = ? WHERE id = ?',
                    (order_index, record_id)
                )
        conn.commit()
        return jsonify({"message": "Order updated successfully"}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"message": f"Error saving order: {e}"}), 500

@app.route('/api/mantenimiento/<int:year>', methods=['GET'])
def get_mantenimiento_by_year(year):
    # ... El código de filtrado que te di anteriormente, ya implementado...
    db = get_db()
    try:
        records = db.execute('SELECT * FROM mantenimiento WHERE year = ? ORDER BY order_index', (year,)).fetchall()
        
        records_list = []
        for rec in records:
            record_dict = dict(rec)
            record_dict['status'] = json.loads(record_dict['status'])
            records_list.append(record_dict)
            
        return jsonify(records_list), 200
    except sqlite3.Error as e:
        return jsonify({'message': f'Error fetching records for year {year}: {str(e)}'}), 500

@app.route('/obtener_partes_piezas', methods=['GET'])
def get_partes_piezas():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM partes_piezas")
    partes = cur.fetchall()
    return jsonify(partes)

# Nuevas rutas para AMEF
@app.route('/api/amef/revisions/<string:no_parte_interno>', methods=['GET'])
def get_amef_revisions(no_parte_interno):
    db = get_db()
    cur = db.cursor()
    # Se agrega ORDER BY para obtener las revisiones más recientes primero
    cur.execute("SELECT * FROM amef_revisions WHERE no_parte_interno = ? ORDER BY id DESC", (no_parte_interno,))
    revisions = cur.fetchall()
    return jsonify([dict(row) for row in revisions])

@app.route('/api/amef/revision', methods=['POST'])
def add_amef_revision():
    data = request.json
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute('''
            INSERT INTO amef_revisions (
                no_parte_interno, no_parte_cliente, revision, descripcion, autor, equipo, sev, 
                class, causas, occ, control_preventivo, control_deteccion, det, rpn, acciones, responsables
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data.get('no_parte_interno'),
            data.get('no_parte_cliente'), # Campo añadido para consistencia
            data.get('revision'), 
            data.get('descripcion'), 
            data.get('autor'),
            data.get('equipo'), 
            data.get('sev'), 
            data.get('class'), 
            data.get('causas'), 
            data.get('occ'),
            data.get('control_preventivo'), 
            data.get('control_deteccion'), 
            data.get('det'), 
            data.get('rpn'),
            data.get('acciones'), 
            data.get('responsables')
        ))
        db.commit()
        return jsonify({"status": "success", "message": "Revisión de AMEF agregada exitosamente!"}), 201
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({"status": "error", "message": f"Error al agregar revisión de AMEF: {str(e)}"}), 500

@app.route('/api/amef/revision/<int:revision_id>', methods=['PUT'])
def update_amef_revision(revision_id):
    data = request.json
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute('''
            UPDATE amef_revisions
            SET
                no_parte_interno=?, no_parte_cliente=?, revision=?, descripcion=?, autor=?, equipo=?, sev=?, 
                class=?, causas=?, occ=?, control_preventivo=?, control_deteccion=?, det=?, rpn=?, acciones=?, 
                responsables=?
            WHERE id = ?
        ''', (
            data.get('no_parte_interno'), # Se asegura de que se actualice este campo
            data.get('no_parte_cliente'), # Se asegura de que se actualice este campo
            data.get('revision'), data.get('descripcion'), data.get('autor'), data.get('equipo'),
            data.get('sev'), data.get('class'), data.get('causas'), data.get('occ'),
            data.get('control_preventivo'), data.get('control_deteccion'), data.get('det'), data.get('rpn'),
            data.get('acciones'), data.get('responsables'), revision_id
        ))
        db.commit()
        if cur.rowcount == 0:
            return jsonify({"status": "error", "message": "Revisión de AMEF no encontrada para actualizar."}), 404
        return jsonify({"status": "success", "message": "Revisión de AMEF actualizada exitosamente!"}), 200
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({"status": "error", "message": f"Error al actualizar revisión de AMEF: {str(e)}"}), 500

@app.route('/api/amef/revision/<int:revision_id>', methods=['DELETE'])
def delete_amef_revision(revision_id):
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("DELETE FROM amef_revisions WHERE id = ?", (revision_id,))
        db.commit()
        if cur.rowcount == 0:
            return jsonify({"status": "error", "message": "Revisión de AMEF no encontrada para eliminar."}), 404
        return jsonify({"status": "success", "message": "Revisión de AMEF eliminada exitosamente!"}), 200
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({"status": "error", "message": f"Error al eliminar revisión de AMEF: {str(e)}"}), 500

@app.route('/api/partes/add', methods=['POST'])
def add_parte_pieza():
    data = request.json
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute('''
            INSERT INTO partes_piezas (no_parte_interno, no_parte_cliente, descripcion)
            VALUES (?, ?, ?)
        ''', (data.get('no_parte_interno'), data.get('no_parte_cliente'), data.get('descripcion')))
        db.commit()
        return jsonify({"status": "success", "message": "Parte/pieza agregada exitosamente!"}), 201
    except sqlite3.IntegrityError as e:
        db.rollback()
        return jsonify({"status": "error", "message": "Ya existe una parte/pieza con ese número interno."}), 409
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({"status": "error", "message": f"Error al agregar parte/pieza: {str(e)}"}), 500

@app.route('/guardar_archivo', methods=['POST'])
def guardar_archivo():
    """
    Maneja la subida de archivos PDF y Excel.
    """
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'No se encontró el archivo en la petición.'}), 400

    file = request.files['file']
    internal_part_number = request.form.get('partNumber')
    document_type = request.form.get('documentType')

    if file.filename == '':
        return jsonify({'success': False, 'message': 'No se seleccionó ningún archivo.'}), 400

    # Define the allowed extensions
    ALLOWED_EXTENSIONS = {'pdf', 'xls', 'xlsx'}
    filename_parts = file.filename.rsplit('.', 1)
    if len(filename_parts) > 1:
        extension = filename_parts[1].lower()
    else:
        extension = ''

    if file and extension in ALLOWED_EXTENSIONS:
        # Create a folder for the part number if it doesn't exist
        part_folder = os.path.join(app.config['UPLOAD_FOLDER'], internal_part_number)
        if not os.path.exists(part_folder):
            os.makedirs(part_folder)

        # Create a folder for the document type
        doc_folder = os.path.join(part_folder, document_type.replace(" ", "_"))
        if not os.path.exists(doc_folder):
            os.makedirs(doc_folder)

        # Save the file
        filename = file.filename
        file_path = os.path.join(doc_folder, filename)
        file.save(file_path)

        return jsonify({'success': True, 'message': 'Archivo guardado con éxito.'}), 200

    else:
        return jsonify({'success': False, 'message': 'Tipo de archivo no permitido. Solo se aceptan archivos PDF y Excel.'}), 400

@app.route('/obtener_archivos', methods=['GET'])
def obtener_archivos():
    """
    Obtiene la lista de archivos para un No. de Parte y tipo de documento.
    """
    internal_part_number = request.args.get('partNumber')
    document_type = request.args.get('docType')

    if not internal_part_number or not document_type:
        return jsonify({'success': False, 'message': 'Faltan parámetros.'}), 400

    # Ensure the document type path is valid and sanitized
    safe_doc_type = document_type.replace(" ", "_")
    doc_folder = os.path.join(app.config['UPLOAD_FOLDER'], internal_part_number, safe_doc_type)

    if not os.path.exists(doc_folder):
        return jsonify({'success': True, 'files': []}), 200 # Return an empty list if the folder doesn't exist

    files = [f for f in os.listdir(doc_folder) if os.path.isfile(os.path.join(doc_folder, f))]
    
    # Return a list of file URLs
    file_urls = [f"/archivos/{internal_part_number}/{safe_doc_type}/{file}" for file in files]
    
    return jsonify({'success': True, 'files': files, 'urls': file_urls}), 200

# Endpoint para servir los archivos
@app.route('/archivos/<path:filename>')
def serve_files(filename):
    """
    Sirve los archivos guardados desde el directorio de subidas.
    """
    # This is a critical security step to prevent directory traversal attacks.
    # It ensures the user can only access files within the UPLOAD_FOLDER.
    # We reconstruct the path to ensure it's safe.
    parts = filename.split('/')
    if len(parts) < 3:
        return "Invalid path", 400
    
    internal_part_number = parts[0]
    doc_type = parts[1]
    file_name = parts[2]
    
    directory = os.path.join(app.config['UPLOAD_FOLDER'], internal_part_number, doc_type)
    
    return send_from_directory(directory, file_name)

@app.route('/borrar_archivo', methods=['POST'])
def borrar_archivo():
    """
    Maneja la eliminación de archivos.
    """
    data = request.get_json()
    internal_part_number = data.get('partNumber')
    document_type = data.get('documentType')
    file_name = data.get('fileName')

    if not internal_part_number or not document_type or not file_name:
        return jsonify({'success': False, 'message': 'Faltan parámetros.'}), 400

    # Sanitize the path to prevent directory traversal attacks
    file_path = os.path.join(
        app.config['UPLOAD_FOLDER'],
        internal_part_number,
        document_type,
        file_name
    )

    # Check if the file exists and is a valid file to prevent errors and unauthorized access
    if os.path.exists(file_path) and os.path.isfile(file_path):
        try:
            os.remove(file_path)
            return jsonify({'success': True, 'message': 'Archivo borrado con éxito.'}), 200
        except OSError as e:
            return jsonify({'success': False, 'message': f'Error al borrar el archivo: {e}'}), 500
    else:
        return jsonify({'success': False, 'message': 'El archivo no se encontró o la ruta es inválida.'}), 404

@app.route('/agregar_columna', methods=['POST'])
def agregar_columna():
    try:
        data = request.json
        column_name = data.get('columnName')
        if not column_name:
            return jsonify({'success': False, 'message': 'El nombre de la columna no puede estar vacío.'}), 400

        dynamic_columns = load_dynamic_columns()
        
        # Evitar columnas duplicadas
        if column_name in dynamic_columns:
            return jsonify({'success': False, 'message': f'La columna "{column_name}" ya existe.'}), 409
        
        dynamic_columns.append(column_name)
        save_dynamic_columns(dynamic_columns)
        
        return jsonify({'success': True, 'message': f'Columna "{column_name}" agregada con éxito.'})
    
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error en el servidor: {str(e)}'}), 500


@app.route('/borrar_archivos_columna', methods=['DELETE'])
@role_required('admin') # <- SOLO ADMINISTRADORES
def borrar_archivos_columna():
    try:
        data = request.get_json()
        part_number = data.get('partNumber')
        document_type = data.get('documentType')

        if not part_number or not document_type:
            return jsonify({'success': False, 'message': 'Faltan datos en la solicitud.'}), 400

        # Aquí va la lógica para borrar los archivos
        # Por ejemplo, encontrar y eliminar todos los archivos
        # en la carpeta del número de parte y del tipo de documento.
        #
        # Por ahora, solo simularé el borrado exitoso.
        print(f"Borrando archivos para No. de Parte: {part_number} y Tipo de Documento: {document_type}")
        
        # Simulación de un borrado exitoso
        return jsonify({'success': True, 'message': 'Archivos borrados con éxito.'})

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/check_scrap', methods=['GET'])
def check_scrap():
    try:
        db = get_db()
        cursor = db.cursor()
        # Muestra los últimos 10 registros para verificar que se están guardando
        cursor.execute("SELECT cantidad_laton, scrap, fecha_orden FROM materiales ORDER BY rowid DESC LIMIT 10")
        results = cursor.fetchall()

        # Formatea los resultados para que se muestren en el navegador
        data_list = [dict(row) for row in results]

        return jsonify({
            'success': True,
            'message': 'Últimos 10 registros de scrap:',
            'data': data_list
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error en el servidor: {str(e)}'}), 500
    
# --- Rutas para la tabla de Eficiencia ---

@app.route('/guardar_eficiencia', methods=['POST'])
def guardar_eficiencia():
    data = request.get_json()
    db = get_db()
    cur = db.cursor()
    try:
        fecha_str = data['fecha']
        fecha_dt = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        semana_iso = fecha_dt.isocalendar()[1]
        anio = fecha_dt.year

        cur.execute('''
            INSERT INTO eficiencia (maquina, no_parte_interno, nombre_operador, piezas_programadas, piezas_reales, scrap, fecha, semana, anio)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['maquina'],
            data['noParteInterno'],
            data['nombreOperador'],
            data['programado'],
            data['real'],
            data['scrap'],
            data['fecha'],
            semana_iso, # <-- Se guarda el número de semana
            anio        # <-- Se guarda el año
        ))
        db.commit()
        return jsonify({"status": "success", "message": "Datos de eficiencia guardados exitosamente."}), 201
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({"status": "error", "message": f"Error al guardar los datos: {str(e)}"}), 500

@app.route('/obtener_eficiencias', methods=['GET'])
def obtener_eficiencias():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM eficiencia ORDER BY fecha DESC")
    resultados = [dict(row) for row in cur.fetchall()]
    return jsonify(resultados)

@app.route('/actualizar_eficiencia/<int:id>', methods=['POST'])
@role_required('admin') # <- SOLO ADMINISTRADORES
def actualizar_eficiencia(id):
    data = request.get_json()
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute('''
            UPDATE eficiencia SET
                maquina = ?,
                no_parte_interno = ?,
                nombre_operador = ?,
                piezas_programadas = ?,
                piezas_reales = ?,
                scrap = ?,
                fecha = ?
            WHERE id = ?
        ''', (
            data['maquina'],
            data['noParteInterno'],
            data['nombreOperador'],
            data['programado'],
            data['real'],
            data['scrap'],
            data['fecha'],
            id
        ))
        db.commit()
        if cur.rowcount == 0:
            return jsonify({"status": "error", "message": "Registro no encontrado para actualizar."}), 404
        return jsonify({"status": "success", "message": "Registro actualizado exitosamente."}), 200
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({"status": "error", "message": f"Error al actualizar el registro: {str(e)}"}), 500

# --- Nuevas rutas para cargar datos específicos ---

@app.route('/obtener_anios_eficiencia', methods=['GET'])
def obtener_anios_eficiencia():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT DISTINCT anio FROM eficiencia ORDER BY anio DESC")
    anios = [row['anio'] for row in cur.fetchall()]
    return jsonify(anios)

@app.route('/obtener_semanas_por_anio/<int:anio>', methods=['GET'])
def obtener_semanas_por_anio(anio):
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT DISTINCT semana FROM eficiencia WHERE anio = ? ORDER BY semana ASC", (anio,))
    semanas = [row['semana'] for row in cur.fetchall()]
    return jsonify(semanas)

@app.route('/obtener_eficiencias_semanal/<int:anio>/<int:semana>', methods=['GET'])
def obtener_eficiencias_semanal(anio, semana):
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM eficiencia WHERE anio = ? AND semana = ?", (anio, semana))
    resultados = [dict(row) for row in cur.fetchall()]
    return jsonify(resultados)


@app.route('/eliminar_eficiencia/<int:id>', methods=['POST'])
@role_required('admin') # <- SOLO ADMINISTRADORES
def eliminar_eficiencia(id):
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("DELETE FROM eficiencia WHERE id = ?", (id,))
        db.commit()
        if cur.rowcount == 0:
            return jsonify({"status": "error", "message": "Registro no encontrado para eliminar."}), 404
        return jsonify({"status": "success", "message": "Registro eliminado exitosamente."}), 200
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({"status": "error", "message": f"Error al eliminar el registro: {str(e)}"}), 500

@app.route('/obtener_maquinas', methods=['GET'])
def obtener_maquinas():
    db = get_db()
    cur = db.cursor()
    # Select distinct machines and their latest standard
    cur.execute("SELECT maquina, no_parte_interno, estandar FROM eficiencia GROUP BY maquina, no_parte_interno")
    resultados = [dict(row) for row in cur.fetchall()]
    return jsonify(resultados)

# CRUD routes for 'disponibilidad' table
@app.route('/guardar_disponibilidad', methods=['POST'])
def guardar_disponibilidad():
    data = request.get_json()
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute('''
            INSERT INTO disponibilidad (maquina, no_parte_interno, operador, estandar, causa, minutos_perdidos, fecha)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['maquina'],
            data['noParteInterno'],
            data['operador'],
            data['estandarParo'],
            data['causaParo'],
            data['minutos'],
            data['fecha']
        ))
        db.commit()
        return jsonify({"status": "success", "message": "Datos de disponibilidad guardados exitosamente."}), 201
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({"status": "error", "message": f"Error al guardar los datos: {str(e)}"}), 500
    
@app.route('/obtener_disponibilidades', methods=['GET'])
def obtener_disponibilidades():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM disponibilidad ORDER BY fecha DESC")
    resultados = [dict(row) for row in cur.fetchall()]
    return jsonify(resultados)

import sqlite3
from flask import Flask, request, jsonify

# (Your existing Flask setup and get_db function here)

@app.route('/actualizar_disponibilidad/<int:id>', methods=['POST'])
@role_required('admin') # <- SOLO ADMINISTRADORES
def actualizar_disponibilidad(id):
    data = request.get_json()
    db = get_db()
    cur = db.cursor()
    try:
        # Corrected variable names to match the incoming JSON data
        maquina = data.get('maquina')
        no_parte_interno = data.get('noParteInterno')
        operador = data.get('operador')
        estandar = data.get('estandarParo')
        causa = data.get('causaParo')
        minutos_perdidos = data.get('minutos')
        fecha = data.get('fecha')

        cur.execute('''
            UPDATE disponibilidad SET
                maquina = ?,
                no_parte_interno = ?,
                operador = ?,
                estandar = ?,
                causa = ?,
                minutos_perdidos = ?,
                fecha = ?
            WHERE id = ?
        ''', (
            maquina,
            no_parte_interno,
            operador,
            estandar,
            causa,
            minutos_perdidos,
            fecha,
            id
        ))
        db.commit()

        if cur.rowcount == 0:
            return jsonify({"status": "error", "message": "Registro no encontrado para actualizar."}), 404
        return jsonify({"status": "success", "message": "Registro actualizado exitosamente."}), 200

    except KeyError as e:
        return jsonify({"status": "error", "message": f"Falta el campo requerido: {str(e)}"}), 400
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({"status": "error", "message": f"Error de base de datos: {str(e)}"}), 500
    
@app.route('/eliminar_disponibilidad/<int:id>', methods=['POST'])
@role_required('admin') # <- SOLO ADMINISTRADORES
def eliminar_disponibilidad(id):
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("DELETE FROM disponibilidad WHERE id = ?", (id,))
        db.commit()
        if cur.rowcount == 0:
            return jsonify({"status": "error", "message": "Registro no encontrado para eliminar."}), 404
        return jsonify({"status": "success", "message": "Registro eliminado exitosamente."}), 200
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({"status": "error", "message": f"Error al eliminar el registro: {str(e)}"}), 500
    
@app.route('/obtener_anios_disponibilidad', methods=['GET'])
def obtener_anios_disponibilidad():
    """
    Obtiene la lista de años únicos registrados en la tabla de DISPONIBILIDAD.
    """
    db = get_db()
    cur = db.cursor()
    # CONSULTA CORREGIDA: Apunta a la tabla 'disponibilidad'
    cur.execute("SELECT DISTINCT anio FROM disponibilidad ORDER BY anio DESC")
    anios = [row['anio'] for row in cur.fetchall()]
    return jsonify(anios)

@app.route('/obtener_semanas_disponibilidad_por_anio/<int:anio>', methods=['GET'])
def obtener_semanas_disponibilidad_por_anio(anio):
    """
    Obtiene la lista de semanas únicas para un año específico 
    registradas en la tabla de DISPONIBILIDAD.
    """
    db = get_db()
    cur = db.cursor()
    # CONSULTA CORREGIDA: Apunta a la tabla 'disponibilidad'
    cur.execute("SELECT DISTINCT semana FROM disponibilidad WHERE anio = ? ORDER BY semana ASC", (anio,))
    semanas = [row['semana'] for row in cur.fetchall()]
    return jsonify(semanas)

@app.route('/obtener_disponibilidad_semanal/<int:anio>/<int:semana>', methods=['GET'])
def obtener_disponibilidad_semanal(anio, semana):
    """
    Obtiene todos los registros de DISPONIBILIDAD para el año y semana específicos.
    """
    db = get_db()
    cur = db.cursor()
    # CONSULTA CORREGIDA: Apunta a la tabla 'disponibilidad'
    cur.execute("SELECT * FROM disponibilidad WHERE anio = ? AND semana = ?", (anio, semana))
    resultados = [dict(row) for row in cur.fetchall()]
    return jsonify(resultados)


# --- ENDPOINT PARA INDICADORES DE TIEMPO MUERTO Y SCRAP ---
@app.route('/obtener_indicadores_maquinas', methods=['GET'])
def obtener_indicadores_maquinas():
    try:
        db = get_db()
        cursor = db.cursor()

        # Obtener datos de Disponibilidad (Tiempo muerto) por máquina
        cursor.execute("""
            SELECT
                maquina,
                SUM(minutos_perdidos) AS total_minutos_paro
            FROM disponibilidad
            GROUP BY maquina
        """)
        # Corregido para usar acceso directo por columna y manejar nulos
        disponibilidad_data = {row['maquina']: row['total_minutos_paro'] or 0 for row in cursor.fetchall()}

        # Obtener datos de Eficiencia (Scrap) por máquina
        cursor.execute("""
            SELECT
                maquina,
                SUM(piezas_reales) AS total_piezas_reales,
                SUM(scrap) AS total_scrap
            FROM eficiencia
            GROUP BY maquina
        """)
        # Corregido para usar acceso directo por columna y manejar nulos
        eficiencia_data = {row['maquina']: {'total_piezas_reales': row['total_piezas_reales'] or 0, 'total_scrap': row['total_scrap'] or 0} for row in cursor.fetchall()}
        
        # Combinar los datos y calcular los indicadores
        indicadores = []
        todas_las_maquinas = set(disponibilidad_data.keys()) | set(eficiencia_data.keys())
        
        # Asumiendo 8 horas (480 minutos) por turno, 3 turnos al día, 30 días
        # Ajusta esta cifra si el tiempo programado de tu empresa es diferente
        minutos_programados = 480 * 3 * 5 
        
        for maquina in todas_las_maquinas:
            minutos_paro = disponibilidad_data.get(maquina, 0)
            
            eficiencia_maquina = eficiencia_data.get(maquina, {})
            piezas_reales = eficiencia_maquina.get('total_piezas_reales', 0)
            piezas_scrap = eficiencia_maquina.get('total_scrap', 0)
            
            piezas_producidas = piezas_reales + piezas_scrap
            
            tiempo_muerto_porcentaje = (minutos_paro / minutos_programados) * 100 if minutos_programados > 0 else 0
            scrap_porcentaje = (piezas_scrap / piezas_producidas) * 100 if piezas_producidas > 0 else 0

            indicadores.append({
                'nombre': maquina,
                'minutos_paro': minutos_paro,
                'minutos_programados': minutos_programados,
                'piezas_scrap': piezas_scrap,
                'piezas_producidas': piezas_producidas,
                'objetivo_tiempo_muerto': 20,  # Objetivo de ejemplo
                'objetivo_scrap': 2.5           # Objetivo de ejemplo
            })
        
        return jsonify(indicadores), 200

    except Exception as e:
        print("Error en el endpoint de indicadores:", e)
        return jsonify({"error": f"Error en el servidor al obtener los indicadores: {str(e)}"}), 500

@app.route("/login", methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        
        if user and check_password_hash(user['password_hash'], password):
            # Iniciar sesión: Guardar información del usuario en la sesión
            session['logged_in'] = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            
            # Redirigir a la página principal o de almacenamiento
            return redirect(url_for('index')) 
        else:
            return render_template('login.html', error='Credenciales incorrectas.')
            
    return render_template('login.html')

@app.route("/logout")
def logout():
    session.pop('logged_in', None)
    session.pop('user_id', None)
    session.pop('username', None)
    session.pop('role', None)
    return redirect(url_for('login'))


@app.route("/register", methods=['GET', 'POST'])
def register():
    # Solo permite el registro si es una petición GET (mostrar formulario)
    if request.method == 'GET':
        return render_template('register.html')
    
    # Si es POST, procesa el formulario
    elif request.method == 'POST':
        data = request.form
        username = data.get('username')
        password = data.get('password')
        # Por defecto, los usuarios registrados desde el formulario son 'employee'. 
        # Si quieres que solo un admin pueda crear nuevos admins, haz que solo 'admin' pueda acceder a este endpoint.
        role = data.get('role', 'employee') 

        if not username or not password:
            return "Nombre de usuario y contraseña son requeridos", 400

        db = get_db()
        try:
            # Hashear la contraseña antes de guardarla
            password_hash = generate_password_hash(password)
            
            db.execute('''
                INSERT INTO users (username, password_hash, role) 
                VALUES (?, ?, ?)
            ''', (username, password_hash, role))
            db.commit()
            
            return redirect(url_for('login')) # Redirigir al login después del registro
        except sqlite3.IntegrityError:
            return "El nombre de usuario ya existe.", 409
        except sqlite3.Error as e:
            db.rollback()
            return f"Error al registrar: {str(e)}", 500
        


if __name__ == '__main__':
    reset_weekly_data()
    with app.app_context():
        init_db()
    app.run(host = '0.0.0.0', port=5000, debug=True)
